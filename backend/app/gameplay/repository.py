from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.gameplay.models import (
    Event,
    Prediction,
    PredictionMarket,
    Race,
    RaceEntry,
    Team,
    Venue,
)


async def list_teams(session: AsyncSession) -> list[Team]:
    return list((await session.execute(select(Team))).scalars().all())


async def list_venues(session: AsyncSession) -> list[Venue]:
    return list((await session.execute(select(Venue))).scalars().all())


async def list_events(session: AsyncSession) -> list[Event]:
    return list((await session.execute(select(Event))).scalars().all())


async def list_races(session: AsyncSession, event_id: int | None = None) -> list[Race]:
    statement = select(Race)
    if event_id is not None:
        statement = statement.where(Race.event_id == event_id)
    return list((await session.execute(statement)).scalars().all())


async def list_race_entries(session: AsyncSession, race_id: int | None = None) -> list[RaceEntry]:
    statement = select(RaceEntry)
    if race_id is not None:
        statement = statement.where(RaceEntry.race_id == race_id)
    return list((await session.execute(statement)).scalars().all())


async def list_prediction_markets(
    session: AsyncSession, race_id: int | None = None
) -> list[PredictionMarket]:
    statement = select(PredictionMarket)
    if race_id is not None:
        statement = statement.where(PredictionMarket.race_id == race_id)
    return list((await session.execute(statement)).scalars().all())


async def list_predictions(
    session: AsyncSession, market_id: int | None = None, user_id: int | None = None
) -> list[Prediction]:
    statement = select(Prediction)
    if market_id is not None:
        statement = statement.where(Prediction.market_id == market_id)
    if user_id is not None:
        statement = statement.where(Prediction.user_id == user_id)
    return list((await session.execute(statement)).scalars().all())


async def get_prediction_market_by_id(
    session: AsyncSession, market_id: int
) -> PredictionMarket | None:
    return (
        await session.execute(select(PredictionMarket).where(PredictionMarket.id == market_id))
    ).scalar_one_or_none()


async def get_prediction_by_market_and_user(
    session: AsyncSession, market_id: int, user_id: int
) -> Prediction | None:
    return (
        await session.execute(
            select(Prediction).where(
                Prediction.market_id == market_id, Prediction.user_id == user_id
            )
        )
    ).scalar_one_or_none()


async def sum_settled_points_by_user(
    session: AsyncSession, user_ids: list[int]
) -> dict[int, float]:
    """Total points_awarded per user, across every settled prediction they hold.

    A prediction is settled once settlement (issue #98) has written points_awarded; until
    then the column is NULL and contributes nothing. Users with no settled predictions are
    absent from the mapping rather than present with 0 -- callers default them, so this
    function never has to know who was asked about but had nothing.

    The explicit `deleted_at IS NULL` looks redundant beside app/soft_delete.py's global
    filter, but that filter's behavior on a column-only aggregate select (no whole entity
    in the select list) is not documented by SQLAlchemy. Stating the predicate keeps the
    query correct on its own terms instead of on an implementation detail of an event
    hook, and a soft-deleted prediction silently inflating every total would be a quiet,
    hard-to-spot bug."""
    if not user_ids:
        return {}

    statement = (
        select(Prediction.user_id, func.sum(Prediction.points_awarded))
        .where(
            Prediction.user_id.in_(user_ids),
            Prediction.points_awarded.is_not(None),
            Prediction.deleted_at.is_(None),
        )
        .group_by(Prediction.user_id)
    )
    return {user_id: float(total) for user_id, total in (await session.execute(statement)).all()}
