from app.models import Race

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


async def test_create_race_without_token_returns_401(client):
    response = await client.post(
        "/races", json={"event_id": 1, "boat_class": "8+", "level": "varsity"}
    )

    assert response.status_code == 401


async def test_create_race_as_non_admin_returns_403(client, make_clerk_token, make_admin):
    token, _admin_id = await make_admin("user_race_setup", "racesetup@example.com", "Admin")
    event_id = await _create_event(client, token)

    nonadmin_token = make_clerk_token(
        clerk_id="user_race_nonadmin", email="racenonadmin@example.com", name="Non Admin"
    )
    await client.get("/me", headers={"Authorization": f"Bearer {nonadmin_token}"})

    response = await client.post(
        "/races",
        json={"event_id": event_id, "boat_class": "8+", "level": "varsity"},
        headers={"Authorization": f"Bearer {nonadmin_token}"},
    )

    assert response.status_code == 403


async def test_create_race_as_admin_sets_created_by(client, make_admin, db_session):
    token, admin_id = await make_admin("user_race_admin", "raceadmin@example.com", "Admin")
    event_id = await _create_event(client, token)

    response = await client.post(
        "/races",
        json={"event_id": event_id, "boat_class": "8+", "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["event_id"] == event_id
    assert body["boat_class"] == "8+"
    assert body["level"] == "varsity"
    assert body["round"] is None
    assert body["created_by"] == admin_id
    assert body["updated_by"] is None
    assert set(body.keys()) == {
        "id",
        "event_id",
        "boat_class",
        "level",
        "round",
        "created_by",
        "updated_by",
    }

    race = await db_session.get(Race, body["id"])
    assert race.created_by == admin_id


async def test_create_race_with_nonexistent_event_id_returns_422(client, make_admin):
    token, _admin_id = await make_admin("user_race_badevent", "racebadevent@example.com", "Admin")

    response = await client.post(
        "/races",
        json={"event_id": 999999, "boat_class": "8+", "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


async def test_get_race_without_token_returns_401(client):
    response = await client.get("/races/1")

    assert response.status_code == 401


async def test_get_race_as_non_admin_succeeds(client, make_clerk_token, make_admin):
    token, _admin_id = await make_admin("user_race_get_admin", "racegetadmin@example.com", "Admin")
    event_id = await _create_event(client, token)
    create_response = await client.post(
        "/races",
        json={"event_id": event_id, "boat_class": "4+", "level": "3v"},
        headers={"Authorization": f"Bearer {token}"},
    )
    race_id = create_response.json()["id"]

    reader_token = make_clerk_token(
        clerk_id="user_race_reader", email="racereader@example.com", name="Reader"
    )
    response = await client.get(
        f"/races/{race_id}", headers={"Authorization": f"Bearer {reader_token}"}
    )

    assert response.status_code == 200
    assert response.json()["boat_class"] == "4+"


async def test_get_nonexistent_race_returns_404(client, make_clerk_token):
    token = make_clerk_token(
        clerk_id="user_race_missing", email="racemissing@example.com", name="Missing"
    )

    response = await client.get("/races/999999", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404


async def test_get_soft_deleted_race_returns_404(client, db_session, make_admin):
    token, _admin_id = await make_admin("user_race_softdel", "racesoftdel@example.com", "Admin")
    event_id = await _create_event(client, token)
    create_response = await client.post(
        "/races",
        json={"event_id": event_id, "boat_class": "8+", "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )
    race_id = create_response.json()["id"]

    race = await db_session.get(Race, race_id)
    await db_session.delete(race)
    await db_session.commit()

    response = await client.get(f"/races/{race_id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404


async def test_list_races_without_token_returns_401(client):
    response = await client.get("/races")

    assert response.status_code == 401


async def test_list_races_returns_all_active_races(client, make_admin):
    token, _admin_id = await make_admin("user_race_lister", "racelister@example.com", "Admin")
    event_id = await _create_event(client, token)
    await client.post(
        "/races",
        json={"event_id": event_id, "boat_class": "8+", "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        "/races",
        json={"event_id": event_id, "boat_class": "4+", "level": "3v"},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.get("/races", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    boat_classes = {race["boat_class"] for race in response.json()}
    assert {"8+", "4+"} <= boat_classes


async def test_list_races_excludes_soft_deleted_races(client, db_session, make_admin):
    token, _admin_id = await make_admin(
        "user_race_list_softdel", "racelistsoftdel@example.com", "Admin"
    )
    event_id = await _create_event(client, token)
    create_response = await client.post(
        "/races",
        json={"event_id": event_id, "boat_class": "2x", "level": "novice"},
        headers={"Authorization": f"Bearer {token}"},
    )
    race_id = create_response.json()["id"]

    race = await db_session.get(Race, race_id)
    await db_session.delete(race)
    await db_session.commit()

    response = await client.get("/races", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    boat_classes = {r["boat_class"] for r in response.json()}
    assert "2x" not in boat_classes


async def test_patch_race_without_token_returns_401(client):
    response = await client.patch("/races/1", json={"level": "novice"})

    assert response.status_code == 401


async def test_patch_race_as_non_admin_returns_403(client, make_clerk_token, make_admin):
    token, _admin_id = await make_admin(
        "user_race_patch_owner", "racepatchowner@example.com", "Admin"
    )
    event_id = await _create_event(client, token)
    create_response = await client.post(
        "/races",
        json={"event_id": event_id, "boat_class": "8+", "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )
    race_id = create_response.json()["id"]

    nonadmin_token = make_clerk_token(
        clerk_id="user_race_patch_nonadmin",
        email="racepatchnonadmin@example.com",
        name="Non Admin",
    )
    await client.get("/me", headers={"Authorization": f"Bearer {nonadmin_token}"})

    response = await client.patch(
        f"/races/{race_id}",
        json={"level": "novice"},
        headers={"Authorization": f"Bearer {nonadmin_token}"},
    )

    assert response.status_code == 403


async def test_patch_nonexistent_race_returns_404(client, make_admin):
    token, _admin_id = await make_admin(
        "user_race_patch_missing", "racepatchmissing@example.com", "Admin"
    )

    response = await client.patch(
        "/races/999999",
        json={"level": "novice"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


async def test_patch_race_updates_fields_and_sets_updated_by(client, make_admin):
    token, admin_id = await make_admin(
        "user_race_patch_admin", "racepatchadmin@example.com", "Admin"
    )
    event_id = await _create_event(client, token)
    create_response = await client.post(
        "/races",
        json={"event_id": event_id, "boat_class": "8+", "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )
    race_id = create_response.json()["id"]

    response = await client.patch(
        f"/races/{race_id}",
        json={"round": "final"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["round"] == "final"
    assert body["updated_by"] == admin_id


async def test_delete_race_without_token_returns_401(client):
    response = await client.delete("/races/1")

    assert response.status_code == 401


async def test_delete_race_as_non_admin_returns_403(client, make_clerk_token, make_admin):
    token, _admin_id = await make_admin(
        "user_race_delete_owner", "racedeleteowner@example.com", "Admin"
    )
    event_id = await _create_event(client, token)
    create_response = await client.post(
        "/races",
        json={"event_id": event_id, "boat_class": "8+", "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )
    race_id = create_response.json()["id"]

    nonadmin_token = make_clerk_token(
        clerk_id="user_race_delete_nonadmin",
        email="racedeletenonadmin@example.com",
        name="Non Admin",
    )
    await client.get("/me", headers={"Authorization": f"Bearer {nonadmin_token}"})

    response = await client.delete(
        f"/races/{race_id}", headers={"Authorization": f"Bearer {nonadmin_token}"}
    )

    assert response.status_code == 403


async def test_delete_nonexistent_race_returns_404(client, make_admin):
    token, _admin_id = await make_admin(
        "user_race_delete_missing", "racedeletemissing@example.com", "Admin"
    )

    response = await client.delete("/races/999999", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404


async def test_delete_race_soft_deletes(client, db_session, make_admin):
    token, _admin_id = await make_admin(
        "user_race_delete_admin", "racedeleteadmin@example.com", "Admin"
    )
    event_id = await _create_event(client, token)
    create_response = await client.post(
        "/races",
        json={"event_id": event_id, "boat_class": "8+", "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )
    race_id = create_response.json()["id"]

    response = await client.delete(
        f"/races/{race_id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 204

    get_response = await client.get(
        f"/races/{race_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert get_response.status_code == 404

    from sqlmodel import select

    row = (
        await db_session.execute(
            select(Race).where(Race.id == race_id).execution_options(include_deleted=True)
        )
    ).scalar_one()
    assert row.deleted_at is not None
