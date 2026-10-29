"""The model docs wiki (W5.6): manifest, pages, assets, limits, path safety, lifecycle."""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from bgsim_server import docs
from bgsim_server.app import create_app
from bgsim_server.projects import ProjectStore

REPO = Path(__file__).resolve().parents[2]
MODEL_FIXTURE = REPO / "contracts" / "fixtures" / "model" / "valid" / "model.dcmotor.bondgraph.json"
SCHEMAS = REPO / "contracts" / "schemas"


def _png(color: int = 0) -> bytes:
    """A valid 1x1 PNG whose pixel depends on ``color`` (so different calls hash differently)."""

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    raw = b"\x00" + bytes([color, 0, 0])
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def page(page_id: str, children: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "id": page_id,
        "title": page_id.title(),
        "file": f"pages/{page_id}.md",
        "children": children or [],
    }


def manifest(*pages: dict[str, Any]) -> dict[str, Any]:
    return {"format": "bgsim.docs", "version": 1, "pages": list(pages)}


@pytest.fixture
def client(fake_settings):
    with TestClient(create_app(fake_settings)) as test_client:
        assert test_client.post("/api/projects", json={"name": "demo"}).status_code == 201
        model = json.loads(MODEL_FIXTURE.read_text(encoding="utf-8"))
        for name in ("a", "b"):
            assert test_client.put(f"/api/projects/demo/models/{name}", json=model).status_code == 200
        yield test_client


def base(model: str = "a", project: str = "demo") -> str:
    return f"/api/projects/{project}/docs/{model}"


def docs_dir(fake_settings, model: str = "a") -> Path:
    return fake_settings.projects_root / "demo" / "models" / f"{model}.docs"


def upload(client, data: bytes, model: str = "a", name: str = "x.png"):
    return client.post(f"{base(model)}/assets", files={"file": (name, data, "image/png")})


# --------------------------------------------------------------------------- manifest


def test_model_without_docs_has_an_empty_tree(client, schema_validate) -> None:
    response = client.get(base())
    assert response.status_code == 200
    assert response.json() == manifest()
    schema_validate("docs", response.json())


def test_manifest_round_trip_is_stored_in_the_docs_folder(client, fake_settings) -> None:
    tree = manifest(page("overview", [page("plant")]), page("results"))
    assert client.put(base(), json=tree).status_code == 200
    assert client.get(base()).json() == tree
    stored = json.loads((docs_dir(fake_settings) / "docs.json").read_text(encoding="utf-8"))
    assert stored == tree
    assert client.get(base("b")).json() == manifest()  # docs belong to one model


@pytest.mark.parametrize(
    ("document", "needle"),
    [
        ({"format": "bgsim.docs", "version": 1}, "pages"),
        (manifest(page("Bad Id")), "does not match"),
        (manifest(page("a"), page("a")), "used twice"),
        (manifest({**page("a"), "file": "pages/other.md"}), "always"),
        (manifest({**page("a"), "file": "../a.md"}), "does not match"),
    ],
)
def test_invalid_manifest_is_rejected_with_a_reason(client, document, needle) -> None:
    response = client.put(base(), json=document)
    assert response.status_code == 422
    assert needle in json.dumps(response.json())


def test_manifest_depth_is_limited(client) -> None:
    deep = page("p0")
    node = deep
    for index in range(1, docs.MAX_DEPTH + 1):
        child = page(f"p{index}")
        node["children"].append(child)
        node = child
    response = client.put(base(), json=manifest(deep))
    assert response.status_code == 422
    assert "deeper" in json.dumps(response.json())


def test_unknown_model_and_project_are_404(client) -> None:
    assert client.get(base("nope")).status_code == 404
    assert client.get(base("a", "nope")).status_code == 404


# --------------------------------------------------------------------------- pages


def test_page_text_round_trip(client, fake_settings) -> None:
    client.put(base(), json=manifest(page("overview")))
    assert client.get(f"{base()}/pages/overview").text == ""  # not written yet
    text = "# Title\r\n\r\n$x^2$\r\n"
    response = client.put(f"{base()}/pages/overview", content=text.encode())
    assert response.status_code == 200
    got = client.get(f"{base()}/pages/overview")
    assert got.status_code == 200
    assert got.headers["content-type"].startswith("text/markdown")
    assert got.text == "# Title\n\n$x^2$\n"
    assert (docs_dir(fake_settings) / "pages" / "overview.md").read_bytes() == got.content


def test_page_must_be_in_the_tree_and_have_a_safe_id(client) -> None:
    missing = client.put(f"{base()}/pages/ghost", content=b"x")
    assert missing.status_code == 404
    assert "add it to the page tree" in missing.json()["detail"]
    for bad in ("Bad", "..%2F..%2Fx", "a.b", "-x", "x" * 65):
        response = client.get(f"{base()}/pages/{bad}")
        assert response.status_code in (400, 404), bad


def test_page_size_limit(client, monkeypatch) -> None:
    client.put(base(), json=manifest(page("big")))
    monkeypatch.setattr(docs, "MAX_PAGE_BYTES", 10)
    response = client.put(f"{base()}/pages/big", content=b"x" * 11)
    assert response.status_code == 413
    assert "Split the page" in response.json()["detail"]


def test_page_must_be_utf8(client) -> None:
    client.put(base(), json=manifest(page("p")))
    assert client.put(f"{base()}/pages/p", content=b"\xff\xfe\x00").status_code == 400


def test_delete_leaf_removes_file_and_entry(client, fake_settings) -> None:
    client.put(base(), json=manifest(page("a1"), page("a2")))
    client.put(f"{base()}/pages/a1", content=b"one")
    response = client.delete(f"{base()}/pages/a1")
    assert response.status_code == 200
    assert response.json()["removed"] == ["a1"]
    assert [p["id"] for p in client.get(base()).json()["pages"]] == ["a2"]
    assert not (docs_dir(fake_settings) / "pages" / "a1.md").exists()
    assert client.delete(f"{base()}/pages/a1").status_code == 404


def test_delete_with_children_needs_a_choice(client, fake_settings) -> None:
    tree = manifest(page("root", [page("kid1"), page("kid2", [page("grand")])]), page("other"))
    client.put(base(), json=tree)
    for pid in ("root", "kid1", "kid2", "grand"):
        client.put(f"{base()}/pages/{pid}", content=pid.encode())

    refused = client.delete(f"{base()}/pages/root")
    assert refused.status_code == 409
    assert "children=delete" in refused.json()["detail"]

    promoted = client.delete(f"{base()}/pages/root?children=promote")
    assert promoted.status_code == 200
    ids = [p["id"] for p in client.get(base()).json()["pages"]]
    assert ids == ["kid1", "kid2", "other"]
    assert not (docs_dir(fake_settings) / "pages" / "root.md").exists()
    assert (docs_dir(fake_settings) / "pages" / "grand.md").exists()

    removed = client.delete(f"{base()}/pages/kid2?children=delete").json()["removed"]
    assert removed == ["kid2", "grand"]
    assert not (docs_dir(fake_settings) / "pages" / "grand.md").exists()
    assert (docs_dir(fake_settings) / "pages" / "kid1.md").exists()


# --------------------------------------------------------------------------- assets


def test_upload_names_by_content_hash_and_dedupes(client, fake_settings) -> None:
    data = _png(1)
    first = upload(client, data)
    assert first.status_code == 201
    body = first.json()
    assert body["file"] == f"{hashlib.sha256(data).hexdigest()[:12]}.png"
    assert body["path"] == f"assets/{body['file']}"
    assert body["existed"] is False

    second = upload(client, data, name="other-name.png")
    assert second.status_code == 200
    assert second.json()["file"] == body["file"]
    assert second.json()["existed"] is True
    assert len(list((docs_dir(fake_settings) / "assets").iterdir())) == 1
    assert upload(client, _png(2)).json()["file"] != body["file"]


def test_asset_is_served_with_a_safe_content_type_and_csp(client) -> None:
    name = upload(client, _png(3)).json()["file"]
    response = client.get(f"{base()}/assets/{name}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in response.headers["content-security-policy"]
    assert response.content == _png(3)


def test_type_is_judged_by_bytes_not_by_name(client) -> None:
    disguised = client.post(
        f"{base()}/assets", files={"file": ("evil.png", b"<html>hi</html>", "image/png")}
    )
    assert disguised.status_code == 415
    assert "PNG, JPEG, GIF, WebP or SVG" in disguised.json()["detail"]
    jpeg = upload(client, b"\xff\xd8\xff\xe0" + b"0" * 20, name="photo.dat")
    assert jpeg.json()["file"].endswith(".jpg")
    gif = upload(client, b"GIF89a" + b"0" * 20)
    assert gif.json()["file"].endswith(".gif")
    webp = upload(client, b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"0" * 20)
    assert webp.json()["file"].endswith(".webp")


def test_svg_is_accepted_but_script_is_refused(client) -> None:
    good = (
        b'<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4">'
        b'<rect width="4" height="4"/></svg>'
    )
    ok = upload(client, good)
    assert ok.status_code == 201
    assert ok.json()["file"].endswith(".svg")
    served = client.get(f"{base()}/assets/{ok.json()['file']}")
    assert served.headers["content-type"] == "image/svg+xml"
    for evil in (
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg" onload="x()"></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><a href="javascript:x()"><rect/></a></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><foreignObject/></svg>',
    ):
        refused = upload(client, evil)
        assert refused.status_code == 422, evil
        assert "could run script" in refused.json()["detail"]


def test_image_size_limit_and_empty_upload(client, monkeypatch) -> None:
    monkeypatch.setattr(docs, "MAX_IMAGE_BYTES", 100)
    big = _png(4) + b"0" * 200
    response = upload(client, big)
    assert response.status_code == 413
    assert "larger than" in response.json()["detail"]
    assert upload(client, b"").status_code == 400


def test_upload_needs_multipart_with_a_file_field(client) -> None:
    assert client.post(f"{base()}/assets", content=b"x").status_code == 415
    other = client.post(f"{base()}/assets", files={"image": ("a.png", _png(), "image/png")})
    assert other.status_code == 400


def test_asset_names_are_strict(client) -> None:
    for bad in ("x.png", "..%2Fdocs.json", "0123456789ab.exe", "0123456789ABCDEF.png"):
        assert client.get(f"{base()}/assets/{bad}").status_code in (400, 404), bad
    assert client.get(f"{base()}/assets/0123456789ab.png").status_code == 404


def test_copy_assets_between_models(client, fake_settings) -> None:
    name = upload(client, _png(5), model="a").json()["file"]
    ghost = "ffffffffffff.png"
    request = {"fromProject": "demo", "fromModel": "a", "files": [name, ghost, name]}
    response = client.post(f"{base('b')}/assets/copy", json=request)
    assert response.status_code == 200
    assert response.json() == {"copied": [name], "existing": [], "missing": [ghost]}
    assert (docs_dir(fake_settings, "b") / "assets" / name).read_bytes() == _png(5)
    assert client.get(f"{base('b')}/assets/{name}").status_code == 200

    again = client.post(f"{base('b')}/assets/copy", json=request).json()
    assert again == {"copied": [], "existing": [name], "missing": [ghost]}


def test_copy_assets_validates_input(client) -> None:
    url = f"{base('b')}/assets/copy"
    assert client.post(url, json={"files": []}).status_code == 422
    traversal = {"fromProject": "demo", "fromModel": "a", "files": ["../../x.png"]}
    assert client.post(url, json=traversal).status_code == 400
    unknown = {"fromProject": "demo", "fromModel": "zzz", "files": []}
    assert client.post(url, json=unknown).status_code == 404
    escape = {"fromProject": "..", "fromModel": "a", "files": []}
    assert client.post(url, json=escape).status_code in (400, 404)


def test_unused_assets_are_listed_and_cleaned_up(client, fake_settings) -> None:
    used = upload(client, _png(6)).json()["file"]
    unused = upload(client, _png(7)).json()["file"]
    client.put(base(), json=manifest(page("p")))
    client.put(f"{base()}/pages/p", content=f"![](assets/{used})\n".encode())

    listing = client.get(f"{base()}/assets").json()
    assert listing["unused"] == 1
    assert {a["file"]: a["used"] for a in listing["assets"]} == {used: True, unused: False}

    response = client.delete(f"{base()}/assets/unused")
    assert response.json() == {"deleted": [unused], "kept": 1}
    assert (docs_dir(fake_settings) / "assets" / used).exists()
    assert not (docs_dir(fake_settings) / "assets" / unused).exists()
    assert client.get(f"{base()}/assets").json()["unused"] == 0


# --------------------------------------------------------------------------- lifecycle


def test_model_delete_removes_the_docs_folder(client, fake_settings) -> None:
    client.put(base(), json=manifest(page("p")))
    upload(client, _png(8))
    assert docs_dir(fake_settings).is_dir()
    assert client.delete("/api/projects/demo/models/a").status_code == 204
    assert not docs_dir(fake_settings).exists()
    assert docs_dir(fake_settings, "b").parent.is_dir()
    assert client.get(base()).status_code == 404


def test_docs_folder_is_not_listed_as_a_model(client) -> None:
    client.put(base(), json=manifest(page("p")))
    listing = client.get("/api/projects/demo").json()
    assert sorted(m["name"] for m in listing["models"]) == ["a", "b"]


def test_project_from_example_carries_the_docs(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "projects", tmp_path / "examples", SCHEMAS)
    models = tmp_path / "examples" / "sample" / "models"
    models.mkdir(parents=True)
    fixture = MODEL_FIXTURE.read_text(encoding="utf-8")
    (models / "m.bgmodel.json").write_text(fixture, encoding="utf-8")
    source = models / "m.docs"
    (source / "pages").mkdir(parents=True)
    (source / "assets").mkdir()
    (source / "docs.json").write_text(json.dumps(manifest(page("intro"))), encoding="utf-8")
    (source / "pages" / "intro.md").write_text("hello\n", encoding="utf-8")
    name = docs.asset_name_for(_png(9), "png")
    (source / "assets" / name).write_bytes(_png(9))

    store.create_project("copy", example="sample")
    copied = tmp_path / "projects" / "copy" / "models" / "m.docs"
    stored = json.loads((copied / "docs.json").read_text(encoding="utf-8"))
    assert stored["pages"][0]["id"] == "intro"
    assert (copied / "pages" / "intro.md").read_text(encoding="utf-8") == "hello\n"
    assert (copied / "assets" / name).read_bytes() == _png(9)


def test_docs_folder_that_is_a_file_is_refused(client, fake_settings) -> None:
    blocker = fake_settings.projects_root / "demo" / "models" / "a.docs"
    blocker.write_text("x", encoding="utf-8")
    assert client.get(base()).status_code == 400
