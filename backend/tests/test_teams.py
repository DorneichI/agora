from app.models import Team


async def _make_admin(client, make_clerk_token, db_session, clerk_id, email, name):
    token = make_clerk_token(clerk_id=clerk_id, email=email, name=name)
    me_response = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    user_id = me_response.json()["id"]

    from app.models import User

    user = await db_session.get(User, user_id)
    user.role = "admin"
    db_session.add(user)
    await db_session.commit()

    return token, user_id


async def test_create_team_without_token_returns_401(client):
    response = await client.post(
        "/teams", json={"name": "Crimson", "school": "Harvard", "mascot": "Crimson"}
    )

    assert response.status_code == 401


async def test_create_team_as_non_admin_returns_403(client, make_clerk_token):
    token = make_clerk_token(
        clerk_id="user_team_nonadmin", email="teamnonadmin@example.com", name="Non Admin"
    )
    await client.get("/me", headers={"Authorization": f"Bearer {token}"})

    response = await client.post(
        "/teams",
        json={"name": "Crimson", "school": "Harvard", "mascot": "Crimson"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


async def test_create_team_as_admin_sets_created_by(client, make_clerk_token, db_session):
    token, admin_id = await _make_admin(
        client, make_clerk_token, db_session, "user_team_admin", "teamadmin@example.com", "Admin"
    )

    response = await client.post(
        "/teams",
        json={"name": "Crimson", "school": "Harvard", "mascot": "Crimson"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Crimson"
    assert body["school"] == "Harvard"
    assert body["mascot"] == "Crimson"
    assert body["image_url"] is None
    assert body["created_by"] == admin_id
    assert body["updated_by"] is None
    assert set(body.keys()) == {
        "id",
        "name",
        "school",
        "mascot",
        "image_url",
        "created_by",
        "updated_by",
    }

    team = await db_session.get(Team, body["id"])
    assert team.created_by == admin_id


async def test_get_team_without_token_returns_401(client):
    response = await client.get("/teams/1")

    assert response.status_code == 401


async def test_get_team_as_non_admin_succeeds(client, make_clerk_token, db_session):
    token, _admin_id = await _make_admin(
        client,
        make_clerk_token,
        db_session,
        "user_team_get_admin",
        "teamgetadmin@example.com",
        "Admin",
    )
    create_response = await client.post(
        "/teams",
        json={"name": "Elis", "school": "Yale", "mascot": "Bulldogs"},
        headers={"Authorization": f"Bearer {token}"},
    )
    team_id = create_response.json()["id"]

    reader_token = make_clerk_token(
        clerk_id="user_team_reader", email="teamreader@example.com", name="Reader"
    )
    response = await client.get(
        f"/teams/{team_id}", headers={"Authorization": f"Bearer {reader_token}"}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Elis"


async def test_get_nonexistent_team_returns_404(client, make_clerk_token):
    token = make_clerk_token(
        clerk_id="user_team_missing", email="teammissing@example.com", name="Missing"
    )

    response = await client.get("/teams/999999", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404


async def test_get_soft_deleted_team_returns_404(client, make_clerk_token, db_session):
    token, _admin_id = await _make_admin(
        client,
        make_clerk_token,
        db_session,
        "user_team_softdel",
        "teamsoftdel@example.com",
        "Admin",
    )
    create_response = await client.post(
        "/teams",
        json={"name": "Disbanded", "school": "Nowhere", "mascot": "Ghosts"},
        headers={"Authorization": f"Bearer {token}"},
    )
    team_id = create_response.json()["id"]

    team = await db_session.get(Team, team_id)
    await db_session.delete(team)
    await db_session.commit()

    response = await client.get(f"/teams/{team_id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404


async def test_list_teams_without_token_returns_401(client):
    response = await client.get("/teams")

    assert response.status_code == 401


async def test_list_teams_returns_all_active_teams(client, make_clerk_token, db_session):
    token, _admin_id = await _make_admin(
        client, make_clerk_token, db_session, "user_team_lister", "teamlister@example.com", "Admin"
    )
    await client.post(
        "/teams",
        json={"name": "Crimson", "school": "Harvard", "mascot": "Crimson"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        "/teams",
        json={"name": "Elis", "school": "Yale", "mascot": "Bulldogs"},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.get("/teams", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    names = {team["name"] for team in response.json()}
    assert {"Crimson", "Elis"} <= names


async def test_patch_team_without_token_returns_401(client):
    response = await client.patch("/teams/1", json={"name": "New Name"})

    assert response.status_code == 401


async def test_patch_team_as_non_admin_returns_403(client, make_clerk_token, db_session):
    token, _admin_id = await _make_admin(
        client,
        make_clerk_token,
        db_session,
        "user_team_patch_owner",
        "teampatchowner@example.com",
        "Admin",
    )
    create_response = await client.post(
        "/teams",
        json={"name": "Crimson", "school": "Harvard", "mascot": "Crimson"},
        headers={"Authorization": f"Bearer {token}"},
    )
    team_id = create_response.json()["id"]

    nonadmin_token = make_clerk_token(
        clerk_id="user_team_patch_nonadmin", email="teampatchnonadmin@example.com", name="Non Admin"
    )
    await client.get("/me", headers={"Authorization": f"Bearer {nonadmin_token}"})

    response = await client.patch(
        f"/teams/{team_id}",
        json={"name": "New Name"},
        headers={"Authorization": f"Bearer {nonadmin_token}"},
    )

    assert response.status_code == 403


async def test_patch_nonexistent_team_returns_404(client, make_clerk_token, db_session):
    token, _admin_id = await _make_admin(
        client,
        make_clerk_token,
        db_session,
        "user_team_patch_missing",
        "teampatchmissing@example.com",
        "Admin",
    )

    response = await client.patch(
        "/teams/999999",
        json={"name": "New Name"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


async def test_patch_team_updates_fields_and_sets_updated_by(client, make_clerk_token, db_session):
    token, admin_id = await _make_admin(
        client,
        make_clerk_token,
        db_session,
        "user_team_patch_admin",
        "teampatchadmin@example.com",
        "Admin",
    )
    create_response = await client.post(
        "/teams",
        json={"name": "Crimson", "school": "Harvard", "mascot": "Crimson"},
        headers={"Authorization": f"Bearer {token}"},
    )
    team_id = create_response.json()["id"]

    response = await client.patch(
        f"/teams/{team_id}",
        json={"mascot": "Crimson Tide"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Crimson"
    assert body["mascot"] == "Crimson Tide"
    assert body["updated_by"] == admin_id


async def test_patch_team_can_clear_image_url(client, make_clerk_token, db_session):
    token, _admin_id = await _make_admin(
        client,
        make_clerk_token,
        db_session,
        "user_team_patch_clear",
        "teampatchclear@example.com",
        "Admin",
    )
    create_response = await client.post(
        "/teams",
        json={
            "name": "Elis",
            "school": "Yale",
            "mascot": "Bulldogs",
            "image_url": "https://example.com/yale.png",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    team_id = create_response.json()["id"]

    response = await client.patch(
        f"/teams/{team_id}",
        json={"image_url": None},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["image_url"] is None


async def test_delete_team_without_token_returns_401(client):
    response = await client.delete("/teams/1")

    assert response.status_code == 401


async def test_delete_team_as_non_admin_returns_403(client, make_clerk_token, db_session):
    token, _admin_id = await _make_admin(
        client,
        make_clerk_token,
        db_session,
        "user_team_delete_owner",
        "teamdeleteowner@example.com",
        "Admin",
    )
    create_response = await client.post(
        "/teams",
        json={"name": "Crimson", "school": "Harvard", "mascot": "Crimson"},
        headers={"Authorization": f"Bearer {token}"},
    )
    team_id = create_response.json()["id"]

    nonadmin_token = make_clerk_token(
        clerk_id="user_team_delete_nonadmin",
        email="teamdeletenonadmin@example.com",
        name="Non Admin",
    )
    await client.get("/me", headers={"Authorization": f"Bearer {nonadmin_token}"})

    response = await client.delete(
        f"/teams/{team_id}", headers={"Authorization": f"Bearer {nonadmin_token}"}
    )

    assert response.status_code == 403


async def test_delete_nonexistent_team_returns_404(client, make_clerk_token, db_session):
    token, _admin_id = await _make_admin(
        client,
        make_clerk_token,
        db_session,
        "user_team_delete_missing",
        "teamdeletemissing@example.com",
        "Admin",
    )

    response = await client.delete("/teams/999999", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404


async def test_delete_team_soft_deletes(client, make_clerk_token, db_session):
    token, _admin_id = await _make_admin(
        client,
        make_clerk_token,
        db_session,
        "user_team_delete_admin",
        "teamdeleteadmin@example.com",
        "Admin",
    )
    create_response = await client.post(
        "/teams",
        json={"name": "Crimson", "school": "Harvard", "mascot": "Crimson"},
        headers={"Authorization": f"Bearer {token}"},
    )
    team_id = create_response.json()["id"]

    response = await client.delete(
        f"/teams/{team_id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 204

    get_response = await client.get(
        f"/teams/{team_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert get_response.status_code == 404

    from sqlmodel import select

    row = (
        await db_session.execute(
            select(Team).where(Team.id == team_id).execution_options(include_deleted=True)
        )
    ).scalar_one()
    assert row.deleted_at is not None
