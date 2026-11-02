"""R1: a robust policy of the double-cart lab rig on the plant FMU with domain randomisation, the sensors and the
loop delay (rl/rlpend/renv.py), from an imitation warm start, then PPO (rsl_rl) with a cloning anchor.

    uv run --project rl rl/train_robust.py <plant export dir> <run dir> [--iterations N] [--bc-steps N]
        [--dagger N] [--bc-only] [--variant imitation|pure|hybrid] [--threads 6] [--torch-threads 4]

Imitation warm start (`--variant imitation`, the main row): the expert (renv.Teacher: the TVLQR swing-up and
the LQR on the TRUE state) is rolled out with action noise in the randomised env, the student (the actor, on its
encoder-history observation) is fitted to the expert's clean action on the visited states, plus `--dagger`
rounds on the student's own rollouts (relabelled by the expert, mixed with the expert's action for the rollout).
Then PPO with the BC anchor (DAPG-style), a frozen observation normaliser, the critic on the privileged state and
the draw's parameters. `pure`: PPO from scratch (fixed observation scale). `hybrid`: the RL swing-up hands over
to the LQR (on the differenced state of the two newest samples) at z'Pz < catch_tol.

Model selection on validation draws (seeds from 5000, not the shared test's 3000-3063): every `--eval-every`
iterations, the swing-up and balance-push scenarios of the shared test on 64 validation draws in the env.
Writes env.json, train.json, curve.csv/png, model_<it>.pt, model_best.pt, policy.npz (best) into the run dir.
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

os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")

import numpy as np  # noqa: E402
import torch  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rlpend.env import TrainCfg  # noqa: E402
from rlpend.renv import RobustCfg, RobustLabEnv, nominal, sample  # noqa: E402
import robust_eval as rev  # noqa: E402


def val_draws(n: int = 64, seed0: int = 5000):
    rng = np.random.default_rng(seed0)
    return [("nominal", nominal(), seed0 - 1)] + [(f"val{i:02d}", sample(rng), seed0 + i) for i in range(n)]


def export_npz(runner, cfg: RobustCfg, path: Path):
    actor = runner.alg.actor
    sd = actor.state_dict()
    norm = actor.obs_normalizer
    mu = norm._mean.detach().double().numpy().ravel()
    std = norm._std.detach().double().numpy().ravel() + norm.eps
    out = {"mu": mu, "sd": std, "hist": cfg.hist, "ts": cfg.ts, "v_max": cfg.v_max}
    k = j = 0
    while f"mlp.{k}.weight" in sd:
        out[f"W{j}"] = sd[f"mlp.{k}.weight"].double().numpy()
        out[f"b{j}"] = sd[f"mlp.{k}.bias"].double().numpy()
        k += 2
        j += 1
    np.savez(path, **out)


def evaluate(runner, cfg: RobustCfg, export_dir, draws, threads: int, catch=None) -> dict:
    pol = runner.get_inference_policy()

    def f(env):
        with torch.inference_mode():
            a = pol(env.obs).numpy().ravel().astype(float)
        if catch is not None:
            a = catch(env, a)
        return a
    out = {}
    for sc in ("swingup", "balance_push"):
        r = rev.run_scenario(export_dir, f, sc, threads, draws=draws, hist=cfg.hist, teacher_swing=False)
        out[sc] = r["summary"]
    return out


class Catch:
    """The hybrid's latched LQR takeover on the observation: z = [x, wrapped th1, th2, the newest differences]."""

    def __init__(self, path: Path, tol: float, v_max: float):
        d = json.loads(path.read_text(encoding="utf-8"))
        self.K, self.P, self.tol, self.v_max = np.asarray(d["K"]), np.asarray(d["P"]), tol, v_max
        self.mode = None

    def z(self, env):
        o = env._pol
        P0 = env.pipe.P[:, 0]
        return np.stack([P0[:, 0], np.remainder(P0[:, 1] + np.pi, 2 * np.pi) - np.pi,
                         np.remainder(P0[:, 2] + np.pi, 2 * np.pi) - np.pi, o[:, 5], o[:, 6], o[:, 7]], 1)

    def __call__(self, env, a):
        if self.mode is None or len(self.mode) != env.num_envs:
            self.mode = np.zeros(env.num_envs, bool)
        fresh = env.episode_length_buf.numpy() == 0
        self.mode[fresh] = False
        z = self.z(env)
        v = np.einsum("ij,jk,ik->i", z, self.P, z)
        self.mode |= v < self.tol
        a_lqr = np.clip(-(z @ self.K) / self.v_max, -1, 1)
        return np.where(self.mode, a_lqr, a)


def collect(env: RobustLabEnv, steps: int, sigma: float, rng, student=None, beta: float = 1.0, every: int = 2,
            p_upright: float | None = None):
    """Roll out (the expert, or a beta-mix of expert and student, plus noise) from fresh resets; return the
    student observations and the expert's clean actions."""
    keep = env.cfg.p_upright
    if p_upright is not None:
        env.cfg.p_upright = p_upright
    env._reset(np.ones(env.num_envs, bool))
    env.obs = env._observe(new_tick=False)
    X, Y = [], []
    with torch.inference_mode():
        for k in range(steps):
            a_star = env.teacher_action()
            if k % every == 0:
                X.append(env.obs["policy"].clone())
                Y.append(torch.as_tensor(a_star, dtype=torch.float32))
            a = a_star
            if student is not None:
                a_s = student(env.obs).numpy().ravel().astype(float)
                a = np.where(rng.random(env.num_envs) < beta, a_star, a_s)
            a = a + sigma * rng.standard_normal(env.num_envs)
            env.step(torch.as_tensor(np.clip(a, -1, 1)[:, None], dtype=torch.float32))
    env.cfg.p_upright = keep
    return torch.cat(X), torch.cat(Y)[:, None]


def fit(actor, X, Y, n: int, lr: float = 1e-3, batch: int = 8192) -> float:
    opt = torch.optim.Adam(actor.mlp.parameters(), lr=lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, n, eta_min=lr * 0.05)
    gen = torch.Generator().manual_seed(0)
    loss = torch.tensor(0.0)
    for _ in range(n):
        idx = torch.randint(0, X.shape[0], (batch,), generator=gen)
        loss = torch.nn.functional.mse_loss(actor.mlp(actor.obs_normalizer(X[idx])), Y[idx])
        opt.zero_grad()
        loss.backward()
        opt.step()
        sched.step()
    return float(loss)


def bc_anchor(actor, X, Y, steps: int, opt) -> float:
    loss = torch.tensor(0.0)
    for _ in range(steps):
        idx = torch.randint(0, X.shape[0], (4096,))
        loss = torch.nn.functional.mse_loss(actor.mlp(actor.obs_normalizer(X[idx])), Y[idx])
        opt.zero_grad()
        loss.backward()
        opt.step()
    return float(loss)


def plot(curve: Path, out: Path, title: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rows = list(csv.DictReader(curve.open()))
    if not rows:
        return
    wall = np.array([float(r["wallS"]) for r in rows]) / 60
    steps = np.array([float(r["envSteps"]) for r in rows]) / 1e6
    fig, ax = plt.subplots(1, 3, figsize=(14, 3.8))
    ax[0].plot(steps, [float(r["meanReward"]) for r in rows], color="#3b6fb6")
    ax[0].set_xlabel("env steps (M)")
    ax[0].set_ylabel("mean reward per step")
    for key, lab, col in (("swingOk", "swing-up 2 deg", "#c0504d"), ("balOk", "balance+push 2 deg", "#3b6fb6"),
                          ("swingOk57", "swing-up 5.7 deg", "#e8a09e"), ("balOk57", "balance+push 5.7 deg", "#9fb8de")):
        ax[1].plot(wall, [float(r[key]) for r in rows], marker="o", ms=3, color=col, label=lab)
    ax[1].set_ylim(-0.02, 1.02)
    ax[1].set_xlabel("wall-clock (min)")
    ax[1].set_ylabel("validation success (64 draws)")
    ax[1].legend(fontsize=7)
    ax[2].plot(wall, [float(r["swingTail"]) for r in rows], marker="o", ms=3, color="#c0504d", label="swing-up")
    ax[2].plot(wall, [float(r["balTail"]) for r in rows], marker="o", ms=3, color="#3b6fb6", label="balance+push")
    ax[2].set_xlabel("wall-clock (min)")
    ax[2].set_ylabel("median tail deviation (deg)")
    ax[2].set_yscale("log")
    ax[2].legend(fontsize=7)
    for a in ax:
        a.grid(alpha=0.3)
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(out, dpi=110)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("export_dir", type=Path)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--variant", choices=["imitation", "pure", "hybrid"], default="imitation")
    ap.add_argument("--iterations", type=int, default=300)
    ap.add_argument("--envs", type=int, default=4096)
    ap.add_argument("--threads", type=int, default=6)
    ap.add_argument("--torch-threads", type=int, default=4)
    ap.add_argument("--hidden", default="64,64")
    ap.add_argument("--hist", type=int, default=4)
    ap.add_argument("--eval-every", type=int, default=10)
    ap.add_argument("--eval-threads", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--bc-steps", type=int, default=6000)
    ap.add_argument("--bc-sigma", type=float, default=0.1)
    ap.add_argument("--dagger", type=int, default=2)
    ap.add_argument("--dagger-beta", type=float, default=0.5)
    ap.add_argument("--bc-only", action="store_true")
    ap.add_argument("--bc-anchor", type=int, default=20)
    ap.add_argument("--bc-anchor-lr", type=float, default=3e-4)
    ap.add_argument("--critic-warmup", type=int, default=20)
    ap.add_argument("--init-std", type=float, default=0.05)
    ap.add_argument("--entropy", type=float, default=0.0)
    ap.add_argument("--desired-kl", type=float, default=0.005)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--catch-tol", type=float, default=2e4)
    ap.add_argument("--dr", type=float, default=1.0)
    ap.add_argument("--episode-s", type=float, default=7.0)
    ap.add_argument("--resume", type=Path)
    ap.add_argument("--max-minutes", type=float, default=60.0)
    args = ap.parse_args()
    torch.set_num_threads(args.torch_threads)
    torch.manual_seed(args.seed)
    run = args.run_dir.resolve()
    run.mkdir(parents=True, exist_ok=True)
    export_dir = args.export_dir.resolve()
    cfg = RobustCfg(export_dir=str(export_dir), num_envs=args.envs, threads=args.threads, hist=args.hist,
                    seed=args.seed, dr=args.dr, episode_s=args.episode_s)
    pure = args.variant == "pure"
    hybrid = args.variant == "hybrid"
    if pure or hybrid:
        cfg.p_upright = 0.3 if pure else 0.0
    tcfg = TrainCfg(hidden=[int(h) for h in args.hidden.split(",")], iterations=args.iterations,
                    init_std=args.init_std, entropy_coef=args.entropy, desired_kl=args.desired_kl,
                    learning_rate=args.lr)
    (run / "env.json").write_text(json.dumps(cfg.to_dict(), indent=2), encoding="utf-8")
    cli = {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()}
    (run / "train.json").write_text(json.dumps({**asdict(tcfg), "runner": tcfg.runner_cfg(), "cli": cli}, indent=2),
                                    encoding="utf-8")
    env = RobustLabEnv(cfg)
    catch = None
    catch_path = Path(__file__).resolve().parent / "classical_lab.json"
    if hybrid:
        catch = Catch(catch_path, args.catch_tol, cfg.v_max)
        orig_step = env.step

        def hstep(actions):
            a = actions.numpy().ravel().astype(float)
            a = catch(env, a)
            entered = catch.mode.copy()
            obs, r, done, ex = orig_step(torch.as_tensor(a[:, None], dtype=torch.float32))
            return obs, r, done, ex
        env.step = hstep
    from rsl_rl.runners import OnPolicyRunner

    runner = OnPolicyRunner(env, tcfg.runner_cfg(), log_dir=None, device="cpu")
    actor = runner.alg.actor
    norm = actor.obs_normalizer
    vdraws = val_draws()
    t0 = time.perf_counter()
    log = (run / "log.txt").open("a", encoding="utf-8")

    def say(msg):
        print(msg, flush=True)
        log.write(msg + "\n")
        log.flush()

    bc = None
    if args.resume:
        runner.load(str(args.resume))
        say(f"resumed {args.resume}")
    if args.variant == "imitation" and not args.resume:
        rng = np.random.default_rng(1)
        t_ep = int(round(cfg.episode_s / cfg.ts))
        X, Y = collect(env, t_ep, args.bc_sigma, rng, every=4)
        norm.train()
        norm.update(X)
        norm.until = int(norm.count)          # frozen: PPO's data must not move the cloned map
        loss = fit(actor, X, Y, args.bc_steps)
        say(f"BC: {X.shape[0]} expert samples, loss {loss:.2e}, {time.perf_counter() - t0:.0f} s")
        for d in range(args.dagger):
            Xd, Yd = collect(env, t_ep, args.bc_sigma, rng, student=runner.get_inference_policy(),
                             beta=args.dagger_beta * (1 - d / max(args.dagger, 1)), every=4)
            X, Y = torch.cat([X, Xd]), torch.cat([Y, Yd])
            loss = fit(actor, X, Y, args.bc_steps)
            say(f"DAgger {d + 1}: {X.shape[0]} samples, loss {loss:.2e}, {time.perf_counter() - t0:.0f} s")
        bc = (X, Y)
        torch.save({"X": X, "Y": Y}, run / "bc_data.pt")
        runner.save(str(run / "model_bc.pt"))
    elif args.variant == "imitation" and args.resume:
        d = torch.load(args.resume.parent / "bc_data.pt")
        bc = (d["X"], d["Y"])
        norm.until = int(norm.count)
        say(f"BC data reloaded: {bc[0].shape[0]} samples")
    elif pure:
        # fixed hand scale of the observation (the R0.3 fix), never updated
        H = cfg.hist
        sc = [0.3, 1.0, 0.3, 1.0, 0.5] + [0.5, 3.0, 3.0] * H + [1.0] * H
        with torch.no_grad():
            s = torch.tensor([sc])
            norm._mean.zero_()
            norm._std.copy_(s - norm.eps)
            norm._var.copy_((s - norm.eps) ** 2)
        norm.until = 0
    curve_path = run / "curve.csv"
    new = not curve_path.exists() or args.resume is None
    curve = curve_path.open("w" if new else "a", newline="")
    w = csv.writer(curve)
    if new:
        w.writerow(["iteration", "envSteps", "wallS", "meanReward", "swingOk", "swingOk57", "swingTail", "balOk",
                    "balOk57", "balTail", "actionStd", "anchorLoss"])

    def record(it, rewards, anchor_loss):
        ev = evaluate(runner, cfg, export_dir, vdraws, args.eval_threads,
                      Catch(catch_path, args.catch_tol, cfg.v_max) if hybrid else None)
        s, b = ev["swingup"], ev["balance_push"]
        std = float(runner.alg.get_policy().output_std.mean()) if hasattr(runner.alg.get_policy(), "output_std") else 0.0
        wall = time.perf_counter() - t0
        steps = it * args.envs * tcfg.num_steps_per_env
        w.writerow([it, steps, f"{wall:.1f}", f"{np.mean(rewards) if rewards else 0:.4f}", s["mc_ok"] / 64,
                    s["mc_ok_5p7"] / 64, f"{s['tail_dev_deg_median']:.3f}", b["mc_ok"] / 64, b["mc_ok_5p7"] / 64,
                    f"{b['tail_dev_deg_median']:.3f}", f"{std:.4f}", f"{anchor_loss:.3e}"])
        curve.flush()
        say(f"[it {it:4d}] {steps / 1e6:6.1f} M steps {wall / 60:5.1f} min: reward "
            f"{np.mean(rewards) if rewards else 0:.3f} | val swing-up {s['mc_ok']}/64 (5.7: {s['mc_ok_5p7']}) tail "
            f"{s['tail_dev_deg_median']:.2f} deg x {s['peak_x_max']:.2f} | balance+push {b['mc_ok']}/64 (5.7: "
            f"{b['mc_ok_5p7']}) tail {b['tail_dev_deg_median']:.2f} deg | std {std:.3f}")
        return s["mc_ok"] + b["mc_ok"] + 0.01 * (s["mc_ok_5p7"] + b["mc_ok_5p7"])

    best = record(0, [], 0.0)
    runner.save(str(run / "model_0.pt"))
    runner.save(str(run / "model_best.pt"))
    export_npz(runner, cfg, run / "policy.npz")
    export_npz(runner, cfg, run / "policy_0.npz")
    if args.bc_only:
        plot(curve_path, run / "curve.png", f"R1 {run.name}: BC only")
        return 0
    if bc is not None and args.critic_warmup:
        ps = list(actor.parameters())
        for p in ps:
            p.requires_grad_(False)
        runner.learn(num_learning_iterations=args.critic_warmup)
        for p in ps:
            p.requires_grad_(True)
        say(f"critic warm-up: {args.critic_warmup} iterations")
    anchor = torch.optim.Adam(actor.mlp.parameters(), lr=args.bc_anchor_lr) if bc is not None else None
    rewards: list[float] = []
    orig = env.step

    def step(actions):
        out = orig(actions)
        rewards.append(float(out[1].mean()))
        return out
    env.step = step
    it = 0
    anchor_loss = 0.0
    while it < args.iterations:
        rewards.clear()
        for _ in range(args.eval_every):
            runner.learn(num_learning_iterations=1)
            if anchor is not None and args.bc_anchor:
                anchor_loss = bc_anchor(actor, bc[0], bc[1], args.bc_anchor, anchor)
            it += 1
        score = record(it, rewards, anchor_loss)
        runner.save(str(run / f"model_{it}.pt"))
        export_npz(runner, cfg, run / f"policy_{it}.npz")
        if score >= best:
            best = score
            runner.save(str(run / "model_best.pt"))
            export_npz(runner, cfg, run / "policy.npz")
            say(f"  best so far ({score:.2f})")
        plot(curve_path, run / "curve.png", f"R1 {run.name} ({args.variant})")
        if (time.perf_counter() - t0) / 60 > args.max_minutes:
            say("stop: time box")
            break
    total = time.perf_counter() - t0
    (run / "summary.json").write_text(json.dumps({"iterations": it, "envSteps": it * args.envs * tcfg.num_steps_per_env,
                                                  "wallS": total, "best": best}, indent=2))
    plot(curve_path, run / "curve.png", f"R1 {run.name} ({args.variant})")
    env.close()
    say(f"done: {it} iterations, {total / 60:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
