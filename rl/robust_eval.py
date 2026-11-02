"""R1: the shared robustness test (design/robustness_test.json) in the batched FMU env: the same 65 draws (nominal
+ 64 Monte Carlo, seeds 3000-3063), scenarios and pass rule as design/robustness.py, on the plant FMU with the
realism forces and the env's sensors and loop delay. Fast (all draws of a scenario in one batch), used during
training and to explain env-vs-harness differences; the scored numbers come from the harness.

    uv run --project rl rl/robust_eval.py <plant export dir> --teacher [--teacher-est 5] | --weights policy.npz
        [--scenarios swingup,balance_push,knockdown_recover] [--out results.json]

Differences to the harness: the truth is the FMU (belt, armature inductance) instead of the twin; the start rates
of the hanging scenarios are zero (the FMU resets set poses only; the harness adds 0.05 rad/s noise); the sensor
noise is drawn from another stream.
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
import torch  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rlpend.renv import LAB, RobustCfg, RobustLabEnv, test_draws, wrap  # noqa: E402

TEST = json.loads((LAB / "design" / "robustness_test.json").read_text(encoding="utf-8"))


def run_scenario(export_dir, policy, scenario: str, threads: int = 4, draws=None, hist: int = 4,
                 teacher_swing: bool = True, teacher_est: int = 0) -> dict:
    """`policy(env) -> actions (n,) in [-1, 1]`; returns per-draw results and the summary."""
    sc = TEST["scenarios"][scenario]
    draws = draws or test_draws()
    n = len(draws)
    t_end = float(sc["t_end"])
    cfg = RobustCfg(export_dir=str(export_dir), num_envs=n, threads=threads, episode_s=t_end + 1.0, p_push=0.0,
                    drop_angle=0.0, x_rail=50.0, hist=hist, seed=12345, teacher_est=teacher_est)
    env = RobustLabEnv(cfg, draws=[d[1] for d in draws])
    hanging = bool(sc["start"].get("hanging"))
    if hanging:
        th = np.zeros((n, 2))
        for j, (_, _, seed) in enumerate(draws):
            rng = np.random.default_rng([seed, 1])
            th[j] = -math.pi + math.radians(sc["start"]["noise_deg"]) * rng.standard_normal(2)
        env.set_pose(np.ones(n, bool), np.zeros(n), th[:, 0], th[:, 1], np.zeros(n, bool))
    else:
        lean = np.radians(sc["start"]["lean_deg"])
        env.set_pose(np.ones(n, bool), np.zeros(n), np.full(n, lean[0]), np.full(n, lean[1]), np.ones(n, bool))
    env.swing[:] = hanging and teacher_swing
    push = sc.get("push")
    env.push_t[:] = push["t"] if push else np.inf
    env.push_a[:] = push["amp_N"] if push else 0.0
    dur = push["dur_s"] if push else 0.04
    env.obs = env._observe(new_tick=False)
    steps = int(round(t_end / cfg.ts))
    zs = np.zeros((steps + 1, n, 6))
    us = np.zeros((steps + 1, n))
    zs[0] = env.true_state()
    for k in range(steps):
        a = np.asarray(policy(env), float).reshape(-1)
        us[k] = cfg.v_max * np.clip(a, -1, 1)
        # the env's push lasts 40 ms; a longer one (knockdown) is held by moving its start
        t = k * cfg.ts
        if push and push["t"] <= t + 1e-9 < push["t"] + dur - 0.04:
            env.push_t[:] = t
        env.step(torch.as_tensor(a[:, None], dtype=torch.float32))
        zs[k + 1] = env.true_state()
    us[-1] = us[-2]
    env.close()
    ps = TEST["pass"]
    t = np.arange(steps + 1) * cfg.ts
    tail = t >= t_end - ps["tail_s"]
    dev = np.degrees(np.max(np.abs(wrap(zs[:, :, 1:3])), axis=2))      # (steps + 1, n)
    rows = []
    for j, (lab, p, seed) in enumerate(draws):
        fin = bool(np.all(np.isfinite(zs[:, j])))
        px = float(np.max(np.abs(zs[:, j, 0])))
        td = float(dev[tail, j].max())
        bad = np.where(dev[:, j] >= ps["upright_deg"])[0]
        ct = 0.0 if not len(bad) else (float(t[bad[-1] + 1]) if bad[-1] + 1 < len(t) else None)
        rows.append({"draw": lab, "ok": fin and px < ps["rail_m"] and td < ps["upright_deg"],
                     "ok_5p7": fin and px < ps["rail_m"] and td < 5.7, "tail_dev_deg": round(td, 3),
                     "peak_x": round(px, 4), "peak_V": round(float(np.abs(us[:, j]).max()), 2),
                     "tail_V_rms": round(float(np.sqrt(np.mean(us[tail, j] ** 2))), 2), "catch_t": ct,
                     "delay": int(p["delay"]), "joint_noise_deg": round(float(p["joint_noise"]), 4)})
    mc = [r for r in rows if r["draw"] != "nominal"]
    nom = rows[0]
    summ = {"nominal_ok": nom["ok"], "nominal_tail_deg": nom["tail_dev_deg"], "nominal_peak_V": nom["peak_V"],
            "nominal_peak_x": nom["peak_x"], "nominal_catch_t": nom["catch_t"],
            "mc_ok": sum(r["ok"] for r in mc), "mc_ok_5p7": sum(r["ok_5p7"] for r in mc), "mc_n": len(mc),
            "tail_dev_deg_median": float(np.median([r["tail_dev_deg"] for r in mc])),
            "tail_V_rms_median": float(np.median([r["tail_V_rms"] for r in mc])),
            "peak_x_max": max(r["peak_x"] for r in mc), "peak_V_max": max(r["peak_V"] for r in mc)}
    return {"summary": summ, "runs": rows, "traces": (t, zs, us)}


def teacher_policy(env):
    return env.teacher_action()


def mlp_policy(path):
    from lab_policy import MLP
    net = MLP(path)

    def f(env):
        return net(env._pol)
    return f


def fmt(name, s):
    return (f"{name:18s} MC {s['mc_ok']:2d}/{s['mc_n']} (5.7 deg {s['mc_ok_5p7']:2d}) nominal "
            f"{'ok' if s['nominal_ok'] else 'FAIL'} {s['nominal_tail_deg']:.2f} deg; MC tail median "
            f"{s['tail_dev_deg_median']:.2f} deg, tail V rms median {s['tail_V_rms_median']:.1f} V, peak V "
            f"{s['peak_V_max']:.1f}, peak x {s['peak_x_max']:.3f} m")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("export_dir", type=Path)
    ap.add_argument("--teacher", action="store_true")
    ap.add_argument("--weights", type=Path)
    ap.add_argument("--scenarios", default="swingup,balance_push")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--teacher-est", type=int, default=0, help="--teacher: the expert on a fit of the last N samples (0: true state)")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    pol = teacher_policy if args.teacher else mlp_policy(args.weights)
    hist = 4
    if args.weights:
        hist = int(np.load(args.weights)["hist"])
    out = {}
    for sc in args.scenarios.split(","):
        r = run_scenario(args.export_dir.resolve(), pol, sc, args.threads, hist=hist, teacher_est=args.teacher_est)
        print(fmt(sc, r["summary"]), flush=True)
        fails = [f"{x['draw']} ({x['tail_dev_deg']:.1f} deg, x {x['peak_x']:.2f})" for x in r["runs"]
                 if not x["ok"] and x["draw"] != "nominal"]
        if fails:
            print("   failures:", ", ".join(fails[:16]), "..." if len(fails) > 16 else "")
        r.pop("traces")
        out[sc] = r
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
