from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.gameplay.models import Event, Prediction, PredictionMarket, Race, Team
from app.gameplay.repository import list_prediction_markets, list_predictions
from app.models import User


async def _make_creator(db_session, clerk_id, email):
    creator = User(clerk_id=clerk_id, email=email)
    db_session.add(creator)
    await db_session.commit()
    return creator


async def _make_race(db_session, creator):
    event = Event(
        name="Head of the Charles",
        description="Fall regatta on the Charles River",
        format="regatta",
        start_date=date(2026, 10, 17),
        end_date=date(2026, 10, 18),
        created_by=creator.id,
    )
    db_session.add(event)
    await db_session.commit()

    race = Race(
        name="Varsity 8+ Heat 1",
        event_id=event.id,
        boat_class="8+",
        level="varsity",
        created_by=creator.id,
    )
    db_session.add(race)
    await db_session.commit()
    return race


async def _make_team(db_session, creator, name="Crimson"):
    team = Team(name=name, school="Harvard", mascot="Crimson", created_by=creator.id)
    db_session.add(team)
    await db_session.commit()
    return team


async def _make_market(db_session, creator, race, scoring_config=None):
    market = PredictionMarket(
        race_id=race.id,
        scoring_config=scoring_config if scoring_config is not None else {"winner": {"points": 10}},
        created_by=creator.id,
    )
    db_session.add(market)
    await db_session.commit()
    return market


async def test_prediction_market_has_soft_delete_fields_and_defaults(db_session):
    creator = await _make_creator(db_session, "user_pm_owner", "pmowner@example.com")
    race = await _make_race(db_session, creator)

    market = PredictionMarket(
        race_id=race.id,
        scoring_config={"winner": {"points": 10}},
        created_by=creator.id,
    )
    db_session.add(market)
    await db_session.commit()

    assert market.id is not None
    assert market.created_at is not None
    assert market.deleted_at is None
    assert market.created_by == creator.id
    assert market.updated_by is None
    assert market.settled_at is None


async def test_prediction_market_scoring_config_roundtrips_nested_dict(db_session):
    creator = await _make_creator(db_session, "user_pm_json", "pmjson@example.com")
    race = await _make_race(db_session, creator)
    config = {
        "winner": {"enabled": True, "points": 10},
        "margin": {"enabled": True, "thresholds": [1.5, 3.0], "points": 5},
        "tiebreak": None,
    }

    market = await _make_market(db_session, creator, race, scoring_config=config)
    db_session.expunge(market)

    reloaded = await db_session.get(PredictionMarket, market.id)
    assert reloaded.scoring_config == config


async def test_duplicate_active_market_for_same_race_rejected(db_session):
    creator = await _make_creator(db_session, "user_pm_dup", "pmdup@example.com")
    race = await _make_race(db_session, creator)

    await _make_market(db_session, creator, race)

    db_session.add(PredictionMarket(race_id=race.id, scoring_config={}, created_by=creator.id))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_market_recreate_after_soft_delete_allowed_by_partial_index(db_session):
    creator = await _make_creator(db_session, "user_pm_readd", "pmreadd@example.com")
    race = await _make_race(db_session, creator)

    first = await _make_market(db_session, creator, race)
    await db_session.delete(first)
    await db_session.commit()

    second = await _make_market(
        db_session, creator, race
    )  # IntegrityError if index weren't partial

    assert second.id is not None
    assert second.id != first.id


async def test_prediction_has_soft_delete_fields_and_defaults(db_session):
    creator = await _make_creator(db_session, "user_p_owner", "powner@example.com")
    race = await _make_race(db_session, creator)
    market = await _make_market(db_session, creator, race)
    team = await _make_team(db_session, creator)

    prediction = Prediction(market_id=market.id, user_id=creator.id, picked_team_id=team.id)
    db_session.add(prediction)
    await db_session.commit()

    assert prediction.id is not None
    assert prediction.created_at is not None
    assert prediction.deleted_at is None
    assert prediction.user_id == creator.id
    assert prediction.picked_team_id == team.id
    assert prediction.margin_threshold_seconds is None
    assert prediction.points_awarded is None


async def test_prediction_margin_threshold_persists_when_supplied(db_session):
    creator = await _make_creator(db_session, "user_p_margin", "pmargin@example.com")
    race = await _make_race(db_session, creator)
    market = await _make_market(db_session, creator, race)
    team = await _make_team(db_session, creator)

    prediction = Prediction(
        market_id=market.id,
        user_id=creator.id,
        picked_team_id=team.id,
        margin_threshold_seconds=2.5,
    )
    db_session.add(prediction)
    await db_session.commit()

    assert prediction.margin_threshold_seconds == 2.5


async def test_duplicate_active_prediction_for_same_market_and_user_rejected(db_session):
    creator = await _make_creator(db_session, "user_p_dup", "pdup@example.com")
    race = await _make_race(db_session, creator)
    market = await _make_market(db_session, creator, race)
    team = await _make_team(db_session, creator)

    db_session.add(Prediction(market_id=market.id, user_id=creator.id, picked_team_id=team.id))
    await db_session.commit()

    db_session.add(Prediction(market_id=market.id, user_id=creator.id, picked_team_id=team.id))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_prediction_recreate_after_soft_delete_allowed_by_partial_index(db_session):
    creator = await _make_creator(db_session, "user_p_readd", "preadd@example.com")
    race = await _make_race(db_session, creator)
    market = await _make_market(db_session, creator, race)
    team = await _make_team(db_session, creator)

    first = Prediction(market_id=market.id, user_id=creator.id, picked_team_id=team.id)
    db_session.add(first)
    await db_session.commit()

    await db_session.delete(first)
    await db_session.commit()

    second = Prediction(market_id=market.id, user_id=creator.id, picked_team_id=team.id)
    db_session.add(second)
    await db_session.commit()  # would raise IntegrityError if the index weren't partial

    assert second.id is not None
    assert second.id != first.id


async def test_list_prediction_markets_returns_active_markets(db_session):
    creator = await _make_creator(db_session, "user_repo_m", "repom@example.com")
    race = await _make_race(db_session, creator)
    market = await _make_market(db_session, creator, race)

    markets = await list_prediction_markets(db_session)

    assert [m.id for m in markets] == [market.id]


async def test_list_prediction_markets_excludes_soft_deleted(db_session):
    creator = await _make_creator(db_session, "user_repo_md", "repomd@example.com")
    race = await _make_race(db_session, creator)
    market = await _make_market(db_session, creator, race)

    await db_session.delete(market)
    await db_session.commit()

    assert await list_prediction_markets(db_session) == []


async def test_list_predictions_returns_all_predictions_across_markets(db_session):
    creator = await _make_creator(db_session, "user_repo_p", "repop@example.com")
    other = await _make_creator(db_session, "user_repo_p2", "repop2@example.com")
    race = await _make_race(db_session, creator)
    market = await _make_market(db_session, creator, race)
    team = await _make_team(db_session, creator)

    db_session.add(Prediction(market_id=market.id, user_id=creator.id, picked_team_id=team.id))
    db_session.add(Prediction(market_id=market.id, user_id=other.id, picked_team_id=team.id))
    await db_session.commit()

    predictions = await list_predictions(db_session)

    assert len(predictions) == 2


async def test_list_predictions_filters_by_market_id(db_session):
    creator = await _make_creator(db_session, "user_repo_pf", "repopf@example.com")
    race_a = await _make_race(db_session, creator)
    race_b = await _make_race(db_session, creator)
    market_a = await _make_market(db_session, creator, race_a)
    market_b = await _make_market(db_session, creator, race_b)
    team = await _make_team(db_session, creator)

    in_a = Prediction(market_id=market_a.id, user_id=creator.id, picked_team_id=team.id)
    db_session.add(in_a)
    db_session.add(Prediction(market_id=market_b.id, user_id=creator.id, picked_team_id=team.id))
    await db_session.commit()

    predictions = await list_predictions(db_session, market_id=market_a.id)

    assert [p.id for p in predictions] == [in_a.id]


async def test_list_predictions_excludes_soft_deleted(db_session):
    creator = await _make_creator(db_session, "user_repo_pd", "repopd@example.com")
    race = await _make_race(db_session, creator)
    market = await _make_market(db_session, creator, race)
    team = await _make_team(db_session, creator)

    prediction = Prediction(market_id=market.id, user_id=creator.id, picked_team_id=team.id)
    db_session.add(prediction)
    await db_session.commit()

    await db_session.delete(prediction)
    await db_session.commit()

    assert await list_predictions(db_session) == []
