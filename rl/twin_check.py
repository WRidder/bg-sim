"""R1: the plant FMU with the realism forces (the training env's truth) against the harness's truth, the Python
twin of `design/lablib.py setup` (every effect), on a few draws of the shared test.

    uv run --project rl rl/twin_check.py <plant export dir> <out dir> [--draws nominal,mc00,mc01]

Per draw, the same closed loop on both: the expert (`renv.Teacher`, the TVLQR swing-up then the LQR, on the true
state) at 200 Hz with the draw's loop delay, no sensor noise or quantisation (the sensors are the wrapper's and
the harness's own, identical by construction):
  open      open loop from hanging rest, a +-6 V level sequence for 3 s (the hanging pendulum is stable)
  balance   2 deg lean of both links, the 0.45 N, 40 ms tip push at 2 s, 4 s
  swingup   hanging rest, the swing-up and balance, 6 s
The twin gets the armature lag L_m / R_m as the harness applies it (`tau_act`); the FMU has the armature
inductance and the belt in its bond graph. Writes twin_check.json and twin_check.png.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rlpend import EXAMPLES  # noqa: E402
from rlpend.renv import RobustCfg, RobustLabEnv, Teacher, test_draws, wrap  # noqa: E402

sys.path.insert(0, str(EXAMPLES["lab"] / "design"))
import lablib as lb  # noqa: E402

ql = lb.ql
TS = 0.005


def levels(n_ms: int, seed: int = 5) -> np.ndarray:
    rng = np.random.default_rng(seed)
    u = np.zeros(n_ms)
    k = 200
    while k < n_ms:
        dur = int(rng.integers(20, 120))
        u[k:k + dur] = rng.uniform(-6, 6)
        k += dur
    return u


def run_twin(p, case, teacher, t_end, seed):
    rs = lb.setup(p, lb.EFFECTS, "diff", seed=seed, sub=8)
    delay = int(p["delay"])
    if case == "balance":
        z = np.zeros(6)
        z[1:3] = math.radians(2.0)
    else:
        z = np.array([0.0, -math.pi, -math.pi, 0, 0, 0])
    n = int(round(t_end / 1e-3))
    ol = levels(n)
    tau = rs.tau_act
    ea = math.exp(-1e-3 / tau)
    wa = 1.0 - tau / 1e-3 * (1.0 - ea)
    uf = 0.0
    line = [0.0] * (delay + 1)
    cmd = 0.0
    zs = np.zeros((n // 5 + 1, 6))
    us = np.zeros(n // 5 + 1)
    zs[0] = z
    for i in range(n):
        t = i * 1e-3
        if i % 5 == 0:
            if case == "open":
                cmd = ol[i]
            else:
                cmd = float(teacher(np.array([t]), z[None, :], np.array([case == "swingup"]))[0])
            us[i // 5] = cmd
        line.insert(0, cmd)
        line.pop()
        u = line[delay]
        u, uf = uf + (u - uf) * wa, u + (uf - u) * ea
        f = 0.45 if case == "balance" and 2.0 <= t + 0.5e-3 < 2.04 else 0.0
        z = np.array(rs.step(z, u, f)).ravel()
        if (i + 1) % 5 == 0:
            zs[(i + 1) // 5] = z
    return zs, us


def run_fmu(export, draws, case, teacher, t_end):
    cfg = RobustCfg(export_dir=str(export), num_envs=len(draws), threads=1, sensors=False, delay=True, p_push=0.0,
                    episode_s=t_end + 1.0, drop_angle=0.0, x_rail=10.0)
    env = RobustLabEnv(cfg, draws=draws)
    n = len(draws)
    if case == "balance":
        env.set_pose(np.ones(n, bool), np.zeros(n), np.full(n, math.radians(2)), np.full(n, math.radians(2)),
                     np.ones(n, bool))
    else:
        env.set_pose(np.ones(n, bool), np.zeros(n), np.full(n, -math.pi), np.full(n, -math.pi),
                     np.zeros(n, bool))
    env.obs = env._observe(new_tick=False)
    steps = int(round(t_end / TS))
    ol = levels(int(round(t_end / 1e-3)))
    zs = np.zeros((steps + 1, n, 6))
    us = np.zeros((steps + 1, n))
    zs[0] = env.true_state()
    import torch
    for k in range(steps):
        t = k * TS
        if case == "open":
            a = np.full(n, ol[k * 5] / 24.0)
        else:
            a = env.teacher_action()
        if case == "balance":
            env.push_t[:] = 2.0
            env.push_a[:] = 0.45
        us[k] = 24.0 * a
        env.step(torch.as_tensor(a[:, None], dtype=torch.float32))
        zs[k + 1] = env.true_state()
    env.close()
    return zs, us


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("export_dir", type=Path)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--draws", default="nominal,mc00,mc01,mc02")
    args = ap.parse_args()
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    pick = args.draws.split(",")
    sel = [d for d in test_draws() if d[0] in pick]
    teacher = Teacher()
    cases = {"open": 3.0, "balance": 4.0, "swingup": 6.0}
    res = {}
    traces = {}
    for case, t_end in cases.items():
        zf, uf = run_fmu(args.export_dir.resolve(), [d[1] for d in sel], case, teacher, t_end)
        for j, (lab, p, seed) in enumerate(sel):
            zt, ut = run_twin(p, case, teacher, t_end, seed)
            m = min(len(zt), zf.shape[0])
            dz = np.abs(zf[:m, j] - zt[:m])
            dz[:, 1:3] = np.abs(wrap(zf[:m, j, 1:3] - zt[:m, 1:3]))
            r = {"x_m": float(dz[:, 0].max()), "th1_deg": float(np.degrees(dz[:, 1].max())),
                 "th2_deg": float(np.degrees(dz[:, 2].max())), "u_V": float(np.abs(uf[:m, j] - ut[:m]).max()),
                 "fmu_tail_deg": float(np.degrees(np.abs(wrap(zf[-80:, j, 1:3])).max())),
                 "twin_tail_deg": float(np.degrees(np.abs(wrap(zt[-80:, 1:3])).max()))}
            res[f"{case}/{lab}"] = r
            traces[f"{case}/{lab}"] = (zf[:m, j], zt[:m])
            print(f"{case:8s} {lab:8s} max |dx| {r['x_m']:.2e} m  |dth1| {r['th1_deg']:.3f} deg  |dth2| "
                  f"{r['th2_deg']:.3f} deg  |du| {r['u_V']:.3f} V  tail 0.4 s: fmu {r['fmu_tail_deg']:.3f} twin "
                  f"{r['twin_tail_deg']:.3f} deg", flush=True)
    (out / "twin_check.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(3, 3, figsize=(13, 8))
    for i, case in enumerate(cases):
        zf, zt = traces[f"{case}/{sel[0][0]}"]
        t = np.arange(len(zf)) * TS
        for j, (lab, idx) in enumerate((("x (m)", 0), ("th1 (rad)", 1), ("th2 (rad)", 2))):
            ax = axs[i, j]
            ax.plot(t, zf[:, idx], color="#3b6fb6", label="FMU env")
            ax.plot(t, zt[:, idx], "--", color="#c0504d", label="twin (harness)")
            ax.set_title(f"{case}, {sel[0][0]}: {lab}", fontsize=9)
            ax.grid(alpha=0.3)
    axs[0, 0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "twin_check.png", dpi=110)
    return 0


if __name__ == "__main__":
    sys.exit(main())
