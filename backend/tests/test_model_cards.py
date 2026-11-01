"""The model picker cards (GET /api/projects/{p}/models): description, thumbnail, miniature."""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from bgsim_server.app import create_app
from bgsim_server.model_cards import DESCRIPTION_LIMIT, first_paragraph

REPO = Path(__file__).resolve().parents[2]
MODEL_FIXTURE = REPO / "contracts" / "fixtures" / "model" / "valid" / "model.dcmotor.bondgraph.json"


def _png() -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
        + chunk(b"IEND", b"")
    )


def _model(comment: str | None = None) -> dict[str, Any]:
    model = json.loads(MODEL_FIXTURE.read_text(encoding="utf-8"))
    model.pop("$comment", None)
    if comment is not None:
        model["$comment"] = comment
    return model


@pytest.fixture
def client(fake_settings):
    with TestClient(create_app(fake_settings)) as test_client:
        assert test_client.post("/api/projects", json={"name": "demo"}).status_code == 201
        yield test_client


def _cards(client: TestClient) -> dict[str, dict[str, Any]]:
    answer = client.get("/api/projects/demo/models")
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["name"] == "demo"
    return {card["name"]: card for card in body["models"]}


def test_a_card_per_model_with_comment_counts_and_miniature(client):
    assert client.put("/api/projects/demo/models/a", json=_model("Plan 9.1: a DC motor.")).status_code == 200
    assert client.put("/api/projects/demo/models/b", json=_model()).status_code == 200

    cards = _cards(client)
    assert list(cards) == ["a", "b"]
    a = cards["a"]
    assert a["description"] == "Plan 9.1: a DC motor."
    assert a["thumbnail"] is None
    assert a["error"] is None
    assert a["inProject"] is True
    model = _model()
    assert a["nodes"] == len(model["diagram"]["nodes"])
    assert len(a["preview"]["nodes"]) == a["nodes"]
    assert all(kind in {"b", "j", "s"} for _, _, kind in a["preview"]["nodes"])
    assert len(a["preview"]["links"]) == len(model["diagram"]["connections"])
    for start, end, kind in a["preview"]["links"]:
        assert 0 <= start < a["nodes"] and 0 <= end < a["nodes"]
        assert kind in {"b", "w", "s"}
    assert cards["b"]["description"] is None


def test_docs_give_the_thumbnail_and_the_fallback_description(client, fake_settings):
    assert client.put("/api/projects/demo/models/a", json=_model()).status_code == 200
    manifest = {
        "format": "bgsim.docs",
        "version": 1,
        "pages": [{"id": "overview", "title": "Overview", "file": "pages/overview.md", "children": []}],
    }
    assert client.put("/api/projects/demo/docs/a", json=manifest).status_code == 200
    upload = client.post(
        "/api/projects/demo/docs/a/assets", files={"file": ("x.png", _png(), "image/png")}
    )
    assert upload.status_code in (200, 201), upload.text
    asset = upload.json()["file"]
    page = (
        "# Title\n\n![The diagram|800](assets/000000000000.png)\n\n"
        f"![Diagram](assets/{asset})\n\n"
        "A **DC motor** with a [voltage source](block:V1) and `R`.\nSecond line.\n\n"
        "## More\n\nNot this one.\n"
    )
    assert client.put(
        "/api/projects/demo/docs/a/pages/overview",
        content=page.encode(),
        headers={"content-type": "text/markdown"},
    ).status_code == 200

    card = _cards(client)["a"]
    # The first image that exists (the missing one is skipped).
    assert card["thumbnail"] == asset
    assert card["description"] == "A DC motor with a voltage source and R. Second line."


def test_the_comment_wins_over_the_docs_and_long_text_is_cut(client):
    long = "word " * 400
    assert client.put("/api/projects/demo/models/a", json=_model(long)).status_code == 200
    card = _cards(client)["a"]
    assert card["description"].endswith("…")
    assert len(card["description"]) <= DESCRIPTION_LIMIT + 1


def test_a_broken_model_file_still_gets_a_card(client, fake_settings):
    assert client.put("/api/projects/demo/models/a", json=_model()).status_code == 200
    path = Path(fake_settings.projects_root) / "demo" / "models" / "a.bgmodel.json"
    path.write_text("{ not json", encoding="utf-8")
    card = _cards(client)["a"]
    assert card["error"] is not None
    assert card["nodes"] == 0


def test_unknown_project_is_404(client):
    assert client.get("/api/projects/nope/models").status_code == 404


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("# Only a heading\n", None),
        ("```\ncode\n```\n\nText after code.", "Text after code."),
        ("- a list\n\n1. numbered\n\n> quote\n\nProse at last.", "Prose at last."),
        ("Line one\nline two\n\nNext paragraph", "Line one line two"),
    ],
)
def test_first_paragraph(markdown, expected):
    assert first_paragraph(markdown) == expected
