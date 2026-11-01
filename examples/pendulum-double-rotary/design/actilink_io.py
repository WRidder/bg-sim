"""Run data of the ACTILINK models: bg-sim run directories (columns.f64 + manifest.json, plan 3.5)
and the CSV layout of the run export (`GET /api/runs/{id}/export.csv`: a header `t,<signal id>,...`,
one row per output point). The identification scripts read CSV, so the same scripts run on lab
logs written with the same column names."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np


def load_run(run_dir) -> tuple[np.ndarray, dict]:
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    ids = [s["id"] for s in manifest["signals"]]
    n = int(manifest["time"]["n"])
    raw = np.fromfile(run_dir / "columns.f64", dtype="<f8").reshape(len(ids) + 1, n)
    t, cols = raw[0], {sid: raw[k + 1] for k, sid in enumerate(ids)}
    keep = np.r_[np.diff(t) > 0, True]  # event instants are recorded twice: keep the last
    return t[keep], {k: v[keep] for k, v in cols.items()}


def write_csv(path: Path, t: np.ndarray, signals: dict, ids: list[str]) -> None:
    """The run export's CSV: `t` first, then the chosen signal ids, round-trip precision."""
    path.parent.mkdir(parents=True, exist_ok=True)
    m = np.column_stack([t] + [signals[i] for i in ids])
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("t," + ",".join(ids) + "\n")
        np.savetxt(f, m, delimiter=",", fmt="%.17g")


def read_csv(path: Path) -> tuple[np.ndarray, dict]:
    path = Path(path)
    with path.open(encoding="utf-8") as f:
        header = f.readline().strip().split(",")
    data = np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)
    cols = {name: data[:, k] for k, name in enumerate(header)}
    return cols.pop("t"), cols


def at(t: np.ndarray, y: np.ndarray, t0: float) -> float:
    return float(np.interp(t0, t, y))
