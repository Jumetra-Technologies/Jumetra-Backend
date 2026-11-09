"""Usage from the website and the desktop app, for the admin portal.

Each open Kiungo window sends a heartbeat while someone is using it: the
website every 30 seconds while the tab is visible and the person has moved,
typed or scrolled in the last five minutes; the desktop app every 60 seconds
while its window is in use. A heartbeat says which page it's on.

From those, three things are kept, and nothing else:

- presence: who is on which page now (online = a heartbeat in the last two minutes),
- seconds per person (or visitor) per day per client,
- views and seconds per page per day per client.

Time is credited for the gap since the previous heartbeat, capped at 75
seconds, so a window left open with nobody there, a sleeping laptop or a lost
connection adds nothing. A visitor who isn't signed in is a keyed hash of a
random id their browser made; ids inside page paths become ``:id``. Rows older
than ``RETAIN_DAYS`` are deleted.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional
from urllib.parse import urlsplit

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.db.models import User
from database.models import (
    ActivityDaily,
    ActivityPageDaily,
    ActivityPresence,
    AdminSignInAttempt,
    AdminSession,
    Consent,
    Device,
    LabSessionRecord,
    OAuthAccount,
    SyncedProject,
    UserProject,
    UserProjectExperiment,
)

Client = Literal["web", "desktop"]
Event = Literal["view", "beat", "leave"]

ONLINE_SECONDS = 120  # seen this recently = online
GAP_SECONDS = 150  # a longer silence starts a new visit
MAX_CREDIT_SECONDS = 75  # the most one heartbeat can add
MIN_BEAT_SECONDS = 10  # beats closer than this are ignored
RETAIN_DAYS = 400
PRUNE_EVERY = 500  # heartbeats between clean-ups, per server process

_UUID = re.compile(r"^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$")
_HEX = re.compile(r"^[0-9a-f]{12,}$")
_DIGITS = re.compile(r"^\d+$")
_SAFE = re.compile(r"^[a-z0-9._~-]+$")

_beats_since_prune = 0


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def keyed_hash(secret: str, value: str, size: int = 32) -> str:
    """A hash only this server can make: the same visitor or address gives the same key, and the key can't be turned back."""
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()[:size]


def normalize_page(raw: str) -> str:
    """A page as the portal groups it: the path only, lower case, ids replaced with :id, at most six parts."""
    text = (raw or "").strip()
    if "://" in text:
        text = urlsplit(text).path
    text = text.split("?", 1)[0].split("#", 1)[0].lower()
    parts: list[str] = []
    for segment in text.split("/"):
        if not segment:
            continue
        if _UUID.match(segment) or _HEX.match(segment) or _DIGITS.match(segment) or len(segment) > 40 or not _SAFE.match(segment):
            segment = ":id"
        parts.append(segment)
        if len(parts) == 6:
            break
    return ("/" + "/".join(parts))[:96]


@dataclass
class Beat:
    client: Client
    page: str
    event: Event
    user_id: Optional[str]
    visitor_key: Optional[str]  # already hashed
    app_version: str = ""


def _subject(beat: Beat) -> Optional[str]:
    if beat.user_id:
        return f"u:{beat.user_id}"
    if beat.visitor_key:
        return f"v:{beat.visitor_key}"
    return None


def _credit(session: Session, *, subject: str, user_id: Optional[str], client: str, page: str, day: date, seconds: int) -> None:
    if seconds <= 0:
        return
    row = session.get(ActivityDaily, (subject, day, client))
    if row is None:
        row = ActivityDaily(subject=subject, day=day, client=client, user_id=user_id, seconds=0)
        session.add(row)
    row.seconds = (row.seconds or 0) + seconds
    _page(session, day=day, client=client, page=page).seconds += seconds


def _page(session: Session, *, day: date, client: str, page: str) -> ActivityPageDaily:
    row = session.get(ActivityPageDaily, (day, client, page))
    if row is None:
        row = ActivityPageDaily(day=day, client=client, page=page, views=0, seconds=0)
        session.add(row)
        session.flush()
    return row


def record(session: Session, beat: Beat, now: Optional[datetime] = None) -> bool:
    """Apply one heartbeat. Returns False when it was ignored (too soon, or nobody to credit)."""
    global _beats_since_prune
    now = now or datetime.now(timezone.utc)
    subject = _subject(beat)
    if subject is None:
        return False
    page = normalize_page(beat.page)
    for attempt in range(2):
        try:
            applied = _apply(session, beat, subject, page, now)
            session.commit()
            break
        except IntegrityError:
            # Two heartbeats for the same person at once: the other made the row, so try again on top of it.
            session.rollback()
            if attempt:
                raise
    _beats_since_prune += 1
    if _beats_since_prune >= PRUNE_EVERY:
        _beats_since_prune = 0
        prune(session, now)
    return applied


def _apply(session: Session, beat: Beat, subject: str, page: str, now: datetime) -> bool:
    presence = session.get(ActivityPresence, (subject, beat.client))
    if presence is not None:
        since = (now - _aware(presence.last_seen_at)).total_seconds()
        if beat.event == "beat" and 0 <= since < MIN_BEAT_SECONDS and not presence.left:
            return False
        if not presence.left and 0 <= since <= GAP_SECONDS:
            _credit(session, subject=subject, user_id=beat.user_id, client=beat.client, page=presence.page, day=now.date(), seconds=int(min(since, MAX_CREDIT_SECONDS)))
        else:
            presence.visit_started_at = now
    else:
        presence = ActivityPresence(subject=subject, client=beat.client, user_id=beat.user_id, page=page, visit_started_at=now, last_seen_at=now)
        session.add(presence)
    if beat.event == "view":
        _page(session, day=now.date(), client=beat.client, page=page).views += 1
    presence.page = page
    presence.last_seen_at = now
    presence.left = beat.event == "leave"
    presence.user_id = beat.user_id
    if beat.app_version:
        presence.app_version = beat.app_version[:32]
    return True


def usage_allowed(session: Session, user_id: str) -> bool:
    """Whether this account said yes to usage counting. Not asked counts as no."""
    consent = session.get(Consent, user_id)
    return bool(consent is not None and consent.usage)


def forget_user(session: Session, user_id: str) -> None:
    """Delete the time and presence recorded for an account (it said no). Page totals have no names in them and stay."""
    session.execute(delete(ActivityDaily).where(ActivityDaily.user_id == user_id))
    session.execute(delete(ActivityPresence).where(ActivityPresence.user_id == user_id))


def forget_visitor(session: Session, visitor_key: str) -> None:
    """The same for a signed-out visitor who said no after saying yes."""
    subject = f"v:{visitor_key}"
    session.execute(delete(ActivityDaily).where(ActivityDaily.subject == subject))
    session.execute(delete(ActivityPresence).where(ActivityPresence.subject == subject))
    session.commit()


def prune(session: Session, now: Optional[datetime] = None) -> None:
    """Delete what's past keeping: daily rows after RETAIN_DAYS, presence after 30 days, admin records after 90."""
    now = now or datetime.now(timezone.utc)
    oldest = (now - timedelta(days=RETAIN_DAYS)).date()
    session.execute(delete(ActivityDaily).where(ActivityDaily.day < oldest))
    session.execute(delete(ActivityPageDaily).where(ActivityPageDaily.day < oldest))
    session.execute(delete(ActivityPresence).where(ActivityPresence.last_seen_at < now - timedelta(days=30)))
    session.execute(delete(AdminSignInAttempt).where(AdminSignInAttempt.at < now - timedelta(days=90)))
    session.execute(delete(AdminSession).where(AdminSession.expires_at < now - timedelta(days=90)))
    session.commit()


# ----- what the portal shows -----


def _day_range(now: datetime, days: int) -> tuple[date, date]:
    end = now.date()
    return end - timedelta(days=days - 1), end


def overview(session: Session, *, days: int = 7, now: Optional[datetime] = None) -> dict:
    """Everything the admin portal shows, for the last ``days`` days (UTC) including today."""
    now = now or datetime.now(timezone.utc)
    start, end = _day_range(now, days)
    online_since = now - timedelta(seconds=ONLINE_SECONDS)

    # Accounts are people who signed in (Google or GitHub). The demo users the platform seeds have no sign-in, so they aren't counted.
    providers: dict[str, list[str]] = {}
    for user_id, provider in session.execute(select(OAuthAccount.user_id, OAuthAccount.provider)):
        providers.setdefault(user_id, []).append(provider)
    users = {u.id: u for u in session.scalars(select(User).where(User.id.in_(list(providers))))} if providers else {}
    # Projects: the website's, and the desktop app's synced to the account (not counting deleted ones).
    project_counts = dict(session.execute(select(UserProject.owner_id, func.count()).group_by(UserProject.owner_id)).all())
    desktop_counts = dict(session.execute(select(SyncedProject.owner_id, func.count()).where(SyncedProject.deleted_at.is_(None)).group_by(SyncedProject.owner_id)).all())
    session_counts = dict(session.execute(select(LabSessionRecord.owner_id, func.count()).group_by(LabSessionRecord.owner_id)).all())

    # Time per account: all time, and in the range, per client.
    totals: dict[str, dict] = {}
    for user_id, client, day, seconds in session.execute(
        select(ActivityDaily.user_id, ActivityDaily.client, ActivityDaily.day, ActivityDaily.seconds).where(ActivityDaily.user_id.is_not(None))
    ):
        t = totals.setdefault(user_id, {"all": 0, "range": 0, "web": 0, "desktop": 0, "days": set()})
        t["all"] += seconds
        if start <= day <= end:
            t["range"] += seconds
            t[client] += seconds
            t["days"].add(day)

    presence_rows = list(session.scalars(select(ActivityPresence)))
    last_seen: dict[str, datetime] = {}
    online: list[dict] = []
    online_visitors = {"web": 0, "desktop": 0}
    for p in presence_rows:
        seen = _aware(p.last_seen_at)
        if p.user_id:
            if p.user_id not in last_seen or seen > last_seen[p.user_id]:
                last_seen[p.user_id] = seen
        is_online = seen >= online_since and not p.left
        if not is_online:
            continue
        if p.user_id and p.user_id in users:
            u = users[p.user_id]
            online.append(
                {
                    "user_id": u.id,
                    "name": u.display_name,
                    "email": u.email,
                    "client": p.client,
                    "page": p.page,
                    "since": _aware(p.visit_started_at).isoformat(),
                    "last_seen": seen.isoformat(),
                    "app_version": p.app_version or None,
                }
            )
        else:
            online_visitors[p.client] = online_visitors.get(p.client, 0) + 1
    online.sort(key=lambda o: o["since"])
    online_ids = {o["user_id"] for o in online}

    # Each account's answer to usage counting: True, False, or None (not asked yet).
    answers = {u: c for u, c in session.execute(select(Consent.user_id, Consent.usage))}
    accounts = []
    for u in users.values():
        t = totals.get(u.id, {"all": 0, "range": 0, "web": 0, "desktop": 0, "days": set()})
        seen = last_seen.get(u.id) or (_aware(u.last_login_at) if u.last_login_at else None)
        accounts.append(
            {
                "id": u.id,
                "name": u.display_name,
                "email": u.email,
                "created_at": _aware(u.created_at).isoformat() if u.created_at else None,
                "sign_in": sorted(set(providers.get(u.id, []))),
                "last_seen": seen.isoformat() if seen else None,
                "online": u.id in online_ids,
                "seconds_total": t["all"],
                "seconds_range": t["range"],
                "seconds_web": t["web"],
                "seconds_desktop": t["desktop"],
                "active_days": len(t["days"]),
                "projects": project_counts.get(u.id, 0) + desktop_counts.get(u.id, 0),
                "desktop_projects": desktop_counts.get(u.id, 0),
                "lab_sessions": session_counts.get(u.id, 0),
                "usage_consent": answers.get(u.id),
            }
        )
    accounts.sort(key=lambda a: (-a["seconds_range"], -a["seconds_total"], a["name"].lower()))

    pages: dict[str, dict] = {}
    for page, client, views, seconds in session.execute(
        select(ActivityPageDaily.page, ActivityPageDaily.client, ActivityPageDaily.views, ActivityPageDaily.seconds).where(ActivityPageDaily.day >= start, ActivityPageDaily.day <= end)
    ):
        p = pages.setdefault(page, {"page": page, "views": 0, "seconds": 0, "web": 0, "desktop": 0})
        p["views"] += views
        p["seconds"] += seconds
        p[client] += seconds
    top_pages = sorted(pages.values(), key=lambda p: (-p["seconds"], -p["views"], p["page"]))[:20]

    # One row per day: people signed in who used Kiungo, visitors who weren't, minutes, and new accounts.
    daily = {start + timedelta(days=i): {"active_accounts": set(), "visitors": set(), "seconds": 0, "new_accounts": 0} for i in range(days)}
    for subject, user_id, day, seconds in session.execute(
        select(ActivityDaily.subject, ActivityDaily.user_id, ActivityDaily.day, ActivityDaily.seconds).where(ActivityDaily.day >= start, ActivityDaily.day <= end)
    ):
        d = daily[day]
        d["seconds"] += seconds
        (d["active_accounts"] if user_id else d["visitors"]).add(subject)
    for u in users.values():
        if u.created_at and start <= _aware(u.created_at).date() <= end:
            daily[_aware(u.created_at).date()]["new_accounts"] += 1

    clients = {"web": 0, "desktop": 0}
    for client, seconds in session.execute(
        select(ActivityDaily.client, func.sum(ActivityDaily.seconds)).where(ActivityDaily.day >= start, ActivityDaily.day <= end).group_by(ActivityDaily.client)
    ):
        clients[client] = int(seconds or 0)

    consent_counts = {
        "allowed": sum(1 for u in users if answers.get(u) is True),
        "declined": sum(1 for u in users if answers.get(u) is False),
        "not_asked": sum(1 for u in users if answers.get(u) is None),
    }

    tracked_since = session.scalar(select(func.min(ActivityDaily.day)))
    created = [_aware(u.created_at) for u in users.values() if u.created_at]
    attempts = list(session.scalars(select(AdminSignInAttempt).order_by(AdminSignInAttempt.at.desc()).limit(12)))

    return {
        "generated_at": now.isoformat(),
        "days": days,
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "tracked_since": tracked_since.isoformat() if tracked_since else None,
        "totals": {
            "accounts": len(users),
            "accounts_new_range": sum(1 for c in created if start <= c.date() <= end),
            "projects": sum(project_counts.values()) + sum(desktop_counts.values()),
            "desktop_projects": sum(desktop_counts.values()),
            "lab_sessions": sum(session_counts.values()),
            "experiments": session.scalar(select(func.count()).select_from(UserProjectExperiment)) or 0,
            "desktop_devices": session.scalar(select(func.count()).select_from(Device).where(Device.revoked_at.is_(None))) or 0,
            "online_accounts": len(online_ids),
            "online_visitors": sum(online_visitors.values()),
            "seconds_range": sum(clients.values()),
            "active_accounts_range": sum(1 for t in totals.values() if t["range"] > 0),
        },
        "online": online,
        "online_visitors": online_visitors,
        "accounts": accounts,
        "pages": top_pages,
        "daily": [
            {"day": day.isoformat(), "active_accounts": len(d["active_accounts"]), "visitors": len(d["visitors"]), "seconds": d["seconds"], "new_accounts": d["new_accounts"]}
            for day, d in sorted(daily.items())
        ],
        "clients": clients,
        "usage_consent": consent_counts,
        "admin_sign_ins": [{"at": _aware(a.at).isoformat(), "ok": a.ok, "from": a.ip_hash[:6]} for a in attempts],
    }
