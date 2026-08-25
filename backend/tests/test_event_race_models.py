from datetime import date

from app.models import Event, Race, User, Venue


async def test_event_has_soft_delete_fields_and_created_by(db_session):
    creator = User(clerk_id="user_event_owner", email="eventowner@example.com")
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
    creator = User(clerk_id="user_event_venue", email="eventvenue@example.com")
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


async def test_race_has_soft_delete_fields_and_created_by(db_session):
    creator = User(clerk_id="user_race_owner", email="raceowner@example.com")
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

    race = Race(event_id=event.id, boat_class="8+", level="varsity", created_by=creator.id)
    db_session.add(race)
    await db_session.commit()

    assert race.id is not None
    assert race.created_at is not None
    assert race.deleted_at is None
    assert race.created_by == creator.id
    assert race.updated_by is None
    assert race.round is None


async def test_race_accepts_optional_round(db_session):
    creator = User(clerk_id="user_race_round", email="raceround@example.com")
    db_session.add(creator)
    await db_session.commit()

    event = Event(
        name="Eastern Sprints",
        description="Spring championship",
        format="regatta",
        start_date=date(2026, 5, 17),
        end_date=date(2026, 5, 17),
        created_by=creator.id,
    )
    db_session.add(event)
    await db_session.commit()

    race = Race(
        event_id=event.id, boat_class="4+", level="3v", round="final", created_by=creator.id
    )
    db_session.add(race)
    await db_session.commit()

    assert race.round == "final"
