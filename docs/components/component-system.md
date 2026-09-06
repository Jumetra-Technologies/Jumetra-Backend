# HHIP Component Package System

Sprint 32 introduces declarative component packages. The existing catalogs remain available during migration; this registry does not execute package code.

## Package layout

Place a package under `components/community/<category>/<component-id>/` with `component.json`, `manifest.json`, `pins.json`, `renderer.svg`, `icon.png`, and `README.md`. Datasheets, examples, and firmware are optional. A package is discovered at the `component.json` file, so categories can be nested freely.

`component.json` describes searchable metadata and references `pins.json`. `manifest.json` provides package identity, semantic version, engine compatibility, and trust level. Pin definitions are completely declarative—no pin list belongs in the registry code.

## Security model

Official packages require a matching `checksum.sha256`, calculated across all package files except that checksum file. Community and local packages require schema validation. Marketplace packages are intentionally not auto-loaded until signature and publisher verification exist. Invalid packages are rejected and reported by `registry.rejected`.

## Workflow

`ComponentRegistry` checks its cache, otherwise `ComponentDiscovery` scans official, community, and marketplace roots. It validates JSON schemas, verifies trust/checksums, then registers metadata for filtered search. The cache at `components/cache/registry.json` stores validated metadata and is invalidated automatically when package files become newer.

## Adding a component

Create the package files, use an `id` matching `^[a-z0-9][a-z0-9-]*$`, provide at least one valid pin, then restart HHIP or call `registry.reload()`. The component will be available through `get`, `list_all`, and `search` without a Python code change.

## Marketplace future

The package format deliberately separates metadata from code. A future marketplace can add signed manifests, publisher identities, review status, and optional behavior sandboxes without changing the registry API.
