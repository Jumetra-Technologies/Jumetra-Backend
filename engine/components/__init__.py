"""Hardware component intelligence layer."""

from .catalog_loader import json_doc_to_spec, load_json_specs
from .definitions import PinType
from .loader import ComponentLoader, load_components
from .models import ComponentCategory, ComponentSearchResult, ComponentSpec, InterfaceType, PinRequirement
from .registry import ComponentRegistry, ComponentSearch, default_registry
from .validator import ComponentValidator
from .search import ComponentIndex, ComponentSearchEngine, SearchFilters

__all__ = [
    "ComponentCategory",
    "ComponentIndex",
    "ComponentRegistry",
    "ComponentSearch",
    "ComponentSearchEngine",
    "ComponentSearchResult",
    "ComponentSpec",
    "InterfaceType",
    "PinRequirement",
    "PinType",
    "SearchFilters",
    "default_registry",
    "json_doc_to_spec",
    "load_json_specs",
    "ComponentLoader",
    "ComponentValidator",
    "load_components",
]
