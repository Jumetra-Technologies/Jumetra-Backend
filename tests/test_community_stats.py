"""GET /community/stats: platform-wide figures that never point at one person."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api.db.models import User
from api.main import create_app
from api.services import community_stats
from database.models import LabSessionRecord, UserProfile, UserProject, UserProjectExperiment

NOW = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HHIP_REQUIRE_AUTH", "false")
    monkeypatch.setenv("HHIP_DISABLE_DISCOVERY", "1")
    community_stats.clear_cache()
    application = create_app(data_dir=tmp_path)
    with TestClient(application):  # startup creates the database
        yield application
    community_stats.clear_cache()


def _org_id(session) -> str:
    return session.scalar(User.__table__.select().with_only_columns(User.organization_id).limit(1))


def add_builder(session, n: int, *, logged_in: datetime | None = NOW) -> str:
    user = User(email=f"builder{n}@example.test", display_name=f"Builder {n}", organization_id=_org_id(session), last_login_at=logged_in)
    session.add(user)
    session.flush()
    return user.id


def lab_doc(session_id: str, parts: list[tuple[str, str]], *, created: str, run_ms: int = 0, runs: int = 0, fixes: int = 0, wires: int = 0) -> dict:
    return {
        "id": session_id,
        "name": session_id,
        "createdAt": created,
        "updatedAt": created,
        "nodes": [{"id": f"n{i}", "partId": p, "label": p, "x": 0, "y": 0, "mode": m} for i, (p, m) in enumerate(parts)],
        "wires": [{"id": f"w{i}"} for i in range(wires)],
        "log": [{"id": f"r{i}", "at": created, "kind": "run", "text": "Run"} for i in range(runs)]
        + [{"id": f"f{i}", "at": created, "kind": "fix", "text": "Fixed"} for i in range(fixes)],
        "runMs": run_ms,
    }


def seed(app, builders: int = 12):
    """`builders` people. Everyone makes a mobile robot with an Uno and an HC-SR04; builder 0 alone also uses a rare part."""
    with app.state.db_factory() as session:
        ids = [add_builder(session, n) for n in range(builders)]
        add_builder(session, 99, logged_in=None)  # an account that never signed in isn't a builder
        for n, owner in enumerate(ids):
            session.add(UserProject(owner_id=owner, name=f"Rover {n}", category="robotics", hardware=["Arduino Uno", "HC-SR04"], created_at=NOW - timedelta(days=3)))
            parts = [("arduino-uno", "virtual"), ("hc-sr04", "hybrid")]
            if n == 0:
                parts.append(("rare-sensor", "physical"))
            session.add(
                LabSessionRecord(
                    id=f"s{n}", owner_id=owner, name=f"s{n}",
                    document=lab_doc(f"s{n}", parts, created="2026-11-02T10:00:00Z", run_ms=600_000, runs=2, fixes=1, wires=3),
                )
            )
            session.add(UserProfile(user_id=owner, learning_progress=["intro", "blink"] if n % 2 == 0 else ["intro"]))
        session.flush()
        project = session.scalar(UserProject.__table__.select().with_only_columns(UserProject.id).limit(1))
        session.add(UserProjectExperiment(project_id=project, title="Range test"))
        session.commit()
        return ids


def test_totals(app):
    seed(app, builders=12)
    with app.state.db_factory() as session:
        stats = community_stats.compute(session, now=NOW)
    totals = stats["totals"]
    assert totals["builders"] == 12
    assert totals["active_builders_30d"] == 12
    assert totals["projects"] == 12
    assert totals["lab_sessions"] == 12
    assert totals["experiments"] == 1
    assert totals["parts_placed"] == 25  # 12 x 2, plus builder 0's rare part
    assert totals["wires"] == 36
    assert totals["runs"] == 24
    assert totals["faults_fixed"] == 12
    assert totals["simulated_hours"] == 2.0  # 12 x 10 minutes
    assert totals["modules_completed"] == 18  # six people with 2, six with 1


def test_breakdowns_list_only_what_enough_people_share(app):
    seed(app, builders=12)
    with app.state.db_factory() as session:
        stats = community_stats.compute(session, now=NOW)
    parts = {row["key"]: row for row in stats["parts"]["rows"]}
    assert set(parts) == {"arduino-uno", "hc-sr04"}
    assert parts["hc-sr04"] == {"key": "hc-sr04", "count": 12, "people": 12}
    # The rare part only one person used is counted, but never named.
    assert stats["parts"]["other"] == {"count": 1, "people": 1}
    assert "rare-sensor" not in str(stats)
    assert [r["key"] for r in stats["categories"]["rows"]] == ["robotics"]
    assert {r["key"] for r in stats["modes"]["rows"]} == {"virtual", "hybrid"}
    assert stats["modes"]["other"] == {"count": 1, "people": 1}  # the one physical part
    assert {r["key"] for r in stats["project_hardware"]["rows"]} == {"Arduino Uno", "HC-SR04"}


def test_a_small_community_shows_totals_but_no_named_rows(app):
    seed(app, builders=9)  # one short of the threshold
    with app.state.db_factory() as session:
        stats = community_stats.compute(session, now=NOW)
    assert stats["totals"]["projects"] == 9
    assert stats["parts"]["rows"] == []
    assert stats["parts"]["other"]["people"] == 9
    assert stats["categories"]["rows"] == []
    # Counts by month still show; how many people were active doesn't.
    november = stats["monthly"][-1]
    assert november["projects"] == 9 and november["builders"] is None


def test_monthly_covers_twelve_months_ending_this_month(app):
    seed(app, builders=12)
    with app.state.db_factory() as session:
        # A project from before the window counts toward the running total, not a month.
        owner = session.scalar(User.__table__.select().with_only_columns(User.id).where(User.last_login_at.is_not(None)).limit(1))
        session.add(UserProject(owner_id=owner, name="Old", category="robotics", created_at=datetime(2024, 3, 1, tzinfo=timezone.utc)))
        session.commit()
        stats = community_stats.compute(session, now=NOW)
    months = [m["month"] for m in stats["monthly"]]
    assert months[0] == "2025-12" and months[-1] == "2026-11" and len(months) == 12
    assert stats["monthly"][-1] == {"month": "2026-11", "projects": 12, "lab_sessions": 12, "projects_to_date": 13, "lab_sessions_to_date": 12, "builders": 12}
    october = stats["monthly"][-2]
    assert october == {"month": "2026-10", "projects": 0, "lab_sessions": 0, "projects_to_date": 1, "lab_sessions_to_date": 0, "builders": None}


def test_nothing_personal_in_the_answer(app):
    ids = seed(app, builders=12)
    with app.state.db_factory() as session:
        text = str(community_stats.compute(session, now=NOW))
    for owner in ids:
        assert owner not in text
    assert "@example.test" not in text and "Builder" not in text and "Rover" not in text


def test_route_is_public_cached_and_typed(app):
    seed(app, builders=12)
    with TestClient(app) as client:
        first = client.get("/community/stats")
        assert first.status_code == 200
        assert first.headers["cache-control"] == "public, max-age=300"
        body = first.json()
        assert body["totals"]["projects"] == 12
        assert body["privacy"] == {"min_group": 10, "cache_seconds": 600}
        # A new project doesn't show until the cache expires.
        with app.state.db_factory() as session:
            owner = session.scalar(User.__table__.select().with_only_columns(User.id).where(User.last_login_at.is_not(None)).limit(1))
            session.add(UserProject(owner_id=owner, name="Arm", category="robotics"))
            session.commit()
        assert client.get("/community/stats").json()["totals"]["projects"] == 12
        community_stats.clear_cache()
        assert client.get("/community/stats").json()["totals"]["projects"] == 13


def test_empty_platform(app):
    with TestClient(app) as client:
        body = client.get("/community/stats").json()
    assert body["totals"]["projects"] == 0
    assert body["parts"] == {"rows": [], "other": None}
    assert len(body["monthly"]) == 12


def test_malformed_lab_documents_are_skipped_not_fatal(app):
    with app.state.db_factory() as session:
        owner = add_builder(session, 1)
        session.add(LabSessionRecord(id="bad", owner_id=owner, name="bad", document={"nodes": "nope", "log": [1, None], "runMs": "x"}))
        session.commit()
        stats = community_stats.compute(session, now=NOW)
    assert stats["totals"]["lab_sessions"] == 1
    assert stats["totals"]["parts_placed"] == 0
