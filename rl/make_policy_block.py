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
from rlpend import EXAMPLES  # noqa: E402

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


def robust_block_source(w: dict, source: str, task: str, name: str = "DoubleCartLabRobustPolicy") -> str:
    """The R1 policy (rl/rlpend/renv.py ObsPipeline, rl/lab_policy.py) as a 1 kHz @discrete block: the encoders
    (noise inputs, 14-bit quantisation), the 200 Hz policy with its sample/action history and the loop delay."""
    H = int(w["hist"])
    ts = float(w["ts"])
    every = int(round(ts / 1e-3))
    W1, b1, W2, b2, W3, b3 = (w[k] for k in ("W0", "b0", "W1", "b1", "W2", "b2"))
    n0, n1, n2 = W1.shape[1], W1.shape[0], W2.shape[0]
    assert n0 == 5 + 4 * H
    hv = []
    for j in range(H + 1):
        hv += [f"px{j}", f"pa{j}", f"pb{j}"]
    av = [f"ap{j}" for j in range(1, H + 1)]
    var_lines = "\n".join(f"        {v}::Real = 0.0" for v in hv + av)
    fill = "\n".join(f"                px{j} = xm\n                pa{j} = m1\n                pb{j} = m2" for j in range(H + 1))
    shift = "\n".join(f"            px{j} = px{j - 1}\n            pa{j} = pa{j - 1}\n            pb{j} = pb{j - 1}"
                      for j in range(H, 0, -1))
    diffs = ", ".join(f"(px{j} - px{j + 1}) / Tp, (pa{j} - pa{j + 1}) / Tp, (pb{j} - pb{j + 1}) / Tp" for j in range(H))
    acts = ", ".join(av)
    ashift = "\n".join(f"            ap{j} = ap{j - 1}" for j in range(H, 1, -1))
    return f"""@block {name} begin
    # Robust learned controller of the double-cart lab rig (plan/RL_PLAN.md, step R1): an rsl_rl PPO actor [{n1}, {n2}] tanh,
    # a single network, trained on the plant FMU pendulum-double-cart-lab-plant with domain randomisation over
    # design/realism.json, the realism forces (Coulomb friction, cable springs, ripple, cogging), 14-bit noisy encoders and the
    # 1-2 ms loop delay. {task}
    # Generated by rl/make_policy_block.py --robust from {source}: do not edit by hand.
    # The block runs at 1 kHz and repeats the training env (rl/rlpend/renv.py) operation for operation:
    #   encoders  rel1 = (q1 - pi/2) + e1, rel2 = q2 + e2 (e1, e2: the noise inputs, rad), quantised to res_q (14 bit);
    #             x quantised to res_s; m = [xm, th1 = c1 res_q, th2 = (c1 + c2) res_q]
    #   policy    every {every} ticks from t_on (Tp = {ts} s): the history of the last {H + 1} samples m and the last {H} actions,
    #             o = [sin th1, cos th1, sin th2, cos th2, x, (m_k - m_(k-1))/Tp, ..., (m_(k-{H - 1}) - m_(k-{H}))/Tp, a_(k-1), ..., a_(k-{H})],
    #             z = (o - mu) / sd, two tanh layers, a = clamp(w3 h + b3, -1, 1), u_cmd = v_max a (held)
    #   delay     u = u_cmd from delay_ms ticks ago: the rig's whole-sample loop delay (0, 1 or 2 ms; 0 on the
    #             real rig, where the delay is physical)
    # Before t_on: u = 0; at t_on the history starts from the first sample (zero differences), like a reset env.
    @constants begin
        n0::Int = {n0}
        n1::Int = {n1}
        n2::Int = {n2}
    end
    @inputs begin
        x::Real, [unit = "m", description = "Cart position (motor encoder)"]
        q1::Real, [unit = "rad", description = "Joint 1 encoder: link 1 angle from the rail's x axis"]
        q2::Real, [unit = "rad", description = "Joint 2 encoder: link 2 relative to link 1"]
        e1::Real, [unit = "rad", description = "Joint 1 encoder noise"]
        e2::Real, [unit = "rad", description = "Joint 2 encoder noise"]
    end
    @outputs begin
        u::Real = 0.0, [unit = "V", description = "Motor terminal voltage (after the loop delay)"]
        u_cmd::Real = 0.0, [unit = "V", description = "The policy's command"]
        th1::Real = -3.141592653589793, [unit = "rad", description = "Measured link 1 angle from upright, wrapped"]
        th2::Real = -3.141592653589793, [unit = "rad", description = "Measured link 2 angle from upright, wrapped"]
    end
    @parameters begin
        t_on::Real = 1.0, [unit = "s", description = "The policy starts here (0 V before)"]
        v_max::Real = {fmt(w['v_max'])}, [unit = "V", min = 0, description = "Action scale and clamp (supply limit)"]
        Tp::Real = {fmt(ts)}, [unit = "s", description = "Policy period (the training env's)"]
        quant::Real = 1.0, [description = "1: quantise the encoders (res_q, res_s), 0: exact"]
        res_q::Real = {fmt(2 * np.pi / 2**14)}, [unit = "rad", description = "Joint encoder resolution (14 bit)"]
        res_s::Real = {repr(float(nominal_res_s()))}, [unit = "m", description = "Motor encoder resolution at the cart"]
        delay_ms::Real = 2.0, [description = "Loop delay in whole 1 ms samples (0, 1 or 2)"]
        mu::Vec{{n0}} = {vec(w['mu'])}, [description = "Observation mean (rsl_rl normaliser, frozen after cloning)"]
        sd::Vec{{n0}} = {vec(w['sd'])}, [description = "Observation std + 1e-2"]
        W1::Mat{{n1,n0}} = {mat(W1)}
        b1::Vec{{n1}} = {vec(b1)}
        W2::Mat{{n2,n1}} = {mat(W2)}
        b2::Vec{{n2}} = {vec(b2)}
        w3::Vec{{n2}} = {vec(W3[0])}
        b3::Real = {fmt(b3[0])}
    end
    @variables begin
        started::Real = 0.0
        kt::Real = 0.0, [description = "1 ms ticks since t_on"]
        d1::Real = 0.0, [unit = "V"]
        d2::Real = 0.0, [unit = "V"]
{var_lines}
    end
    @discrete Ts = 0.001 begin
        rel1 = (q1 - 1.5707963267948966) + e1
        rel2 = q2 + e2
        m1 = rel1
        m2 = rel1 + rel2
        xm = x
        if quant > 0.5
            c1 = round(rel1 / res_q)
            c2 = round(rel2 / res_q)
            m1 = c1 * res_q
            m2 = (c1 + c2) * res_q
            xm = round(x / res_s) * res_s
        end
        if t > t_on - 0.0005
            if started < 0.5
{fill}
                started = 1.0
                kt = 0.0
            end
            if mod(kt, {every}.0) < 0.5
{shift}
                px0 = xm
                pa0 = m1
                pb0 = m2
                o = [sin(m1), cos(m1), sin(m2), cos(m2), xm, {diffs}, {acts}]
                z = o
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
                a = clamp(dot(w3, h2) + b3, -1.0, 1.0)
{ashift}
                ap1 = a
                u_cmd = v_max * a
            end
            kt = kt + 1.0
        end
        uo = u_cmd
        if delay_ms > 1.5
            uo = d2
        elseif delay_ms > 0.5
            uo = d1
        end
        u = uo
        d2 = d1
        d1 = u_cmd
        th1 = mod(m1 + 3.141592653589793, 6.283185307179586) - 3.141592653589793
        th2 = mod(m2 + 3.141592653589793, 6.283185307179586) - 3.141592653589793
    end
end
"""


def nominal_res_s() -> float:
    spec = json.loads((EXAMPLES["lab"] / "design" / "realism.json").read_text(encoding="utf-8"))
    return spec["rigs"]["lab"]["params"]["base_res"]["nominal"]


def main_robust(args) -> int:
    run = args.run_dir.resolve()
    npz = run / args.checkpoint
    w = dict(np.load(npz))
    train = json.loads((run / "train.json").read_text(encoding="utf-8"))
    # the numpy twin (rl/lab_policy.py) against the torch actor
    from lab_policy import MLP
    from rsl_rl.models import MLPModel
    from tensordict import TensorDict
    pt = npz.with_name("model_best.pt" if npz.stem == "policy" else npz.stem.replace("policy", "model") + ".pt")
    if pt.exists():
        net = MLP(npz)
        rng = np.random.default_rng(0)
        n0 = w["W0"].shape[1]
        obs = w["mu"] + rng.normal(0, 1, (2000, n0)) * (w["sd"] - EPS)
        td = TensorDict({"policy": torch.as_tensor(obs, dtype=torch.float32), "privileged": torch.zeros(2000, 26)},
                        batch_size=[2000])
        rc = train["runner"]["actor"]
        model = MLPModel(td, {"actor": ["policy"]}, "actor", 1, hidden_dims=rc["hidden_dims"],
                         activation=rc["activation"], obs_normalization=True, distribution_cfg=rc["distribution_cfg"])
        model.load_state_dict(torch.load(pt, map_location="cpu", weights_only=False)["actor_state_dict"])
        model.eval()
        with torch.inference_mode():
            a_t = np.clip(model(td).numpy().ravel().astype(float), -1, 1)
        diff = float(np.max(np.abs(net(obs) - a_t)))
        print(f"numpy twin vs torch actor ({pt.name}): max |a| difference {diff:.2e}")
        assert diff < 1e-4, diff
    cli = train.get("cli", {})
    task = ("Warm start: behaviour cloning on the rig's TVLQR swing-up + LQR (on the true state)"
            + (f", {cli.get('dagger')} DAgger rounds" if cli.get("dagger") else "") + ", then PPO with a BC anchor."
            if cli.get("variant", "imitation") == "imitation" else f"Variant: {cli.get('variant')}.")
    src = robust_block_source(w, f"{run.name}/{args.checkpoint}", task, args.name)
    out = args.out or EXAMPLES["lab"] / "library" / f"{args.name}.jl"
    out.write_text(src, encoding="utf-8", newline="\n")
    nw = sum(w[k].size for k in w if k[0] in "Wb")
    print(f"wrote {out} ({len(src) / 1024:.0f} KiB, {nw} weights)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--checkpoint", default="model.pt")
    ap.add_argument("--robust", action="store_true",
                    help="R1: the robust lab policy (checkpoint = a policy*.npz of rl/train_robust.py)")
    ap.add_argument("--name", default="DoubleCartPolicy", help="block name (DoubleCartSwingPolicy: the swing-up)")
    ap.add_argument("--out", type=Path, help="default: the example's library/<name>.jl")
    ap.add_argument("--rig", choices=sorted(EXAMPLES), default="cart",
                    help="the example: cart = pendulum-double-cart, lab = pendulum-double-cart-lab")
    args = ap.parse_args()
    if args.robust:
        if args.name == "DoubleCartPolicy":
            args.name = "DoubleCartLabRobustPolicy"
        return main_robust(args)
    if args.out is None:
        args.out = EXAMPLES[args.rig] / "library" / f"{args.name}.jl"
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
