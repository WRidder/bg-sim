# /// script
# requires-python = ">=3.11"
# dependencies = ["casadi>=3.6", "httpx>=0.28", "numpy>=2.0", "scipy>=1.13"]
# ///
"""Measure a fixed-pivot pendulum example on a running real-worker backend and write ``measured.json``.

    uv run examples/pendulum-double-fixed/design/pendulum_measure.py <example> [--url http://127.0.0.1:8787]

The backend is the one of ``uv run bgsim`` (real worker). The script copies the example into a
project, runs the main model, reads the columns, compares the link angles with the design prediction
(``design.py --save-prediction``, recomputed here) and records: catch time, upright band before the
disturbance, peak deflection after it, recovery time, peak voltage, compile and run times.
The README of the example is rendered from this file (``build_readme.py``).
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
import time
from pathlib import Path

import httpx
import numpy as np

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE.parents[1]
sys.path.insert(0, str(EXAMPLES))
sys.path.insert(0, str(HERE))

import run_checks as rc  # noqa: E402
from pendulum_flow import design  # noqa: E402
from pendulum_common import TS  # noqa: E402


def load_params(example: str):
    folder = EXAMPLES / example / "design"
    sys.path.insert(0, str(folder))
    spec = importlib.util.spec_from_file_location("params", folder / "params.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["params"] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    example = sys.argv[1]
    url = sys.argv[sys.argv.index("--url") + 1] if "--url" in sys.argv else "http://127.0.0.1:8787"
    prm = load_params(example)
    P, C = prm.PLANT, prm.CFG
    n = P.n
    # the design prediction (also rewrites the library, expected.json and results.json: they are reproducible)
    pred_path = Path(prm.HERE) / "predicted.tmp.npz"
    sys.argv += ["--save-prediction", str(pred_path)]
    design(prm)
    with np.load(pred_path) as data:
        pred = {k: data[k] for k in data.files}
    pred_path.unlink()

    client = httpx.Client(base_url=url, timeout=httpx.Timeout(900.0, connect=10.0))
    project = f"measure-{example}"
    client.delete(f"/api/projects/{project}")
    response = client.post("/api/projects", json={"name": project, "example": example})
    assert response.status_code == 201, response.text
    try:
        project_dir = Path(rc._get_json(client, f"/api/projects/{project}")["path"])
        started = time.perf_counter()
        run = rc._run_model(client, project, project_dir, example, None, 900.0)
        wall = time.perf_counter() - started
        stats = run.manifest.get("stats") or {}
    finally:
        client.delete(f"/api/projects/{project}")

    t = run.time
    a = [run.signals[f"Upright/a{k + 1}"] for k in range(n)]
    u = run.signals["Ctrl/u"]
    phase = run.signals["Ctrl/phase"]
    t_dist = C["t_dist"]
    t_catch = float(t[np.argmax(phase == 2)])
    pre = (t >= t_catch + 0.5) & (t < t_dist - 0.01)
    post = t >= t_dist
    band = max(float(np.abs(x[pre]).max()) for x in a)
    outside = np.where(post & np.any([np.abs(x) > math.radians(1.0) for x in a], axis=0))[0]
    diffs = [float(np.abs(a[k] - np.interp(t, pred["t"], pred["a"][:, k])).max()) for k in range(n)]
    measured = dict(
        t_catch=t_catch,
        band_deg=math.degrees(band),
        peak_deg=[math.degrees(float(np.abs(x[post]).max())) for x in a],
        recovered=float(t[outside[-1]]) if len(outside) else t_dist,
        peak_u=float(np.abs(u).max()),
        peak_u_after=float(np.abs(u[post]).max()),
        clamped_ms=int(np.sum(np.abs(np.interp(np.arange(0, t[-1], TS), t, u)) >= P.umax - 1e-9)),
        pred_diff=max(diffs),
        points=int(t.size),
        time_s=wall,
        compile_s=float(stats.get("compile_s", float("nan"))),
        run_s=float(stats.get("sim_s", float("nan"))),
        steps=stats.get("steps"),
        events=stats.get("events"),
        states=stats.get("states"),
        equations=stats.get("equations"),
    )
    (Path(prm.HERE) / "measured.json").write_text(json.dumps(measured, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(measured, indent=2))


if __name__ == "__main__":
    main()
