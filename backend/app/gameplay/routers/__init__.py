from fastapi import APIRouter

from app.gameplay.routers import events, race_entries, races, teams, venues

router = APIRouter()
router.include_router(teams.router)
router.include_router(venues.router)
router.include_router(events.router)
router.include_router(races.router)
router.include_router(race_entries.router)
