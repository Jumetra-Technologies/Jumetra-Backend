"""Hardware component intelligence layer."""

from .catalog_loader import json_doc_to_spec, load_json_specs
from .models import ComponentCategory, ComponentSearchResult, ComponentSpec, InterfaceType, PinRequirement
from .registry import ComponentRegistry, ComponentSearch, default_registry
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
    "SearchFilters",
    "default_registry",
    "json_doc_to_spec",
    "load_json_specs",
]
