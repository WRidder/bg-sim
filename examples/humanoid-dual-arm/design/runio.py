"""Read a run directory (columns.f64 + manifest.json, plan 3.5) as numpy arrays."""

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


def at(t: np.ndarray, y: np.ndarray, t0: float) -> float:
    return float(np.interp(t0, t, y))
