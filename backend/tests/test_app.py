"""HTTP tests (plan 3.7): /api/health and the web/dist serving rules."""

from __future__ import annotations

import time
from dataclasses import replace

from fastapi.testclient import TestClient

from bgsim_server.app import create_app


def test_health_reaches_ready_with_the_fake_worker(fake_settings) -> None:
    app = create_app(fake_settings)
    with TestClient(app) as client:
        deadline = time.monotonic() + 5.0
        payload = None
        while time.monotonic() < deadline:
            payload = client.get("/api/health").json()
            if payload["worker"] == "ready":
                break
            time.sleep(0.05)
        assert payload is not None
        assert payload["worker"] == "ready", "the fake must reach ready within about a second"
        assert payload["backend"] == "0.1.0"
        assert payload["versions"]["backend"] == "0.1.0"
        assert payload["versions"]["python"]
        assert payload["versions"]["julia"] == "fake"
        assert client.get("/api/health").status_code == 200


def test_root_is_json_when_the_web_app_is_not_built(fake_settings) -> None:
    with TestClient(create_app(fake_settings)) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        assert response.json()["health"] == "/api/health"
        assert client.get("/api/nope").status_code == 404


def test_root_serves_web_dist_with_spa_fallback(fake_settings, tmp_path) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>bg-sim</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('bg-sim')", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("top secret", encoding="utf-8")
    settings = replace(fake_settings, web_dist=dist)
    with TestClient(create_app(settings)) as client:
        index = client.get("/")
        assert index.status_code == 200 and "bg-sim" in index.text
        deep = client.get("/editor/some/model")
        assert deep.status_code == 200 and "bg-sim" in deep.text, "SPA fallback"
        asset = client.get("/assets/app.js")
        assert asset.status_code == 200 and "console.log" in asset.text
        assert client.get("/api/nope").status_code == 404, "the SPA fallback never shadows /api"
        escaped = client.get("/..%2Fsecret.txt")
        assert "top secret" not in escaped.text, "no path escapes out of web/dist"
