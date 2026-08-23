from sqlmodel import select

from app.models import League, LeagueUser


async def test_create_league_without_token_returns_401(client):
    response = await client.post("/leagues", json={"name": "Head of the Charles"})

    assert response.status_code == 401


async def test_create_league_creates_league_and_membership(client, make_clerk_token, db_session):
    token = make_clerk_token(
        clerk_id="user_league_creator", email="creator@example.com", name="Creator"
    )

    response = await client.post(
        "/leagues",
        json={"name": "Head of the Charles"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Head of the Charles"

    league_rows = (
        (await db_session.execute(select(League).where(League.id == body["id"]))).scalars().all()
    )
    assert len(league_rows) == 1
    assert league_rows[0].created_by == body["created_by"]

    membership_rows = (
        (await db_session.execute(select(LeagueUser).where(LeagueUser.league_id == body["id"])))
        .scalars()
        .all()
    )
    assert len(membership_rows) == 1
    assert membership_rows[0].user_id == body["created_by"]
