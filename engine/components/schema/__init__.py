"""Structured component definition schema."""

from .component_definition import (
    ComponentDefinition,
    Documentation,
    Firmware,
    Hardware,
    Identity,
    PinDefinition,
    Rendering,
    Simulation,
    component_definition_from_spec,
)

__all__ = [
    "ComponentDefinition",
    "Documentation",
    "Firmware",
    "Hardware",
    "Identity",
    "PinDefinition",
    "Rendering",
    "Simulation",
    "component_definition_from_spec",
]