"""R0.5: the bgsim closed loop (plant + generated policy block) against the training env, from the
same initial states, plus the swing-up / balance / push run of `pendulum-double-cart-rl`.

    uv run --project rl rl/compare.py <run dir> <plant export dir> <out dir> [--checkpoint model.pt]
        [--skip-bgsim]

1. Writes closed-loop model variants (policy from t = 0, no push) for a set of poses at rest
   (``design/rlmodels.py --cases``) and the default `pendulum-double-cart-rl` copy, runs them
   in bgsim (``rl/closed_loop.jl``: Rodas5P, reltol 1e-8);
2. rolls the same policy out in the training env (the batched FMU) from the same poses. The
   bgsim clock's first tick is at t = Ts (u = 0 before, spec "Discrete semantics"), so the env
   holds 0 V for the first period too and the first observation uses the start pose as the
   previous sample, as the block's start values do;
3. compares x, th1, th2 (wrapped) and u at the ticks: max deviation over 0.5 s, 1 s and the
   whole run (a double pendulum swing-up is chaotic, so deviations grow over time), and writes
   ``compare.json`` and ``compare.png`` (trajectories overlaid).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")

import numpy as np  # noqa: E402
import torch  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rlpend import EXAMPLE, ROOT  # noqa: E402
from rlpend.env import DoubleCartEnv, EnvCfg, wrap  # noqa: E402

UP_CASES = [
    {"name": "rlcmp-up-a", "x": 0.0, "th1": 0.1, "th2": -0.05, "t_end": 4.0},
    {"name": "rlcmp-up-b", "x": 0.05, "th1": -0.12, "th2": 0.1, "t_end": 4.0},
    {"name": "rlcmp-up-c", "x": -0.1, "th1": 0.2, "th2": 0.15, "t_end": 4.0},
    {"name": "rlcmp-up-d", "x": 0.1, "th1": -0.05, "th2": -0.25, "t_end": 4.0},
]
HANG_CASES = [
    {"name": "rlcmp-hang", "x": 0.0, "th1": -math.pi, "th2": -math.pi, "t_end": 6.0},
    {"name": "rlcmp-hang-a", "x": 0.05, "th1": -math.pi + 0.1, "th2": -math.pi - 0.1, "t_end": 6.0},
    {"name": "rlcmp-hang-b", "x": -0.1, "th1": -math.pi - 0.15, "th2": -math.pi + 0.05, "t_end": 6.0},
]
TASKS = {   # the comparison cases and the default model's timing (design/rlmodels.py RL_TASKS)
    "balance": {"cases": UP_CASES, "t_on": 0.0, "t_push": 3.0},
    "swingup": {"cases": HANG_CASES + UP_CASES[:2], "t_on": 1.0, "t_push": 7.0},
}


def read_run(run_dir: Path):
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    ids = [s["id"] for s in manifest["signals"]]
    rows = np.fromfile(run_dir / "stream.f64", dtype="<f8").reshape(-1, 1 + len(ids))
    keep = np.append(rows[1:, 0] != rows[:-1, 0], True)   # the right limit at a tick
    rows = rows[keep]
    return {s: rows[:, i + 1] for i, s in enumerate(ids)} | {"t": rows[:, 0]}


def at(run, name, t):
    idx = np.clip(np.searchsorted(run["t"], t - 1e-9), 0, len(run["t"]) - 1)
    assert np.max(np.abs(run["t"][idx] - t)) < 1e-9
    return run[name][idx]


def load_policy(run: Path, checkpoint: str, obs):
    from rsl_rl.models import MLPModel

    train = json.loads((run / "train.json").read_text(encoding="utf-8"))
    rc = train["runner"]["actor"]
    model = MLPModel(obs, {"actor": ["policy"]}, "actor", 1, hidden_dims=rc["hidden_dims"],
                     activation=rc["activation"], obs_normalization=True, distribution_cfg=rc["distribution_cfg"])
    model.load_state_dict(torch.load(run / checkpoint, map_location="cpu", weights_only=False)["actor_state_dict"])
    model.eval()
    return model


def env_rollout(run: Path, checkpoint: str, export_dir: Path, cases: list[dict]) -> dict:
    env_cfg = json.loads((run / "env.json").read_text(encoding="utf-8"))
    env_cfg.pop("ts", None)
    t_end = max(c["t_end"] for c in cases)
    cfg = EnvCfg(**{**env_cfg, "export_dir": str(export_dir), "num_envs": len(cases), "threads": 1,
                    "episode_s": t_end + 1.0, "x_rail": 10.0, "drop_angle": 0.0, "catch_end": False})
    env = DoubleCartEnv(cfg)
    n = len(cases)
    mask = np.ones(n, bool)
    env.set_pose(mask, np.array([c["x"] for c in cases]), np.array([c["th1"] for c in cases]),
                 np.array([c["th2"] for c in cases]))
    policy = load_policy(run, checkpoint, env.get_observations())
    env.plant.step(np.zeros((n, env.plant.nu)), cfg.nsub)   # 0 V until the first tick at Ts
    env.obs = env._observe()                               # prev = the start pose, a_prev = 0
    steps = int(round(t_end / cfg.ts))
    rec = {k: np.zeros((n, steps)) for k in ("x", "th1", "th2", "u")}
    t = np.arange(1, steps + 1) * cfg.ts
    with torch.inference_mode():
        for k in range(steps):
            x, th1, th2 = env._state[0], env._state[1], env._state[2]
            a = policy(env.obs)
            u = cfg.v_max * np.clip(a.numpy().ravel(), -1, 1)
            rec["x"][:, k], rec["th1"][:, k], rec["th2"][:, k], rec["u"][:, k] = x, th1, th2, u
            env.step(a)
    env.close()
    return {"t": t, **rec}


def metrics(run: dict, t_on: float, t_push: float) -> dict:
    """Swing-up / catch, balance and push numbers of the default run (policy from t_on, push at t_push)."""
    t = run["t"]
    th1, th2, x, u = run["Policy/th1"], run["Policy/th2"], run["Rail/qout"], run["Policy/u"]
    up = (np.abs(th1) < math.radians(2)) & (np.abs(th2) < math.radians(2))
    # first time after which it stays inside 2 deg until the push
    pre = t < t_push
    idx = np.where(pre & ~up)[0]
    t_up = float(t[idx[-1] + 1]) if len(idx) and idx[-1] + 1 < len(t) else float("nan")
    band = (t >= t_up + 0.5) & (t < t_push)
    post = (t >= t_push) & (t <= t_push + 2.0)
    inside = np.abs(th1) < math.radians(0.5)
    late = np.where((t >= t_push) & ~inside)[0]
    hold = t < t_on - 0.01
    return {
        "atRestBeforeOn": float(np.max(np.abs(x[hold]))) if hold.any() else None,
        "uBeforeOn": float(np.max(np.abs(u[hold]))) if hold.any() else None,
        "upright2degFromS": t_up, "toUpright2degS": t_up - t_on,
        "bandTh1Deg": float(np.degrees(np.max(np.abs(th1[band])))) if band.any() else float("nan"),
        "bandTh2Deg": float(np.degrees(np.max(np.abs(th2[band])))) if band.any() else float("nan"),
        "bandXmm": float(1e3 * np.max(np.abs(x[band]))) if band.any() else float("nan"),
        "pushPeakTh1Deg": float(np.degrees(np.max(np.abs(th1[post])))),
        "pushPeakTh2Deg": float(np.degrees(np.max(np.abs(th2[post])))),
        "recovered05degAtS": float(t[late[-1] + 1]) if len(late) and late[-1] + 1 < len(t) else float("nan"),
        "lastSecondTh1Deg": float(np.degrees(np.max(np.abs(th1[t >= t[-1] - 1.0])))),
        "lastSecondTh2Deg": float(np.degrees(np.max(np.abs(th2[t >= t[-1] - 1.0])))),
        "lastSecondXmm": float(1e3 * np.max(np.abs(x[t >= t[-1] - 1.0]))),
        "peakV": float(np.max(np.abs(u))), "peakXm": float(np.max(np.abs(x))),
    }


def plot(cases, env, runs, out: Path, default_run=None, t_push: float = 7.0):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = len(cases) + (1 if default_run is not None else 0)
    fig, axes = plt.subplots(n, 3, figsize=(13, 2.3 * n), squeeze=False)
    for i, c in enumerate(cases):
        r = runs[c["name"]]
        m = env["t"] <= c["t_end"] + 1e-9
        for j, (key, sig, label) in enumerate([("x", "Rail/qout", "x (m)"), ("th1", "Policy/th1", "angles (rad)"),
                                               ("u", "Policy/u", "u (V)")]):
            ax = axes[i, j]
            ax.plot(r["t"], r[sig], color="#3b6fb6", lw=1.2, label="bgsim" if j == 0 else None)
            ax.plot(env["t"][m], env[key][i][m], color="#c0504d", lw=1.0, ls="--", label="env" if j == 0 else None)
            if key == "th1":
                ax.plot(r["t"], r["Policy/th2"], color="#6a9f58", lw=1.2)
                ax.plot(env["t"][m], env["th2"][i][m], color="#d9a13b", lw=1.0, ls="--")
            ax.set_ylabel(label)
            ax.grid(alpha=0.3)
            if i == 0:
                ax.set_title(["cart position", "th1 (blue/red), th2 (green/orange)", "motor voltage"][j])
        axes[i, 0].text(0.02, 0.85, c["name"], transform=axes[i, 0].transAxes, fontsize=8)
    if default_run is not None:
        r = default_run
        axes[-1, 0].plot(r["t"], r["Rail/qout"], color="#3b6fb6")
        axes[-1, 1].plot(r["t"], r["Policy/th1"], color="#3b6fb6")
        axes[-1, 1].plot(r["t"], r["Policy/th2"], color="#6a9f58")
        axes[-1, 2].plot(r["t"], r["Policy/u"], color="#3b6fb6")
        axes[-1, 0].text(0.02, 0.85, "pendulum-double-cart-rl (bgsim)", transform=axes[-1, 0].transAxes, fontsize=8)
        for ax in axes[-1]:
            ax.grid(alpha=0.3)
            ax.axvline(t_push, color="0.5", lw=0.8, ls=":")
    axes[0, 0].legend(fontsize=8, loc="lower right")
    for ax in axes[-1]:
        ax.set_xlabel("t (s)")
    fig.tight_layout()
    fig.savefig(out, dpi=110)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("export_dir", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--checkpoint", default="model.pt")
    ap.add_argument("--skip-bgsim", action="store_true")
    ap.add_argument("--task", choices=sorted(TASKS), default="balance",
                    help="which cases, and the timing of the default pendulum-double-cart-rl model")
    args = ap.parse_args()
    task = TASKS[args.task]
    CASES = task["cases"]
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "cases.json").write_text(json.dumps(CASES, indent=2), encoding="utf-8")
    models = out / "models"
    if not args.skip_bgsim:
        subprocess.run(["uv", "run", str(EXAMPLE / "design" / "rlmodels.py"), "--cases", str(out / "cases.json"),
                        str(models)], check=True, cwd=ROOT)
        paths = [str(EXAMPLE / "models" / "pendulum-double-cart-rl.bgmodel.json")]
        paths += [str(models / f"{c['name']}.bgmodel.json") for c in CASES]
        subprocess.run(["julia", "--project=julia/BGSim", "rl/closed_loop.jl", str(out / "bgsim"), *paths],
                       check=True, cwd=ROOT)
    runs = {c["name"]: read_run(out / "bgsim" / c["name"]) for c in CASES}
    env = env_rollout(args.run_dir.resolve(), args.checkpoint, args.export_dir.resolve(), CASES)
    res = {"cases": {}}
    for i, c in enumerate(CASES):
        r = runs[c["name"]]
        m = env["t"] <= c["t_end"] + 1e-9
        t = env["t"][m]
        dev = {
            "x": np.abs(at(r, "Rail/qout", t) - env["x"][i][m]),
            "th1": np.abs(wrap(at(r, "Policy/th1", t) - env["th1"][i][m])),
            "th2": np.abs(wrap(at(r, "Policy/th2", t) - env["th2"][i][m])),
            "u": np.abs(at(r, "Policy/u", t) - env["u"][i][m]),
        }
        res["cases"][c["name"]] = {
            k: {f"to{h}s": float(np.max(v[t <= h + 1e-9])) for h in (0.5, 1.0, c["t_end"])} for k, v in dev.items()}
        print(c["name"], {k: f"{float(np.max(v[t <= 1.0])):.1e} (1 s) / {float(np.max(v)):.1e}" for k, v in dev.items()})
    default = read_run(out / "bgsim" / "pendulum-double-cart-rl")
    res["default"] = metrics(default, task["t_on"], task["t_push"])
    print("pendulum-double-cart-rl:", json.dumps(res["default"], indent=1))
    timings = json.loads((out / "bgsim" / "timings.json").read_text(encoding="utf-8"))
    res["timings"] = timings
    (out / "compare.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    plot(CASES, env, runs, out / "compare.png", default_run=default, t_push=task["t_push"])
    print("wrote", out / "compare.json", out / "compare.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
