"""Controller registry and compatibility engine."""

from __future__ import annotations

from typing import Optional

from engine.components.models import ComponentSpec

from .models import CompatibilityResult, ControllerSpec
from .seed import SEED_CONTROLLERS


class ControllerRegistry:
    """In-memory catalog of supported microcontrollers."""

    def __init__(self) -> None:
        self._controllers: dict[str, ControllerSpec] = {}

    def register(self, controller: ControllerSpec) -> None:
        self._controllers[controller.controller_id] = controller

    def get(self, controller_id: str) -> Optional[ControllerSpec]:
        return self._controllers.get(controller_id)

    def require(self, controller_id: str) -> ControllerSpec:
        ctrl = self.get(controller_id)
        if ctrl is None:
            raise KeyError(f"controller not found: {controller_id}")
        return ctrl

    def list_all(self) -> list[ControllerSpec]:
        return sorted(self._controllers.values(), key=lambda c: c.name)

    def load_seed(self) -> None:
        for controller in SEED_CONTROLLERS:
            self.register(controller)


class CompatibilityEngine:
    """Check whether a component can be used with a microcontroller."""

    def check(self, component: ComponentSpec, controller: ControllerSpec) -> CompatibilityResult:
        reasons: list[str] = []
        warnings: list[str] = []
        score = 1.0

        required_interfaces = set(i.lower() for i in component.interfaces)
        supported: set[str] = {"digital", "analog", "pwm", "uart"}
        if controller.supports_i2c:
            supported.add("i2c")
        if controller.supports_spi:
            supported.add("spi")
        if controller.supports_onewire:
            supported.add("onewire")

        missing = required_interfaces - supported
        if missing:
            return CompatibilityResult(
                component_id=component.component_id,
                controller_id=controller.controller_id,
                compatible=False,
                score=0.0,
                reasons=[f"Missing interfaces: {', '.join(sorted(missing))}"],
            )

        pin_count = component.pins.count if hasattr(component.pins, "count") else 1
        if "digital" in required_interfaces and controller.digital_pins < pin_count:
            return CompatibilityResult(
                component_id=component.component_id,
                controller_id=controller.controller_id,
                compatible=False,
                score=0.0,
                reasons=[f"Needs {pin_count} digital pins, board has {controller.digital_pins}"],
            )

        if "analog" in required_interfaces and controller.analog_pins < 1:
            return CompatibilityResult(
                component_id=component.component_id,
                controller_id=controller.controller_id,
                compatible=False,
                score=0.0,
                reasons=["Board lacks analog input pins"],
            )

        if "pwm" in required_interfaces and controller.pwm_pins < 1:
            warnings.append("Limited PWM pins — verify timer availability")

        if component.voltage_v > controller.voltage_v + 0.5:
            warnings.append(
                f"Component rated {component.voltage_v}V may need level shifting on {controller.voltage_v}V board"
            )
            score -= 0.1
        elif component.voltage_v <= controller.voltage_v:
            reasons.append(f"Voltage compatible ({component.voltage_v}V component on {controller.voltage_v}V board)")

        if controller.supports_wifi and "iot" in component.tags:
            reasons.append("Wi-Fi capable controller suits IoT sensor")
            score += 0.1

        reasons.append("All required interfaces supported")
        return CompatibilityResult(
            component_id=component.component_id,
            controller_id=controller.controller_id,
            compatible=True,
            score=min(1.0, max(0.5, score)),
            reasons=reasons,
            warnings=warnings,
        )

    def compatible_controllers(
        self, component: ComponentSpec, registry: ControllerRegistry
    ) -> list[CompatibilityResult]:
        results = [self.check(component, ctrl) for ctrl in registry.list_all()]
        return sorted(
            [r for r in results if r.compatible],
            key=lambda r: -r.score,
        )


def default_controller_registry() -> ControllerRegistry:
    registry = ControllerRegistry()
    registry.load_seed()
    return registry
