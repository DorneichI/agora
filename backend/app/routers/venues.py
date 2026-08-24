from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, select

from app.db import get_session
from app.deps import get_current_user, require_admin
from app.models import User, Venue, VenueRead

router = APIRouter()


class VenueCreate(SQLModel):
    name: str
    location: str
    image_url: str | None = None


@router.post("/venues", response_model=VenueRead)
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
    await session.refresh(venue)
    return venue


@router.get("/venues/{venue_id}", response_model=VenueRead)
async def get_venue(
    venue_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Venue:
    venue = (await session.execute(select(Venue).where(Venue.id == venue_id))).scalar_one_or_none()
    if venue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")
    return venue


@router.get("/venues", response_model=list[VenueRead])
async def list_venues(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Venue]:
    return list((await session.execute(select(Venue))).scalars().all())


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
    venue = (await session.execute(select(Venue).where(Venue.id == venue_id))).scalar_one_or_none()
    if venue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(venue, field, value)
    venue.updated_by = user.id

    session.add(venue)
    await session.commit()
    await session.refresh(venue)
    return venue


@router.delete("/venues/{venue_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_venue(
    venue_id: int,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    venue = (await session.execute(select(Venue).where(Venue.id == venue_id))).scalar_one_or_none()
    if venue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")

    await session.delete(venue)
    await session.commit()
