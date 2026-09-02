from fastapi import APIRouter

from app.gameplay.routers import (
    events,
    prediction_markets,
    predictions,
    race_entries,
    races,
    standings,
    teams,
    venues,
)

router = APIRouter()
router.include_router(teams.router)
router.include_router(venues.router)
router.include_router(events.router)
router.include_router(races.router)
router.include_router(race_entries.router)
router.include_router(prediction_markets.router)
router.include_router(predictions.router)
router.include_router(standings.router)
