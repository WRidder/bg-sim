# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Compare the in-model firmware of a run with its Python twin (`humanoid.twin`).

    uv run examples/humanoid-dual-arm/design/compare_twin.py <run_dir> [--dof6] [--bias B]

Prints, per ArmIK instance, the largest joint difference [deg] and readout differences over the
run's output samples (the samples on the 1 kHz tick grid).
"""

from __future__ import annotations

import argparse

import numpy as np

import humanoid as dz
from runio import load_run


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--dof6", action="store_true")
    ap.add_argument("--bias", type=float, default=dz.BIAS)
    a = ap.parse_args()
    t, cols = load_run(a.run)
    tw = dz.twin(dof6=a.dof6, bias=a.bias, t_end=float(t[-1]), every=1)
    ticks = tw["t"]
    for key, inst in (("L", "IKL"), ("R", "IKR"), ("IL", "IdealL"), ("IR", "IdealR")):
        name = f"{inst}/q1"
        if name not in cols:
            continue
        sel = t >= dz.TS
        idx = np.clip(np.round(t[sel] / dz.TS).astype(int) - 1, 0, len(ticks) - 1)
        dq = max(float(np.max(np.abs(cols[f"{inst}/q{k}"][sel] - tw[key]["q"][idx, k - 1]))) for k in range(1, 8))
        dpe = float(np.max(np.abs(cols[f"{inst}/pe"][sel] - tw[key]["pe"][idx])))
        doe = float(np.max(np.abs(cols[f"{inst}/oe"][sel] - tw[key]["oe"][idx])))
        dl = float(np.max(np.abs(cols[f"{inst}/lim"][sel] - tw[key]["lim"][idx])))
        print(f"{inst:7s} max |dq| {dq:.3g} deg, |dpe| {dpe:.3g} mm, |doe| {doe:.3g} deg, |dlim| {dl:.3g} %;"
              f" end: pe {cols[f'{inst}/pe'][-1]:.4g} mm oe {cols[f'{inst}/oe'][-1]:.4g} deg lim {cols[f'{inst}/lim'][-1]:.3g}%")  # fmt: skip


if __name__ == "__main__":
    main()
