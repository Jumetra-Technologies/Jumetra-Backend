from engine.component_registry import ComponentDiscovery
from component_package_helpers import make_package

def test_official_checksum_accepts_then_rejects_modification(tmp_path):
    package = make_package(tmp_path, source="official")
    assert len(ComponentDiscovery(tmp_path).scan()) == 1
    (package / "renderer.svg").write_text("<svg>changed</svg>", encoding="utf-8")
    discovery = ComponentDiscovery(tmp_path)
    assert discovery.scan() == []
    assert "checksum" in discovery.last_rejected[0]["reason"]

def test_invalid_manifest_is_rejected(tmp_path):
    package = make_package(tmp_path)
    (package / "manifest.json").write_text("{}", encoding="utf-8")
    assert ComponentDiscovery(tmp_path).scan() == []
