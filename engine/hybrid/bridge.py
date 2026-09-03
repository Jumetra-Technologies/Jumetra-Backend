"""Hybrid bridge orchestrator — coordinates physical, virtual, and simulated devices."""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from engine.components.registry import ComponentRegistry
from engine.communication.memory_adapter import InMemoryAdapter, make_adapter_pair
from engine.controllers.compatibility import ControllerRegistry
from engine.devices.base.physical_device import PhysicalDevice
from engine.devices.device_manager import DeviceManager
from engine.events.event_bus import EventBus
from engine.simulation import SimulationEngine, VirtualLaboratoryService
from engine.simulation.adapters import InProcessSimulatorAdapter
from engine.simulation.events import SimulationEventType

from .adapters import (
    HybridSerialAdapter,
    HybridSimulatorAdapter,
    HybridVirtualAdapter,
)
from .device import HybridDevice
from .modes import HybridDeviceMode
from .events import HybridEventType, publish_hybrid_event
from .experiment.session import DeviceAssignment, HybridExperimentSession
from .physical.esp32 import PhysicalESP32
from .simulators import ProteusAdapter, WokwiAdapter, wrap_backend
from .storage.persistence import HybridStorage


class HybridBridgeService:
    """High-level service for hybrid hardware experiments."""

    def __init__(
        self,
        component_registry: ComponentRegistry,
        controller_registry: ControllerRegistry,
        *,
        lab_service: Optional[VirtualLaboratoryService] = None,
        storage: Optional[HybridStorage] = None,
        event_bus: Optional[EventBus] = None,
        device_manager: Optional[DeviceManager] = None,
    ) -> None:
        self.components = component_registry
        self.controllers = controller_registry
        self.lab_service = lab_service or VirtualLaboratoryService(
            component_registry, controller_registry, event_bus=event_bus or EventBus()
        )
        self.storage = storage or HybridStorage()
        self.event_bus = event_bus or EventBus()
        self.device_manager = device_manager or DeviceManager()
        self._sessions: dict[str, HybridExperimentSession] = {}
        self._engines: dict[str, SimulationEngine] = {}
        self._physical: dict[str, PhysicalESP32] = {}

    def create_experiment(
        self,
        *,
        name: str,
        controller_id: str,
        component_ids: list[str],
        device_modes: Optional[dict[str, str]] = None,
        physical_device_id: str = "esp32_01",
        use_memory_transport: bool = True,
        simulator_backend: str = "in-process",
    ) -> dict[str, Any]:
        modes = device_modes or {}
        lab = self.lab_service.create(
            name=name,
            controller_id=controller_id,
            component_ids=component_ids,
            description="Hybrid experiment laboratory",
            metadata={"hybrid": True},
        )
        lab_id = lab["laboratory_id"]

        assignments: list[DeviceAssignment] = []
        devices: list[HybridDevice] = []

        for cid in component_ids:
            mode_str = modes.get(cid, "virtual")
            try:
                mode = HybridDeviceMode(mode_str.lower())
            except ValueError:
                mode = HybridDeviceMode.VIRTUAL

            spec = self.components.require(cid)
            assignment = DeviceAssignment(
                component_id=cid,
                mode=mode,
                available=mode != HybridDeviceMode.PHYSICAL,
                simulator_backend=simulator_backend if mode == HybridDeviceMode.SIMULATED else "",
            )

            if mode == HybridDeviceMode.PHYSICAL:
                assignment.device_id = physical_device_id
                assignment.available = use_memory_transport
            elif mode == HybridDeviceMode.VIRTUAL:
                for comp in lab.get("session", {}).get("components", []):
                    if comp.get("component_id") == cid:
                        assignment.instance_id = str(comp.get("instance_id", ""))
                        assignment.device_id = assignment.instance_id
                        assignment.available = True
                        break
            elif mode == HybridDeviceMode.SIMULATED:
                assignment.device_id = f"sim_{cid}"
                assignment.available = True

            assignments.append(assignment)

        session = HybridExperimentSession.create(
            name=name,
            laboratory_id=lab_id,
            controller_id=controller_id,
            component_ids=component_ids,
            assignments=assignments,
        )

        if use_memory_transport and any(a.mode == HybridDeviceMode.PHYSICAL for a in assignments):
            engine_adapter, device_adapter = make_adapter_pair()
            serial = HybridSerialAdapter(device_adapter)
            physical = PhysicalESP32(
                physical_device_id,
                serial,
                event_bus=self.event_bus,
                experiment_id=session.experiment_id,
            )
            physical.connect()
            physical.send_hello()
            self._physical[session.experiment_id] = physical
            phys_dev = PhysicalDevice(device_id=physical_device_id, device_type="ESP32")
            self.device_manager.register_device(phys_dev)
            devices.append(HybridDevice.from_physical(phys_dev, serial))

        for assignment in assignments:
            if assignment.mode == HybridDeviceMode.VIRTUAL and assignment.available:
                virt = HybridDevice.from_virtual(
                    device_id=assignment.device_id,
                    component_id=assignment.component_id,
                    instance_id=assignment.instance_id,
                    adapter=HybridVirtualAdapter(),
                    name=assignment.component_id,
                )
                devices.append(virt)
            elif assignment.mode == HybridDeviceMode.SIMULATED:
                if simulator_backend in ("wokwi", "proteus"):
                    backend = self._create_simulator_backend(simulator_backend)
                    sim_adapter = HybridSimulatorAdapter(wrap_backend(backend))
                    backend_name = backend.name
                else:
                    backend = InProcessSimulatorAdapter()
                    sim_adapter = HybridSimulatorAdapter(backend)
                    backend_name = backend.name
                sim_adapter.connect()
                circuit = lab.get("session", {}).get("circuit", {})
                if circuit:
                    sim_adapter.load_circuit(circuit)
                devices.append(
                    HybridDevice.from_simulated(assignment.device_id, sim_adapter, name=backend_name)
                )

        session.devices = devices
        self._sessions[session.experiment_id] = session

        project = session.to_dict()
        project["laboratory"] = lab
        project["circuit"] = lab.get("session", {}).get("circuit", {})
        self.storage.save_project(session.experiment_id, project)
        self.storage.save_assignments(session.experiment_id, [a.to_dict() for a in assignments])
        self.storage.save_mappings(
            session.experiment_id,
            {"laboratory_id": lab_id, "device_modes": modes, "simulator_backend": simulator_backend},
        )

        publish_hybrid_event(
            self.event_bus,
            HybridEventType.HYBRID_BINDING_CREATED,
            source=session.experiment_id,
            payload=project,
            experiment_id=session.experiment_id,
        )
        return project

    def start(self, experiment_id: str) -> dict[str, Any]:
        session = self._require_session(experiment_id)
        lab_result = self.lab_service.start(session.laboratory_id)
        engine = self.lab_service._engines.get(session.laboratory_id)
        if engine is not None:
            self._engines[experiment_id] = engine
            for device in session.devices:
                if device.adapter and isinstance(device.adapter, HybridVirtualAdapter):
                    device.adapter.bind_engine(engine)
                    device.adapter.connect()

        session.start(self.event_bus)
        state = session.get_state()
        state["simulation"] = lab_result.get("state", {})
        self.storage.save_run(experiment_id, f"RUN{uuid.uuid4().hex[:6].upper()}", state)
        return {"status": session.status.value, "state": state}

    def advance(self, experiment_id: str, delta_ms: int = 100) -> dict[str, Any]:
        session = self._require_session(experiment_id)
        t0 = time.perf_counter()

        step: dict[str, Any] = {}
        engine = self._engines.get(experiment_id)
        if engine is not None:
            step = self.lab_service.advance_simulation(session.laboratory_id, delta_ms)
            session.record_simulation({"step": step})
            for event_type in (SimulationEventType.SENSOR_DATA, SimulationEventType.GPIO_CHANGE):
                session.record_virtual({"event_type": event_type, "tick": step.get("step", {}).get("tick")})

        physical = self._physical.get(experiment_id)
        if physical is not None:
            converted = physical.poll()
            if converted:
                latency = (time.perf_counter() - t0) * 1000
                session.record_physical(converted, latency_ms=latency)

        for device in session.devices:
            if isinstance(device.adapter, HybridSimulatorAdapter):
                result = device.adapter.step(delta_ms)
                session.record_simulation({"simulator": device.device_id, "result": result})

        session.record_sync_observation(
            {"observed_latency_ms": session.average_latency_ms(), "delta_ms": delta_ms}
        )
        return {"status": session.status.value, "step": step, "state": session.get_state()}

    def stop(self, experiment_id: str) -> dict[str, Any]:
        session = self._require_session(experiment_id)
        if session.laboratory_id in self.lab_service._engines:
            self.lab_service.stop_simulation(session.laboratory_id)
        physical = self._physical.pop(experiment_id, None)
        if physical is not None:
            physical.disconnect()
        session.stop(self.event_bus)
        self._engines.pop(experiment_id, None)
        state = session.get_state()
        self.storage.save_run(experiment_id, f"RUN{uuid.uuid4().hex[:6].upper()}", state)
        return {"status": session.status.value, "state": state}

    def get_state(self, experiment_id: str) -> dict[str, Any]:
        session = self._require_session(experiment_id)
        return session.get_state()

    def list_experiments(self) -> list[dict[str, Any]]:
        return [s.to_dict() for s in self._sessions.values()]

    def _require_session(self, experiment_id: str) -> HybridExperimentSession:
        session = self._sessions.get(experiment_id)
        if session is None:
            stored = self.storage.load_project(experiment_id)
            if stored is None:
                raise KeyError(f"hybrid experiment not found: {experiment_id}")
            raise KeyError(f"hybrid experiment {experiment_id} not in memory; reload not implemented")
        return session

    @staticmethod
    def _create_simulator_backend(name: str):
        if name == "wokwi":
            return WokwiAdapter()
        if name == "proteus":
            return ProteusAdapter()
        return InProcessSimulatorAdapter()
