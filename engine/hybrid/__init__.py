"""Hybrid Hardware Bridge — physical, virtual, and simulated devices as one experiment."""

from .adapters import (
    DeviceAdapter,
    HybridMqttAdapter,
    HybridSerialAdapter,
    HybridSimulatorAdapter,
    HybridVirtualAdapter,
    HybridWifiAdapter,
)
from .bridge import HybridBridgeService
from .device import HybridDevice, map_legacy_mode
from .device_agent import DeviceAgent
from .hybrid_router import HybridRouter
from .modes import HybridDeviceMode
from .events import HybridEventType, publish_hybrid_event
from .experiment import DeviceAssignment, HybridExperimentSession, HybridExperimentStatus
from .physical_layer import PhysicalHybridLayer
from .pin_mapper import PinMapper
from .physical import PhysicalESP32
from .physical_device import PhysicalDevice, PhysicalPin
from .registry import HybridRegistry, PhysicalDeviceRegistry
from .serial_transport import SerialTransport
from .simulators import HybridSimulatorBackend, ProteusAdapter, WokwiAdapter, wrap_backend
from .storage import HybridStorage
from .hardware import (
    Capability,
    HardwareDevice,
    HardwarePin,
    HardwareProfile,
    ProfileRegistry,
    get_profile_registry,
)
from .transports import (
    HardwareTransport,
    MqttHardwareTransport,
    SerialHardwareTransport,
    SshHardwareTransport,
    TransportKind,
    create_transport,
)

# Sprint 30 wiring re-exports (optional import path)
from .wiring import (  # noqa: E402
    AutoMapper,
    PinConnection,
    PinValidator,
    WireManager,
    WiringEventType,
)

__all__ = [
    "DeviceAdapter",
    "DeviceAgent",
    "DeviceAssignment",
    "HybridBridgeService",
    "HybridDevice",
    "HybridDeviceMode",
    "HybridEventType",
    "HybridExperimentSession",
    "HybridExperimentStatus",
    "HybridMqttAdapter",
    "HybridRegistry",
    "HybridRouter",
    "HybridSerialAdapter",
    "HybridSimulatorAdapter",
    "HybridSimulatorBackend",
    "HybridStorage",
    "HybridVirtualAdapter",
    "HybridWifiAdapter",
    "HardwareDevice",
    "HardwarePin",
    "HardwareProfile",
    "HardwareTransport",
    "Capability",
    "MqttHardwareTransport",
    "PhysicalDevice",
    "PhysicalDeviceRegistry",
    "PhysicalESP32",
    "PhysicalHybridLayer",
    "PhysicalPin",
    "PinMapper",
    "ProfileRegistry",
    "ProteusAdapter",
    "SerialHardwareTransport",
    "SerialTransport",
    "SshHardwareTransport",
    "TransportKind",
    "AutoMapper",
    "PinConnection",
    "PinValidator",
    "WireManager",
    "WiringEventType",
    "create_transport",
    "get_profile_registry",
    "WokwiAdapter",
    "map_legacy_mode",
    "publish_hybrid_event",
    "wrap_backend",
]
