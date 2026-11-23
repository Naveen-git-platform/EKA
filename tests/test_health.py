from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app


def test_health_ok(settings):
    client = TestClient(create_app(settings))
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"
    assert body["llm_provider"] == "fake"


def test_app_factory_uses_given_settings(settings):
    app = create_app(settings)
    assert app.state.settings is settings
    assert app.title == settings.app_name


def test_dependency_override_works(settings):
    app = create_app(settings)
    custom = Settings(_env_file=None, app_env="overridden", llm_provider="fake")
    app.dependency_overrides[get_settings] = lambda: custom
    r = TestClient(app).get("/health")
    assert r.json()["environment"] == "overridden"


def test_unknown_route_404(settings):
    assert TestClient(create_app(settings)).get("/nope").status_code == 404


def test_openapi_lists_health(settings):
    r = TestClient(create_app(settings)).get("/openapi.json")
    assert "/health" in r.json()["paths"]
