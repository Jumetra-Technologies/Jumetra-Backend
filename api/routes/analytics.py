"""Analytics API routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..schemas import AnalyticsOverview, ComparisonResult, DashboardOverview

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("", response_model=AnalyticsOverview)
def get_analytics(request: Request) -> AnalyticsOverview:
    return request.app.state.data_service.get_analytics_overview()


@router.get("/dashboard", response_model=DashboardOverview)
def get_dashboard_overview(request: Request) -> DashboardOverview:
    return request.app.state.data_service.get_dashboard_overview()


@router.get("/comparison", response_model=ComparisonResult)
def get_comparison(request: Request) -> ComparisonResult:
    return request.app.state.data_service.get_comparison()
