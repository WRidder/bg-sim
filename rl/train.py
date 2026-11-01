"""R0.3: PPO (rsl_rl) swing-up and balance of the double cart on the batched plant FMU.

    uv run --project rl rl/train.py <plant export dir> <run dir> [--iterations N] [--envs N]
        [--threads N] [--hidden 64,64] [--eval-every 25]

Trains on CPU, evaluates the deterministic policy every ``--eval-every`` iterations (64 episodes
from hanging rest, 6 s: success = both links within 0.1 rad of upright over the last second
and the cart on the rail), and writes into the run dir:
    env.json, train.json        the configurations (the generator reads env.json)
    curve.csv                   iteration, env steps, wall s, mean reward, eval success, ...
    model_<it>.pt, model.pt     rsl_rl checkpoints (model.pt: the final one)
    curve.png                   the learning curve
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

# The plant's OpenMP threads (libgomp) and torch's own thread pool take turns; spinning idle
# threads of one would steal the cores of the other.
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")

import numpy as np  # noqa: E402
import torch  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rlpend.env import DoubleCartEnv, EnvCfg, TrainCfg  # noqa: E402


def evaluate(policy, cfg: EnvCfg, episodes: int = 64, seed: int = 123, upright: bool = False) -> dict:
    """From hanging rest (the gate), or from the upright starts (balance only, for insight)."""
    ecfg = EnvCfg(**{**asdict(cfg), "num_envs": episodes, "p_upright_start": 1.0 if upright else 0.0,
                     "p_random_start": 0.0, "seed": seed, "catch_end": False})   # hybrid: the LQR balances on
    env = DoubleCartEnv(ecfg)
    obs = env.get_observations()
    n_steps = env.max_episode_length
    last = int(round(1.0 / ecfg.ts))
    alive = np.ones(episodes, bool)
    ok_last = np.ones(episodes, bool)
    max_x = np.zeros(episodes)
    peak_v = np.zeros(episodes)
    t_up = np.full(episodes, np.nan)
    with torch.inference_mode():
        for k in range(n_steps - 1):   # the time-out step would reset the env
            a = policy(obs)
            obs, _, done, _ = env.step(a)
            x, th1, th2 = env._state[0], env._state[1], env._state[2]
            alive &= ~done.numpy()
            max_x = np.maximum(max_x, np.abs(x))
            peak_v = np.maximum(peak_v, np.abs(env.u[:, 0]))
            up = (np.abs(th1) < 0.1) & (np.abs(th2) < 0.1)
            newly = up & np.isnan(t_up)
            t_up[newly] = (k + 1) * ecfg.ts
            t_up[~up] = np.nan
            if k >= n_steps - 1 - last:
                ok_last &= up
    env.close()
    succ = alive & ok_last
    return {"success": float(succ.mean()), "fell": float((~alive).mean()), "maxX": float(max_x.max()),
            "peakV": float(peak_v.max()),
            "upTimeMedian": float(np.nanmedian(t_up[succ])) if succ.any() else float("nan")}


# The example's balance LQR (examples/pendulum-double-cart/library/DoubleCartCtrl.jl, discrete 1 kHz design
# gain, also stable at 200 Hz in this env): u = -K [x, th1, th2, v, w1, w2] in volts.
K_LQR = np.array([30.0509285, 128.115493, -257.959052, 23.9559011, -7.47878546, -26.3963107])


def lqr_action(env: DoubleCartEnv, obs) -> np.ndarray:
    p = obs["policy"].numpy().astype(float)
    x, th1, th2 = env._state[0], env._state[1], env._state[2]
    z = np.stack([x, th1, th2, p[:, 5], p[:, 6], p[:, 7]], 1)
    return np.clip(-(z @ K_LQR) / env.cfg.v_max, -1.0, 1.0)


def bc_lqr(runner, env: DoubleCartEnv, steps: int, rollout: int = 64, sigma: float = 0.2,
           region: float = 0.6) -> dict:
    """Warm start: fit the actor's mean to the LQR on the states the noisy expert visits from the
    env's resets: the LQR where both links are within ``region`` rad of upright, 0 V elsewhere (so
    the swing-up starts from "do nothing", not from the LQR extrapolated to hanging, which drives
    the cart off the rail). Sets the actor's observation normaliser from the same samples. The
    critic is left untrained (see ``--critic-warmup``)."""
    rng = np.random.default_rng(1)
    obs = env.get_observations()
    X, Y = [], []
    with torch.inference_mode():
        for _ in range(rollout):
            near = (np.abs(env._state[1]) < region) & (np.abs(env._state[2]) < region)
            a_star = np.where(near, lqr_action(env, obs), 0.0)
            X.append(obs["policy"].clone())
            Y.append(torch.as_tensor(a_star, dtype=torch.float32))
            a = a_star + sigma * rng.standard_normal(env.num_envs)
            obs, _, _, _ = env.step(torch.as_tensor(a[:, None], dtype=torch.float32))
    X, Y = torch.cat(X), torch.cat(Y)[:, None]
    actor = runner.alg.actor
    norm = actor.obs_normalizer
    norm.train()
    norm.update(X)
    norm.until = int(norm.count)   # frozen from here on: PPO's data must not move the cloned map
    opt = torch.optim.Adam(actor.mlp.parameters(), lr=1e-3)
    gen = torch.Generator().manual_seed(0)
    loss = torch.tensor(0.0)
    for _ in range(steps):
        idx = torch.randint(0, X.shape[0], (4096,), generator=gen)
        loss = torch.nn.functional.mse_loss(actor.mlp(norm(X[idx])), Y[idx])
        opt.zero_grad()
        loss.backward()
        opt.step()
    env._reset(np.ones(env.num_envs, bool))
    env.obs = env._observe()
    return {"samples": int(X.shape[0]), "loss": float(loss)}


def plot(curve_path: Path, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = list(csv.DictReader(curve_path.open()))
    if not rows:
        return
    it = np.array([float(r["envSteps"]) for r in rows]) / 1e6
    wall = np.array([float(r["wallS"]) for r in rows]) / 60
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
    ax[0].plot(it, [float(r["meanReward"]) for r in rows], color="#3b6fb6")
    ax[0].set_xlabel("env steps (millions)")
    ax[0].set_ylabel("mean reward per step (rollouts)")
    ax[0].grid(alpha=0.3)
    ev = [(float(r["envSteps"]) / 1e6, float(r["evalSuccess"]), float(r["wallS"]) / 60) for r in rows
          if r["evalSuccess"] != ""]
    if ev:
        ax[1].plot([e[2] for e in ev], [e[1] for e in ev], marker="o", ms=3, color="#c0504d")
    ax[1].set_xlabel("wall-clock (min)")
    ax[1].set_ylabel("eval success (64 swing-ups)")
    ax[1].set_ylim(-0.02, 1.02)
    ax[1].grid(alpha=0.3)
    fig.suptitle(f"PPO double cart swing-up + balance ({wall[-1]:.1f} min, {it[-1]:.0f} M steps)")
    fig.tight_layout()
    fig.savefig(out, dpi=120)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("export_dir", type=Path)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--iterations", type=int, default=1500)
    ap.add_argument("--envs", type=int, default=4096)
    ap.add_argument("--threads", type=int, default=12)
    ap.add_argument("--torch-threads", type=int, default=8)
    ap.add_argument("--hidden", default="64,64")
    ap.add_argument("--eval-every", type=int, default=25)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--stop-success", type=float, default=0.98,
                    help="stop when two evaluations in a row reach this success rate")
    ap.add_argument("--no-curriculum", action="store_true",
                    help="fixed resets (15 %% upright, rest hanging) instead of the reset curriculum")
    ap.add_argument("--upright-only", action="store_true",
                    help="balance only: every reset near the upright; the upright eval is the gate")
    ap.add_argument("--init-std", type=float, default=TrainCfg.init_std,
                    help="initial action noise std (action units, 1 = 24 V)")
    ap.add_argument("--drop-angle", type=float, default=0.8,
                    help="end the episode when a link passes this angle (rad) after a catch (0 = off)")
    ap.add_argument("--drop-penalty", type=float, default=50.0)
    ap.add_argument("--bc-lqr", type=int, default=0,
                    help="warm start: this many behaviour-cloning steps of the actor on the balance LQR")
    ap.add_argument("--critic-warmup", type=int, default=0,
                    help="iterations at the start with the actor frozen (fits the critic to a warm-started actor)")
    ap.add_argument("--catch-tol", type=float, default=0.0,
                    help="hybrid variant: the balance LQR takes over once z'Pz < this (rl/classical.json); "
                         "training episodes end there as a success")
    ap.add_argument("--p-up", type=float, help="with --no-curriculum: share of resets near upright")
    ap.add_argument("--p-random", type=float, help="with --no-curriculum: share of resets at random poses")
    ap.add_argument("--entropy", type=float, default=TrainCfg.entropy_coef)
    ap.add_argument("--gamma", type=float, default=TrainCfg.gamma)
    ap.add_argument("--resume", type=Path, help="continue from this checkpoint")
    args = ap.parse_args()
    torch.set_num_threads(args.torch_threads)
    torch.manual_seed(args.seed)
    run = args.run_dir.resolve()
    run.mkdir(parents=True, exist_ok=True)
    ecfg = EnvCfg(export_dir=str(args.export_dir.resolve()), num_envs=args.envs, threads=args.threads,
                  seed=args.seed)
    ecfg.drop_angle, ecfg.drop_penalty = args.drop_angle, args.drop_penalty
    if args.catch_tol > 0:
        cl = json.loads((Path(__file__).resolve().parent / "classical.json").read_text(encoding="utf-8"))
        ecfg.catch_tol = args.catch_tol
        ecfg.lqr_K = tuple(cl["K"])
        ecfg.lqr_P = tuple(np.ravel(cl["P"]).tolist())
    if args.p_up is not None:
        ecfg.p_upright_start = args.p_up
    if args.p_random is not None:
        ecfg.p_random_start = args.p_random
    if args.upright_only:
        ecfg.p_upright_start, ecfg.p_random_start = 1.0, 0.0
    tcfg = TrainCfg(hidden=[int(h) for h in args.hidden.split(",")], iterations=args.iterations,
                    init_std=args.init_std, entropy_coef=args.entropy, gamma=args.gamma)
    (run / "env.json").write_text(json.dumps(ecfg.to_dict(), indent=2), encoding="utf-8")
    cli = {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()}
    (run / "train.json").write_text(json.dumps({**asdict(tcfg), "runner": tcfg.runner_cfg(), "cli": cli}, indent=2),
                                    encoding="utf-8")
    curriculum = not (args.no_curriculum or args.upright_only)

    def schedule(s_hang: float) -> None:
        """The reset mix from the hanging-rest eval success: 20 % hanging at 0, 80 % at 1; the
        rest 60/40 near upright / random along the swing."""
        p_hang = 0.2 + 0.6 * s_hang
        env.cfg.p_upright_start = 0.6 * (1.0 - p_hang)
        env.cfg.p_random_start = 0.4 * (1.0 - p_hang)

    env = DoubleCartEnv(ecfg)
    if curriculum:
        schedule(0.0)

    from rsl_rl.runners import OnPolicyRunner

    runner = OnPolicyRunner(env, tcfg.runner_cfg(), log_dir=None, device="cpu")
    if args.resume:
        runner.load(str(args.resume))
    if args.bc_lqr:
        bc = bc_lqr(runner, env, args.bc_lqr)
        evb = evaluate(runner.get_inference_policy(), ecfg, upright=True, episodes=64)
        print(f"BC on the LQR: {bc['samples']} samples, loss {bc['loss']:.2e}, from upright "
              f"{evb['success']:.2f}", flush=True)
    if args.critic_warmup:
        actor_params = list(runner.alg.actor.parameters())
        for p in actor_params:
            p.requires_grad_(False)
        runner.learn(num_learning_iterations=args.critic_warmup)
        for p in actor_params:
            p.requires_grad_(True)
        print(f"critic warm-up: {args.critic_warmup} iterations with the actor frozen", flush=True)
    curve = (run / "curve.csv").open("w", newline="")
    w = csv.writer(curve)
    w.writerow(["iteration", "envSteps", "wallS", "meanReward", "evalSuccess", "evalFell", "evalMaxX",
                "evalPeakV", "evalUpTime", "actionStd", "evalUprightSuccess", "pHang"])
    t0 = time.perf_counter()
    steps_per_it = args.envs * tcfg.num_steps_per_env
    it = 0
    good = 0
    best = -1.0
    # Learn in chunks; the reward is tracked through a wrapper of the env's step.
    rewards: list[float] = []
    orig_step = env.step

    def step(actions):
        out = orig_step(actions)
        rewards.append(float(out[1].mean()))
        return out

    env.step = step
    while it < args.iterations:
        chunk = min(args.eval_every, args.iterations - it)
        rewards.clear()
        te, tp, t_chunk = env.t_env, env.t_plant, time.perf_counter()
        runner.learn(num_learning_iterations=chunk)
        it += chunk
        wall = time.perf_counter() - t0
        dt_chunk = time.perf_counter() - t_chunk
        print(f"  chunk {dt_chunk:.1f} s: env.step {env.t_env - te:.1f} s (C plant {env.t_plant - tp:.1f} s), "
              f"policy inference + PPO update {dt_chunk - (env.t_env - te):.1f} s", flush=True)
        policy = runner.get_inference_policy()
        ev = evaluate(policy, ecfg)
        evu = evaluate(policy, ecfg, upright=True, episodes=64 if args.upright_only else 32)
        p_hang = 1.0 - env.cfg.p_upright_start - env.cfg.p_random_start
        std = float(runner.alg.get_policy().output_std.mean())
        w.writerow([it, it * steps_per_it, f"{wall:.1f}", f"{np.mean(rewards):.4f}", ev["success"], ev["fell"],
                    f"{ev['maxX']:.3f}", f"{ev['peakV']:.2f}", f"{ev['upTimeMedian']:.2f}", f"{std:.3f}",
                    evu["success"], f"{p_hang:.2f}"])
        curve.flush()
        print(f"[it {it:5d}] {it * steps_per_it / 1e6:7.1f} M steps, {wall / 60:6.1f} min: reward "
              f"{np.mean(rewards):7.3f}, eval success {ev['success']:.2f} fell {ev['fell']:.2f} max|x| "
              f"{ev['maxX']:.3f} peak V {ev['peakV']:.1f} up at {ev['upTimeMedian']:.2f} s, std {std:.3f}; "
              f"from upright {evu['success']:.2f}; resets hanging {p_hang:.2f}", flush=True)
        if curriculum:
            schedule(ev["success"])
        runner.save(str(run / f"model_{it}.pt"))
        gate = evu["success"] if args.upright_only else ev["success"]
        if gate >= best:
            best = gate
            runner.save(str(run / "model_best.pt"))
        good = good + 1 if gate >= args.stop_success else 0
        if good >= 2:
            print("stop: success reached twice in a row", flush=True)
            break
    runner.save(str(run / "model.pt"))
    total = time.perf_counter() - t0
    (run / "summary.json").write_text(json.dumps({"iterations": it, "envSteps": it * steps_per_it,
                                                  "wallS": total, "bestEvalSuccess": best}, indent=2))
    curve.close()
    plot(run / "curve.csv", run / "curve.png")
    env.close()
    print(f"done: {it} iterations, {it * steps_per_it / 1e6:.1f} M env steps, {total / 60:.1f} min", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
