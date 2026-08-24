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
