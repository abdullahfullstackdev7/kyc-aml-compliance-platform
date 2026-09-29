from fastapi import APIRouter

from backend.app.api.v1 import auth, cases, lists, portal, screening

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(screening.router)
router.include_router(portal.router)
router.include_router(cases.router)
router.include_router(lists.router)
