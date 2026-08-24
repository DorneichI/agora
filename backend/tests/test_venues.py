from app.models import Venue


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


async def test_create_venue_without_token_returns_401(client):
    response = await client.post("/venues", json={"name": "Red Top", "location": "Ledyard, CT"})

    assert response.status_code == 401


async def test_create_venue_as_non_admin_returns_403(client, make_clerk_token):
    token = make_clerk_token(
        clerk_id="user_venue_nonadmin", email="venuenonadmin@example.com", name="Non Admin"
    )
    await client.get("/me", headers={"Authorization": f"Bearer {token}"})

    response = await client.post(
        "/venues",
        json={"name": "Red Top", "location": "Ledyard, CT"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


async def test_create_venue_as_admin_sets_created_by(client, make_clerk_token, db_session):
    token, admin_id = await _make_admin(
        client, make_clerk_token, db_session, "user_venue_admin", "venueadmin@example.com", "Admin"
    )

    response = await client.post(
        "/venues",
        json={"name": "Red Top", "location": "Ledyard, CT"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Red Top"
    assert body["location"] == "Ledyard, CT"
    assert body["image_url"] is None
    assert body["created_by"] == admin_id
    assert body["updated_by"] is None
    assert set(body.keys()) == {
        "id",
        "name",
        "location",
        "image_url",
        "created_by",
        "updated_by",
    }

    venue = await db_session.get(Venue, body["id"])
    assert venue.created_by == admin_id


async def test_get_venue_without_token_returns_401(client):
    response = await client.get("/venues/1")

    assert response.status_code == 401


async def test_get_venue_as_non_admin_succeeds(client, make_clerk_token, db_session):
    token, _admin_id = await _make_admin(
        client,
        make_clerk_token,
        db_session,
        "user_venue_get_admin",
        "venuegetadmin@example.com",
        "Admin",
    )
    create_response = await client.post(
        "/venues",
        json={"name": "Cooper River", "location": "Camden, NJ"},
        headers={"Authorization": f"Bearer {token}"},
    )
    venue_id = create_response.json()["id"]

    reader_token = make_clerk_token(
        clerk_id="user_venue_reader", email="venuereader@example.com", name="Reader"
    )
    response = await client.get(
        f"/venues/{venue_id}", headers={"Authorization": f"Bearer {reader_token}"}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Cooper River"


async def test_get_nonexistent_venue_returns_404(client, make_clerk_token):
    token = make_clerk_token(
        clerk_id="user_venue_missing", email="venuemissing@example.com", name="Missing"
    )

    response = await client.get("/venues/999999", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404


async def test_get_soft_deleted_venue_returns_404(client, make_clerk_token, db_session):
    token, _admin_id = await _make_admin(
        client,
        make_clerk_token,
        db_session,
        "user_venue_softdel",
        "venuesoftdel@example.com",
        "Admin",
    )
    create_response = await client.post(
        "/venues",
        json={"name": "Disbanded Course", "location": "Nowhere"},
        headers={"Authorization": f"Bearer {token}"},
    )
    venue_id = create_response.json()["id"]

    venue = await db_session.get(Venue, venue_id)
    await db_session.delete(venue)
    await db_session.commit()

    response = await client.get(f"/venues/{venue_id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404


async def test_list_venues_without_token_returns_401(client):
    response = await client.get("/venues")

    assert response.status_code == 401


async def test_list_venues_returns_all_active_venues(client, make_clerk_token, db_session):
    token, _admin_id = await _make_admin(
        client,
        make_clerk_token,
        db_session,
        "user_venue_lister",
        "venuelister@example.com",
        "Admin",
    )
    await client.post(
        "/venues",
        json={"name": "Red Top", "location": "Ledyard, CT"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        "/venues",
        json={"name": "Cooper River", "location": "Camden, NJ"},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.get("/venues", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    names = {venue["name"] for venue in response.json()}
    assert {"Red Top", "Cooper River"} <= names


async def test_patch_venue_without_token_returns_401(client):
    response = await client.patch("/venues/1", json={"name": "New Name"})

    assert response.status_code == 401


async def test_patch_venue_as_non_admin_returns_403(client, make_clerk_token, db_session):
    token, _admin_id = await _make_admin(
        client,
        make_clerk_token,
        db_session,
        "user_venue_patch_owner",
        "venuepatchowner@example.com",
        "Admin",
    )
    create_response = await client.post(
        "/venues",
        json={"name": "Red Top", "location": "Ledyard, CT"},
        headers={"Authorization": f"Bearer {token}"},
    )
    venue_id = create_response.json()["id"]

    nonadmin_token = make_clerk_token(
        clerk_id="user_venue_patch_nonadmin",
        email="venuepatchnonadmin@example.com",
        name="Non Admin",
    )
    await client.get("/me", headers={"Authorization": f"Bearer {nonadmin_token}"})

    response = await client.patch(
        f"/venues/{venue_id}",
        json={"name": "New Name"},
        headers={"Authorization": f"Bearer {nonadmin_token}"},
    )

    assert response.status_code == 403


async def test_patch_nonexistent_venue_returns_404(client, make_clerk_token, db_session):
    token, _admin_id = await _make_admin(
        client,
        make_clerk_token,
        db_session,
        "user_venue_patch_missing",
        "venuepatchmissing@example.com",
        "Admin",
    )

    response = await client.patch(
        "/venues/999999",
        json={"name": "New Name"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


async def test_patch_venue_updates_fields_and_sets_updated_by(client, make_clerk_token, db_session):
    token, admin_id = await _make_admin(
        client,
        make_clerk_token,
        db_session,
        "user_venue_patch_admin",
        "venuepatchadmin@example.com",
        "Admin",
    )
    create_response = await client.post(
        "/venues",
        json={"name": "Red Top", "location": "Ledyard, CT"},
        headers={"Authorization": f"Bearer {token}"},
    )
    venue_id = create_response.json()["id"]

    response = await client.patch(
        f"/venues/{venue_id}",
        json={"location": "Gales Ferry, CT"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Red Top"
    assert body["location"] == "Gales Ferry, CT"
    assert body["updated_by"] == admin_id


async def test_patch_venue_can_clear_image_url(client, make_clerk_token, db_session):
    token, _admin_id = await _make_admin(
        client,
        make_clerk_token,
        db_session,
        "user_venue_patch_clear",
        "venuepatchclear@example.com",
        "Admin",
    )
    create_response = await client.post(
        "/venues",
        json={
            "name": "Cooper River",
            "location": "Camden, NJ",
            "image_url": "https://example.com/cooper.png",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    venue_id = create_response.json()["id"]

    response = await client.patch(
        f"/venues/{venue_id}",
        json={"image_url": None},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["image_url"] is None


async def test_delete_venue_without_token_returns_401(client):
    response = await client.delete("/venues/1")

    assert response.status_code == 401


async def test_delete_venue_as_non_admin_returns_403(client, make_clerk_token, db_session):
    token, _admin_id = await _make_admin(
        client,
        make_clerk_token,
        db_session,
        "user_venue_delete_owner",
        "venuedeleteowner@example.com",
        "Admin",
    )
    create_response = await client.post(
        "/venues",
        json={"name": "Red Top", "location": "Ledyard, CT"},
        headers={"Authorization": f"Bearer {token}"},
    )
    venue_id = create_response.json()["id"]

    nonadmin_token = make_clerk_token(
        clerk_id="user_venue_delete_nonadmin",
        email="venuedeletenonadmin@example.com",
        name="Non Admin",
    )
    await client.get("/me", headers={"Authorization": f"Bearer {nonadmin_token}"})

    response = await client.delete(
        f"/venues/{venue_id}", headers={"Authorization": f"Bearer {nonadmin_token}"}
    )

    assert response.status_code == 403


async def test_delete_nonexistent_venue_returns_404(client, make_clerk_token, db_session):
    token, _admin_id = await _make_admin(
        client,
        make_clerk_token,
        db_session,
        "user_venue_delete_missing",
        "venuedeletemissing@example.com",
        "Admin",
    )

    response = await client.delete("/venues/999999", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404


async def test_delete_venue_soft_deletes(client, make_clerk_token, db_session):
    token, _admin_id = await _make_admin(
        client,
        make_clerk_token,
        db_session,
        "user_venue_delete_admin",
        "venuedeleteadmin@example.com",
        "Admin",
    )
    create_response = await client.post(
        "/venues",
        json={"name": "Red Top", "location": "Ledyard, CT"},
        headers={"Authorization": f"Bearer {token}"},
    )
    venue_id = create_response.json()["id"]

    response = await client.delete(
        f"/venues/{venue_id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 204

    get_response = await client.get(
        f"/venues/{venue_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert get_response.status_code == 404

    from sqlmodel import select

    row = (
        await db_session.execute(
            select(Venue).where(Venue.id == venue_id).execution_options(include_deleted=True)
        )
    ).scalar_one()
    assert row.deleted_at is not None
