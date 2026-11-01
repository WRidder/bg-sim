"""The rsl_rl ``VecEnv`` of the double cart pendulum on the batched FMU (plan/RL_PLAN.md R0.3).

Timing. One env step is one policy period ``Ts = nsub * dt`` (5 x 1 ms, 200 Hz): at t_k the
policy reads the encoders (x, q1, q2 sampled at t_k), its voltage is held over [t_k, t_k + Ts)
(zero-order hold, no delay), exactly like a ``@discrete Ts`` block in bgsim.

Observation pipeline (``policy_obs``; the generated bgsim block repeats it operation for
operation), from the encoder readings only:
    th1 = q1 - pi/2, th2 = th1 + q2                     absolute angles from the upward vertical
    [sin th1, cos th1, sin th2, cos th2, x,
     (x - x_prev)/Ts, (th1 - th1_prev)/Ts, (th2 - th2_prev)/Ts, a_prev]
with the previous samples and the previous action ``a_prev`` (clipped, in [-1, 1]); at a reset
the previous samples are the current ones and a_prev = 0. Action: V = V_max * clip(a, -1, 1).
The critic also sees the true rates, the motor current, the wrapped angles and the energy error
("privileged").

Reward per step (the angles wrapped to (-pi, pi]):
    up       = (1 + cos th1)/2 * (1 + cos th2)/2        in [0, 1], both links must be up
    balance  = exp(-(th1^2 + th2^2)/0.05) * exp(-0.02 (w1^2 + w2^2))
    energy   = |E - E_up| / (2 E_up)                    pendulum energy in the cart frame
    r = w_up up + w_balance balance - w_energy energy - w_x x^2 - w_soft max(|x| - x_soft, 0)
        - w_rate (a - a_prev)^2 - w_act a^2
and -fall_penalty when the cart leaves the rail (|x| > 0.40 m), which ends the episode. The time
limit (``episode_s``) is a time-out, not a termination. (A first version with the sum
(cos th1 + cos th2)/2, w_energy 0.5, w_soft 5 found the local optimum "link 1 up, link 2
spinning" and kicked the cart past the rail end at the start.)
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import torch
from rsl_rl.env import VecEnv
from tensordict import TensorDict

from .cbuild import BatchedPlant

G0 = 9.81


@dataclass
class EnvCfg:
    export_dir: str
    num_envs: int = 4096
    threads: int = 12
    nsub: int = 5                    # internal 1 ms steps per policy step
    v_max: float = 24.0              # supply limit = action scale = clamp
    x_rail: float = 0.40             # episode end
    x_soft: float = 0.30             # soft limit of the rail penalty
    episode_s: float = 6.0
    p_upright_start: float = 0.15    # share of resets near the upright (balance practice)
    hang_noise: tuple = (0.05, 0.15, 0.15)   # x (m), th1, th2 (rad): uniform +- around hanging
    up_noise: tuple = (0.05, 0.15, 0.15)
    w_up: float = 1.0
    w_balance: float = 2.0
    w_energy: float = 1.0
    w_x: float = 1.0
    w_soft: float = 20.0
    w_rate: float = 0.05
    w_act: float = 0.01
    fall_penalty: float = 100.0
    seed: int = 0
    # the plant geometry for the energy (the export's nominal values; no randomisation in step 0)
    m: tuple = (0.10, 0.08)
    L: tuple = (0.25, 0.25)

    @property
    def ts(self) -> float:
        return self.nsub * 1e-3

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ts"] = self.ts
        return d


def wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


def policy_obs(x, q1, q2, prev, a_prev, ts):
    """The actor's observation from the encoder readings; ``prev`` = (x, th1, th2) of the last
    sample. Returns (obs (n, 9), new prev)."""
    th1 = q1 - math.pi / 2
    th2 = th1 + q2
    obs = np.stack([np.sin(th1), np.cos(th1), np.sin(th2), np.cos(th2), x,
                    (x - prev[0]) / ts, (th1 - prev[1]) / ts, (th2 - prev[2]) / ts, a_prev], axis=1)
    return obs, (np.array(x, copy=True), th1, th2)   # x may be a view of the plant's output buffer


class DoubleCartEnv(VecEnv):
    def __init__(self, cfg: EnvCfg, device: str = "cpu"):
        self.cfg = cfg
        self.device = device
        self.num_envs = cfg.num_envs
        self.num_actions = 1
        self.max_episode_length = int(round(cfg.episode_s / cfg.ts))
        self.episode_length_buf = torch.zeros(self.num_envs, dtype=torch.long)
        self.plant = BatchedPlant(Path(cfg.export_dir), cfg.num_envs, threads=cfg.threads)
        p = self.plant
        self.iy = {k: p.y_names.index(k) for k in ("x", "q1", "q2", "v", "w1", "w2", "i_m")}
        self.ix = {"x": p.x_names.index("__bgint/Rail/1"), "q1": p.x_names.index("__bgint/Joint1/2"),
                   "q2": p.x_names.index("__bgint/Joint2/3")}
        # output = state + offset (the joint's q0), read once from the export's start
        x0 = p.get_x()[0]
        self.offset = {k: p.y[0, self.iy[k]] - x0[self.ix[k]] for k in self.ix}
        self.rng = np.random.default_rng(cfg.seed)
        n = self.num_envs
        self.a_prev = np.zeros(n)
        self.prev = (np.zeros(n), np.zeros(n), np.zeros(n))
        self.ep_ret = np.zeros(n)
        self.u = np.zeros((n, p.nu))
        self.t_env = 0.0      # wall time inside step() (s), of which
        self.t_plant = 0.0    # inside the C plant step
        self.n_steps = 0
        m1, m2 = cfg.m
        L1, L2 = cfg.L
        self.E_up = G0 * (m1 * L1 / 2 + m2 * (L1 + L2 / 2))
        self._reset(np.ones(n, bool))
        self.obs = self._observe()

    # -- state -----------------------------------------------------------------------------
    def initial_states(self, mask: np.ndarray) -> dict[str, np.ndarray]:
        """Poses at rest: around hanging, or (a share) around upright."""
        n = self.num_envs
        cfg = self.cfg
        up = self.rng.random(n) < cfg.p_upright_start
        noise = np.where(up[:, None], np.array(cfg.up_noise), np.array(cfg.hang_noise))
        d = self.rng.uniform(-1.0, 1.0, (n, 3)) * noise
        x = d[:, 0]
        th1 = np.where(up, 0.0, -np.pi) + d[:, 1]
        th2 = np.where(up, 0.0, -np.pi) + d[:, 2]
        return {"x": x, "th1": th1, "th2": th2}

    def set_pose(self, mask, x, th1, th2):
        """Reset the instances in ``mask`` to the pose (absolute angles from upright) at rest."""
        q1 = th1 + math.pi / 2
        q2 = th2 - th1
        states = {self.ix["x"]: x - self.offset["x"], self.ix["q1"]: q1 - self.offset["q1"],
                  self.ix["q2"]: q2 - self.offset["q2"]}
        self.plant.reset(mask, states=states)
        y = self.plant.y
        th1m = y[:, self.iy["q1"]] - math.pi / 2
        err = np.abs(np.stack([y[:, self.iy["x"]] - x, th1m - th1, th1m + y[:, self.iy["q2"]] - th2]))[:, mask]
        if err.size and err.max() > 1e-9:
            raise RuntimeError(f"set_pose: the plant reads back a different pose (max error {err.max():.3g})")
        px, p1, p2 = self.prev
        self.prev = (np.where(mask, y[:, self.iy["x"]], px), np.where(mask, th1m, p1),
                     np.where(mask, th1m + y[:, self.iy["q2"]], p2))
        self.a_prev = np.where(mask, 0.0, self.a_prev)
        self.episode_length_buf[torch.as_tensor(mask)] = 0
        self.ep_ret[mask] = 0.0

    def _reset(self, mask):
        s = self.initial_states(mask)
        self.set_pose(mask, s["x"], s["th1"], s["th2"])

    # -- observations ----------------------------------------------------------------------
    def _observe(self) -> TensorDict:
        y = self.plant.y
        x, q1, q2 = y[:, self.iy["x"]], y[:, self.iy["q1"]], y[:, self.iy["q2"]]
        pol, self._next_prev = policy_obs(x, q1, q2, self.prev, self.a_prev, self.cfg.ts)
        th1 = wrap(q1 - math.pi / 2)
        th2 = wrap(q1 - math.pi / 2 + q2)
        w1 = y[:, self.iy["w1"]]
        w2 = w1 + y[:, self.iy["w2"]]
        E = self.energy(th1, th2, w1, w2)
        priv = np.stack([y[:, self.iy["v"]], w1, w2, y[:, self.iy["i_m"]] / 10.0, th1, th2,
                         (E - self.E_up) / (2 * self.E_up)], axis=1)
        self._state = (x, th1, th2, w1, w2, E)
        return TensorDict({"policy": torch.as_tensor(pol, dtype=torch.float32),
                           "privileged": torch.as_tensor(priv, dtype=torch.float32)},
                          batch_size=[self.num_envs])

    def energy(self, th1, th2, w1, w2):
        """Pendulum energy in the cart frame (rods, centre of mass at the middle)."""
        m1, m2 = self.cfg.m
        L1, L2 = self.cfg.L
        c1, c2 = L1 / 2, L2 / 2
        J1, J2 = m1 * L1 * L1 / 12, m2 * L2 * L2 / 12
        v1sq = (c1 * w1) ** 2
        v2sq = (L1 * w1) ** 2 + (c2 * w2) ** 2 + 2 * L1 * c2 * w1 * w2 * np.cos(th1 - th2)
        T = 0.5 * m1 * v1sq + 0.5 * J1 * w1**2 + 0.5 * m2 * v2sq + 0.5 * J2 * w2**2
        V = G0 * (m1 * c1 * np.cos(th1) + m2 * (L1 * np.cos(th1) + c2 * np.cos(th2)))
        return T + V

    def get_observations(self) -> TensorDict:
        return self.obs

    # -- step ------------------------------------------------------------------------------
    def step(self, actions: torch.Tensor):
        t_start = time.perf_counter()
        cfg = self.cfg
        a = np.clip(actions.detach().cpu().numpy().reshape(-1).astype(float), -1.0, 1.0)
        self.u[:, 0] = cfg.v_max * a
        self.prev = self._next_prev
        t_p = time.perf_counter()
        self.plant.step(self.u, cfg.nsub)
        self.t_plant += time.perf_counter() - t_p
        a_prev = self.a_prev
        self.a_prev = a
        obs = self._observe()
        x, th1, th2, w1, w2, E = self._state
        up = 0.25 * (1.0 + np.cos(th1)) * (1.0 + np.cos(th2))
        bal = np.exp(-(th1**2 + th2**2) / 0.05) * np.exp(-0.02 * (w1**2 + w2**2))
        e_err = np.abs(E - self.E_up) / (2 * self.E_up)
        soft = np.maximum(np.abs(x) - cfg.x_soft, 0.0)
        r = (cfg.w_up * up + cfg.w_balance * bal - cfg.w_energy * e_err - cfg.w_x * x**2
             - cfg.w_soft * soft - cfg.w_rate * (a - a_prev) ** 2 - cfg.w_act * a**2)
        fell = (np.abs(x) > cfg.x_rail) | (self.plant.status != 0)
        r = np.where(fell, r - cfg.fall_penalty, r)
        self.episode_length_buf += 1
        timeout = self.episode_length_buf.numpy() >= self.max_episode_length
        done = fell | timeout
        self.ep_ret += r
        extras = {"time_outs": torch.as_tensor(timeout & ~fell)}
        if done.any():
            upright = (np.abs(th1) < 0.2) & (np.abs(th2) < 0.2)
            extras["log"] = {
                "/episode_return": float(self.ep_ret[done].mean()),
                "/episode_fell": float(fell[done].mean()),
                "/upright_at_end": float(upright[done & timeout].mean()) if (done & timeout).any() else 0.0,
                "/episode_length_s": float(self.episode_length_buf.numpy()[done].mean() * cfg.ts),
            }
            self._reset(done)
            obs = self._observe()
        self.obs = obs
        self.t_env += time.perf_counter() - t_start
        self.n_steps += 1
        return (obs, torch.as_tensor(r, dtype=torch.float32), torch.as_tensor(done), extras)

    def close(self):
        self.plant.close()


@dataclass
class TrainCfg:
    hidden: list = field(default_factory=lambda: [64, 64])
    activation: str = "tanh"
    num_steps_per_env: int = 32
    iterations: int = 1500
    learning_rate: float = 1e-3
    gamma: float = 0.995
    lam: float = 0.95
    entropy_coef: float = 0.01
    init_std: float = 1.0
    num_learning_epochs: int = 5
    num_mini_batches: int = 4

    def runner_cfg(self) -> dict:
        return {
            "num_steps_per_env": self.num_steps_per_env,
            "save_interval": 100,
            "obs_groups": {"actor": ["policy"], "critic": ["policy", "privileged"]},
            "logger": "tensorboard",
            "algorithm": {
                "class_name": "PPO", "learning_rate": self.learning_rate, "gamma": self.gamma, "lam": self.lam,
                "entropy_coef": self.entropy_coef, "num_learning_epochs": self.num_learning_epochs,
                "num_mini_batches": self.num_mini_batches, "schedule": "adaptive", "desired_kl": 0.01,
                "clip_param": 0.2, "value_loss_coef": 1.0, "max_grad_norm": 1.0,
            },
            "actor": {
                "class_name": "MLPModel", "hidden_dims": list(self.hidden), "activation": self.activation,
                "obs_normalization": True,
                "distribution_cfg": {"class_name": "GaussianDistribution", "init_std": self.init_std,
                                     "std_type": "scalar"},
            },
            "critic": {"class_name": "MLPModel", "hidden_dims": [128, 128], "activation": "elu",
                       "obs_normalization": True},
        }
