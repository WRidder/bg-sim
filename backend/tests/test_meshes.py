"""Scenes and mesh upload (P5.1): SDF files, STL/OBJ/DAE/GLB to GLB conversion."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
import trimesh
from fastapi.testclient import TestClient

from bgsim_server import meshes
from bgsim_server.app import create_app
from bgsim_server.projects import ProjectStore

REPO = Path(__file__).resolve().parents[2]

SDF = """<?xml version="1.0"?>
<sdf version="1.9">
  <model name="m"><link name="base"/></model>
</sdf>
"""

DAE = """<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
<asset><up_axis>Z_UP</up_axis></asset>
<library_geometries><geometry id="g" name="g"><mesh>
<source id="p"><float_array id="pa" count="9">0 0 0 1 0 0 0 1 0</float_array>
<technique_common><accessor source="#pa" count="3" stride="3"><param name="X" type="float"/>
<param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>
<vertices id="v"><input semantic="POSITION" source="#p"/></vertices>
<triangles count="1"><input semantic="VERTEX" source="#v" offset="0"/><p>0 1 2</p></triangles>
</mesh></geometry></library_geometries>
<library_visual_scenes><visual_scene id="s"><node id="n"><instance_geometry url="#g"/></node>
</visual_scene></library_visual_scenes>
<scene><instance_visual_scene url="#s"/></scene></COLLADA>
"""


@pytest.fixture
def client(fake_settings):
    with TestClient(create_app(fake_settings)) as test_client:
        assert test_client.post("/api/projects", json={"name": "demo"}).status_code == 201
        yield test_client


def _project_dir(fake_settings) -> Path:
    return fake_settings.projects_root / "demo"


def _upload(client, name: str, data: bytes, project: str = "demo"):
    return client.post(
        f"/api/projects/{project}/meshes", files={"file": (name, data, "application/octet-stream")}
    )


def _box(extent=(1.0, 2.0, 3.0)) -> trimesh.Trimesh:
    return trimesh.creation.box(extents=extent)


def _load_glb(data: bytes) -> trimesh.Trimesh:
    assert data[:4] == b"glTF", "a GLB starts with the glTF magic"
    assert int.from_bytes(data[4:8], "little") == 2, "glTF version 2"
    assert int.from_bytes(data[8:12], "little") == len(data), "the GLB header length matches"
    loaded = trimesh.load(io.BytesIO(data), file_type="glb", force="mesh")
    assert isinstance(loaded, trimesh.Trimesh)
    return loaded


# --------------------------------------------------------------------------- scenes


def test_scene_put_then_get_round_trips_with_lf(client, fake_settings) -> None:
    response = client.put(
        "/api/projects/demo/scenes/robot.sdf", content=SDF.replace("\n", "\r\n").encode()
    )
    assert response.status_code == 200, response.text
    assert response.json()["path"] == "scenes/robot.sdf"
    stored = (_project_dir(fake_settings) / "scenes" / "robot.sdf").read_bytes()
    assert stored == SDF.encode()
    assert b"\r" not in stored
    got = client.get("/api/projects/demo/scenes/robot.sdf")
    assert got.status_code == 200
    assert got.text == SDF
    assert got.headers["content-type"].startswith("application/xml")
    assert not list((_project_dir(fake_settings) / "scenes").glob(".*.tmp")), "temp file cleaned"


def test_scene_put_replaces_atomically(client, fake_settings) -> None:
    client.put("/api/projects/demo/scenes/a.sdf", content=b"<sdf>1</sdf>")
    client.put("/api/projects/demo/scenes/a.sdf", content=b"<sdf>2</sdf>")
    assert client.get("/api/projects/demo/scenes/a.sdf").text == "<sdf>2</sdf>\n"


def test_scene_follows_the_scenes_dir_of_the_project_file(client, fake_settings) -> None:
    project_file = _project_dir(fake_settings) / "bgsim.project.json"
    document = json.loads(project_file.read_text(encoding="utf-8"))
    document["scenesDir"] = "worlds"
    project_file.write_text(json.dumps(document), encoding="utf-8")
    assert client.put("/api/projects/demo/scenes/w.sdf", content=SDF.encode()).status_code == 200
    assert (_project_dir(fake_settings) / "worlds" / "w.sdf").is_file()


def test_unknown_scene_and_project_are_404(client) -> None:
    assert client.get("/api/projects/demo/scenes/none.sdf").status_code == 404
    assert client.get("/api/projects/ghost/scenes/a.sdf").status_code == 404
    assert client.put("/api/projects/ghost/scenes/a.sdf", content=SDF.encode()).status_code == 404


@pytest.mark.parametrize(
    "name",
    [
        "..%2F..%2Fsecret.sdf",
        "%2e%2e%2fsecret.sdf",
        "..%5Csecret.sdf",
        "a%5Cb.sdf",
        "C%3A%5Cx.sdf",
        "..sdf.",
        ".hidden.sdf",
        "scene.txt",
        "scene",
        ".sdf",
        "NUL.sdf",
        "a%00b.sdf",
    ],
)
def test_scene_names_that_could_escape_are_rejected(client, fake_settings, name) -> None:
    got = client.get(f"/api/projects/demo/scenes/{name}")
    put = client.put(f"/api/projects/demo/scenes/{name}", content=SDF.encode())
    assert got.status_code in {400, 404}
    assert put.status_code in {400, 404, 405}  # 405: the encoded slash never routes
    projects = fake_settings.projects_root
    assert not (projects / "secret.sdf").exists()
    assert not (_project_dir(fake_settings) / "secret.sdf").exists()
    assert [p.name for p in (_project_dir(fake_settings) / "scenes").iterdir()] == []


def test_scene_body_errors_say_what_to_do(client) -> None:
    assert client.put("/api/projects/demo/scenes/e.sdf", content=b"   \n").status_code == 400
    bad = client.put("/api/projects/demo/scenes/e.sdf", content=b"\xff\xfe\x00")
    assert bad.status_code == 400
    assert "UTF-8" in bad.json()["detail"]
    too_big = client.put(
        "/api/projects/demo/scenes/e.sdf", content=b"x" * (meshes.MAX_SCENE_BYTES + 1)
    )
    assert too_big.status_code == 413


# --------------------------------------------------------------------------- meshes


def test_stl_upload_becomes_a_valid_glb(client, fake_settings) -> None:
    box = _box()
    stl = box.export(file_type="stl")
    response = _upload(client, "My Arm (v2).STL", stl)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["path"] == "meshes/My_Arm__v2.glb"
    assert body["vertices"] == len(box.vertices) == 8
    assert body["faces"] == len(box.faces) == 12
    stored = (_project_dir(fake_settings) / body["path"]).read_bytes()
    assert body["bytes"] == len(stored)
    mesh = _load_glb(stored)
    assert len(mesh.vertices) == 8
    assert len(mesh.faces) == 12
    assert mesh.extents == pytest.approx([1.0, 2.0, 3.0], abs=1e-5)
    # the stored GLB is served back as model/gltf-binary
    served = client.get(f"/api/projects/demo/{body['path']}")
    assert served.status_code == 200
    assert served.headers["content-type"] == "model/gltf-binary"
    assert served.content == stored


def test_stl_with_many_faces_keeps_its_counts(client, fake_settings) -> None:
    sphere = trimesh.creation.icosphere(subdivisions=3, radius=0.5)
    response = _upload(client, "ball.stl", sphere.export(file_type="stl"))
    assert response.status_code == 201, response.text
    mesh = _load_glb((_project_dir(fake_settings) / "meshes" / "ball.glb").read_bytes())
    assert len(mesh.faces) == len(sphere.faces) == 1280
    assert len(mesh.vertices) == len(sphere.vertices)


def test_obj_dae_and_glb_uploads(client, fake_settings) -> None:
    box = _box((1, 1, 1))
    obj = _upload(client, "box.obj", box.export(file_type="obj").encode())
    assert obj.status_code == 201, obj.text
    assert obj.json()["faces"] == 12
    dae = _upload(client, "tri.dae", DAE.encode())
    assert dae.status_code == 201, dae.text
    assert (dae.json()["vertices"], dae.json()["faces"]) == (3, 1)
    glb = _upload(client, "cyl.glb", trimesh.creation.cylinder(0.5, 2.0).export(file_type="glb"))
    assert glb.status_code == 201, glb.text
    for name in ("box", "tri", "cyl"):
        stored = (_project_dir(fake_settings) / "meshes" / f"{name}.glb").read_bytes()
        assert stored[:4] == b"glTF"
        assert len(_load_glb(stored).faces) > 0


def test_upload_replaces_a_mesh_of_the_same_name(client, fake_settings) -> None:
    _upload(client, "part.stl", _box((1, 1, 1)).export(file_type="stl"))
    again = _upload(client, "part.stl", trimesh.creation.icosphere().export(file_type="stl"))
    assert again.json()["faces"] == 1280
    mesh = _load_glb((_project_dir(fake_settings) / "meshes" / "part.glb").read_bytes())
    assert len(mesh.faces) == 1280


def test_upload_errors_say_what_to_do(client, fake_settings) -> None:
    unsupported = _upload(client, "model.step", b"ISO-10303")
    assert unsupported.status_code == 415
    assert ".stl" in unsupported.json()["detail"]
    assert _upload(client, "noext", b"x").status_code == 415
    empty = _upload(client, "e.stl", b"")
    assert empty.status_code == 400
    garbage = _upload(client, "g.stl", b"this is not a mesh at all")
    assert garbage.status_code == 422
    assert "upload again" in garbage.json()["detail"]
    points = _upload(client, "pts.obj", b"v 0 0 0\nv 1 0 0\n")
    assert points.status_code == 422
    assert "no triangle mesh" in points.json()["detail"]
    nameless = _upload(client, "...stl", _box().export(file_type="stl"))
    assert nameless.status_code == 400
    assert _upload(client, "a.stl", b"x", project="ghost").status_code == 404
    not_multipart = client.post("/api/projects/demo/meshes", content=b"x")
    assert not_multipart.status_code == 415
    no_file = client.post("/api/projects/demo/meshes", data={"other": "1"})
    assert no_file.status_code in {400, 415}
    assert not list((_project_dir(fake_settings) / "meshes").glob("*")), "nothing stored on error"


def test_upload_size_limit(client, fake_settings, monkeypatch) -> None:
    monkeypatch.setattr(meshes, "MAX_UPLOAD_BYTES", 100)
    response = _upload(client, "big.stl", _box().export(file_type="stl"))
    assert response.status_code == 413
    assert "decimate" in response.json()["detail"]


def test_upload_names_never_escape_the_meshes_dir(client, fake_settings) -> None:
    stl = _box().export(file_type="stl")
    response = _upload(client, "..\\..\\evil/../x.stl", stl)
    assert response.status_code == 201
    assert response.json()["path"] == "meshes/x.glb"
    assert not (_project_dir(fake_settings) / "x.glb").exists()


@pytest.mark.parametrize("name", ["..%2Fa.glb", "a%5Cb.glb", "a.stl", ".glb", "none.glb"])
def test_mesh_get_rejects_bad_names(client, name) -> None:
    assert client.get(f"/api/projects/demo/meshes/{name}").status_code in {400, 404}


# --------------------------------------------------------------------------- examples


def test_project_from_an_example_copies_scenes_and_meshes(tmp_path) -> None:
    examples = tmp_path / "examples"
    source = examples / "arm"
    (source / "scenes").mkdir(parents=True)
    (source / "meshes").mkdir()
    (source / "scenes" / "arm.sdf").write_text(SDF, encoding="utf-8", newline="\n")
    glb = _box().export(file_type="glb")
    (source / "meshes" / "link.glb").write_bytes(glb)
    store = ProjectStore(tmp_path / "projects", examples, REPO / "contracts" / "schemas")
    store.create_project("copy", example="arm")
    copied = tmp_path / "projects" / "copy"
    assert (copied / "scenes" / "arm.sdf").read_text(encoding="utf-8") == SDF
    assert (copied / "meshes" / "link.glb").read_bytes() == glb
