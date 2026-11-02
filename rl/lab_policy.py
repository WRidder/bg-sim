"""The R1 robust policy of the double-cart lab rig as a numpy controller (no torch), for the shared robustness
harness and the env evaluations:

    uv run examples/pendulum-double-cart-lab/design/robustness.py run --controller rl/lab_policy.py:robust_policy
        --name rl-imitation-dr --opt weights=rl/runs/<run>/policy.npz

The weights file (`rl/export_policy.py` writes it from an rsl_rl checkpoint) holds the observation normaliser
`mu`, `sd` (std + 1e-2), the layers `W0, b0, W1, b1, ...` (tanh between, the last linear), `hist` (H), `ts`
(the policy period) and `v_max`. The observation pipeline is `rlpend.renv.ObsPipeline` (the training env's),
from the encoder counts: th1 = c1 res_q, th2 = (c1 + c2) res_q, x = x_count res_s, at `1 / ts` (200 Hz) with
zero-order hold; the bgsim block (rl/make_policy_block.py --robust) repeats it operation for operation.
Optional `catch` (a classical_lab.json with catch_tol): the hybrid's latched LQR takeover on a least-squares
fit of the encoder history (up to 5 samples).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np


class ObsPipeline1:
    """`rlpend.renv.ObsPipeline` for one controller instance (kept free of the env's imports)."""

    def __init__(self, hist: int, ts: float):
        self.H, self.ts = hist, ts
        self.P = np.zeros((hist + 1, 3))
        self.A = np.zeros(hist)

    def reset(self, m):
        self.P[:] = np.asarray(m, float)[None, :]
        self.A[:] = 0.0

    def push(self, m):
        self.P[1:] = self.P[:-1]
        self.P[0] = m
        P = self.P
        d = (P[:-1] - P[1:]) / self.ts
        th1, th2 = P[0, 1], P[0, 2]
        return np.concatenate([[math.sin(th1), math.cos(th1), math.sin(th2), math.cos(th2), P[0, 0]],
                               d.ravel(), self.A])

    def act(self, a):
        self.A[1:] = self.A[:-1]
        self.A[0] = a

    def estimate(self, N: int) -> np.ndarray:
        """`RobustLabEnv.estimate`: least-squares line through the last N samples -> [x, th1, th2, rates]."""
        k = np.arange(N, dtype=float)
        kc = k - k.mean()
        P = self.P[:N]
        slope = -(kc @ P) / (kc @ kc) / self.ts
        return np.concatenate([P.mean(0) + slope * k.mean() * self.ts, slope])


class MLP:
    def __init__(self, path):
        d = np.load(path)
        self.mu, self.sd = d["mu"].ravel(), d["sd"].ravel()
        self.layers = []
        k = 0
        while f"W{k}" in d:
            self.layers.append((d[f"W{k}"], d[f"b{k}"].ravel()))
            k += 1
        self.hist = int(d["hist"])
        self.ts = float(d["ts"])
        self.v_max = float(d["v_max"])

    def __call__(self, o: np.ndarray) -> np.ndarray:
        """Batched (n, dim) or single (dim,) observation -> action(s) in [-1, 1]."""
        h = (o - self.mu) / self.sd
        for j, (W, b) in enumerate(self.layers):
            h = h @ W.T + b
            if j < len(self.layers) - 1:
                h = np.tanh(h)
        return np.clip(h[..., 0], -1.0, 1.0)


class RobustPolicy:
    def __init__(self, p_nominal: dict, weights: str, catch: str | None = None):
        self.net = MLP(weights)
        self.rate_hz = 1.0 / self.net.ts
        self.catch = None
        if catch:
            c = json.loads(Path(catch).read_text(encoding="utf-8"))
            self.catch = (np.array(c["K"], float).ravel(), np.array(c["P"], float), float(c["catch_tol"]))
        self.phase = 0

    def reset(self, *, seed: int, start: str):
        self.pipe = None
        self.latched = False
        self.phase = 1

    def step(self, s) -> float:
        m = s.positions()
        if self.pipe is None:
            self.pipe = ObsPipeline1(self.net.hist, self.net.ts)
            self.pipe.reset(m)
        o = self.pipe.push(m)
        if self.catch is not None:
            K, P, tol = self.catch
            z = self.pipe.estimate(min(5, self.net.hist + 1))
            z[1:3] = np.remainder(z[1:3] + math.pi, 2 * math.pi) - math.pi
            if self.latched or float(z @ P @ z) < tol:
                self.latched = True
                self.phase = 2
                a = min(max(-float(K @ z) / self.net.v_max, -1.0), 1.0)
                self.pipe.act(a)
                return self.net.v_max * a
        a = float(self.net(o))
        self.pipe.act(a)
        return self.net.v_max * a


def robust_policy(p_nominal: dict, **kw):
    return RobustPolicy(p_nominal, **kw)
