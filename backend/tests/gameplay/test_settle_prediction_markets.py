from datetime import date

import pytest

from app.gameplay.models import Event, Prediction, PredictionMarket, Race, RaceEntry, Team

WINNER_FLAT = {"enabled": True, "mode": "flat", "flat_points": 10.0}
MARGIN_FLAT_GLOBAL = {"enabled": True, "mode": "flat", "flat_base": 5.0, "m_source": "global"}


async def _seed_market(db_session, creator_id, scoring_config):
    """A race with two finished RaceEntry rows (team_b wins by 4.0s over team_a) plus a
    PredictionMarket for that race with the given scoring_config. Mirrors
    tests/gameplay/scoring/test_scoring_settle.py's ENTRIES fixture (team 20 wins at
    396.0 vs team 10 at 400.0, margin 4.0s) so the endpoint can be checked against the
    same already-tested point values."""
    team_a = Team(name="Crimson", school="Harvard", mascot="Crimson", created_by=creator_id)
    team_b = Team(name="Bulldogs", school="Yale", mascot="Bulldogs", created_by=creator_id)
    event = Event(
        name="Regatta",
        description="Test regatta",
        format="head",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 2),
        created_by=creator_id,
    )
    db_session.add_all([team_a, team_b, event])
    await db_session.commit()

    race = Race(
        name="Varsity 8+ Heat 1",
        event_id=event.id,
        boat_class="8+",
        level="varsity",
        created_by=creator_id,
    )
    db_session.add(race)
    await db_session.commit()

    db_session.add_all(
        [
            RaceEntry(
                race_id=race.id,
                team_id=team_a.id,
                level="varsity",
                time=400.0,
                status="finished",
                created_by=creator_id,
            ),
            RaceEntry(
                race_id=race.id,
                team_id=team_b.id,
                level="varsity",
                time=396.0,
                status="finished",
                created_by=creator_id,
            ),
        ]
    )
    market = PredictionMarket(race_id=race.id, scoring_config=scoring_config, created_by=creator_id)
    db_session.add(market)
    await db_session.commit()

    return market.id, team_a.id, team_b.id


async def test_settle_market_awards_points_and_stamps_settled_at(
    client, make_admin, make_user, db_session
):
    admin_token, admin_id = await make_admin(
        "user_settle_admin", "settleadmin@example.com", "Admin"
    )
    _correct_token, correct_user_id = await make_user(
        "user_settle_correct", "settlecorrect@example.com", "Correct Picker"
    )
    _wrong_token, wrong_user_id = await make_user(
        "user_settle_wrong", "settlewrong@example.com", "Wrong Picker"
    )

    market_id, team_a_id, team_b_id = await _seed_market(
        db_session, admin_id, {"winner": WINNER_FLAT, "margin": MARGIN_FLAT_GLOBAL}
    )

    db_session.add_all(
        [
            Prediction(
                market_id=market_id,
                user_id=correct_user_id,
                picked_team_id=team_b_id,
                margin_threshold_seconds=3.0,
            ),
            Prediction(
                market_id=market_id,
                user_id=wrong_user_id,
                picked_team_id=team_a_id,
                margin_threshold_seconds=1.0,
            ),
        ]
    )
    await db_session.commit()

    response = await client.post(
        f"/prediction-markets/{market_id}/settle",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    points_by_user = {row["user_id"]: row["points_awarded"] for row in response.json()}
    assert points_by_user[correct_user_id] == pytest.approx(10.0 + 5.0 * 2 ** (3.0 / 3.0))
    assert points_by_user[wrong_user_id] == 0.0

    market = await db_session.get(PredictionMarket, market_id)
    assert market.settled_at is not None


async def test_settling_twice_returns_409(client, make_admin, db_session):
    admin_token, admin_id = await make_admin(
        "user_settle_twice", "settletwice@example.com", "Admin"
    )
    market_id, _team_a_id, _team_b_id = await _seed_market(
        db_session, admin_id, {"winner": WINNER_FLAT}
    )

    first = await client.post(
        f"/prediction-markets/{market_id}/settle",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert first.status_code == 200

    second = await client.post(
        f"/prediction-markets/{market_id}/settle",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert second.status_code == 409


async def test_settle_as_non_admin_returns_403(client, make_admin, make_user, db_session):
    _admin_token, admin_id = await make_admin("user_settle_na1", "settlena1@example.com", "Admin")
    nonadmin_token, _nonadmin_id = await make_user(
        "user_settle_na2", "settlena2@example.com", "Non Admin"
    )
    market_id, _team_a_id, _team_b_id = await _seed_market(
        db_session, admin_id, {"winner": WINNER_FLAT}
    )

    response = await client.post(
        f"/prediction-markets/{market_id}/settle",
        headers={"Authorization": f"Bearer {nonadmin_token}"},
    )
    assert response.status_code == 403


async def test_settle_without_token_returns_401(client, make_admin, db_session):
    _admin_token, admin_id = await make_admin(
        "user_settle_noauth", "settlenoauth@example.com", "Admin"
    )
    market_id, _team_a_id, _team_b_id = await _seed_market(
        db_session, admin_id, {"winner": WINNER_FLAT}
    )

    response = await client.post(f"/prediction-markets/{market_id}/settle")
    assert response.status_code == 401


async def test_settle_unknown_market_returns_404(client, make_admin):
    admin_token, _admin_id = await make_admin("user_settle_404", "settle404@example.com", "Admin")

    response = await client.post(
        "/prediction-markets/999999/settle",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404


async def test_settle_market_with_no_predictions_returns_empty_list(client, make_admin, db_session):
    admin_token, admin_id = await make_admin(
        "user_settle_empty", "settleempty@example.com", "Admin"
    )
    market_id, _team_a_id, _team_b_id = await _seed_market(
        db_session, admin_id, {"winner": WINNER_FLAT}
    )

    response = await client.post(
        f"/prediction-markets/{market_id}/settle",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert response.json() == []
    market = await db_session.get(PredictionMarket, market_id)
    assert market.settled_at is not None
