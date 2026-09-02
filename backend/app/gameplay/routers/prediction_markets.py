"""Prediction markets: creation, read/list, and settlement.

Settlement (issue #98) turns recorded race results plus a market's predictions into points,
using the scoring framework in app.gameplay.scoring (issue #95/#107). Prediction submission
(issue #97) is a separate concern and lives elsewhere once it lands.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

from app.auth.deps import require_username
from app.crud_helpers import get_or_404, validate_fk_exists
from app.db import get_session
from app.deps import require_admin
from app.gameplay import repository
from app.gameplay.models import (
    Prediction,
    PredictionMarket,
    PredictionMarketRead,
    PredictionRead,
    Race,
)
from app.gameplay.scoring import ScoringConfigError, settle_market, validate_scoring_config
from app.models import User

router = APIRouter()


async def _validate_race_id(race_id: int, session: AsyncSession) -> None:
    await validate_fk_exists(session, Race, race_id, "race_id")


async def _validate_no_existing_market(race_id: int, session: AsyncSession) -> None:
    existing = await repository.list_prediction_markets(session, race_id=race_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="race_id already has an active PredictionMarket",
        )


async def _validate_scoring_config_for_race(
    scoring_config: dict, race_id: int, session: AsyncSession
) -> None:
    entry_count = len(await repository.list_race_entries(session, race_id=race_id))
    try:
        validate_scoring_config(scoring_config, entry_count)
    except ScoringConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


class PredictionMarketCreate(SQLModel):
    race_id: int
    scoring_config: dict


@router.post(
    "/prediction-markets",
    response_model=PredictionMarketRead,
    # deliberate: issue #96 requires 201 here, unlike every other create route's implicit 200
    status_code=status.HTTP_201_CREATED,
)
async def create_prediction_market(
    body: PredictionMarketCreate,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> PredictionMarket:
    await _validate_race_id(body.race_id, session)
    await _validate_no_existing_market(body.race_id, session)
    await _validate_scoring_config_for_race(body.scoring_config, body.race_id, session)

    market = PredictionMarket(
        race_id=body.race_id,
        scoring_config=body.scoring_config,
        created_by=user.id,
    )
    session.add(market)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="race_id already has an active PredictionMarket",
        ) from exc
    return market


@router.get("/prediction-markets/{prediction_market_id}", response_model=PredictionMarketRead)
async def get_prediction_market(
    prediction_market_id: int,
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> PredictionMarket:
    return await get_or_404(session, PredictionMarket, prediction_market_id)


@router.get("/prediction-markets", response_model=list[PredictionMarketRead])
async def list_prediction_markets(
    race_id: int | None = None,
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> list[PredictionMarket]:
    return await repository.list_prediction_markets(session, race_id=race_id)


@router.post(
    "/prediction-markets/{prediction_market_id}/settle", response_model=list[PredictionRead]
)
async def settle_prediction_market(
    prediction_market_id: int,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[Prediction]:
    market = await get_or_404(session, PredictionMarket, prediction_market_id)
    if market.settled_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="PredictionMarket is already settled",
        )

    race_entries = await repository.list_race_entries(session, race_id=market.race_id)
    predictions = await repository.list_predictions(session, market_id=market.id)

    totals = settle_market(market, predictions, race_entries)
    for prediction in predictions:
        prediction.points_awarded = totals[prediction.id]
        session.add(prediction)

    market.settled_at = datetime.now(UTC)
    market.updated_by = admin.id
    session.add(market)
    await session.commit()

    return predictions
