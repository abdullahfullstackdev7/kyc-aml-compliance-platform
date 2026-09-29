"""Applicant self-service portal. A "customer" role JWT may only ever touch
the Customer/Application rows linked to its own user_id.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_principal, get_tenant_scoped_db
from backend.app.core.security.blind_index import compute_blind_index
from backend.app.core.security.encryption import encrypt_pii
from backend.app.core.security.permissions import Principal
from backend.app.models.cases import Case
from backend.app.models.onboarding import Application, Customer, Document, DocumentCheck
from backend.app.schemas.onboarding import (
    ApplicationCreateRequest,
    ApplicationResponse,
    ApplicationStatusResponse,
    ApplicationUpdateRequest,
    DocumentCheckResponse,
    DocumentUploadResponse,
)
from backend.app.services.onboarding import documents as doc_service
from backend.app.services.onboarding.screening_integration import run_screening_and_route
from backend.app.services.onboarding.state_machine import InvalidTransitionError, transition

router = APIRouter(prefix="/portal", tags=["portal"])


def _require_tenant_id(principal: Principal) -> int:
    if principal.tenant_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A tenant-scoped account is required")
    return principal.tenant_id


def _require_own_application(db: Session, principal: Principal, application_id: int) -> Application:
    application = db.execute(
        select(Application).where(Application.id == application_id)
    ).scalar_one_or_none()
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    customer = db.execute(
        select(Customer).where(Customer.id == application.customer_id)
    ).scalar_one_or_none()
    if customer is None or customer.user_id != principal.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your application")
    return application


@router.post(
    "/applications", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED
)
def create_application(
    body: ApplicationCreateRequest,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_tenant_scoped_db),
) -> ApplicationResponse:
    tenant_id = _require_tenant_id(principal)

    existing = db.execute(
        select(Customer).where(Customer.user_id == principal.user_id)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "An application already exists for this account"
        )

    customer = Customer(
        tenant_id=tenant_id,
        user_id=principal.user_id,
        customer_type=body.customer_type,
        full_name_encrypted=encrypt_pii(db, tenant_id, body.full_name),
        full_name_blind_index=compute_blind_index(body.full_name),
        dob_encrypted=encrypt_pii(db, tenant_id, body.date_of_birth.isoformat())
        if body.date_of_birth
        else None,
        nationality=body.nationality,
        residence_country=body.residence_country,
        occupation=body.occupation,
        source_of_funds=body.source_of_funds,
        expected_monthly_volume=body.expected_monthly_volume,
    )
    db.add(customer)
    db.flush()

    application = Application(tenant_id=tenant_id, customer_id=customer.id, state="DRAFT")
    db.add(application)
    db.commit()

    return ApplicationResponse(
        id=application.id,
        customer_id=customer.id,
        state=application.state,
        created_at=application.created_at,
        submitted_at=None,
        decided_at=None,
    )


@router.put("/applications/{application_id}", response_model=ApplicationResponse)
def update_application(
    application_id: int,
    body: ApplicationUpdateRequest,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_tenant_scoped_db),
) -> ApplicationResponse:
    tenant_id = _require_tenant_id(principal)
    application = _require_own_application(db, principal, application_id)
    if application.state != "DRAFT":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a draft application can be edited")

    customer = db.execute(
        select(Customer).where(Customer.id == application.customer_id)
    ).scalar_one()
    if body.full_name is not None:
        customer.full_name_encrypted = encrypt_pii(db, tenant_id, body.full_name)
        customer.full_name_blind_index = compute_blind_index(body.full_name)
    if body.date_of_birth is not None:
        customer.dob_encrypted = encrypt_pii(db, tenant_id, body.date_of_birth.isoformat())
    for field in (
        "nationality",
        "residence_country",
        "occupation",
        "source_of_funds",
        "expected_monthly_volume",
    ):
        value = getattr(body, field)
        if value is not None:
            setattr(customer, field, value)

    db.commit()
    return ApplicationResponse(
        id=application.id,
        customer_id=customer.id,
        state=application.state,
        created_at=application.created_at,
        submitted_at=application.submitted_at,
        decided_at=application.decided_at,
    )


@router.post("/applications/{application_id}/documents", response_model=DocumentUploadResponse)
async def upload_document(
    application_id: int,
    doc_type: str,
    file: UploadFile,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_tenant_scoped_db),
) -> DocumentUploadResponse:
    tenant_id = _require_tenant_id(principal)
    application = _require_own_application(db, principal, application_id)
    content = await file.read()

    customer = db.execute(
        select(Customer).where(Customer.id == application.customer_id)
    ).scalar_one()
    from backend.app.core.security.encryption import decrypt_pii

    full_name = decrypt_pii(db, tenant_id, customer.full_name_encrypted)
    dob_iso = decrypt_pii(db, tenant_id, customer.dob_encrypted) if customer.dob_encrypted else None

    document = Document(
        tenant_id=tenant_id,
        application_id=application_id,
        doc_type=doc_type,
        storage_path=f"encrypted://{application_id}/{file.filename}",
        mime_type=file.content_type,
        size_bytes=len(content),
    )
    db.add(document)
    db.flush()

    results = doc_service.run_document_verification(
        content,
        declared_mime=file.content_type,
        application_full_name=full_name,
        application_dob_iso=dob_iso,
        application_nationality=customer.nationality,
    )
    for r in results:
        db.add(
            DocumentCheck(
                tenant_id=tenant_id,
                document_id=document.id,
                check_type=r.check_type,
                result=r.result,
                details=r.details,
            )
        )
    db.commit()

    overall = (
        "fail"
        if any(r.result == "fail" for r in results)
        else ("warn" if any(r.result == "warn" for r in results) else "pass")
    )
    return DocumentUploadResponse(
        document_id=document.id,
        checks=[
            DocumentCheckResponse(check_type=r.check_type, result=r.result, details=r.details)
            for r in results
        ],
        overall_status=overall,
    )


@router.post("/applications/{application_id}/submit", response_model=ApplicationStatusResponse)
def submit_application(
    application_id: int,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_tenant_scoped_db),
) -> ApplicationStatusResponse:
    tenant_id = _require_tenant_id(principal)
    application = _require_own_application(db, principal, application_id)
    customer = db.execute(
        select(Customer).where(Customer.id == application.customer_id)
    ).scalar_one()

    try:
        transition(db, application, "SUBMITTED", actor_id=principal.user_id, actor_role="customer")
        transition(
            db, application, "DOCS_PROCESSING", actor_id=principal.user_id, actor_role="customer"
        )
    except InvalidTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    doc_status = (
        db.execute(
            select(DocumentCheck.result)
            .join(Document, Document.id == DocumentCheck.document_id)
            .where(Document.application_id == application_id)
        )
        .scalars()
        .all()
    )

    if doc_status and "fail" in doc_status:
        transition(
            db, application, "DOCS_FAILED", actor_id=principal.user_id, actor_role="customer"
        )
        db.commit()
        return ApplicationStatusResponse(
            id=application.id,
            state=application.state,
            tier=None,
            case_id=None,
            submitted_at=application.submitted_at,
            decided_at=application.decided_at,
        )

    transition(db, application, "DOCS_VERIFIED", actor_id=principal.user_id, actor_role="customer")
    transition(db, application, "SCREENING", actor_id=principal.user_id, actor_role="customer")

    from backend.app.core.security.encryption import decrypt_pii

    full_name = decrypt_pii(db, tenant_id, customer.full_name_encrypted)
    _run, case = run_screening_and_route(db, application, customer, full_name)
    db.commit()

    return ApplicationStatusResponse(
        id=application.id,
        state=application.state,
        tier=case.tier,
        case_id=case.id,
        submitted_at=application.submitted_at,
        decided_at=application.decided_at,
    )


@router.get("/applications/{application_id}/status", response_model=ApplicationStatusResponse)
def application_status(
    application_id: int,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_tenant_scoped_db),
) -> ApplicationStatusResponse:
    application = _require_own_application(db, principal, application_id)
    case = db.execute(
        select(Case).where(Case.application_id == application_id)
    ).scalar_one_or_none()
    return ApplicationStatusResponse(
        id=application.id,
        state=application.state,
        tier=case.tier if case else None,
        case_id=case.id if case else None,
        submitted_at=application.submitted_at,
        decided_at=application.decided_at,
    )
