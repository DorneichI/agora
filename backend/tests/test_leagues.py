from sqlmodel import select

from app.leagues.models import League, LeagueUser


async def _make_league_public(client, token, league_id):
    response = await client.patch(
        f"/leagues/{league_id}",
        json={"visibility": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


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

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Head of the Charles"

    league_rows = (
        (await db_session.execute(select(League).where(League.id == body["id"]))).scalars().all()
    )
    assert len(league_rows) == 1
    assert league_rows[0].created_by == body["created_by"]
    assert league_rows[0].owner_id == body["created_by"]

    membership_rows = (
        (await db_session.execute(select(LeagueUser).where(LeagueUser.league_id == body["id"])))
        .scalars()
        .all()
    )
    assert len(membership_rows) == 1
    assert membership_rows[0].user_id == body["created_by"]
    assert membership_rows[0].role == "admin"


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
    assert set(body.keys()) == {
        "id",
        "name",
        "created_by",
        "owner_id",
        "visibility",
        "invite_policy",
        "settings_policy",
    }


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
    assert set(body.keys()) == {
        "id",
        "name",
        "created_by",
        "owner_id",
        "visibility",
        "invite_policy",
        "settings_policy",
    }


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


async def test_get_private_league_by_nonmember_returns_403(client, make_user):
    """Regression test: GET /leagues/{id} had no access check at all -- any authenticated
    user could read (and by walking IDs, enumerate) every private league's details."""
    owner_token, _owner_id = await make_user(
        "user_league_private_get_owner", "leagueprivategetowner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Private Get League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]

    outsider_token, _outsider_id = await make_user(
        "user_league_private_get_outsider", "leagueprivategetoutsider@example.com", "Outsider"
    )

    response = await client.get(
        f"/leagues/{league_id}", headers={"Authorization": f"Bearer {outsider_token}"}
    )

    assert response.status_code == 403


async def test_get_public_league_by_nonmember_returns_200(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_league_public_get_owner", "leaguepublicgetowner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Public Get League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    await _make_league_public(client, owner_token, league_id)

    outsider_token, _outsider_id = await make_user(
        "user_league_public_get_outsider", "leaguepublicgetoutsider@example.com", "Outsider"
    )

    response = await client.get(
        f"/leagues/{league_id}", headers={"Authorization": f"Bearer {outsider_token}"}
    )

    assert response.status_code == 200


async def test_patch_private_league_by_nonmember_with_empty_body_returns_403(client, make_user):
    """Regression test: the empty-body early return in update_league_settings ran before any
    permission check, so `PATCH /leagues/{id}` with `{}` leaked the same private-league
    record GET did."""
    owner_token, _owner_id = await make_user(
        "user_league_private_patch_owner", "leagueprivatepatchowner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Private Patch League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]

    outsider_token, _outsider_id = await make_user(
        "user_league_private_patch_outsider",
        "leagueprivatepatchoutsider@example.com",
        "Outsider",
    )

    response = await client.patch(
        f"/leagues/{league_id}",
        json={},
        headers={"Authorization": f"Bearer {outsider_token}"},
    )

    assert response.status_code == 403


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
    await _make_league_public(client, creator_token, league_id)

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
    await _make_league_public(client, token, league_id)

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


async def test_join_league_concurrent_insert_race_is_idempotent(
    client, make_user, db_session, monkeypatch
):
    """Regression test: two concurrent join requests for the same user could both miss the
    existing-membership check before either committed, so the second's INSERT would hit the
    real partial unique index as an unhandled IntegrityError/500 instead of the intended
    idempotent 204. Simulated deterministically (true concurrency isn't practical here) by
    forcing the membership lookup to report "not found" even though an active row already
    exists, so the real INSERT hits the real unique index."""
    from app.leagues.routers import leagues as leagues_module

    owner_token, _owner_id = await make_user(
        "user_join_race_owner", "joinraceowner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Join Race League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    await _make_league_public(client, owner_token, league_id)

    joiner_token, joiner_id = await make_user(
        "user_join_race_joiner", "joinracejoiner@example.com", "Joiner"
    )
    first_join = await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {joiner_token}"}
    )
    assert first_join.status_code == 204

    async def _always_report_no_membership(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        leagues_module, "get_membership_including_deleted", _always_report_no_membership
    )

    second_join = await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {joiner_token}"}
    )

    assert second_join.status_code == 204
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
    await _make_league_public(client, creator_token, league_id)

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


async def test_rejoin_after_kick_does_not_restore_admin_role(client, make_user, db_session):
    """Regression test: kicking a member soft-deletes their LeagueUser row without clearing
    `role`, so an admin who gets kicked and then rejoins a public league used to silently
    regain admin (join/redeem only cleared `deleted_at`, never reset `role`)."""
    owner_token, _owner_id = await make_user(
        "user_rejoin_role_owner", "rejoinroleowner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Rejoin Role League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    await _make_league_public(client, owner_token, league_id)

    admin_token, admin_id = await make_user(
        "user_rejoin_role_admin", "rejoinroleadmin@example.com", "Admin"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {admin_token}"}
    )
    await client.post(
        f"/leagues/{league_id}/admins/{admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    kick_response = await client.delete(
        f"/leagues/{league_id}/members/{admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert kick_response.status_code == 204

    rejoin_response = await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert rejoin_response.status_code == 204

    membership = (
        await db_session.execute(
            select(LeagueUser).where(
                LeagueUser.league_id == league_id, LeagueUser.user_id == admin_id
            )
        )
    ).scalar_one()
    assert membership.role == "member"


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
    creator_token, _creator_id = await make_user(
        "user_leave_creator", "leavecreator@example.com", "Creator"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Leave Test League"},
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    league_id = create_response.json()["id"]
    await _make_league_public(client, creator_token, league_id)

    token, member_id = await make_user(
        "user_leave_member", "leavemember@example.com", "Leave Member"
    )
    await client.post(f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {token}"})

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


async def test_promote_to_admin_without_token_returns_401(client):
    response = await client.post("/leagues/1/admins/1")

    assert response.status_code == 401


async def test_promote_to_admin_by_non_admin_returns_403(client, make_user, db_session):
    creator_token, _creator_id = await make_user(
        "user_promote_creator", "promotecreator@example.com", "Creator"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Promote League"},
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    league_id = create_response.json()["id"]
    await _make_league_public(client, creator_token, league_id)

    member_token, member_id = await make_user(
        "user_promote_member", "promotemember@example.com", "Member"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {member_token}"}
    )

    other_token, _other_id = await make_user(
        "user_promote_other", "promoteother@example.com", "Other"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {other_token}"}
    )

    response = await client.post(
        f"/leagues/{league_id}/admins/{member_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert response.status_code == 403


async def test_promote_to_admin_by_admin_succeeds(client, make_user, db_session):
    creator_token, _creator_id = await make_user(
        "user_promote_ok_creator", "promoteokcreator@example.com", "Creator"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Promote OK League"},
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    league_id = create_response.json()["id"]
    await _make_league_public(client, creator_token, league_id)

    member_token, member_id = await make_user(
        "user_promote_ok_member", "promoteokmember@example.com", "Member"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {member_token}"}
    )

    response = await client.post(
        f"/leagues/{league_id}/admins/{member_id}",
        headers={"Authorization": f"Bearer {creator_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "admin"
    assert body["user_id"] == member_id

    membership = (
        await db_session.execute(
            select(LeagueUser).where(
                LeagueUser.league_id == league_id, LeagueUser.user_id == member_id
            )
        )
    ).scalar_one()
    assert membership.role == "admin"


async def test_promote_nonmember_returns_404(client, make_user):
    creator_token, _creator_id = await make_user(
        "user_promote_404_creator", "promote404creator@example.com", "Creator"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Promote 404 League"},
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    league_id = create_response.json()["id"]

    response = await client.post(
        f"/leagues/{league_id}/admins/999999", headers={"Authorization": f"Bearer {creator_token}"}
    )

    assert response.status_code == 404


async def test_promote_already_admin_returns_409(client, make_user):
    creator_token, _creator_id = await make_user(
        "user_promote_409_creator", "promote409creator@example.com", "Creator"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Promote 409 League"},
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    league_id = create_response.json()["id"]
    creator_id = create_response.json()["created_by"]

    response = await client.post(
        f"/leagues/{league_id}/admins/{creator_id}",
        headers={"Authorization": f"Bearer {creator_token}"},
    )

    assert response.status_code == 409


async def test_demote_admin_without_token_returns_401(client):
    response = await client.delete("/leagues/1/admins/1")

    assert response.status_code == 401


async def test_demote_admin_by_non_owner_admin_returns_403(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_demote_403_owner", "demote403owner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Demote 403 League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    await _make_league_public(client, owner_token, league_id)

    admin_token, admin_id = await make_user(
        "user_demote_403_admin", "demote403admin@example.com", "Admin"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {admin_token}"}
    )
    await client.post(
        f"/leagues/{league_id}/admins/{admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    other_admin_token, other_admin_id = await make_user(
        "user_demote_403_other", "demote403other@example.com", "OtherAdmin"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {other_admin_token}"}
    )
    await client.post(
        f"/leagues/{league_id}/admins/{other_admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    response = await client.delete(
        f"/leagues/{league_id}/admins/{admin_id}",
        headers={"Authorization": f"Bearer {other_admin_token}"},
    )

    assert response.status_code == 403


async def test_demote_admin_by_owner_succeeds(client, make_user, db_session):
    owner_token, _owner_id = await make_user(
        "user_demote_ok_owner", "demoteokowner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Demote OK League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    await _make_league_public(client, owner_token, league_id)

    admin_token, admin_id = await make_user(
        "user_demote_ok_admin", "demoteokadmin@example.com", "Admin"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {admin_token}"}
    )
    await client.post(
        f"/leagues/{league_id}/admins/{admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    response = await client.delete(
        f"/leagues/{league_id}/admins/{admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "member"

    membership = (
        await db_session.execute(
            select(LeagueUser).where(
                LeagueUser.league_id == league_id, LeagueUser.user_id == admin_id
            )
        )
    ).scalar_one()
    assert membership.role == "member"


async def test_demote_owner_returns_409(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_demote_owner_409", "demoteowner409@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Demote Owner League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    owner_id = create_response.json()["created_by"]

    response = await client.delete(
        f"/leagues/{league_id}/admins/{owner_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 409


async def test_demote_plain_member_returns_409(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_demote_plain_409", "demoteplain409@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Demote Plain League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    await _make_league_public(client, owner_token, league_id)

    member_token, member_id = await make_user(
        "user_demote_plain_member", "demoteplainmember@example.com", "Member"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {member_token}"}
    )

    response = await client.delete(
        f"/leagues/{league_id}/admins/{member_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 409


async def test_demote_nonmember_returns_404(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_demote_404_owner", "demote404owner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Demote 404 League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]

    response = await client.delete(
        f"/leagues/{league_id}/admins/999999", headers={"Authorization": f"Bearer {owner_token}"}
    )

    assert response.status_code == 404


async def test_kick_member_without_token_returns_401(client):
    response = await client.delete("/leagues/1/members/1")

    assert response.status_code == 401


async def test_kick_member_by_admin_succeeds(client, make_user, db_session):
    owner_token, _owner_id = await make_user(
        "user_kick_ok_owner", "kickokowner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Kick OK League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    await _make_league_public(client, owner_token, league_id)

    member_token, member_id = await make_user(
        "user_kick_ok_member", "kickokmember@example.com", "Member"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {member_token}"}
    )

    response = await client.delete(
        f"/leagues/{league_id}/members/{member_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 204

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


async def test_kick_member_by_non_admin_returns_403(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_kick_403_owner", "kick403owner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Kick 403 League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    await _make_league_public(client, owner_token, league_id)

    member_a_token, member_a_id = await make_user(
        "user_kick_403_a", "kick403a@example.com", "MemberA"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {member_a_token}"}
    )

    member_b_token, _member_b_id = await make_user(
        "user_kick_403_b", "kick403b@example.com", "MemberB"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {member_b_token}"}
    )

    response = await client.delete(
        f"/leagues/{league_id}/members/{member_a_id}",
        headers={"Authorization": f"Bearer {member_b_token}"},
    )

    assert response.status_code == 403


async def test_kick_admin_by_non_owner_admin_returns_403(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_kick_admin_403_owner", "kickadmin403owner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Kick Admin 403 League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    await _make_league_public(client, owner_token, league_id)

    admin_token, admin_id = await make_user(
        "user_kick_admin_403_admin", "kickadmin403admin@example.com", "Admin"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {admin_token}"}
    )
    await client.post(
        f"/leagues/{league_id}/admins/{admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    other_admin_token, other_admin_id = await make_user(
        "user_kick_admin_403_other",
        "kickadmin403other@example.com",
        "OtherAdmin",
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {other_admin_token}"}
    )
    await client.post(
        f"/leagues/{league_id}/admins/{other_admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    response = await client.delete(
        f"/leagues/{league_id}/members/{admin_id}",
        headers={"Authorization": f"Bearer {other_admin_token}"},
    )

    assert response.status_code == 403


async def test_kick_admin_by_owner_succeeds(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_kick_admin_ok_owner", "kickadminokowner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Kick Admin OK League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    await _make_league_public(client, owner_token, league_id)

    admin_token, admin_id = await make_user(
        "user_kick_admin_ok_admin", "kickadminokadmin@example.com", "Admin"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {admin_token}"}
    )
    await client.post(
        f"/leagues/{league_id}/admins/{admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    response = await client.delete(
        f"/leagues/{league_id}/members/{admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 204


async def test_kick_owner_returns_409(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_kick_owner_403", "kickowner403@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Kick Owner League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    owner_id = create_response.json()["created_by"]
    await _make_league_public(client, owner_token, league_id)

    second_admin_token, second_admin_id = await make_user(
        "user_kick_owner_403_second", "kickowner403second@example.com", "Second"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {second_admin_token}"}
    )
    await client.post(
        f"/leagues/{league_id}/admins/{second_admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    response = await client.delete(
        f"/leagues/{league_id}/members/{owner_id}",
        headers={"Authorization": f"Bearer {second_admin_token}"},
    )

    assert response.status_code == 409


async def test_self_kick_returns_409(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_selfkick_409", "selfkick409@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Self Kick League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    owner_id = create_response.json()["created_by"]

    response = await client.delete(
        f"/leagues/{league_id}/members/{owner_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 409


async def test_kick_nonmember_returns_404(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_kick_404_owner", "kick404owner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Kick 404 League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]

    response = await client.delete(
        f"/leagues/{league_id}/members/999999", headers={"Authorization": f"Bearer {owner_token}"}
    )

    assert response.status_code == 404


async def test_transfer_ownership_without_token_returns_401(client):
    response = await client.post("/leagues/1/owner", json={"new_owner_id": 1})

    assert response.status_code == 401


async def test_transfer_ownership_by_non_owner_returns_403(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_transfer_403_owner", "transfer403owner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Transfer 403 League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    await _make_league_public(client, owner_token, league_id)

    member_token, member_id = await make_user(
        "user_transfer_403_member", "transfer403member@example.com", "Member"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {member_token}"}
    )

    response = await client.post(
        f"/leagues/{league_id}/owner",
        json={"new_owner_id": member_id},
        headers={"Authorization": f"Bearer {member_token}"},
    )

    assert response.status_code == 403


async def test_transfer_ownership_to_member_succeeds(client, make_user, db_session):
    owner_token, _owner_id = await make_user(
        "user_transfer_ok_owner", "transferokowner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Transfer OK League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    await _make_league_public(client, owner_token, league_id)

    member_token, member_id = await make_user(
        "user_transfer_ok_member", "transferokmember@example.com", "Member"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {member_token}"}
    )

    response = await client.post(
        f"/leagues/{league_id}/owner",
        json={"new_owner_id": member_id},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 200
    assert response.json()["owner_id"] == member_id

    league = await db_session.get(League, league_id)
    assert league.owner_id == member_id

    membership = (
        await db_session.execute(
            select(LeagueUser).where(
                LeagueUser.league_id == league_id, LeagueUser.user_id == member_id
            )
        )
    ).scalar_one()
    assert membership.role == "admin"


async def test_transfer_ownership_to_existing_admin_succeeds(client, make_user, db_session):
    owner_token, _owner_id = await make_user(
        "user_transfer_admin_owner",
        "transferadminowner@example.com",
        "Owner",
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Transfer Admin League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    await _make_league_public(client, owner_token, league_id)

    admin_token, admin_id = await make_user(
        "user_transfer_admin_target",
        "transferadmintarget@example.com",
        "Admin",
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {admin_token}"}
    )
    await client.post(
        f"/leagues/{league_id}/admins/{admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    response = await client.post(
        f"/leagues/{league_id}/owner",
        json={"new_owner_id": admin_id},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 200
    assert response.json()["owner_id"] == admin_id

    membership = (
        await db_session.execute(
            select(LeagueUser).where(
                LeagueUser.league_id == league_id, LeagueUser.user_id == admin_id
            )
        )
    ).scalar_one()
    assert membership.role == "admin"


async def test_transfer_ownership_to_nonmember_returns_404(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_transfer_404_owner", "transfer404owner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Transfer 404 League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]

    response = await client.post(
        f"/leagues/{league_id}/owner",
        json={"new_owner_id": 999999},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 404


async def test_transfer_ownership_to_self_returns_409(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_transfer_409_owner", "transfer409owner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Transfer 409 League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    owner_id = create_response.json()["created_by"]

    response = await client.post(
        f"/leagues/{league_id}/owner",
        json={"new_owner_id": owner_id},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 409


async def test_owner_leave_without_transfer_returns_409(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_leave_owner_409", "leaveowner409@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Leave Owner League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]

    response = await client.post(
        f"/leagues/{league_id}/leave", headers={"Authorization": f"Bearer {owner_token}"}
    )

    assert response.status_code == 409


async def test_owner_leave_as_sole_member_returns_409(client, make_user):
    """Same check as above, named explicitly for the AC's 'even when they're the only member'
    case -- there's no separate code path for it (owner_id doesn't depend on member count), but
    this pins that behavior against a future regression that adds member-counting logic."""
    owner_token, _owner_id = await make_user(
        "user_leave_sole_409", "leavesole409@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Sole Member League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]

    response = await client.post(
        f"/leagues/{league_id}/leave", headers={"Authorization": f"Bearer {owner_token}"}
    )

    assert response.status_code == 409


async def test_owner_can_leave_after_transferring(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_leave_after_transfer_owner",
        "leaveaftertransferowner@example.com",
        "Owner",
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Leave After Transfer League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    await _make_league_public(client, owner_token, league_id)

    member_token, member_id = await make_user(
        "user_leave_after_transfer_member",
        "leaveaftertransfermember@example.com",
        "Member",
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {member_token}"}
    )

    await client.post(
        f"/leagues/{league_id}/owner",
        json={"new_owner_id": member_id},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    response = await client.post(
        f"/leagues/{league_id}/leave", headers={"Authorization": f"Bearer {owner_token}"}
    )

    assert response.status_code == 204


async def test_non_owner_member_can_still_leave_freely(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_leave_free_owner", "leavefreeowner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Leave Freely League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    await _make_league_public(client, owner_token, league_id)

    member_token, _member_id = await make_user(
        "user_leave_free_member", "leavefreemember@example.com", "Member"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {member_token}"}
    )

    response = await client.post(
        f"/leagues/{league_id}/leave", headers={"Authorization": f"Bearer {member_token}"}
    )

    assert response.status_code == 204


async def test_patch_league_without_token_returns_401(client):
    response = await client.patch("/leagues/1", json={"visibility": "public"})

    assert response.status_code == 401


async def test_patch_league_empty_body_is_noop(client, make_user):
    token, _creator_id = await make_user("user_patch_noop", "patchnoop@example.com", "Patch Noop")
    create_response = await client.post(
        "/leagues",
        json={"name": "Patch Noop League"},
        headers={"Authorization": f"Bearer {token}"},
    )
    league_id = create_response.json()["id"]

    response = await client.patch(
        f"/leagues/{league_id}", json={}, headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["visibility"] == "private"
    assert body["invite_policy"] == "owner_only"
    assert body["settings_policy"] == "owner_only"


async def test_patch_league_invalid_visibility_returns_422(client, make_user):
    token, _creator_id = await make_user("user_patch_422", "patch422@example.com", "Patch 422")
    create_response = await client.post(
        "/leagues",
        json={"name": "Patch 422 League"},
        headers={"Authorization": f"Bearer {token}"},
    )
    league_id = create_response.json()["id"]

    response = await client.patch(
        f"/leagues/{league_id}",
        json={"visibility": "foo"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


async def test_patch_league_owner_can_change_visibility(client, make_user, db_session):
    token, _creator_id = await make_user(
        "user_patch_owner", "patchowner@example.com", "Patch Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Patch Owner League"},
        headers={"Authorization": f"Bearer {token}"},
    )
    league_id = create_response.json()["id"]

    response = await client.patch(
        f"/leagues/{league_id}",
        json={"visibility": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["visibility"] == "public"

    league = await db_session.get(League, league_id)
    assert league.visibility == "public"


async def test_patch_league_settings_policy_owner_only_blocks_non_owner_admin(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_patch_oo_owner", "patchooowner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Patch Owner Only League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    await _make_league_public(client, owner_token, league_id)

    admin_token, admin_id = await make_user(
        "user_patch_oo_admin", "patchooadmin@example.com", "Admin"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {admin_token}"}
    )
    await client.post(
        f"/leagues/{league_id}/admins/{admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    response = await client.patch(
        f"/leagues/{league_id}",
        json={"visibility": "private"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Only the league owner can change these settings"


async def test_patch_league_settings_policy_admins_only_allows_admin(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_patch_ao_owner", "patchaoowner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Patch Admins Only League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    await _make_league_public(client, owner_token, league_id)

    admin_token, admin_id = await make_user(
        "user_patch_ao_admin", "patchaoadmin@example.com", "Admin"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {admin_token}"}
    )
    await client.post(
        f"/leagues/{league_id}/admins/{admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    setup_response = await client.patch(
        f"/leagues/{league_id}",
        json={"settings_policy": "admins_only"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert setup_response.status_code == 200

    response = await client.patch(
        f"/leagues/{league_id}",
        json={"visibility": "public"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert response.json()["visibility"] == "public"


async def test_patch_league_settings_policy_admins_only_still_blocks_plain_member(
    client, make_user
):
    owner_token, _owner_id = await make_user(
        "user_patch_ao_member_owner", "patchaomemberowner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Patch Admins Only Member League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    await _make_league_public(client, owner_token, league_id)

    setup_response = await client.patch(
        f"/leagues/{league_id}",
        json={"settings_policy": "admins_only"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert setup_response.status_code == 200

    member_token, _member_id = await make_user(
        "user_patch_ao_member", "patchaomember@example.com", "Member"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {member_token}"}
    )

    response = await client.patch(
        f"/leagues/{league_id}",
        json={"invite_policy": "anyone"},
        headers={"Authorization": f"Bearer {member_token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "League admin privileges required"


async def test_patch_league_non_owner_cannot_change_settings_policy_even_under_admins_only(
    client, make_user
):
    owner_token, _owner_id = await make_user(
        "user_patch_sp_owner", "patchspowner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Patch Settings Policy League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    await _make_league_public(client, owner_token, league_id)

    admin_token, admin_id = await make_user(
        "user_patch_sp_admin", "patchspadmin@example.com", "Admin"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {admin_token}"}
    )
    await client.post(
        f"/leagues/{league_id}/admins/{admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    setup_response = await client.patch(
        f"/leagues/{league_id}",
        json={"settings_policy": "admins_only"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert setup_response.status_code == 200

    response = await client.patch(
        f"/leagues/{league_id}",
        json={"settings_policy": "owner_only"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Only the league owner can change settings_policy"


async def test_patch_league_owner_combines_settings_policy_and_visibility_in_one_request(
    client, make_user, db_session
):
    owner_token, _owner_id = await make_user(
        "user_patch_combo_owner", "patchcomboowner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Patch Combo League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]

    response = await client.patch(
        f"/leagues/{league_id}",
        json={"settings_policy": "admins_only", "visibility": "public"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["settings_policy"] == "admins_only"
    assert body["visibility"] == "public"

    league = await db_session.get(League, league_id)
    assert league.settings_policy == "admins_only"
    assert league.visibility == "public"


async def test_patch_league_owner_can_change_settings_policy_alone(client, make_user, db_session):
    token, _creator_id = await make_user(
        "user_patch_sp_alone", "patchspalone@example.com", "Patch SP Alone"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Patch Settings Policy Alone League"},
        headers={"Authorization": f"Bearer {token}"},
    )
    league_id = create_response.json()["id"]

    response = await client.patch(
        f"/leagues/{league_id}",
        json={"settings_policy": "admins_only"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["settings_policy"] == "admins_only"

    league = await db_session.get(League, league_id)
    assert league.settings_policy == "admins_only"


async def test_patch_nonexistent_league_returns_404(client, make_user):
    token, _creator_id = await make_user("user_patch_404", "patch404@example.com", "Patch 404")

    response = await client.patch(
        "/leagues/999999",
        json={"visibility": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


async def test_join_public_league_succeeds(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_join_public_owner", "joinpublicowner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Join Public League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    await client.patch(
        f"/leagues/{league_id}",
        json={"visibility": "public"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    joiner_token, _joiner_id = await make_user(
        "user_join_public_joiner", "joinpublicjoiner@example.com", "Joiner"
    )
    response = await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {joiner_token}"}
    )

    assert response.status_code == 204


async def test_join_private_league_returns_409(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_join_private_owner", "joinprivateowner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Join Private League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]

    joiner_token, _joiner_id = await make_user(
        "user_join_private_joiner", "joinprivatejoiner@example.com", "Joiner"
    )
    response = await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {joiner_token}"}
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "This league is not public"


async def test_patch_league_admin_can_change_invite_policy_under_admins_only(
    client, make_user, db_session
):
    owner_token, _owner_id = await make_user(
        "user_patch_ip_owner", "patchipowner@example.com", "Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Patch Invite Policy League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]

    admin_token, admin_id = await make_user(
        "user_patch_ip_admin", "patchipadmin@example.com", "Admin"
    )
    await _make_league_public(client, owner_token, league_id)
    join_response = await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert join_response.status_code == 204
    promote_response = await client.post(
        f"/leagues/{league_id}/admins/{admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert promote_response.status_code == 200
    settings_response = await client.patch(
        f"/leagues/{league_id}",
        json={"settings_policy": "admins_only"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert settings_response.status_code == 200

    response = await client.patch(
        f"/leagues/{league_id}",
        json={"invite_policy": "anyone"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert response.json()["invite_policy"] == "anyone"

    league = await db_session.get(League, league_id)
    assert league.invite_policy == "anyone"
