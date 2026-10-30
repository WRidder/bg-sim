# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["numpy<2", "matplotlib"]
# ///
"""Result plots of the Planar Links docs, from the run data of the three models.

``uv run reference/plots.py <inverse-run> <forward-run> <payload-run>`` where every argument is
a run folder (``manifest.json`` and ``columns.f64``, as written by the backend under
``<project>/runs/`` or by ``BGSim.simulate``). The PNGs are written to
``models/planar-links.docs/assets/<first 12 hex of the sha256>.png`` and the mapping
``name -> file`` is printed, so the Markdown pages can reference them.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "models" / "planar-links.docs" / "assets"
BLUE, ORANGE, GREEN, PINK = "#0072B2", "#D55E00", "#009E73", "#CC79A7"


class Run:
    def __init__(self, folder: str):
        path = Path(folder)
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        n = int(manifest["time"]["n"])
        ids = [s["id"] for s in manifest["signals"]]
        raw = np.fromfile(path / "columns.f64", dtype="<f8").reshape(len(ids) + 1, n)
        self.t = raw[0]
        self.cols = {name: raw[k + 1] for k, name in enumerate(ids)}

    def __getitem__(self, name: str) -> np.ndarray:
        return self.cols[name]


def save(fig, name: str) -> str:
    ASSETS.mkdir(parents=True, exist_ok=True)
    tmp = ASSETS / f"{name}.tmp.png"
    fig.savefig(tmp, dpi=110, metadata={"Software": None})
    plt.close(fig)
    digest = hashlib.sha256(tmp.read_bytes()).hexdigest()[:12]
    target = ASSETS / f"{digest}.png"
    tmp.replace(target)
    print(f"{name}: {target.name}")
    return target.name


def style(ax, xlabel, ylabel, title):
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=10)
    ax.grid(True, alpha=0.3)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def main(inverse: str, forward: str, payload: str) -> None:
    inv, fwd, pay = Run(inverse), Run(forward), Run(payload)
    colors = [BLUE, ORANGE, GREEN]

    fig, ax = plt.subplots(figsize=(7.2, 3.6), constrained_layout=True)
    for j in (1, 2, 3):
        ax.plot(inv.t, inv[f"A3_Torque{j}/y"], color=colors[j - 1], lw=1.8, label=f"joint {j}, bond graph")
        ref = inv[f"A3_Torque{j}/y"] - inv[f"A3_TauErr{j}/e_rtb"]
        ax.plot(inv.t[::40], ref[::40], "o", ms=3.5, mfc="none", color=colors[j - 1],
                label=f"joint {j}, Robotics Toolbox" if j == 1 else None)
    style(ax, "time [s]", "joint torque [N m]", "3-link arm: torque the bond graph needs (lines) vs RTB (circles)")
    ax.legend(fontsize=8, ncol=2, frameon=False)
    save(fig, "torque3")

    fig, ax = plt.subplots(figsize=(7.2, 3.6), constrained_layout=True)
    for j in (1, 2, 3):
        ax.plot(inv.t, inv[f"A3_TauErr{j}/e_rtb"], color=colors[j - 1], lw=1.3, label=f"joint {j}")
    ax.axvspan(0.0, 0.02, color="0.9", zorder=0)
    style(ax, "time [s]", "bond graph - RTB [N m]",
          "3-link arm: torque error (grey: start-up ring of the compliant pivots)")
    ax.legend(fontsize=8, frameon=False)
    save(fig, "error3")

    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.4), constrained_layout=True, sharey=False)
    for ax, n, tag in ((axes[0], 2, "2-link"), (axes[1], 3, "3-link")):
        for j in range(1, n + 1):
            ax.plot(fwd.t, fwd[f"A{n}_QErr{j}/e"] * 1e6, color=colors[j - 1], lw=1.5, label=f"joint {j}")
        style(ax, "time [s]", "q(model) - q(CSV) [micro rad]", f"{tag}: open-loop drift")
        ax.legend(fontsize=8, frameon=False)
    save(fig, "drift")

    fig, ax = plt.subplots(figsize=(7.2, 3.4), constrained_layout=True)
    for j in (1, 2, 3):
        ax.plot(pay.t, pay[f"A3_TauErr{j}/e_rtb"], color=colors[j - 1], lw=1.3, label=f"joint {j}")
    ax.axvspan(0.0, 0.02, color="0.9", zorder=0)
    style(ax, "time [s]", "bond graph - RTB 4-link [N m]", "3-link arm with the 1 kg payload: torque error")
    ax.legend(fontsize=8, frameon=False)
    save(fig, "payload")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
