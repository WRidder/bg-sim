"""The example runner's ``scene_bindings`` check (X5.1).

``examples/run_checks.py`` is an inline ``uv`` script, so the tests load it by path.  The
check gets a fake ``Run`` (model document, manifest signals with units, signal columns, a
project folder holding a small SDF) and the real ``Report``.  The valid bindings pass and each
kind of mistake the viewer reports as E301 to E304 fails; the ``fk`` form passes with the right
joint axis and fails with the opposite sign.
"""

from __future__ import annotations

import importlib.util
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
