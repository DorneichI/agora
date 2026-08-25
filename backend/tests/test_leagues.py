from sqlmodel import select

from app.models import League, LeagueUser


async def test_create_league_without_token_returns_401(client):
    response = await client.post("/leagues", json={"name": "Head of the Charles"})

    assert response.status_code == 401


async def test_create_league_without_username_returns_403(client, make_clerk_token):
    """Regression test for the require_username gate itself (test_deps.py only exercises
    it as a bare unit, and the cascade test in test_events.py only covers the
    require_admin path) -- a plain authenticated-but-not-onboarded user must be blocked on
    a route that depends on require_username directly, with no require_admin involved."""
    token = make_clerk_token(
        clerk_id="user_league_no_username", email="leaguenousername@example.com", name="No Username"
    )
    await client.get("/me", headers={"Authorization": f"Bearer {token}"})

    response = await client.post(
        "/leagues",
        json={"name": "Head of the Charles"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


async def test_create_league_creates_league_and_membership(client, make_user, db_session):
    token, _creator_id = await make_user("user_league_creator", "creator@example.com", "Creator")

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


async def test_create_league_response_excludes_internal_fields(client, make_user):
    """LeagueRead is the response shape, not the League table model -- soft-delete
    bookkeeping columns must not be exposed to API consumers."""
    token, _creator_id = await make_user(
        "user_league_read_shape", "readshape@example.com", "Read Shape"
    )

    response = await client.post(
        "/leagues",
        json={"name": "Charles River Regatta"},
        headers={"Authorization": f"Bearer {token}"},
    )

    body = response.json()
    assert set(body.keys()) == {"id", "name", "created_by"}


async def test_get_league_without_token_returns_401(client):
    response = await client.get("/leagues/1")

    assert response.status_code == 401


async def test_get_league_returns_created_league(client, make_user):
    token, _creator_id = await make_user("user_league_getter", "getter@example.com", "Getter")
    create_response = await client.post(
        "/leagues", json={"name": "Boston Sprints"}, headers={"Authorization": f"Bearer {token}"}
    )
    league_id = create_response.json()["id"]

    get_response = await client.get(
        f"/leagues/{league_id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert get_response.status_code == 200
    body = get_response.json()
    assert body["name"] == "Boston Sprints"
    assert set(body.keys()) == {"id", "name", "created_by"}


async def test_get_nonexistent_league_returns_404(client, make_user):
    token, _creator_id = await make_user("user_league_missing", "missing@example.com", "Missing")

    response = await client.get("/leagues/999999", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404


async def test_get_soft_deleted_league_returns_404(client, make_user, db_session):
    token, _creator_id = await make_user(
        "user_league_soft_delete", "softdel@example.com", "SoftDel"
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


async def test_join_league_without_token_returns_401(client):
    response = await client.post("/leagues/1/join")

    assert response.status_code == 401


async def test_join_nonexistent_league_returns_404(client, make_user):
    token, _creator_id = await make_user(
        "user_join_missing_league", "joinmissing@example.com", "Join Missing"
    )

    response = await client.post(
        "/leagues/999999/join", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


async def test_join_league_creates_active_membership(client, make_user, db_session):
    creator_token, _creator_id = await make_user(
        "user_join_creator", "joincreator@example.com", "Join Creator"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Join Test League"},
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    league_id = create_response.json()["id"]

    joiner_token, joiner_id = await make_user(
        "user_join_joiner", "joinjoiner@example.com", "Join Joiner"
    )
    join_response = await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {joiner_token}"}
    )

    assert join_response.status_code == 204

    membership_rows = (
        (
            await db_session.execute(
                select(LeagueUser).where(
                    LeagueUser.league_id == league_id, LeagueUser.user_id == joiner_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(membership_rows) == 1
    assert membership_rows[0].deleted_at is None


async def test_join_league_already_active_member_is_idempotent(client, make_user, db_session):
    token, creator_id = await make_user(
        "user_join_idempotent", "joinidempotent@example.com", "Join Idempotent"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Idempotent Join League"},
        headers={"Authorization": f"Bearer {token}"},
    )
    league_id = create_response.json()["id"]

    join_response = await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {token}"}
    )

    assert join_response.status_code == 204

    membership_rows = (
        (
            await db_session.execute(
                select(LeagueUser).where(
                    LeagueUser.league_id == league_id, LeagueUser.user_id == creator_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(membership_rows) == 1


async def test_rejoin_after_leave_resurrects_same_row(client, make_user, db_session):
    creator_token, _creator_id = await make_user(
        "user_rejoin_creator", "rejoincreator@example.com", "Rejoin Creator"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Rejoin Test League"},
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    league_id = create_response.json()["id"]

    joiner_token, joiner_id = await make_user(
        "user_rejoin_joiner", "rejoinjoiner@example.com", "Rejoin Joiner"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {joiner_token}"}
    )

    original_membership = (
        await db_session.execute(
            select(LeagueUser).where(
                LeagueUser.league_id == league_id, LeagueUser.user_id == joiner_id
            )
        )
    ).scalar_one()
    original_id = original_membership.id

    await client.post(
        f"/leagues/{league_id}/leave", headers={"Authorization": f"Bearer {joiner_token}"}
    )

    rejoin_response = await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {joiner_token}"}
    )

    assert rejoin_response.status_code == 204

    all_rows = (
        (
            await db_session.execute(
                select(LeagueUser)
                .where(LeagueUser.league_id == league_id, LeagueUser.user_id == joiner_id)
                .execution_options(include_deleted=True)
            )
        )
        .scalars()
        .all()
    )
    assert len(all_rows) == 1
    assert all_rows[0].id == original_id
    assert all_rows[0].deleted_at is None


async def test_leave_league_without_token_returns_401(client):
    response = await client.post("/leagues/1/leave")

    assert response.status_code == 401


async def test_leave_nonexistent_league_returns_404(client, make_user):
    token, _creator_id = await make_user(
        "user_leave_missing_league", "leavemissing@example.com", "Leave Missing"
    )

    response = await client.post(
        "/leagues/999999/leave", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


async def test_leave_league_soft_deletes_membership(client, make_user, db_session):
    token, member_id = await make_user(
        "user_leave_member", "leavemember@example.com", "Leave Member"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Leave Test League"},
        headers={"Authorization": f"Bearer {token}"},
    )
    league_id = create_response.json()["id"]

    leave_response = await client.post(
        f"/leagues/{league_id}/leave", headers={"Authorization": f"Bearer {token}"}
    )

    assert leave_response.status_code == 204

    active_rows = (
        (
            await db_session.execute(
                select(LeagueUser).where(
                    LeagueUser.league_id == league_id, LeagueUser.user_id == member_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert active_rows == []

    all_rows = (
        (
            await db_session.execute(
                select(LeagueUser)
                .where(LeagueUser.league_id == league_id, LeagueUser.user_id == member_id)
                .execution_options(include_deleted=True)
            )
        )
        .scalars()
        .all()
    )
    assert len(all_rows) == 1
    assert all_rows[0].deleted_at is not None


async def test_leave_league_never_joined_is_noop(client, make_user):
    creator_token, _creator_id = await make_user(
        "user_leave_noop_creator", "leavenoopcreator@example.com", "Creator"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Never Joined League"},
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    league_id = create_response.json()["id"]

    bystander_token, _bystander_id = await make_user(
        "user_leave_noop_bystander", "leavenoopbystander@example.com", "Bystander"
    )
    response = await client.post(
        f"/leagues/{league_id}/leave", headers={"Authorization": f"Bearer {bystander_token}"}
    )

    assert response.status_code == 204
