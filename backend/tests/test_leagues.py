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


async def test_get_league_without_token_returns_401(client):
    response = await client.get("/leagues/1")

    assert response.status_code == 401


async def test_get_league_returns_created_league(client, make_clerk_token):
    token = make_clerk_token(
        clerk_id="user_league_getter", email="getter@example.com", name="Getter"
    )
    create_response = await client.post(
        "/leagues", json={"name": "Boston Sprints"}, headers={"Authorization": f"Bearer {token}"}
    )
    league_id = create_response.json()["id"]

    get_response = await client.get(
        f"/leagues/{league_id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Boston Sprints"


async def test_get_nonexistent_league_returns_404(client, make_clerk_token):
    token = make_clerk_token(
        clerk_id="user_league_missing", email="missing@example.com", name="Missing"
    )

    response = await client.get("/leagues/999999", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404


async def test_get_soft_deleted_league_returns_404(client, make_clerk_token, db_session):
    from app.models import League

    token = make_clerk_token(
        clerk_id="user_league_soft_delete", email="softdel@example.com", name="SoftDel"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Disbanded League"},
        headers={"Authorization": f"Bearer {token}"},
    )
    league_id = create_response.json()["id"]

    league = await db_session.get(League, league_id)
    await db_session.delete(league)
    await db_session.commit()

    response = await client.get(
        f"/leagues/{league_id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404
