"""Run example models through a real backend (for `design.py --verify` and the docs plots).

Reuses the harness of `examples/run_checks.py` (backend start/stop, run, columns) and saves each
run as `design/_runs/<model>.npz` (time column and one array per signal).
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import time
from pathlib import Path

import httpx
import numpy as np

REPO = Path(__file__).resolve().parents[3]


def _harness():
    spec = importlib.util.spec_from_file_location("run_checks", REPO / "examples" / "run_checks.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_checks"] = module
    spec.loader.exec_module(module)
    return module


def run_models(example: str, models: list[str], out_dir: Path, timeout: float = 1800.0) -> dict[str, dict]:
    rc = _harness()
    rc._kill_children_with_me()
    root = Path(tempfile.mkdtemp(prefix="bgsim-design-"))
    log = root / "backend.log"
    process = None
    client = None
    stats: dict[str, dict] = {}
    try:
        process, port = rc._start_backend(root, log)
        client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=httpx.Timeout(180.0, connect=10.0))
        rc._wait_for_worker(client, process, log)
        project = f"design-{example}"
        response = client.post("/api/projects", json={"name": project, "example": example})
        response.raise_for_status()
        project_dir = Path(rc._get_json(client, f"/api/projects/{project}")["path"])
        out_dir.mkdir(parents=True, exist_ok=True)
        for model in models:
            started = time.perf_counter()
            run = rc._run_model(client, project, project_dir, model, None, timeout)
            elapsed = time.perf_counter() - started
            np.savez(out_dir / f"{model}.npz", time=run.time, **{k.replace("/", "__"): v for k, v in run.signals.items()})
            stats[model] = {"seconds": elapsed, "points": int(run.time.size), "diagnostics": run.manifest.get("diagnostics")}
            print(f"{model}: {elapsed:.1f} s, {run.time.size} points, diagnostics {run.manifest.get('diagnostics')}", flush=True)
        client.delete(f"/api/projects/{project}")
    finally:
        if client is not None:
            client.close()
        if process is not None:
            rc._stop_backend(process)
        shutil.rmtree(root, ignore_errors=True)
    return stats


def load(path: Path) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    data = np.load(path)
    return data["time"], {k.replace("__", "/"): data[k] for k in data.files if k != "time"}
