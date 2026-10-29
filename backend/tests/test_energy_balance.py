"""The port-power energy ledger ``tools/energy_balance.py`` (plan 9.2, X-MB6).

``tools/energy_balance.py`` is an inline ``uv`` script, so the tests load it by
path (like ``test_example_runner.py`` does for ``examples/run_checks.py``).  The
synthetic cases write a tiny run directory (``manifest.json`` + ``columns.f64`` in
the plan 3.5 layout, inside a project folder with its model document) from an
analytic series RLC: the charge ``q(t) = A e^{-a t} sin(w t)`` gives the current,
the inductor, capacitor and resistor powers in closed form, and the source power
is the negative of their sum, so the ledger closes exactly.  The last test runs
the real X-MB1 pendulum through the real worker.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "energy_balance.py"
RUNNER = REPO / "examples" / "run_checks.py"

R, L, C = 3.0, 0.5, 0.2
A, DECAY, OMEGA = 2.0, 0.4, 3.0


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool():
    return _load(TOOL, "bgsim_energy_balance")


# --------------------------------------------------------------------------- synthetic runs


def rlc(t: np.ndarray) -> dict[str, np.ndarray]:
    """Closed-form signals of a series RLC driven by the voltage that closes the loop."""
    ex = np.exp(-DECAY * t)
    s, c = np.sin(OMEGA * t), np.cos(OMEGA * t)
    q = A * ex * s
    i = A * ex * (OMEGA * c - DECAY * s)
    di = A * ex * ((DECAY**2 - OMEGA**2) * s - 2.0 * DECAY * OMEGA * c)
    e_source = R * i + L * di + q / C
    return {"q": q, "i": i, "di": di, "e": e_source}


def rlc_powers(t: np.ndarray) -> dict[str, np.ndarray]:
    x = rlc(t)
    return {
        "R1/p.P": R * x["i"] ** 2,
        "L1/p.P": L * x["i"] * x["di"],
        "C1/p.P": x["q"] / C * x["i"],
        "V1/p.P": -x["e"] * x["i"],
        # a transformer carries power through: its two ports cancel
        "T1/a.P": 0.7 * x["e"] * x["i"],
        "T1/b.P": -0.7 * x["e"] * x["i"],
    }


MODEL = {
    "format": "bgsim.model",
    "name": "rlc",
    "diagram": {
        "nodes": [
            {"id": "n1", "name": "V1", "block": {"ref": "stdlib:bondgraph/Se"}},
            {"id": "n2", "name": "R1", "block": {"ref": "stdlib:bondgraph/R"}},
            {"id": "n3", "name": "L1", "block": {"ref": "stdlib:bondgraph/I"}},
            {"id": "n4", "name": "C1", "block": {"ref": "stdlib:bondgraph/C"}},
            {"id": "n5", "name": "T1", "block": {"ref": "stdlib:bondgraph/TF"}},
            {"id": "n6", "name": "J1", "block": {"junction": "1"}},
        ]
    },
}

STORED = [
    {"coeff": 0.5 * L, "signal": "L1/i", "pow": 2},
    {"coeff": 0.5 / C, "signal": "C1/q", "pow": 2},
]


def write_run(
    root: Path,
    t: np.ndarray,
    powers: dict[str, np.ndarray],
    extra: dict[str, np.ndarray] | None = None,
    model: dict | None = MODEL,
    run_name: str = "run-1",
) -> Path:
    """``<root>/models/rlc.bgmodel.json`` + ``<root>/runs/<run>/{manifest,columns.f64}``."""
    signals: list[tuple[str, str, str, np.ndarray]] = []
    for sid, values in powers.items():
        signals.append((sid, "power", sid.split("/")[0], values))
    for sid, values in (extra or {}).items():
        signals.append((sid, "state", sid.split("/")[0], values))
    run_dir = root / "runs" / run_name
    run_dir.mkdir(parents=True)
    if model is not None:
        (root / "models").mkdir(exist_ok=True)
        (root / "models" / "rlc.bgmodel.json").write_text(json.dumps(model), encoding="utf-8")
    manifest = {
        "id": run_name,
        "model": "rlc",
        "status": "done",
        "time": {"n": int(t.size), "t0": float(t[0]), "t1": float(t[-1])},
        "signals": [
            {"id": sid, "kind": kind, "path": path, "type": "Real", "unit": "W"}
            for sid, kind, path, _ in signals
        ],
        "diagnostics": [],
        "layout": "columnar-f64-v1",
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    table = np.vstack([t, *[values for *_, values in signals]]).astype("<f8")
    table.tofile(run_dir / "columns.f64")
    return run_dir


def rlc_run(root: Path, dt: float = 1e-3, t_end: float = 6.0, **kwargs) -> Path:
    t = np.arange(0.0, t_end + 0.5 * dt, dt)
    x = rlc(t)
    return write_run(
        root, t, rlc_powers(t), {"L1/i": x["i"], "C1/q": x["q"]}, **kwargs
    )


# --------------------------------------------------------------------------- tests


def test_exact_ledger_on_an_rlc_signal_set(tool, tmp_path):
    result = tool.energy_balance(rlc_run(tmp_path), tol=1e-5, stored=STORED)
    assert result["ok"], tool.format_table(result)

    # classification came from the model: stdlib types resolved through the run's project
    by_path = {e["path"]: e["class"] for e in result["elements"]}
    assert by_path == {
        "R1": "dissipation",
        "L1": "storage",
        "C1": "storage",
        "V1": "source",
        "T1": "conversion",
    }

    # closed forms on a fine grid: dissipation = int R i^2, source = -int e i, storage = Delta E
    fine = np.linspace(0.0, 6.0, 600_001)
    x = rlc(fine)
    diss = float(np.trapezoid(R * x["i"] ** 2, fine))
    supplied = float(np.trapezoid(x["e"] * x["i"], fine))
    energy = 0.5 * L * x["i"] ** 2 + 0.5 * x["q"] ** 2 / C
    classes = result["classes"]
    assert classes["dissipation"]["integral"] == pytest.approx(diss, rel=1e-5)
    assert classes["source"]["integral"] == pytest.approx(-supplied, rel=1e-5)
    assert classes["storage"]["integral"] == pytest.approx(energy[-1] - energy[0], rel=1e-4)
    assert abs(classes["conversion"]["integral"]) < 1e-12
    # Tellegen: every bond carries opposite power at its two ends -> zero to round-off
    assert result["residual_rel"] < 1e-13
    assert abs(result["residual"]) < 1e-12 * result["throughput"]
    # the named stored energy closes both balances to the trapezoid order
    assert result["stored"]["storage_balance_rel"] < 1e-5
    assert result["stored"]["supply_balance_rel"] < 1e-5
    assert result["stored"]["delta_E"] == pytest.approx(energy[-1] - energy[0], rel=1e-9)


def test_broken_ledger_is_caught(tool, tmp_path):
    t = np.arange(0.0, 6.0 + 5e-4, 1e-3)
    powers = rlc_powers(t)
    powers["R1/p.P"] = powers["R1/p.P"] * 1.02          # the resistor "creates" 2 % more heat
    x = rlc(t)
    run_dir = write_run(tmp_path, t, powers, {"L1/i": x["i"], "C1/q": x["q"]})
    result = tool.energy_balance(run_dir, tol=1e-5, stored=STORED)
    assert not result["ok"]
    assert result["residual_rel"] > 1e-3
    assert result["stored"]["supply_balance_rel"] > 1e-3
    # a wrong stored-energy expression is caught by the balances while Tellegen still holds
    good = rlc_run(tmp_path / "good")
    wrong = [{"coeff": 0.5 * L, "signal": "L1/i", "pow": 2}]   # forgot the capacitor
    result = tool.energy_balance(good, tol=1e-5, stored=wrong)
    assert result["residual_rel"] < 1e-13
    assert result["stored"]["storage_balance_rel"] > 1e-2
    assert not result["ok"]


def test_cli_exit_code_and_json(tool, tmp_path, capsys):
    out = tmp_path / "ledger.json"
    stored = tmp_path / "stored.json"
    stored.write_text(json.dumps(STORED), encoding="utf-8")
    good = rlc_run(tmp_path / "good")
    assert tool.main([str(good), "--tol", "1e-5", "--stored", str(stored), "--json", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "PASS" in printed and "dissipation" in printed and "residual" in printed
    summary = json.loads(out.read_text(encoding="utf-8"))
    assert summary["ok"] and summary["classes"]["storage"]["count"] == 2

    # a tolerance the trapezoid order cannot meet fails with a non-zero exit
    assert tool.main([str(good), "--tol", "1e-15", "--stored", str(stored)]) == 1
    # a missing run directory is a usage error
    assert tool.main([str(tmp_path / "nope")]) == 2
    # strict mode fails on an element the model cannot classify
    unknown = json.loads(json.dumps(MODEL))
    unknown["diagram"]["nodes"][1]["block"] = {"ref": "stdlib:bondgraph/NoSuchBlock"}
    odd = rlc_run(tmp_path / "odd", model=unknown)
    assert tool.main([str(odd), "--tol", "1e-5"]) == 0
    assert tool.main([str(odd), "--tol", "1e-5", "--strict"]) == 1


def test_classification_override(tool, tmp_path):
    run_dir = rlc_run(tmp_path)
    plain = tool.energy_balance(run_dir, tol=1e-5)
    assert {e["path"]: e["class"] for e in plain["elements"]}["R1"] == "dissipation"

    moved = tool.energy_balance(run_dir, tol=1e-5, overrides={"R1": "mixed", "T*": "measure"})
    by_path = {e["path"]: e for e in moved["elements"]}
    assert by_path["R1"]["class"] == "mixed" and by_path["R1"]["why"] == "override R1"
    assert by_path["T1"]["class"] == "measure"
    assert moved["classes"]["dissipation"]["count"] == 0
    assert moved["classes"]["mixed"]["integral"] == pytest.approx(
        plain["classes"]["dissipation"]["integral"]
    )
    # the supply balance counts mixed elements as exchange, so it still closes
    with_energy = tool.energy_balance(run_dir, tol=1e-5, stored=STORED, overrides={"R1": "mixed"})
    assert with_energy["ok"]
    # moving the resistor into storage breaks the storage balance (heat is not stored energy)
    wrong = tool.energy_balance(run_dir, tol=1e-5, stored=STORED, overrides={"R1": "storage"})
    assert not wrong["ok"]
    with pytest.raises(ValueError):
        tool.energy_balance(run_dir, overrides={"R1": "banana"})

    # without a model document every element is unclassified until overridden
    bare = rlc_run(tmp_path / "bare", model=None)
    unknown = tool.energy_balance(bare, tol=1e-5)
    assert sorted(unknown["unclassified"]) == ["C1", "L1", "R1", "T1", "V1"]
    named = tool.energy_balance(
        bare, tol=1e-5, stored=STORED,
        overrides={"R1": "dissipation", "L1": "storage", "C1": "storage",
                   "V1": "source", "T1": "conversion"},
    )
    assert named["ok"] and not named["unclassified"]


def test_composite_paths_resolve_through_components(tool):
    model = {"diagram": {"nodes": [
        {"name": "Body1", "block": {"ref": "stdlib:planar/RigidBody2D"}},
        {"name": "Sub", "block": {"subsystem": {"diagram": {"nodes": [
            {"name": "Damp", "block": {"ref": "stdlib:bondgraph/R"}}]}}}},
        {"name": "Zero", "block": {"junction": "0"}},
    ]}}
    classifier = tool.Classifier(model)
    assert classifier.classify("Body1/inertia")[0] == "storage"
    assert classifier.classify("Body1/gravity")[0] == "storage"
    assert classifier.classify("Body1/flow")[0] == "measure"
    assert classifier.classify("Sub/Damp")[0] == "dissipation"
    assert classifier.classify("Zero")[0] == "conversion"
    cls, why = classifier.classify("Body1/ghost")
    assert cls == "unclassified" and "no component" in why


def test_expected_trapezoid_order(tool, tmp_path):
    """The balance error of the trapezoid on the solver grid is O(dt^2)."""
    errors = []
    steps = (4e-3, 2e-3, 1e-3)
    for k, dt in enumerate(steps):
        run_dir = rlc_run(tmp_path / f"d{k}", dt=dt)
        result = tool.energy_balance(run_dir, tol=1.0, stored=STORED)
        errors.append(result["stored"]["storage_balance_max"])
    for coarse, fine in itertools.pairwise(errors):
        assert coarse / fine == pytest.approx(4.0, rel=0.05), errors
    # and the primitive itself: int_0^1 e^t = e - 1 with error ~ dt^2 e / 12
    exact = np.e - 1.0
    prev = None
    for n in (50, 100, 200):
        t = np.linspace(0.0, 1.0, n + 1)
        error = abs(tool.trapezoid(t, np.exp(t)) - exact)
        if prev is not None:
            assert prev / error == pytest.approx(4.0, rel=0.05)
        prev = error


def test_repeated_event_times_do_not_break_the_integral(tool):
    t = np.array([0.0, 1.0, 1.0, 2.0])         # an event: left and right limits at t = 1
    p = np.array([1.0, 1.0, 3.0, 3.0])
    assert tool.trapezoid(t, p) == pytest.approx(1.0 + 0.0 + 3.0)
    assert tool.cumulative(t, p)[-1] == pytest.approx(4.0)


def test_terms_from_energy_spec_match_the_runner_budget(tool):
    rng = np.random.default_rng(7)
    n = 20
    names = ["P1", "P2", "P3", "q", "g[3]", "d1", "d2"]
    signals = {k: rng.normal(size=n) for k in names}
    spec = {"p": ["P1", "P2", "P3"], "q": "q", "pose": "g", "d": ["d1", "d2"],
            "J": 0.3, "m": 1.7, "L": 0.5, "g0": 9.81, "kt": 1e4, "q0": 0.1}
    terms = tool.terms_from_energy_spec(spec)
    energy = tool.stored_energy(signals, terms, np.ones(n, dtype=bool))
    kinetic = 0.5 * (signals["P1"] ** 2 / 0.3 + signals["P2"] ** 2 / 1.7 + signals["P3"] ** 2 / 1.7)
    height = signals["g[3]"] + np.sin(signals["q"]) * signals["d1"] + np.cos(signals["q"]) * signals["d2"]
    reference = kinetic + 1.7 * 9.81 * height + 0.5 * 1e4 * (signals["d1"] ** 2 + signals["d2"] ** 2)
    assert np.allclose(energy, reference, rtol=1e-12, atol=1e-12)


def test_runner_energy_ledger_kind(tmp_path):
    """The runner's ``energy_ledger`` kind passes on a closed ledger and fails on a broken one."""
    runner = _load(RUNNER, "bgsim_example_runner_ledger_kind")
    tool = _load(TOOL, "bgsim_energy_balance_kind")

    def run_for(root: Path, scale: float):
        t = np.arange(0.0, 6.0 + 5e-4, 1e-3)
        x = rlc(t)
        powers = rlc_powers(t)
        powers["R1/p.P"] = powers["R1/p.P"] * scale
        run_dir = write_run(root, t, powers, {"L1/i": x["i"], "C1/q": x["q"]})
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        time, signals = runner._read_columns(run_dir, manifest)
        return runner.Run("rlc", "run-1", manifest, time, signals, MODEL, root, run_dir)

    check = {"kind": "energy_ledger", "tol": 1e-5, "stored": STORED,
             "class_totals": {"dissipation": {"value": 0.0, "abs": 1e6}}}
    report = runner.Report()
    runner._check_model_checks(report, "p", "rlc", run_for(tmp_path / "ok", 1.0), [check])
    assert (report.checks, report.failures) == (1, 0)
    report = runner.Report()
    runner._check_model_checks(report, "p", "rlc", run_for(tmp_path / "bad", 1.05), [check])
    assert (report.checks, report.failures) == (1, 1)
    report = runner.Report()
    pinned = dict(check, class_totals={"source": {"value": 123.0, "abs": 1e-3}})
    runner._check_model_checks(report, "p", "rlc", run_for(tmp_path / "pin", 1.0), [pinned])
    assert report.failures == 1
    report = runner.Report()
    runner._check_model_checks(
        report, "p", "rlc", run_for(tmp_path / "mal", 1.0), [{"kind": "energy_ledger", "tol": -1}]
    )
    assert report.failures == 1
    assert tool.CLASSES[0] == "storage"


# --------------------------------------------------------------------------- real worker


@pytest.mark.julia
def test_real_pendulum_run_closes_at_integrator_order(tool, tmp_path):
    """The X-MB1 pendulum through the real worker: Tellegen at round-off, balances at the solver's order."""
    import shutil
    import tempfile

    import httpx

    runner = _load(RUNNER, "bgsim_example_runner_real")
    root = Path(tempfile.mkdtemp(prefix="bgsim-ledger-"))
    log = root / "backend.log"
    process, port = runner._start_backend(root, log)
    try:
        client = httpx.Client(
            base_url=f"http://127.0.0.1:{port}", timeout=httpx.Timeout(180.0, connect=10.0)
        )
        runner._wait_for_worker(client, process, log)
        name = "multibond-pendulum-2d"
        assert client.post("/api/projects", json={"name": name, "example": name}).status_code == 201
        project_dir = Path(runner._get_json(client, f"/api/projects/{name}")["path"])
        run = runner._run_model(client, name, project_dir, "pendulum")
        expected = json.loads((REPO / "examples" / name / "expected.json").read_text(encoding="utf-8"))
        spec = next(c for c in expected["models"]["pendulum-10s"]["checks"] if c["kind"] == "energy")

        result = tool.energy_balance(
            project_dir / "runs" / run.run_id,
            tol=1e-9,
            stored=tool.terms_from_energy_spec(spec),
        )
        print(tool.format_table(result))
        assert result["ok"], tool.format_table(result)
        assert not result["unclassified"]
        classes = result["classes"]
        assert classes["storage"]["count"] == 4        # Body, Gravity, Joint (+ Coriolis)
        assert result["residual_rel"] < 1e-12            # Tellegen at round-off
        assert result["stored"]["storage_balance_rel"] < 1e-9
        assert result["stored"]["supply_balance_rel"] < 1e-9

        # a deliberately wrong ledger is caught on the same real data
        broken = tool.energy_balance(
            project_dir / "runs" / run.run_id, tol=1e-9, stored=tool.terms_from_energy_spec(
                {**spec, "m": spec["m"] * 1.01}
            ),
        )
        assert not broken["ok"]
    finally:
        runner._stop_backend(process)
        shutil.rmtree(root, ignore_errors=True)
