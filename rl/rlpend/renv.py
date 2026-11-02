"""The robust (R1) rsl_rl ``VecEnv`` of the double-cart lab rig on its plant FMU (plan/RL_PLAN.md step 1).

Physics: the plant FMU `pendulum-double-cart-lab-plant` is the single truth. Besides the bond graph it has the
realism forces of `library/LabRealism.jl` (Coulomb friction of the joints, the carriage and the motor, the cable
springs, commutation ripple and cogging) with their globals exposed, so a domain-randomised episode sets every
physical parameter of a `realism.json` draw before initialisation (`BatchedPlant.reset(params=...)`) and nothing
physical is added around the FMU. The armature lag is physical in the FMU (the motor's L_m).

Around the FMU, as on the rig (and as `design/robustness.py` does around the twin):
- the loop delay of the draw (1 or 2 ms): the command computed at a policy tick acts from d ms later; the env
  steps the d first internal 1 ms steps with the previous command (`bgenv_step_delay`);
- the sensors: the joint encoders measure th1 and th2 - th1 with white noise (joint_noise of the draw) and
  quantise them to 2^14 counts per turn; the motor encoder quantises x to base_res (`measure`);
- random tip pushes through `F_push` (the disturbance range of realism.json, 40 ms).

Actor observation (`ObsPipeline`, repeated operation for operation by the bgsim block and `rl/lab_policy.py`)
from the measured positions m_k = (x, th1, th2) at the 200 Hz ticks and its own previous actions:

    o = [sin th1, cos th1, sin th2, cos th2, x,
         (m_k - m_{k-1})/Ts, (m_{k-1} - m_{k-2})/Ts, ..., (m_{k-H+1} - m_{k-H})/Ts,    3 H differences
         a_{k-1}, ..., a_{k-H}]                                                        H previous actions

(5 + 4 H inputs; H = 4: 21). After a reset the history holds the first sample (zero differences) and zero
actions. The network can filter the 14-bit noise from the history instead of using one noisy difference.

Critic (privileged): the true state (wrapped angles, the FMU's rates), the motor current, the energy error, the
normalised parameters of the draw, the delay and the joint noise.

Expert (`teacher`): the rig's classical controller on the TRUE state: the TVLQR swing-up (the design.json tables,
from the reset, no hold) then the balance LQR, plus the Coulomb compensation of the nominal firmware. The
realism screen (design/screen_results.json) found that this design with a good state estimate passes all its
Monte Carlo draws over the realism ranges, so one nominal expert serves every draw; what the student has to
learn on top is the estimation from the encoder history.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch
from rsl_rl.env import VecEnv
from tensordict import TensorDict

from . import EXAMPLES
from .cbuild import BatchedPlant

G0 = 9.81
LAB = EXAMPLES["lab"]
REALISM = LAB / "design" / "realism.json"
CLASSICAL = Path(__file__).resolve().parents[1] / "classical_lab.json"
# the parameters the critic sees (normalised to [-1, 1] over their realism range)
CRITIC_PARAMS = ("m_tube1", "m_tube2", "com_shift1", "com_shift2", "m_head1", "m_tip2", "m_cart", "b_carriage",
                 "tc_carriage", "tc_motor", "tc_joint1", "tc_joint2", "R_m", "k_t", "ripple_rel", "cogging",
                 "joint_noise", "delay")


# ----------------------------------------------------------------------------- the parameter sets
def spec() -> dict:
    return json.loads(REALISM.read_text(encoding="utf-8"))["rigs"]["lab"]["params"]


def nominal() -> dict:
    return {k: v["nominal"] for k, v in spec().items()}


def sample(rng: np.random.Generator) -> dict:
    """One draw, exactly as quadlib.sample_realism (lablib.sample): uniform between min and max in the order
    of realism.json, integers for integer ranges, fixed when min == max."""
    out = {}
    for k, v in spec().items():
        lo, hi = v["min"], v["max"]
        if lo == hi:
            out[k] = v["nominal"]
        elif isinstance(lo, int) and isinstance(hi, int):
            out[k] = int(rng.integers(lo, hi + 1))
        else:
            out[k] = float(rng.uniform(lo, hi))
    return out


def test_draws() -> list[tuple[str, dict, int]]:
    """The draws of the shared test (design/robustness_test.json, design/robustness.py draws())."""
    t = json.loads((LAB / "design" / "robustness_test.json").read_text(encoding="utf-8"))
    mc = t["draws"]["monte_carlo"]
    rng = np.random.default_rng(mc["seed0"])
    out = [("nominal", nominal(), mc["seed0"] - 1)]
    for i in range(mc["n"]):
        out.append((f"mc{i:02d}", sample(rng), mc["seed0"] + i))
    return out


def link_props(p: dict) -> tuple:
    """lablib.link_props on arrays (each value of `p` a scalar or an (n,) array): per link mass, centre of mass
    from the pivot and inertia about the centre of mass."""
    L1, L2 = p["L1"], p["L2"]
    ro = p["tube_od"] / 2
    ri = ro - p["tube_wall"]

    def tube(m, L, shift):
        return (m, L * (0.5 + shift), m * (L * L / 12 + (ro * ro + ri * ri) / 4))

    def cube(m, x, s):
        return (m, x, m * s * s / 6)

    z = 0.0 * L1
    mc = p["rho_cable"] * L1
    link1 = [tube(p["m_tube1"], L1, p["com_shift1"]), cube(p["m_hub1"], z, p["s_hub"]), (p["m_enc_magnet"], z, z),
             cube(p["m_head1"], L1, p["s_head"]), (p["m_enc_board"], L1, z), (mc, L1 / 2, mc * L1 * L1 / 12)]
    link2 = [tube(p["m_tube2"], L2, p["com_shift2"]), cube(p["m_hub2"], z, p["s_hub"]), (p["m_enc_magnet"], z, z),
             cube(p["m_tip2"], L2, p["s_tip"])]
    ms, cs, Js = [], [], []
    for parts in (link1, link2):
        mt = sum(a for a, _, _ in parts)
        ct = sum(a * x for a, x, _ in parts) / mt
        ms.append(mt)
        cs.append(ct)
        Js.append(sum(j + a * (x - ct) ** 2 for a, x, j in parts))
    return ms, cs, Js


# ----------------------------------------------------------------------------- observation pipeline
class ObsPipeline:
    """The actor's observation from measured positions (n, 3) = (x, th1, th2) and the previous actions."""

    def __init__(self, n: int, hist: int, ts: float):
        self.n, self.H, self.ts = n, hist, ts
        self.P = np.zeros((n, hist + 1, 3))     # measured positions, index 0 the newest
        self.A = np.zeros((n, hist))            # previous actions, index 0 the newest

    @property
    def dim(self) -> int:
        return 5 + 4 * self.H

    def reset(self, mask: np.ndarray, m: np.ndarray):
        self.P[mask] = m[mask][:, None, :]
        self.A[mask] = 0.0

    def push(self, m: np.ndarray) -> np.ndarray:
        """A new tick: shift the history, store the sample, return the observation."""
        self.P[:, 1:] = self.P[:, :-1]
        self.P[:, 0] = m
        return self.obs()

    def obs(self) -> np.ndarray:
        P = self.P
        th1, th2 = P[:, 0, 1], P[:, 0, 2]
        d = (P[:, :-1] - P[:, 1:]) / self.ts           # (n, H, 3)
        return np.concatenate([np.stack([np.sin(th1), np.cos(th1), np.sin(th2), np.cos(th2), P[:, 0, 0]], 1),
                               d.reshape(self.n, -1), self.A], 1)

    def act(self, a: np.ndarray):
        self.A[:, 1:] = self.A[:, :-1]
        self.A[:, 0] = a


def wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


# ----------------------------------------------------------------------------- the expert
class Teacher:
    """TVLQR swing-up (from the reset, tau < T_s) then the balance LQR, on the true state, plus the nominal
    firmware's cart Coulomb compensation comp * fc tanh(v / (2 eps)) (volts). Returns volts."""

    def __init__(self, path: Path = CLASSICAL, comp: float = 1.0):
        d = json.loads(path.read_text(encoding="utf-8"))
        self.tk, self.uff, self.xs, self.Ks = (np.asarray(d[k]) for k in ("tk", "uff", "xs", "Ks"))
        self.T_s = float(d["T_s"])
        self.K = np.asarray(d["K"])
        self.u_max = float(d["u_max"])
        nom = nominal()
        n = nom["N_gear"] / nom["r_pulley"]
        alpha = nom["k_t"] * n / nom["R_m"]
        self.fc = comp * (nom["tc_carriage"] + nom["tc_motor"] * n) / alpha
        self.fc_eps = 2.0 * nom["eps_base"]

    def __call__(self, tau: np.ndarray, z: np.ndarray, swing: np.ndarray) -> np.ndarray:
        """tau: time since the reset (s); z = [x, th1, th2, v, w1, w2] (unwrapped angles); swing: the envs that
        run the swing-up (hanging starts); the others balance."""
        n = len(tau)
        out = np.empty(n)
        zw = z.copy()
        zw[:, 1:3] = wrap(z[:, 1:3])
        sw = swing & (tau < self.T_s)
        if sw.any():
            tt = tau[sw]
            uff = np.interp(tt, self.tk, self.uff)
            xs = np.stack([np.interp(tt, self.tk, self.xs[:, i]) for i in range(6)], 1)
            Ks = np.stack([np.interp(tt, self.tk, self.Ks[:, i]) for i in range(6)], 1)
            zs = z[sw].copy()
            zs[:, 1] = xs[:, 1] + wrap(z[sw, 1] - xs[:, 1])
            zs[:, 2] = xs[:, 2] + wrap(z[sw, 2] - xs[:, 2])
            out[sw] = uff - np.sum(Ks * (zs - xs), 1)
        if (~sw).any():
            out[~sw] = -(zw[~sw] @ self.K)
        out += self.fc * np.tanh(z[:, 3] / self.fc_eps)
        return np.clip(out, -self.u_max, self.u_max)


# ----------------------------------------------------------------------------- the env
@dataclass
class RobustCfg:
    export_dir: str
    num_envs: int = 4096
    threads: int = 8
    nsub: int = 5
    v_max: float = 24.0
    x_rail: float = 0.95
    x_soft: float = 0.80
    episode_s: float = 7.0
    hist: int = 4
    # domain randomisation: fraction of the realism range (0 = nominal; the delay and the noise always follow it)
    dr: float = 1.0
    sensors: bool = True             # noise + quantisation (False: exact positions)
    delay: bool = True
    # starts: hanging at rest (+- hang_noise), or upright with a lean (+- up_noise), share p_upright
    p_upright: float = 0.3
    hang_noise: tuple = (0.05, 0.05, 0.05)
    up_noise: tuple = (0.05, 0.12, 0.12)
    # random tip pushes: probability per episode, amplitude up to push_max (N), 40 ms, at a random time in
    # [push_t0, episode end - 1 s] (hanging starts: after the swing-up)
    p_push: float = 0.5
    push_max: float = 0.6
    push_t0_up: float = 0.5
    push_t0_hang: float = 3.8
    # reward
    w_up: float = 1.0
    w_balance: float = 2.0
    w_fine: float = 2.0
    fine_rad2: float = 0.0012       # exp(-(th1^2 + th2^2) / fine_rad2): about 2 deg
    w_energy: float = 1.0
    w_x: float = 1.0
    w_soft: float = 20.0
    w_rate: float = 0.05
    w_act: float = 0.01
    fall_penalty: float = 100.0
    catch_angle: float = 0.3
    drop_angle: float = 0.8
    drop_penalty: float = 50.0
    comp: float = 1.0               # the teacher's Coulomb compensation fraction
    seed: int = 0

    @property
    def ts(self) -> float:
        return self.nsub * 1e-3

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ts"] = self.ts
        return d


class RobustLabEnv(VecEnv):
    def __init__(self, cfg: RobustCfg, device: str = "cpu", draws: list[dict] | None = None):
        """`draws`: fixed parameter sets per env (evaluation), else sampled per episode."""
        self.cfg = cfg
        self.device = device
        self.num_envs = n = cfg.num_envs
        self.num_actions = 1
        self.max_episode_length = int(round(cfg.episode_s / cfg.ts))
        self.episode_length_buf = torch.zeros(n, dtype=torch.long)
        self.plant = p = BatchedPlant(Path(cfg.export_dir), n, threads=cfg.threads)
        self.iy = {k: p.y_names.index(k) for k in ("x", "q1", "q2", "v", "w1", "w2", "i_m")}
        self.iu = {k: p.u_names.index(k) for k in ("V", "F_push")}
        self.ix = {"x": p.x_names.index("__bgint/Rail/1"), "q1": p.x_names.index("__bgint/Joint1/2"),
                   "q2": p.x_names.index("__bgint/Joint2/3")}
        x0 = p.get_x()[0]
        self.offset = {k: p.y[0, self.iy[k]] - x0[self.ix[k]] for k in self.ix}
        self.ix_stop = next((i for i, s in enumerate(p.x_names) if s.startswith("__bgint/EndStops/")), None)
        if self.ix_stop is not None:
            self.offset_stop = p.y[0, self.iy["x"]] - x0[self.ix_stop]
        self.settable = [k for k in p.settable() if k in spec()]
        self.spec = spec()
        self.nom = nominal()
        self.rng = np.random.default_rng(cfg.seed)
        self.fixed_draws = draws
        self.pipe = ObsPipeline(n, cfg.hist, cfg.ts)
        self.teacher = Teacher(comp=cfg.comp)
        # per-env state
        self.params = {k: np.full(n, float(v)) for k, v in self.nom.items() if not isinstance(v, str)}
        self.delay = np.full(n, int(self.nom["delay"]), np.int32)
        self.noise_q = np.full(n, math.radians(self.nom["joint_noise"]))
        self.push_t = np.full(n, np.inf)
        self.push_a = np.zeros(n)
        self.swing = np.zeros(n, bool)
        self.caught = np.zeros(n, bool)
        self.u_prev = np.zeros(n)        # the command (V) of the previous period, still acting for `delay` ms
        self.a_prev = np.zeros(n)
        self.ep_ret = np.zeros(n)
        self.u0 = np.zeros((n, p.nu))
        self.u1 = np.zeros((n, p.nu))
        self.t_env = self.t_plant = 0.0
        self.n_steps = 0
        self.res_q = 2 * math.pi / 2 ** int(self.nom["joint_bits"])
        self.res_s = float(self.nom["base_res"])
        self._reset(np.ones(n, bool))
        self.obs = self._observe(new_tick=False)

    # -- parameters ------------------------------------------------------------------------
    def _draw(self, mask: np.ndarray):
        idx = np.where(mask)[0]
        for k in idx:
            if self.fixed_draws is not None:
                d = self.fixed_draws[k]
            else:
                d = sample(self.rng)
                f = self.cfg.dr
                if f < 1.0:
                    d = {kk: (self.nom[kk] + f * (v - self.nom[kk]) if isinstance(v, float) else v) for kk, v in d.items()}
            for kk, v in d.items():
                if kk in self.params:
                    self.params[kk][k] = float(v)
        self.delay[mask] = self.params["delay"][mask].astype(np.int32) if self.cfg.delay else 0
        self.noise_q[mask] = np.radians(self.params["joint_noise"][mask]) if self.cfg.sensors else 0.0
        ms, cs, Js = link_props({k: v for k, v in self.params.items()})
        self.m_l, self.c_l, self.J_l = ms, cs, Js
        self.E_up = G0 * (ms[0] * cs[0] + ms[1] * (self.params["L1"] + cs[1]))

    # -- resets ----------------------------------------------------------------------------
    def initial_states(self, mask):
        n, cfg = self.num_envs, self.cfg
        up = self.rng.random(n) < cfg.p_upright
        noise = np.where(up[:, None], np.array(cfg.up_noise), np.array(cfg.hang_noise))
        d = self.rng.uniform(-1.0, 1.0, (n, 3)) * noise
        return {"x": d[:, 0], "th1": np.where(up, 0.0, -np.pi) + d[:, 1],
                "th2": np.where(up, 0.0, -np.pi) + d[:, 2], "up": up}

    def set_pose(self, mask, x, th1, th2, up=None):
        """Reset the envs in `mask` to the pose at rest (absolute angles from upright) with a new draw."""
        self._draw(mask)
        q1 = th1 + math.pi / 2
        q2 = th2 - th1
        states = {self.ix["x"]: x - self.offset["x"], self.ix["q1"]: q1 - self.offset["q1"],
                  self.ix["q2"]: q2 - self.offset["q2"]}
        if self.ix_stop is not None:
            states[self.ix_stop] = x - self.offset_stop
        params = {k: self.params[k] for k in self.settable}
        self.plant.reset(mask, params=params, states=states)
        y = self.plant.y
        th1m = y[:, self.iy["q1"]] - math.pi / 2
        err = np.abs(np.stack([y[:, self.iy["x"]] - x, th1m - th1, th1m + y[:, self.iy["q2"]] - th2]))[:, mask]
        if err.size and err.max() > 1e-9:
            raise RuntimeError(f"set_pose: the plant reads back a different pose (max error {err.max():.3g})")
        up = (np.abs(wrap(th1)) < 1.0) if up is None else up
        self.swing = np.where(mask, ~up, self.swing)
        self.caught = np.where(mask, False, self.caught)
        self.u_prev = np.where(mask, 0.0, self.u_prev)
        self.a_prev = np.where(mask, 0.0, self.a_prev)
        self.ep_ret[mask] = 0.0
        self.episode_length_buf[torch.as_tensor(mask)] = 0
        # pushes
        cfg = self.cfg
        k = mask & (self.rng.random(self.num_envs) < cfg.p_push)
        t0 = np.where(up, cfg.push_t0_up, cfg.push_t0_hang)
        t1 = np.maximum(cfg.episode_s - 1.0, t0 + 0.01)
        tp = np.round((t0 + self.rng.random(self.num_envs) * (t1 - t0)) / cfg.ts) * cfg.ts
        self.push_t = np.where(mask, np.where(k, tp, np.inf), self.push_t)
        amp = self.rng.uniform(-1, 1, self.num_envs) * cfg.push_max
        self.push_a = np.where(mask, amp, self.push_a)
        self.pipe.reset(mask, self.measure())

    def _reset(self, mask):
        s = self.initial_states(mask)
        self.set_pose(mask, s["x"], s["th1"], s["th2"], s["up"])

    # -- sensors ---------------------------------------------------------------------------
    def true_state(self) -> np.ndarray:
        """[x, th1, th2, v, w1, w2] with unwrapped absolute angles and the FMU's rates."""
        y = self.plant.y
        th1 = y[:, self.iy["q1"]] - math.pi / 2
        th2 = th1 + y[:, self.iy["q2"]]
        w1 = y[:, self.iy["w1"]]
        return np.stack([y[:, self.iy["x"]], th1, th2, y[:, self.iy["v"]], w1, w1 + y[:, self.iy["w2"]]], 1)

    def measure(self) -> np.ndarray:
        """The encoders: (n, 3) measured x, th1, th2 (noise on the relative joint angles, then quantised)."""
        z = self.true_state()
        rel = np.stack([z[:, 1], z[:, 2] - z[:, 1]], 1)
        if self.cfg.sensors:
            rel = rel + self.noise_q[:, None] * self.rng.standard_normal((self.num_envs, 2))
            c = np.round(rel / self.res_q)
            xm = np.round(z[:, 0] / self.res_s) * self.res_s
            return np.stack([xm, c[:, 0] * self.res_q, (c[:, 0] + c[:, 1]) * self.res_q], 1)
        return np.stack([z[:, 0], rel[:, 0], rel[:, 0] + rel[:, 1]], 1)

    # -- observations ----------------------------------------------------------------------
    def energy(self, th1, th2, w1, w2):
        (m1, m2), (c1, c2), (J1, J2) = self.m_l, self.c_l, self.J_l
        L1 = self.params["L1"]
        v1sq = (c1 * w1) ** 2
        v2sq = (L1 * w1) ** 2 + (c2 * w2) ** 2 + 2 * L1 * c2 * w1 * w2 * np.cos(th1 - th2)
        T = 0.5 * m1 * v1sq + 0.5 * J1 * w1**2 + 0.5 * m2 * v2sq + 0.5 * J2 * w2**2
        V = G0 * (m1 * c1 * np.cos(th1) + m2 * (L1 * np.cos(th1) + c2 * np.cos(th2)))
        return T + V

    def _observe(self, new_tick: bool = True) -> TensorDict:
        if new_tick:
            pol = self.pipe.push(self.measure())
        else:
            pol = self.pipe.obs()
        self._pol = pol
        z = self.true_state()
        self._z = z
        th1, th2 = wrap(z[:, 1]), wrap(z[:, 2])
        E = self.energy(th1, th2, z[:, 4], z[:, 5])
        self._E = E
        pn = []
        for k in CRITIC_PARAMS:
            lo, hi = self.spec[k]["min"], self.spec[k]["max"]
            pn.append((self.params[k] - 0.5 * (lo + hi)) / (0.5 * (hi - lo) + 1e-12))
        priv = np.stack([z[:, 0], th1, th2, z[:, 3], z[:, 4], z[:, 5], self.plant.y[:, self.iy["i_m"]] / 10.0,
                         (E - self.E_up) / (2 * self.E_up), *pn], 1)
        return TensorDict({"policy": torch.as_tensor(pol, dtype=torch.float32),
                           "privileged": torch.as_tensor(priv, dtype=torch.float32)}, batch_size=[self.num_envs])

    def get_observations(self) -> TensorDict:
        return self.obs

    def teacher_action(self) -> np.ndarray:
        """The expert's action in [-1, 1] at the current tick (true state)."""
        tau = self.episode_length_buf.numpy() * self.cfg.ts
        return self.teacher(tau, self._z, self.swing) / self.cfg.v_max

    # -- step ------------------------------------------------------------------------------
    def step(self, actions: torch.Tensor):
        t_start = time.perf_counter()
        cfg = self.cfg
        a = np.clip(actions.detach().cpu().numpy().reshape(-1).astype(float), -1.0, 1.0)
        V = cfg.v_max * a
        t = self.episode_length_buf.numpy() * cfg.ts
        push = np.where((t >= self.push_t - 1e-9) & (t < self.push_t + 0.04 - 1e-9), self.push_a, 0.0)
        self.u0[:, self.iu["V"]] = self.u_prev
        self.u1[:, self.iu["V"]] = V
        self.u0[:, self.iu["F_push"]] = push
        self.u1[:, self.iu["F_push"]] = push
        t_p = time.perf_counter()
        self.plant.step_delay(self.u0, self.u1, self.delay, cfg.nsub)
        self.t_plant += time.perf_counter() - t_p
        self.u_prev = V
        a_prev = self.a_prev
        self.a_prev = a
        self.pipe.act(a)
        self.episode_length_buf += 1
        obs = self._observe()
        z = self._z
        x, th1, th2, w1, w2 = z[:, 0], wrap(z[:, 1]), wrap(z[:, 2]), z[:, 4], z[:, 5]
        up = 0.25 * (1.0 + np.cos(th1)) * (1.0 + np.cos(th2))
        r2 = th1**2 + th2**2
        bal = np.exp(-r2 / 0.05) * np.exp(-0.02 * (w1**2 + w2**2))
        fine = np.exp(-r2 / cfg.fine_rad2)
        e_err = np.abs(self._E - self.E_up) / (2 * self.E_up)
        soft = np.maximum(np.abs(x) - cfg.x_soft, 0.0)
        cost = (cfg.w_energy * e_err + cfg.w_x * x**2 + cfg.w_soft * soft + cfg.w_rate * (a - a_prev) ** 2
                + cfg.w_act * a**2)
        r = cfg.w_up * up + cfg.w_balance * bal + cfg.w_fine * fine - cost
        fell = (np.abs(x) > cfg.x_rail) | (self.plant.status != 0)
        r = np.where(fell, r - cfg.fall_penalty, r)
        self.caught |= (np.abs(th1) < cfg.catch_angle) & (np.abs(th2) < cfg.catch_angle)
        dropped = self.caught & ((np.abs(th1) > cfg.drop_angle) | (np.abs(th2) > cfg.drop_angle)) & ~fell
        if cfg.drop_angle > 0:
            r = np.where(dropped, r - cfg.drop_penalty, r)
        else:
            dropped[:] = False
        timeout = self.episode_length_buf.numpy() >= self.max_episode_length
        fell = fell | dropped
        done = fell | timeout
        self.ep_ret += r
        extras = {"time_outs": torch.as_tensor(timeout & ~fell)}
        if done.any():
            ok = (np.abs(th1) < 0.035) & (np.abs(th2) < 0.035)
            extras["log"] = {"/episode_return": float(self.ep_ret[done].mean()),
                             "/episode_fell": float(fell[done].mean()),
                             "/upright2deg_at_end": float(ok[done & timeout].mean()) if (done & timeout).any() else 0.0}
            self._reset(done)
            obs = self._observe(new_tick=False)
        self.obs = obs
        self.t_env += time.perf_counter() - t_start
        self.n_steps += 1
        return obs, torch.as_tensor(r, dtype=torch.float32), torch.as_tensor(done), extras

    def close(self):
        self.plant.close()
