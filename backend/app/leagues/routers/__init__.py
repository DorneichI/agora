from fastapi import APIRouter

from app.leagues.routers import invites, leagues

router = APIRouter()
router.include_router(leagues.router)
router.include_router(invites.router)
