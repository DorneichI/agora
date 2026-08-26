from datetime import UTC, datetime, timedelta

from sqlmodel import select

from app.models import LeagueInvite


async def _make_league_public(client, token, league_id):
    response = await client.patch(
        f"/leagues/{league_id}",
        json={"visibility": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


async def _make_league_private(client, token, league_id):
    response = await client.patch(
        f"/leagues/{league_id}",
        json={"visibility": "private"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


async def _set_invite_policy(client, token, league_id, policy):
    response = await client.patch(
        f"/leagues/{league_id}",
        json={"invite_policy": policy},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


async def _add_member(client, owner_token, league_id, member_token):
    """Add member_token's user to league_id, toggling visibility public just long enough to
    join (the only way to add a member before the redeem endpoint exists), then restoring the
    league's original visibility."""
    league_response = await client.get(
        f"/leagues/{league_id}", headers={"Authorization": f"Bearer {owner_token}"}
    )
    original_visibility = league_response.json()["visibility"]
    if original_visibility != "public":
        await _make_league_public(client, owner_token, league_id)

    join_response = await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {member_token}"}
    )
    assert join_response.status_code == 204

    if original_visibility != "public":
        await _make_league_private(client, owner_token, league_id)


async def _create_league(client, token, name):
    response = await client.post(
        "/leagues", json={"name": name}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    return response.json()["id"]


async def test_create_invite_without_token_returns_401(client):
    response = await client.post("/leagues/1/invites", json={})

    assert response.status_code == 401


async def test_create_invite_nonexistent_league_returns_404(client, make_user):
    token, _owner_id = await make_user("user_inv_missing", "invmissing@example.com", "Missing")

    response = await client.post(
        "/leagues/999999/invites", json={}, headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


async def test_create_invite_non_member_returns_403(client, make_user):
    owner_token, _owner_id = await make_user("user_inv_owner_1", "invowner1@example.com", "Owner")
    league_id = await _create_league(client, owner_token, "Invite League 1")

    outsider_token, _outsider_id = await make_user(
        "user_inv_outsider", "invoutsider@example.com", "Outsider"
    )
    response = await client.post(
        f"/leagues/{league_id}/invites",
        json={},
        headers={"Authorization": f"Bearer {outsider_token}"},
    )

    assert response.status_code == 403


async def test_create_invite_public_league_owner_only_default_succeeds_for_owner(client, make_user):
    owner_token, owner_id = await make_user("user_inv_owner_2", "invowner2@example.com", "Owner")
    league_id = await _create_league(client, owner_token, "Invite League 2")
    await _make_league_public(client, owner_token, league_id)

    response = await client.post(
        f"/leagues/{league_id}/invites",
        json={},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["league_id"] == league_id
    assert body["created_by"] == owner_id
    assert body["target_user_id"] is None
    assert body["redeemed_at"] is None
    assert body["revoked_at"] is None
    assert body["code"]


async def test_create_invite_owner_only_policy_rejects_plain_member(client, make_user):
    owner_token, _owner_id = await make_user("user_inv_owner_3", "invowner3@example.com", "Owner")
    league_id = await _create_league(client, owner_token, "Invite League 3")

    member_token, _member_id = await make_user(
        "user_inv_member_1", "invmember1@example.com", "Member"
    )
    await _add_member(client, owner_token, league_id, member_token)

    response = await client.post(
        f"/leagues/{league_id}/invites",
        json={},
        headers={"Authorization": f"Bearer {member_token}"},
    )

    assert response.status_code == 403


async def test_create_invite_admins_only_policy_allows_admin(client, make_user):
    owner_token, owner_id = await make_user("user_inv_owner_4", "invowner4@example.com", "Owner")
    league_id = await _create_league(client, owner_token, "Invite League 4")
    await _set_invite_policy(client, owner_token, league_id, "admins_only")

    admin_token, admin_id = await make_user("user_inv_admin_1", "invadmin1@example.com", "Admin")
    await _add_member(client, owner_token, league_id, admin_token)
    promote_response = await client.post(
        f"/leagues/{league_id}/admins/{admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert promote_response.status_code == 200

    await _make_league_public(client, owner_token, league_id)
    response = await client.post(
        f"/leagues/{league_id}/invites",
        json={},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert response.json()["created_by"] == admin_id


async def test_create_invite_admins_only_policy_rejects_plain_member(client, make_user):
    owner_token, _owner_id = await make_user("user_inv_owner_5", "invowner5@example.com", "Owner")
    league_id = await _create_league(client, owner_token, "Invite League 5")
    await _set_invite_policy(client, owner_token, league_id, "admins_only")
    await _make_league_public(client, owner_token, league_id)

    member_token, _member_id = await make_user(
        "user_inv_member_2", "invmember2@example.com", "Member"
    )
    await _add_member(client, owner_token, league_id, member_token)

    response = await client.post(
        f"/leagues/{league_id}/invites",
        json={},
        headers={"Authorization": f"Bearer {member_token}"},
    )

    assert response.status_code == 403


async def test_create_invite_anyone_policy_allows_plain_member(client, make_user):
    owner_token, _owner_id = await make_user("user_inv_owner_6", "invowner6@example.com", "Owner")
    league_id = await _create_league(client, owner_token, "Invite League 6")
    await _set_invite_policy(client, owner_token, league_id, "anyone")
    await _make_league_public(client, owner_token, league_id)

    member_token, member_id = await make_user(
        "user_inv_member_3", "invmember3@example.com", "Member"
    )
    await _add_member(client, owner_token, league_id, member_token)

    response = await client.post(
        f"/leagues/{league_id}/invites",
        json={},
        headers={"Authorization": f"Bearer {member_token}"},
    )

    assert response.status_code == 200
    assert response.json()["created_by"] == member_id


async def test_create_invite_public_league_with_target_username_returns_422(client, make_user):
    owner_token, _owner_id = await make_user("user_inv_owner_7", "invowner7@example.com", "Owner")
    league_id = await _create_league(client, owner_token, "Invite League 7")
    await _make_league_public(client, owner_token, league_id)

    _target_token, target_id = await make_user(
        "user_inv_target_1", "invtarget1@example.com", "Target"
    )

    response = await client.post(
        f"/leagues/{league_id}/invites",
        json={"target_username": f"user{target_id}"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 422


async def test_create_invite_private_league_without_target_returns_422(client, make_user):
    owner_token, _owner_id = await make_user("user_inv_owner_8", "invowner8@example.com", "Owner")
    league_id = await _create_league(client, owner_token, "Invite League 8")

    response = await client.post(
        f"/leagues/{league_id}/invites",
        json={},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 422


async def test_create_invite_private_league_unknown_username_returns_404(client, make_user):
    owner_token, _owner_id = await make_user("user_inv_owner_9", "invowner9@example.com", "Owner")
    league_id = await _create_league(client, owner_token, "Invite League 9")

    response = await client.post(
        f"/leagues/{league_id}/invites",
        json={"target_username": "nosuchuser"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 404


async def test_create_invite_private_league_valid_target_succeeds(client, make_user, db_session):
    owner_token, _owner_id = await make_user("user_inv_owner_10", "invowner10@example.com", "Owner")
    league_id = await _create_league(client, owner_token, "Invite League 10")

    _target_token, target_id = await make_user(
        "user_inv_target_2", "invtarget2@example.com", "Target"
    )

    response = await client.post(
        f"/leagues/{league_id}/invites",
        json={"target_username": f"user{target_id}"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["target_user_id"] == target_id

    invite_rows = (
        (await db_session.execute(select(LeagueInvite).where(LeagueInvite.id == body["id"])))
        .scalars()
        .all()
    )
    assert len(invite_rows) == 1
    assert invite_rows[0].expires_at is not None


async def test_create_invite_retries_on_code_collision(client, make_user, db_session, monkeypatch):
    """Pre-seed an existing invite with a fixed code, then force the code-generation loop
    to draw that same code first (colliding with the partial unique index) before a fresh
    one -- proving the retry loop's collision path is actually exercised, not just that the
    happy path works."""
    from app.routers import invites as invites_module

    owner_token, owner_id = await make_user("user_inv_owner_11", "invowner11@example.com", "Owner")
    league_id = await _create_league(client, owner_token, "Invite League 11")
    await _make_league_public(client, owner_token, league_id)

    colliding_code = "colliding-fixed-code"
    fresh_code = "fresh-distinct-code"
    codes = iter([colliding_code, fresh_code])
    monkeypatch.setattr(invites_module.secrets, "token_urlsafe", lambda _n: next(codes))

    existing_invite = LeagueInvite(
        league_id=league_id,
        code=colliding_code,
        created_by=owner_id,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db_session.add(existing_invite)
    await db_session.commit()

    response = await client.post(
        f"/leagues/{league_id}/invites",
        json={},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == fresh_code
    assert body["code"] != colliding_code
