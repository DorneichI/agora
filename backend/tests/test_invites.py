from datetime import UTC, datetime, timedelta

from sqlmodel import select

from app.leagues.models import LeagueInvite, LeagueUser
from app.models import User


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
    assert response.status_code == 201
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

    assert response.status_code == 201
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

    assert response.status_code == 201
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

    assert response.status_code == 201
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

    assert response.status_code == 201
    body = response.json()
    assert body["target_user_id"] == target_id

    invite_rows = (
        (await db_session.execute(select(LeagueInvite).where(LeagueInvite.id == body["id"])))
        .scalars()
        .all()
    )
    assert len(invite_rows) == 1
    assert invite_rows[0].expires_at is not None


async def test_create_invite_private_league_matches_target_username_case_insensitively(
    client, make_user, db_session
):
    """Regression test: usernames are always stored lowercased (POST /me/username lowercases
    on write), but the invite lookup compared case-sensitively -- so inviting a real user by
    any non-lowercase spelling of their username used to 404."""
    owner_token, _owner_id = await make_user(
        "user_inv_owner_case", "invownercase@example.com", "Owner"
    )
    league_id = await _create_league(client, owner_token, "Invite League Case")

    _target_token, target_id = await make_user(
        "user_inv_target_case", "invtargetcase@example.com", "Target"
    )
    target_user = await db_session.get(User, target_id)
    target_user.username = "casesensitivetarget"
    db_session.add(target_user)
    await db_session.commit()

    response = await client.post(
        f"/leagues/{league_id}/invites",
        json={"target_username": "CaseSensitiveTarget"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 201
    assert response.json()["target_user_id"] == target_id


async def test_create_invite_retries_on_code_collision(client, make_user, db_session, monkeypatch):
    """Pre-seed an existing invite with a fixed code, then force the code-generation loop
    to draw that same code first (colliding with the partial unique index) before a fresh
    one -- proving the retry loop's collision path is actually exercised, not just that the
    happy path works."""
    from app.leagues.routers import invites as invites_module

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

    assert response.status_code == 201
    body = response.json()
    assert body["code"] == fresh_code
    assert body["code"] != colliding_code


async def test_redeem_invite_without_token_returns_401(client):
    response = await client.post("/invites/some-code/redeem")

    assert response.status_code == 401


async def test_redeem_unknown_code_returns_404(client, make_user):
    token, _user_id = await make_user("user_redeem_1", "redeem1@example.com", "Redeemer")

    response = await client.post(
        "/invites/does-not-exist/redeem", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


async def test_redeem_public_invite_joins_league(client, make_user, db_session):
    owner_token, _owner_id = await make_user(
        "user_redeem_owner_1", "redeemowner1@example.com", "Owner"
    )
    league_id = await _create_league(client, owner_token, "Redeem League 1")
    await _make_league_public(client, owner_token, league_id)

    create_response = await client.post(
        f"/leagues/{league_id}/invites",
        json={},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    code = create_response.json()["code"]

    joiner_token, joiner_id = await make_user(
        "user_redeem_joiner_1", "redeemjoiner1@example.com", "Joiner"
    )
    redeem_response = await client.post(
        f"/invites/{code}/redeem", headers={"Authorization": f"Bearer {joiner_token}"}
    )

    assert redeem_response.status_code == 204
    membership = (
        await db_session.execute(
            select(LeagueUser).where(
                LeagueUser.league_id == league_id, LeagueUser.user_id == joiner_id
            )
        )
    ).scalar_one_or_none()
    assert membership is not None
    assert membership.deleted_at is None


async def test_redeem_public_invite_can_be_used_more_than_once(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_redeem_owner_2", "redeemowner2@example.com", "Owner"
    )
    league_id = await _create_league(client, owner_token, "Redeem League 2")
    await _make_league_public(client, owner_token, league_id)

    create_response = await client.post(
        f"/leagues/{league_id}/invites",
        json={},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    code = create_response.json()["code"]

    for i in range(2):
        joiner_token, _joiner_id = await make_user(
            f"user_redeem_joiner_multi_{i}", f"redeemjoinermulti{i}@example.com", "Joiner"
        )
        response = await client.post(
            f"/invites/{code}/redeem", headers={"Authorization": f"Bearer {joiner_token}"}
        )
        assert response.status_code == 204


async def test_redeem_private_targeted_invite_by_target_succeeds_and_sets_redeemed_at(
    client, make_user, db_session
):
    owner_token, _owner_id = await make_user(
        "user_redeem_owner_3", "redeemowner3@example.com", "Owner"
    )
    league_id = await _create_league(client, owner_token, "Redeem League 3")

    target_token, target_id = await make_user(
        "user_redeem_target_1", "redeemtarget1@example.com", "Target"
    )
    create_response = await client.post(
        f"/leagues/{league_id}/invites",
        json={"target_username": f"user{target_id}"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    code = create_response.json()["code"]

    redeem_response = await client.post(
        f"/invites/{code}/redeem", headers={"Authorization": f"Bearer {target_token}"}
    )

    assert redeem_response.status_code == 204
    invite = (
        await db_session.execute(select(LeagueInvite).where(LeagueInvite.code == code))
    ).scalar_one()
    assert invite.redeemed_at is not None

    membership = (
        await db_session.execute(
            select(LeagueUser).where(
                LeagueUser.league_id == league_id, LeagueUser.user_id == target_id
            )
        )
    ).scalar_one_or_none()
    assert membership is not None


async def test_redeem_targeted_invite_by_wrong_user_returns_403(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_redeem_owner_4", "redeemowner4@example.com", "Owner"
    )
    league_id = await _create_league(client, owner_token, "Redeem League 4")

    _target_token, target_id = await make_user(
        "user_redeem_target_2", "redeemtarget2@example.com", "Target"
    )
    create_response = await client.post(
        f"/leagues/{league_id}/invites",
        json={"target_username": f"user{target_id}"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    code = create_response.json()["code"]

    wrong_token, _wrong_id = await make_user(
        "user_redeem_wrong_1", "redeemwrong1@example.com", "Wrong"
    )
    response = await client.post(
        f"/invites/{code}/redeem", headers={"Authorization": f"Bearer {wrong_token}"}
    )

    assert response.status_code == 403


async def test_redeem_targeted_invite_twice_returns_410_second_time(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_redeem_owner_5", "redeemowner5@example.com", "Owner"
    )
    league_id = await _create_league(client, owner_token, "Redeem League 5")

    target_token, target_id = await make_user(
        "user_redeem_target_3", "redeemtarget3@example.com", "Target"
    )
    create_response = await client.post(
        f"/leagues/{league_id}/invites",
        json={"target_username": f"user{target_id}"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    code = create_response.json()["code"]

    first = await client.post(
        f"/invites/{code}/redeem", headers={"Authorization": f"Bearer {target_token}"}
    )
    assert first.status_code == 204

    second = await client.post(
        f"/invites/{code}/redeem", headers={"Authorization": f"Bearer {target_token}"}
    )
    assert second.status_code == 410


async def test_redeem_revoked_invite_returns_410(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_redeem_owner_6", "redeemowner6@example.com", "Owner"
    )
    league_id = await _create_league(client, owner_token, "Redeem League 6")
    await _make_league_public(client, owner_token, league_id)

    create_response = await client.post(
        f"/leagues/{league_id}/invites",
        json={},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    code = create_response.json()["code"]

    revoke_response = await client.delete(
        f"/invites/{code}", headers={"Authorization": f"Bearer {owner_token}"}
    )
    assert revoke_response.status_code == 204

    joiner_token, _joiner_id = await make_user(
        "user_redeem_joiner_2", "redeemjoiner2@example.com", "Joiner"
    )
    response = await client.post(
        f"/invites/{code}/redeem", headers={"Authorization": f"Bearer {joiner_token}"}
    )

    assert response.status_code == 410


async def test_redeem_expired_invite_returns_410(client, make_user, db_session):
    owner_token, _owner_id = await make_user(
        "user_redeem_owner_7", "redeemowner7@example.com", "Owner"
    )
    league_id = await _create_league(client, owner_token, "Redeem League 7")
    await _make_league_public(client, owner_token, league_id)

    create_response = await client.post(
        f"/leagues/{league_id}/invites",
        json={},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    code = create_response.json()["code"]

    invite = (
        await db_session.execute(select(LeagueInvite).where(LeagueInvite.code == code))
    ).scalar_one()
    invite.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.add(invite)
    await db_session.commit()

    joiner_token, _joiner_id = await make_user(
        "user_redeem_joiner_3", "redeemjoiner3@example.com", "Joiner"
    )
    response = await client.post(
        f"/invites/{code}/redeem", headers={"Authorization": f"Bearer {joiner_token}"}
    )

    assert response.status_code == 410


async def test_redeem_already_active_member_is_idempotent(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_redeem_owner_8", "redeemowner8@example.com", "Owner"
    )
    league_id = await _create_league(client, owner_token, "Redeem League 8")
    await _make_league_public(client, owner_token, league_id)

    create_response = await client.post(
        f"/leagues/{league_id}/invites",
        json={},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    code = create_response.json()["code"]

    response = await client.post(
        f"/invites/{code}/redeem", headers={"Authorization": f"Bearer {owner_token}"}
    )

    assert response.status_code == 204


async def test_redeem_concurrent_insert_race_is_idempotent(
    client, make_user, db_session, monkeypatch
):
    """Regression test: same race as join_league's, reached via redeem_invite instead --
    two concurrent redemptions for the same user could both miss the existing-membership
    check before either committed, so the second's INSERT would hit the real partial unique
    index as an unhandled IntegrityError/500. Simulated deterministically by forcing the
    membership lookup to report "not found" even though an active row already exists."""
    from app.leagues.routers import invites as invites_module

    owner_token, _owner_id = await make_user(
        "user_redeem_race_owner", "redeemraceowner@example.com", "Owner"
    )
    league_id = await _create_league(client, owner_token, "Redeem Race League")
    await _make_league_public(client, owner_token, league_id)

    create_response = await client.post(
        f"/leagues/{league_id}/invites",
        json={},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    code = create_response.json()["code"]

    joiner_token, joiner_id = await make_user(
        "user_redeem_race_joiner", "redeemracejoiner@example.com", "Joiner"
    )
    first_redeem = await client.post(
        f"/invites/{code}/redeem", headers={"Authorization": f"Bearer {joiner_token}"}
    )
    assert first_redeem.status_code == 204

    async def _always_report_no_membership(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        invites_module, "get_membership_including_deleted", _always_report_no_membership
    )

    second_redeem = await client.post(
        f"/invites/{code}/redeem", headers={"Authorization": f"Bearer {joiner_token}"}
    )

    assert second_redeem.status_code == 204
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


async def test_redeem_targeted_invite_already_active_member_still_sets_redeemed_at(
    client, make_user, db_session
):
    owner_token, _owner_id = await make_user(
        "user_redeem_owner_9", "redeemowner9@example.com", "Owner"
    )
    league_id = await _create_league(client, owner_token, "Redeem League 9")

    target_token, target_id = await make_user(
        "user_redeem_target_4", "redeemtarget4@example.com", "Target"
    )
    await _add_member(client, owner_token, league_id, target_token)

    create_response = await client.post(
        f"/leagues/{league_id}/invites",
        json={"target_username": f"user{target_id}"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    code = create_response.json()["code"]

    response = await client.post(
        f"/invites/{code}/redeem", headers={"Authorization": f"Bearer {target_token}"}
    )

    assert response.status_code == 204
    invite = (
        await db_session.execute(select(LeagueInvite).where(LeagueInvite.code == code))
    ).scalar_one()
    assert invite.redeemed_at is not None


async def test_redeem_untargeted_invite_becomes_410_after_league_goes_private(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_redeem_owner_10", "redeemowner10@example.com", "Owner"
    )
    league_id = await _create_league(client, owner_token, "Redeem League 10")
    await _make_league_public(client, owner_token, league_id)

    create_response = await client.post(
        f"/leagues/{league_id}/invites",
        json={},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    code = create_response.json()["code"]

    first_joiner_token, _first_joiner_id = await make_user(
        "user_redeem_joiner_4", "redeemjoiner4@example.com", "Joiner"
    )
    still_public_response = await client.post(
        f"/invites/{code}/redeem", headers={"Authorization": f"Bearer {first_joiner_token}"}
    )
    assert still_public_response.status_code == 204

    await _make_league_private(client, owner_token, league_id)

    second_joiner_token, _second_joiner_id = await make_user(
        "user_redeem_joiner_5", "redeemjoiner5@example.com", "Joiner"
    )
    now_private_response = await client.post(
        f"/invites/{code}/redeem", headers={"Authorization": f"Bearer {second_joiner_token}"}
    )

    assert now_private_response.status_code == 410


async def test_redeem_targeted_invite_stays_targeted_after_league_goes_public(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_redeem_owner_11", "redeemowner11@example.com", "Owner"
    )
    league_id = await _create_league(client, owner_token, "Redeem League 11")

    target_token, target_id = await make_user(
        "user_redeem_target_5", "redeemtarget5@example.com", "Target"
    )
    create_response = await client.post(
        f"/leagues/{league_id}/invites",
        json={"target_username": f"user{target_id}"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    code = create_response.json()["code"]

    await _make_league_public(client, owner_token, league_id)

    wrong_token, _wrong_id = await make_user(
        "user_redeem_wrong_2", "redeemwrong2@example.com", "Wrong"
    )
    wrong_response = await client.post(
        f"/invites/{code}/redeem", headers={"Authorization": f"Bearer {wrong_token}"}
    )
    assert wrong_response.status_code == 403

    target_response = await client.post(
        f"/invites/{code}/redeem", headers={"Authorization": f"Bearer {target_token}"}
    )
    assert target_response.status_code == 204

    other_token, _other_id = await make_user(
        "user_redeem_other_1", "redeemother1@example.com", "Other"
    )
    other_response = await client.post(
        f"/invites/{code}/redeem", headers={"Authorization": f"Bearer {other_token}"}
    )
    assert other_response.status_code == 410


async def test_redeem_targeted_invite_resurrects_soft_deleted_membership(
    client, make_user, db_session
):
    owner_token, _owner_id = await make_user(
        "user_redeem_owner_12", "redeemowner12@example.com", "Owner"
    )
    league_id = await _create_league(client, owner_token, "Redeem League 12")

    target_token, target_id = await make_user(
        "user_redeem_target_6", "redeemtarget6@example.com", "Target"
    )
    await _add_member(client, owner_token, league_id, target_token)

    leave_response = await client.post(
        f"/leagues/{league_id}/leave", headers={"Authorization": f"Bearer {target_token}"}
    )
    assert leave_response.status_code == 204

    membership_before = (
        await db_session.execute(
            select(LeagueUser)
            .where(LeagueUser.league_id == league_id, LeagueUser.user_id == target_id)
            .execution_options(include_deleted=True)
        )
    ).scalar_one()
    assert membership_before.deleted_at is not None
    original_membership_id = membership_before.id

    create_response = await client.post(
        f"/leagues/{league_id}/invites",
        json={"target_username": f"user{target_id}"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    code = create_response.json()["code"]

    redeem_response = await client.post(
        f"/invites/{code}/redeem", headers={"Authorization": f"Bearer {target_token}"}
    )

    assert redeem_response.status_code == 204
    membership_after = (
        await db_session.execute(
            select(LeagueUser).where(
                LeagueUser.league_id == league_id, LeagueUser.user_id == target_id
            )
        )
    ).scalar_one()
    assert membership_after.id == original_membership_id
    assert membership_after.deleted_at is None


async def test_redeem_targeted_invite_after_kick_does_not_restore_admin_role(
    client, make_user, db_session
):
    """Regression test: same role-reset gap as join_league, but reached via redeem_invite --
    an admin kicked from the league and later re-invited must come back as a plain member."""
    owner_token, _owner_id = await make_user(
        "user_redeem_role_owner", "redeemroleowner@example.com", "Owner"
    )
    league_id = await _create_league(client, owner_token, "Redeem Role League")

    admin_token, admin_id = await make_user(
        "user_redeem_role_admin", "redeemroleadmin@example.com", "Admin"
    )
    await _add_member(client, owner_token, league_id, admin_token)
    await client.post(
        f"/leagues/{league_id}/admins/{admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    kick_response = await client.delete(
        f"/leagues/{league_id}/members/{admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert kick_response.status_code == 204

    create_response = await client.post(
        f"/leagues/{league_id}/invites",
        json={"target_username": f"user{admin_id}"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    code = create_response.json()["code"]

    redeem_response = await client.post(
        f"/invites/{code}/redeem", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert redeem_response.status_code == 204

    membership = (
        await db_session.execute(
            select(LeagueUser).where(
                LeagueUser.league_id == league_id, LeagueUser.user_id == admin_id
            )
        )
    ).scalar_one()
    assert membership.role == "member"


async def test_revoke_invite_without_token_returns_401(client):
    response = await client.delete("/invites/some-code")

    assert response.status_code == 401


async def test_revoke_unknown_code_returns_404(client, make_user):
    token, _user_id = await make_user("user_revoke_1", "revoke1@example.com", "Revoker")

    response = await client.delete(
        "/invites/does-not-exist", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


async def test_revoke_by_creator_succeeds(client, make_user, db_session):
    owner_token, _owner_id = await make_user(
        "user_revoke_owner_1", "revokeowner1@example.com", "Owner"
    )
    league_id = await _create_league(client, owner_token, "Revoke League 1")
    await _make_league_public(client, owner_token, league_id)

    create_response = await client.post(
        f"/leagues/{league_id}/invites",
        json={},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    code = create_response.json()["code"]

    response = await client.delete(
        f"/invites/{code}", headers={"Authorization": f"Bearer {owner_token}"}
    )

    assert response.status_code == 204
    invite = (
        await db_session.execute(select(LeagueInvite).where(LeagueInvite.code == code))
    ).scalar_one()
    assert invite.revoked_at is not None


async def test_revoke_by_creator_who_has_left_league_still_succeeds(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_revoke_owner_2", "revokeowner2@example.com", "Owner"
    )
    league_id = await _create_league(client, owner_token, "Revoke League 2")
    await _set_invite_policy(client, owner_token, league_id, "anyone")
    await _make_league_public(client, owner_token, league_id)

    creator_token, _creator_id = await make_user(
        "user_revoke_creator_1", "revokecreator1@example.com", "Creator"
    )
    await _add_member(client, owner_token, league_id, creator_token)

    create_response = await client.post(
        f"/leagues/{league_id}/invites",
        json={},
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    code = create_response.json()["code"]

    leave_response = await client.post(
        f"/leagues/{league_id}/leave", headers={"Authorization": f"Bearer {creator_token}"}
    )
    assert leave_response.status_code == 204

    response = await client.delete(
        f"/invites/{code}", headers={"Authorization": f"Bearer {creator_token}"}
    )

    assert response.status_code == 204


async def test_revoke_by_admin_of_someone_elses_invite_succeeds(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_revoke_owner_3", "revokeowner3@example.com", "Owner"
    )
    league_id = await _create_league(client, owner_token, "Revoke League 3")
    await _set_invite_policy(client, owner_token, league_id, "anyone")
    await _make_league_public(client, owner_token, league_id)

    creator_token, _creator_id = await make_user(
        "user_revoke_creator_2", "revokecreator2@example.com", "Creator"
    )
    await _add_member(client, owner_token, league_id, creator_token)

    create_response = await client.post(
        f"/leagues/{league_id}/invites",
        json={},
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    code = create_response.json()["code"]

    response = await client.delete(
        f"/invites/{code}", headers={"Authorization": f"Bearer {owner_token}"}
    )

    assert response.status_code == 204


async def test_revoke_by_plain_member_who_is_not_creator_returns_403(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_revoke_owner_4", "revokeowner4@example.com", "Owner"
    )
    league_id = await _create_league(client, owner_token, "Revoke League 4")
    await _make_league_public(client, owner_token, league_id)

    create_response = await client.post(
        f"/leagues/{league_id}/invites",
        json={},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    code = create_response.json()["code"]

    member_token, _member_id = await make_user(
        "user_revoke_member_1", "revokemember1@example.com", "Member"
    )
    await _add_member(client, owner_token, league_id, member_token)

    response = await client.delete(
        f"/invites/{code}", headers={"Authorization": f"Bearer {member_token}"}
    )

    assert response.status_code == 403


async def test_revoke_already_revoked_invite_returns_410(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_revoke_owner_5", "revokeowner5@example.com", "Owner"
    )
    league_id = await _create_league(client, owner_token, "Revoke League 5")
    await _make_league_public(client, owner_token, league_id)

    create_response = await client.post(
        f"/leagues/{league_id}/invites",
        json={},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    code = create_response.json()["code"]

    first = await client.delete(
        f"/invites/{code}", headers={"Authorization": f"Bearer {owner_token}"}
    )
    assert first.status_code == 204

    second = await client.delete(
        f"/invites/{code}", headers={"Authorization": f"Bearer {owner_token}"}
    )
    assert second.status_code == 410


async def test_revoke_already_redeemed_invite_returns_410(client, make_user):
    owner_token, _owner_id = await make_user(
        "user_revoke_owner_6", "revokeowner6@example.com", "Owner"
    )
    league_id = await _create_league(client, owner_token, "Revoke League 6")

    target_token, target_id = await make_user(
        "user_revoke_target_1", "revoketarget1@example.com", "Target"
    )
    create_response = await client.post(
        f"/leagues/{league_id}/invites",
        json={"target_username": f"user{target_id}"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    code = create_response.json()["code"]

    redeem_response = await client.post(
        f"/invites/{code}/redeem", headers={"Authorization": f"Bearer {target_token}"}
    )
    assert redeem_response.status_code == 204

    response = await client.delete(
        f"/invites/{code}", headers={"Authorization": f"Bearer {owner_token}"}
    )

    assert response.status_code == 410


async def test_revoke_expired_invite_returns_410(client, make_user, db_session):
    owner_token, _owner_id = await make_user(
        "user_revoke_owner_7", "revokeowner7@example.com", "Owner"
    )
    league_id = await _create_league(client, owner_token, "Revoke League 7")
    await _make_league_public(client, owner_token, league_id)

    create_response = await client.post(
        f"/leagues/{league_id}/invites",
        json={},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    code = create_response.json()["code"]

    invite = (
        await db_session.execute(select(LeagueInvite).where(LeagueInvite.code == code))
    ).scalar_one()
    invite.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.add(invite)
    await db_session.commit()

    response = await client.delete(
        f"/invites/{code}", headers={"Authorization": f"Bearer {owner_token}"}
    )

    assert response.status_code == 410
