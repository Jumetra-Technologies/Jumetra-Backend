from __future__ import annotations

from pathlib import Path

import pytest

from engine.components.package_assets import PackageAssets


def make_package(root: Path, component_id: str = "esp32") -> Path:
    package = root / "controllers" / component_id
    (package / "assets").mkdir(parents=True)
    (package / "datasheets").mkdir()
    (package / "examples" / "blink").mkdir(parents=True)
    (package / "firmware").mkdir()
    (package / "libraries").mkdir()
    (package / "manifest.json").write_text("{}", encoding="utf-8")
    return package


@pytest.fixture
def package_assets(tmp_path: Path) -> tuple[PackageAssets, Path]:
    package = make_package(tmp_path)
    (package / "assets" / "board.svg").touch()
    (package / "assets" / "breadboard.svg").touch()
    (package / "assets" / "schematic.svg").touch()
    (package / "assets" / "icon.png").touch()
    (package / "assets" / "thumbnail.png").touch()
    (package / "datasheets" / "esp32.pdf").touch()
    (package / "firmware" / "blink.ino").touch()
    (package / "examples" / "blink" / "README.md").touch()
    (package / "libraries" / "arduino.json").touch()
    return PackageAssets(tmp_path), package


def test_named_asset_resolution(package_assets: tuple[PackageAssets, Path]) -> None:
    assets, package = package_assets

    assert assets.get_board_svg("esp32") == package / "assets" / "board.svg"
    assert assets.get_schematic_svg("esp32") == package / "assets" / "schematic.svg"
    assert assets.get_breadboard_svg("esp32") == package / "assets" / "breadboard.svg"
    assert assets.get_icon("esp32") == package / "assets" / "icon.png"
    assert assets.get_thumbnail("esp32") == package / "assets" / "thumbnail.png"


def test_package_asset_group_resolution(package_assets: tuple[PackageAssets, Path]) -> None:
    assets, package = package_assets

    assert assets.get_datasheet("esp32") == package / "datasheets" / "esp32.pdf"
    assert assets.get_firmware_templates("esp32") == package / "firmware" / "blink.ino"
    assert assets.get_examples("esp32") == package / "examples"
    assert assets.get_library_metadata("esp32") == package / "libraries" / "arduino.json"


def test_missing_asset_returns_none(package_assets: tuple[PackageAssets, Path]) -> None:
    assets, _ = package_assets
    assert assets.get_board_svg("missing") is None
    assert assets.get_datasheet("esp32") is not None


def test_invalid_package_returns_none(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid" / "assets"
    invalid.mkdir(parents=True)
    (invalid / "board.svg").touch()

    assert PackageAssets(tmp_path).get_board_svg("invalid") is None


def test_path_traversal_is_blocked(package_assets: tuple[PackageAssets, Path]) -> None:
    assets, _ = package_assets
    assert assets.get_board_svg("../esp32") is None
    assert assets.get_board_svg("esp32/../other") is None


def test_symlink_escape_is_blocked(package_assets: tuple[PackageAssets, Path], tmp_path: Path) -> None:
    assets, package = package_assets
    outside = tmp_path / "outside.svg"
    outside.touch()
    escaped = package / "assets" / "icon.png"
    try:
        escaped.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable in this environment")

    assert assets.get_icon("esp32") is None


def test_symlink_into_another_package_is_not_listed(
    package_assets: tuple[PackageAssets, Path], tmp_path: Path
) -> None:
    assets, package = package_assets
    other_package = make_package(tmp_path, "other")
    foreign_asset = other_package / "assets" / "foreign.svg"
    foreign_asset.touch()
    escaped = package / "assets" / "foreign.svg"
    try:
        escaped.symlink_to(foreign_asset)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable in this environment")

    assert escaped not in {item["path"] for item in assets.list_assets("esp32")}


def test_list_assets_returns_path_metadata(package_assets: tuple[PackageAssets, Path]) -> None:
    assets, package = package_assets
    listed = assets.list_assets("esp32")

    assert all(isinstance(item["path"], Path) for item in listed)
    assert {item["kind"] for item in listed} == {"asset", "datasheet", "examples", "firmware", "library"}
    assert {item["path"] for item in listed} >= {
        package / "assets" / "board.svg",
        package / "datasheets" / "esp32.pdf",
        package / "firmware" / "blink.ino",
        package / "libraries" / "arduino.json",
        package / "examples",
    }