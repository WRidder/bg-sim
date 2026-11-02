"""The example runner's ``scene_bindings`` check (X5.1).

``examples/run_checks.py`` is an inline ``uv`` script, so the tests load it by path.  The
check gets a fake ``Run`` (model document, manifest signals with units, signal columns, a
project folder holding a small SDF) and the real ``Report``.  The valid bindings pass and each
kind of mistake the viewer reports as E301 to E304 fails; the ``fk`` form passes with the right
joint axis and fails with the opposite sign.
"""

from __future__ import annotations

import importlib.util
import json
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

RUNNER = Path(__file__).resolve().parents[2] / "examples" / "run_checks.py"

SDF = """<?xml version="1.0"?>
<sdf version="1.9"><model name="arm">
  <link name="base"><pose>0 0 0 0 0 0</pose><visual name="plate"><geometry><box><size>1 1 1</size></box></geometry></visual></link>
  <link name="bar"><pose>0 0 0 0 0 0</pose><visual name="bar_box"><geometry><box><size>1 1 1</size></box></geometry></visual></link>
  <link name="slider"><pose>0 0 0 0 0 0</pose></link>
  <joint name="shoulder" type="revolute"><parent>base</parent><child>bar</child><axis><xyz>0 -1 0</xyz></axis></joint>
  <joint name="slide" type="prismatic"><parent>base</parent><child>slider</child><axis><xyz>1 0 0</xyz></axis></joint>
</model></sdf>
"""

UNITS = {"q": "1", "x": "m", "w": "1/s", "s": None, **{f"P/g[{i}]": None for i in range(1, 8)}}


@pytest.fixture(scope="module")
def runner():
    spec = importlib.util.spec_from_file_location("bgsim_example_runner_scene", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Report:
    def __init__(self) -> None:
        self.results: list[tuple[bool, str, str]] = []

    def check(self, ok: bool, label: str, detail: str) -> None:
        self.results.append((ok, label, detail))


def _run(tmp_path: Path, bindings: list[dict], q: np.ndarray | None = None):
    (tmp_path / "scenes").mkdir(exist_ok=True)
    (tmp_path / "scenes" / "a.sdf").write_text(SDF, encoding="utf-8")
    time = np.linspace(0.0, 1.0, 11)
    angle = np.linspace(0.0, 1.0, 11) if q is None else q
    signals = {name: np.zeros(11) for name in UNITS}
    signals["q"] = angle
    # the bar tip (1, 0, 0) of the link "bar" for an axis of -Y: x = cos q, z = sin q
    signals["tip_x"] = np.cos(angle)
    signals["tip_z"] = np.sin(angle)
    return SimpleNamespace(
        model_document={"scene": {"file": "scenes/a.sdf"}, "bindings": bindings},
        manifest={"signals": [{"id": name, "unit": unit} for name, unit in UNITS.items()]},
        project_dir=tmp_path,
        time=time,
        signals=signals,
    )


def _check(runner, run, check: dict | None = None) -> list[tuple[bool, str, str]]:
    report = _Report()
    runner._scene_bindings_check(report, "p", "m", run, check or {"kind": "scene_bindings"})
    return report.results


GOOD = [
    {"target": "joint:shoulder", "property": "position", "signal": "q"},
    {"target": "joint:slide", "property": "position", "signal": "x"},
    {"target": "link:bar", "property": "pose", "signal": [f"P/g[{i}]" for i in range(1, 8)]},
    {"target": "visual:bar_box", "property": "scale.z", "signal": "s"},
    {"target": "visual:bar_box", "property": "color", "signal": "s", "colormap": "heat", "range": [0, 1]},
]


def test_valid_bindings_pass(runner, tmp_path):
    results = _check(runner, _run(tmp_path, GOOD))
    assert [r[0] for r in results] == [True], results
    assert "5 binding(s) (2 joint position, 1 pose, 2 visual)" in results[0][2]


@pytest.mark.parametrize(
    ("binding", "fragment"),
    [
        ({"target": "joint:elbow", "property": "position", "signal": "q"}, "no joint named 'elbow'"),
        ({"target": "joint:shoulder", "property": "position", "signal": "nope"}, "unknown signal 'nope'"),
        ({"target": "joint:shoulder", "property": "position", "signal": "x"}, "does not fit a revolute joint"),
        ({"target": "joint:slide", "property": "position", "signal": "q"}, "does not fit a prismatic joint"),
        ({"target": "joint:shoulder", "property": "position", "signal": "w"}, "does not fit a revolute joint"),
        ({"target": "link:bar", "property": "pose", "signal": ["P/g[1]"] * 6}, "needs 7 signals"),
        ({"target": "link:missing", "property": "pose", "signal": [f"P/g[{i}]" for i in range(1, 8)]}, "no link named"),
        ({"target": "visual:missing", "property": "scale.x", "signal": "s"}, "no visual named"),
        ({"target": "link:bar", "property": "scale.x", "signal": "s"}, "no link named 'bar'"),
    ],
)
def test_each_mistake_fails(runner, tmp_path, binding, fragment):
    results = _check(runner, _run(tmp_path, [binding]))
    assert results[0][0] is False
    assert fragment in results[0][2]


def _deform(**over):
    return {
        "target": "visual:bar_box",
        "property": "deformation",
        "family": "bending-y",
        "basis": "clamped-free",
        "beam": {"axis": "+x"},
        "signal": ["x"],
        **over,
    }


def test_deformation_bindings_pass(runner, tmp_path):
    bindings = [_deform(), _deform(family="torsion", signal=["q", "s"])]
    results = _check(runner, _run(tmp_path, bindings))
    assert [r[0] for r in results] == [True], results
    assert "2 binding(s) (0 joint position, 0 pose, 2 visual)" in results[0][2]


def test_linear_torsion_binding_passes(runner, tmp_path):
    bindings = [_deform(family="torsion", basis="linear", signal=["q"], gain=-1)]
    results = _check(runner, _run(tmp_path, bindings))
    assert [r[0] for r in results] == [True], results


@pytest.mark.parametrize(
    ("bindings", "fragment"),
    [
        ([_deform(target="visual:nope")], "no visual named 'nope'"),
        ([_deform(signal=["x", "x", "x", "x"])], "needs 1 to 3 modal coordinates"),
        ([_deform(signal="x")], "needs 1 to 3 modal coordinates"),
        ([_deform(signal=["q"], family="bending-z")], "does not fit a bending-z modal coordinate"),
        ([_deform(signal=["x"], family="torsion")], "does not fit a torsion modal coordinate"),
        ([_deform(), _deform(signal=["s"])], "a second bending-y binding"),
        ([_deform(basis="linear")], "the linear basis is the twist of a torsion spring, not bending-y"),
        ([_deform(family="torsion", basis="linear", signal=["q", "s"])], "the linear basis needs 1 signal"),
    ],
)
def test_each_deformation_mistake_fails(runner, tmp_path, bindings, fragment):
    results = _check(runner, _run(tmp_path, bindings))
    assert results[0][0] is False
    assert fragment in results[0][2]


def test_deformation_needs_a_beam_shape(runner, tmp_path):
    run = _run(tmp_path, [_deform()])
    (tmp_path / "scenes" / "a.sdf").write_text(
        SDF.replace("<box><size>1 1 1</size></box></geometry></visual></link>\n  <link name=\"slider\">", "<sphere><radius>1</radius></sphere></geometry></visual></link>\n  <link name=\"slider\">"),
        encoding="utf-8",
    )
    results = _check(runner, run)
    assert results[0][0] is False
    assert "a sphere is not a beam" in results[0][2]


def _segment(**over):
    return {"target": "visual:bar_box", "property": "segment", "signal": ["x", "x", "s", "s"], **over}


def test_segment_bindings_pass(runner, tmp_path):
    bindings = [_segment(broken="s", brokenStyle="hidden"), _segment(signal=["x"] * 6, axis="-y")]
    results = _check(runner, _run(tmp_path, bindings))
    assert [r[0] for r in results] == [True], results
    assert "2 binding(s) (0 joint position, 0 pose, 2 visual)" in results[0][2]


@pytest.mark.parametrize(
    ("bindings", "fragment"),
    [
        ([_segment(target="visual:nope")], "no visual named 'nope'"),
        ([_segment(signal=["x", "x"])], "needs 4 (planar) or 6 (spatial)"),
        ([_segment(signal="x")], "needs 4 (planar) or 6 (spatial)"),
        ([_segment(signal=["x", "q", "x", "x"])], "is not a length"),
        ([_segment(broken="nope")], "unknown broken signal 'nope'"),
    ],
)
def test_each_segment_mistake_fails(runner, tmp_path, bindings, fragment):
    results = _check(runner, _run(tmp_path, bindings))
    assert results[0][0] is False
    assert fragment in results[0][2]


def test_segment_needs_a_box_or_cylinder(runner, tmp_path):
    run = _run(tmp_path, [_segment()])
    (tmp_path / "scenes" / "a.sdf").write_text(
        SDF.replace("<box><size>1 1 1</size></box></geometry></visual></link>\n  <link name=\"slider\">", "<cylinder><radius>0.1</radius><length>1</length></cylinder></geometry></visual></link>\n  <link name=\"slider\">"),
        encoding="utf-8",
    )
    results = _check(runner, run)
    assert results[0][0] is True, results
    results = _check(runner, _run_with(run, [_segment(axis="+x")]))
    assert results[0][0] is False
    assert "own axis only" in results[0][2]


def _run_with(run, bindings):
    run.model_document["bindings"] = bindings
    return run


def test_model_without_scene_fails(runner, tmp_path):
    run = _run(tmp_path, GOOD)
    run.model_document["scene"] = None
    results = _check(runner, run)
    assert results[0][0] is False
    assert "no scene.file" in results[0][2]


def test_fk_follows_the_joint_axis(runner, tmp_path):
    bindings = [GOOD[0]]
    fk = {"kind": "scene_bindings", "fk": [{"link": "bar", "point": [1, 0, 0], "signals": ["tip_x", None, "tip_z"]}]}
    ok = _check(runner, _run(tmp_path, bindings), fk)
    assert [r[0] for r in ok] == [True, True], ok
    # the model turns the other way: the axis of the scene is wrong for it
    flipped = _run(tmp_path, bindings)
    flipped.signals["tip_z"] = -flipped.signals["tip_z"]
    bad = _check(runner, flipped, fk)
    assert [r[0] for r in bad] == [True, False], bad
    assert "max |SDF point - model signals|" in bad[1][2]


MESH_SDF = SDF.replace(
    '<link name="slider">',
    '<link name="flex"><visual name="bracket"><geometry><mesh><uri>model://flex/meshes/bracket.glb</uri></mesh>'
    '</geometry></visual></link>\n  <link name="slider">',
)


def _glb(targets: int, stress: int | None = None, view_bytes: int | None = None) -> bytes:
    """A GLB whose JSON chunk has one mesh primitive with ``targets`` morph targets (no binary chunk),
    and with ``stress`` a stress table of that many modes on 5 vertices (its bufferView ``view_bytes``
    long, by default the right length)."""
    primitive: dict = {"attributes": {"POSITION": 0}}
    if targets:
        primitive["targets"] = [{"POSITION": 0} for _ in range(targets)]
    gltf: dict = {"asset": {"version": "2.0"}, "meshes": [{"primitives": [primitive]}]}
    if stress is not None:
        gltf["asset"]["extras"] = {"bgsim": {"stress": {"bufferView": 0, "vertices": 5, "modes": stress}}}
        gltf["bufferViews"] = [{"buffer": 0, "byteLength": 5 * stress * 24 if view_bytes is None else view_bytes}]
    text = json.dumps(gltf).encode("utf-8")
    chunk = text + b" " * ((4 - len(text) % 4) % 4)
    return b"glTF" + struct.pack("<II", 2, 20 + len(chunk)) + struct.pack("<I", len(chunk)) + b"JSON" + chunk


def _mesh_run(tmp_path: Path, bindings: list[dict], targets: int | None = 4):
    run = _run(tmp_path, bindings)
    (tmp_path / "scenes" / "a.sdf").write_text(MESH_SDF, encoding="utf-8")
    if targets is not None:
        (tmp_path / "meshes").mkdir(exist_ok=True)
        (tmp_path / "meshes" / "bracket.glb").write_bytes(_glb(targets))
    return run


def _modes(**over):
    return {"target": "visual:bracket", "property": "mode-shapes", "signal": ["x", "s"], **over}


def test_mode_shapes_binding_passes(runner, tmp_path):
    results = _check(runner, _mesh_run(tmp_path, [_modes()]))
    assert [r[0] for r in results] == [True], results
    assert "1 binding(s) (0 joint position, 0 pose, 1 visual)" in results[0][2]


@pytest.mark.parametrize(
    ("bindings", "targets", "fragment"),
    [
        ([_modes(target="visual:nope")], 4, "no visual named 'nope'"),
        ([_modes(target="link:flex")], 4, "no visual named 'flex'"),
        ([_modes(target="visual:bar_box")], 4, "a box is not a mesh"),
        ([_modes(signal="x")], 4, "needs 1 to 64 modal coordinates"),
        ([_modes(signal=[])], 4, "needs 1 to 64 modal coordinates"),
        ([_modes(signal=["x"] * 65)], 100, "needs 1 to 64 modal coordinates"),
        ([_modes(signal=["x", "s", "x"])], 2, "3 modal coordinates but mesh 'bracket.glb' has 2 morph targets"),
        ([_modes()], 0, "has no morph targets"),
        ([_modes()], None, "mesh 'bracket.glb' unreadable"),
        ([_modes(signal=["q", "w"])], 4, "does not fit a modal coordinate (m)"),
        ([_modes(), _modes(signal=["x"])], 4, "a second mode-shapes binding of visual:bracket"),
    ],
)
def test_each_mode_shapes_mistake_fails(runner, tmp_path, bindings, targets, fragment):
    results = _check(runner, _mesh_run(tmp_path, bindings, targets))
    assert results[0][0] is False
    assert fragment in results[0][2]


HEAT = {"colormap": "heat", "range": [0, 5e7]}


def test_mode_shapes_stress_colouring_passes_with_a_table(runner, tmp_path):
    run = _mesh_run(tmp_path, [_modes(stress=HEAT)])
    (tmp_path / "meshes" / "bracket.glb").write_bytes(_glb(4, stress=2))
    results = _check(runner, run)
    assert [r[0] for r in results] == [True], results


@pytest.mark.parametrize(
    ("glb", "stress", "fragment"),
    [
        (_glb(4), HEAT, "has no stress table"),
        (_glb(4, stress=1), HEAT, "2 modal coordinates but the stress table of mesh 'bracket.glb' has 1 modes"),
        (_glb(4, stress=2, view_bytes=100), HEAT, "has a bufferView of 100 bytes"),
        (_glb(4, stress=2), {"colormap": "heat", "range": [5e7, 0]}, "the stress range must be two finite values"),
    ],
)
def test_each_mode_shapes_stress_mistake_fails(runner, tmp_path, glb, stress, fragment):
    run = _mesh_run(tmp_path, [_modes(stress=stress)])
    (tmp_path / "meshes" / "bracket.glb").write_bytes(glb)
    results = _check(runner, run)
    assert results[0][0] is False
    assert fragment in results[0][2]


def test_glb_morph_targets_counts_the_fewest(runner, tmp_path):
    path = tmp_path / "a.glb"
    path.write_bytes(_glb(7))
    assert runner._glb_morph_targets(path) == 7
    path.write_bytes(b"not a glb at all, really")
    with pytest.raises(ValueError):
        runner._glb_morph_targets(path)
