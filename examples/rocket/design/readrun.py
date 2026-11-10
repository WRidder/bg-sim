# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Read a run folder written by design/run_model.jl and print signals at given times.

    uv run examples/rocket/design/readrun.py <run_dir> <signal>[,<signal>..] <t>[,<t>..]
    uv run examples/rocket/design/readrun.py <run_dir> --max <signal> [t0 t1]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np


def read_run(run_dir: str | Path) -> dict:
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    raw = np.fromfile(run_dir / "columns.f64", dtype="<f8")
    n = int(manifest["time"]["n"])
    ids = [str(s["id"]) for s in manifest["signals"]]
    out = {"t": raw[:n]}
    for k, sid in enumerate(ids):
        out[sid] = raw[n * (k + 1): n * (k + 2)]
    return out


def main() -> int:
    run = read_run(sys.argv[1])
    if sys.argv[2] == "--max":
        sig = sys.argv[3]
        t0, t1 = (float(sys.argv[4]), float(sys.argv[5])) if len(sys.argv) > 5 else (-np.inf, np.inf)
        w = (run["t"] >= t0) & (run["t"] <= t1)
        k = int(np.argmax(np.abs(run[sig][w])))
        print(sig, "max", run[sig][w][k], "at", run["t"][w][k])
        return 0
    for sig in sys.argv[2].split(","):
        if sig not in run:
            print(sig, "MISSING; similar:", [s for s in run if s.split("/")[0] == sig.split("/")[0]][:40])
            continue
        vals = [float(np.interp(float(t), run["t"], run[sig])) for t in sys.argv[3].split(",")]
        print(f"{sig:24s}", " ".join(f"{v:14.6f}" for v in vals))
    return 0


if __name__ == "__main__":
    sys.exit(main())
