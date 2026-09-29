"""Document verification pipeline. See PROJECT_PLAN.md Phase 5.2.

Runs synchronously within the submit request in this phase (no Celery
broker is stood up yet); each check writes one `document_checks` row with
result pass|warn|fail so the outcome is auditable per-check, not just as a
single pass/fail verdict.
"""

from __future__ import annotations

import datetime as dt
import io

import cv2
import numpy as np
from PIL import Image
from rapidfuzz import fuzz

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/tiff"}

BLUR_VARIANCE_THRESHOLD = 100.0
MIN_RESOLUTION_PX = 600
NAME_MATCH_THRESHOLD = 90

_FACE_CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"  # type: ignore[attr-defined]


class DocumentCheckResult:
    def __init__(self, check_type: str, result: str, details: dict):
        self.check_type = check_type
        self.result = result  # pass | warn | fail
        self.details = details


def check_mime_and_size(content: bytes, declared_mime: str | None) -> DocumentCheckResult:
    if len(content) > MAX_FILE_SIZE_BYTES:
        return DocumentCheckResult(
            "mime_and_size",
            "fail",
            {"reason": "file exceeds 10 MB limit", "size_bytes": len(content)},
        )

    detected_mime = _detect_mime(content)
    if detected_mime not in ALLOWED_MIME_TYPES:
        return DocumentCheckResult(
            "mime_and_size",
            "fail",
            {"reason": "unsupported file type", "detected_mime": detected_mime},
        )
    if declared_mime and declared_mime != detected_mime:
        return DocumentCheckResult(
            "mime_and_size",
            "warn",
            {
                "reason": "declared MIME does not match file content",
                "declared": declared_mime,
                "detected": detected_mime,
            },
        )
    return DocumentCheckResult("mime_and_size", "pass", {"detected_mime": detected_mime})


def _detect_mime(content: bytes) -> str:
    try:
        import magic

        return magic.from_buffer(content, mime=True)
    except Exception:  # noqa: BLE001 - libmagic unavailable in some environments; fall back
        try:
            image = Image.open(io.BytesIO(content))
            return Image.MIME.get(image.format or "", "application/octet-stream")
        except Exception:  # noqa: BLE001
            return "application/octet-stream"


def check_image_quality(content: bytes) -> DocumentCheckResult:
    array = np.frombuffer(content, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_GRAYSCALE)
    if image is None:
        return DocumentCheckResult("image_quality", "fail", {"reason": "could not decode image"})

    height, width = image.shape[:2]
    if min(height, width) < MIN_RESOLUTION_PX:
        return DocumentCheckResult(
            "image_quality",
            "fail",
            {"reason": "resolution below minimum", "width": width, "height": height},
        )

    blur_variance = cv2.Laplacian(image, cv2.CV_64F).var()
    if blur_variance < BLUR_VARIANCE_THRESHOLD:
        return DocumentCheckResult(
            "image_quality",
            "fail",
            {"reason": "image too blurry", "blur_variance": round(float(blur_variance), 1)},
        )

    overexposed_ratio = float(np.mean(image > 250))
    if overexposed_ratio > 0.15:
        return DocumentCheckResult(
            "image_quality",
            "warn",
            {"reason": "possible glare", "overexposed_ratio": round(overexposed_ratio, 3)},
        )

    return DocumentCheckResult(
        "image_quality",
        "pass",
        {"width": width, "height": height, "blur_variance": round(float(blur_variance), 1)},
    )


def check_face_presence(content: bytes) -> DocumentCheckResult:
    array = np.frombuffer(content, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_GRAYSCALE)
    if image is None:
        return DocumentCheckResult("face_presence", "fail", {"reason": "could not decode image"})

    cascade = cv2.CascadeClassifier(_FACE_CASCADE_PATH)
    faces = cascade.detectMultiScale(image, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
    if len(faces) == 0:
        return DocumentCheckResult("face_presence", "warn", {"reason": "no face detected"})
    return DocumentCheckResult("face_presence", "pass", {"faces_detected": len(faces)})


def run_ocr(content: bytes) -> str | None:
    """Returns extracted text, or None if the Tesseract binary is not
    available in this environment (the check that depends on it then warns
    rather than crashing the whole verification pipeline)."""
    try:
        import pytesseract

        image = Image.open(io.BytesIO(content))
        return pytesseract.image_to_string(image)
    except Exception:  # noqa: BLE001 - no tesseract binary, or unreadable image
        return None


def check_mrz(ocr_text: str | None) -> tuple[DocumentCheckResult, dict | None]:
    """Parses and checksum-validates an ICAO 9303 MRZ if OCR found one.
    Returns the check result plus the parsed fields (name, dob, expiry,
    country) for use in check_cross_references, or None if no MRZ found."""
    if not ocr_text:
        return DocumentCheckResult("mrz", "warn", {"reason": "no OCR text available"}), None

    from mrz.checker.td3 import TD3CodeChecker

    lines = [line.strip() for line in ocr_text.splitlines() if len(line.strip()) >= 30]
    for i in range(len(lines) - 1):
        candidate = lines[i] + "\n" + lines[i + 1]
        try:
            checker = TD3CodeChecker(candidate, check_expiry=False)
        except Exception:  # noqa: BLE001, S112 - not a valid two-line MRZ candidate, try the next pair
            continue
        fields = checker.fields()
        if bool(checker):
            return (
                DocumentCheckResult("mrz", "pass", {"valid_checksums": True}),
                {
                    "surname": fields.surname,
                    "given_names": fields.name,
                    "document_number": fields.document_number,
                    "birth_date": fields.birth_date,
                    "expiry_date": fields.expiry_date,
                    "nationality": fields.nationality,
                    "country": fields.country,
                },
            )
        return (
            DocumentCheckResult("mrz", "fail", {"reason": "MRZ checksum validation failed"}),
            None,
        )

    return DocumentCheckResult("mrz", "warn", {"reason": "no MRZ pattern found in OCR text"}), None


def _parse_mrz_yymmdd(value: str) -> dt.date | None:
    """MRZ dates are six digits, YYMMDD, with no century: pivot on a 50-year
    window (>=50 -> 1900s) the same way ICAO 9303 readers commonly do."""

    if not value or len(value) != 6 or not value.isdigit():
        return None
    yy, mm, dd = int(value[0:2]), int(value[2:4]), int(value[4:6])
    year = 1900 + yy if yy >= 50 else 2000 + yy
    try:
        return dt.date(year, mm, dd)
    except ValueError:
        return None


def _country_names(code_or_name: str) -> set[str]:
    """Returns the plausible display names for an ISO alpha-2/alpha-3 code or
    already-a-name string, so an MRZ's 3-letter country and an application's
    free-text country field can be compared meaningfully."""
    import pycountry

    candidate = code_or_name.strip()
    names = {candidate.casefold()}
    lookup = None
    if len(candidate) == 3:
        lookup = pycountry.countries.get(alpha_3=candidate.upper())
    elif len(candidate) == 2:
        lookup = pycountry.countries.get(alpha_2=candidate.upper())
    else:
        lookup = pycountry.countries.get(name=candidate.title())
    if lookup is not None:
        names.add(lookup.name.casefold())
    return names


def check_cross_references(
    mrz_fields: dict | None,
    *,
    application_full_name: str,
    application_dob_iso: str | None,
    application_nationality: str | None,
) -> DocumentCheckResult:
    if mrz_fields is None:
        return DocumentCheckResult(
            "cross_reference", "warn", {"reason": "no MRZ data to cross-check"}
        )

    issues = []
    mrz_name = f"{mrz_fields.get('given_names', '')} {mrz_fields.get('surname', '')}".strip()
    # token_set_ratio is case-sensitive; MRZ names are all-caps by the ICAO
    # 9303 spec, so without casefolding here "Anna Eriksson" vs "ANNA
    # ERIKSSON" scores as a near-total mismatch instead of an exact one.
    name_score = fuzz.token_set_ratio(application_full_name.casefold(), mrz_name.casefold())
    if name_score < NAME_MATCH_THRESHOLD:
        issues.append(f"name mismatch (score {name_score})")

    mrz_dob = _parse_mrz_yymmdd(str(mrz_fields.get("birth_date") or ""))
    if application_dob_iso and mrz_dob:
        try:
            application_dob = dt.date.fromisoformat(application_dob_iso)
            if mrz_dob != application_dob:
                issues.append("date of birth mismatch")
        except ValueError:
            pass

    expiry_date = _parse_mrz_yymmdd(str(mrz_fields.get("expiry_date") or ""))
    if expiry_date and expiry_date < dt.datetime.now(dt.UTC).date():
        issues.append("document expired")

    mrz_country_code = mrz_fields.get("nationality") or mrz_fields.get("country")
    if (
        application_nationality
        and mrz_country_code
        and application_nationality.strip().casefold() not in _country_names(mrz_country_code)
    ):
        issues.append("issuing country inconsistent with stated nationality")

    if not issues:
        return DocumentCheckResult("cross_reference", "pass", {"name_score": name_score})
    return DocumentCheckResult(
        "cross_reference", "fail", {"issues": issues, "name_score": name_score}
    )


def run_document_verification(
    content: bytes,
    *,
    declared_mime: str | None,
    application_full_name: str,
    application_dob_iso: str | None,
    application_nationality: str | None,
) -> list[DocumentCheckResult]:
    """Runs the full pipeline and returns one result per check. The caller
    persists each as a document_checks row and decides overall pass/fail
    from the presence of any "fail" result."""
    results = [check_mime_and_size(content, declared_mime)]
    if results[0].result == "fail":
        return results

    results.append(check_image_quality(content))
    results.append(check_face_presence(content))

    ocr_text = run_ocr(content)
    mrz_result, mrz_fields = check_mrz(ocr_text)
    results.append(mrz_result)
    results.append(
        check_cross_references(
            mrz_fields,
            application_full_name=application_full_name,
            application_dob_iso=application_dob_iso,
            application_nationality=application_nationality,
        )
    )
    return results
