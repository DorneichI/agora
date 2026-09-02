from app.gameplay.models import PredictionMarket

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
        json={
            "name": "Varsity 8+ Heat 1",
            "event_id": event_id,
            "boat_class": "8+",
            "level": "varsity",
        },
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


async def _create_race_entry(client, token, race_id, team_id):
    response = await client.post(
        "/race-entries",
        json={"race_id": race_id, "team_id": team_id, "level": "varsity"},
        headers={"Authorization": f"Bearer {token}"},
    )
    return response.json()["id"]


async def _create_race_with_entries(client, token, entry_count=2):
    event_id = await _create_event(client, token)
    race_id = await _create_race(client, token, event_id)
    for i in range(entry_count):
        team_id = await _create_team(client, token, name=f"Team {i}")
        await _create_race_entry(client, token, race_id, team_id)
    return race_id


WINNER_FLAT_CONFIG = {"winner": {"enabled": True, "mode": "flat", "flat_points": 10}}


async def test_create_prediction_market_without_token_returns_401(client):
    response = await client.post("/prediction-markets", json={"race_id": 1, "scoring_config": {}})

    assert response.status_code == 401


async def test_create_prediction_market_as_non_admin_returns_403(
    client, make_clerk_token, make_admin
):
    token, _admin_id = await make_admin("user_pm_setup", "pmsetup@example.com", "Admin")
    race_id = await _create_race_with_entries(client, token)

    nonadmin_token = make_clerk_token(
        clerk_id="user_pm_nonadmin", email="pmnonadmin@example.com", name="Non Admin"
    )
    await client.get("/me", headers={"Authorization": f"Bearer {nonadmin_token}"})

    response = await client.post(
        "/prediction-markets",
        json={"race_id": race_id, "scoring_config": WINNER_FLAT_CONFIG},
        headers={"Authorization": f"Bearer {nonadmin_token}"},
    )

    assert response.status_code == 403


async def test_create_prediction_market_as_admin_with_eligible_config_returns_201(
    client, make_admin, db_session
):
    token, admin_id = await make_admin("user_pm_admin", "pmadmin@example.com", "Admin")
    race_id = await _create_race_with_entries(client, token)

    response = await client.post(
        "/prediction-markets",
        json={"race_id": race_id, "scoring_config": WINNER_FLAT_CONFIG},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["race_id"] == race_id
    assert body["scoring_config"] == WINNER_FLAT_CONFIG
    assert body["created_by"] == admin_id
    assert body["updated_by"] is None
    assert body["settled_at"] is None
    assert set(body.keys()) == {
        "id",
        "race_id",
        "scoring_config",
        "settled_at",
        "created_by",
        "updated_by",
    }

    market = await db_session.get(PredictionMarket, body["id"])
    assert market.created_by == admin_id
