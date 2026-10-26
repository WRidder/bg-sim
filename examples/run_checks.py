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
* evaluates every ``final_value``, ``cursor_value`` and ``compare`` check,
  prints one line per check and exits non-zero when any check fails.

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
          "value": 239.8, "abs": 0.1}]}},
     "compare": {"a": "iconic", "b": "bondgraph",
                 "signal_a": "Motor1/shaft.f", "signal_b": "IJ/p.f",
                 "from_t": 0.5, "max_abs": 1e-6}}

A model entry may also be a bare list of checks. ``compare`` may be a list of
such objects. ``rtol`` is relative to the expected value; ``abs`` is an extra
absolute tolerance. ``compare`` evaluates both signals on the union of the two
runs' time grids over ``[from_t, t1]``, so a different sample grid cannot hide
a peak.
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


def _run_model(client: httpx.Client, project: str, project_dir: Path, model: str) -> Run:
    """Open the model, run it and read its columns once it is done."""
    model_document = _get_json(client, f"/api/projects/{project}/models/{model}")
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
            try:
                run = _run_model(client, project, project_dir, model)
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
