"""HHIP Research Analytics & Data Intelligence Layer."""

from .comparison import ExperimentComparison, ExperimentComparisonResult
from .engine import AnalyticsEngine, ResearchReport
from .export import (
    export_csv_devices,
    export_csv_string,
    export_full,
    export_json,
    export_research_summary,
    research_summary,
)
from .models import (
    CorrectionMetrics,
    DeviceMetrics,
    ExperimentAnalytics,
    SynchronizationMetrics,
)
from .reliability import DeviceReliabilityScore

__all__ = [
    "AnalyticsEngine",
    "CorrectionMetrics",
    "DeviceMetrics",
    "DeviceReliabilityScore",
    "ExperimentAnalytics",
    "ExperimentComparison",
    "ExperimentComparisonResult",
    "ResearchReport",
    "SynchronizationMetrics",
    "export_csv_devices",
    "export_csv_string",
    "export_full",
    "export_json",
    "export_research_summary",
    "research_summary",
]
