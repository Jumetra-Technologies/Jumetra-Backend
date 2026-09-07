from engine.components.security import ComponentSecurityScanner, SecurityViolation


def test_security_rejects_oversized_files(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text("x" * (1024 * 1024 + 1), encoding="utf-8")
    try:
        ComponentSecurityScanner().validate_path(tmp_path, path)
        assert False
    except SecurityViolation:
        pass


def test_security_rejects_invalid_extensions(tmp_path):
    path = tmp_path / "run.py"
    path.write_text("print('no')", encoding="utf-8")
    try:
        ComponentSecurityScanner().validate_path(tmp_path, path)
        assert False
    except SecurityViolation:
        pass


def test_security_rejects_executable_metadata(tmp_path):
    path = tmp_path / "metadata.json"
    path.write_text('{"script": "run.sh"}', encoding="utf-8")
    try:
        ComponentSecurityScanner().read_json(tmp_path, path)
        assert False
    except SecurityViolation:
        pass