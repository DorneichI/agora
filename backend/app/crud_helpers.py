"""Shared helpers for the plain-CRUD routers (events, races, race_entries, teams, venues).

Each of those routers repeated the same three shapes by hand; this module gives them one
place to share instead of drifting independently:

- `get_or_404`: fetch a row by id or raise 404 (the `{Model} not found` message is derived
  from the model's class name, matching what every router already said verbatim).
- `validate_fk_exists`: used at create/update time to reject a foreign-key id that doesn't
  reference an existing (non soft-deleted) row, before it's persisted.
- `assert_not_referenced`: used at delete time to reject soft-deleting a row that other,
  still-active rows still point to via a foreign key -- without this, a delete would leave
  a live child row referencing a parent that no longer resolves through the API.
"""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, select


async def get_or_404(session: AsyncSession, model: type[SQLModel], id_: int) -> SQLModel:
    obj = (await session.execute(select(model).where(model.id == id_))).scalar_one_or_none()
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"{model.__name__} not found"
        )
    return obj


async def validate_fk_exists(
    session: AsyncSession, model: type[SQLModel], id_: int, field_name: str
) -> None:
    obj = (await session.execute(select(model).where(model.id == id_))).scalar_one_or_none()
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field_name} does not reference an existing {model.__name__}",
        )


async def assert_not_referenced(
    session: AsyncSession, model: type[SQLModel], field_name: str, id_: int, blocked_label: str
) -> None:
    referencing = (
        await session.execute(select(model).where(getattr(model, field_name) == id_).limit(1))
    ).scalar_one_or_none()
    if referencing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot delete this {blocked_label}: an active {model.__name__} still "
                f"references it via {field_name}"
            ),
        )
