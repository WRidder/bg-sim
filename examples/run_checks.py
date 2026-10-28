# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.28", "numpy>=2.0"]
# ///
"""Run every example's acceptance checks through the real Julia worker.

This is the example lane of the integration gate (plan 9 and 10.3). For every
``examples/<name>/expected.json`` the script:

* starts one backend with the real worker on a free port and a temporary
  projects root (``uv run bgsim``; ``BGSIM_FAKE_WORKER`` is cleared);
* creates the example project through the HTTP API (``POST /api/projects``
  with ``{"name", "example"}``);
* starts each model's run through ``POST /api/projects/{p}/runs``, waits for
  the run to finish and reads ``<project>/runs/<id>/columns.f64`` with numpy;
* evaluates every check kind (``final_value``, ``cursor_value``, ``max_abs``,
  ``max_abs_le``, ``ratio``, ``zero_crossing``, ``period``, ``energy``,
  ``invariant``, ``planar_fk``, ``compare_signals``, ``rms_difference``,
  ``step_response``, ``ripple``, ``fft_peak`` and ``no_diagnostics``), prints one
  line per check and exits non-zero when any check fails.

``columns.f64`` is the columnar layout of plan 3.5: the whole time column
(``n`` Float64 values), then one contiguous column per manifest signal, in
manifest order. The manifest is the source of the signal order and of
``time.n``.

``expected.json`` shape::

    {"project": "dc-motor",
     "models": {
       "iconic": {"checks": [
         {"kind": "final_value", "signal": "Motor1/shaft.f", "t": 1.0,
          "value": 239.80815347721824, "rtol": 1e-4},
         {"kind": "cursor_value", "signal": "Motor1/shaft.f", "t": 0.2,
          "value": 239.8, "abs": 0.1},
         {"kind": "max_abs", "signal": "Rod/phi", "from_t": 0.01,
          "to_t": 1.0, "value": 0.186, "rtol": 1e-3},
         {"kind": "ratio", "signal": "Motor1/shaft.f", "signal_b": "Gear1/b.f",
          "t": 2.0, "value": 10.0, "rtol": 1e-4}]}},
     "compare": {"a": "iconic", "b": "bondgraph",
                 "signal_a": "Motor1/shaft.f", "signal_b": "IJ/p.f",
                 "from_t": 0.5, "max_abs": 1e-6}}

A model entry may also be a bare list of checks. ``compare`` may be a list of
such objects. ``rtol`` is relative to the expected value; ``abs`` is an extra
absolute tolerance. ``compare`` evaluates both signals on the union of the two
runs' time grids over ``[from_t, t1]``, so a different sample grid cannot hide
a peak. ``max_abs`` takes the largest absolute value over ``[from_t, to_t]``
(default the whole run); ``ratio`` evaluates ``signal / signal_b`` at ``t``
(default the final time), which checks a gear ratio or two speeds agreeing.

``zero_crossing`` finds the ``n``-th crossing of ``signal`` through ``level``
(default 0) in the given ``direction`` (``"down"`` by default, or ``"up"``) and
compares the crossing time against ``value``. Event instants are recorded twice
at the same ``t`` (left and right limits, plan 3.5), so equal consecutive times
are collapsed first and the last value of each group is used; the crossing time
is then linearly interpolated between the two samples that straddle the level. A
contact is accepted within ``1e-9`` of the signal scale, because the root finder
stops on the level with a residual of its tolerance (a bouncing height sits at
about ``+1e-16``, not at a negative value); a sample still on the near side only
counts when the next sample turns around::

    {"kind": "zero_crossing", "signal": "Ball1/h", "n": 1,
     "direction": "down", "value": 0.45152, "abs": 1e-6}

``compare_signals`` is the same-run form (two signals of one model, e.g. the two
RLC subsystems): it interpolates both onto the union of the run's own time grid
over ``[from_t, to_t]`` and checks the maximum absolute difference against
``max_abs``. ``rms_difference`` is its RMS form (the drivetrain's estimator error),
and ``max_abs_le`` is a *bound* (the voltage limit), not an equality: it passes when
the largest absolute value over the window is at most ``value``::

    {"kind": "compare_signals", "signal": "Iconic/C1/p.e",
     "signal_b": "Bondgraph/C1/p.e", "from_t": 0.0, "max_abs": 1e-8},
    {"kind": "max_abs_le", "signal": "V/p.e", "value": 24.0},
    {"kind": "rms_difference", "signal": "LQG/w_load_hat",
     "signal_b": "IW2/p.f", "from_t": 0.5, "to_t": 2.0, "value": 0.2},

``no_diagnostics`` takes ``codes`` and fails when any of them appears in the run
manifest; other codes (such as the expected W205 of a pure bond-graph island) are
printed but ignored::

    {"kind": "compare_signals", "signal": "Iconic/C1/p.e",
     "signal_b": "Bondgraph/C1/p.e", "from_t": 0.0, "max_abs": 1e-8},
    {"kind": "no_diagnostics", "codes": ["W201", "W202", "E106"]}

``step_response`` evaluates a step in one signal over ``[from_t, to_t]``.  ``value``
is the target, ``initial`` the value before the step (default: the first sample in
the window), and the band is ``settle_abs`` rad (or A, V, ...) when given, else
``settle`` (default 0.02) times the step size.  It measures the 10-90 % rise time,
the overshoot beyond the target (as a fraction of the step), the settling time (the
last sample outside the band, measured from ``step_t``, default ``from_t``) and the
final error at ``to_t``, then applies the optional ``max_rise_time``,
``max_overshoot`` and ``max_settling_time`` bounds.  It is one PASS/FAIL line (the
detail carries all four measurements)::

    {"kind": "step_response", "signal": "WmSens/p.f", "from_t": 0.05,
     "to_t": 0.29, "value": 100.0, "initial": 0.0, "settle_abs": 2.0,
     "max_rise_time": 0.08, "max_overshoot": 0.12,
     "max_settling_time": 0.25}

``ripple`` is the RMS (``measure = "rms"``, the default) or peak-to-peak
(``"pp"``) of the high-frequency component of ``signal`` over a steady window.  The
time column is collapsed (event instants appear twice), resampled on a uniform grid
at the median sample spacing, and ``highpass_hz`` (default 0: subtract the window
mean) removes everything below that corner with a centered moving average of
``round(fs / highpass_hz)`` samples.  It passes when the measured value is at most
``value``.  Two such checks (an unfiltered and a filtered signal) document a notch::

    {"kind": "ripple", "signal": "Iphase/y", "from_t": 1.0, "to_t": 1.15,
     "highpass_hz": 1000.0, "measure": "rms", "value": 0.8}

``fft_peak`` is the dominant frequency (Hz) of ``signal`` over ``[from_t, to_t]``
(default the whole run), compared with ``value`` through ``rtol``/``abs`` like the
other value checks.  It collapses equal event times, resamples the window on a
uniform grid at the median sample spacing, removes the DC term and the trend
(``detrend``: ``"linear"``, the default; ``"mean"`` subtracts only the mean;
``"none"`` keeps the signal as-is), applies a Hann taper to reduce leakage, and
searches the zero-padded FFT for the largest magnitude outside bin 0.  A parabolic
fit through the three samples around that peak gives a sub-bin frequency.  The
optional ``min_hz``/``max_hz`` restrict the search to a band (useful when a second
mode or a slow drift is present), and ``highpass_hz`` (default 0) subtracts a
centered moving average so a decaying envelope does not dominate a ring-down::

    {"kind": "fft_peak", "signal": "SInt/y", "from_t": 1.8, "to_t": 4.0,
     "min_hz": 0.5, "max_hz": 2.5, "value": 1.24, "rtol": 0.05}

``period`` measures the period of ``signal`` from two consecutive crossings of
``level`` (default 0) in ``direction`` (default ``"up"``).  ``n`` (default 1) is
the first crossing of the pair, so ``n = 1`` uses the first and second crossings.
It collapses the event rows and interpolates the crossings exactly as
``zero_crossing`` does, then compares the difference with ``value`` through
``rtol``/``abs`` (the M3 pendulum reads its period this way, and reports the
simple-reference period with a second check)::

    {"kind": "period", "signal": "Joint/qout", "direction": "up", "n": 1,
     "value": 1.4187960322, "rtol": 1e-5}

``energy`` is the X-MB1 planar-pendulum energy budget over a run.  It reads the
three momentum components ``p``, the joint angle ``q``, the composed CoM pose
(``pose`` is a component id such as ``"Compose/g[3]"``, or the base id
``"Compose/g"`` and then its y component is used) and the two pivot deflections
``d``, and computes, with ``J``, ``m``, ``kt`` and ``g0``::

    KE = 0.5 * (P1^2/J + P2^2/m + P3^2/m)
    h  = pose_y + sin(q)*d1 + cos(q)*d2
    E  = KE + m*g0*h + 0.5*kt*(d1^2 + d2^2)

It passes when ``max|E - E0| / swing <= tol`` (default ``tol = 1e-6``), where
``E0`` is the first sample of the window and ``swing = m*g0*L*(1 - cos(q0))``.
``q0`` is the given initial angle, default the first ``q`` sample of the window.
The detail prints E0, the drift in J, the swing and the ratio::

    {"kind": "energy", "p": ["Body/P[1]", "Body/P[2]", "Body/P[3]"],
     "q": "Joint/qout", "pose": "Compose/g[3]",
     "d": ["Joint/dout[1]", "Joint/dout[2]"],
     "J": 1e-4, "m": 1.0, "L": 0.5, "g0": 9.81, "kt": 1e8,
     "q0": 0.01, "tol": 1e-6}

``energy`` also has a **multi-body form** (X-MB2, additive; the pendulum form
above is unchanged).  ``bodies`` is a list of rigid bodies, each with its three
body-frame momenta ``p``, its ``J`` and ``m``, the y component ``pose`` of its
composed CoM pose and an optional list of ``corrections`` — one per compliant
joint between the world and the body, each a ``q`` (the **absolute** angle of
the joint's child frame) and the two deflections ``d``; the correction adds
``sin(q)*d1 + cos(q)*d2`` to the CoM height, exactly the pendulum's ``h`` term
generalised to a chain.  ``springs`` lists the ``kt``/``d`` pairs whose strain
``1/2 kt |d|^2`` is stored.  With ``swing`` the check is the drift form
(``max|E - E0| / swing <= tol``); with ``bound`` it is the bounded form
(``max|E| <= bound``) for a plant with a drive that does work::

    {"kind": "energy", "g0": 9.81,
     "bodies": [
       {"p": ["Body1/inertia/P[1]", "Body1/inertia/P[2]", "Body1/inertia/P[3]"],
        "J": 0.0266667, "m": 2.0, "pose": "PoseB1/g[3]",
        "corrections": [{"q": "Joint1/qout",
                         "d": ["Joint1/dout[1]", "Joint1/dout[2]"]}]},
       {"p": ["Body2/inertia/P[1]", "Body2/inertia/P[2]", "Body2/inertia/P[3]"],
        "J": 0.015, "m": 1.5, "pose": "PoseB2/g[3]",
        "corrections": [{"q": "Joint1/qout",
                         "d": ["Joint1/dout[1]", "Joint1/dout[2]"]},
                        {"q": "PoseJ2/g[1]",
                         "d": ["Joint2/dout[1]", "Joint2/dout[2]"]}]}],
     "springs": [{"kt": 1e8, "d": ["Joint1/dout[1]", "Joint1/dout[2]"]},
                 {"kt": 1e8, "d": ["Joint2/dout[1]", "Joint2/dout[2]"]}],
     "swing": 18.8768265045, "tol": 1e-6}

``invariant`` checks that a linear combination of recorded signals is constant:
``terms`` is a list of ``{"signal", "coeff"}``, the invariant is
``H = sum(coeff * signal)`` over ``[from_t, to_t]`` and the check passes when
``max|H - H0| <= tol * scale``.  ``scale`` defaults to ``max|H|`` over the window
(the invariant's own magnitude); give it explicitly when the invariant is
identically zero.  The reaction-wheel example reads the total angular momentum
about the pivot this way::

    {"kind": "invariant", "tol": 1e-6,
     "terms": [{"signal": "Pivot/qdout", "coeff": 0.257},
               {"signal": "WheelJ/qdout", "coeff": 0.002}]}

``planar_fk`` checks the composed pose chain of a 2-link planar arm against the
analytic forward kinematics of the **measured** joint angles: ``tip`` is the
composed tip pose's ``[x, y]`` signals, ``angles`` the two joint-angle signals and
``lengths`` the two link lengths.  It passes when ``max|tip - fk(q)| <= max_abs``
over the whole run; it is an identity between two recorded quantities (the pose
composition and the angles), so it is exact to round-off::

    {"kind": "planar_fk", "tip": ["PoseTip/g[2]", "PoseTip/g[3]"],
     "angles": ["Joint1/qout", "Joint2/qout"], "lengths": [0.4, 0.3],
     "max_abs": 1e-6}

A model entry may also carry ``"model"`` (the file to run when the key is only a
label) and ``"settings"`` (deep-merged into the model document before the run).
The pendulum uses that to read its 10 s energy window from the same 4 s model::

    {"models": {"pendulum-10s": {"model": "pendulum",
      "settings": {"t_end": 10.0, "output": {"points": 10001}},
      "checks": [...]}}}
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"

#: A cold worker may precompile; plan 5.12 budgets about a minute.
START_TIMEOUT = 300.0
#: One example run is seconds; this only catches a hung worker.
RUN_TIMEOUT = 180.0


# --------------------------------------------------------------------------- backend


def _free_port() -> int:
    """A port that is free on 127.0.0.1 right now."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _log_tail(path: Path, lines: int = 25) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"(could not read {path}: {exc})"
    return "\n".join(text.splitlines()[-lines:])


def _start_backend(projects_root: Path, log_path: Path) -> tuple[subprocess.Popen, int]:
    """Spawn ``uv run bgsim`` with the real worker; return the process and port."""
    port = _free_port()
    environment = os.environ.copy()
    environment["BGSIM_PORT_HTTP"] = str(port)
    environment["BGSIM_PROJECTS_ROOT"] = str(projects_root)
    environment["BGSIM_REPO"] = str(ROOT)
    environment.pop("BGSIM_FAKE_WORKER", None)
    # The inline-script environment is not the backend's; do not let `uv run`
    # inherit it and warn about the mismatch.
    environment.pop("VIRTUAL_ENV", None)

    uv = shutil.which("uv") or "uv"
    log = log_path.open("wb")
    options: dict[str, Any] = {}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        process = subprocess.Popen(
            [uv, "run", "bgsim"],
            cwd=ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            **options,
        )
    finally:
        log.close()
    return process, port


def _stop_backend(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=20.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10.0)


def _wait_for_worker(client: httpx.Client, process: subprocess.Popen, log_path: Path) -> None:
    """Wait until the backend serves and its worker reports ``ready``."""
    deadline = time.monotonic() + START_TIMEOUT
    last = "no answer"
    while time.monotonic() < deadline:
        code = process.poll()
        if code is not None:
            raise RuntimeError(
                f"the backend exited with code {code}:\n{_log_tail(log_path)}"
            )
        try:
            response = client.get("/api/health", timeout=5.0)
        except httpx.HTTPError as exc:
            last = f"{type(exc).__name__}: {exc}"
        else:
            if response.status_code == 200:
                state = response.json().get("worker")
                last = f"worker state {state!r}"
                if state == "ready":
                    return
            else:
                last = f"GET /api/health -> {response.status_code}"
        time.sleep(0.2)
    raise TimeoutError(f"the worker did not become ready within {START_TIMEOUT:g} s ({last})")


# --------------------------------------------------------------------------- runs


@dataclass
class Run:
    """One finished run: its manifest and its columnar data."""

    model: str
    run_id: str
    manifest: dict[str, Any]
    time: np.ndarray
    signals: dict[str, np.ndarray]


def _get_json(client: httpx.Client, path: str) -> Any:
    response = client.get(path)
    if response.status_code != 200:
        raise RuntimeError(f"GET {path} -> {response.status_code}: {response.text[:500]}")
    return response.json()


def _read_columns(
    run_dir: Path, manifest: dict[str, Any]
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """The time column and the signal columns, in manifest order."""
    metadata = manifest.get("signals") or []
    count = len(metadata)
    n = int(manifest["time"]["n"])
    path = run_dir / "columns.f64"
    if not path.is_file():
        raise RuntimeError(f"{path} does not exist")
    raw = np.fromfile(path, dtype="<f8")
    if raw.size != n * (count + 1):
        raise RuntimeError(
            f"{path} holds {raw.size} Float64 values, expected {n} x {count + 1}"
        )
    table = raw.reshape(count + 1, n)
    signals = {str(signal["id"]): table[index + 1] for index, signal in enumerate(metadata)}
    return table[0], signals


def _merge_settings(target: dict[str, Any], overlay: dict[str, Any]) -> None:
    """Deep-merge an expected.json ``settings`` overlay into a model document."""
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge_settings(target[key], value)
        else:
            target[key] = value


def _run_model(
    client: httpx.Client,
    project: str,
    project_dir: Path,
    model: str,
    settings: Any = None,
) -> Run:
    """Open the model, run it and read its columns once it is done."""
    model_document = _get_json(client, f"/api/projects/{project}/models/{model}")
    if settings is not None:
        if not isinstance(settings, dict):
            raise ValueError("'settings' must be an object")
        _merge_settings(model_document.setdefault("settings", {}), settings)
    response = client.post(f"/api/projects/{project}/runs", json={"model": model_document})
    if response.status_code != 201:
        raise RuntimeError(
            f"POST /api/projects/{project}/runs -> {response.status_code}: "
            f"{response.text[:500]}"
        )
    run_id = str(response.json()["runId"])

    deadline = time.monotonic() + RUN_TIMEOUT
    manifest: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        manifest = _get_json(client, f"/api/runs/{run_id}")
        if manifest.get("status") != "running":
            break
        time.sleep(0.05)
    if manifest is None:
        raise RuntimeError(f"run {run_id} was never created")
    status = manifest.get("status")
    if status != "done":
        diagnostics = manifest.get("diagnostics") or []
        raise RuntimeError(f"run {run_id} ended {status!r}: {json.dumps(diagnostics)[:800]}")

    time_column, signals = _read_columns(project_dir / "runs" / run_id, manifest)
    return Run(model=model, run_id=run_id, manifest=manifest, time=time_column, signals=signals)


# --------------------------------------------------------------------------- checks


class Report:
    """One PASS/FAIL line per check and the failure count."""

    def __init__(self) -> None:
        self.checks = 0
        self.failures = 0

    def check(self, ok: bool, label: str, detail: str) -> None:
        self.checks += 1
        if not ok:
            self.failures += 1
        print(f"{'PASS' if ok else 'FAIL'}  {label}: {detail}", flush=True)


def _tolerance(check: dict[str, Any], expected: float) -> tuple[float, str] | None:
    """The absolute tolerance from ``rtol``/``abs``, and how to print it."""
    rtol = check.get("rtol")
    atol = check.get("abs")
    if rtol is None and atol is None:
        return None
    total = 0.0
    parts: list[str] = []
    if rtol is not None:
        total += float(rtol) * abs(expected)
        parts.append(f"rtol {float(rtol):g}")
    if atol is not None:
        total += float(atol)
        parts.append(f"abs {float(atol):g}")
    return total, " + ".join(parts)


def _value_check(
    report: Report, project: str, model: str, run: Run, check: dict[str, Any], kind: str
) -> None:
    signal = str(check.get("signal", ""))
    label = f"{project}/{model} {signal} {kind}"
    if "t" not in check or "value" not in check:
        report.check(False, label, "the check needs 't' and 'value'")
        return
    if signal not in run.signals:
        report.check(False, label, f"unknown signal; the run records {len(run.signals)} signals")
        return
    t = float(check["t"])
    expected = float(check["value"])
    tolerance = _tolerance(check, expected)
    if tolerance is None:
        report.check(False, label, "the check needs 'rtol' or 'abs'")
        return
    total, tolerance_text = tolerance
    first = float(run.time[0])
    last = float(run.time[-1])
    if not (first <= t <= last):
        report.check(False, label, f"t={t:g} is outside the run's [{first:g}, {last:g}]")
        return
    measured = float(np.interp(t, run.time, run.signals[signal]))
    difference = abs(measured - expected)
    detail = (
        f"t={t:g} measured {measured:.12g}, expected {expected:.12g} "
        f"({tolerance_text}; |delta| {difference:.3g})"
    )
    report.check(difference <= total, label, detail)


def _max_abs_check(
    report: Report, project: str, model: str, run: Run, check: dict[str, Any]
) -> None:
    """The largest absolute value of a signal over a time window."""
    signal = str(check.get("signal", ""))
    label = f"{project}/{model} {signal} max_abs"
    if "value" not in check:
        report.check(False, label, "the check needs 'value'")
        return
    if signal not in run.signals:
        report.check(False, label, f"unknown signal; the run records {len(run.signals)} signals")
        return
    expected = abs(float(check["value"]))
    tolerance = _tolerance(check, expected)
    if tolerance is None:
        report.check(False, label, "the check needs 'rtol' or 'abs'")
        return
    total, tolerance_text = tolerance
    from_t = float(check.get("from_t", float(run.time[0])))
    to_t = float(check.get("to_t", float(run.time[-1])))
    mask = (run.time >= from_t) & (run.time <= to_t)
    if not mask.any():
        report.check(False, label, f"no samples in [{from_t:g}, {to_t:g}]")
        return
    values = run.signals[signal][mask]
    times = run.time[mask]
    index = int(np.argmax(np.abs(values)))
    measured = float(abs(values[index]))
    detail = (
        f"max|{signal}| over [{from_t:g}, {to_t:g}] measured {measured:.12g} "
        f"at t={times[index]:.6g}, expected {expected:.12g} "
        f"({tolerance_text}; |delta| {abs(measured - expected):.3g})"
    )
    report.check(abs(measured - expected) <= total, label, detail)


def _ratio_check(
    report: Report, project: str, model: str, run: Run, check: dict[str, Any]
) -> None:
    """`signal / signal_b` at one time (a gear ratio, or two speeds agreeing)."""
    signal = str(check.get("signal", ""))
    signal_b = str(check.get("signal_b", ""))
    label = f"{project}/{model} {signal} / {signal_b}"
    if "value" not in check:
        report.check(False, label, "the check needs 'value'")
        return
    for name in (signal, signal_b):
        if name not in run.signals:
            report.check(False, label, f"unknown signal {name!r}")
            return
    expected = float(check["value"])
    if expected == 0.0:
        report.check(False, label, "the expected ratio must not be zero")
        return
    tolerance = _tolerance(check, expected)
    if tolerance is None:
        report.check(False, label, "the check needs 'rtol' or 'abs'")
        return
    total, tolerance_text = tolerance
    t = float(check.get("t", float(run.time[-1])))
    if not (float(run.time[0]) <= t <= float(run.time[-1])):
        report.check(False, label, f"t={t:g} is outside the run")
        return
    value_a = float(np.interp(t, run.time, run.signals[signal]))
    value_b = float(np.interp(t, run.time, run.signals[signal_b]))
    if value_b == 0.0:
        report.check(False, label, f"{signal_b} is zero at t={t:g}")
        return
    measured = value_a / value_b
    detail = (
        f"t={t:g} {signal}={value_a:.12g}, {signal_b}={value_b:.12g} "
        f"ratio {measured:.12g}, expected {expected:.12g} "
        f"({tolerance_text}; |delta| {abs(measured - expected):.3g})"
    )
    report.check(abs(measured - expected) <= total, label, detail)


def _collapsed(times: np.ndarray, values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Collapse equal consecutive times to one row, keeping the last value.

    The recorder writes every event instant twice at the same ``t`` (left and
    right limits, plan 3.5). Keeping the *last* value of each group uses the
    post-event limit, so a crossing that ends exactly on the level is still one
    sample rather than two.
    """
    out_t: list[float] = []
    out_v: list[float] = []
    for t, value in zip(times.tolist(), values.tolist()):
        if out_t and t == out_t[-1]:
            out_v[-1] = value
        else:
            out_t.append(t)
            out_v.append(value)
    return np.asarray(out_t, dtype=float), np.asarray(out_v, dtype=float)


def _crossing_times(
    times: np.ndarray, values: np.ndarray, level: float, direction: str
) -> list[float]:
    """The interpolated instants where ``values`` crosses ``level``.

    Event instants appear twice, so ``times``/``values`` come from
    :func:`_collapsed`.  An event stops the solver on the level but leaves a
    residual of the order of its tolerance: a band relative to the signal scale
    lets the contact count as reaching the level, and a sample still on the near
    side only counts when the next sample turns around, so a slow approach is not
    counted early.
    """
    band = 1e-9 * max(1.0, float(np.max(np.abs(values))) if values.size else 0.0)
    crossings: list[float] = []
    for i in range(times.size - 1):
        before = float(values[i])
        after = float(values[i + 1])
        if direction == "down":
            reached = before > level and after <= level + band
            turned = after <= level or (
                i + 2 < times.size and float(values[i + 2]) > after
            )
        else:
            reached = before < level and after >= level - band
            turned = after >= level or (
                i + 2 < times.size and float(values[i + 2]) < after
            )
        if not reached or not turned:
            continue
        span = after - before
        if span == 0.0:
            continue
        fraction = (level - before) / span
        crossings.append(float(times[i] + fraction * (times[i + 1] - times[i])))
    return crossings


def _zero_crossing_check(
    report: Report, project: str, model: str, run: Run, check: dict[str, Any]
) -> None:
    """The ``n``-th upward or downward crossing of a signal through a level."""
    signal = str(check.get("signal", ""))
    direction = str(check.get("direction", "down"))
    label = f"{project}/{model} {signal} zero_crossing {direction}"
    if "value" not in check:
        report.check(False, label, "the check needs 'value'")
        return
    if signal not in run.signals:
        report.check(False, label, f"unknown signal; the run records {len(run.signals)} signals")
        return
    if direction not in {"down", "up"}:
        report.check(False, label, "'direction' must be 'down' or 'up'")
        return
    try:
        n = int(check.get("n", 1))
        level = float(check.get("level", 0.0))
    except (TypeError, ValueError):
        report.check(False, label, "'n' must be an integer and 'level' a number")
        return
    if n < 1:
        report.check(False, label, "'n' must be at least 1")
        return
    expected = float(check["value"])
    tolerance = _tolerance(check, expected)
    if tolerance is None:
        report.check(False, label, "the check needs 'rtol' or 'abs'")
        return
    total, tolerance_text = tolerance

    times, values = _collapsed(run.time, run.signals[signal])
    crossings = _crossing_times(times, values, level, direction)
    if len(crossings) < n:
        report.check(
            False,
            label,
            f"found {len(crossings)} {direction} crossing(s) of {level:g}, "
            f"the check needs #{n}",
        )
        return
    measured = crossings[n - 1]
    detail = (
        f"#{n} {direction} crossing of {level:g} at t={measured:.12g}, "
        f"expected {expected:.12g} ({tolerance_text}; |delta| {abs(measured - expected):.3g}; "
        f"{len(crossings)} crossing(s))"
    )
    report.check(abs(measured - expected) <= total, label, detail)


def _period_check(
    report: Report, project: str, model: str, run: Run, check: dict[str, Any]
) -> None:
    """The period between two consecutive crossings of a signal."""
    signal = str(check.get("signal", ""))
    direction = str(check.get("direction", "up"))
    label = f"{project}/{model} {signal} period {direction}"
    if "value" not in check:
        report.check(False, label, "the check needs 'value'")
        return
    if signal not in run.signals:
        report.check(False, label, f"unknown signal; the run records {len(run.signals)} signals")
        return
    if direction not in {"down", "up"}:
        report.check(False, label, "'direction' must be 'down' or 'up'")
        return
    try:
        n = int(check.get("n", 1))
        level = float(check.get("level", 0.0))
    except (TypeError, ValueError):
        report.check(False, label, "'n' must be an integer and 'level' a number")
        return
    if n < 1:
        report.check(False, label, "'n' must be at least 1")
        return
    try:
        expected = float(check["value"])
    except (TypeError, ValueError):
        report.check(False, label, "'value' must be a number")
        return
    if expected == 0.0:
        report.check(False, label, "the expected period must not be zero")
        return
    tolerance = _tolerance(check, expected)
    if tolerance is None:
        report.check(False, label, "the check needs 'rtol' or 'abs'")
        return
    total, tolerance_text = tolerance

    times, values = _collapsed(run.time, run.signals[signal])
    crossings = _crossing_times(times, values, level, direction)
    if len(crossings) < n + 1:
        report.check(
            False,
            label,
            f"found {len(crossings)} {direction} crossing(s) of {level:g}, "
            f"the check needs #{n} and #{n + 1}",
        )
        return
    first = crossings[n - 1]
    second = crossings[n]
    measured = second - first
    detail = (
        f"#{n} at t={first:.12g}, #{n + 1} at t={second:.12g}: period "
        f"{measured:.12g} s, expected {expected:.12g} "
        f"({tolerance_text}; |delta| {abs(measured - expected):.3g})"
    )
    report.check(abs(measured - expected) <= total, label, detail)


def _compare_signals_check(
    report: Report, project: str, model: str, run: Run, check: dict[str, Any]
) -> None:
    """Two signals of the same run, on the union grid over a time window."""
    signal = str(check.get("signal", ""))
    signal_b = str(check.get("signal_b", ""))
    label = f"{project}/{model} {signal} vs {signal_b}"
    if "max_abs" not in check:
        report.check(False, label, "the check needs 'max_abs'")
        return
    for name in (signal, signal_b):
        if name not in run.signals:
            report.check(False, label, f"unknown signal {name!r}")
            return
    try:
        limit = float(check["max_abs"])
    except (TypeError, ValueError):
        report.check(False, label, "'max_abs' must be a number")
        return
    first = float(run.time[0])
    last = float(run.time[-1])
    from_t = float(check.get("from_t", first))
    to_t = float(check.get("to_t", last))
    lower = max(from_t, first)
    upper = min(to_t, last)
    if not upper > lower:
        report.check(False, label, f"no samples in [{from_t:g}, {to_t:g}]")
        return
    window = (run.time >= lower) & (run.time <= upper)
    times = run.time[window]
    times_b = run.time[window]
    grid = np.union1d(times, times_b)
    values = np.interp(grid, run.time, run.signals[signal])
    values_b = np.interp(grid, run.time, run.signals[signal_b])
    difference = float(np.max(np.abs(values - values_b)))
    detail = (
        f"over [{lower:g}, {upper:g}] max|delta| {difference:.3g} "
        f"(limit {limit:g} over {grid.size} points)"
    )
    report.check(difference <= limit, label, detail)


def _max_abs_le_check(
    report: Report, project: str, model: str, run: Run, check: dict[str, Any]
) -> None:
    """The largest absolute value of a signal over a time window is at most ``value``."""
    signal = str(check.get("signal", ""))
    label = f"{project}/{model} {signal} max_abs_le"
    if "value" not in check:
        report.check(False, label, "the check needs 'value'")
        return
    if signal not in run.signals:
        report.check(False, label, f"unknown signal; the run records {len(run.signals)} signals")
        return
    limit = abs(float(check["value"]))
    from_t = float(check.get("from_t", float(run.time[0])))
    to_t = float(check.get("to_t", float(run.time[-1])))
    mask = (run.time >= from_t) & (run.time <= to_t)
    if not mask.any():
        report.check(False, label, f"no samples in [{from_t:g}, {to_t:g}]")
        return
    values = run.signals[signal][mask]
    times = run.time[mask]
    index = int(np.argmax(np.abs(values)))
    measured = float(abs(values[index]))
    detail = (
        f"max|{signal}| over [{from_t:g}, {to_t:g}] measured {measured:.12g} "
        f"at t={times[index]:.6g}, limit {limit:.12g}"
    )
    report.check(measured <= limit, label, detail)


def _signal_id(value: Any) -> str:
    """A signal id from an expected.json entry (strings only)."""
    if not isinstance(value, str) or not value:
        raise ValueError("signal ids must be non-empty strings")
    return value


def _signal_list(value: Any, length: int, what: str) -> list[str]:
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"'{what}' must be a list of {length} signal ids")
    return [_signal_id(item) for item in value]


def _pose_y(value: Any) -> str:
    """The Composed-pose y signal: a component id, or a base id for component 3."""
    signal = _signal_id(value)
    return signal if signal.endswith("]") else f"{signal}[3]"


def _energy_check(
    report: Report, project: str, model: str, run: Run, check: dict[str, Any]
) -> None:
    """The planar-pendulum energy budget ``KE + m*g*h + 1/2 kt |d|^2``.

    X-MB1's specialised kind (X-MB6 generalises it): the body momenta, the joint
    angle, the composed CoM pose and the pivot deflection are read from the run and
    the total mechanical energy must stay constant relative to the KE/PE swing.
    The multi-body form (``bodies``/``springs``, X-MB2) is handled by
    :func:`_multi_body_energy`, so the pendulum's budget is unchanged.
    """
    if "bodies" in check:
        _multi_body_energy(report, project, model, run, check)
        return
    label = f"{project}/{model} energy"
    try:
        momenta = _signal_list(check.get("p"), 3, "p")
        deflection = _signal_list(check.get("d"), 2, "d")
        q_signal = _signal_id(check.get("q"))
        pose_signal = _pose_y(check.get("pose"))
        inertia = float(check["J"])
        mass = float(check["m"])
        length = float(check["L"])
        gravity = float(check["g0"])
        stiffness = float(check["kt"])
        tolerance = float(check.get("tol", 1e-6))
    except (KeyError, TypeError, ValueError) as exc:
        report.check(False, label, f"malformed energy check: {exc}")
        return
    if inertia <= 0.0 or mass <= 0.0 or length <= 0.0 or gravity <= 0.0:
        report.check(False, label, "J, m, L and g0 must be positive")
        return
    if stiffness < 0.0:
        report.check(False, label, "'kt' must not be negative")
        return
    if tolerance <= 0.0:
        report.check(False, label, "'tol' must be positive")
        return
    for signal in [*momenta, q_signal, pose_signal, *deflection]:
        if signal not in run.signals:
            report.check(False, label, f"unknown signal {signal!r}")
            return

    first = float(run.time[0])
    last = float(run.time[-1])
    try:
        from_t = float(check.get("from_t", first))
        to_t = float(check.get("to_t", last))
    except (TypeError, ValueError):
        report.check(False, label, "'from_t' and 'to_t' must be numbers")
        return
    window = (run.time >= from_t) & (run.time <= to_t)
    if int(np.count_nonzero(window)) < 2:
        report.check(False, label, f"no samples in [{from_t:g}, {to_t:g}]")
        return

    angular, linear_x, linear_y = (run.signals[signal][window] for signal in momenta)
    q = run.signals[q_signal][window]
    pose_y = run.signals[pose_signal][window]
    d1, d2 = (run.signals[signal][window] for signal in deflection)
    samples = np.column_stack(
        [angular, linear_x, linear_y, q, pose_y, d1, d2]
    )
    if not np.all(np.isfinite(samples)):
        report.check(False, label, "the energy signals hold a non-finite sample")
        return
    try:
        q0 = float(check["q0"]) if "q0" in check else float(q[0])
    except (TypeError, ValueError):
        report.check(False, label, "'q0' must be a number")
        return
    swing = mass * gravity * length * (1.0 - np.cos(q0))
    if not swing > 0.0:
        report.check(False, label, "the swing is zero (q0 = 0): no energy scale")
        return

    kinetic = 0.5 * (angular**2 / inertia + linear_x**2 / mass + linear_y**2 / mass)
    height = pose_y + np.sin(q) * d1 + np.cos(q) * d2
    spring = 0.5 * stiffness * (d1**2 + d2**2)
    total_energy = kinetic + mass * gravity * height + spring
    drift = float(np.max(np.abs(total_energy - total_energy[0])))
    ratio = drift / swing
    detail = (
        f"over [{from_t:g}, {to_t:g}] E0 {total_energy[0]:.12g} J, "
        f"max|E - E0| {drift:.6g} J, swing {swing:.6g} J, ratio {ratio:.6g} "
        f"(tol {tolerance:g}, {int(np.count_nonzero(window))} samples)"
    )
    report.check(ratio <= tolerance, label, detail)


def _multi_body_energy(
    report: Report, project: str, model: str, run: Run, check: dict[str, Any]
) -> None:
    """The multi-body mechanical energy (X-MB2's ``bodies``/``springs`` form).

    ``E = sum_b [ 1/2 p^T M^-1 p + m g (pose_y + sum_corr (sin q d1 + cos q d2)) ]
    + sum_springs 1/2 kt |d|^2``.  The drift form normalises ``max|E - E0|`` by
    ``swing`` and compares with ``tol``; the bounded form compares ``max|E|`` with
    ``bound`` (a plant with a drive that does work).
    """
    label = f"{project}/{model} energy"
    bodies = check.get("bodies")
    if not isinstance(bodies, list) or not bodies:
        report.check(False, label, "'bodies' must be a non-empty list")
        return
    try:
        gravity = float(check.get("g0", 9.81))
        tolerance = float(check.get("tol", 1e-6))
        wanted: list[str] = []
        body_specs: list[dict[str, Any]] = []
        for body in bodies:
            if not isinstance(body, dict):
                raise TypeError("each body must be an object")
            momenta = _signal_list(body.get("p"), 3, "p")
            pose = _pose_y(body.get("pose"))
            inertia = float(body["J"])
            mass = float(body["m"])
            if inertia <= 0.0 or mass <= 0.0:
                raise ValueError("a body needs J > 0 and m > 0")
            corrections: list[tuple[str, list[str]]] = []
            for correction in body.get("corrections") or []:
                if not isinstance(correction, dict):
                    raise TypeError("a correction must be an object")
                corrections.append(
                    (
                        _signal_id(correction.get("q")),
                        _signal_list(correction.get("d"), 2, "d"),
                    )
                )
            body_specs.append(
                {
                    "p": momenta,
                    "pose": pose,
                    "J": inertia,
                    "m": mass,
                    "corrections": corrections,
                }
            )
            wanted += [*momenta, pose]
            for q_signal, deflection in corrections:
                wanted += [q_signal, *deflection]
        springs: list[tuple[float, list[str]]] = []
        for spring in check.get("springs") or []:
            if not isinstance(spring, dict):
                raise TypeError("a spring must be an object")
            stiffness = float(spring["kt"])
            if stiffness < 0.0:
                raise ValueError("a spring needs kt >= 0")
            springs.append((stiffness, _signal_list(spring.get("d"), 2, "d")))
            wanted += springs[-1][1]
        if gravity <= 0.0:
            report.check(False, label, "'g0' must be positive")
            return
        if tolerance <= 0.0:
            report.check(False, label, "'tol' must be positive")
            return
        drift_form = "swing" in check
        bound_form = "bound" in check
        if drift_form == bound_form:
            report.check(False, label, "give exactly one of 'swing' (drift) and 'bound'")
            return
        swing = float(check["swing"]) if drift_form else 0.0
        bound = float(check["bound"]) if bound_form else 0.0
        if drift_form and not swing > 0.0:
            report.check(False, label, "'swing' must be positive")
            return
        if bound_form and not bound > 0.0:
            report.check(False, label, "'bound' must be positive")
            return
        from_t = float(check.get("from_t", float(run.time[0])))
        to_t = float(check.get("to_t", float(run.time[-1])))
    except (KeyError, TypeError, ValueError) as exc:
        report.check(False, label, f"malformed energy check: {exc}")
        return
    for signal in wanted:
        if signal not in run.signals:
            report.check(False, label, f"unknown signal {signal!r}")
            return
    window = (run.time >= from_t) & (run.time <= to_t)
    if int(np.count_nonzero(window)) < 2:
        report.check(False, label, f"no samples in [{from_t:g}, {to_t:g}]")
        return

    total = np.zeros(int(np.count_nonzero(window)))
    kinetic_all = np.zeros_like(total)
    potential_all = np.zeros_like(total)
    spring_all = np.zeros_like(total)
    for body in body_specs:
        angular, linear_x, linear_y = (
            run.signals[signal][window] for signal in body["p"]
        )
        samples = np.column_stack([angular, linear_x, linear_y])
        if not np.all(np.isfinite(samples)):
            report.check(False, label, "the energy signals hold a non-finite sample")
            return
        height = run.signals[body["pose"]][window].astype(float, copy=True)
        for q_signal, deflection in body["corrections"]:
            q = run.signals[q_signal][window]
            d1, d2 = (run.signals[signal][window] for signal in deflection)
            height = height + np.sin(q) * d1 + np.cos(q) * d2
        kinetic = 0.5 * (
            angular**2 / body["J"] + linear_x**2 / body["m"] + linear_y**2 / body["m"]
        )
        potential = body["m"] * gravity * height
        kinetic_all = kinetic_all + kinetic
        potential_all = potential_all + potential
        total = total + kinetic + potential
    for stiffness, deflection in springs:
        d1, d2 = (run.signals[signal][window] for signal in deflection)
        strain = 0.5 * stiffness * (d1**2 + d2**2)
        spring_all = spring_all + strain
        total = total + strain
    if not np.all(np.isfinite(total)):
        report.check(False, label, "the energy budget holds a non-finite sample")
        return
    if drift_form:
        drift = float(np.max(np.abs(total - total[0])))
        ratio = drift / swing
        detail = (
            f"over [{from_t:g}, {to_t:g}] E0 {total[0]:.12g} J, "
            f"max|E - E0| {drift:.6g} J, swing {swing:.6g} J, ratio {ratio:.6g} "
            f"(tol {tolerance:g}, {total.size} samples)"
        )
        report.check(ratio <= tolerance, label, detail)
        return
    peak = float(np.max(np.abs(total)))
    detail = (
        f"over [{from_t:g}, {to_t:g}] E0 {total[0]:.12g} J, max|E| {peak:.6g} J "
        f"(KE {float(np.max(kinetic_all)):.6g}, PE {float(np.max(potential_all)):.6g}, "
        f"strain {float(np.max(spring_all)):.6g}), bound {bound:.6g} J, "
        f"{total.size} samples"
    )
    report.check(peak <= bound, label, detail)


def _invariant_check(
    report: Report, project: str, model: str, run: Run, check: dict[str, Any]
) -> None:
    """A linear combination of recorded signals is constant over a time window.

    ``H = sum(coeff * signal)``; the check passes when ``max|H - H0| <= tol *
    scale``, with ``scale`` the explicit value or ``max|H|`` over the window.
    """
    terms = check.get("terms")
    label = f"{project}/{model} invariant"
    if not isinstance(terms, list) or not terms:
        report.check(False, label, "'terms' must be a non-empty list")
        return
    try:
        pairs: list[tuple[str, float]] = []
        for term in terms:
            if not isinstance(term, dict):
                raise TypeError("each term must be an object")
            pairs.append((_signal_id(term.get("signal")), float(term["coeff"])))
        tolerance = float(check.get("tol", 1e-6))
        explicit_scale = float(check["scale"]) if "scale" in check else None
        from_t = float(check.get("from_t", float(run.time[0])))
        to_t = float(check.get("to_t", float(run.time[-1])))
    except (KeyError, TypeError, ValueError) as exc:
        report.check(False, label, f"malformed invariant check: {exc}")
        return
    if tolerance <= 0.0:
        report.check(False, label, "'tol' must be positive")
        return
    for signal, _ in pairs:
        if signal not in run.signals:
            report.check(False, label, f"unknown signal {signal!r}")
            return
    window = (run.time >= from_t) & (run.time <= to_t)
    if int(np.count_nonzero(window)) < 2:
        report.check(False, label, f"no samples in [{from_t:g}, {to_t:g}]")
        return
    invariant = np.zeros(int(np.count_nonzero(window)))
    for signal, coefficient in pairs:
        invariant = invariant + coefficient * run.signals[signal][window]
    if not np.all(np.isfinite(invariant)):
        report.check(False, label, "the invariant holds a non-finite sample")
        return
    drift = float(np.max(np.abs(invariant - invariant[0])))
    scale = explicit_scale if explicit_scale is not None else float(
        np.max(np.abs(invariant))
    )
    if scale is None or not scale > 0.0:
        report.check(
            False,
            label,
            "the invariant is identically zero: give 'scale' explicitly",
        )
        return
    ratio = drift / scale
    terms_text = " + ".join(
        f"{coefficient:g}*{signal}" for signal, coefficient in pairs
    )
    detail = (
        f"over [{from_t:g}, {to_t:g}] H0 {invariant[0]:.12g}, "
        f"max|H - H0| {drift:.6g}, scale {scale:.6g}, ratio {ratio:.6g} "
        f"(tol {tolerance:g}, {invariant.size} samples; {terms_text})"
    )
    report.check(ratio <= tolerance, label, detail)


def _planar_fk_check(
    report: Report, project: str, model: str, run: Run, check: dict[str, Any]
) -> None:
    """The composed planar tip pose against the analytic forward kinematics.

    ``x = L1 cos q1 + L2 cos(q1 + q2)`` and the same in ``y``; the composed pose is
    an exact composition of the same angles, so the identity holds to round-off and
    ``max_abs`` is the tolerance on both components.
    """
    label = f"{project}/{model} planar_fk"
    try:
        tip = _signal_list(check.get("tip"), 2, "tip")
        angles = _signal_list(check.get("angles"), 2, "angles")
        lengths = [float(value) for value in check.get("lengths") or []]
        limit = float(check["max_abs"])
    except (KeyError, TypeError, ValueError) as exc:
        report.check(False, label, f"malformed planar_fk check: {exc}")
        return
    if len(lengths) != 2 or any(length <= 0.0 for length in lengths):
        report.check(False, label, "'lengths' must be two positive link lengths")
        return
    if limit <= 0.0:
        report.check(False, label, "'max_abs' must be positive")
        return
    for signal in [*tip, *angles]:
        if signal not in run.signals:
            report.check(False, label, f"unknown signal {signal!r}")
            return
    q1 = run.signals[angles[0]]
    q2 = run.signals[angles[1]]
    x = lengths[0] * np.cos(q1) + lengths[1] * np.cos(q1 + q2)
    y = lengths[0] * np.sin(q1) + lengths[1] * np.sin(q1 + q2)
    delta_x = float(np.max(np.abs(x - run.signals[tip[0]])))
    delta_y = float(np.max(np.abs(y - run.signals[tip[1]])))
    worst = max(delta_x, delta_y)
    detail = (
        f"max|delta| x {delta_x:.6g} m, y {delta_y:.6g} m over {run.time.size} "
        f"samples (lengths {lengths[0]:g} / {lengths[1]:g} m, limit {limit:g} m)"
    )
    report.check(worst <= limit, label, detail)


def _rms_difference_check(
    report: Report, project: str, model: str, run: Run, check: dict[str, Any]
) -> None:
    """The RMS of ``signal - signal_b`` over a time window is at most ``value``."""
    signal = str(check.get("signal", ""))
    signal_b = str(check.get("signal_b", ""))
    label = f"{project}/{model} rms({signal} - {signal_b})"
    if "value" not in check:
        report.check(False, label, "the check needs 'value'")
        return
    for name in (signal, signal_b):
        if name not in run.signals:
            report.check(False, label, f"unknown signal {name!r}")
            return
    try:
        limit = float(check["value"])
    except (TypeError, ValueError):
        report.check(False, label, "'value' must be a number")
        return
    first = float(run.time[0])
    last = float(run.time[-1])
    from_t = float(check.get("from_t", first))
    to_t = float(check.get("to_t", last))
    lower = max(from_t, first)
    upper = min(to_t, last)
    mask = (run.time >= lower) & (run.time <= upper)
    if not mask.any():
        report.check(False, label, f"no samples in [{from_t:g}, {to_t:g}]")
        return
    times = run.time[mask]
    difference = run.signals[signal][mask] - run.signals[signal_b][mask]
    measured = float(np.sqrt(np.mean(difference**2)))
    detail = (
        f"over [{lower:g}, {upper:g}] RMS|delta| {measured:.6g} "
        f"(limit {limit:g} over {times.size} points)"
    )
    report.check(measured <= limit, label, detail)


def _no_diagnostics_check(
    report: Report, project: str, model: str, run: Run, check: dict[str, Any]
) -> None:
    """The forbidden diagnostic codes are absent from the run manifest."""
    codes = check.get("codes")
    if not isinstance(codes, list) or not all(isinstance(code, str) for code in codes):
        report.check(False, f"{project}/{model} no_diagnostics", "'codes' must be a list of strings")
        return
    label = f"{project}/{model} no {'/'.join(codes)}"
    diagnostics = run.manifest.get("diagnostics") or []
    found = sorted(
        {
            str(entry.get("code"))
            for entry in diagnostics
            if isinstance(entry, dict) and entry.get("code") in codes
        }
    )
    present = sorted(
        {
            str(entry.get("code"))
            for entry in diagnostics
            if isinstance(entry, dict) and entry.get("code") is not None
        }
    )
    detail = (
        "forbidden code(s) reported: " + ", ".join(found)
        if found
        else "none reported (run diagnostics: " + (", ".join(present) or "none") + ")"
    )
    report.check(not found, label, detail)


def _step_response_check(
    report: Report, project: str, model: str, run: Run, check: dict[str, Any]
) -> None:
    """Rise time, overshoot, settling and final error of a step in one signal."""
    signal = str(check.get("signal", ""))
    label = f"{project}/{model} {signal} step_response"
    if "value" not in check:
        report.check(False, label, "the check needs 'value' (the target)")
        return
    if signal not in run.signals:
        report.check(False, label, f"unknown signal; the run records {len(run.signals)} signals")
        return
    try:
        target = float(check["value"])
    except (TypeError, ValueError):
        report.check(False, label, "'value' must be a number")
        return
    first = float(run.time[0])
    last = float(run.time[-1])
    from_t = float(check.get("from_t", first))
    to_t = float(check.get("to_t", last))
    window = (run.time >= from_t) & (run.time <= to_t)
    if not window.any():
        report.check(False, label, f"no samples in [{from_t:g}, {to_t:g}]")
        return
    times, values = _collapsed(run.time[window], run.signals[signal][window])
    if times.size < 2:
        report.check(False, label, "the window has fewer than two samples")
        return
    try:
        initial = float(check["initial"]) if "initial" in check else float(values[0])
        step_t = float(check.get("step_t", from_t))
        low = float(check.get("rise_low", 0.1))
        high = float(check.get("rise_high", 0.9))
        settle_fraction = float(check.get("settle", 0.02))
        settle_abs = float(check["settle_abs"]) if "settle_abs" in check else None
    except (TypeError, ValueError):
        report.check(False, label, "the step parameters must be numbers")
        return
    if not 0.0 <= low < high <= 1.0:
        report.check(False, label, "rise_low/rise_high must satisfy 0 <= low < high <= 1")
        return
    delta = target - initial
    scale = abs(delta)
    if scale == 0.0:
        report.check(False, label, "the target equals the initial value (no step)")
        return
    band = settle_abs if settle_abs is not None else settle_fraction * scale

    if delta > 0.0:
        overshoot = max(0.0, (float(np.max(values)) - target) / scale)
    else:
        overshoot = max(0.0, (target - float(np.min(values))) / scale)

    def crossing(level: float) -> float | None:
        if values[0] == level:
            return float(times[0])
        for index in range(times.size - 1):
            before = float(values[index])
            after = float(values[index + 1])
            if before == after:
                continue
            if (before - level) * (after - level) <= 0.0:
                fraction = (level - before) / (after - before)
                return float(times[index] + fraction * (times[index + 1] - times[index]))
        return None

    t_low = crossing(initial + low * delta)
    t_high = crossing(initial + high * delta)
    rise = None if t_low is None or t_high is None else max(0.0, t_high - t_low)

    outside = np.abs(values - target) > band
    if bool(np.any(outside)):
        last_outside = int(np.nonzero(outside)[0][-1])
        settling = max(0.0, float(times[last_outside]) - step_t)
    else:
        settling = 0.0
    final_error = abs(float(values[-1]) - target)

    failures: list[str] = []
    if final_error > band:
        failures.append(f"final error {final_error:.4g} > band {band:.4g}")
    if rise is None:
        failures.append("the signal never crosses the rise levels")
    else:
        limit = check.get("max_rise_time")
        if limit is not None and rise > float(limit):
            failures.append(f"rise {rise:.4g} s > {float(limit):.4g} s")
    limit = check.get("max_overshoot")
    if limit is not None and overshoot > float(limit):
        failures.append(f"overshoot {100.0 * overshoot:.2f} % > {100.0 * float(limit):.2f} %")
    limit = check.get("max_settling_time")
    if limit is not None and settling > float(limit):
        failures.append(f"settling {settling:.4g} s > {float(limit):.4g} s")

    rise_text = "n/a" if rise is None else f"{rise:.4g} s"
    detail = (
        f"step {initial:.6g} -> {target:.6g} over [{from_t:g}, {to_t:g}]: "
        f"rise {rise_text}, overshoot {100.0 * overshoot:.2f} %, "
        f"settling {settling:.4g} s (band {band:.4g}), final error {final_error:.4g}"
    )
    if failures:
        detail += "; FAIL: " + "; ".join(failures)
    report.check(not failures, label, detail)


def _ripple_check(
    report: Report, project: str, model: str, run: Run, check: dict[str, Any]
) -> None:
    """RMS or peak-to-peak of the high-frequency component over a steady window."""
    signal = str(check.get("signal", ""))
    measure = str(check.get("measure", "rms"))
    label = f"{project}/{model} {signal} ripple ({measure})"
    if signal not in run.signals:
        report.check(False, label, f"unknown signal; the run records {len(run.signals)} signals")
        return
    if "value" not in check:
        report.check(False, label, "the check needs 'value' (the limit)")
        return
    if measure not in {"rms", "pp"}:
        report.check(False, label, "'measure' must be 'rms' or 'pp'")
        return
    try:
        limit = float(check["value"])
        highpass = float(check.get("highpass_hz", 0.0))
    except (TypeError, ValueError):
        report.check(False, label, "'value' and 'highpass_hz' must be numbers")
        return
    first = float(run.time[0])
    last = float(run.time[-1])
    from_t = float(check.get("from_t", first))
    to_t = float(check.get("to_t", last))
    window = (run.time >= from_t) & (run.time <= to_t)
    if not window.any():
        report.check(False, label, f"no samples in [{from_t:g}, {to_t:g}]")
        return
    times, values = _collapsed(run.time[window], run.signals[signal][window])
    if times.size < 3:
        report.check(False, label, "the window has fewer than three samples")
        return
    steps = np.diff(times)
    steps = steps[steps > 0.0]
    if steps.size == 0:
        report.check(False, label, "the window has no positive sample spacing")
        return
    dt = float(np.median(steps))
    grid = np.arange(float(times[0]), float(times[-1]) + 0.5 * dt, dt)
    if grid.size < 3:
        report.check(False, label, "the resampled window has fewer than three samples")
        return
    samples = np.interp(grid, times, values)
    if highpass > 0.0:
        width = max(2, int(round(1.0 / (dt * highpass))))
        pad = width // 2
        padded = np.pad(samples, (pad, pad), mode="edge")
        average = np.convolve(padded, np.ones(width) / width, mode="valid")[: samples.size]
        residual = samples - average
        cutoff_text = f"high-pass {highpass:g} Hz (moving average {width} samples)"
    else:
        residual = samples - float(np.mean(samples))
        cutoff_text = "window mean removed"
    if measure == "rms":
        measured = float(np.sqrt(np.mean(residual**2)))
    else:
        measured = float(np.max(residual) - np.min(residual))
    detail = (
        f"over [{from_t:g}, {to_t:g}] at {1.0 / dt:.0f} Hz, {cutoff_text}: "
        f"{measure} {measured:.6g} (limit {limit:g}, {grid.size} samples)"
    )
    report.check(measured <= limit, label, detail)


def _resample_window(
    times: np.ndarray, values: np.ndarray
) -> tuple[np.ndarray, float] | None:
    """Collapse event pairs and resample on the uniform grid of the median spacing.

    Returns the grid and its spacing, or ``None`` when the window has fewer than
    three distinct times or no positive spacing.  ``fft_peak`` uses this so a run's
    non-uniform event rows cannot distort the sample rate; ``ripple`` has the same
    steps inline.
    """
    times, values = _collapsed(times, values)
    if times.size < 3:
        return None
    steps = np.diff(times)
    steps = steps[steps > 0.0]
    if steps.size == 0:
        return None
    dt = float(np.median(steps))
    if not np.isfinite(dt) or dt <= 0.0:
        return None
    grid = np.arange(float(times[0]), float(times[-1]) + 0.5 * dt, dt)
    if grid.size < 3:
        return None
    return np.interp(grid, times, values), dt


def _fft_peak_frequency(
    samples: np.ndarray,
    dt: float,
    detrend: str = "linear",
    min_hz: float = 0.0,
    max_hz: float | None = None,
    highpass_hz: float = 0.0,
) -> float | None:
    """The dominant frequency (Hz) of a uniformly sampled window.

    The DC term and the trend are removed before a Hann taper; the FFT is zero-padded
    so the peak is well resolved, and a parabolic fit through the three log-magnitude
    samples around the maximum gives a sub-bin estimate.  ``highpass_hz`` (> 0)
    subtracts a centered moving average of ``round(fs / highpass_hz)`` samples, which
    removes a slow decay envelope that would otherwise dominate the spectrum of a
    free-decay ring-down.  Returns ``None`` when the band holds no candidate (e.g. an
    all-zero or constant signal).
    """
    values = np.asarray(samples, dtype=float)
    count = values.size
    if count < 4 or not np.isfinite(dt) or dt <= 0.0:
        return None
    if not np.all(np.isfinite(values)):
        return None
    scale = float(np.max(np.abs(values)))
    if not np.isfinite(scale) or scale == 0.0:
        return None
    if detrend == "linear":
        positions = np.arange(count, dtype=float)
        slope, offset = np.polyfit(positions, values, 1)
        residual = values - (slope * positions + offset)
    elif detrend == "mean":
        residual = values - float(np.mean(values))
    elif detrend == "none":
        residual = values
    else:
        return None
    if highpass_hz > 0.0:
        width = max(2, int(round(1.0 / (dt * highpass_hz))))
        pad = width // 2
        padded = np.pad(residual, (pad, pad), mode="edge")
        average = np.convolve(padded, np.ones(width) / width, mode="valid")[: count]
        residual = residual - average
    if float(np.max(np.abs(residual))) <= 1e-12 * scale:
        return None                      # flat window: no spectral content at all
    tapered = residual * np.hanning(count)
    if not np.any(tapered):
        return None
    size = 1 << int(np.ceil(np.log2(max(4 * count, 1024))))
    spectrum = np.abs(np.fft.rfft(tapered, n=size))
    frequencies = np.fft.rfftfreq(size, d=dt)
    mask = np.zeros(frequencies.size, dtype=bool)
    mask[1:] = True                      # ignore the DC bin explicitly
    if min_hz > 0.0:
        mask &= frequencies >= min_hz
    if max_hz is not None:
        mask &= frequencies <= max_hz
    if not np.any(mask):
        return None
    candidates = np.flatnonzero(mask)
    peak = int(candidates[int(np.argmax(spectrum[mask]))])
    if not spectrum[peak] > 0.0:
        return None
    frequency = float(frequencies[peak])
    if 0 < peak < spectrum.size - 1:
        left = float(np.log(spectrum[peak - 1] + 1e-300))
        middle = float(np.log(spectrum[peak] + 1e-300))
        right = float(np.log(spectrum[peak + 1] + 1e-300))
        curvature = left - 2.0 * middle + right
        if curvature < 0.0:
            fraction = 0.5 * (left - right) / curvature
            if abs(fraction) <= 0.5:
                frequency += fraction * float(frequencies[1] - frequencies[0])
    return frequency


def _fft_peak_check(
    report: Report, project: str, model: str, run: Run, check: dict[str, Any]
) -> None:
    """The dominant frequency of a signal over a window."""
    signal = str(check.get("signal", ""))
    label = f"{project}/{model} {signal} fft_peak"
    if signal not in run.signals:
        report.check(False, label, f"unknown signal; the run records {len(run.signals)} signals")
        return
    if "value" not in check:
        report.check(False, label, "the check needs 'value' (the expected frequency in Hz)")
        return
    try:
        expected = float(check["value"])
        detrend = str(check.get("detrend", "linear"))
        min_hz = float(check.get("min_hz", 0.0))
        max_hz = float(check["max_hz"]) if "max_hz" in check else None
        highpass_hz = float(check.get("highpass_hz", 0.0))
    except (TypeError, ValueError):
        report.check(
            False, label,
            "'value', 'min_hz', 'max_hz', 'highpass_hz' and 'detrend' must be valid",
        )
        return
    if detrend not in {"linear", "mean", "none"}:
        report.check(False, label, "'detrend' must be 'linear', 'mean' or 'none'")
        return
    if expected <= 0.0:
        report.check(False, label, "the expected frequency must be positive")
        return
    if min_hz < 0.0 or (max_hz is not None and max_hz <= min_hz):
        report.check(False, label, "the band needs 0 <= min_hz < max_hz")
        return
    if highpass_hz < 0.0:
        report.check(False, label, "'highpass_hz' must not be negative")
        return
    tolerance = _tolerance(check, expected)
    if tolerance is None:
        report.check(False, label, "the check needs 'rtol' or 'abs'")
        return
    total, tolerance_text = tolerance
    first = float(run.time[0])
    last = float(run.time[-1])
    from_t = float(check.get("from_t", first))
    to_t = float(check.get("to_t", last))
    window = (run.time >= from_t) & (run.time <= to_t)
    if not window.any():
        report.check(False, label, f"no samples in [{from_t:g}, {to_t:g}]")
        return
    resampled = _resample_window(run.time[window], run.signals[signal][window])
    if resampled is None:
        report.check(False, label, "the window has too few samples to transform")
        return
    samples, dt = resampled
    measured = _fft_peak_frequency(
        samples, dt, detrend, min_hz, max_hz, highpass_hz
    )
    if measured is None:
        report.check(False, label, "the window has no spectral peak in the requested band")
        return
    band = f"[{min_hz:g}" + (", -]" if max_hz is None else f", {max_hz:g}]")
    filter_text = f", high-pass {highpass_hz:g} Hz" if highpass_hz > 0.0 else ""
    detail = (
        f"over [{from_t:g}, {to_t:g}] at {1.0 / dt:.0f} Hz ({samples.size} samples, "
        f"{detrend} detrend{filter_text}, band {band}): {measured:.6g} Hz, "
        f"expected {expected:.12g} ({tolerance_text}; |delta| {abs(measured - expected):.3g})"
    )
    report.check(abs(measured - expected) <= total, label, detail)


def _compare_checks(report: Report, project: str, specs: Any, runs: dict[str, Run]) -> None:
    if isinstance(specs, dict):
        specs = [specs]
    if not isinstance(specs, list):
        report.check(False, f"{project} compare", "'compare' must be an object or a list")
        return
    for spec in specs:
        try:
            a_name = str(spec["a"])
            b_name = str(spec["b"])
            signal_a = str(spec["signal_a"])
            signal_b = str(spec["signal_b"])
            limit = float(spec["max_abs"])
        except (KeyError, TypeError, ValueError) as exc:
            report.check(False, f"{project} compare", f"malformed compare entry: {exc!r}")
            continue
        label = f"{project} compare {a_name}/{signal_a} vs {b_name}/{signal_b}"
        if a_name not in runs or b_name not in runs:
            report.check(False, label, f"the runs {a_name!r} and {b_name!r} are both required")
            continue
        run_a = runs[a_name]
        run_b = runs[b_name]
        if signal_a not in run_a.signals or signal_b not in run_b.signals:
            missing = signal_a if signal_a not in run_a.signals else signal_b
            report.check(False, label, f"unknown signal {missing!r}")
            continue
        from_t = float(spec.get("from_t", max(run_a.time[0], run_b.time[0])))
        lower = max(from_t, float(run_a.time[0]), float(run_b.time[0]))
        upper = min(float(run_a.time[-1]), float(run_b.time[-1]))
        if not upper > lower:
            report.check(False, label, f"the runs do not overlap after t={from_t:g}")
            continue
        grid = np.union1d(
            run_a.time[(run_a.time >= lower) & (run_a.time <= upper)],
            run_b.time[(run_b.time >= lower) & (run_b.time <= upper)],
        )
        values_a = np.interp(grid, run_a.time, run_a.signals[signal_a])
        values_b = np.interp(grid, run_b.time, run_b.signals[signal_b])
        difference = float(np.max(np.abs(values_a - values_b)))
        detail = (
            f"from t={lower:g} max|delta| {difference:.3g} "
            f"(limit {limit:g} over {grid.size} points)"
        )
        report.check(difference <= limit, label, detail)


def _check_model_checks(
    report: Report, project: str, model: str, run: Run, checks: Any
) -> None:
    if not isinstance(checks, list):
        report.check(False, f"{project}/{model} checks", "'checks' must be a list")
        return
    for check in checks:
        if not isinstance(check, dict):
            report.check(False, f"{project}/{model} check", f"not an object: {check!r}")
            continue
        kind = check.get("kind")
        if kind in {"final_value", "cursor_value"}:
            _value_check(report, project, model, run, check, str(kind))
        elif kind == "max_abs":
            _max_abs_check(report, project, model, run, check)
        elif kind == "max_abs_le":
            _max_abs_le_check(report, project, model, run, check)
        elif kind == "rms_difference":
            _rms_difference_check(report, project, model, run, check)
        elif kind == "ratio":
            _ratio_check(report, project, model, run, check)
        elif kind == "zero_crossing":
            _zero_crossing_check(report, project, model, run, check)
        elif kind == "period":
            _period_check(report, project, model, run, check)
        elif kind == "energy":
            _energy_check(report, project, model, run, check)
        elif kind == "invariant":
            _invariant_check(report, project, model, run, check)
        elif kind == "planar_fk":
            _planar_fk_check(report, project, model, run, check)
        elif kind == "compare_signals":
            _compare_signals_check(report, project, model, run, check)
        elif kind == "step_response":
            _step_response_check(report, project, model, run, check)
        elif kind == "ripple":
            _ripple_check(report, project, model, run, check)
        elif kind == "fft_peak":
            _fft_peak_check(report, project, model, run, check)
        elif kind == "no_diagnostics":
            _no_diagnostics_check(report, project, model, run, check)
        else:
            label = f"{project}/{model} {check.get('signal', '?')} {kind!r}"
            report.check(False, label, "unknown check kind")


# --------------------------------------------------------------------------- examples


def _check_example(client: httpx.Client, expected_path: Path, report: Report) -> None:
    example = expected_path.parent.name
    try:
        document = json.loads(expected_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        report.check(False, f"{example} expected.json", f"unreadable: {exc}")
        return
    if not isinstance(document, dict):
        report.check(False, f"{example} expected.json", "the document must be an object")
        return
    project = str(document.get("project") or example)
    models = document.get("models")
    if not isinstance(models, dict) or not models:
        report.check(False, f"{example} expected.json", "'models' must be a non-empty object")
        return

    response = client.post("/api/projects", json={"name": project, "example": example})
    if response.status_code != 201:
        report.check(
            False,
            f"{example} project",
            f"POST /api/projects -> {response.status_code}: {response.text[:500]}",
        )
        return
    try:
        project_dir = Path(_get_json(client, f"/api/projects/{project}")["path"])
        runs: dict[str, Run] = {}
        for model, entry in models.items():
            checks = entry.get("checks", []) if isinstance(entry, dict) else entry
            source = model
            settings: Any = None
            if isinstance(entry, dict):
                source = str(entry.get("model") or model)
                settings = entry.get("settings")
            try:
                run = _run_model(client, project, project_dir, source, settings)
            except (RuntimeError, httpx.HTTPError, KeyError, ValueError) as exc:
                report.check(False, f"{project}/{model} run", str(exc))
                continue
            runs[model] = run
            print(
                f"      {project}/{model}: {run.run_id}, {run.time.size} points, "
                f"{len(run.signals)} signals",
                flush=True,
            )
            _check_model_checks(report, project, model, run, checks)
        compare = document.get("compare")
        if compare:
            _compare_checks(report, project, compare, runs)
    finally:
        client.delete(f"/api/projects/{project}")


def main() -> int:
    expected_files = sorted(EXAMPLES.glob("*/expected.json"))
    print(f"example checks: {len(expected_files)} expected.json file(s) under {EXAMPLES}")
    if not expected_files:
        print("no example checks found")
        return 0

    report = Report()
    projects_root = Path(tempfile.mkdtemp(prefix="bgsim-example-checks-"))
    log_path = projects_root / "backend.log"
    process: subprocess.Popen | None = None
    client: httpx.Client | None = None
    started = time.perf_counter()
    try:
        process, port = _start_backend(projects_root, log_path)
        client = httpx.Client(
            base_url=f"http://127.0.0.1:{port}",
            timeout=httpx.Timeout(180.0, connect=10.0),
        )
        _wait_for_worker(client, process, log_path)
        print(f"backend ready on 127.0.0.1:{port}", flush=True)
        for expected_path in expected_files:
            _check_example(client, expected_path, report)
    except Exception as exc:  # noqa: BLE001 - the harness reports, never tracebacks
        report.check(False, "harness", f"{type(exc).__name__}: {exc}")
        if log_path.is_file():
            print(f"--- backend log ({log_path}) ---\n{_log_tail(log_path)}", flush=True)
    finally:
        if client is not None:
            client.close()
        if process is not None:
            _stop_backend(process)
        shutil.rmtree(projects_root, ignore_errors=True)
        elapsed = time.perf_counter() - started

    print(
        f"\n{report.checks - report.failures} passed, {report.failures} failed "
        f"in {elapsed:.1f} s",
        flush=True,
    )
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main())
