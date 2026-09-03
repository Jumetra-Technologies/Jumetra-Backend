"""Seed sample experiment data for dashboard development and tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, separators=(",", ":")))
            fh.write("\n")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")


def seed_experiments(base_dir: Path | str = "data") -> list[str]:
    """Write fixed and adaptive sample experiments. Returns experiment IDs."""
    root = Path(base_dir) / "experiments"
    created: list[str] = []

    fixed_id = "EXP_FIXED01"
    adaptive_id = "EXP_ADAPT01"

    fixed_measurements = [
        {"device_id": "esp32_a", "estimated_offset": 42.0, "round_trip_time": 20, "timestamp": 1000},
        {"device_id": "esp32_a", "estimated_offset": 38.0, "round_trip_time": 22, "timestamp": 6000},
        {"device_id": "esp32_a", "estimated_offset": 35.0, "round_trip_time": 21, "timestamp": 11000},
        {"device_id": "esp32_b", "estimated_offset": 15.0, "round_trip_time": 18, "timestamp": 1000},
        {"device_id": "esp32_b", "estimated_offset": 12.0, "round_trip_time": 19, "timestamp": 6000},
    ]
    adaptive_measurements = [
        {"device_id": "esp32_a", "estimated_offset": 30.0, "round_trip_time": 19, "timestamp": 1000},
        {"device_id": "esp32_a", "estimated_offset": 28.0, "round_trip_time": 18, "timestamp": 8000},
        {"device_id": "esp32_a", "estimated_offset": 26.0, "round_trip_time": 17, "timestamp": 15000},
        {"device_id": "esp32_b", "estimated_offset": 10.0, "round_trip_time": 17, "timestamp": 1000},
        {"device_id": "esp32_b", "estimated_offset": 8.0, "round_trip_time": 16, "timestamp": 8000},
    ]

    fixed_results = [
        {"device_id": "esp32_a", "offset": 38.0, "drift_rate": 0.002, "timestamp": 11000},
        {"device_id": "esp32_b", "offset": 13.0, "drift_rate": 0.001, "timestamp": 6000},
    ]
    adaptive_results = [
        {"device_id": "esp32_a", "offset": 28.0, "drift_rate": 0.0012, "timestamp": 15000},
        {"device_id": "esp32_b", "offset": 9.0, "drift_rate": 0.0008, "timestamp": 8000},
    ]

    fixed_transactions = [
        {"device_id": "esp32_a", "state": "COMPLETED", "improvement": 5.0},
        {"device_id": "esp32_a", "state": "ROLLED_BACK", "improvement": 0.0},
    ]
    adaptive_transactions = [
        {"device_id": "esp32_a", "state": "COMPLETED", "improvement": 7.0},
        {"device_id": "esp32_a", "state": "COMPLETED", "improvement": 3.0},
        {"device_id": "esp32_b", "state": "COMPLETED", "improvement": 2.0},
    ]

    fixed_time_series = [
        {"sequence": i, "elapsed_ms": i * 5000, "device_id": "esp32_a", "estimated_offset": o}
        for i, o in enumerate([42.0, 38.0, 35.0])
    ]
    adaptive_time_series = [
        {"sequence": i, "elapsed_ms": i * 7000, "device_id": "esp32_a", "estimated_offset": o}
        for i, o in enumerate([30.0, 28.0, 26.0])
    ]

    fixed_dir = root / fixed_id
    _write_jsonl(fixed_dir / "sync_measurements.jsonl", fixed_measurements)
    _write_jsonl(fixed_dir / "sync_results.jsonl", fixed_results)
    _write_jsonl(fixed_dir / "events.jsonl", [
        {"device_id": "esp32_a", "latencies": {"total_latency": 5.0}},
        {"device_id": "esp32_b", "latencies": {"total_latency": 8.0}},
    ])
    _write_jsonl(fixed_dir / "transactions.jsonl", fixed_transactions)
    _write_jsonl(fixed_dir / "sync_time_series.jsonl", fixed_time_series)
    _write_json(fixed_dir / "summary.json", {
        "experiment_id": fixed_id,
        "name": "fixed_sync_baseline",
        "start_time": 1000,
        "end_time": 12000,
        "duration_ms": 11000,
        "devices": ["esp32_a", "esp32_b"],
        "event_count": 2,
        "sync_measurement_count": 5,
        "metadata": {"strategy": "fixed", "communication_cost": 10},
    })
    created.append(fixed_id)

    adaptive_dir = root / adaptive_id
    _write_jsonl(adaptive_dir / "sync_measurements.jsonl", adaptive_measurements)
    _write_jsonl(adaptive_dir / "sync_results.jsonl", adaptive_results)
    _write_jsonl(adaptive_dir / "events.jsonl", [
        {"device_id": "esp32_a", "latencies": {"total_latency": 4.2}},
        {"device_id": "esp32_b", "latencies": {"total_latency": 6.8}},
    ])
    _write_jsonl(adaptive_dir / "transactions.jsonl", adaptive_transactions)
    _write_jsonl(adaptive_dir / "sync_time_series.jsonl", adaptive_time_series)
    _write_json(adaptive_dir / "summary.json", {
        "experiment_id": adaptive_id,
        "name": "adaptive_sync_study",
        "start_time": 1000,
        "end_time": 16000,
        "duration_ms": 15000,
        "devices": ["esp32_a", "esp32_b"],
        "event_count": 2,
        "sync_measurement_count": 5,
        "metadata": {"strategy": "adaptive", "communication_cost": 7},
    })
    created.append(adaptive_id)

    snapshot_dir = Path(base_dir) / "snapshots"
    _write_json(snapshot_dir / "state.json", {
        "esp32_a": {"status": "connected", "last_seen": 16000},
        "esp32_b": {"status": "connected", "last_seen": 16000},
    })

    return created


if __name__ == "__main__":
    ids = seed_experiments()
    print("Seeded experiments:", ", ".join(ids))
