"""What the Kiungo community has built, counted across every account.

`GET /community/stats` serves this to anyone, signed in or not, so it holds
only platform-wide totals and breakdowns: never a name, an email, an id or a
single person's record. Two rules keep it that way:

- A breakdown row (a part, a project category, a board mode) is only listed
  when at least MIN_GROUP different people account for it. Rarer rows are
  folded into one "other" row, so a part only one student has tried never
  points at that student. MIN_GROUP is 10, the small-cell rule US health
  statistics use (CMS suppresses counts of 1 to 10).
- Activity by month counts what was created that month, platform-wide: a
  count of projects says nothing about who made them, so it is always shown,
  and a young platform's chart isn't blank. The number of people active in a
  month is null when it is under MIN_GROUP.

Computing it reads every lab session document, so the result is cached for
CACHE_SECONDS per process.
"""

from __future__ import annotations

import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from api.db.models import User
from database.models import LabSessionRecord, UserProfile, UserProject, UserProjectExperiment

MIN_GROUP = 10
CACHE_SECONDS = 600
TOP_PARTS = 12
MONTHS = 12

_lock = threading.Lock()
_cache: dict[int, tuple[float, dict[str, Any]]] = {}


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _month(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    value = _aware(value)
    return f"{value.year:04d}-{value.month:02d}" if value else None


def _last_months(now: datetime, count: int) -> list[str]:
    months: list[str] = []
    year, month = now.year, now.month
    for _ in range(count):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(months))


def _grouped(people_by_key: dict[str, set[str]], uses_by_key: Counter, limit: int | None = None) -> dict[str, Any]:
    """Rows with at least MIN_GROUP people, biggest first; the rest summed into `other`."""
    shown = [k for k, people in people_by_key.items() if len(people) >= MIN_GROUP]
    shown.sort(key=lambda k: (-uses_by_key[k], k))
    if limit is not None:
        shown = shown[:limit]
    listed = set(shown)
    other_people: set[str] = set()
    other_uses = 0
    for key, people in people_by_key.items():
        if key not in listed:
            other_people |= people
            other_uses += uses_by_key[key]
    return {
        "rows": [{"key": k, "count": uses_by_key[k], "people": len(people_by_key[k])} for k in shown],
        "other": {"count": other_uses, "people": len(other_people)} if other_uses else None,
    }


def compute(session: Session, now: datetime | None = None) -> dict[str, Any]:
    now = _aware(now) or datetime.now(timezone.utc)
    months = _last_months(now, MONTHS)
    first_month = months[0]

    builders = session.scalar(select(func.count()).select_from(User).where(User.last_login_at.is_not(None))) or 0
    active_30 = (
        session.scalar(
            select(func.count()).select_from(User).where(User.last_login_at.is_not(None), User.last_login_at >= now - timedelta(days=30))
        )
        or 0
    )

    # Projects: counts, categories, and who made each, by month.
    projects = 0
    category_people: dict[str, set[str]] = defaultdict(set)
    category_uses: Counter = Counter()
    month_projects: Counter = Counter()
    month_people: dict[str, set[str]] = defaultdict(set)
    hardware_people: dict[str, set[str]] = defaultdict(set)
    for owner, category, created, hardware in session.execute(
        select(UserProject.owner_id, UserProject.category, UserProject.created_at, UserProject.hardware)
    ):
        projects += 1
        key = (category or "other").strip().lower() or "other"
        category_people[key].add(owner)
        category_uses[key] += 1
        m = _month(created)
        if m and m >= first_month:
            month_projects[m] += 1
            month_people[m].add(owner)
        for item in hardware or []:
            if isinstance(item, str) and item.strip():
                hardware_people[item.strip()].add(owner)

    experiments = session.scalar(select(func.count()).select_from(UserProjectExperiment)) or 0

    # Lab sessions: parts, wires, runs, simulated time, board modes.
    lab_sessions = 0
    parts_placed = 0
    wires = 0
    runs = 0
    faults_fixed = 0
    run_ms = 0
    part_people: dict[str, set[str]] = defaultdict(set)
    part_sessions: Counter = Counter()
    mode_people: dict[str, set[str]] = defaultdict(set)
    mode_uses: Counter = Counter()
    month_sessions: Counter = Counter()
    for owner, created, document in session.execute(
        select(LabSessionRecord.owner_id, LabSessionRecord.created_at, LabSessionRecord.document).execution_options(yield_per=200)
    ):
        lab_sessions += 1
        doc = document if isinstance(document, dict) else {}
        nodes = doc.get("nodes") if isinstance(doc.get("nodes"), list) else []
        parts_placed += len(nodes)
        wires += len(doc.get("wires") or []) if isinstance(doc.get("wires"), list) else 0
        value = doc.get("runMs")
        if isinstance(value, (int, float)) and value > 0:
            run_ms += int(value)
        for entry in doc.get("log") or []:
            if isinstance(entry, dict):
                if entry.get("kind") == "run":
                    runs += 1
                elif entry.get("kind") == "fix":
                    faults_fixed += 1
        seen: set[str] = set()
        for node in nodes:
            if not isinstance(node, dict):
                continue
            part = node.get("partId")
            if isinstance(part, str) and part and part not in seen:
                seen.add(part)
                part_people[part].add(owner)
                part_sessions[part] += 1
            mode = node.get("mode")
            if mode in ("virtual", "physical", "hybrid"):
                mode_people[mode].add(owner)
                mode_uses[mode] += 1
        m = _month(doc.get("createdAt")) or _month(created)
        if m and m >= first_month:
            month_sessions[m] += 1
            month_people[m].add(owner)

    modules_completed = 0
    for (progress,) in session.execute(select(UserProfile.learning_progress)):
        if isinstance(progress, list):
            modules_completed += len(progress)

    # Everything created before the window, so the growth line starts at the right height.
    monthly = []
    running_projects = projects - sum(month_projects[m] for m in months)
    running_sessions = lab_sessions - sum(month_sessions[m] for m in months)
    for m in months:
        running_projects += month_projects[m]
        running_sessions += month_sessions[m]
        people = len(month_people[m])
        monthly.append(
            {
                "month": m,
                "projects": month_projects[m],
                "lab_sessions": month_sessions[m],
                "projects_to_date": running_projects,
                "lab_sessions_to_date": running_sessions,
                # Too few people that month to say how many without pointing at someone.
                "builders": people if people >= MIN_GROUP else None,
            }
        )

    return {
        "generated_at": now.isoformat(),
        "totals": {
            "builders": builders,
            "active_builders_30d": active_30,
            "projects": projects,
            "lab_sessions": lab_sessions,
            "experiments": experiments,
            "parts_placed": parts_placed,
            "wires": wires,
            "runs": runs,
            "faults_fixed": faults_fixed,
            "simulated_hours": round(run_ms / 3_600_000, 1),
            "modules_completed": modules_completed,
        },
        "parts": _grouped(part_people, part_sessions, TOP_PARTS),
        "project_hardware": _grouped(hardware_people, Counter({k: len(v) for k, v in hardware_people.items()}), TOP_PARTS),
        "categories": _grouped(category_people, category_uses),
        "modes": _grouped(mode_people, mode_uses),
        "monthly": monthly,
        "privacy": {"min_group": MIN_GROUP, "cache_seconds": CACHE_SECONDS},
    }


def cached(factory: sessionmaker[Session], now: float | None = None) -> dict[str, Any]:
    """The stats, recomputed at most once every CACHE_SECONDS per database."""
    key = id(factory)
    clock = time.monotonic() if now is None else now
    with _lock:
        hit = _cache.get(key)
        if hit and clock - hit[0] < CACHE_SECONDS:
            return hit[1]
    with factory() as session:
        result = compute(session)
    with _lock:
        _cache[key] = (clock, result)
    return result


def clear_cache() -> None:
    with _lock:
        _cache.clear()
