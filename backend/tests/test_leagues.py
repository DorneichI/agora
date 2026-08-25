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
    assert league_rows[0].owner_id == body["created_by"]

    membership_rows = (
        (await db_session.execute(select(LeagueUser).where(LeagueUser.league_id == body["id"])))
        .scalars()
        .all()
    )
    assert len(membership_rows) == 1
    assert membership_rows[0].user_id == body["created_by"]
    assert membership_rows[0].role == "admin"


async def test_create_league_response_excludes_internal_fields(client, make_clerk_token):
    """LeagueRead is the response shape, not the League table model -- soft-delete
    bookkeeping columns must not be exposed to API consumers."""
    token = make_clerk_token(
        clerk_id="user_league_read_shape", email="readshape@example.com", name="Read Shape"
    )

    response = await client.post(
        "/leagues",
        json={"name": "Charles River Regatta"},
        headers={"Authorization": f"Bearer {token}"},
    )

    body = response.json()
    assert set(body.keys()) == {"id", "name", "created_by", "owner_id"}


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
    body = get_response.json()
    assert body["name"] == "Boston Sprints"
    assert set(body.keys()) == {"id", "name", "created_by", "owner_id"}


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


async def test_join_league_without_token_returns_401(client):
    response = await client.post("/leagues/1/join")

    assert response.status_code == 401


async def test_join_nonexistent_league_returns_404(client, make_clerk_token):
    token = make_clerk_token(
        clerk_id="user_join_missing_league", email="joinmissing@example.com", name="Join Missing"
    )

    response = await client.post(
        "/leagues/999999/join", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


async def test_join_league_creates_active_membership(client, make_clerk_token, db_session):
    creator_token = make_clerk_token(
        clerk_id="user_join_creator", email="joincreator@example.com", name="Join Creator"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Join Test League"},
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    league_id = create_response.json()["id"]

    joiner_token = make_clerk_token(
        clerk_id="user_join_joiner", email="joinjoiner@example.com", name="Join Joiner"
    )
    join_response = await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {joiner_token}"}
    )

    assert join_response.status_code == 204

    me_response = await client.get("/me", headers={"Authorization": f"Bearer {joiner_token}"})
    joiner_id = me_response.json()["id"]

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


async def test_join_league_already_active_member_is_idempotent(
    client, make_clerk_token, db_session
):
    token = make_clerk_token(
        clerk_id="user_join_idempotent", email="joinidempotent@example.com", name="Join Idempotent"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Idempotent Join League"},
        headers={"Authorization": f"Bearer {token}"},
    )
    league_id = create_response.json()["id"]
    creator_id = create_response.json()["created_by"]

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


async def test_rejoin_after_leave_resurrects_same_row(client, make_clerk_token, db_session):
    creator_token = make_clerk_token(
        clerk_id="user_rejoin_creator", email="rejoincreator@example.com", name="Rejoin Creator"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Rejoin Test League"},
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    league_id = create_response.json()["id"]

    joiner_token = make_clerk_token(
        clerk_id="user_rejoin_joiner", email="rejoinjoiner@example.com", name="Rejoin Joiner"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {joiner_token}"}
    )

    me_response = await client.get("/me", headers={"Authorization": f"Bearer {joiner_token}"})
    joiner_id = me_response.json()["id"]

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


async def test_leave_nonexistent_league_returns_404(client, make_clerk_token):
    token = make_clerk_token(
        clerk_id="user_leave_missing_league",
        email="leavemissing@example.com",
        name="Leave Missing",
    )

    response = await client.post(
        "/leagues/999999/leave", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


async def test_leave_league_soft_deletes_membership(client, make_clerk_token, db_session):
    token = make_clerk_token(
        clerk_id="user_leave_member", email="leavemember@example.com", name="Leave Member"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Leave Test League"},
        headers={"Authorization": f"Bearer {token}"},
    )
    league_id = create_response.json()["id"]
    member_id = create_response.json()["created_by"]

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


async def test_leave_league_never_joined_is_noop(client, make_clerk_token):
    creator_token = make_clerk_token(
        clerk_id="user_leave_noop_creator", email="leavenoopcreator@example.com", name="Creator"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Never Joined League"},
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    league_id = create_response.json()["id"]

    bystander_token = make_clerk_token(
        clerk_id="user_leave_noop_bystander",
        email="leavenoopbystander@example.com",
        name="Bystander",
    )
    response = await client.post(
        f"/leagues/{league_id}/leave", headers={"Authorization": f"Bearer {bystander_token}"}
    )

    assert response.status_code == 204


async def test_promote_to_admin_without_token_returns_401(client):
    response = await client.post("/leagues/1/admins/1")

    assert response.status_code == 401


async def test_promote_to_admin_by_non_admin_returns_403(client, make_clerk_token, db_session):
    creator_token = make_clerk_token(
        clerk_id="user_promote_creator", email="promotecreator@example.com", name="Creator"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Promote League"},
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    league_id = create_response.json()["id"]

    member_token = make_clerk_token(
        clerk_id="user_promote_member", email="promotemember@example.com", name="Member"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {member_token}"}
    )
    member_id = (
        await client.get("/me", headers={"Authorization": f"Bearer {member_token}"})
    ).json()["id"]

    other_token = make_clerk_token(
        clerk_id="user_promote_other", email="promoteother@example.com", name="Other"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {other_token}"}
    )

    response = await client.post(
        f"/leagues/{league_id}/admins/{member_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert response.status_code == 403


async def test_promote_to_admin_by_admin_succeeds(client, make_clerk_token, db_session):
    creator_token = make_clerk_token(
        clerk_id="user_promote_ok_creator", email="promoteokcreator@example.com", name="Creator"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Promote OK League"},
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    league_id = create_response.json()["id"]

    member_token = make_clerk_token(
        clerk_id="user_promote_ok_member", email="promoteokmember@example.com", name="Member"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {member_token}"}
    )
    member_id = (
        await client.get("/me", headers={"Authorization": f"Bearer {member_token}"})
    ).json()["id"]

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


async def test_promote_nonmember_returns_404(client, make_clerk_token):
    creator_token = make_clerk_token(
        clerk_id="user_promote_404_creator", email="promote404creator@example.com", name="Creator"
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


async def test_promote_already_admin_returns_409(client, make_clerk_token):
    creator_token = make_clerk_token(
        clerk_id="user_promote_409_creator", email="promote409creator@example.com", name="Creator"
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


async def test_demote_admin_by_non_owner_admin_returns_403(client, make_clerk_token):
    owner_token = make_clerk_token(
        clerk_id="user_demote_403_owner", email="demote403owner@example.com", name="Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Demote 403 League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]

    admin_token = make_clerk_token(
        clerk_id="user_demote_403_admin", email="demote403admin@example.com", name="Admin"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {admin_token}"}
    )
    admin_id = (await client.get("/me", headers={"Authorization": f"Bearer {admin_token}"})).json()[
        "id"
    ]
    await client.post(
        f"/leagues/{league_id}/admins/{admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    other_admin_token = make_clerk_token(
        clerk_id="user_demote_403_other", email="demote403other@example.com", name="OtherAdmin"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {other_admin_token}"}
    )
    other_admin_id = (
        await client.get("/me", headers={"Authorization": f"Bearer {other_admin_token}"})
    ).json()["id"]
    await client.post(
        f"/leagues/{league_id}/admins/{other_admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    response = await client.delete(
        f"/leagues/{league_id}/admins/{admin_id}",
        headers={"Authorization": f"Bearer {other_admin_token}"},
    )

    assert response.status_code == 403


async def test_demote_admin_by_owner_succeeds(client, make_clerk_token, db_session):
    owner_token = make_clerk_token(
        clerk_id="user_demote_ok_owner", email="demoteokowner@example.com", name="Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Demote OK League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]

    admin_token = make_clerk_token(
        clerk_id="user_demote_ok_admin", email="demoteokadmin@example.com", name="Admin"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {admin_token}"}
    )
    admin_id = (await client.get("/me", headers={"Authorization": f"Bearer {admin_token}"})).json()[
        "id"
    ]
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


async def test_demote_owner_returns_409(client, make_clerk_token):
    owner_token = make_clerk_token(
        clerk_id="user_demote_owner_409", email="demoteowner409@example.com", name="Owner"
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


async def test_demote_plain_member_returns_409(client, make_clerk_token):
    owner_token = make_clerk_token(
        clerk_id="user_demote_plain_409", email="demoteplain409@example.com", name="Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Demote Plain League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]

    member_token = make_clerk_token(
        clerk_id="user_demote_plain_member", email="demoteplainmember@example.com", name="Member"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {member_token}"}
    )
    member_id = (
        await client.get("/me", headers={"Authorization": f"Bearer {member_token}"})
    ).json()["id"]

    response = await client.delete(
        f"/leagues/{league_id}/admins/{member_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 409


async def test_demote_nonmember_returns_404(client, make_clerk_token):
    owner_token = make_clerk_token(
        clerk_id="user_demote_404_owner", email="demote404owner@example.com", name="Owner"
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


async def test_kick_member_by_admin_succeeds(client, make_clerk_token, db_session):
    owner_token = make_clerk_token(
        clerk_id="user_kick_ok_owner", email="kickokowner@example.com", name="Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Kick OK League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]

    member_token = make_clerk_token(
        clerk_id="user_kick_ok_member", email="kickokmember@example.com", name="Member"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {member_token}"}
    )
    member_id = (
        await client.get("/me", headers={"Authorization": f"Bearer {member_token}"})
    ).json()["id"]

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


async def test_kick_member_by_non_admin_returns_403(client, make_clerk_token):
    owner_token = make_clerk_token(
        clerk_id="user_kick_403_owner", email="kick403owner@example.com", name="Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Kick 403 League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]

    member_a_token = make_clerk_token(
        clerk_id="user_kick_403_a", email="kick403a@example.com", name="MemberA"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {member_a_token}"}
    )
    member_a_id = (
        await client.get("/me", headers={"Authorization": f"Bearer {member_a_token}"})
    ).json()["id"]

    member_b_token = make_clerk_token(
        clerk_id="user_kick_403_b", email="kick403b@example.com", name="MemberB"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {member_b_token}"}
    )

    response = await client.delete(
        f"/leagues/{league_id}/members/{member_a_id}",
        headers={"Authorization": f"Bearer {member_b_token}"},
    )

    assert response.status_code == 403


async def test_kick_admin_by_non_owner_admin_returns_403(client, make_clerk_token):
    owner_token = make_clerk_token(
        clerk_id="user_kick_admin_403_owner", email="kickadmin403owner@example.com", name="Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Kick Admin 403 League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]

    admin_token = make_clerk_token(
        clerk_id="user_kick_admin_403_admin", email="kickadmin403admin@example.com", name="Admin"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {admin_token}"}
    )
    admin_id = (await client.get("/me", headers={"Authorization": f"Bearer {admin_token}"})).json()[
        "id"
    ]
    await client.post(
        f"/leagues/{league_id}/admins/{admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    other_admin_token = make_clerk_token(
        clerk_id="user_kick_admin_403_other",
        email="kickadmin403other@example.com",
        name="OtherAdmin",
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {other_admin_token}"}
    )
    other_admin_id = (
        await client.get("/me", headers={"Authorization": f"Bearer {other_admin_token}"})
    ).json()["id"]
    await client.post(
        f"/leagues/{league_id}/admins/{other_admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    response = await client.delete(
        f"/leagues/{league_id}/members/{admin_id}",
        headers={"Authorization": f"Bearer {other_admin_token}"},
    )

    assert response.status_code == 403


async def test_kick_admin_by_owner_succeeds(client, make_clerk_token):
    owner_token = make_clerk_token(
        clerk_id="user_kick_admin_ok_owner", email="kickadminokowner@example.com", name="Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Kick Admin OK League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]

    admin_token = make_clerk_token(
        clerk_id="user_kick_admin_ok_admin", email="kickadminokadmin@example.com", name="Admin"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {admin_token}"}
    )
    admin_id = (await client.get("/me", headers={"Authorization": f"Bearer {admin_token}"})).json()[
        "id"
    ]
    await client.post(
        f"/leagues/{league_id}/admins/{admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    response = await client.delete(
        f"/leagues/{league_id}/members/{admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 204


async def test_kick_owner_returns_403(client, make_clerk_token):
    owner_token = make_clerk_token(
        clerk_id="user_kick_owner_403", email="kickowner403@example.com", name="Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Kick Owner League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]
    owner_id = create_response.json()["created_by"]

    second_admin_token = make_clerk_token(
        clerk_id="user_kick_owner_403_second", email="kickowner403second@example.com", name="Second"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {second_admin_token}"}
    )
    second_admin_id = (
        await client.get("/me", headers={"Authorization": f"Bearer {second_admin_token}"})
    ).json()["id"]
    await client.post(
        f"/leagues/{league_id}/admins/{second_admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    response = await client.delete(
        f"/leagues/{league_id}/members/{owner_id}",
        headers={"Authorization": f"Bearer {second_admin_token}"},
    )

    assert response.status_code == 403


async def test_self_kick_returns_409(client, make_clerk_token):
    owner_token = make_clerk_token(
        clerk_id="user_selfkick_409", email="selfkick409@example.com", name="Owner"
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


async def test_kick_nonmember_returns_404(client, make_clerk_token):
    owner_token = make_clerk_token(
        clerk_id="user_kick_404_owner", email="kick404owner@example.com", name="Owner"
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


async def test_transfer_ownership_by_non_owner_returns_403(client, make_clerk_token):
    owner_token = make_clerk_token(
        clerk_id="user_transfer_403_owner", email="transfer403owner@example.com", name="Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Transfer 403 League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]

    member_token = make_clerk_token(
        clerk_id="user_transfer_403_member", email="transfer403member@example.com", name="Member"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {member_token}"}
    )
    member_id = (
        await client.get("/me", headers={"Authorization": f"Bearer {member_token}"})
    ).json()["id"]

    response = await client.post(
        f"/leagues/{league_id}/owner",
        json={"new_owner_id": member_id},
        headers={"Authorization": f"Bearer {member_token}"},
    )

    assert response.status_code == 403


async def test_transfer_ownership_to_member_succeeds(client, make_clerk_token, db_session):
    owner_token = make_clerk_token(
        clerk_id="user_transfer_ok_owner", email="transferokowner@example.com", name="Owner"
    )
    create_response = await client.post(
        "/leagues",
        json={"name": "Transfer OK League"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    league_id = create_response.json()["id"]

    member_token = make_clerk_token(
        clerk_id="user_transfer_ok_member", email="transferokmember@example.com", name="Member"
    )
    await client.post(
        f"/leagues/{league_id}/join", headers={"Authorization": f"Bearer {member_token}"}
    )
    member_id = (
        await client.get("/me", headers={"Authorization": f"Bearer {member_token}"})
    ).json()["id"]

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


async def test_transfer_ownership_to_nonmember_returns_404(client, make_clerk_token):
    owner_token = make_clerk_token(
        clerk_id="user_transfer_404_owner", email="transfer404owner@example.com", name="Owner"
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


async def test_transfer_ownership_to_self_returns_409(client, make_clerk_token):
    owner_token = make_clerk_token(
        clerk_id="user_transfer_409_owner", email="transfer409owner@example.com", name="Owner"
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
