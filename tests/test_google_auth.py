from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import create_app


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-google-client-secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret")
    app = create_app(data_dir=tmp_path)
    return TestClient(app)


def test_google_login_redirects_to_google(monkeypatch, tmp_path):
    client = _client(tmp_path, monkeypatch)

    response = client.get("/auth/google/login", follow_redirects=False)

    assert response.status_code in {302, 307}
    location = response.headers["location"]
    assert "accounts.google.com" in location
    assert "client_id=test-google-client-id" in location
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fauth%2Fgoogle%2Fcallback" in location


def test_google_callback_returns_local_token(monkeypatch, tmp_path):
    client = _client(tmp_path, monkeypatch)

    def fake_post(url, data=None, headers=None, timeout=None):
        class FakeResponse:
            status_code = 200

            def json(self):
                return {
                    "access_token": "google-access-token",
                    "id_token": "google-id-token",
                    "token_type": "bearer",
                }

        return FakeResponse()

    def fake_verify(token, request, client_id):
        assert token == "google-id-token"
        assert client_id == "test-google-client-id"
        return {
            "sub": "google-user-123",
            "email": "alice@example.com",
            "name": "Alice Example",
            "picture": "https://example.com/avatar.png",
            "iss": "https://accounts.google.com",
            "aud": "test-google-client-id",
        }

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr("google.oauth2.id_token.verify_oauth2_token", fake_verify)

    response = client.get("/auth/google/callback?code=test-code")

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["email"] == "alice@example.com"
    assert payload["user"]["google_sub"] == "google-user-123"
    assert payload["token_type"] == "bearer"
    assert "access_token" in payload


def test_protected_user_route_requires_token(monkeypatch, tmp_path):
    client = _client(tmp_path, monkeypatch)

    response = client.get("/auth/me")

    assert response.status_code == 401
