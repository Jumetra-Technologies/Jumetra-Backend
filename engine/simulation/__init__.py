"""Virtual simulation and laboratory foundation."""

from .adapters import InProcessSimulatorAdapter, SimulatorAdapter
from .behaviors import VirtualActuator, VirtualComponentBehavior, VirtualSensor, create_behavior, list_supported_behaviors
from .circuit import CircuitGraph, CircuitValidator, Connection, ValidationResult
from .events import SimulationEventType, publish_simulation_event
from .factory import VirtualComponentFactory, VirtualComponentInstance
from .laboratory import VirtualLaboratoryService
from .runtime import EngineState, SimulationClock, SimulationEngine, SimulationScheduler
from .session import LaboratoryManager, SimulationSession, SimulationStatus, VirtualLaboratory
from .storage import LaboratoryStorage
from .virtual_controllers import VirtualESP32, VirtualMicrocontroller, create_virtual_controller

__all__ = [
    "CircuitGraph",
    "CircuitValidator",
    "Connection",
    "EngineState",
    "InProcessSimulatorAdapter",
    "LaboratoryManager",
    "LaboratoryStorage",
    "SimulationClock",
    "SimulationEngine",
    "SimulationEventType",
    "SimulationScheduler",
    "SimulationSession",
    "SimulationStatus",
    "SimulatorAdapter",
    "ValidationResult",
    "VirtualActuator",
    "VirtualComponentBehavior",
    "VirtualComponentFactory",
    "VirtualComponentInstance",
    "VirtualESP32",
    "VirtualLaboratory",
    "VirtualLaboratoryService",
    "VirtualMicrocontroller",
    "VirtualSensor",
    "create_behavior",
    "create_virtual_controller",
    "list_supported_behaviors",
    "publish_simulation_event",
]
