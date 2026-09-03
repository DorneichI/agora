from app.gameplay.models import Team, Venue
from app.models import User


async def test_team_has_soft_delete_fields_and_created_by(db_session):
    creator = User(clerk_id="user_team_owner", email="teamowner@example.com")
    db_session.add(creator)
    await db_session.commit()

    team = Team(name="Crimson", school="Harvard", mascot="Crimson", created_by=creator.id)
    db_session.add(team)
    await db_session.commit()

    assert team.id is not None
    assert team.created_at is not None
    assert team.deleted_at is None
    assert team.created_by == creator.id
    assert team.updated_by is None
    assert team.image_url is None


async def test_team_accepts_optional_image_url(db_session):
    creator = User(clerk_id="user_team_img", email="teamimg@example.com")
    db_session.add(creator)
    await db_session.commit()

    team = Team(
        name="Elis",
        school="Yale",
        mascot="Bulldogs",
        image_url="https://example.com/yale.png",
        created_by=creator.id,
    )
    db_session.add(team)
    await db_session.commit()

    assert team.image_url == "https://example.com/yale.png"


async def test_venue_has_soft_delete_fields_and_created_by(db_session):
    creator = User(clerk_id="user_venue_owner", email="venueowner@example.com")
    db_session.add(creator)
    await db_session.commit()

    venue = Venue(name="Red Top", location="Ledyard, CT", created_by=creator.id)
    db_session.add(venue)
    await db_session.commit()

    assert venue.id is not None
    assert venue.created_at is not None
    assert venue.deleted_at is None
    assert venue.created_by == creator.id
    assert venue.updated_by is None
    assert venue.image_url is None
