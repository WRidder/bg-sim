"""R0.4: turn a trained rsl_rl actor into a bgsim library block (``@discrete Ts`` = the policy period).

    uv run --project rl rl/make_policy_block.py <run dir> [--checkpoint model.pt]
        [--out examples/pendulum-double-cart/library/DoubleCartPolicy.jl]

The block repeats the training env's pipeline (rl/rlpend/env.py ``policy_obs`` and ``step``)
operation for operation:

    th1 = q1 - pi/2, th2 = th1 + q2
    o   = [sin th1, cos th1, sin th2, cos th2, x, (x - xp)/Ts, (th1 - th1p)/Ts, (th2 - th2p)/Ts, ap]
    z   = (o - mu) / (sd + eps)                         rsl_rl EmpiricalNormalization, eps = 1e-2
    h1  = tanh(W1 z + b1), h2 = tanh(W2 h1 + b2)        the actor MLP (deterministic: the mean)
    a   = clamp(dot(w3, h2) + b3, -1, 1),  u = v_max a  the env's action clip and scale
    xp, th1p, th2p, ap = x, th1, th2, a                  for the next tick

Before ``t_on`` the block outputs 0 V and only tracks the previous samples (a = 0), so at t_on
it starts exactly like a reset env. The weights are written with 9 significant digits, which
reproduces the float32 values exactly; the block computes in float64 (the env's actor in
float32: a difference of ~1e-6 in the action). The script checks the block's arithmetic in
numpy against the torch actor on the rollout distribution.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rlpend import EXAMPLE  # noqa: E402

EPS = 1e-2   # EmpiricalNormalization's default


def fmt(v) -> str:
    return "%.9g" % float(v)


def vec(a) -> str:
    return "[" + ", ".join(fmt(v) for v in np.ravel(a)) + "]"


def mat(a) -> str:
    return "[" + "; ".join(" ".join(fmt(v) for v in row) for row in np.asarray(a)) + "]"


def load_actor(path: Path) -> dict:
    sd = torch.load(path, map_location="cpu", weights_only=False)["actor_state_dict"]
    layers = []
    k = 0
    while f"mlp.{k}.weight" in sd:
        layers.append((sd[f"mlp.{k}.weight"].double().numpy(), sd[f"mlp.{k}.bias"].double().numpy()))
        k += 2
    return {"mu": sd["obs_normalizer._mean"].double().numpy().ravel(),
            "sd": sd["obs_normalizer._std"].double().numpy().ravel(), "layers": layers}


def forward_np(actor: dict, obs: np.ndarray) -> np.ndarray:
    z = (obs - actor["mu"]) / (actor["sd"] + EPS)
    h = z
    for j, (W, b) in enumerate(actor["layers"]):
        h = h @ W.T + b
        if j < len(actor["layers"]) - 1:
            h = np.tanh(h)
    return h[:, 0]


def task_text(env: dict, train: dict) -> str:
    cli = train.get("cli", {})
    task = ("Task: balance (trained from rest starts within +-0.3 rad of upright)."
            if env.get("p_upright_start", 0.0) >= 1.0 else "Task: swing-up from hanging rest and balance.")
    if cli.get("bc_lqr"):
        what = ("the example's TVLQR swing-up + balance LQR" if cli.get("bc_expert") == "tvlqr"
                else "the example's balance LQR")
        what += ", then PPO" + (" with a BC anchor" if cli.get("bc_anchor") else "")
        task += f"\n    # Warm start: behaviour cloning on {what}."
    return task


def block_source(actor: dict, env: dict, source: str, task: str = "", name: str = "DoubleCartPolicy") -> str:
    (W1, b1), (W2, b2), (W3, b3) = actor["layers"]
    n0, n1, n2 = W1.shape[1], W1.shape[0], W2.shape[0]
    ts = env["ts"]
    sdeps = actor["sd"] + EPS
    body = """            z = o
            for i in 1:n0
                z[i] = (o[i] - mu[i]) / sd[i]
            end
            h1 = W1 * z + b1
            for i in 1:n1
                h1[i] = tanh(h1[i])
            end
            h2 = W2 * h1 + b2
            for i in 1:n2
                h2[i] = tanh(h2[i])
            end
            a = clamp(dot(w3, h2) + b3, -1.0, 1.0)"""
    hyb_out = hyb_params = hyb_vars = hyb_set = ""
    if float(env.get("catch_tol", 0.0)) > 0:
        # the env's DoubleCartEnv.hybrid: latched catch on the LQR cost-to-go, then the balance LQR
        task += ("\n    # Hybrid (risk 4 (c)): once the LQR cost-to-go z' Pc z (z = [x, th1, th2, v, w1, w2], wrapped angles,"
                 "\n    # differenced rates) is below catch_tol, the example's balance LQR takes over, latched.")
        body = ("            zc = [x, w1, w2, o[6], o[7], o[8]]\n"
                "            vc = dot(zc, Pc * zc)\n"
                "            if mode < 0.5 && vc < catch_tol\n"
                "                mode = 1.0\n"
                "            end\n"
                "            if mode > 0.5\n"
                "                a = clamp(-dot(Klqr, zc) / v_max, -1.0, 1.0)\n"
                "            else\n"
                + "\n".join("    " + ln for ln in body.splitlines()) + "\n"
                "            end")
        P = np.asarray(env["lqr_P"], float).reshape(6, 6)
        hyb_out = '        lqr::Real = 0.0, [description = "1 once the LQR balances (latched catch)"]\n'
        hyb_params = (f'        catch_tol::Real = {fmt(env["catch_tol"])}, [min = 0, description = "Catch region: z\' Pc z below this"]\n'
                      f'        Pc::Mat{{6,6}} = {mat(P)}, [description = "LQR cost-to-go matrix (rl/classical.json)"]\n'
                      f'        Klqr::Vec{{6}} = {vec(env["lqr_K"])}, [description = "Balance LQR gain on [x, th1, th2, v, w1, w2] (u = -K z), as DoubleCartCtrl"]\n')
        hyb_vars = '        mode::Real = 0.0, [description = "1 once the LQR is in charge (latched)"]\n'
        hyb_set = "        lqr = mode\n"
    return f"""@block {name} begin
    # Learned controller of the double cart (plan/RL_PLAN.md, step 0): an rsl_rl PPO actor [{n1}, {n2}] tanh, a single
    # network running alone, trained on the exported plant FMU (pendulum-double-cart-plant). {task}
    # Generated by rl/make_policy_block.py from {source}: do not edit by hand.
    # Every tick (Ts = {ts} s) it reads the encoders, builds the training env's observation
    #   o = [sin th1, cos th1, sin th2, cos th2, x, (x - xp)/Ts, (th1 - th1p)/Ts, (th2 - th2p)/Ts, ap]
    # with th1 = q1 - pi/2, th2 = th1 + q2 (absolute angles from upright) and the previous samples, normalises it with
    # the stored mean and std, runs the MLP and outputs u = v_max * clamp(a, -1, 1). Before t_on: u = 0.
    @constants begin
        n0::Int = {n0}
        n1::Int = {n1}
        n2::Int = {n2}
    end
    @inputs begin
        x::Real, [unit = "m", description = "Cart position (encoder)"]
        q1::Real, [unit = "rad", description = "Joint 1 encoder: link 1 angle from the rail's x axis"]
        q2::Real, [unit = "rad", description = "Joint 2 encoder: link 2 relative to link 1"]
    end
    @outputs begin
        u::Real = 0.0, [unit = "V", description = "Motor terminal voltage"]
        th1::Real = -3.141592653589793, [unit = "rad", description = "Link 1 angle from upright, wrapped to [-pi, pi)"]
        th2::Real = -3.141592653589793, [unit = "rad", description = "Link 2 angle from upright, wrapped to [-pi, pi)"]
{hyb_out}    end
    @parameters begin
        t_on::Real = 1.0, [unit = "s", description = "The policy starts here (0 V before)"]
        v_max::Real = {fmt(env['v_max'])}, [unit = "V", min = 0, description = "Action scale and clamp (supply limit)"]
        mu::Vec{{n0}} = {vec(actor['mu'])}, [description = "Observation running mean (rsl_rl)"]
        sd::Vec{{n0}} = {vec(sdeps)}, [description = "Observation running std + 1e-2 (rsl_rl)"]
        W1::Mat{{n1,n0}} = {mat(W1)}
        b1::Vec{{n1}} = {vec(b1)}
        W2::Mat{{n2,n1}} = {mat(W2)}
        b2::Vec{{n2}} = {vec(b2)}
        w3::Vec{{n2}} = {vec(W3[0])}
        b3::Real = {fmt(b3[0])}
{hyb_params}    end
    @variables begin
        xp::Real = 0.0, [unit = "m", description = "Previous cart position sample"]
        th1p::Real = -3.141592653589793, [unit = "rad", description = "Previous th1 sample (unwrapped)"]
        th2p::Real = -3.141592653589793, [unit = "rad", description = "Previous th2 sample (unwrapped)"]
        ap::Real = 0.0, [description = "Previous action in [-1, 1]"]
{hyb_vars}    end
    @discrete Ts = {ts} begin
        a1 = q1 - 1.5707963267948966
        a2 = a1 + q2
        w1 = mod(a1 + 3.141592653589793, 6.283185307179586) - 3.141592653589793
        w2 = mod(a2 + 3.141592653589793, 6.283185307179586) - 3.141592653589793
        a = 0.0
        if t > t_on - 0.5 * Ts
            o = [sin(a1), cos(a1), sin(a2), cos(a2), x, (x - xp) / Ts, (a1 - th1p) / Ts, (a2 - th2p) / Ts, ap]
{body}
        end
        u = v_max * a
        xp = x
        th1p = a1
        th2p = a2
        ap = a
        th1 = w1
        th2 = w2
{hyb_set}    end
end
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--checkpoint", default="model.pt")
    ap.add_argument("--name", default="DoubleCartPolicy", help="block name (DoubleCartSwingPolicy: the swing-up)")
    ap.add_argument("--out", type=Path, help="default: the example's library/<name>.jl")
    args = ap.parse_args()
    if args.out is None:
        args.out = EXAMPLE / "library" / f"{args.name}.jl"
    run = args.run_dir.resolve()
    env = json.loads((run / "env.json").read_text(encoding="utf-8"))
    actor = load_actor(run / args.checkpoint)
    assert len(actor["layers"]) == 3, "the generator writes two hidden layers"
    train = json.loads((run / "train.json").read_text(encoding="utf-8"))
    assert train["activation"] == "tanh"

    # The numpy twin of the block against the torch actor (deterministic output).
    from rsl_rl.models import MLPModel
    from tensordict import TensorDict

    rng = np.random.default_rng(0)
    n = 2000
    th1 = rng.uniform(-np.pi, np.pi, n)
    th2 = rng.uniform(-np.pi, np.pi, n)
    obs = np.stack([np.sin(th1), np.cos(th1), np.sin(th2), np.cos(th2), rng.uniform(-0.4, 0.4, n),
                    rng.normal(0, 1, n), rng.normal(0, 8, n), rng.normal(0, 12, n), rng.uniform(-1, 1, n)], 1)
    td = TensorDict({"policy": torch.as_tensor(obs, dtype=torch.float32),
                     "privileged": torch.zeros(n, 7)}, batch_size=[n])
    rc = train["runner"]["actor"]
    model = MLPModel(td, {"actor": ["policy"]}, "actor", 1, hidden_dims=rc["hidden_dims"],
                     activation=rc["activation"], obs_normalization=True,
                     distribution_cfg=rc["distribution_cfg"])
    model.load_state_dict(torch.load(run / args.checkpoint, map_location="cpu", weights_only=False)["actor_state_dict"])
    model.eval()
    with torch.inference_mode():
        a_torch = model(td).numpy().ravel().astype(float)
    a_np = forward_np(actor, obs)
    diff = float(np.max(np.abs(a_np - a_torch)))
    print(f"numpy twin vs torch actor: max |a| difference {diff:.2e} over {n} observations")
    assert diff < 1e-4, diff

    src = block_source(actor, env, f"{run.name}/{args.checkpoint}", task_text(env, train), args.name)
    args.out.write_text(src, encoding="utf-8", newline="\n")
    print(f"wrote {args.out} ({len(src) / 1024:.0f} KiB, {sum(W.size + b.size for W, b in actor['layers'])} weights)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
