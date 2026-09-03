"""HHIP Component Engine v2 — Wokwi-style package definitions."""

from __future__ import annotations

from .behavior_registry import BehaviorRegistry, BaseBehavior, default_behavior_registry
from .component_definition import ComponentDefinition
from .component_registry import ComponentRegistryV2, default_registry_v2
from .events import COMPONENT_SIGNAL_CHANGED, publish_component_signal
from .hardware_binding import BindingMode, HardwareBinding, HardwareBindingStore
from .package_loader import PackageLoader, resolve_packages_dir
from .pin_model import PinDefinition, PinDirection, PinType, SUPPORTED_PIN_TYPES
from .renderer_registry import RendererRegistry
from .schema import MANIFEST_SCHEMA, validate_manifest_shape

__all__ = [
    "COMPONENT_SIGNAL_CHANGED",
    "BaseBehavior",
    "BehaviorRegistry",
    "BindingMode",
    "ComponentDefinition",
    "ComponentRegistryV2",
    "HardwareBinding",
    "HardwareBindingStore",
    "MANIFEST_SCHEMA",
    "PackageLoader",
    "PinDefinition",
    "PinDirection",
    "PinType",
    "RendererRegistry",
    "SUPPORTED_PIN_TYPES",
    "default_behavior_registry",
    "default_registry_v2",
    "publish_component_signal",
    "resolve_packages_dir",
    "validate_manifest_shape",
]
