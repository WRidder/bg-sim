"""R1 helper: one scenario of the shared test in the env for a policy.npz (or the expert), plots of a few draws
(angles, cart, voltage) to see how a run fails (limit cycle, offset, rail).

    uv run --project rl rl/trace_plot.py <plant export dir> <policy.npz | teacher> <out.png> [--scenario balance_push]
        [--draws nominal,mc00,mc01]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import robust_eval as rev  # noqa: E402
from rlpend.renv import test_draws  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("export_dir", type=Path)
    ap.add_argument("policy")
    ap.add_argument("out", type=Path)
    ap.add_argument("--scenario", default="balance_push")
    ap.add_argument("--draws", default="nominal,mc00,mc01,mc02")
    args = ap.parse_args()
    pick = args.draws.split(",")
    draws = [d for d in test_draws() if d[0] in pick]
    pol = rev.teacher_policy if args.policy == "teacher" else rev.mlp_policy(args.policy)
    hist = 4 if args.policy == "teacher" else int(np.load(args.policy)["hist"])
    r = rev.run_scenario(args.export_dir.resolve(), pol, args.scenario, 2, draws=draws, hist=hist)
    t, zs, us = r["traces"]
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(len(draws), 3, figsize=(14, 2.4 * len(draws)), squeeze=False)
    for j, (lab, _, _) in enumerate(draws):
        ax[j, 0].plot(t, np.degrees(rev.wrap(zs[:, j, 1])), label="th1")
        ax[j, 0].plot(t, np.degrees(rev.wrap(zs[:, j, 2])), label="th2")
        ax[j, 0].set_ylim(-8, 8)
        ax[j, 0].set_ylabel(f"{lab}: deg")
        ax[j, 1].plot(t, zs[:, j, 0])
        ax[j, 1].set_ylabel("x (m)")
        ax[j, 2].plot(t, us[:, j], lw=0.6)
        ax[j, 2].set_ylabel("V")
        for a in ax[j]:
            a.grid(alpha=0.3)
        print(lab, r["runs"][j])
    ax[0, 0].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(args.out, dpi=100)
    return 0


if __name__ == "__main__":
    sys.exit(main())
