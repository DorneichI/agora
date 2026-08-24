from datetime import date

from app.models import Event, User, Venue


async def test_event_has_soft_delete_fields_and_created_by(db_session):
    creator = User(
        clerk_id="user_event_owner", email="eventowner@example.com", display_name="Owner"
    )
    db_session.add(creator)
    await db_session.commit()

    event = Event(
        name="Head of the Charles",
        description="Fall regatta on the Charles River",
        format="regatta",
        start_date=date(2026, 10, 17),
        end_date=date(2026, 10, 18),
        created_by=creator.id,
    )
    db_session.add(event)
    await db_session.commit()

    assert event.id is not None
    assert event.created_at is not None
    assert event.deleted_at is None
    assert event.created_by == creator.id
    assert event.updated_by is None
    assert event.venue_id is None
    assert event.image_url is None


async def test_event_accepts_optional_venue_and_image_url(db_session):
    creator = User(
        clerk_id="user_event_venue", email="eventvenue@example.com", display_name="Owner"
    )
    db_session.add(creator)
    await db_session.commit()

    venue = Venue(name="Red Top", location="Ledyard, CT", created_by=creator.id)
    db_session.add(venue)
    await db_session.commit()

    event = Event(
        name="Head of the Charles",
        description="Fall regatta on the Charles River",
        venue_id=venue.id,
        format="regatta",
        start_date=date(2026, 10, 17),
        end_date=date(2026, 10, 18),
        image_url="https://example.com/hoc.png",
        created_by=creator.id,
    )
    db_session.add(event)
    await db_session.commit()

    assert event.venue_id == venue.id
    assert event.image_url == "https://example.com/hoc.png"
