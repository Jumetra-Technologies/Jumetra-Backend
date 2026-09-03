"""Synchronization validation scenarios (measurement only)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Union

from ...devices.base.device import Device
from ...experiments.session import ExperimentSession
from ...network.model import NetworkConditionModel
from ...time.clock_domain import ClockDomainRegistry
from ..manager import SynchronizationManager
from ..observation import ClockObservation
from ..report import SynchronizationReport

logger = logging.getLogger("hhip.synchronization.scenarios")


@dataclass
class SyncScenario:
    """Named measurement scenario that produces ExperimentSession + report."""

    name: str
    sample_count: int = 50
    network: Optional[NetworkConditionModel] = None
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def run(
        self,
        sync_manager: SynchronizationManager,
        device: Union[Device, str],
        *,
        experiment_id: Optional[str] = None,
        clock_domains: Optional[ClockDomainRegistry] = None,
        advance_clock_ms: int = 0,
    ) -> tuple[ExperimentSession, SynchronizationReport, list[ClockObservation]]:
        """Execute the scenario and return session, report, and samples."""
        device_id = device.device_id if isinstance(device, Device) else str(device)

        previous_network = getattr(sync_manager, "_network", None)
        previous_domains = getattr(sync_manager, "_clock_domains", None)
        sync_manager.set_network_model(self.network)
        if clock_domains is not None:
            sync_manager.set_clock_domains(clock_domains)

        session = ExperimentSession(
            name=f"sync_scenario_{self.name}",
            experiment_id=experiment_id or f"SCN{self.name[:6].upper()}",
        )
        session.metadata.update(
            {
                "scenario": self.name,
                "description": self.description,
                "network": self.network.to_dict() if self.network else None,
                **self.metadata,
            }
        )
        session.start(devices=[device_id])
        sync_manager.bind_experiment(session)

        try:
            samples = sync_manager.collect_samples(
                device,
                count=self.sample_count,
                advance_clock_ms=advance_clock_ms,
            )
        finally:
            sync_manager.bind_experiment(None)
            sync_manager.set_network_model(previous_network)
            if clock_domains is not None:
                sync_manager.set_clock_domains(previous_domains)

        session.finish()
        quality = sync_manager.get_quality(
            device_id, target_samples=max(self.sample_count, 1)
        )
        report = SynchronizationReport.from_quality(
            quality,
            scenario_name=self.name,
            experiment_id=session.experiment_id,
            metadata={
                "description": self.description,
                "network": self.network.to_dict() if self.network else None,
            },
        )
        logger.info(
            "[SCENARIO] %s samples=%d avg_rtt=%s confidence=%.3f",
            self.name,
            report.sample_count,
            report.average_rtt,
            report.confidence_score,
        )
        return session, report, samples


def baseline_scenario(*, sample_count: int = 50) -> SyncScenario:
    return SyncScenario(
        name="baseline",
        sample_count=sample_count,
        network=None,
        description="Ideal virtual path with no injected network impairment",
    )


def high_latency_scenario(*, sample_count: int = 50, seed: int = 10) -> SyncScenario:
    return SyncScenario(
        name="high_latency",
        sample_count=sample_count,
        network=NetworkConditionModel(latency_ms=50.0, jitter_ms=5.0, packet_loss=0.0, seed=seed),
        description="Elevated base latency with modest jitter",
    )


def network_noise_scenario(*, sample_count: int = 50, seed: int = 20) -> SyncScenario:
    return SyncScenario(
        name="network_noise",
        sample_count=sample_count,
        network=NetworkConditionModel(
            latency_ms=10.0, jitter_ms=20.0, packet_loss=0.05, seed=seed
        ),
        description="Noisy path with jitter and light packet loss",
    )


def serial_load_scenario(*, sample_count: int = 50, seed: int = 30) -> SyncScenario:
    return SyncScenario(
        name="serial_load",
        sample_count=sample_count,
        network=NetworkConditionModel(
            latency_ms=5.0, jitter_ms=15.0, packet_loss=0.02, seed=seed
        ),
        description="Serial-bus contention style delay and occasional drops",
    )


SCENARIO_BUILDERS = {
    "baseline": baseline_scenario,
    "high_latency": high_latency_scenario,
    "network_noise": network_noise_scenario,
    "serial_load": serial_load_scenario,
}


def get_scenario(name: str, **kwargs: Any) -> SyncScenario:
    builder = SCENARIO_BUILDERS.get(name)
    if builder is None:
        raise KeyError(f"unknown sync scenario: {name}")
    return builder(**kwargs)
