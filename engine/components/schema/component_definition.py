"""Versioned, package-oriented component definition models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..models import ComponentSpec, PinRequirement


@dataclass
class Identity:
    id: str
    name: str
    version: str = "1.0.0"
    manufacturer: str = "Generic"
    description: str = ""
    category: str = "module"


@dataclass
class VoltageRange:
    minimum: float = 3.3
    maximum: float = 3.3


@dataclass
class PowerRequirements:
    voltage_range: VoltageRange = field(default_factory=VoltageRange)
    current_ma: float = 0.0


@dataclass
class Hardware:
    voltage_range: VoltageRange = field(default_factory=VoltageRange)
    power_requirements: PowerRequirements = field(default_factory=PowerRequirements)
    interfaces: list[str] = field(default_factory=list)


@dataclass
class PinDefinition:
    pin_number: str | int
    pin_name: str
    pin_type: str
    supported_modes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Simulation:
    behavior_model: str = ""
    simulation_supported: bool = False


@dataclass
class Rendering:
    asset_path: str = ""
    renderer_type: str = ""


@dataclass
class Firmware:
    supported_frameworks: list[str] = field(default_factory=list)
    drivers: list[str] = field(default_factory=list)


@dataclass
class Documentation:
    datasheet: str = ""
    examples: list[str] = field(default_factory=list)


@dataclass
class ComponentDefinition:
    identity: Identity
    hardware: Hardware = field(default_factory=Hardware)
    pins: list[PinDefinition] = field(default_factory=list)
    simulation: Simulation = field(default_factory=Simulation)
    rendering: Rendering = field(default_factory=Rendering)
    firmware: Firmware = field(default_factory=Firmware)
    documentation: Documentation = field(default_factory=Documentation)
    tags: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    compatible_controllers: list[str] = field(default_factory=list)

    @property
    def component_id(self) -> str:
        return self.identity.id

    @property
    def version(self) -> str:
        return self.identity.version

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_documents(
        cls,
        manifest: dict[str, Any],
        *,
        pins_document: Any = None,
        metadata: dict[str, Any] | None = None,
        firmware_document: dict[str, Any] | None = None,
    ) -> "ComponentDefinition":
        metadata = metadata or {}
        hardware_data = manifest.get("hardware") if isinstance(manifest.get("hardware"), dict) else {}
        voltage = manifest.get("voltage") or hardware_data.get("voltage_range") or {}
        if isinstance(voltage, list):
            voltage = {"min": voltage[0], "max": voltage[-1]} if voltage else {}
        minimum = float(voltage.get("min", voltage.get("minimum", 3.3)))
        maximum = float(voltage.get("max", voltage.get("maximum", minimum)))
        current = float(manifest.get("current_ma", hardware_data.get("current_ma", 0.0)))
        interfaces = [str(value) for value in manifest.get("interfaces", hardware_data.get("interfaces", []))]
        raw_pins = pins_document if isinstance(pins_document, list) else manifest.get("pins", [])
        pins = [
            PinDefinition(
                pin_number=pin.get("pin_number", pin.get("number", pin.get("id", index + 1))),
                pin_name=str(pin.get("pin_name", pin.get("name", pin.get("id", "")))),
                pin_type=str(pin.get("pin_type", pin.get("type", "GPIO"))).upper(),
                supported_modes=[str(mode) for mode in pin.get("supported_modes", pin.get("modes", []))],
            )
            for index, pin in enumerate(raw_pins)
            if isinstance(pin, dict)
        ]
        simulation_data = manifest.get("simulation") or {}
        rendering_data = manifest.get("rendering") or manifest.get("visual") or {}
        firmware_data = firmware_document or manifest.get("firmware") or {}
        docs = manifest.get("documentation") or {}
        return cls(
            identity=Identity(
                id=str(manifest.get("id") or manifest.get("component_id") or ""),
                name=str(manifest.get("name") or ""),
                version=str(manifest.get("version") or "1.0.0"),
                manufacturer=str(manifest.get("manufacturer") or "Generic"),
                description=str(manifest.get("description") or ""),
                category=str(manifest.get("category") or "module").lower(),
            ),
            hardware=Hardware(
                voltage_range=VoltageRange(minimum, maximum),
                power_requirements=PowerRequirements(VoltageRange(minimum, maximum), current),
                interfaces=interfaces,
            ),
            pins=pins,
            simulation=Simulation(
                behavior_model=str(simulation_data.get("behavior_model", simulation_data.get("model", ""))),
                simulation_supported=bool(simulation_data.get("simulation_supported", simulation_data.get("supported", False))),
            ),
            rendering=Rendering(
                asset_path=str(rendering_data.get("asset_path", rendering_data.get("asset", ""))),
                renderer_type=str(rendering_data.get("renderer_type", rendering_data.get("renderer", ""))),
            ),
            firmware=Firmware(
                supported_frameworks=[str(item) for item in firmware_data.get("supported_frameworks", firmware_data.get("frameworks", []))],
                drivers=[str(item) for item in firmware_data.get("drivers", [])],
            ),
            documentation=Documentation(
                datasheet=str(docs.get("datasheet", manifest.get("datasheet_url", ""))),
                examples=[str(item) for item in docs.get("examples", [])],
            ),
            tags=[str(item) for item in metadata.get("tags", manifest.get("tags", []))],
            keywords=[str(item) for item in metadata.get("keywords", manifest.get("keywords", []))],
            compatible_controllers=[str(item) for item in manifest.get("compatible_controllers", [])],
        )

    def to_spec(self) -> ComponentSpec:
        interface_aliases = {
            "gpio": "digital",
            "digital": "digital",
            "adc": "analog",
            "analog": "analog",
            "wifi": "wifi",
            "bluetooth": "bluetooth",
        }
        interfaces = list(dict.fromkeys(interface_aliases.get(value.lower(), value.lower()) for value in self.hardware.interfaces))
        return ComponentSpec(
            component_id=self.identity.id,
            name=self.identity.name,
            category=self.identity.category,
            description=self.identity.description,
            manufacturer=self.identity.manufacturer,
            interfaces=interfaces,
            voltage_v=self.hardware.voltage_range.maximum,
            current_ma=self.hardware.power_requirements.current_ma,
            pins=PinRequirement(
                count=len(self.pins) or 1,
                interfaces=interfaces[:3],
                notes=", ".join(pin.pin_name for pin in self.pins),
            ),
            tags=list(dict.fromkeys(self.tags + self.keywords)),
            datasheet_url=self.documentation.datasheet,
            version=self.identity.version,
        )


def component_definition_from_spec(spec: ComponentSpec) -> ComponentDefinition:
    voltage = VoltageRange(spec.voltage_v, spec.voltage_v)
    return ComponentDefinition(
        identity=Identity(spec.component_id, spec.name, spec.version, spec.manufacturer, spec.description, spec.category),
        hardware=Hardware(voltage, PowerRequirements(voltage, spec.current_ma), list(spec.interfaces)),
        pins=[PinDefinition(index + 1, name, "GPIO", []) for index, name in enumerate(spec.pins.interfaces)],
        documentation=Documentation(datasheet=spec.datasheet_url),
        tags=list(spec.tags),
    )