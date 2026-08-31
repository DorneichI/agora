from app.gameplay.models import RaceEntry

EVENT_PAYLOAD = {
    "name": "Head of the Charles",
    "description": "Fall regatta on the Charles River",
    "format": "regatta",
    "start_date": "2026-10-17",
    "end_date": "2026-10-18",
}


async def _create_event(client, token):
    response = await client.post(
        "/events", json=EVENT_PAYLOAD, headers={"Authorization": f"Bearer {token}"}
    )
    return response.json()["id"]


async def _create_race(client, token, event_id):
    response = await client.post(
        "/races",
        json={"event_id": event_id, "boat_class": "8+", "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )
    return response.json()["id"]


async def _create_team(client, token, name="Crimson"):
    response = await client.post(
        "/teams",
        json={"name": name, "school": "Harvard", "mascot": "Crimson"},
        headers={"Authorization": f"Bearer {token}"},
    )
    return response.json()["id"]


async def _create_race_and_team(client, token):
    event_id = await _create_event(client, token)
    race_id = await _create_race(client, token, event_id)
    team_id = await _create_team(client, token)
    return race_id, team_id


async def test_create_race_entry_without_token_returns_401(client):
    response = await client.post(
        "/race-entries", json={"race_id": 1, "team_id": 1, "level": "varsity"}
    )

    assert response.status_code == 401


async def test_create_race_entry_as_non_admin_returns_403(client, make_clerk_token, make_admin):
    token, _admin_id = await make_admin("user_re_setup", "resetup@example.com", "Admin")
    race_id, team_id = await _create_race_and_team(client, token)

    nonadmin_token = make_clerk_token(
        clerk_id="user_re_nonadmin", email="renonadmin@example.com", name="Non Admin"
    )
    await client.get("/me", headers={"Authorization": f"Bearer {nonadmin_token}"})

    response = await client.post(
        "/race-entries",
        json={"race_id": race_id, "team_id": team_id, "level": "varsity"},
        headers={"Authorization": f"Bearer {nonadmin_token}"},
    )

    assert response.status_code == 403


async def test_create_race_entry_as_admin_sets_created_by_and_defaults(
    client, make_admin, db_session
):
    token, admin_id = await make_admin("user_re_admin", "readmin@example.com", "Admin")
    race_id, team_id = await _create_race_and_team(client, token)

    response = await client.post(
        "/race-entries",
        json={"race_id": race_id, "team_id": team_id, "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["race_id"] == race_id
    assert body["team_id"] == team_id
    assert body["level"] == "varsity"
    assert body["time"] is None
    assert body["status"] == "dns"
    assert body["created_by"] == admin_id
    assert body["updated_by"] is None
    assert set(body.keys()) == {
        "id",
        "race_id",
        "team_id",
        "level",
        "time",
        "status",
        "created_by",
        "updated_by",
    }

    entry = await db_session.get(RaceEntry, body["id"])
    assert entry.created_by == admin_id


async def test_create_race_entry_with_nonexistent_race_id_returns_422(client, make_admin):
    token, _admin_id = await make_admin("user_re_badrace", "rebadrace@example.com", "Admin")
    team_id = await _create_team(client, token)

    response = await client.post(
        "/race-entries",
        json={"race_id": 999999, "team_id": team_id, "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


async def test_create_race_entry_with_nonexistent_team_id_returns_422(client, make_admin):
    token, _admin_id = await make_admin("user_re_badteam", "rebadteam@example.com", "Admin")
    event_id = await _create_event(client, token)
    race_id = await _create_race(client, token, event_id)

    response = await client.post(
        "/race-entries",
        json={"race_id": race_id, "team_id": 999999, "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


async def test_create_race_entry_with_invalid_status_returns_422(client, make_admin):
    token, _admin_id = await make_admin("user_re_badstatus", "rebadstatus@example.com", "Admin")
    race_id, team_id = await _create_race_and_team(client, token)

    response = await client.post(
        "/race-entries",
        json={"race_id": race_id, "team_id": team_id, "level": "varsity", "status": "winning"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


async def test_create_duplicate_active_race_entry_returns_409(client, make_admin):
    token, _admin_id = await make_admin("user_re_dup409", "redup409@example.com", "Admin")
    race_id, team_id = await _create_race_and_team(client, token)

    await client.post(
        "/race-entries",
        json={"race_id": race_id, "team_id": team_id, "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )
    response = await client.post(
        "/race-entries",
        json={"race_id": race_id, "team_id": team_id, "level": "novice"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409


async def test_get_race_entry_without_token_returns_401(client):
    response = await client.get("/race-entries/1")

    assert response.status_code == 401


async def test_get_race_entry_without_username_returns_403(client, make_clerk_token):
    token = make_clerk_token(
        clerk_id="user_re_no_username", email="renousername@example.com", name="No Username"
    )
    await client.get("/me", headers={"Authorization": f"Bearer {token}"})

    response = await client.get("/race-entries/1", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


async def test_get_race_entry_as_non_admin_succeeds(client, make_user, make_admin):
    token, _admin_id = await make_admin("user_re_get_admin", "regetadmin@example.com", "Admin")
    race_id, team_id = await _create_race_and_team(client, token)
    create_response = await client.post(
        "/race-entries",
        json={"race_id": race_id, "team_id": team_id, "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )
    entry_id = create_response.json()["id"]

    reader_token, _reader_id = await make_user("user_re_reader", "rereader@example.com", "Reader")
    response = await client.get(
        f"/race-entries/{entry_id}", headers={"Authorization": f"Bearer {reader_token}"}
    )

    assert response.status_code == 200
    assert response.json()["level"] == "varsity"


async def test_get_nonexistent_race_entry_returns_404(client, make_user):
    token, _user_id = await make_user("user_re_missing", "remissing@example.com", "Missing")

    response = await client.get(
        "/race-entries/999999", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


async def test_get_soft_deleted_race_entry_returns_404(client, db_session, make_admin):
    token, _admin_id = await make_admin("user_re_softdel", "resoftdel@example.com", "Admin")
    race_id, team_id = await _create_race_and_team(client, token)
    create_response = await client.post(
        "/race-entries",
        json={"race_id": race_id, "team_id": team_id, "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )
    entry_id = create_response.json()["id"]

    entry = await db_session.get(RaceEntry, entry_id)
    await db_session.delete(entry)
    await db_session.commit()

    response = await client.get(
        f"/race-entries/{entry_id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


async def test_list_race_entries_without_token_returns_401(client):
    response = await client.get("/race-entries")

    assert response.status_code == 401


async def test_list_race_entries_returns_all_active_entries(client, make_admin):
    token, _admin_id = await make_admin("user_re_lister", "relister@example.com", "Admin")
    event_id = await _create_event(client, token)
    race_id = await _create_race(client, token, event_id)
    team_a = await _create_team(client, token, name="Crimson")
    team_b = await _create_team(client, token, name="Elis")
    await client.post(
        "/race-entries",
        json={"race_id": race_id, "team_id": team_a, "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        "/race-entries",
        json={"race_id": race_id, "team_id": team_b, "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.get("/race-entries", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    team_ids = {entry["team_id"] for entry in response.json()}
    assert {team_a, team_b} <= team_ids


async def test_list_race_entries_excludes_soft_deleted_entries(client, db_session, make_admin):
    token, _admin_id = await make_admin(
        "user_re_list_softdel", "relistsoftdel@example.com", "Admin"
    )
    race_id, team_id = await _create_race_and_team(client, token)
    create_response = await client.post(
        "/race-entries",
        json={"race_id": race_id, "team_id": team_id, "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )
    entry_id = create_response.json()["id"]

    entry = await db_session.get(RaceEntry, entry_id)
    await db_session.delete(entry)
    await db_session.commit()

    response = await client.get("/race-entries", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    entry_ids = {e["id"] for e in response.json()}
    assert entry_id not in entry_ids


async def test_list_race_entries_filters_by_race_id(client, make_admin):
    token, _admin_id = await make_admin("user_re_filter", "refilter@example.com", "Admin")
    event_id = await _create_event(client, token)
    race_one = await _create_race(client, token, event_id)
    race_two = await _create_race(client, token, event_id)
    team_one = await _create_team(client, token, name="Crimson")
    team_two = await _create_team(client, token, name="Bulldogs")

    kept_ids = []
    for team_id in (team_one, team_two):
        response = await client.post(
            "/race-entries",
            json={"race_id": race_one, "team_id": team_id, "level": "varsity"},
            headers={"Authorization": f"Bearer {token}"},
        )
        kept_ids.append(response.json()["id"])

    await client.post(
        "/race-entries",
        json={"race_id": race_two, "team_id": team_one, "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.get(
        f"/race-entries?race_id={race_one}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert {entry["race_id"] for entry in body} == {race_one}
    assert sorted(entry["id"] for entry in body) == sorted(kept_ids)


async def test_list_race_entries_with_unknown_race_id_returns_empty(client, make_admin):
    token, _admin_id = await make_admin(
        "user_re_filter_unknown", "refilterunknown@example.com", "Admin"
    )
    race_id, team_id = await _create_race_and_team(client, token)
    await client.post(
        "/race-entries",
        json={"race_id": race_id, "team_id": team_id, "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.get(
        "/race-entries?race_id=999999", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json() == []


async def test_patch_race_entry_without_token_returns_401(client):
    response = await client.patch("/race-entries/1", json={"status": "finished"})

    assert response.status_code == 401


async def test_patch_race_entry_as_non_admin_returns_403(client, make_clerk_token, make_admin):
    token, _admin_id = await make_admin("user_re_patch_owner", "repatchowner@example.com", "Admin")
    race_id, team_id = await _create_race_and_team(client, token)
    create_response = await client.post(
        "/race-entries",
        json={"race_id": race_id, "team_id": team_id, "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )
    entry_id = create_response.json()["id"]

    nonadmin_token = make_clerk_token(
        clerk_id="user_re_patch_nonadmin",
        email="repatchnonadmin@example.com",
        name="Non Admin",
    )
    await client.get("/me", headers={"Authorization": f"Bearer {nonadmin_token}"})

    response = await client.patch(
        f"/race-entries/{entry_id}",
        json={"status": "finished", "time": 383.45},
        headers={"Authorization": f"Bearer {nonadmin_token}"},
    )

    assert response.status_code == 403


async def test_patch_nonexistent_race_entry_returns_404(client, make_admin):
    token, _admin_id = await make_admin(
        "user_re_patch_missing", "repatchmissing@example.com", "Admin"
    )

    response = await client.patch(
        "/race-entries/999999",
        json={"status": "finished"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


async def test_patch_race_entry_records_result_and_sets_updated_by(client, make_admin):
    token, admin_id = await make_admin("user_re_patch_admin", "repatchadmin@example.com", "Admin")
    race_id, team_id = await _create_race_and_team(client, token)
    create_response = await client.post(
        "/race-entries",
        json={"race_id": race_id, "team_id": team_id, "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )
    entry_id = create_response.json()["id"]

    response = await client.patch(
        f"/race-entries/{entry_id}",
        json={"status": "finished", "time": 383.45},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "finished"
    assert body["time"] == 383.45
    assert body["updated_by"] == admin_id


async def test_patch_race_entry_updates_level_only(client, make_admin):
    token, _admin_id = await make_admin("user_re_patch_level", "repatchlevel@example.com", "Admin")
    race_id, team_id = await _create_race_and_team(client, token)
    create_response = await client.post(
        "/race-entries",
        json={"race_id": race_id, "team_id": team_id, "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )
    entry_id = create_response.json()["id"]

    response = await client.patch(
        f"/race-entries/{entry_id}",
        json={"level": "novice"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["level"] == "novice"
    assert body["status"] == "dns"
    assert body["time"] is None


async def test_patch_race_entry_with_invalid_status_returns_422(client, make_admin):
    token, _admin_id = await make_admin(
        "user_re_patch_badstatus", "repatchbadstatus@example.com", "Admin"
    )
    race_id, team_id = await _create_race_and_team(client, token)
    create_response = await client.post(
        "/race-entries",
        json={"race_id": race_id, "team_id": team_id, "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )
    entry_id = create_response.json()["id"]

    response = await client.patch(
        f"/race-entries/{entry_id}",
        json={"status": "winning"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


async def test_delete_race_entry_without_token_returns_401(client):
    response = await client.delete("/race-entries/1")

    assert response.status_code == 401


async def test_delete_race_entry_as_non_admin_returns_403(client, make_clerk_token, make_admin):
    token, _admin_id = await make_admin(
        "user_re_delete_owner", "redeleteowner@example.com", "Admin"
    )
    race_id, team_id = await _create_race_and_team(client, token)
    create_response = await client.post(
        "/race-entries",
        json={"race_id": race_id, "team_id": team_id, "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )
    entry_id = create_response.json()["id"]

    nonadmin_token = make_clerk_token(
        clerk_id="user_re_delete_nonadmin",
        email="redeletenonadmin@example.com",
        name="Non Admin",
    )
    await client.get("/me", headers={"Authorization": f"Bearer {nonadmin_token}"})

    response = await client.delete(
        f"/race-entries/{entry_id}", headers={"Authorization": f"Bearer {nonadmin_token}"}
    )

    assert response.status_code == 403


async def test_delete_nonexistent_race_entry_returns_404(client, make_admin):
    token, _admin_id = await make_admin(
        "user_re_delete_missing", "redeletemissing@example.com", "Admin"
    )

    response = await client.delete(
        "/race-entries/999999", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


async def test_delete_race_entry_soft_deletes(client, db_session, make_admin):
    token, _admin_id = await make_admin(
        "user_re_delete_admin", "redeleteadmin@example.com", "Admin"
    )
    race_id, team_id = await _create_race_and_team(client, token)
    create_response = await client.post(
        "/race-entries",
        json={"race_id": race_id, "team_id": team_id, "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )
    entry_id = create_response.json()["id"]

    response = await client.delete(
        f"/race-entries/{entry_id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 204

    get_response = await client.get(
        f"/race-entries/{entry_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert get_response.status_code == 404

    from sqlmodel import select

    row = (
        await db_session.execute(
            select(RaceEntry)
            .where(RaceEntry.id == entry_id)
            .execution_options(include_deleted=True)
        )
    ).scalar_one()
    assert row.deleted_at is not None


async def test_delete_race_entry_allows_recreating_same_race_and_team(client, make_admin):
    token, _admin_id = await make_admin(
        "user_re_delete_readd", "redeletereadd@example.com", "Admin"
    )
    race_id, team_id = await _create_race_and_team(client, token)
    create_response = await client.post(
        "/race-entries",
        json={"race_id": race_id, "team_id": team_id, "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )
    entry_id = create_response.json()["id"]

    await client.delete(f"/race-entries/{entry_id}", headers={"Authorization": f"Bearer {token}"})

    response = await client.post(
        "/race-entries",
        json={"race_id": race_id, "team_id": team_id, "level": "novice"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] != entry_id


async def test_patch_race_entry_with_empty_body_does_not_set_updated_by(client, make_admin):
    token, _admin_id = await make_admin("user_re_patch_noop", "repatchnoop@example.com", "Admin")
    race_id, team_id = await _create_race_and_team(client, token)
    create_response = await client.post(
        "/race-entries",
        json={"race_id": race_id, "team_id": team_id, "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )
    entry_id = create_response.json()["id"]

    response = await client.patch(
        f"/race-entries/{entry_id}", json={}, headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["updated_by"] is None
