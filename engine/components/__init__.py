"""Hardware component intelligence layer."""

from .catalog_loader import json_doc_to_spec, load_json_specs
from .definitions import PinType
from .loader import ComponentLoader, load_components
from .package_loader import ComponentPackageLoader, LoadedComponentPackage, load_component_packages
from .package_assets import AssetMetadata, PackageAssets
from .resolution import ComponentResolver
from .models import ComponentCategory, ComponentSearchResult, ComponentSpec, InterfaceType, PinRequirement
from .registry import ComponentRegistry, ComponentSearch, default_registry
from .validator import ComponentValidator
from .versioning import ComponentVersion, resolve_latest, versioned_id
from .search import ComponentIndex, ComponentSearchEngine, SearchFilters
from .search_index import ComponentSearchIndex

__all__ = [
    "ComponentCategory",
    "ComponentIndex",
    "ComponentRegistry",
    "ComponentSearch",
    "ComponentSearchEngine",
    "ComponentSearchIndex",
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
    "ComponentPackageLoader",
    "LoadedComponentPackage",
    "load_component_packages",
    "AssetMetadata",
    "PackageAssets",
    "ComponentResolver",
    "ComponentVersion",
    "resolve_latest",
    "versioned_id",
    "load_components",
]
