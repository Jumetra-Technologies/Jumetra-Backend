"""Sign-in on a server without the Firebase service-account file (Render): FIREBASE_PROJECT_ID is enough."""

from __future__ import annotations

import firebase_admin
import pytest
from firebase_admin import auth as firebase_auth

from auth import firebase


@pytest.fixture
def no_app(monkeypatch, tmp_path):
    for app in list(firebase_admin._apps.values()):
        firebase_admin.delete_app(app)
    monkeypatch.setattr(firebase, "credential_path", lambda: tmp_path / "missing.json")
    monkeypatch.setattr(firebase, "load_auth_env", lambda: None)
    yield
    for app in list(firebase_admin._apps.values()):
        firebase_admin.delete_app(app)
    firebase._available = False


def test_without_a_project_id_sign_in_is_off(no_app, monkeypatch):
    monkeypatch.delenv("FIREBASE_PROJECT_ID", raising=False)
    assert firebase.init_firebase() is False
    with pytest.raises(firebase.FirebaseUnavailable):
        firebase.verify_id_token("anything")


def test_the_project_id_alone_turns_sign_in_on_and_bad_tokens_are_refused(no_app, monkeypatch):
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "hhipsystemv0")
    assert firebase.init_firebase() is True
    assert firebase_admin.get_app().project_id == "hhipsystemv0"
    with pytest.raises(firebase_auth.InvalidIdTokenError):  # refused for what it is, not for want of credentials
        firebase.verify_id_token("not-a-token")
