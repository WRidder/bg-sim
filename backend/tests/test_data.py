"""Project data files and CSV preview (F5.1)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bgsim_server import data
from bgsim_server.app import create_app

CSV = "t [s],q [rad],qd\n0,0,1\n0.5,0.25,1\n1,0.5,1\n"


@pytest.fixture
def client(fake_settings):
    with TestClient(create_app(fake_settings)) as test_client:
        assert test_client.post("/api/projects", json={"name": "demo"}).status_code == 201
        yield test_client


def _upload(client, name: str, payload: bytes | str, project: str = "demo"):
    if isinstance(payload, str):
        payload = payload.encode()
    return client.post(
        f"/api/projects/{project}/data", files={"file": (name, payload, "text/csv")}
    )


def test_split_header_reads_the_optional_unit():
    assert data.split_header("q1 [rad/s]") == {"name": "q1", "unit": "rad/s"}
    assert data.split_header(' "t" ') == {"name": "t", "unit": ""}


def test_preview_counts_rows_and_parses_cells():
    result = data.preview_csv(CSV, rows=2)
    assert [c["name"] for c in result["columns"]] == ["t", "q", "qd"]
    assert result["columns"][0]["unit"] == "s"
    assert result["rows"] == 3
    assert result["head"] == [[0.0, 0.0, 1.0], [0.5, 0.25, 1.0]]


def test_preview_uses_the_delimiter_of_the_header():
    result = data.preview_csv("t;a\n0;1\n1;2\n")
    assert result["delimiter"] == ";" and result["rows"] == 2


def test_upload_list_get_preview_delete_round_trip(client, fake_settings):
    response = _upload(client, "My Traj.csv", CSV)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["file"] == "My_Traj.csv" and body["path"] == "data/My_Traj.csv"
    assert body["rows"] == 3
    assert (fake_settings.projects_root / "demo" / "data" / "My_Traj.csv").is_file()

    listing = client.get("/api/projects/demo/data").json()
    assert [f["file"] for f in listing] == ["My_Traj.csv"]
    assert client.get("/api/projects/demo/data/My_Traj.csv").text == CSV

    preview = client.get("/api/projects/demo/data/My_Traj.csv/preview?rows=1").json()
    assert preview["rows"] == 3 and len(preview["head"]) == 1
    assert preview["columns"][1] == {"name": "q", "unit": "rad"}

    assert client.delete("/api/projects/demo/data/My_Traj.csv").status_code == 204
    assert client.get("/api/projects/demo/data/My_Traj.csv").status_code == 404
    assert client.get("/api/projects/demo/data").json() == []


def test_put_replaces_and_normalizes_line_endings(client):
    assert client.put("/api/projects/demo/data/a.csv", content=CSV).status_code == 200
    replaced = client.put("/api/projects/demo/data/a.csv", content="t,x\r\n0,1\r\n1,2\r\n")
    assert replaced.status_code == 200 and replaced.json()["rows"] == 2
    assert client.get("/api/projects/demo/data/a.csv").text == "t,x\n0,1\n1,2\n"


@pytest.mark.parametrize("name", ["../a.csv", "a.txt", ".csv", "sub%2Fa.csv", "C%3Aa.csv"])
def test_bad_names_are_refused(client, name):
    assert client.get(f"/api/projects/demo/data/{name}").status_code in (400, 404, 405)
    assert client.put(f"/api/projects/demo/data/{name}", content=CSV).status_code in (400, 404, 405)


def test_bad_name_message_says_what_to_do(client):
    response = client.put("/api/projects/demo/data/a.txt", content=CSV)
    assert response.status_code == 400
    assert "ending in .csv" in response.text


def test_upload_rejects_other_formats_empty_and_ragged_files(client):
    assert _upload(client, "a.xlsx", CSV).status_code == 415
    assert _upload(client, "a.csv", "   ").status_code == 400
    ragged = _upload(client, "a.csv", "t,a,b\n0,1\n")
    assert ragged.status_code == 422 and "data row 1" in ragged.text
    assert client.post("/api/projects/demo/data", json={}).status_code == 415


def test_size_limit(client, monkeypatch):
    monkeypatch.setattr(data, "MAX_DATA_BYTES", 16)
    response = _upload(client, "big.csv", "t,a\n" + "0,1\n" * 20)
    assert response.status_code == 413
    assert "Reduce the number of rows" in response.text


def test_unknown_project_is_404(client):
    assert client.get("/api/projects/nope/data").status_code == 404


def test_example_copy_carries_the_data_folder(fake_settings, tmp_path):
    from bgsim_server.projects import ProjectStore

    examples = tmp_path / "examples"
    (examples / "ex" / "data").mkdir(parents=True)
    (examples / "ex" / "data" / "traj.csv").write_text(CSV, encoding="utf-8")
    (examples / "ex" / "bgsim.project.json").write_text(
        '{"format": "bgsim.project", "language": "0.1.0", "name": "ex", "models": [],'
        ' "libraryDir": "library", "scenesDir": "scenes"}',
        encoding="utf-8",
    )
    store = ProjectStore(tmp_path / "projects", examples_root=examples)
    store.create_project("copy", example="ex")
    assert (tmp_path / "projects" / "copy" / "data" / "traj.csv").read_text(encoding="utf-8") == CSV


# --------------------------------------------------------------------------- reduced-model files

MODAL = (
    '{"format": "bgsim.modal-body", "version": 1, "name": "bracket", "nm": 2, "mass": 0.5,\n'
    ' "frequency_hz": [120.0, 340.0], "visual": {"glb": "bracket.glb"}}\n'
)


def test_modal_file_upload_list_get_delete(client, fake_settings):
    assert _upload(client, "traj.csv", CSV).status_code == 201
    response = _upload(client, "My Bracket.modal.json", MODAL)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["file"] == "My_Bracket.modal.json"
    assert body["path"] == "data/My_Bracket.modal.json"
    assert (body["kind"], body["name"], body["nm"]) == ("modal", "bracket", 2)
    stored = fake_settings.projects_root / "demo" / "data" / "My_Bracket.modal.json"
    assert stored.read_text(encoding="utf-8") == MODAL

    # the plain list stays the CSV list; ?kind= selects the reduced models or everything
    assert [f["file"] for f in client.get("/api/projects/demo/data").json()] == ["traj.csv"]
    modal = client.get("/api/projects/demo/data?kind=modal").json()
    assert modal == [{"file": "My_Bracket.modal.json", "bytes": len(MODAL), "kind": "modal"}]
    every = client.get("/api/projects/demo/data?kind=all").json()
    assert [(f["file"], f["kind"]) for f in every] == [
        ("My_Bracket.modal.json", "modal"),
        ("traj.csv", "csv"),
    ]
    assert client.get("/api/projects/demo/data?kind=xlsx").status_code == 422

    fetched = client.get("/api/projects/demo/data/My_Bracket.modal.json")
    assert fetched.status_code == 200 and fetched.text == MODAL
    assert fetched.headers["content-type"].startswith("application/json")
    assert client.get("/api/projects/demo/data/My_Bracket.modal.json/preview").status_code == 400

    assert client.delete("/api/projects/demo/data/My_Bracket.modal.json").status_code == 204
    assert client.get("/api/projects/demo/data?kind=modal").json() == []


def test_modal_put_validates_the_header(client):
    put = client.put("/api/projects/demo/data/b.modal.json", content=MODAL.replace("\n", "\r\n"))
    assert put.status_code == 200 and put.json()["kind"] == "modal"
    assert client.get("/api/projects/demo/data/b.modal.json").text == MODAL
    broken = client.put("/api/projects/demo/data/b.modal.json", content="{not json")
    assert broken.status_code == 422 and "BGSimFEM" in broken.text
    other = client.put("/api/projects/demo/data/b.modal.json", content='{"format": "x"}')
    assert other.status_code == 422 and "bgsim.modal-body" in other.text
    newer = client.put(
        "/api/projects/demo/data/b.modal.json",
        content='{"format": "bgsim.modal-body", "version": 2}',
    )
    assert newer.status_code == 422 and "version" in newer.text
    assert client.get("/api/projects/demo/data/b.modal.json").text == MODAL, "kept on error"
    assert _upload(client, "c.modal.json", "[]").status_code == 422
    assert _upload(client, "c.modal.json", "  ").status_code == 400


@pytest.mark.parametrize(
    "name", ["../a.modal.json", ".modal.json", "a.json", "sub%2Fa.modal.json", "C%3Aa.modal.json"]
)
def test_bad_modal_names_are_refused(client, name):
    assert client.get(f"/api/projects/demo/data/{name}").status_code in (400, 404, 405)
    assert client.put(f"/api/projects/demo/data/{name}", content=MODAL).status_code in (400, 404, 405)


def test_modal_upload_names(client):
    assert _upload(client, "part.json", MODAL).status_code == 415
    escaped = _upload(client, "..\\..\\evil/../x.modal.json", MODAL)
    assert escaped.status_code == 201 and escaped.json()["path"] == "data/x.modal.json"
    assert _upload(client, "...modal.json", MODAL).status_code == 400
