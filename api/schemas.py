"""Pydantic response schemas for the HHIP dashboard API."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ExperimentSummary(BaseModel):
    experiment_id: str
    name: str
    strategy: str = "unknown"
    status: str = "completed"
    device_count: int = 0
    start_time: Optional[int] = None
    end_time: Optional[int] = None
    duration_ms: Optional[int] = None
    average_sync_error: float = 0.0
    correction_success_rate: float = 0.0


class DeviceSummary(BaseModel):
    device_id: str
    status: str = "unknown"
    reliability_score: float = 0.0
    health_score: float = 0.0
    average_sync_error: float = 0.0
    drift_rate: float = 0.0
    experiment_count: int = 0


class LatencyDistribution(BaseModel):
    p50: float = 0.0
    p95: float = 0.0
    min: float = 0.0
    max: float = 0.0
    mean: float = 0.0


class DashboardOverview(BaseModel):
    active_experiments: int = 0
    total_experiments: int = 0
    connected_devices: int = 0
    synchronization_accuracy: float = 0.0
    latency: LatencyDistribution = Field(default_factory=LatencyDistribution)
    system_health: float = 0.0
    recent_experiments: list[ExperimentSummary] = Field(default_factory=list)


class ExperimentDetail(BaseModel):
    experiment_id: str
    name: str
    strategy: str = "unknown"
    status: str = "completed"
    summary: dict[str, Any] = Field(default_factory=dict)
    analytics: dict[str, Any] = Field(default_factory=dict)
    report: dict[str, Any] = Field(default_factory=dict)
    sync_time_series: list[dict[str, Any]] = Field(default_factory=list)
    sync_measurements: list[dict[str, Any]] = Field(default_factory=list)
    sync_results: list[dict[str, Any]] = Field(default_factory=list)
    transactions: list[dict[str, Any]] = Field(default_factory=list)


class DeviceDetail(BaseModel):
    device_id: str
    status: str = "unknown"
    metrics: dict[str, Any] = Field(default_factory=dict)
    reliability: dict[str, Any] = Field(default_factory=dict)
    sync_history: list[dict[str, Any]] = Field(default_factory=list)
    experiments: list[str] = Field(default_factory=list)


class AnalyticsOverview(BaseModel):
    experiment_count: int = 0
    device_count: int = 0
    average_sync_error: float = 0.0
    offset_stability: float = 0.0
    drift_rate: float = 0.0
    correction_success_rate: float = 0.0
    rollback_frequency: float = 0.0
    communication_cost: int = 0
    latency_distribution: dict[str, float] = Field(default_factory=dict)
    device_rankings: list[dict[str, Any]] = Field(default_factory=list)


class ComparisonResult(BaseModel):
    fixed_experiment_id: str = ""
    adaptive_experiment_id: str = ""
    accuracy_difference: float = 0.0
    communication_savings: int = 0
    correction_efficiency: float = 0.0
    failure_difference: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExperimentStartRequest(BaseModel):
    name: str
    devices: list[str] = Field(default_factory=list)
    strategy: str = "fixed"
    duration_ms: Optional[int] = None
    sync_interval_ms: Optional[int] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExperimentStatusResponse(BaseModel):
    experiment_id: str
    name: str
    status: str
    strategy: str
    devices: list[str] = Field(default_factory=list)
    progress: float = 0.0
    start_time: Optional[int] = None
    end_time: Optional[int] = None
    elapsed_ms: Optional[int] = None
    event_count: int = 0
    sync_measurement_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectSummary(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    organization: str = ""
    experiment_count: int = 0
    created_at: Optional[str] = None


class ProjectDetail(ProjectSummary):
    experiments: list[dict[str, Any]] = Field(default_factory=list)
    datasets: list[dict[str, Any]] = Field(default_factory=list)
    reports: list[dict[str, Any]] = Field(default_factory=list)
