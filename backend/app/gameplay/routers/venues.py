from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

from app.auth.deps import require_username
from app.crud_helpers import assert_not_referenced, get_or_404
from app.db import get_session
from app.deps import require_admin
from app.gameplay import repository
from app.gameplay.models import Event, Venue, VenueRead
from app.gameplay.routers._shared import _reject_null_updates
from app.models import User

router = APIRouter()


class VenueCreate(SQLModel):
    name: str
    location: str
    image_url: str | None = None


@router.post("/venues", response_model=VenueRead, status_code=status.HTTP_201_CREATED)
async def create_venue(
    body: VenueCreate,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Venue:
    venue = Venue(
        name=body.name,
        location=body.location,
        image_url=body.image_url,
        created_by=user.id,
    )
    session.add(venue)
    await session.commit()
    return venue


@router.get("/venues/{venue_id}", response_model=VenueRead)
async def get_venue(
    venue_id: int,
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> Venue:
    return await get_or_404(session, Venue, venue_id)


@router.get("/venues", response_model=list[VenueRead])
async def list_venues(
    user: User = Depends(require_username),
    session: AsyncSession = Depends(get_session),
) -> list[Venue]:
    return await repository.list_venues(session)


class VenueUpdate(SQLModel):
    name: str | None = None
    location: str | None = None
    image_url: str | None = None


@router.patch("/venues/{venue_id}", response_model=VenueRead)
async def update_venue(
    venue_id: int,
    body: VenueUpdate,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Venue:
    venue = await get_or_404(session, Venue, venue_id)

    updates = body.model_dump(exclude_unset=True)
    _reject_null_updates(updates, {"name", "location"})
    if updates:
        for field, value in updates.items():
            setattr(venue, field, value)
        venue.updated_by = user.id
        session.add(venue)
        await session.commit()
    return venue


@router.delete("/venues/{venue_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_venue(
    venue_id: int,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    venue = await get_or_404(session, Venue, venue_id)
    await assert_not_referenced(session, Event, "venue_id", venue_id, "Venue")

    await session.delete(venue)
    await session.commit()
