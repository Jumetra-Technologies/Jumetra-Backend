"""Read-only data access for the HHIP dashboard API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from engine.analytics import AnalyticsEngine, ExperimentComparison
from engine.storage.storage_manager import StorageManager

from ..schemas import (
    AnalyticsOverview,
    ComparisonResult,
    DashboardOverview,
    DeviceDetail,
    DeviceSummary,
    ExperimentDetail,
    ExperimentSummary,
    LatencyDistribution,
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            if isinstance(data, dict):
                records.append(data)
    return records


def _read_json(path: Path) -> Optional[dict[str, Any]]:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else None


class DataService:
    """Load HHIP experiment data and analytics without touching sync logic."""

    def __init__(self, base_dir: Path | str = "data") -> None:
        self.storage = StorageManager(base_dir)
        self.base_dir = Path(base_dir)

    def list_experiment_ids(self) -> list[str]:
        root = self.storage.experiments_dir
        if not root.exists():
            return []
        return sorted(
            p.name
            for p in root.iterdir()
            if p.is_dir() and (p / "summary.json").exists()
        )

    def _experiment_dir(self, experiment_id: str) -> Path:
        return self.storage.experiment_path(experiment_id)

    def load_experiment_payload(self, experiment_id: str) -> dict[str, Any]:
        """Build analytics input dict from exported experiment files."""
        root = self._experiment_dir(experiment_id)
        if not root.exists():
            raise FileNotFoundError(f"experiment not found: {experiment_id}")

        summary = _read_json(root / "summary.json") or {}
        metadata = dict(summary.get("metadata") or {})
        strategy = str(metadata.get("strategy", "unknown"))

        sync_measurements = _read_jsonl(root / "sync_measurements.jsonl")
        if not sync_measurements:
            sync_measurements = _read_jsonl(root / "sync_samples.jsonl")

        transactions = _read_jsonl(root / "transactions.jsonl")
        health_reports = _read_json(root / "health_report.json")
        health_list: list[dict[str, Any]] = []
        if isinstance(health_reports, dict):
            health_list = [health_reports]
        elif isinstance(health_reports, list):
            health_list = [h for h in health_reports if isinstance(h, dict)]

        return {
            "experiment_id": experiment_id,
            "name": str(summary.get("name", experiment_id)),
            "strategy": strategy,
            "sync_measurements": sync_measurements,
            "sync_results": _read_jsonl(root / "sync_results.jsonl"),
            "events": _read_jsonl(root / "events.jsonl"),
            "transactions": transactions,
            "health_reports": health_list,
            "metadata": metadata,
            "communication_cost": int(metadata.get("communication_cost", 0)),
            "summary": summary,
        }

    def analyze_experiment(self, experiment_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        payload = self.load_experiment_payload(experiment_id)
        engine = AnalyticsEngine()
        analytics = engine.load_from_dict(payload)
        report = engine.generate_report()
        return analytics.to_dict(), report.to_dict()

    def list_experiments(self) -> list[ExperimentSummary]:
        results: list[ExperimentSummary] = []
        for exp_id in self.list_experiment_ids():
            try:
                payload = self.load_experiment_payload(exp_id)
                summary = payload.get("summary") or {}
                _, report = self.analyze_experiment(exp_id)
                metadata = payload.get("metadata") or {}
                status = "active" if metadata.get("active") else "completed"
                results.append(
                    ExperimentSummary(
                        experiment_id=exp_id,
                        name=str(payload.get("name", exp_id)),
                        strategy=str(payload.get("strategy", "unknown")),
                        status=status,
                        device_count=len(summary.get("devices") or []),
                        start_time=summary.get("start_time"),
                        end_time=summary.get("end_time"),
                        duration_ms=summary.get("duration_ms"),
                        average_sync_error=float(report.get("average_sync_error", 0.0)),
                        correction_success_rate=float(report.get("correction_success_rate", 0.0)),
                    )
                )
            except (FileNotFoundError, json.JSONDecodeError, KeyError):
                continue
        return results

    def get_experiment(self, experiment_id: str) -> ExperimentDetail:
        payload = self.load_experiment_payload(experiment_id)
        analytics, report = self.analyze_experiment(experiment_id)
        root = self._experiment_dir(experiment_id)
        summary = payload.get("summary") or {}
        metadata = payload.get("metadata") or {}
        status = "active" if metadata.get("active") else "completed"

        return ExperimentDetail(
            experiment_id=experiment_id,
            name=str(payload.get("name", experiment_id)),
            strategy=str(payload.get("strategy", "unknown")),
            status=status,
            summary=summary,
            analytics=analytics,
            report=report,
            sync_time_series=_read_jsonl(root / "sync_time_series.jsonl"),
            sync_measurements=payload.get("sync_measurements") or [],
            sync_results=payload.get("sync_results") or [],
            transactions=payload.get("transactions") or [],
        )

    def _collect_devices(self) -> dict[str, dict[str, Any]]:
        devices: dict[str, dict[str, Any]] = {}

        snapshot = self.storage.load_snapshot()
        if isinstance(snapshot, dict):
            for device_id, state in snapshot.items():
                if isinstance(state, dict):
                    devices.setdefault(str(device_id), {}).update(
                        {"status": state.get("status", "connected"), "snapshot": state}
                    )

        for exp_id in self.list_experiment_ids():
            try:
                analytics, _ = self.analyze_experiment(exp_id)
            except (FileNotFoundError, json.JSONDecodeError):
                continue
            for dm in analytics.get("devices") or []:
                did = str(dm.get("device_id", ""))
                if not did:
                    continue
                entry = devices.setdefault(
                    did,
                    {"status": "observed", "experiments": [], "metrics": []},
                )
                exps = entry.setdefault("experiments", [])
                if exp_id not in exps:
                    exps.append(exp_id)
                metrics = entry.setdefault("metrics", [])
                metrics.append(dm)

        return devices

    def list_devices(self) -> list[DeviceSummary]:
        devices = self._collect_devices()
        summaries: list[DeviceSummary] = []
        for device_id, info in sorted(devices.items()):
            metrics_list = info.get("metrics") or []
            if metrics_list:
                avg_error = sum(
                    m.get("synchronization", {}).get("average_sync_error", 0.0)
                    for m in metrics_list
                ) / len(metrics_list)
                avg_drift = sum(
                    m.get("synchronization", {}).get("drift_rate", 0.0) for m in metrics_list
                ) / len(metrics_list)
                avg_rel = sum(m.get("reliability_score", 0.0) for m in metrics_list) / len(
                    metrics_list
                )
                avg_health = sum(
                    m.get("correction", {}).get("correction_success_rate", 0.0)
                    for m in metrics_list
                ) / len(metrics_list)
            else:
                avg_error = avg_drift = avg_rel = avg_health = 0.0

            summaries.append(
                DeviceSummary(
                    device_id=device_id,
                    status=str(info.get("status", "unknown")),
                    reliability_score=avg_rel,
                    health_score=avg_health,
                    average_sync_error=avg_error,
                    drift_rate=avg_drift,
                    experiment_count=len(info.get("experiments") or []),
                )
            )
        return summaries

    def get_device(self, device_id: str) -> DeviceDetail:
        devices = self._collect_devices()
        if device_id not in devices:
            raise FileNotFoundError(f"device not found: {device_id}")

        info = devices[device_id]
        metrics_list = info.get("metrics") or []
        merged: dict[str, Any] = {}
        sync_history: list[dict[str, Any]] = []

        if metrics_list:
            last = metrics_list[-1]
            merged = dict(last)
            for exp_id in info.get("experiments") or []:
                try:
                    detail = self.get_experiment(exp_id)
                except FileNotFoundError:
                    continue
                for point in detail.sync_time_series:
                    if str(point.get("device_id")) == device_id:
                        sync_history.append(point)
                for sample in detail.sync_measurements:
                    if str(sample.get("device_id")) == device_id:
                        sync_history.append(
                            {
                                "timestamp": sample.get("timestamp"),
                                "estimated_offset": sample.get("estimated_offset"),
                                "round_trip_time": sample.get("round_trip_time"),
                                "experiment_id": exp_id,
                            }
                        )

        from engine.analytics import DeviceReliabilityScore

        reliability = {}
        if merged:
            reliability = DeviceReliabilityScore.from_device_metrics(merged).to_dict()

        return DeviceDetail(
            device_id=device_id,
            status=str(info.get("status", "unknown")),
            metrics=merged,
            reliability=reliability,
            sync_history=sorted(
                sync_history,
                key=lambda p: p.get("timestamp") or p.get("elapsed_ms") or 0,
            ),
            experiments=list(info.get("experiments") or []),
        )

    def get_analytics_overview(self) -> AnalyticsOverview:
        experiments = self.list_experiments()
        if not experiments:
            return AnalyticsOverview()

        reports = []
        for exp in experiments:
            try:
                _, report = self.analyze_experiment(exp.experiment_id)
                reports.append(report)
            except (FileNotFoundError, json.JSONDecodeError):
                continue

        if not reports:
            return AnalyticsOverview()

        n = len(reports)
        device_ids: set[str] = set()
        rankings: list[dict[str, Any]] = []
        for report in reports:
            for rank in report.get("device_rankings") or []:
                device_ids.add(str(rank.get("device_id", "")))
                rankings.append(rank)

        rankings = sorted(rankings, key=lambda r: r.get("score", 0), reverse=True)

        return AnalyticsOverview(
            experiment_count=len(experiments),
            device_count=len(device_ids),
            average_sync_error=sum(r.get("average_sync_error", 0.0) for r in reports) / n,
            offset_stability=sum(r.get("offset_stability", 0.0) for r in reports) / n,
            drift_rate=sum(r.get("drift_rate", 0.0) for r in reports) / n,
            correction_success_rate=sum(r.get("correction_success_rate", 0.0) for r in reports) / n,
            rollback_frequency=sum(r.get("rollback_frequency", 0.0) for r in reports) / n,
            communication_cost=sum(int(r.get("communication_cost", 0)) for r in reports),
            latency_distribution=reports[-1].get("latency_distribution") or {},
            device_rankings=rankings[:10],
        )

    def get_dashboard_overview(self) -> DashboardOverview:
        experiments = self.list_experiments()
        devices = self.list_devices()
        active = sum(1 for e in experiments if e.status == "active")

        if experiments:
            accuracy = sum(e.average_sync_error for e in experiments) / len(experiments)
            # Lower sync error = higher accuracy score
            sync_accuracy = max(0.0, min(100.0, 100.0 - accuracy))
        else:
            sync_accuracy = 0.0

        latency = LatencyDistribution()
        health = 0.0
        if experiments:
            try:
                _, report = self.analyze_experiment(experiments[0].experiment_id)
                dist = report.get("latency_distribution") or {}
                latency = LatencyDistribution(
                    p50=float(dist.get("p50", 0.0)),
                    p95=float(dist.get("p95", 0.0)),
                    min=float(dist.get("min", 0.0)),
                    max=float(dist.get("max", 0.0)),
                    mean=float(dist.get("mean", 0.0)),
                )
                health = float(report.get("correction_success_rate", 0.0)) * 100.0
            except (FileNotFoundError, json.JSONDecodeError):
                pass

        return DashboardOverview(
            active_experiments=active,
            total_experiments=len(experiments),
            connected_devices=len(devices),
            synchronization_accuracy=sync_accuracy,
            latency=latency,
            system_health=health,
            recent_experiments=experiments[:5],
        )

    def get_comparison(self) -> ComparisonResult:
        experiments = self.list_experiments()
        fixed = next((e for e in experiments if e.strategy == "fixed"), None)
        adaptive = next((e for e in experiments if e.strategy == "adaptive"), None)

        if fixed is None or adaptive is None:
            # Try metadata comparison file
            comparison_path = self.base_dir / "analytics" / "comparison.json"
            comp_data = _read_json(comparison_path)
            if comp_data:
                return ComparisonResult(**comp_data)

            return ComparisonResult(
                metadata={"message": "Need both fixed and adaptive experiments for comparison"}
            )

        fixed_analytics, _ = self.analyze_experiment(fixed.experiment_id)
        adaptive_analytics, _ = self.analyze_experiment(adaptive.experiment_id)

        from engine.analytics.models import ExperimentAnalytics

        result = ExperimentComparison.compare(
            ExperimentAnalytics.from_dict(fixed_analytics),
            ExperimentAnalytics.from_dict(adaptive_analytics),
        )
        d = result.to_dict()
        return ComparisonResult(
            fixed_experiment_id=fixed.experiment_id,
            adaptive_experiment_id=adaptive.experiment_id,
            accuracy_difference=float(d.get("accuracy_difference", 0.0)),
            communication_savings=int(d.get("communication_savings", 0)),
            correction_efficiency=float(d.get("correction_efficiency_difference", 0.0)),
            failure_difference=int(d.get("failure_difference", 0)),
            metadata=d.get("metadata") or {},
        )
