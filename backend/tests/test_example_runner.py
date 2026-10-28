"""The example runner's ``fft_peak``, ``period``, ``energy``, ``invariant`` and
``planar_fk`` checks.

``examples/run_checks.py`` is an inline ``uv`` script, not an installed module, so
the tests load it by path.  The spectral helper is checked against synthetic
signals with a known frequency; the check wrappers get a fake ``Run`` and the
real ``Report``, so a PASS/FAIL line and its tolerance are exercised without a
worker, a backend or a run file.  The energy cases use a synthetic planar
pendulum with an exactly constant budget (and a drifting one for the failure);
the multi-body form uses a synthetic 2-link arm whose total energy is constant by
construction, the invariant a synthetic wheel momentum, and ``planar_fk`` a
synthetic arm whose tip is the analytic forward kinematics.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

RUNNER = Path(__file__).resolve().parents[2] / "examples" / "run_checks.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("bgsim_example_runner", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner():
    return _load_runner()


def _run(time: np.ndarray, signal: np.ndarray):
    return SimpleNamespace(
        model="model",
        run_id="0" * 12,
        manifest={},
        time=time,
        signals={"sig": signal},
    )


def test_fft_peak_finds_a_known_sine(runner):
    time = np.arange(0.0, 2.0, 1e-3)
    signal = 0.4 + 0.25 * np.sin(2.0 * np.pi * 4.0 * time)
    samples, dt = runner._resample_window(time, signal)
    measured = runner._fft_peak_frequency(samples, dt)
    assert measured == pytest.approx(4.0, rel=5e-3)


def test_fft_peak_collapses_event_rows_and_resamples(runner):
    # Every event instant appears twice (left/right limits) and one row is missing,
    # so the raw grid is not uniform; the helper must still recover the frequency.
    time = np.arange(0.0, 2.0, 1e-3)
    keep = np.ones(time.size, dtype=bool)
    keep[500] = False
    time = np.concatenate([time[keep], [0.25, 0.75]])
    time.sort()
    signal = np.sin(2.0 * np.pi * 6.0 * time)
    samples, dt = runner._resample_window(time, signal)
    assert samples.size > 1000
    measured = runner._fft_peak_frequency(samples, dt)
    assert measured == pytest.approx(6.0, rel=5e-3)


def test_fft_peak_rejects_a_dc_only_window(runner):
    samples, dt = runner._resample_window(np.arange(0.0, 1.0, 1e-3), np.full(1000, 3.0))
    assert runner._fft_peak_frequency(samples, dt) is None
    assert runner._fft_peak_frequency(np.ones(3), 1e-3) is None


def test_fft_peak_highpass_removes_a_decay_envelope(runner):
    frequency, damping = 10.0, 8.0
    time = np.arange(0.0, 1.2, 1e-3)
    envelope = np.exp(-damping * time)
    signal = 0.2 + 0.1 * envelope * np.sin(2.0 * np.pi * frequency * time)
    samples, dt = runner._resample_window(time, signal)
    measured = runner._fft_peak_frequency(samples, dt, highpass_hz=4.0, min_hz=5.0)
    assert measured == pytest.approx(frequency, rel=0.03)


def test_fft_peak_check_passes_and_fails(runner):
    time = np.arange(0.0, 2.0, 1e-3)
    run = _run(time, np.sin(2.0 * np.pi * 5.0 * time))
    good = {
        "kind": "fft_peak", "signal": "sig", "value": 5.0, "rtol": 0.05,
        "from_t": 0.0, "to_t": 2.0,
    }
    report = runner.Report()
    runner._fft_peak_check(report, "project", "model", run, good)
    assert report.checks == 1 and report.failures == 0

    bad = dict(good, value=8.0)
    report = runner.Report()
    runner._fft_peak_check(report, "project", "model", run, bad)
    assert report.checks == 1 and report.failures == 1


def test_fft_peak_check_rejects_bad_parameters(runner):
    time = np.arange(0.0, 1.0, 1e-3)
    run = _run(time, np.sin(2.0 * np.pi * 5.0 * time))
    for entry in (
        {"signal": "sig", "rtol": 0.05},                            # no value
        {"signal": "missing", "value": 5.0, "rtol": 0.05},          # no signal
        {"signal": "sig", "value": 5.0},                            # no tolerance
        {"signal": "sig", "value": 5.0, "rtol": 0.05, "detrend": "cubic"},
        {"signal": "sig", "value": 5.0, "rtol": 0.05, "min_hz": 9.0, "max_hz": 2.0},
        {"signal": "sig", "value": 5.0, "rtol": 0.05, "highpass_hz": -1.0},
    ):
        report = runner.Report()
        runner._fft_peak_check(report, "project", "model", run, entry)
        assert report.checks == 1 and report.failures == 1, entry


# --------------------------------------------------------------------- period


def test_period_check_measures_two_consecutive_crossings(runner):
    time = np.arange(0.0, 3.0, 1e-3)
    run = _run(time, np.sin(2.0 * np.pi * 2.0 * time))
    good = {
        "kind": "period", "signal": "sig", "direction": "up", "n": 1,
        "value": 0.5, "rtol": 1e-6,
    }
    report = runner.Report()
    runner._period_check(report, "project", "model", run, good)
    assert report.checks == 1 and report.failures == 0

    report = runner.Report()
    runner._period_check(report, "project", "model", run, dict(good, value=0.4))
    assert report.checks == 1 and report.failures == 1

    report = runner.Report()
    runner._period_check(report, "project", "model", run, dict(good, n=99))
    assert report.checks == 1 and report.failures == 1


def test_period_check_rejects_bad_parameters(runner):
    time = np.arange(0.0, 1.0, 1e-3)
    run = _run(time, np.sin(2.0 * np.pi * 5.0 * time))
    for entry in (
        {"signal": "sig", "rtol": 0.05},                           # no value
        {"signal": "missing", "value": 0.2, "rtol": 0.05},         # no signal
        {"signal": "sig", "value": 0.2},                           # no tolerance
        {"signal": "sig", "value": 0.0, "rtol": 0.05},             # zero period
        {"signal": "sig", "value": 0.2, "rtol": 0.05, "direction": "left"},
        {"signal": "sig", "value": 0.2, "rtol": 0.05, "n": 0},
    ):
        report = runner.Report()
        runner._period_check(report, "project", "model", run, entry)
        assert report.checks == 1 and report.failures == 1, entry


# --------------------------------------------------------------------- energy


def _pendulum_run(*, drift: float = 0.0):
    """A synthetic planar pendulum with an exactly constant total energy.

    ``q(t) = q0 cos(omega t)`` sets the potential; the speed is chosen from the
    energy budget, so ``KE + PE`` is constant to rounding.  ``drift`` scales the
    momenta linearly to give the failing case a real energy drift.
    """
    inertia, mass, length, gravity, q0 = 1e-4, 1.0, 0.5, 9.81, 0.01
    time = np.linspace(0.0, 10.0, 10001)
    q = q0 * np.cos(np.sqrt(mass * gravity * length / (inertia + mass * length**2)) * time)
    potential = -mass * gravity * length * np.cos(q)
    energy0 = -mass * gravity * length * np.cos(q0)
    speed = np.sqrt(
        2.0 * np.maximum(energy0 - potential, 0.0) / (inertia + mass * length**2)
    )
    factor = 1.0 + drift * time / time[-1]
    signals = {
        "Body/P[1]": inertia * speed * factor,
        "Body/P[2]": np.zeros_like(time),
        "Body/P[3]": mass * length * speed * factor,
        "Joint/qout": q,
        "Compose/g[3]": potential / (mass * gravity),
        "Joint/dout[1]": np.zeros_like(time),
        "Joint/dout[2]": np.zeros_like(time),
    }
    swing = mass * gravity * length * (1.0 - np.cos(q0))
    run = SimpleNamespace(model="pendulum", run_id="0" * 12, manifest={},
                          time=time, signals=signals)
    return run, swing


def _energy_entry(**overrides):
    entry = {
        "kind": "energy",
        "p": ["Body/P[1]", "Body/P[2]", "Body/P[3]"],
        "q": "Joint/qout",
        "pose": "Compose/g",          # the base id: the y component is used
        "d": ["Joint/dout[1]", "Joint/dout[2]"],
        "J": 1e-4, "m": 1.0, "L": 0.5, "g0": 9.81, "kt": 1e8,
        "q0": 0.01, "tol": 1e-6,
    }
    entry.update(overrides)
    return entry


def test_energy_check_passes_a_conservative_pendulum(runner):
    run, swing = _pendulum_run()
    report = runner.Report()
    runner._energy_check(report, "project", "pendulum-10s", run, _energy_entry())
    assert report.checks == 1 and report.failures == 0
    assert swing == pytest.approx(0.00024524795625688323)


def test_energy_check_fails_a_drifting_pendulum(runner):
    run, _ = _pendulum_run(drift=0.01)
    report = runner.Report()
    runner._energy_check(report, "project", "pendulum-10s", run, _energy_entry())
    assert report.checks == 1 and report.failures == 1


def test_energy_check_includes_the_spring_energy(runner):
    # A run whose total energy is constant only when 1/2 kt |d|^2 is counted:
    # q = 0, the pose cancels d2, d1 oscillates and the momenta carry E0 - spring.
    inertia, mass, stiffness, amplitude, omega = 1e-4, 1.0, 1e8, 1e-6, 10.0
    time = np.linspace(0.0, 0.5, 501)
    d1 = amplitude * np.sin(omega * time)
    spring = 0.5 * stiffness * d1**2
    ceiling = 0.5 * stiffness * amplitude**2
    speed = np.sqrt(2.0 * (ceiling - spring) / (inertia + mass * 0.5**2))
    signals = {
        "Body/P[1]": inertia * speed,
        "Body/P[2]": np.zeros_like(time),
        "Body/P[3]": mass * 0.5 * speed,
        "Joint/qout": np.zeros_like(time),
        "Compose/g[3]": np.zeros_like(time),
        "Joint/dout[1]": d1,
        "Joint/dout[2]": np.zeros_like(time),
    }
    run = SimpleNamespace(model="pendulum", run_id="0" * 12, manifest={},
                          time=time, signals=signals)
    report = runner.Report()
    runner._energy_check(report, "project", "pendulum", run,
                         _energy_entry(kt=stiffness))
    assert report.checks == 1 and report.failures == 0

    # The same signals without the spring term in the budget drift by 0.5 kt A^2.
    report = runner.Report()
    runner._energy_check(report, "project", "pendulum", run, _energy_entry(kt=0.0))
    assert report.checks == 1 and report.failures == 1


def test_energy_check_rejects_bad_parameters(runner):
    run, _ = _pendulum_run()
    for broken in (
        _energy_entry(pose="Compose/missing"),
        _energy_entry(d=["Joint/dout[1]", "Joint/missing"]),
        _energy_entry(p=["Body/P[1]", "Body/P[2]"]),
        _energy_entry(J=0.0),
        _energy_entry(tol=0.0),
        _energy_entry(q0=0.0),
    ):
        report = runner.Report()
        runner._energy_check(report, "project", "pendulum", run, broken)
        assert report.checks == 1 and report.failures == 1, broken


# ------------------------------------------------------------- multi-body energy


def _arm_run(*, drift: float = 0.0):
    """A synthetic 2-link arm whose multi-body budget is constant by construction.

    Both links rotate as one rigid body about the shoulder (``q2 = 0``), so the
    kinetic energy is ``1/2 (J1 + J2) omega^2`` and the potential is
    ``(m1 lc1 + m2 (lc1 + lc2)) g sin(q1)``; ``omega`` is chosen from the budget
    ``E = g S`` (its own maximum), so ``E`` is constant to rounding.  ``drift``
    scales the momenta to give the failing case a real energy drift.
    """
    mass1, inertia1, lc1 = 2.0, 0.02666666666666667, 0.2
    mass2, inertia2, lc2 = 1.5, 0.015, 0.2
    gravity, rate, inertia = 9.81, 0.8, inertia1 + inertia2
    moment = mass1 * lc1 + mass2 * (lc1 + lc2)
    time = np.linspace(0.0, 3.0, 3001)
    q1 = rate * time
    ceiling = gravity * moment
    speed = np.sqrt(2.0 * np.maximum(ceiling - gravity * moment * np.sin(q1), 0.0) / inertia)
    factor = 1.0 + drift * time / time[-1]
    signals = {
        "Joint1/qout": q1,
        "Joint2/qout": np.zeros_like(time),
        "Joint1/dout[1]": np.zeros_like(time),
        "Joint1/dout[2]": np.zeros_like(time),
        "Joint2/dout[1]": np.zeros_like(time),
        "Joint2/dout[2]": np.zeros_like(time),
        "PoseJ2/g[1]": q1,
        "PoseB1/g[3]": lc1 * np.sin(q1),
        "PoseB2/g[3]": (lc1 + lc2) * np.sin(q1),
        "Body1/inertia/P[1]": inertia1 * speed * factor,
        "Body1/inertia/P[2]": np.zeros_like(time),
        "Body1/inertia/P[3]": np.zeros_like(time),
        "Body2/inertia/P[1]": inertia2 * speed * factor,
        "Body2/inertia/P[2]": np.zeros_like(time),
        "Body2/inertia/P[3]": np.zeros_like(time),
    }
    run = SimpleNamespace(model="arm-free", run_id="0" * 12, manifest={},
                          time=time, signals=signals)
    return run, ceiling


def _multi_body_entry(**overrides):
    entry = {
        "kind": "energy",
        "g0": 9.81,
        "bodies": [
            {
                "p": ["Body1/inertia/P[1]", "Body1/inertia/P[2]", "Body1/inertia/P[3]"],
                "J": 0.02666666666666667,
                "m": 2.0,
                "pose": "PoseB1/g[3]",
                "corrections": [
                    {"q": "Joint1/qout", "d": ["Joint1/dout[1]", "Joint1/dout[2]"]}
                ],
            },
            {
                "p": ["Body2/inertia/P[1]", "Body2/inertia/P[2]", "Body2/inertia/P[3]"],
                "J": 0.015,
                "m": 1.5,
                "pose": "PoseB2/g[3]",
                "corrections": [
                    {"q": "Joint1/qout", "d": ["Joint1/dout[1]", "Joint1/dout[2]"]},
                    {"q": "PoseJ2/g[1]", "d": ["Joint2/dout[1]", "Joint2/dout[2]"]},
                ],
            },
        ],
        "springs": [
            {"kt": 1e8, "d": ["Joint1/dout[1]", "Joint1/dout[2]"]},
            {"kt": 1e8, "d": ["Joint2/dout[1]", "Joint2/dout[2]"]},
        ],
        "tol": 1e-6,
    }
    entry.update(overrides)
    if "bound" not in entry:
        entry.setdefault("swing", 1.0)
    return entry


def test_multi_body_energy_passes_a_conservative_arm(runner):
    run, swing = _arm_run()
    report = runner.Report()
    runner._energy_check(report, "project", "arm-free", run,
                         _multi_body_entry(swing=swing))
    assert report.checks == 1 and report.failures == 0
    assert swing == pytest.approx(9.81)


def test_multi_body_energy_fails_a_drifting_arm(runner):
    run, swing = _arm_run(drift=0.02)
    report = runner.Report()
    runner._energy_check(report, "project", "arm-free", run,
                         _multi_body_entry(swing=swing))
    assert report.checks == 1 and report.failures == 1


def test_multi_body_energy_bound_form(runner):
    run, _ = _arm_run()
    report = runner.Report()
    # The budget is E = g S = 9.81 J (the potential ceiling) for the whole run.
    runner._energy_check(report, "project", "balancer", run,
                         _multi_body_entry(bound=10.0))
    assert report.checks == 1 and report.failures == 0
    report = runner.Report()
    runner._energy_check(report, "project", "balancer", run,
                         _multi_body_entry(bound=9.0))
    assert report.checks == 1 and report.failures == 1


def test_multi_body_energy_uses_the_joint_corrections(runner):
    # A pose that ignores a constant pivot deflection is corrected by
    # ``sin(q) d1 + cos(q) d2``: with ``d = (0, -offset)`` the true height is
    # ``lc sin q - offset cos q``.  The momenta follow the corrected budget, so the
    # run is conservative only when the correction is applied.
    mass1, inertia1, lc1 = 2.0, 0.02666666666666667, 0.2
    mass2, inertia2, lc2 = 1.5, 0.015, 0.2
    gravity, rate, offset = 9.81, 0.8, 1e-3
    inertia = inertia1 + inertia2
    moment = mass1 * lc1 + mass2 * (lc1 + lc2)
    mass = mass1 + mass2
    time = np.linspace(0.0, 3.0, 3001)
    q1 = rate * time
    # The corrected potential is moment g sin(q1) - mass g offset cos(q1); its
    # maximum is moment g + mass g offset (at q1 = 0).
    ceiling = gravity * moment + gravity * mass * offset
    potential = gravity * moment * np.sin(q1) - gravity * mass * offset * np.cos(q1)
    speed = np.sqrt(2.0 * np.maximum(ceiling - potential, 0.0) / inertia)
    signals = {
        "Joint1/qout": q1,
        "Joint2/qout": np.zeros_like(time),
        "Joint1/dout[1]": np.zeros_like(time),
        "Joint1/dout[2]": -offset * np.ones_like(time),
        "Joint2/dout[1]": np.zeros_like(time),
        "Joint2/dout[2]": np.zeros_like(time),
        "PoseJ2/g[1]": q1,
        # The composed poses ignore the deflection (that is the point of the term).
        "PoseB1/g[3]": lc1 * np.sin(q1),
        "PoseB2/g[3]": (lc1 + lc2) * np.sin(q1),
        "Body1/inertia/P[1]": inertia1 * speed,
        "Body1/inertia/P[2]": np.zeros_like(time),
        "Body1/inertia/P[3]": np.zeros_like(time),
        "Body2/inertia/P[1]": inertia2 * speed,
        "Body2/inertia/P[2]": np.zeros_like(time),
        "Body2/inertia/P[3]": np.zeros_like(time),
    }
    run = SimpleNamespace(model="arm", run_id="0" * 12, manifest={},
                          time=time, signals=signals)
    entry = _multi_body_entry(
        swing=1.0,
        springs=[],  # the strain term is a constant offset here, not part of drift
        bodies=[
            {
                "p": ["Body1/inertia/P[1]", "Body1/inertia/P[2]", "Body1/inertia/P[3]"],
                "J": inertia1,
                "m": mass1,
                "pose": "PoseB1/g[3]",
                "corrections": [
                    {"q": "Joint1/qout", "d": ["Joint1/dout[1]", "Joint1/dout[2]"]}
                ],
            },
            {
                "p": ["Body2/inertia/P[1]", "Body2/inertia/P[2]", "Body2/inertia/P[3]"],
                "J": inertia2,
                "m": mass2,
                "pose": "PoseB2/g[3]",
                "corrections": [
                    {"q": "Joint1/qout", "d": ["Joint1/dout[1]", "Joint1/dout[2]"]},
                ],
            },
        ],
    )
    report = runner.Report()
    runner._energy_check(report, "project", "arm", run, entry)
    assert report.checks == 1 and report.failures == 0

    # Dropping the correction leaves the 1e-3 m dispatch in the height: the same
    # run drifts by (m1 + m2) g offset cos(q1) = 0.0343 cos(q1) J, which is far
    # outside the 1e-6 J budget.
    without = {**entry, "bodies": [
        {**body, "corrections": []} for body in entry["bodies"]
    ]}
    report = runner.Report()
    runner._energy_check(report, "project", "arm", run, without)
    assert report.checks == 1 and report.failures == 1


def test_multi_body_energy_rejects_bad_parameters(runner):
    run, swing = _arm_run()
    for broken in (
        _multi_body_entry(bodies=[]),
        _multi_body_entry(bodies="nope"),
        _multi_body_entry(swing=swing, bound=9.0),
        _multi_body_entry(swing=0.0),
        _multi_body_entry(swing=swing, tol=0.0),
        _multi_body_entry(swing=swing, g0=0.0),
        _multi_body_entry(
            swing=swing,
            bodies=[
                {
                    "p": ["Body1/inertia/P[1]", "Body1/inertia/P[2]",
                          "Body1/inertia/P[3]"],
                    "J": 0.0,
                    "m": 2.0,
                    "pose": "PoseB1/g[3]",
                }
            ],
        ),
        _multi_body_entry(
            swing=swing,
            bodies=[
                {
                    "p": ["Body1/inertia/P[1]", "Body1/inertia/P[2]",
                          "Body1/inertia/P[3]"],
                    "J": 0.02,
                    "m": 2.0,
                    "pose": "PoseB1/missing",
                }
            ],
        ),
        _multi_body_entry(
            swing=swing,
            bodies=[
                {
                    "p": ["Body1/inertia/P[1]", "Body1/inertia/P[2]",
                          "Body1/inertia/P[3]"],
                    "J": 0.02,
                    "m": 2.0,
                    "pose": "PoseB1/g[3]",
                    "corrections": [{"q": "Joint1/qout", "d": ["Joint1/dout[1]"]}],
                }
            ],
        ),
        _multi_body_entry(swing=swing, springs=[{"kt": 1e8, "d": ["Joint1/nope"]}]),
    ):
        report = runner.Report()
        runner._energy_check(report, "project", "arm-free", run, broken)
        assert report.checks == 1 and report.failures == 1, broken


# --------------------------------------------------------------------- invariant


def _wheel_run(*, drift: float = 0.0):
    """A synthetic reaction wheel: the body rate and the wheel rate exchange.

    ``H = 0.257 * theta_dot + 0.002 * wheel_rate``; the body rate is a sine and the
    wheel rate is chosen to keep ``H`` at 0.06 exactly (plus ``drift``).
    """
    time = np.linspace(0.0, 3.0, 3001)
    rate = 0.035 * np.sin(2.0 * np.pi * 0.4 * time)
    coefficient = 0.257 / 0.002
    wheel = 30.0 - coefficient * rate + drift * time / time[-1]
    signals = {"Pivot/qdout": rate, "WheelJ/qdout": wheel}
    run = SimpleNamespace(model="balancer-free", run_id="0" * 12, manifest={},
                          time=time, signals=signals)
    return run


def test_invariant_check_passes_a_conserved_momentum(runner):
    run = _wheel_run()
    report = runner.Report()
    runner._invariant_check(report, "project", "balancer-free", run, {
        "kind": "invariant", "tol": 1e-6,
        "terms": [{"signal": "Pivot/qdout", "coeff": 0.257},
                  {"signal": "WheelJ/qdout", "coeff": 0.002}],
    })
    assert report.checks == 1 and report.failures == 0


def test_invariant_check_fails_a_drifting_momentum(runner):
    run = _wheel_run(drift=1e-3)  # 1e-3 kg m^2/s against 0.06 -> ratio 1.7e-2
    report = runner.Report()
    runner._invariant_check(report, "project", "balancer-free", run, {
        "kind": "invariant", "tol": 1e-6,
        "terms": [{"signal": "Pivot/qdout", "coeff": 0.257},
                  {"signal": "WheelJ/qdout", "coeff": 0.002}],
    })
    assert report.checks == 1 and report.failures == 1


def test_invariant_scale_and_window(runner):
    run = _wheel_run(drift=1e-3)
    entry = {
        "kind": "invariant", "tol": 1e-6,
        "terms": [{"signal": "Pivot/qdout", "coeff": 0.257},
                  {"signal": "WheelJ/qdout", "coeff": 0.002}],
    }
    # An explicit scale much smaller than H makes the same run fail.
    report = runner.Report()
    runner._invariant_check(report, "project", "balancer-free", run,
                            {**entry, "scale": 1e-3})
    assert report.checks == 1 and report.failures == 1
    # A window before the excitation sees a constant H.
    report = runner.Report()
    runner._invariant_check(report, "project", "balancer-free", run,
                            {**entry, "from_t": 0.0, "to_t": 0.0})
    assert report.checks == 1 and report.failures == 1   # fewer than two samples


def test_invariant_check_rejects_bad_parameters(runner):
    run = _wheel_run()
    good = {
        "kind": "invariant", "tol": 1e-6,
        "terms": [{"signal": "Pivot/qdout", "coeff": 0.257}],
    }
    for broken in (
        {"tol": 1e-6},
        {"terms": []},
        {"terms": [{"signal": "missing", "coeff": 1.0}], "tol": 1e-6},
        {"terms": [{"coeff": 1.0}], "tol": 1e-6},
        {**good, "tol": 0.0},
        {**good, "from_t": 2.0, "to_t": 1.0},
        # The invariant is identically zero and no scale is given.
        {"terms": [{"signal": "Pivot/qdout", "coeff": 0.0}], "tol": 1e-6},
    ):
        report = runner.Report()
        runner._invariant_check(report, "project", "balancer-free", run, broken)
        assert report.checks == 1 and report.failures == 1, broken


# -------------------------------------------------------------------- planar_fk


def test_planar_fk_matches_the_analytic_arm(runner):
    time = np.linspace(0.0, 3.0, 301)
    q1 = 0.6 * np.sin(time)
    q2 = -0.4 * np.cos(time)
    length1, length2 = 0.4, 0.3
    signals = {
        "Joint1/qout": q1,
        "Joint2/qout": q2,
        "PoseTip/g[2]": length1 * np.cos(q1) + length2 * np.cos(q1 + q2),
        "PoseTip/g[3]": length1 * np.sin(q1) + length2 * np.sin(q1 + q2),
    }
    run = SimpleNamespace(model="arm", run_id="0" * 12, manifest={},
                          time=time, signals=signals)
    entry = {
        "kind": "planar_fk", "tip": ["PoseTip/g[2]", "PoseTip/g[3]"],
        "angles": ["Joint1/qout", "Joint2/qout"], "lengths": [length1, length2],
        "max_abs": 1e-12,
    }
    report = runner.Report()
    runner._planar_fk_check(report, "project", "arm", run, entry)
    assert report.checks == 1 and report.failures == 0

    # A 1 mm tip offset is caught by the 1e-6 m limit.
    bad = dict(signals)
    bad["PoseTip/g[2]"] = signals["PoseTip/g[2]"] + 1e-3
    report = runner.Report()
    runner._planar_fk_check(
        report, "project", "arm",
        SimpleNamespace(model="arm", run_id="0" * 12, manifest={}, time=time,
                        signals=bad),
        entry,
    )
    assert report.checks == 1 and report.failures == 1


def test_planar_fk_rejects_bad_parameters(runner):
    time = np.linspace(0.0, 1.0, 11)
    signals = {
        "Joint1/qout": np.zeros_like(time),
        "Joint2/qout": np.zeros_like(time),
        "PoseTip/g[2]": np.full_like(time, 0.7),
        "PoseTip/g[3]": np.zeros_like(time),
    }
    run = SimpleNamespace(model="arm", run_id="0" * 12, manifest={},
                          time=time, signals=signals)
    good = {
        "kind": "planar_fk", "tip": ["PoseTip/g[2]", "PoseTip/g[3]"],
        "angles": ["Joint1/qout", "Joint2/qout"], "lengths": [0.4, 0.3],
        "max_abs": 1e-6,
    }
    for broken in (
        {**good, "tip": ["PoseTip/g[2]"]},
        {**good, "angles": ["Joint1/qout", "Joint1/missing"]},
        {**good, "lengths": [0.4]},
        {**good, "lengths": [0.4, -0.3]},
        {**good, "max_abs": 0.0},
        {**good, "tip": ["PoseTip/g[2]", "PoseTip/g[3]", "PoseTip/g[1]"]},
    ):
        report = runner.Report()
        runner._planar_fk_check(report, "project", "arm", run, broken)
        assert report.checks == 1 and report.failures == 1, broken

