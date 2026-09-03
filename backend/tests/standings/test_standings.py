from datetime import date

from app.gameplay.models import Event, Prediction, PredictionMarket, Race, Team
from app.gameplay.repository import sum_settled_points_by_user
from app.leagues.models import League, LeagueUser
from app.leagues.repository import list_active_members
from app.models import User


async def _seed_league(db_session, owner_id, member_ids):
    """A league owned by owner_id, with one LeagueUser row per id in member_ids.

    member_ids must include owner_id if the owner is meant to appear in standings --
    this helper does not add the owner implicitly, so tests stay explicit about who is
    a member."""
    league = League(name="Standings League", created_by=owner_id, owner_id=owner_id)
    db_session.add(league)
    await db_session.commit()

    db_session.add_all([LeagueUser(league_id=league.id, user_id=user_id) for user_id in member_ids])
    await db_session.commit()
    return league.id


async def _seed_markets(db_session, creator_id, count):
    """`count` PredictionMarkets, each on its own Race, plus one Team to pick.

    One market per race is required: ix_predictionmarket_race_id_active makes race_id
    unique among live rows. Returns (team_id, [market_id, ...])."""
    team = Team(name="Crew", school="State", mascot="Otters", created_by=creator_id)
    event = Event(
        name="Regatta",
        description="Test regatta",
        format="head",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 2),
        created_by=creator_id,
    )
    db_session.add_all([team, event])
    await db_session.commit()

    races = [
        Race(
            name=f"Race {index}",
            event_id=event.id,
            boat_class="8+",
            level="varsity",
            created_by=creator_id,
        )
        for index in range(count)
    ]
    db_session.add_all(races)
    await db_session.commit()

    markets = [
        PredictionMarket(race_id=race.id, scoring_config={}, created_by=creator_id)
        for race in races
    ]
    db_session.add_all(markets)
    await db_session.commit()

    return team.id, [market.id for market in markets]


async def test_list_active_members_returns_members_with_users(db_session):
    owner = User(clerk_id="user_lam_1", email="lam1@example.com", username="owner")
    member = User(clerk_id="user_lam_2", email="lam2@example.com", username="member")
    db_session.add_all([owner, member])
    await db_session.commit()

    league_id = await _seed_league(db_session, owner.id, [owner.id, member.id])

    rows = await list_active_members(db_session, league_id)

    assert {user.id for _membership, user in rows} == {owner.id, member.id}
    assert {user.username for _membership, user in rows} == {"owner", "member"}
    assert all(membership.league_id == league_id for membership, _user in rows)


async def test_list_active_members_excludes_departed_member(db_session):
    owner = User(clerk_id="user_lam_3", email="lam3@example.com", username="owner2")
    leaver = User(clerk_id="user_lam_4", email="lam4@example.com", username="leaver")
    db_session.add_all([owner, leaver])
    await db_session.commit()

    league_id = await _seed_league(db_session, owner.id, [owner.id, leaver.id])

    membership = next(
        m for m, u in await list_active_members(db_session, league_id) if u.id == leaver.id
    )
    await db_session.delete(membership)  # rewritten to a soft delete by app/soft_delete.py
    await db_session.commit()

    rows = await list_active_members(db_session, league_id)

    assert {user.id for _membership, user in rows} == {owner.id}


async def test_list_active_members_excludes_other_leagues(db_session):
    owner = User(clerk_id="user_lam_5", email="lam5@example.com", username="owner3")
    outsider = User(clerk_id="user_lam_6", email="lam6@example.com", username="outsider")
    db_session.add_all([owner, outsider])
    await db_session.commit()

    league_id = await _seed_league(db_session, owner.id, [owner.id])
    await _seed_league(db_session, outsider.id, [outsider.id])

    rows = await list_active_members(db_session, league_id)

    assert {user.id for _membership, user in rows} == {owner.id}


async def test_sum_settled_points_by_user_totals_across_markets(db_session):
    scorer = User(clerk_id="user_ssp_1", email="ssp1@example.com", username="scorer")
    db_session.add(scorer)
    await db_session.commit()

    team_id, market_ids = await _seed_markets(db_session, scorer.id, 3)
    db_session.add_all(
        [
            Prediction(
                market_id=market_ids[0],
                user_id=scorer.id,
                picked_team_id=team_id,
                points_awarded=3.0,
            ),
            Prediction(
                market_id=market_ids[1],
                user_id=scorer.id,
                picked_team_id=team_id,
                points_awarded=1.5,
            ),
            # Unsettled: points_awarded is still NULL, so it must contribute nothing.
            Prediction(
                market_id=market_ids[2],
                user_id=scorer.id,
                picked_team_id=team_id,
            ),
        ]
    )
    await db_session.commit()

    totals = await sum_settled_points_by_user(db_session, [scorer.id])

    assert totals == {scorer.id: 4.5}


async def test_sum_settled_points_by_user_omits_users_without_settled_predictions(db_session):
    scorer = User(clerk_id="user_ssp_2", email="ssp2@example.com", username="scorer2")
    idler = User(clerk_id="user_ssp_3", email="ssp3@example.com", username="idler")
    db_session.add_all([scorer, idler])
    await db_session.commit()

    team_id, market_ids = await _seed_markets(db_session, scorer.id, 1)
    db_session.add(
        Prediction(
            market_id=market_ids[0],
            user_id=scorer.id,
            picked_team_id=team_id,
            points_awarded=2.0,
        )
    )
    await db_session.commit()

    totals = await sum_settled_points_by_user(db_session, [scorer.id, idler.id])

    assert totals == {scorer.id: 2.0}
    assert idler.id not in totals


async def test_sum_settled_points_by_user_excludes_soft_deleted_predictions(db_session):
    scorer = User(clerk_id="user_ssp_4", email="ssp4@example.com", username="scorer3")
    db_session.add(scorer)
    await db_session.commit()

    team_id, market_ids = await _seed_markets(db_session, scorer.id, 2)
    kept = Prediction(
        market_id=market_ids[0], user_id=scorer.id, picked_team_id=team_id, points_awarded=5.0
    )
    removed = Prediction(
        market_id=market_ids[1], user_id=scorer.id, picked_team_id=team_id, points_awarded=100.0
    )
    db_session.add_all([kept, removed])
    await db_session.commit()

    await db_session.delete(removed)  # soft delete
    await db_session.commit()

    totals = await sum_settled_points_by_user(db_session, [scorer.id])

    assert totals == {scorer.id: 5.0}


async def test_sum_settled_points_by_user_ignores_users_not_asked_for(db_session):
    asked = User(clerk_id="user_ssp_5", email="ssp5@example.com", username="asked")
    other = User(clerk_id="user_ssp_6", email="ssp6@example.com", username="other")
    db_session.add_all([asked, other])
    await db_session.commit()

    team_id, market_ids = await _seed_markets(db_session, asked.id, 1)
    db_session.add_all(
        [
            Prediction(
                market_id=market_ids[0],
                user_id=asked.id,
                picked_team_id=team_id,
                points_awarded=1.0,
            ),
            Prediction(
                market_id=market_ids[0],
                user_id=other.id,
                picked_team_id=team_id,
                points_awarded=99.0,
            ),
        ]
    )
    await db_session.commit()

    totals = await sum_settled_points_by_user(db_session, [asked.id])

    assert totals == {asked.id: 1.0}


async def test_sum_settled_points_by_user_handles_empty_user_list(db_session):
    assert await sum_settled_points_by_user(db_session, []) == {}


async def _set_username(db_session, user_id, username):
    """conftest's make_user assigns a generated `user{id}` username. Tests that assert on
    ordering need to control it, since ties break alphabetically."""
    user = await db_session.get(User, user_id)
    user.username = username
    db_session.add(user)
    await db_session.commit()


async def test_standings_returns_every_member_sorted_by_points(client, make_user, db_session):
    """Acceptance criterion #1: three members, some with settled predictions and some
    without, all returned with correct totals, sorted descending."""
    lead_token, lead_id = await make_user("user_st_1", "st1@example.com", "Lead")
    _mid_token, mid_id = await make_user("user_st_2", "st2@example.com", "Mid")
    _zero_token, zero_id = await make_user("user_st_3", "st3@example.com", "Zero")
    await _set_username(db_session, lead_id, "lead")
    await _set_username(db_session, mid_id, "mid")
    await _set_username(db_session, zero_id, "zero")

    league_id = await _seed_league(db_session, lead_id, [lead_id, mid_id, zero_id])
    team_id, market_ids = await _seed_markets(db_session, lead_id, 2)
    db_session.add_all(
        [
            Prediction(
                market_id=market_ids[0], user_id=lead_id, picked_team_id=team_id, points_awarded=6.0
            ),
            Prediction(
                market_id=market_ids[1], user_id=lead_id, picked_team_id=team_id, points_awarded=4.0
            ),
            Prediction(
                market_id=market_ids[0], user_id=mid_id, picked_team_id=team_id, points_awarded=2.5
            ),
        ]
    )
    await db_session.commit()

    response = await client.get(
        f"/leagues/{league_id}/standings",
        headers={"Authorization": f"Bearer {lead_token}"},
    )

    assert response.status_code == 200
    assert response.json() == [
        {"user_id": lead_id, "username": "lead", "points": 10.0},
        {"user_id": mid_id, "username": "mid", "points": 2.5},
        {"user_id": zero_id, "username": "zero", "points": 0.0},
    ]


async def test_standings_rejects_non_member(client, make_user, db_session):
    """Acceptance criterion #2."""
    _owner_token, owner_id = await make_user("user_st_4", "st4@example.com", "Owner")
    outsider_token, _outsider_id = await make_user("user_st_5", "st5@example.com", "Outsider")

    league_id = await _seed_league(db_session, owner_id, [owner_id])

    response = await client.get(
        f"/leagues/{league_id}/standings",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )

    assert response.status_code == 403


async def test_standings_unknown_league_returns_404(client, make_user):
    token, _user_id = await make_user("user_st_6", "st6@example.com", "Seeker")

    response = await client.get(
        "/leagues/999999/standings", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


async def test_standings_without_token_returns_401(client):
    response = await client.get("/leagues/1/standings")

    assert response.status_code == 401


async def test_standings_includes_member_with_no_predictions_as_zero(client, make_user, db_session):
    """Called out separately from the three-member test because this is the exact case a
    single LEFT JOIN + global soft-delete filter would silently drop."""
    token, owner_id = await make_user("user_st_7", "st7@example.com", "Owner")
    await _set_username(db_session, owner_id, "solo")

    league_id = await _seed_league(db_session, owner_id, [owner_id])

    response = await client.get(
        f"/leagues/{league_id}/standings", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json() == [{"user_id": owner_id, "username": "solo", "points": 0.0}]


async def test_standings_ignores_unsettled_predictions(client, make_user, db_session):
    token, owner_id = await make_user("user_st_8", "st8@example.com", "Owner")
    await _set_username(db_session, owner_id, "pending")

    league_id = await _seed_league(db_session, owner_id, [owner_id])
    team_id, market_ids = await _seed_markets(db_session, owner_id, 1)
    db_session.add(Prediction(market_id=market_ids[0], user_id=owner_id, picked_team_id=team_id))
    await db_session.commit()

    response = await client.get(
        f"/leagues/{league_id}/standings", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.json() == [{"user_id": owner_id, "username": "pending", "points": 0.0}]


async def test_standings_excludes_departed_member(client, make_user, db_session):
    token, owner_id = await make_user("user_st_9", "st9@example.com", "Owner")
    leaver_token, leaver_id = await make_user("user_st_10", "st10@example.com", "Leaver")
    await _set_username(db_session, owner_id, "stayer")
    await _set_username(db_session, leaver_id, "goner")

    league_id = await _seed_league(db_session, owner_id, [owner_id, leaver_id])

    leave_response = await client.post(
        f"/leagues/{league_id}/leave", headers={"Authorization": f"Bearer {leaver_token}"}
    )
    assert leave_response.status_code == 204

    response = await client.get(
        f"/leagues/{league_id}/standings", headers={"Authorization": f"Bearer {token}"}
    )

    assert [row["user_id"] for row in response.json()] == [owner_id]


async def test_standings_breaks_ties_alphabetically_by_username(client, make_user, db_session):
    token, first_id = await make_user("user_st_11", "st11@example.com", "First")
    _second_token, second_id = await make_user("user_st_12", "st12@example.com", "Second")
    # Deliberately reversed: the lower user id gets the later username, so a passing
    # assertion cannot be explained by insertion order.
    await _set_username(db_session, first_id, "zoe")
    await _set_username(db_session, second_id, "adam")

    league_id = await _seed_league(db_session, first_id, [first_id, second_id])
    team_id, market_ids = await _seed_markets(db_session, first_id, 1)
    db_session.add_all(
        [
            Prediction(
                market_id=market_ids[0],
                user_id=first_id,
                picked_team_id=team_id,
                points_awarded=7.0,
            ),
            Prediction(
                market_id=market_ids[0],
                user_id=second_id,
                picked_team_id=team_id,
                points_awarded=7.0,
            ),
        ]
    )
    await db_session.commit()

    response = await client.get(
        f"/leagues/{league_id}/standings", headers={"Authorization": f"Bearer {token}"}
    )

    assert [row["username"] for row in response.json()] == ["adam", "zoe"]


async def test_standings_totals_are_global_not_league_scoped(client, make_user, db_session):
    """Predictions have no league of their own -- a member's total is every settled
    prediction they hold, regardless of which league (if any) the market relates to. This
    pins the premise app.standings' whole existence rests on."""
    token, member_id = await make_user("user_st_13", "st13@example.com", "Member")
    _outsider_token, outsider_id = await make_user("user_st_14", "st14@example.com", "Outsider")
    await _set_username(db_session, member_id, "member")

    league_id = await _seed_league(db_session, member_id, [member_id])
    # A second league the member does not belong to; its existence must not change totals.
    await _seed_league(db_session, outsider_id, [outsider_id])

    team_id, market_ids = await _seed_markets(db_session, member_id, 2)
    db_session.add_all(
        [
            Prediction(
                market_id=market_ids[0],
                user_id=member_id,
                picked_team_id=team_id,
                points_awarded=1.0,
            ),
            Prediction(
                market_id=market_ids[1],
                user_id=member_id,
                picked_team_id=team_id,
                points_awarded=2.0,
            ),
            # The outsider's points must not leak into the member's row.
            Prediction(
                market_id=market_ids[0],
                user_id=outsider_id,
                picked_team_id=team_id,
                points_awarded=50.0,
            ),
        ]
    )
    await db_session.commit()

    response = await client.get(
        f"/leagues/{league_id}/standings", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.json() == [{"user_id": member_id, "username": "member", "points": 3.0}]
