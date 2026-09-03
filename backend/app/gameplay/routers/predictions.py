"""Prediction submission: create-or-update a user's pick against an open PredictionMarket,
and read back predictions. Market creation/read (issue #96) lives in prediction_markets.py;
settlement (issue #98) also lives there."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

from app.auth.deps import require_username
from app.crud_helpers import get_or_404
from app.db import get_session
from app.gameplay import repository
from app.gameplay.models import Prediction, PredictionMarket, PredictionRead
from app.gameplay.scoring import ScoringPayloadError, validate_prediction_payload
from app.models import User

router = APIRouter()


async def _get_open_market(market_id: int, session: AsyncSession) -> PredictionMarket:
    market = await repository.get_prediction_market_by_id(session, market_id)
    if market is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="market_id does not reference an existing PredictionMarket",
        )
    if market.settled_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="PredictionMarket is already settled",
        )
    return market


async def _validate_picked_team_id(
    picked_team_id: int, race_id: int, session: AsyncSession
) -> None:
    race_entries = await repository.list_race_entries(session, race_id=race_id)
    if picked_team_id not in {entry.team_id for entry in race_entries}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="picked_team_id is not an entrant in this race",
        )


def _validate_payload(market: PredictionMarket, margin_threshold_seconds: float | None) -> None:
    try:
        validate_prediction_payload(
            market.scoring_config, {"margin_threshold_seconds": margin_threshold_seconds}
        )
    except ScoringPayloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


class PredictionCreate(SQLModel):
    market_id: int
    picked_team_id: int
    margin_threshold_seconds: float | None = None


@router.post("/predictions", response_model=PredictionRead)
async def create_or_update_prediction(
    body: PredictionCreate,
    response: Response,
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> Prediction:
    market = await _get_open_market(body.market_id, session)
    await _validate_picked_team_id(body.picked_team_id, market.race_id, session)
    _validate_payload(market, body.margin_threshold_seconds)

    existing = await repository.get_prediction_by_market_and_user(session, body.market_id, user.id)

    if existing is not None:
        existing.picked_team_id = body.picked_team_id
        existing.margin_threshold_seconds = body.margin_threshold_seconds
        session.add(existing)
        await session.commit()
        return existing

    response.status_code = status.HTTP_201_CREATED
    prediction = Prediction(
        market_id=body.market_id,
        user_id=user.id,
        picked_team_id=body.picked_team_id,
        margin_threshold_seconds=body.margin_threshold_seconds,
    )
    session.add(prediction)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A Prediction for this market_id and user_id was just created concurrently",
        ) from exc
    return prediction


@router.get("/predictions/{prediction_id}", response_model=PredictionRead)
async def get_prediction(
    prediction_id: int,
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> Prediction:
    prediction = await get_or_404(session, Prediction, prediction_id)
    if prediction.user_id != user.id and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view another user's prediction",
        )
    return prediction


@router.get("/predictions", response_model=list[PredictionRead])
async def list_predictions(
    market_id: int | None = None,
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> list[Prediction]:
    return await repository.list_predictions(session, market_id=market_id, user_id=user.id)
