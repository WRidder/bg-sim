"""The example's classical controllers as experts for imitation warm starts (plan/RL_PLAN.md risk 4 (b)).

Data from ``rl/classical.json`` (``rl/classical.py``). Both act on the env's own measurements at the
policy rate: wrapped absolute angles, the cart position and the differenced rates of the actor's
observation; actions are in [-1, 1] (V / v_max).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

CLASSICAL = Path(__file__).resolve().parents[1] / "classical.json"


def _z(env) -> np.ndarray:
    p = env._pol
    return np.stack([env._state[0], env._state[1], env._state[2], p[:, 5], p[:, 6], p[:, 7]], 1)


def classical_path(cfg) -> Path:
    return Path(cfg.classical) if getattr(cfg, "classical", "") else CLASSICAL


class Lqr:
    def __init__(self, path: Path = CLASSICAL):
        self.K = np.asarray(json.loads(path.read_text(encoding="utf-8"))["K"])

    def __call__(self, env) -> np.ndarray:
        return np.clip(-(_z(env) @ self.K) / env.cfg.v_max, -1.0, 1.0)


class TvlqrSwingUp:
    """The example's firmware without its hold phase: from a hanging start (tau = time since the
    env's reset), u = u_ff(tau) - K(tau) (z - z*(tau)) for tau < T_s (tables linearly interpolated,
    angles of z - z* not wrapped: the nominal runs from -pi to 0), then the balance LQR."""

    def __init__(self, path: Path = CLASSICAL):
        d = json.loads(path.read_text(encoding="utf-8"))
        self.tk = np.asarray(d["tk"])
        self.uff = np.asarray(d["uff"])
        self.xs = np.asarray(d["xs"])
        self.Ks = np.asarray(d["Ks"])
        self.T_s = float(d["T_s"])
        self.K = np.asarray(d["K"])

    def __call__(self, env) -> np.ndarray:
        tau = env.episode_length_buf.numpy() * env.cfg.ts
        z = _z(env)
        # unwrapped angles for the tracking error: the nominal starts at -pi
        p = env._pol
        th1u = np.arctan2(p[:, 0], p[:, 1])
        th2u = np.arctan2(p[:, 2], p[:, 3])
        out = np.empty(env.num_envs)
        sw = tau < self.T_s
        if sw.any():
            tt = tau[sw]
            uff = np.interp(tt, self.tk, self.uff)
            xs = np.stack([np.interp(tt, self.tk, self.xs[:, i]) for i in range(6)], 1)
            Ks = np.stack([np.interp(tt, self.tk, self.Ks[:, i]) for i in range(6)], 1)
            zs = z[sw].copy()
            # angle errors on the circle (the nominal crosses +-pi at the start)
            zs[:, 1] = xs[:, 1] + np.angle(np.exp(1j * (th1u[sw] - xs[:, 1])))
            zs[:, 2] = xs[:, 2] + np.angle(np.exp(1j * (th2u[sw] - xs[:, 2])))
            out[sw] = uff - np.sum(Ks * (zs - xs), 1)
        if (~sw).any():
            out[~sw] = -(z[~sw] @ self.K)
        return np.clip(out / env.cfg.v_max, -1.0, 1.0)
