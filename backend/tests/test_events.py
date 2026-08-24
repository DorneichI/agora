from app.models import Event

EVENT_PAYLOAD = {
    "name": "Head of the Charles",
    "description": "Fall regatta on the Charles River",
    "format": "regatta",
    "start_date": "2026-10-17",
    "end_date": "2026-10-18",
}


async def test_create_event_without_token_returns_401(client):
    response = await client.post("/events", json=EVENT_PAYLOAD)

    assert response.status_code == 401


async def test_create_event_as_non_admin_returns_403(client, make_clerk_token):
    token = make_clerk_token(
        clerk_id="user_event_nonadmin", email="eventnonadmin@example.com", name="Non Admin"
    )
    await client.get("/me", headers={"Authorization": f"Bearer {token}"})

    response = await client.post(
        "/events", json=EVENT_PAYLOAD, headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403


async def test_create_event_as_admin_sets_created_by(client, make_admin, db_session):
    token, admin_id = await make_admin("user_event_admin", "eventadmin@example.com", "Admin")

    response = await client.post(
        "/events", json=EVENT_PAYLOAD, headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Head of the Charles"
    assert body["description"] == "Fall regatta on the Charles River"
    assert body["venue_id"] is None
    assert body["format"] == "regatta"
    assert body["start_date"] == "2026-10-17"
    assert body["end_date"] == "2026-10-18"
    assert body["image_url"] is None
    assert body["created_by"] == admin_id
    assert body["updated_by"] is None
    assert set(body.keys()) == {
        "id",
        "name",
        "description",
        "venue_id",
        "format",
        "start_date",
        "end_date",
        "image_url",
        "created_by",
        "updated_by",
    }

    event = await db_session.get(Event, body["id"])
    assert event.created_by == admin_id


async def test_create_event_with_venue_id_succeeds(client, make_admin):
    token, _admin_id = await make_admin("user_event_venue", "eventvenue@example.com", "Admin")

    venue_response = await client.post(
        "/venues",
        json={"name": "Red Top", "location": "Ledyard, CT"},
        headers={"Authorization": f"Bearer {token}"},
    )
    venue_id = venue_response.json()["id"]

    response = await client.post(
        "/events",
        json={**EVENT_PAYLOAD, "venue_id": venue_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["venue_id"] == venue_id


async def test_create_event_with_nonexistent_venue_id_returns_422(client, make_admin):
    token, _admin_id = await make_admin("user_event_badvenue", "eventbadvenue@example.com", "Admin")

    response = await client.post(
        "/events",
        json={**EVENT_PAYLOAD, "venue_id": 999999},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


async def test_get_event_without_token_returns_401(client):
    response = await client.get("/events/1")

    assert response.status_code == 401


async def test_get_event_as_non_admin_succeeds(client, make_clerk_token, make_admin):
    token, _admin_id = await make_admin(
        "user_event_get_admin", "eventgetadmin@example.com", "Admin"
    )
    create_response = await client.post(
        "/events", json=EVENT_PAYLOAD, headers={"Authorization": f"Bearer {token}"}
    )
    event_id = create_response.json()["id"]

    reader_token = make_clerk_token(
        clerk_id="user_event_reader", email="eventreader@example.com", name="Reader"
    )
    response = await client.get(
        f"/events/{event_id}", headers={"Authorization": f"Bearer {reader_token}"}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Head of the Charles"


async def test_get_nonexistent_event_returns_404(client, make_clerk_token):
    token = make_clerk_token(
        clerk_id="user_event_missing", email="eventmissing@example.com", name="Missing"
    )

    response = await client.get("/events/999999", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404


async def test_get_soft_deleted_event_returns_404(client, db_session, make_admin):
    token, _admin_id = await make_admin("user_event_softdel", "eventsoftdel@example.com", "Admin")
    create_response = await client.post(
        "/events", json=EVENT_PAYLOAD, headers={"Authorization": f"Bearer {token}"}
    )
    event_id = create_response.json()["id"]

    event = await db_session.get(Event, event_id)
    await db_session.delete(event)
    await db_session.commit()

    response = await client.get(f"/events/{event_id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404


async def test_list_events_without_token_returns_401(client):
    response = await client.get("/events")

    assert response.status_code == 401


async def test_list_events_returns_all_active_events(client, make_admin):
    token, _admin_id = await make_admin("user_event_lister", "eventlister@example.com", "Admin")
    await client.post("/events", json=EVENT_PAYLOAD, headers={"Authorization": f"Bearer {token}"})
    await client.post(
        "/events",
        json={**EVENT_PAYLOAD, "name": "Eastern Sprints"},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.get("/events", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    names = {event["name"] for event in response.json()}
    assert {"Head of the Charles", "Eastern Sprints"} <= names


async def test_list_events_excludes_soft_deleted_events(client, db_session, make_admin):
    token, _admin_id = await make_admin(
        "user_event_list_softdel", "eventlistsoftdel@example.com", "Admin"
    )
    create_response = await client.post(
        "/events",
        json={**EVENT_PAYLOAD, "name": "Ghosted Regatta"},
        headers={"Authorization": f"Bearer {token}"},
    )
    event_id = create_response.json()["id"]

    event = await db_session.get(Event, event_id)
    await db_session.delete(event)
    await db_session.commit()

    response = await client.get("/events", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    names = {e["name"] for e in response.json()}
    assert "Ghosted Regatta" not in names


async def test_patch_event_without_token_returns_401(client):
    response = await client.patch("/events/1", json={"name": "New Name"})

    assert response.status_code == 401


async def test_patch_event_as_non_admin_returns_403(client, make_clerk_token, make_admin):
    token, _admin_id = await make_admin(
        "user_event_patch_owner", "eventpatchowner@example.com", "Admin"
    )
    create_response = await client.post(
        "/events", json=EVENT_PAYLOAD, headers={"Authorization": f"Bearer {token}"}
    )
    event_id = create_response.json()["id"]

    nonadmin_token = make_clerk_token(
        clerk_id="user_event_patch_nonadmin",
        email="eventpatchnonadmin@example.com",
        name="Non Admin",
    )
    await client.get("/me", headers={"Authorization": f"Bearer {nonadmin_token}"})

    response = await client.patch(
        f"/events/{event_id}",
        json={"name": "New Name"},
        headers={"Authorization": f"Bearer {nonadmin_token}"},
    )

    assert response.status_code == 403


async def test_patch_nonexistent_event_returns_404(client, make_admin):
    token, _admin_id = await make_admin(
        "user_event_patch_missing", "eventpatchmissing@example.com", "Admin"
    )

    response = await client.patch(
        "/events/999999",
        json={"name": "New Name"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


async def test_patch_event_updates_fields_and_sets_updated_by(client, make_admin):
    token, admin_id = await make_admin(
        "user_event_patch_admin", "eventpatchadmin@example.com", "Admin"
    )
    create_response = await client.post(
        "/events", json=EVENT_PAYLOAD, headers={"Authorization": f"Bearer {token}"}
    )
    event_id = create_response.json()["id"]

    response = await client.patch(
        f"/events/{event_id}",
        json={"description": "Updated description"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["description"] == "Updated description"
    assert body["updated_by"] == admin_id


async def test_patch_event_can_set_and_clear_venue_id(client, make_admin):
    token, _admin_id = await make_admin(
        "user_event_patch_venue", "eventpatchvenue@example.com", "Admin"
    )
    create_response = await client.post(
        "/events", json=EVENT_PAYLOAD, headers={"Authorization": f"Bearer {token}"}
    )
    event_id = create_response.json()["id"]

    venue_response = await client.post(
        "/venues",
        json={"name": "Cooper River", "location": "Camden, NJ"},
        headers={"Authorization": f"Bearer {token}"},
    )
    venue_id = venue_response.json()["id"]

    set_response = await client.patch(
        f"/events/{event_id}",
        json={"venue_id": venue_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert set_response.status_code == 200
    assert set_response.json()["venue_id"] == venue_id

    clear_response = await client.patch(
        f"/events/{event_id}",
        json={"venue_id": None},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert clear_response.status_code == 200
    assert clear_response.json()["venue_id"] is None


async def test_patch_event_venue_id_to_nonexistent_returns_422(client, make_admin):
    token, _admin_id = await make_admin(
        "user_event_patch_badvenue", "eventpatchbadvenue@example.com", "Admin"
    )
    create_response = await client.post(
        "/events", json=EVENT_PAYLOAD, headers={"Authorization": f"Bearer {token}"}
    )
    event_id = create_response.json()["id"]

    response = await client.patch(
        f"/events/{event_id}",
        json={"venue_id": 999999},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


async def test_delete_event_without_token_returns_401(client):
    response = await client.delete("/events/1")

    assert response.status_code == 401


async def test_delete_event_as_non_admin_returns_403(client, make_clerk_token, make_admin):
    token, _admin_id = await make_admin(
        "user_event_delete_owner", "eventdeleteowner@example.com", "Admin"
    )
    create_response = await client.post(
        "/events", json=EVENT_PAYLOAD, headers={"Authorization": f"Bearer {token}"}
    )
    event_id = create_response.json()["id"]

    nonadmin_token = make_clerk_token(
        clerk_id="user_event_delete_nonadmin",
        email="eventdeletenonadmin@example.com",
        name="Non Admin",
    )
    await client.get("/me", headers={"Authorization": f"Bearer {nonadmin_token}"})

    response = await client.delete(
        f"/events/{event_id}", headers={"Authorization": f"Bearer {nonadmin_token}"}
    )

    assert response.status_code == 403


async def test_delete_nonexistent_event_returns_404(client, make_admin):
    token, _admin_id = await make_admin(
        "user_event_delete_missing", "eventdeletemissing@example.com", "Admin"
    )

    response = await client.delete("/events/999999", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404


async def test_delete_event_soft_deletes(client, db_session, make_admin):
    token, _admin_id = await make_admin(
        "user_event_delete_admin", "eventdeleteadmin@example.com", "Admin"
    )
    create_response = await client.post(
        "/events", json=EVENT_PAYLOAD, headers={"Authorization": f"Bearer {token}"}
    )
    event_id = create_response.json()["id"]

    response = await client.delete(
        f"/events/{event_id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 204

    get_response = await client.get(
        f"/events/{event_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert get_response.status_code == 404

    from sqlmodel import select

    row = (
        await db_session.execute(
            select(Event).where(Event.id == event_id).execution_options(include_deleted=True)
        )
    ).scalar_one()
    assert row.deleted_at is not None
