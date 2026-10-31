"""Contract tests (M0.2).

The schemas in `contracts/schemas/` are the single source of truth. These tests

1. check that every schema is a valid JSON Schema 2020-12 document and that all
   cross-schema `$ref`s resolve inside the registry,
2. validate every fixture in `contracts/fixtures/<name>/valid/` and reject every
   fixture in `contracts/fixtures/<name>/invalid/`,
3. check that the generated pydantic models in `bgsim_server.contracts` agree
   with the schema on every fixture,
4. check the fixture coverage the work package asks for (one diagnostic per
   code, the M1 blocks in the catalog, the synthetic run's data files), and
5. check that the catalog fixture is self-consistent with its own source text.
"""

from __future__ import annotations

import itertools
import json
import math
import re
import struct
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

REPO = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO / "contracts" / "schemas"
FIXTURE_DIR = REPO / "contracts" / "fixtures"
GENERATED_PY = REPO / "backend" / "src" / "bgsim_server" / "contracts.py"
GENERATED_TS_DIR = REPO / "web" / "src" / "contracts"

# The schema base names of the plan's fixture layout, and the generated model
# class each schema root becomes in bgsim_server.contracts.
SCHEMAS: dict[str, str] = {
    "catalog": "Catalog",
    "model": "Model",
    "project": "Project",
    "diagnostic": "Diagnostics",
    "run-manifest": "RunManifest",
    "worker-rpc": "WorkerRpc",
    "stream-handshake": "StreamHandshake",
    "bindings": "Bindings",
    "debug": "Debug",
    "docs": "Docs",
    "export-request": "ExportRequest",
    "export-report": "ExportReport",
    "export-job": "ExportJob",
}

# The M1 blocks of plan section 8, as ref -> name.
M1_BLOCKS: dict[str, str] = {
    "stdlib:bondgraph/Se": "Se",
    "stdlib:bondgraph/Sf": "Sf",
    "stdlib:bondgraph/MSe": "MSe",
    "stdlib:bondgraph/C": "C",
    "stdlib:bondgraph/I": "I",
    "stdlib:bondgraph/R": "R",
    "stdlib:bondgraph/TF": "TF",
    "stdlib:bondgraph/GY": "GY",
    "stdlib:bondgraph/De": "De",
    "stdlib:bondgraph/Df": "Df",
    "stdlib:sources/Constant": "Constant",
    "stdlib:sources/Step": "Step",
    "stdlib:sources/Sine": "Sine",
    "stdlib:continuous/Gain": "Gain",
    "stdlib:continuous/Sum": "Sum",
    "stdlib:continuous/Integrator": "Integrator",
    "stdlib:continuous/PIController": "PIController",
    "stdlib:electrical/Resistor": "Resistor",
    "stdlib:electrical/Capacitor": "Capacitor",
    "stdlib:electrical/Inductor": "Inductor",
    "stdlib:electrical/Ground": "Ground",
    "stdlib:electrical/VoltageSource": "VoltageSource",
    "stdlib:translation/Mass": "Mass",
    "stdlib:translation/Spring": "Spring",
    "stdlib:translation/Damper": "Damper",
    "stdlib:translation/Fixed": "Fixed",
    "stdlib:translation/ForceSource": "ForceSource",
    "stdlib:rotation/Inertia": "Inertia",
    "stdlib:rotation/TorsionSpring": "TorsionSpring",
    "stdlib:rotation/RotationalDamper": "RotationalDamper",
    "stdlib:rotation/FixedShaft": "FixedShaft",
    "stdlib:rotation/TorqueSource": "TorqueSource",
    "stdlib:rotation/IdealGear": "IdealGear",
    "stdlib:converters/DCMotor": "DCMotor",
    "stdlib:converters/SpeedSensor": "SpeedSensor",
    "stdlib:converters/AngleSensor": "AngleSensor",
}

DOMAIN_NAMES = [
    "Electrical", "Translation", "Rotation", "Hydraulic", "Generic", "Planar", "Spatial", "Thermal",
]

# One instance of every code in the spec's table plus D14's additions, the
# multibond codes (E007 frame mismatch, E108 invalid inertia parameters,
# E109 singular assembled mass), E113 (global parameter cycle) and the viewer codes of plan 7.6.
DIAGNOSTIC_CODES = [
    "E000", "E001", "E002", "E003", "E004", "E005", "E006", "E007",
    "E101", "E102", "E103", "E104", "E105", "E106", "E108", "E109", "E113",
    "E900", "E901",
    "W201", "W202", "W203", "W204", "W205", "W206", "W216",
    "E301", "E302", "E303", "E304", "E305", "E306",
    "E401", "E402", "W401",
]


def _load_schemas() -> dict[str, dict]:
    return {
        path.name[: -len(".schema.json")]: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(SCHEMA_DIR.glob("*.schema.json"))
    }


SCHEMAS_DOCS = _load_schemas()
REGISTRY = Registry().with_resources(
    [(doc["$id"], Resource.from_contents(doc)) for doc in SCHEMAS_DOCS.values()]
)
VALIDATORS = {
    name: Draft202012Validator(doc, registry=REGISTRY) for name, doc in SCHEMAS_DOCS.items()
}


def _fixture_cases(kind: str) -> list[tuple[str, str, Path]]:
    cases: list[tuple[str, str, Path]] = []
    for schema_name in SCHEMAS:
        base = FIXTURE_DIR / schema_name / kind
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.json")):
            label = f"{schema_name}/{path.relative_to(base).as_posix()}"
            cases.append((schema_name, label, path))
    return cases


VALID_CASES = _fixture_cases("valid")
INVALID_CASES = _fixture_cases("invalid")
SEMANTIC_CASES = _fixture_cases("semantic")


def _read(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _reason(document: object) -> str:
    """The `$comment` that says why an invalid fixture is invalid."""
    if isinstance(document, dict):
        return document.get("$comment", "")
    if isinstance(document, list):
        for item in document:
            if isinstance(item, dict) and "$comment" in item:
                return item["$comment"]
    return ""


# --------------------------------------------------------------------------- schemas


def test_schemas_are_valid_2020_12() -> None:
    assert len(SCHEMAS_DOCS) == len(SCHEMAS)
    for name, doc in SCHEMAS_DOCS.items():
        assert doc["$id"] == f"https://bgsim.local/schemas/{name}.schema.json"
        assert doc["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        Draft202012Validator.check_schema(doc)


def test_cross_schema_refs_resolve() -> None:
    for name, doc in SCHEMAS_DOCS.items():
        for ref in re.findall(r'"\$ref"\s*:\s*"([^"]+)"', json.dumps(doc)):
            if ref.startswith("https://bgsim.local/"):
                assert ref.split("#")[0] in REGISTRY, f"{name}: unresolved $ref {ref}"


def test_every_schema_has_a_valid_and_two_invalid_fixtures() -> None:
    for name in SCHEMAS:
        valid = [case for case in VALID_CASES if case[0] == name]
        invalid = [case for case in INVALID_CASES if case[0] == name]
        assert valid, f"{name}: no valid fixture"
        assert len(invalid) >= 2, f"{name}: fewer than two invalid fixtures"


# --------------------------------------------------------------------------- fixtures


@pytest.mark.parametrize("schema_name,label,path", VALID_CASES, ids=[c[1] for c in VALID_CASES])
def test_valid_fixture_validates(schema_name: str, label: str, path: Path) -> None:
    document = _read(path)
    errors = sorted(VALIDATORS[schema_name].iter_errors(document), key=lambda e: list(e.path))
    assert not errors, "\n".join(f"{list(e.path)}: {e.message}" for e in errors)


@pytest.mark.parametrize("schema_name,label,path", INVALID_CASES, ids=[c[1] for c in INVALID_CASES])
def test_invalid_fixture_is_rejected(schema_name: str, label: str, path: Path) -> None:
    document = _read(path)
    assert _reason(document), f"{label}: invalid fixtures explain the reason in $comment"
    assert not VALIDATORS[schema_name].is_valid(document), f"{label}: expected to be rejected"


@pytest.mark.parametrize("schema_name,label,path", SEMANTIC_CASES, ids=[c[1] for c in SEMANTIC_CASES])
def test_semantic_fixture_is_schema_valid_and_names_the_expected_code(
    schema_name: str, label: str, path: Path
) -> None:
    document = _read(path)
    errors = sorted(VALIDATORS[schema_name].iter_errors(document), key=lambda e: list(e.path))
    assert not errors, "\n".join(f"{list(e.path)}: {e.message}" for e in errors)
    assert re.match(r"^expected E\d{3}: ", _reason(document)), (
        f"{label}: a semantic fixture must start its $comment with `expected E<code>: `"
    )


# --------------------------------------------------------------------------- generated models


def _generated_models() -> dict[str, type]:
    sys.path.insert(0, str(REPO / "backend" / "src"))
    from bgsim_server import contracts

    return {name: getattr(contracts, class_name) for name, class_name in SCHEMAS.items()}


@pytest.mark.parametrize("schema_name,label,path", VALID_CASES, ids=[c[1] for c in VALID_CASES])
def test_generated_model_accepts_valid_fixture(schema_name: str, label: str, path: Path) -> None:
    model = _generated_models()[schema_name]
    model.model_validate(_read(path))


@pytest.mark.parametrize("schema_name,label,path", INVALID_CASES, ids=[c[1] for c in INVALID_CASES])
def test_generated_model_rejects_invalid_fixture(schema_name: str, label: str, path: Path) -> None:
    from pydantic import ValidationError

    model = _generated_models()[schema_name]
    with pytest.raises(ValidationError):
        model.model_validate(_read(path))


def _mutate(document: dict, change) -> dict:
    import copy

    mutated = copy.deepcopy(document)
    change(mutated)
    return mutated


def _set_domain(document: dict, name: str, key: str, value: object) -> None:
    next(d for d in document["domains"] if d["name"] == name)[key] = value


MULTIBOND_MUTATIONS = {
    "block dimension 4": lambda d: d["blocks"][0].__setitem__("dimension", 4),
    "block dimension as a string": lambda d: d["blocks"][0].__setitem__("dimension", "2"),
    "Spatial size 3": lambda d: _set_domain(d, "Spatial", "size", 3),
    "Planar size 6": lambda d: _set_domain(d, "Planar", "size", 6),
    "Planar effort components of length 4": lambda d: next(
        x for x in d["domains"] if x["name"] == "Planar"
    )["components"]["effort"].append("N"),
    "Spatial flow components of length 5": lambda d: next(
        x for x in d["domains"] if x["name"] == "Spatial"
    )["components"]["flow"].pop(),
    "frame as an integer": lambda d: d["blocks"][0]["ports"][0].__setitem__("frame", 3),
}


@pytest.mark.parametrize("label", sorted(MULTIBOND_MUTATIONS))
def test_multibond_catalog_mutation_is_rejected_by_schema_and_generated_model(label: str) -> None:
    """C-MB2: the multibond shape rules hold in the schema and in the generated pydantic."""
    from pydantic import ValidationError

    base = _read(FIXTURE_DIR / "catalog" / "valid" / "catalog.planar.json")
    VALIDATORS["catalog"].validate(base)
    mutated = _mutate(base, MULTIBOND_MUTATIONS[label])
    assert list(VALIDATORS["catalog"].iter_errors(mutated)), f"schema accepted: {label}"
    with pytest.raises(ValidationError):
        _generated_models()["catalog"].model_validate(mutated)


def test_explicit_null_dimension_is_a_known_pydantic_laxness() -> None:
    """C-MB2: `dimension` is absent-or-2|3 in the schema; pydantic also takes an explicit null.

    The JSON Schema is authoritative (the Julia worker omits the key for scalar blocks, never
    sends null). The generated model is typing support, so this laxness is recorded in
    ADR-MB1 rather than worked around; this test pins both halves of the statement.
    """
    base = _read(FIXTURE_DIR / "catalog" / "valid" / "catalog.planar.json")
    mutated = _mutate(base, lambda d: d["blocks"][0].__setitem__("dimension", None))
    assert list(VALIDATORS["catalog"].iter_errors(mutated)), "schema must reject a null dimension"
    _generated_models()["catalog"].model_validate(mutated)


NODE_IMAGE_MAX_BYTES = 512 * 1024


def _with_image_data(data: str) -> dict:
    document = _read(FIXTURE_DIR / "model" / "valid" / "model.subsystem-images.json")
    document["diagram"]["nodes"][0]["ui"]["image"]["data"] = data
    return document


def test_node_image_limit_is_512_kib_decoded_in_schema_and_generated_model() -> None:
    """ui.image.data: 512 KiB decoded (699052 base64 characters) passes, one quad more fails."""
    import base64

    from pydantic import ValidationError

    limit = SCHEMAS_DOCS["model"]["$defs"]["nodeImage"]["properties"]["data"]["maxLength"]
    assert limit == 4 * math.ceil(NODE_IMAGE_MAX_BYTES / 3) == 699052
    at_limit = base64.b64encode(bytes(NODE_IMAGE_MAX_BYTES)).decode("ascii")
    assert len(at_limit) == limit
    model = _generated_models()["model"]

    document = _with_image_data(at_limit)
    VALIDATORS["model"].validate(document)
    parsed = model.model_validate(document)
    assert parsed.diagram.nodes[0].ui.image.data == at_limit

    over = _with_image_data(base64.b64encode(bytes(NODE_IMAGE_MAX_BYTES + 3)).decode("ascii"))
    errors = list(VALIDATORS["model"].iter_errors(over))
    assert [list(error.path)[-1] for error in errors] == ["data"]
    with pytest.raises(ValidationError):
        model.model_validate(over)


def test_node_image_fixture_round_trips_through_the_generated_model() -> None:
    """The PNG and the SVG survive pydantic unchanged (the backend stores the raw document)."""
    document = _read(FIXTURE_DIR / "model" / "valid" / "model.subsystem-images.json")
    model = _generated_models()["model"].model_validate(document)
    dumped = model.model_dump(mode="json", by_alias=True, exclude_unset=True)
    for index, (mime, fit) in enumerate([("image/png", "contain"), ("image/svg+xml", "stretch")]):
        image = dumped["diagram"]["nodes"][index]["ui"]["image"]
        assert image == document["diagram"]["nodes"][index]["ui"]["image"]
        assert (image["mime"], image["fit"]) == (mime, fit)


def test_subsystem_port_ui_round_trips_through_the_generated_model() -> None:
    """A subsystem port's ui.position survives pydantic; a port without ui gains none."""
    document = _read(FIXTURE_DIR / "model" / "valid" / "model.subsystem-port-ui.json")
    model = _generated_models()["model"].model_validate(document)
    dumped = model.model_dump(mode="json", by_alias=True, exclude_unset=True)
    original = document["diagram"]["nodes"][1]["block"]["subsystem"]["ports"]
    ports = dumped["diagram"]["nodes"][1]["block"]["subsystem"]["ports"]
    assert ports == original
    assert ports[0]["ui"] == {"position": {"x": -140, "y": 60}}
    assert "ui" not in ports[1]


def test_sticky_notes_round_trip_through_the_generated_model() -> None:
    """diagram.annotations (root and nested) survive pydantic; a note without color gains none."""
    document = _read(FIXTURE_DIR / "model" / "valid" / "model.sticky-notes.json")
    model = _generated_models()["model"].model_validate(document)
    dumped = model.model_dump(mode="json", by_alias=True, exclude_unset=True)
    assert dumped["diagram"]["annotations"] == document["diagram"]["annotations"]
    assert "color" not in dumped["diagram"]["annotations"][0]
    inner = dumped["diagram"]["nodes"][1]["block"]["subsystem"]["diagram"]["annotations"]
    assert inner == document["diagram"]["nodes"][1]["block"]["subsystem"]["diagram"]["annotations"]
    colours = SCHEMAS_DOCS["model"]["$defs"]["annotation"]["properties"]["color"]["enum"]
    assert colours == ["yellow", "blue", "green", "pink", "grey"]


def test_sticky_note_colour_is_an_enum_in_both_lanes() -> None:
    """A note colour outside the enum is rejected by the schema and by pydantic."""
    from pydantic import ValidationError

    document = _read(FIXTURE_DIR / "model" / "invalid" / "model.bad-note-color.json")
    errors = list(VALIDATORS["model"].iter_errors(document))
    assert [list(error.path)[-1] for error in errors] == ["color"]
    with pytest.raises(ValidationError):
        _generated_models()["model"].model_validate(document)


def test_canvas_shapes_round_trip_through_the_generated_model() -> None:
    """diagram.shapes (root and nested, every kind, z order kept) survive pydantic unchanged."""
    document = _read(FIXTURE_DIR / "model" / "valid" / "model.canvas-shapes.json")
    model = _generated_models()["model"].model_validate(document)
    dumped = model.model_dump(mode="json", by_alias=True, exclude_unset=True)
    assert dumped["diagram"]["shapes"] == document["diagram"]["shapes"]
    assert [shape["id"] for shape in dumped["diagram"]["shapes"]] == ["s1", "s2", "s3", "s4", "s5"]
    assert dumped["diagram"]["shapes"][0]["locked"] is True
    assert "fill" not in dumped["diagram"]["shapes"][1]
    inner = dumped["diagram"]["nodes"][1]["block"]["subsystem"]["diagram"]["shapes"]
    assert inner == document["diagram"]["nodes"][1]["block"]["subsystem"]["diagram"]["shapes"]
    defs = SCHEMAS_DOCS["model"]["$defs"]
    assert defs["shape"]["properties"]["kind"]["enum"] == [
        "rectangle",
        "roundedRectangle",
        "ellipse",
        "line",
        "arrow",
    ]
    # The shape palette is the sticky-note palette plus none and ink.
    notes = defs["annotation"]["properties"]["color"]["enum"]
    assert defs["shapeColor"]["enum"] == ["none", "ink", *notes]


@pytest.mark.parametrize(
    ("fixture", "field"),
    [("model.bad-shape-kind.json", "kind"), ("model.bad-shape-opacity.json", "opacity")],
)
def test_canvas_shape_fields_are_checked_in_both_lanes(fixture: str, field: str) -> None:
    """A shape kind outside the enum or an opacity above 1 is rejected by the schema and pydantic."""
    from pydantic import ValidationError

    document = _read(FIXTURE_DIR / "model" / "invalid" / fixture)
    errors = list(VALIDATORS["model"].iter_errors(document))
    assert [list(error.path)[-1] for error in errors] == [field]
    with pytest.raises(ValidationError):
        _generated_models()["model"].model_validate(document)


def test_subsystem_port_ui_requires_a_position() -> None:
    """ui is optional on a port, but a ui without position is rejected by both lanes."""
    from pydantic import ValidationError

    document = _read(
        FIXTURE_DIR / "model" / "invalid" / "model.subsystem-port-ui-no-position.json"
    )
    assert list(VALIDATORS["model"].iter_errors(document))
    with pytest.raises(ValidationError):
        _generated_models()["model"].model_validate(document)


def test_bindings_pose_order_is_documented_in_the_schema() -> None:
    """C-MB2: the pose binding says quaternion first, matching the model's Vec{7} chart."""
    description = SCHEMAS_DOCS["bindings"]["$defs"]["poseBinding"]["properties"]["signal"][
        "description"
    ]
    assert "(q_w, q_x, q_y, q_z, x, y, z)" in description
    assert "quaternion then position" in description


def test_generated_files_exist() -> None:
    assert GENERATED_PY.exists() and GENERATED_PY.stat().st_size > 0
    for name in SCHEMAS:
        path = GENERATED_TS_DIR / f"{name}.ts"
        assert path.exists() and path.stat().st_size > 0, f"missing {path}"
    assert (GENERATED_TS_DIR / "index.ts").exists()


# --------------------------------------------------------------------------- coverage


def test_catalog_covers_the_m1_blocks() -> None:
    catalog = _read(FIXTURE_DIR / "catalog" / "valid" / "catalog.min.json")
    blocks = {block["ref"]: block for block in catalog["blocks"]}
    assert set(M1_BLOCKS) <= set(blocks), f"missing: {sorted(set(M1_BLOCKS) - set(blocks))}"
    for ref, name in M1_BLOCKS.items():
        assert blocks[ref]["name"] == name
        assert blocks[ref]["group"]
        assert blocks[ref]["release"] == "0.1"
        assert blocks[ref]["path"].endswith(f"/{name}.jl")
        assert blocks[ref]["source"].startswith(f"@block {name} begin")
    assert [junction["ref"] for junction in catalog["junctions"]] == ["junction:0", "junction:1"]
    assert [domain["name"] for domain in catalog["domains"]] == DOMAIN_NAMES


def test_catalog_blocks_agree_with_their_source() -> None:
    catalog = _read(FIXTURE_DIR / "catalog" / "valid" / "catalog.min.json")
    for block in catalog["blocks"]:
        source = block["source"]
        assert source.rstrip().endswith("end"), f"{block['ref']}: source is not a complete block"
        declared = (
            block["constants"]
            + block["parameters"]
            + block["inputs"]
            + block["outputs"]
            + block["ports"]
            + block["variables"]
        )
        for decl in declared:
            assert re.search(rf"\b{decl['name']}\s*::", source), (
                f"{block['ref']}: {decl['name']} is not declared in the source"
            )
        for parameter in block["parameters"]:
            if parameter["unit"] is not None:
                assert f'unit = "{parameter["unit"]}"' in source, (
                    f"{block['ref']}: unit of {parameter['name']} differs from the source"
                )
        for variable in block["variables"]:
            if variable["unit"] is not None:
                assert f'unit = "{variable["unit"]}"' in source, (
                    f"{block['ref']}: unit of {variable['name']} differs from the source"
                )
        for port in block["ports"]:
            match = re.search(rf"\b{port['name']}\s*::\s*Power\{{(\w+)\}}", source)
            assert match, f"{block['ref']}: port {port['name']} is not declared in the source"
            assert match.group(1) == port["domain"], (
                f"{block['ref']}: domain of {port['name']} differs from the source"
            )
        port_names = {port["name"] for port in block["ports"]}
        for causality in block["causality"]:
            assert set(causality["ports"]) <= port_names, (
                f"{block['ref']}: causality names a port that does not exist"
            )


def test_diagnostics_sample_covers_every_code() -> None:
    sample = _read(FIXTURE_DIR / "diagnostic" / "valid" / "diagnostics.sample.json")
    codes = [item["code"] for item in sample]
    assert sorted(codes) == sorted(DIAGNOSTIC_CODES), "one instance of every code, no extras"
    assert len(codes) == len(set(codes)), "no code appears twice"
    for item in sample:
        assert item["message"], f"{item['code']}: needs a message"
        # A global-parameter diagnostic is model-wide (path null, scope "global:<name>").
        assert item["path"] or item["code"] == "E113", f"{item['code']}: needs a path"
        assert item["severity"] == ("error" if item["code"].startswith("E") else "warning")


def test_bindings_sample_has_the_spec_examples() -> None:
    bindings = _read(FIXTURE_DIR / "bindings" / "valid" / "bindings.robot.json")["bindings"]
    assert [b["property"] for b in bindings] == ["position", "pose", "scale.z", "color", "visible"]
    pose = next(b for b in bindings if b["property"] == "pose")
    assert len(pose["signal"]) == 7, "a pose is a unit quaternion plus a position"
    # The model's pose chart is Vec{7} = (q_w, q_x, q_y, q_z, x, y, z): quaternion first.
    assert [s.rsplit("/", 1)[1] for s in pose["signal"]] == ["qw", "qx", "qy", "qz", "x", "y", "z"]
    assert all(b["target"].split(":")[0] in {"joint", "link", "frame", "visual"} for b in bindings)


# --------------------------------------------------------------------------- synthetic run


def _run_generator(out_dir: Path) -> None:
    script = FIXTURE_DIR / "run-manifest" / "valid" / "run.synthetic" / "generate.py"
    proc = subprocess.run(
        ["uv", "run", str(script), str(out_dir)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"generate.py failed:\n{proc.stdout}\n{proc.stderr}"


def _generate_if_missing() -> Path:
    run_dir = FIXTURE_DIR / "run-manifest" / "valid" / "run.synthetic"
    if not (run_dir / "columns.f64").exists() or not (run_dir / "stream.f64").exists():
        _run_generator(run_dir)
    return run_dir


def _columns(run_dir: Path) -> tuple[list[float], dict]:
    manifest = _read(run_dir / "manifest.json")
    count = (1 + len(manifest["signals"])) * manifest["time"]["n"]
    data = (run_dir / "columns.f64").read_bytes()
    assert len(data) == count * 8, "columns.f64 is 8 bytes per Float64 value"
    return list(struct.unpack(f"<{count}d", data)), manifest


def test_run_synthetic_manifest_lists_the_generated_columns() -> None:
    run_dir = _generate_if_missing()
    values, manifest = _columns(run_dir)
    assert manifest["layout"] == "columnar-f64-v1"
    assert [signal["id"] for signal in manifest["signals"]] == [
        "Synthetic/sine",
        "Synthetic/step",
        "Synthetic/counter",
        "Synthetic/flag",
    ]
    assert manifest["time"] == {"n": 1001, "t0": 0.0, "t1": 1.0}
    assert manifest["status"] == "done"
    assert len(values) == 5 * 1001


def test_run_synthetic_columns_are_little_endian_and_monotone() -> None:
    run_dir = _generate_if_missing()
    values, manifest = _columns(run_dir)
    n = manifest["time"]["n"]
    time = values[:n]
    assert time[0] == 0.0 and time[-1] == 1.0
    assert all(b > a for a, b in itertools.pairwise(time)), "the time column is strictly monotone"


def test_run_synthetic_values_match_the_generator() -> None:
    run_dir = _generate_if_missing()
    values, manifest = _columns(run_dir)
    n = manifest["time"]["n"]
    sine, step, counter, flag = (values[i * n : (i + 1) * n] for i in range(1, 5))
    assert abs(sine[125] - math.sin(2.0 * math.pi * 0.125)) < 1e-12
    assert step[249] == 0.0 and step[250] == 2.0
    assert counter[250] == 2.0 and counter[1000] == 10.0
    assert flag[499] == 0.0 and flag[500] == 1.0


def test_run_synthetic_stream_is_the_same_data_row_major() -> None:
    run_dir = _generate_if_missing()
    values, manifest = _columns(run_dir)
    n = manifest["time"]["n"]
    stream = (run_dir / "stream.f64").read_bytes()
    assert len(stream) == (1 + len(manifest["signals"])) * n * 8
    rows = struct.unpack(f"<{len(stream) // 8}d", stream)
    for index in (0, 125, 500, n - 1):
        row = rows[index * 5 : index * 5 + 5]
        assert list(row) == [values[column * n + index] for column in range(5)]


def test_run_synthetic_generator_is_deterministic(tmp_path: Path) -> None:
    run_dir = _generate_if_missing()
    _run_generator(tmp_path)
    for name in ("columns.f64", "stream.f64"):
        assert (tmp_path / name).read_bytes() == (run_dir / name).read_bytes(), (
            f"{name} differs between two runs of generate.py"
        )
