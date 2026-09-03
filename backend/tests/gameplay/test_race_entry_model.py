from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.gameplay.models import Event, Race, RaceEntry, Team
from app.models import User


async def _make_creator(db_session, clerk_id, email):
    creator = User(clerk_id=clerk_id, email=email)
    db_session.add(creator)
    await db_session.commit()
    return creator


async def _make_race(db_session, creator):
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

    race = Race(
        name="Varsity 8+ Heat 1",
        event_id=event.id,
        boat_class="8+",
        level="varsity",
        created_by=creator.id,
    )
    db_session.add(race)
    await db_session.commit()
    return race


async def _make_team(db_session, creator, name="Crimson"):
    team = Team(name=name, school="Harvard", mascot="Crimson", created_by=creator.id)
    db_session.add(team)
    await db_session.commit()
    return team


async def test_race_entry_has_soft_delete_fields_and_created_by(db_session):
    creator = await _make_creator(db_session, "user_re_owner", "reowner@example.com")
    race = await _make_race(db_session, creator)
    team = await _make_team(db_session, creator)

    entry = RaceEntry(race_id=race.id, team_id=team.id, level="varsity", created_by=creator.id)
    db_session.add(entry)
    await db_session.commit()

    assert entry.id is not None
    assert entry.created_at is not None
    assert entry.deleted_at is None
    assert entry.created_by == creator.id
    assert entry.updated_by is None
    assert entry.time is None
    assert entry.status == "dns"


async def test_race_entry_finished_status_can_have_time(db_session):
    creator = await _make_creator(db_session, "user_re_finished", "refinished@example.com")
    race = await _make_race(db_session, creator)
    team = await _make_team(db_session, creator)

    entry = RaceEntry(
        race_id=race.id,
        team_id=team.id,
        level="varsity",
        status="finished",
        time=383.45,
        created_by=creator.id,
    )
    db_session.add(entry)
    await db_session.commit()

    assert entry.status == "finished"
    assert entry.time == 383.45


async def test_race_entry_non_finished_status_allows_null_time(db_session):
    creator = await _make_creator(db_session, "user_re_dnf", "rednf@example.com")
    race = await _make_race(db_session, creator)
    team = await _make_team(db_session, creator)

    entry = RaceEntry(
        race_id=race.id,
        team_id=team.id,
        level="varsity",
        status="dnf",
        created_by=creator.id,
    )
    db_session.add(entry)
    await db_session.commit()

    assert entry.status == "dnf"
    assert entry.time is None


async def test_duplicate_active_race_entry_for_same_race_and_team_rejected(db_session):
    creator = await _make_creator(db_session, "user_re_dup", "redup@example.com")
    race = await _make_race(db_session, creator)
    team = await _make_team(db_session, creator)

    db_session.add(
        RaceEntry(race_id=race.id, team_id=team.id, level="varsity", created_by=creator.id)
    )
    await db_session.commit()

    db_session.add(
        RaceEntry(race_id=race.id, team_id=team.id, level="varsity", created_by=creator.id)
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_race_entry_readd_after_soft_delete_allowed_by_partial_index(db_session):
    creator = await _make_creator(db_session, "user_re_readd", "rereadd@example.com")
    race = await _make_race(db_session, creator)
    team = await _make_team(db_session, creator)

    first_entry = RaceEntry(
        race_id=race.id, team_id=team.id, level="varsity", created_by=creator.id
    )
    db_session.add(first_entry)
    await db_session.commit()

    await db_session.delete(first_entry)
    await db_session.commit()

    second_entry = RaceEntry(
        race_id=race.id, team_id=team.id, level="varsity", created_by=creator.id
    )
    db_session.add(second_entry)
    await db_session.commit()  # would raise IntegrityError if the index weren't partial

    assert second_entry.id is not None
    assert second_entry.id != first_entry.id
