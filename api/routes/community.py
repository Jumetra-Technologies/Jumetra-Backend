"""Community figures for the website's Advanced Analytics page.

Public and read-only: platform-wide totals and breakdowns, never anything
about one person. The rules that keep it that way are in
api/services/community_stats.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from ..services import community_stats

router = APIRouter(prefix="/community", tags=["community"])


class CommunityTotals(BaseModel):
    builders: int
    active_builders_30d: int
    projects: int
    lab_sessions: int
    experiments: int
    parts_placed: int
    wires: int
    runs: int
    faults_fixed: int
    simulated_hours: float
    modules_completed: int


class CommunityRow(BaseModel):
    key: str
    count: int
    people: int


class CommunityOther(BaseModel):
    count: int
    people: int


class CommunityBreakdown(BaseModel):
    rows: list[CommunityRow]
    other: CommunityOther | None


class CommunityMonth(BaseModel):
    month: str
    projects: int
    lab_sessions: int
    projects_to_date: int
    lab_sessions_to_date: int
    builders: int | None


class CommunityPrivacy(BaseModel):
    min_group: int
    cache_seconds: int


class CommunityStats(BaseModel):
    generated_at: str
    totals: CommunityTotals
    parts: CommunityBreakdown
    project_hardware: CommunityBreakdown
    categories: CommunityBreakdown
    modes: CommunityBreakdown
    monthly: list[CommunityMonth]
    privacy: CommunityPrivacy


@router.get("/stats", response_model=CommunityStats)
def community_stats_route(request: Request, response: Response) -> dict:
    """What everyone has built in Kiungo. Breakdown rows need at least `privacy.min_group` people."""
    response.headers["Cache-Control"] = f"public, max-age={community_stats.CACHE_SECONDS // 2}"
    return community_stats.cached(request.app.state.db_factory)
