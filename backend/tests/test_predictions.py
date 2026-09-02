from datetime import UTC, datetime

from sqlmodel import select

from app.gameplay.models import Prediction, PredictionMarket

EVENT_PAYLOAD = {
    "name": "Head of the Charles",
    "description": "Fall regatta on the Charles River",
    "format": "regatta",
    "start_date": "2026-10-17",
    "end_date": "2026-10-18",
}

WINNER_FLAT_CONFIG = {"winner": {"enabled": True, "mode": "flat", "flat_points": 10}}
MARGIN_ENABLED_CONFIG = {
    "margin": {"enabled": True, "mode": "pool", "pool_points": 20},
}
# Unlike WINNER_FLAT_CONFIG (which omits "margin" entirely -- meaning margin is *absent*, so a
# stray margin_threshold_seconds is silently skipped per app/gameplay/scoring/__init__.py's
# validate_prediction_payload), this config explicitly disables margin, so a stray
# margin_threshold_seconds must be rejected. Needed to actually exercise the
# "present but disabled" test below.
WINNER_FLAT_MARGIN_DISABLED_CONFIG = {
    "winner": {"enabled": True, "mode": "flat", "flat_points": 10},
    "margin": {"enabled": False},
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
    team_ids = []
    for i in range(entry_count):
        team_id = await _create_team(client, token, name=f"Team {i}")
        await _create_race_entry(client, token, race_id, team_id)
        team_ids.append(team_id)
    return race_id, team_ids


async def _create_market(client, token, race_id, scoring_config):
    response = await client.post(
        "/prediction-markets",
        json={"race_id": race_id, "scoring_config": scoring_config},
        headers={"Authorization": f"Bearer {token}"},
    )
    return response.json()["id"]


async def test_create_prediction_without_token_returns_401(client):
    response = await client.post("/predictions", json={"market_id": 1, "picked_team_id": 1})

    assert response.status_code == 401


async def test_submit_valid_prediction_succeeds(client, make_admin, make_user):
    admin_token, _admin_id = await make_admin("user_pred_admin", "predadmin@example.com", "Admin")
    race_id, team_ids = await _create_race_with_entries(client, admin_token)
    market_id = await _create_market(client, admin_token, race_id, WINNER_FLAT_CONFIG)

    user_token, user_id = await make_user("user_pred_1", "pred1@example.com", "Predictor")
    response = await client.post(
        "/predictions",
        json={"market_id": market_id, "picked_team_id": team_ids[0]},
        headers={"Authorization": f"Bearer {user_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["market_id"] == market_id
    assert body["user_id"] == user_id
    assert body["picked_team_id"] == team_ids[0]
    assert body["margin_threshold_seconds"] is None
    assert body["points_awarded"] is None
    assert set(body.keys()) == {
        "id",
        "market_id",
        "user_id",
        "picked_team_id",
        "margin_threshold_seconds",
        "points_awarded",
    }


async def test_submit_prediction_with_margin_required_but_missing_returns_422(
    client, make_admin, make_user
):
    admin_token, _admin_id = await make_admin(
        "user_pred_margin_admin", "predmarginadmin@example.com", "Admin"
    )
    race_id, team_ids = await _create_race_with_entries(client, admin_token)
    market_id = await _create_market(client, admin_token, race_id, MARGIN_ENABLED_CONFIG)

    user_token, _user_id = await make_user(
        "user_pred_margin_missing", "predmarginmissing@example.com", "Predictor"
    )
    response = await client.post(
        "/predictions",
        json={"market_id": market_id, "picked_team_id": team_ids[0]},
        headers={"Authorization": f"Bearer {user_token}"},
    )

    assert response.status_code == 422


async def test_submit_prediction_with_margin_present_but_disabled_returns_422(
    client, make_admin, make_user
):
    admin_token, _admin_id = await make_admin(
        "user_pred_margin_admin2", "predmarginadmin2@example.com", "Admin"
    )
    race_id, team_ids = await _create_race_with_entries(client, admin_token)
    market_id = await _create_market(
        client, admin_token, race_id, WINNER_FLAT_MARGIN_DISABLED_CONFIG
    )

    user_token, _user_id = await make_user(
        "user_pred_margin_extra", "predmarginextra@example.com", "Predictor"
    )
    response = await client.post(
        "/predictions",
        json={
            "market_id": market_id,
            "picked_team_id": team_ids[0],
            "margin_threshold_seconds": 5.0,
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )

    assert response.status_code == 422


async def test_resubmitting_updates_existing_prediction_instead_of_duplicating(
    client, make_admin, make_user, db_session
):
    admin_token, _admin_id = await make_admin(
        "user_pred_resub_admin", "predresubadmin@example.com", "Admin"
    )
    race_id, team_ids = await _create_race_with_entries(client, admin_token)
    market_id = await _create_market(client, admin_token, race_id, WINNER_FLAT_CONFIG)

    user_token, user_id = await make_user("user_pred_resub", "predresub@example.com", "Predictor")
    first = await client.post(
        "/predictions",
        json={"market_id": market_id, "picked_team_id": team_ids[0]},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert first.status_code == 200
    first_id = first.json()["id"]

    second = await client.post(
        "/predictions",
        json={"market_id": market_id, "picked_team_id": team_ids[1]},
        headers={"Authorization": f"Bearer {user_token}"},
    )

    assert second.status_code == 200
    assert second.json()["id"] == first_id
    assert second.json()["picked_team_id"] == team_ids[1]

    rows = (
        (
            await db_session.execute(
                select(Prediction).where(
                    Prediction.market_id == market_id, Prediction.user_id == user_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


async def test_submit_prediction_with_invalid_picked_team_id_returns_422(
    client, make_admin, make_user
):
    admin_token, _admin_id = await make_admin(
        "user_pred_badteam_admin", "predbadteamadmin@example.com", "Admin"
    )
    race_id, _team_ids = await _create_race_with_entries(client, admin_token)
    market_id = await _create_market(client, admin_token, race_id, WINNER_FLAT_CONFIG)
    other_team_id = await _create_team(client, admin_token, name="Not In This Race")

    user_token, _user_id = await make_user(
        "user_pred_badteam", "predbadteam@example.com", "Predictor"
    )
    response = await client.post(
        "/predictions",
        json={"market_id": market_id, "picked_team_id": other_team_id},
        headers={"Authorization": f"Bearer {user_token}"},
    )

    assert response.status_code == 422


async def test_submit_prediction_with_nonexistent_market_id_returns_422(client, make_user):
    token, _user_id = await make_user(
        "user_pred_badmarket", "predbadmarket@example.com", "Predictor"
    )

    response = await client.post(
        "/predictions",
        json={"market_id": 999999, "picked_team_id": 1},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


async def test_submit_prediction_to_settled_market_returns_409(
    client, make_admin, make_user, db_session
):
    admin_token, admin_id = await make_admin(
        "user_pred_settled_admin", "predsettledadmin@example.com", "Admin"
    )
    race_id, team_ids = await _create_race_with_entries(client, admin_token)
    market_id = await _create_market(client, admin_token, race_id, WINNER_FLAT_CONFIG)

    market = await db_session.get(PredictionMarket, market_id)
    market.settled_at = datetime.now(UTC)
    market.updated_by = admin_id
    db_session.add(market)
    await db_session.commit()

    user_token, _user_id = await make_user(
        "user_pred_settled", "predsettled@example.com", "Predictor"
    )
    response = await client.post(
        "/predictions",
        json={"market_id": market_id, "picked_team_id": team_ids[0]},
        headers={"Authorization": f"Bearer {user_token}"},
    )

    assert response.status_code == 409


async def test_get_prediction_without_token_returns_401(client):
    response = await client.get("/predictions/1")

    assert response.status_code == 401


async def test_get_own_prediction_succeeds(client, make_admin, make_user):
    admin_token, _admin_id = await make_admin(
        "user_pred_get_admin", "predgetadmin@example.com", "Admin"
    )
    race_id, team_ids = await _create_race_with_entries(client, admin_token)
    market_id = await _create_market(client, admin_token, race_id, WINNER_FLAT_CONFIG)

    user_token, user_id = await make_user("user_pred_get", "predget@example.com", "Predictor")
    create_response = await client.post(
        "/predictions",
        json={"market_id": market_id, "picked_team_id": team_ids[0]},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    prediction_id = create_response.json()["id"]

    response = await client.get(
        f"/predictions/{prediction_id}", headers={"Authorization": f"Bearer {user_token}"}
    )

    assert response.status_code == 200
    assert response.json()["user_id"] == user_id


async def test_get_another_users_prediction_returns_403(client, make_admin, make_user):
    admin_token, _admin_id = await make_admin(
        "user_pred_403_admin", "pred403admin@example.com", "Admin"
    )
    race_id, team_ids = await _create_race_with_entries(client, admin_token)
    market_id = await _create_market(client, admin_token, race_id, WINNER_FLAT_CONFIG)

    owner_token, _owner_id = await make_user("user_pred_owner", "predowner@example.com", "Owner")
    create_response = await client.post(
        "/predictions",
        json={"market_id": market_id, "picked_team_id": team_ids[0]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    prediction_id = create_response.json()["id"]

    other_token, _other_id = await make_user("user_pred_other", "predother@example.com", "Other")
    response = await client.get(
        f"/predictions/{prediction_id}", headers={"Authorization": f"Bearer {other_token}"}
    )

    assert response.status_code == 403


async def test_admin_can_get_another_users_prediction(client, make_admin, make_user):
    admin_token, _admin_id = await make_admin(
        "user_pred_admin_get", "predadminget@example.com", "Admin"
    )
    race_id, team_ids = await _create_race_with_entries(client, admin_token)
    market_id = await _create_market(client, admin_token, race_id, WINNER_FLAT_CONFIG)

    owner_token, owner_id = await make_user("user_pred_owner2", "predowner2@example.com", "Owner")
    create_response = await client.post(
        "/predictions",
        json={"market_id": market_id, "picked_team_id": team_ids[0]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    prediction_id = create_response.json()["id"]

    response = await client.get(
        f"/predictions/{prediction_id}", headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    assert response.json()["user_id"] == owner_id


async def test_get_nonexistent_prediction_returns_404(client, make_user):
    token, _user_id = await make_user("user_pred_404", "pred404@example.com", "Predictor")

    response = await client.get("/predictions/999999", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404


async def test_list_predictions_only_returns_own_predictions(client, make_admin, make_user):
    admin_token, _admin_id = await make_admin(
        "user_pred_list_admin", "predlistadmin@example.com", "Admin"
    )
    race_id, team_ids = await _create_race_with_entries(client, admin_token)
    market_id = await _create_market(client, admin_token, race_id, WINNER_FLAT_CONFIG)

    user_a_token, user_a_id = await make_user("user_pred_list_a", "predlista@example.com", "A")
    await client.post(
        "/predictions",
        json={"market_id": market_id, "picked_team_id": team_ids[0]},
        headers={"Authorization": f"Bearer {user_a_token}"},
    )

    user_b_token, _user_b_id = await make_user("user_pred_list_b", "predlistb@example.com", "B")
    await client.post(
        "/predictions",
        json={"market_id": market_id, "picked_team_id": team_ids[1]},
        headers={"Authorization": f"Bearer {user_b_token}"},
    )

    response = await client.get("/predictions", headers={"Authorization": f"Bearer {user_a_token}"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["user_id"] == user_a_id


async def test_list_predictions_filters_by_market_id(client, make_admin, make_user):
    admin_token, _admin_id = await make_admin(
        "user_pred_filter_admin", "predfilteradmin@example.com", "Admin"
    )
    race_one, team_ids_one = await _create_race_with_entries(client, admin_token)
    market_one = await _create_market(client, admin_token, race_one, WINNER_FLAT_CONFIG)
    race_two, team_ids_two = await _create_race_with_entries(client, admin_token)
    market_two = await _create_market(client, admin_token, race_two, WINNER_FLAT_CONFIG)

    user_token, _user_id = await make_user(
        "user_pred_filter", "predfilter@example.com", "Predictor"
    )
    await client.post(
        "/predictions",
        json={"market_id": market_one, "picked_team_id": team_ids_one[0]},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    await client.post(
        "/predictions",
        json={"market_id": market_two, "picked_team_id": team_ids_two[0]},
        headers={"Authorization": f"Bearer {user_token}"},
    )

    response = await client.get(
        f"/predictions?market_id={market_one}",
        headers={"Authorization": f"Bearer {user_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["market_id"] == market_one
