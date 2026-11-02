"""Calibrate the hybrid's catch region z' P z < catch_tol (rl/classical.json) in the training env.

    uv run --project rl rl/catch_calib.py <plant export dir> [--n 2048] [--rig cart|lab]

Runs the balance LQR (200 Hz, the env's differenced rates, the clamp) from rest poses spread up to
+-0.45 rad / +-0.25 m, 3 s each, and reports the cost-to-go V0 = z0' P z0 of the starts that fail
(a link past 0.8 rad or the cart off the rail): the catch tolerance must stay below the smallest
failing V0. (Rest starts only: the shim sets poses, not rates, so velocity states are covered only
by the training's own post-catch statistics.)
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
from rlpend.env import DoubleCartEnv, EnvCfg  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("export_dir", type=Path)
    ap.add_argument("--n", type=int, default=2048)
    ap.add_argument("--rig", choices=("cart", "lab"), default="cart")
    args = ap.parse_args()
    lab = args.rig == "lab"
    cl = json.loads((Path(__file__).resolve().parent / ("classical_lab.json" if lab else "classical.json"))
                    .read_text(encoding="utf-8"))
    K, P = np.array(cl["K"]), np.array(cl["P"])
    extra = {}
    if lab:
        pl = cl["plant"]
        extra = {"x_rail": 0.95, "m": tuple(pl["m"]), "L": tuple(pl["L"]), "c": tuple(pl["c"]), "J": tuple(pl["J"])}
    cfg = EnvCfg(export_dir=str(args.export_dir.resolve()), num_envs=args.n, threads=4, p_upright_start=1.0,
                 up_noise=(0.25, 0.45, 0.45), episode_s=3.0, seed=11, **extra)
    env = DoubleCartEnv(cfg)
    x0, th10, th20 = (np.array(v, copy=True) for v in env._state[:3])
    z0 = np.stack([x0, th10, th20, 0 * x0, 0 * x0, 0 * x0], 1)
    V0 = np.einsum("ij,jk,ik->i", z0, P, z0)
    obs = env.get_observations()
    ok = np.ones(args.n, bool)
    for _ in range(env.max_episode_length - 1):
        p = obs["policy"].numpy().astype(float)
        x, th1, th2 = env._state[:3]
        z = np.stack([x, th1, th2, p[:, 5], p[:, 6], p[:, 7]], 1)
        a = np.clip(-(z @ K) / cfg.v_max, -1, 1)
        obs, _, done, _ = env.step(torch.as_tensor(a[:, None], dtype=torch.float32))
        ok &= ~done.numpy() & (np.abs(env._state[1]) < 0.8) & (np.abs(env._state[2]) < 0.8)
    env.close()
    order = np.argsort(V0)
    print(f"V0 range {V0.min():.1f} .. {V0.max():.1f}; success {ok.mean():.3f}")
    bad = V0[~ok]
    print(f"smallest failing V0: {bad.min():.1f}" if bad.size else "no failures")
    for q in (1000, 2000, 5000, 10000, 20000, 30000, 50000, 100000):
        inside = V0 < q
        print(f"  V0 < {q:5d}: {inside.sum():5d} starts, success {ok[inside].mean() if inside.any() else float('nan'):.3f}")
    _ = order
    return 0


if __name__ == "__main__":
    sys.exit(main())
