"""Analytics export — JSON, CSV, and research summary."""

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path
from typing import Any, Mapping, Union

from .engine import AnalyticsEngine, ResearchReport
from .models import ExperimentAnalytics

PathLike = Union[str, Path]


def export_json(
    report: Mapping[str, Any],
    path: PathLike,
    *,
    indent: int = 2,
) -> Path:
    """Export report dict to JSON file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        json.dump(dict(report), fh, indent=indent, sort_keys=True)
        fh.write("\n")
    return p


def export_csv_devices(analytics: ExperimentAnalytics, path: PathLike) -> Path:
    """Export per-device metrics as CSV."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "device_id",
        "reliability_score",
        "average_sync_error",
        "offset_stability",
        "drift_rate",
        "correction_success_rate",
        "rollback_count",
        "communication_cost",
        "sync_event_count",
        "correction_attempts",
    ]
    with p.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for d in analytics.devices:
            writer.writerow(
                {
                    "device_id": d.device_id,
                    "reliability_score": d.reliability_score,
                    "average_sync_error": d.synchronization.average_sync_error,
                    "offset_stability": d.synchronization.offset_stability,
                    "drift_rate": d.synchronization.drift_rate,
                    "correction_success_rate": d.correction.correction_success_rate,
                    "rollback_count": d.correction.rollback_count,
                    "communication_cost": d.synchronization.communication_cost,
                    "sync_event_count": d.synchronization.sync_event_count,
                    "correction_attempts": d.correction.correction_attempts,
                }
            )
    return p


def export_csv_string(analytics: ExperimentAnalytics) -> str:
    """Return per-device CSV as string."""
    buf = StringIO()
    fieldnames = [
        "device_id",
        "reliability_score",
        "average_sync_error",
        "offset_stability",
        "drift_rate",
        "correction_success_rate",
        "rollback_count",
        "communication_cost",
    ]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for d in analytics.devices:
        writer.writerow(
            {
                "device_id": d.device_id,
                "reliability_score": d.reliability_score,
                "average_sync_error": d.synchronization.average_sync_error,
                "offset_stability": d.synchronization.offset_stability,
                "drift_rate": d.synchronization.drift_rate,
                "correction_success_rate": d.correction.correction_success_rate,
                "rollback_count": d.correction.rollback_count,
                "communication_cost": d.synchronization.communication_cost,
            }
        )
    return buf.getvalue()


def research_summary(report: ResearchReport) -> str:
    """Generate a plain-text research summary."""
    lines = [
        f"HHIP Research Summary — {report.name} ({report.experiment_id})",
        f"Strategy: {report.strategy}",
        f"Devices analyzed: {report.device_count}",
        "",
        "Synchronization",
        f"  Average sync error: {report.average_sync_error:.2f} ms",
        f"  Offset stability: {report.offset_stability:.3f}",
        f"  Drift rate: {report.drift_rate:.6f}",
        "",
        "Correction",
        f"  Success rate: {report.correction_success_rate:.1%}",
        f"  Rollback frequency: {report.rollback_frequency:.1%}",
        "",
        "Communication",
        f"  Total cost (units): {report.communication_cost}",
        "",
        "Latency distribution (ms)",
        f"  p50: {report.latency_distribution.get('p50', 0):.2f}",
        f"  p95: {report.latency_distribution.get('p95', 0):.2f}",
        f"  mean: {report.latency_distribution.get('mean', 0):.2f}",
        "",
        "Device reliability ranking",
    ]
    for i, rank in enumerate(report.device_rankings, 1):
        lines.append(f"  {i}. {rank['device_id']} — score {rank['score']:.3f}")
    return "\n".join(lines)


def export_research_summary(report: ResearchReport, path: PathLike) -> Path:
    """Write research summary text to file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(research_summary(report), encoding="utf-8")
    return p


def export_full(
    engine: AnalyticsEngine,
    output_dir: PathLike,
    *,
    basename: str = "research",
) -> dict[str, Path]:
    """Export JSON report, CSV devices, and text summary."""
    if engine.analytics is None:
        raise RuntimeError("no analytics loaded")
    report = engine.generate_report()
    out = Path(output_dir)
    paths = {
        "json": export_json(report.to_dict(), out / f"{basename}.json"),
        "csv": export_csv_devices(engine.analytics, out / f"{basename}_devices.csv"),
        "summary": export_research_summary(report, out / f"{basename}_summary.txt"),
    }
    return paths
