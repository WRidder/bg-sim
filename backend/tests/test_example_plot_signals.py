"""The example runner's ``plots`` check: saved plots (their ``signals`` and the XY axis ``x``) and
the dashboard display cards must name signals the run records.

``examples/run_checks.py`` is an inline ``uv`` script; the test loads it by path, like
``test_example_runner.py``, and calls the check with a fake ``Run``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "examples" / "run_checks.py"


@pytest.fixture(scope="module")
def runner():
    spec = importlib.util.spec_from_file_location("bgsim_example_runner_plots", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run(document: dict, signals: list[str]):
    return SimpleNamespace(
        model="model",
        run_id="0" * 12,
        manifest={},
        time=np.zeros(1),
        signals={signal: np.zeros(1) for signal in signals},
        model_document=document,
    )


RECORDED = ["Osc/x", "Osc/v", "Osc/F"]


def test_plots_with_recorded_signals_and_x_pass(runner):
    document = {
        "plots": [
            {"id": "p1", "title": "x", "signals": ["Osc/x"]},
            {"id": "p2", "title": "phase", "signals": ["Osc/v"], "x": "Osc/x", "equalAspect": True},
        ],
        "dashboard": {
            "cards": [
                {"id": "d1", "kind": "plot", "size": "2x2", "signals": ["Osc/F"], "x": "Osc/x"},
                {"id": "d2", "kind": "value", "size": "1x1", "signals": ["Osc/v"]},
                {"id": "d3", "kind": "slider", "size": "2x1", "parameter": "Osc/k"},
            ]
        },
    }
    assert runner.plot_signal_problems(document, set(RECORDED)) == []
    report = runner.Report()
    runner._plot_signals_check(report, "project", "model", _run(document, RECORDED))
    assert report.checks == 1 and report.failures == 0


def test_an_unknown_x_signal_fails(runner):
    document = {
        "plots": [{"id": "p2", "title": "phase", "signals": ["Osc/v"], "x": "Osc/gone"}],
        "dashboard": {"cards": [{"id": "d1", "kind": "plot", "size": "2x2", "signals": ["Osc/v"], "x": "Old/x"}]},
    }
    problems = runner.plot_signal_problems(document, set(RECORDED))
    assert problems == [
        "plot 'p2': unknown signal(s) Osc/gone (x axis)",
        "dashboard card 'd1': unknown signal(s) Old/x (x axis)",
    ]
    report = runner.Report()
    runner._plot_signals_check(report, "project", "model", _run(document, RECORDED))
    assert report.checks == 1 and report.failures == 1


def test_an_unknown_y_signal_and_x_in_signals_fail(runner):
    document = {"plots": [{"id": "p1", "title": "t", "signals": ["Osc/x", "Osc/nope"], "x": "Osc/x"}]}
    assert runner.plot_signal_problems(document, set(RECORDED)) == [
        "plot 'p1': x 'Osc/x' is also one of its signals",
        "plot 'p1': unknown signal(s) Osc/nope",
    ]


def test_the_xy_fixture_names_only_its_own_signals(runner):
    document = json.loads(
        (REPO / "contracts" / "fixtures" / "model" / "valid" / "model.xy-plots.json").read_text(encoding="utf-8")
    )
    assert runner.plot_signal_problems(document, {"C1/v", "C1/i", "L1/i"}) == []
    assert runner.plot_signal_problems(document, {"C1/v", "L1/i"}) == ["plot 'p3': unknown signal(s) C1/i"]
