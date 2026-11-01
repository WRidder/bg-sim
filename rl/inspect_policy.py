"""Roll out a checkpoint from hanging rest and print what happens (diagnostics for R0.3).

    uv run --project rl rl/inspect_policy.py <run dir> <checkpoint> [--envs 8] [--seconds 6] [--plot out.png]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")

import numpy as np  # noqa: E402
import torch  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare import load_policy  # noqa: E402
from rlpend.env import DoubleCartEnv, EnvCfg  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("checkpoint")
    ap.add_argument("--envs", type=int, default=8)
    ap.add_argument("--seconds", type=float, default=6.0)
    ap.add_argument("--plot", type=Path)
    ap.add_argument("--upright", action="store_true", help="start near the upright instead of hanging")
    args = ap.parse_args()
    d = json.loads((args.run_dir / "env.json").read_text(encoding="utf-8"))
    d.pop("ts")
    cfg = EnvCfg(**{**d, "num_envs": args.envs, "threads": 1, "p_upright_start": 1.0 if args.upright else 0.0,
                    "seed": 7, "episode_s": args.seconds + 1, "x_rail": 10.0, "drop_angle": 0.0,
                    "catch_end": False})
    env = DoubleCartEnv(cfg)
    pol = load_policy(args.run_dir, args.checkpoint, env.get_observations())
    n = int(args.seconds / cfg.ts)
    rec = np.zeros((n, 5, args.envs))
    with torch.inference_mode():
        for k in range(n):
            a = pol(env.obs)
            x, th1, th2 = env._state[:3]
            rec[k] = [x, th1, th2, cfg.v_max * np.clip(a.numpy().ravel(), -1, 1), env._state[5]]
            env.step(a)
    t = np.arange(n) * cfg.ts
    for s in (0.5, 1, 1.5, 2, 3, 4, 5, 5.9):
        k = min(int(s / cfg.ts), n - 1)
        print(f"t={s:4.1f}  x {np.round(rec[k, 0], 2)}  th1 {np.round(rec[k, 1], 2)}  th2 {np.round(rec[k, 2], 2)}")
    print("max |x| per env", np.round(np.abs(rec[:, 0]).max(0), 2))
    print("time |x| > 0.4 first:", [float(t[np.argmax(np.abs(rec[:, 0, i]) > 0.4)]) if (np.abs(rec[:, 0, i]) > 0.4).any()
                                     else None for i in range(args.envs)])
    if args.plot:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(4, 1, figsize=(9, 8), sharex=True)
        for i, lab in enumerate(["x (m)", "th1 (rad)", "th2 (rad)", "u (V)"]):
            ax[i].plot(t, rec[:, i, :], lw=0.8)
            ax[i].set_ylabel(lab)
            ax[i].grid(alpha=0.3)
        ax[-1].set_xlabel("t (s)")
        fig.tight_layout()
        fig.savefig(args.plot, dpi=100)
    env.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
