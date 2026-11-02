# /// script
# requires-python = ">=3.11"
# dependencies = ["casadi>=3.6", "numpy>=2.0", "scipy>=1.13"]
# ///
"""The shared robustness test of the double-cart lab rig (`design/robustness_test.json`): runs any controller
on the truth twin and writes `design/robustness_results.json` (plan C1-C3 and C5, RL step R1).

    uv run examples/pendulum-double-cart-lab/design/robustness.py nominal [--jobs 8]
    uv run examples/pendulum-double-cart-lab/design/robustness.py run --controller MODULE:FACTORY --name NAME
        [--opt key=value ...] [--jobs 8] [--scenarios swingup,balance_push,knockdown_recover]
        [--draws nominal,0-63] [--dry]
    uv run examples/pendulum-double-cart-lab/design/robustness.py show [--name NAME]

`MODULE` is a module importable from `design/` (e.g. `robustness`, `robust_ctrl`) or a path to a .py file
(e.g. `rl/lab_policy.py`); `FACTORY(p_nominal, **opts)` returns a controller (`--opt key=value` passes the
options as strings). A controller that needs extra packages runs with `uv run --with torch ... robustness.py
run ...`. `--dry` runs the nominal draw only and writes nothing. The default scenarios are the scored two
(`swingup`, `balance_push`); `knockdown_recover` (unscored) runs on request.

Controller protocol (duck-typed; see `Sensors`, `FirmwareController`, `MLPPolicy`):

    rate_hz: float                       # tick rate; 1000 / rate_hz must be an integer number of 1 ms samples
    reset(*, seed: int, start: str)      # before each run; start = "hanging" or "upright" (a timed firmware may
                                         # use it to select balance-only; a state-driven controller ignores it)
    step(s: Sensors) -> float            # the motor voltage command, held (zero-order hold) until the next tick
    phase: int (optional)                # reported per sample (0 hold, 1 swing-up, 2 balance, by convention)

The controller sees only what real firmware gets (`Sensors`): the time, the two joint-encoder counts, the motor
encoder count and its own previous command. It knows the nominal parameter set (the factory's argument) and
does its own estimation (filtered differences, an EKF, an observation history).

Truth (per 1 ms sample, `robustness_test.json` truth_model): the twin of `lablib.setup(p, EFFECTS)` for the
draw p (every effect of realism.json, RK4 with 8 substeps); the encoders measure the joint angles with white
noise (joint_noise of the draw) and quantise them (14 bit), the motor encoder the cart position (base_res);
the command passes the drive clamp |V| <= u_max, the whole-sample loop delay of the draw (1 or 2 samples:
the command computed at sample k acts from sample k + delay) and the armature lag L_m / R_m (the plant sees
its mean over each sample). The tip push acts perpendicular to link 2.

Draws: `nominal` (realism.json nominal column, noise seed 2999) and Monte Carlo draws 0..63: the parameter
sets `lablib.sample(rng)` drawn in sequence from `numpy.random.default_rng(3000)` (as the realism screen does
with 2000), draw i with seed 3000 + i. The seed sets the start noise (`default_rng([seed, 1])`: hanging rest
of the twin plus normal noise, sd 2 deg on each link angle and 0.05 rad/s on each link rate; the same for
`swingup` and `knockdown_recover`) and the sensor noise (`default_rng([seed, 2])`), and is passed to
`reset`.

Scoring (`pass` of the test): the run finishes (no divergence), |x| < 0.95 m throughout, and both links are
within 2 deg of upright (angles wrapped to +-pi) over the last 2 s; `ok_5p7` the same with 5.7 deg. Per run:
catch time (the first time after which both links stay within 2 deg to the end), peak |V| (the applied
voltage), peak |i_m| (quasi-static armature current, `lablib.current`), peak |x|, rms V over the tail, the
tail deviation. Raw runs (10 ms decimated, npz) go to `design/_robustness/<name>/` (ignored by git).
"""

from __future__ import annotations

import dataclasses
import datetime
import importlib
import importlib.util
import json
import math
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

import lablib as lb  # noqa: E402

ql = lb.ql
TEST = json.loads((HERE / "robustness_test.json").read_text(encoding="utf-8"))
RESULTS = HERE / "robustness_results.json"
RAW = HERE / "_robustness"
TS = lb.TS
SCORED = [k for k, v in TEST["scenarios"].items() if v.get("scored")]
SUB = int(TEST["truth_model"]["substeps_per_ms"])
P_NOM = lb.nominal()
RES_Q = 2 * math.pi / 2 ** int(P_NOM["joint_bits"])
RES_S = float(P_NOM["base_res"])
NOMINAL_SEED = TEST["draws"]["monte_carlo"]["seed0"] - 1


# ----------------------------------------------------------------------------- the controller interface
@dataclasses.dataclass
class Sensors:
    """What the firmware reads at a tick.

    t: time (s) of the sample.
    q_counts: the two joint-encoder counts (int), 2**14 per turn (res_q = 2 pi / 16384 rad), unwrapped
        (multi-turn) and zero at the upright: joint 1 measures th1, the angle of link 1 from the upward
        vertical; joint 2 measures th2 - th1, link 2 relative to link 1 (th1 = c1 res_q, th2 = (c1 + c2) res_q;
        hanging is th = -pi, positive counter-clockwise, the design state convention).
    x_count: the motor-encoder count (int, x4 quadrature through gearbox and pulley): x = x_count res_s (m),
        zero at the rail centre.
    u_prev: the controller's own previous command (V, 0 before its first tick).
    res_q, res_s: the resolutions (rad, m)."""

    t: float
    q_counts: np.ndarray
    x_count: int
    u_prev: float
    res_q: float = RES_Q
    res_s: float = RES_S

    def positions(self) -> np.ndarray:
        """[x, th1, th2] in m and rad (absolute link angles from the upward vertical)."""
        c = np.asarray(self.q_counts, float)
        return np.array([self.x_count * self.res_s, c[0] * self.res_q, (c[0] + c[1]) * self.res_q])


class FirmwareController:
    """The nominal firmware replica (`lablib.firmware`: the design.json swing-up tables, TVLQR, time-based catch
    at 4.0 s, discrete LQR, Coulomb compensation of the cart) on the harness sensors. The estimator ("diff",
    filtered differences with tau_f 2 ms, or "ekf" on the nominal twin) and its model knowledge are those of
    `lablib.setup` for the nominal parameter set; the loop delay is applied by the harness, the EKF assumes the
    nominal 2 samples. `k_lqr` / `tab`: replace the balance gain (a 1x6 state feedback) or the whole tables.
    `balance`: a callable state -> V replacing the balance law (dynamic balance controllers: see C1)."""

    rate_hz = 1000.0

    def __init__(self, p_nominal: dict, estimator: str = "ekf", comp: float = 1.0, tab=None, k_lqr=None,
                 balance=None, fw: dict | None = None):
        import design as dsg
        self.tab = tab if tab is not None else dsg.load_tables()
        rs = lb.setup(p_nominal, lb.EFFECTS, estimator, comp=comp)
        kw = {k: v for k, v in rs.fw_kw.items() if k not in ("noise_q", "noise_s", "delay", "seed")}
        kw |= {"quant": True, "res_q": RES_Q, "res_s": RES_S, "delay": 0}
        if estimator == "ekf":
            kw["ekf_delay"] = int(p_nominal["delay"])
        self.kw = kw | (fw or {})
        self.k_lqr = None if k_lqr is None else np.asarray(k_lqr, float).ravel()
        self.balance = balance
        self.phase = 0

    def reset(self, *, seed: int, start: str):
        kw = dict(self.kw)
        if self.k_lqr is not None:
            kw["k_lqr"] = self.k_lqr
        self.fw = lb.firmware(self.tab, balance_only=(start == "upright"), **kw)
        self.st = {"phase": 0}
        if self.balance is not None and hasattr(self.balance, "reset"):
            self.balance.reset()
        self.phase = 0

    def step(self, s: Sensors) -> float:
        pos = s.positions()
        z = np.concatenate([pos, np.zeros(3)])
        u = ql.tick(self.fw, s.t, z, self.st)
        self.phase = int(self.st["phase"])
        if self.balance is not None and self.phase == 2:
            # the same estimate as the firmware's (tick has just updated it), the external balance law
            xh = self.st["xh"] if self.fw.estimator == "ekf" else np.concatenate([self.st["prev"], self.st["wf"]])
            u = float(self.balance(xh))
            if self.fw.fc_base:
                u += self.fw.fc_base * math.tanh(xh[3] / self.fw.fc_eps)
            u = min(max(u, -self.fw.u_max), self.fw.u_max)
            self.st["line"][0] = u      # the EKF's input history (delay line of the replica)
        return u


def nominal_diff(p_nominal: dict, **kw):
    return FirmwareController(p_nominal, "diff", **kw)


def nominal_ekf(p_nominal: dict, **kw):
    return FirmwareController(p_nominal, "ekf", **kw)


class MLPPolicy:
    """A numpy MLP policy with the observation of the RL env (`rl/rlpend/env.py` policy_obs, the bgsim block of
    `rl/make_policy_block.py`) at `rate_hz` (200 Hz):

        o = [sin th1, cos th1, sin th2, cos th2, x, (x - xp)/Ts, (th1 - th1p)/Ts, (th2 - th2p)/Ts, ap]
        z = (o - mu) / (sd + 1e-2);  h = tanh(W_k h + b_k) ...;  a = clamp(W_out h + b_out, -1, 1);  u = v_max a

    Weights from an .npz with `mu`, `sd`, `W0`, `b0`, `W1`, `b1`, ... (the last layer linear). Before `t_on`
    the output is 0 and only the previous samples are tracked. `catch`: an optional (K, P, catch_tol) of a
    latched LQR takeover (the hybrid: z' P z < catch_tol on the differenced state -> u = -K z, clamped)."""

    def __init__(self, p_nominal: dict, weights: str, rate_hz: float = 200.0, v_max: float = 24.0, t_on: float = 0.0,
                 catch: str | None = None):
        d = np.load(weights)
        self.mu, self.sd = d["mu"].ravel(), d["sd"].ravel()
        self.layers = []
        k = 0
        while f"W{k}" in d:
            self.layers.append((d[f"W{k}"], d[f"b{k}"].ravel()))
            k += 1
        self.rate_hz, self.v_max, self.t_on = float(rate_hz), float(v_max), float(t_on)
        self.catch = None
        if catch:
            c = json.loads(Path(catch).read_text(encoding="utf-8"))
            self.catch = (np.array(c["K"], float).ravel(), np.array(c["P"], float), float(c["catch_tol"]))
        self.phase = 0

    def reset(self, *, seed: int, start: str):
        self.prev = None
        self.a_prev = 0.0
        self.latched = False
        self.phase = 0

    def step(self, s: Sensors) -> float:
        x, th1, th2 = s.positions()
        ts = 1.0 / self.rate_hz
        prev = self.prev if self.prev is not None else (x, th1, th2)
        rates = [(x - prev[0]) / ts, (th1 - prev[1]) / ts, (th2 - prev[2]) / ts]
        self.prev = (x, th1, th2)
        if s.t < self.t_on - 1e-9:
            self.a_prev = 0.0
            return 0.0
        if self.catch is not None:
            K, P, tol = self.catch
            w1, w2 = (math.remainder(th1, 2 * math.pi), math.remainder(th2, 2 * math.pi))
            z = np.array([x, w1, w2, *rates])
            if self.latched or float(z @ P @ z) < tol:
                self.latched = True
                self.phase = 2
                a = min(max(-float(K @ z) / self.v_max, -1.0), 1.0)
                self.a_prev = a
                return self.v_max * a
        o = np.array([math.sin(th1), math.cos(th1), math.sin(th2), math.cos(th2), x, *rates, self.a_prev])
        h = (o - self.mu) / (self.sd + 1e-2)
        for j, (W, b) in enumerate(self.layers):
            h = W @ h + b
            if j < len(self.layers) - 1:
                h = np.tanh(h)
        a = min(max(float(h[0]), -1.0), 1.0)
        self.a_prev = a
        self.phase = 1
        return self.v_max * a


def mlp_policy(p_nominal: dict, **kw):
    for k in ("rate_hz", "v_max", "t_on"):
        if k in kw:
            kw[k] = float(kw[k])
    return MLPPolicy(p_nominal, **kw)


def load_factory(spec: str):
    mod, _, fn = spec.rpartition(":")
    if not mod or not fn:
        raise SystemExit(f"--controller wants MODULE:FACTORY, got {spec!r}")
    if mod.endswith(".py"):
        path = Path(mod)
        if not path.is_absolute():
            path = (ROOT / path) if (ROOT / path).exists() else path.resolve()
        name = "ctrl_" + path.stem
        if name not in sys.modules:
            sp = importlib.util.spec_from_file_location(name, path)
            m = importlib.util.module_from_spec(sp)
            sys.modules[name] = m
            sys.path.insert(0, str(path.parent))
            sp.loader.exec_module(m)
        return getattr(sys.modules[name], fn)
    return getattr(importlib.import_module(mod), fn)


# ----------------------------------------------------------------------------- draws and scenarios
def draws() -> list[tuple[str, dict, int]]:
    """[(label, parameter set, seed)]: the nominal draw, then the Monte Carlo draws."""
    mc = TEST["draws"]["monte_carlo"]
    rng = np.random.default_rng(mc["seed0"])
    out = [("nominal", lb.nominal(), NOMINAL_SEED)] if TEST["draws"].get("nominal") else []
    for i in range(mc["n"]):
        out.append((f"mc{i:02d}", lb.sample(rng), mc["seed0"] + i))
    return out


def start_state(rs, sc: dict, seed: int) -> np.ndarray:
    st = sc["start"]
    if st.get("hanging"):
        z = ql.rest_state(rs.plant).copy()
        rng = np.random.default_rng([seed, 1])
        z[1:3] += math.radians(st.get("noise_deg", 0.0)) * rng.standard_normal(2)
        z[4:6] += st.get("noise_rate", 0.0) * rng.standard_normal(2)
        return z
    z = np.zeros(6)
    z[1:3] = np.radians(st["lean_deg"])
    return z


def run_one(ctrl, p: dict, seed: int, scenario: str, raw: Path | None = None) -> dict:
    """One closed loop of `ctrl` on the truth twin of `p` for the scenario; the per-run report."""
    sc = TEST["scenarios"][scenario]
    rs = lb.setup(p, lb.EFFECTS, "diff", seed=seed, sub=SUB)
    q = rs.p
    kw = rs.fw_kw
    delay, res_q, res_s = int(kw["delay"]), kw["res_q"], kw["res_s"]
    noise_q, noise_s = kw["noise_q"], kw["noise_s"]
    u_max = float(q["u_max"])
    every = int(round(1000.0 / float(ctrl.rate_hz)))
    if abs(every * float(ctrl.rate_hz) - 1000.0) > 1e-6 or every < 1:
        raise ValueError(f"rate_hz {ctrl.rate_hz} does not divide 1 kHz")
    push = sc.get("push")
    t_end = float(sc["t_end"])
    n = int(round(t_end / TS))
    start = "hanging" if sc["start"].get("hanging") else "upright"
    ctrl.reset(seed=seed, start=start)
    rng = np.random.default_rng([seed, 2])
    x = start_state(rs, sc, seed)
    xs = np.full((n + 1, 6), np.nan)
    us = np.zeros(n + 1)
    ph = np.zeros(n + 1, np.int8)
    xs[0] = x
    line = [0.0] * (delay + 1)
    u_cmd = 0.0
    u_prev = 0.0
    tau = rs.tau_act
    uf = 0.0
    if tau > 0:
        ea = math.exp(-TS / tau)
        wa = 1.0 - tau / TS * (1.0 - ea)
    t_wall = time.time()
    k_end = n
    for i in range(n):
        t = i * TS
        rel = np.array([x[1], x[2] - x[1]]) + noise_q * rng.standard_normal(2)
        xm = x[0] + noise_s * rng.standard_normal()
        if i % every == 0:
            s = Sensors(t=t, q_counts=np.round(rel / res_q).astype(np.int64), x_count=int(round(xm / res_s)),
                        u_prev=u_prev)
            u_cmd = float(ctrl.step(s))
            if not math.isfinite(u_cmd):
                u_cmd = 0.0
            u_cmd = min(max(u_cmd, -u_max), u_max)
            u_prev = u_cmd
        line.insert(0, u_cmd)
        line.pop()
        u = line[delay]
        if tau > 0:
            u, uf = uf + (u - uf) * wa, u + (uf - u) * ea
        us[i] = u
        ph[i] = int(getattr(ctrl, "phase", 0))
        f = push["amp_N"] if push and push["t"] <= t + 0.5 * TS < push["t"] + push["dur_s"] else 0.0
        x = np.array(rs.step(x, u, f)).ravel()
        if not np.all(np.isfinite(x)) or np.max(np.abs(x[3:])) > 1e3 or abs(x[0]) > 5.0:
            k_end = i
            break
        xs[i + 1] = x
    if k_end == n:
        us[n], ph[n] = us[n - 1], ph[n - 1]
    out = score(q, xs[: k_end + 1], us[: k_end + 1], ph[: k_end + 1], k_end == n and np.all(np.isfinite(xs)), t_end)
    out |= {"scenario": scenario, "seed": seed, "seconds": round(time.time() - t_wall, 1),
            "delay": delay, "joint_noise_deg": round(float(q["joint_noise"]), 4)}
    if raw is not None:
        raw.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(raw, t=np.arange(0, k_end + 1, 10) * TS, x=xs[: k_end + 1: 10], u=us[: k_end + 1: 10],
                            phase=ph[: k_end + 1: 10])
    return out


def score(p: dict, xs, us, ph, finished: bool, t_end: float) -> dict:
    ps = TEST["pass"]
    t = np.arange(len(xs)) * TS
    ang = np.degrees(np.abs(np.remainder(xs[:, 1:3] + math.pi, 2 * math.pi) - math.pi))
    dev = np.max(ang, axis=1)
    tail = t >= t_end - ps["tail_s"]
    cur = lb.current(p, us, xs[:, 3])
    peak_x = float(np.max(np.abs(xs[:, 0])))
    inside = finished and peak_x < ps["rail_m"]
    tail_dev = float(np.max(dev[tail])) if finished else math.inf
    out = {
        "finished": bool(finished), "ok": bool(inside and tail_dev < ps["upright_deg"]),
        "ok_5p7": bool(inside and tail_dev < 5.7),
        "catch_t": None, "peak_V": round(float(np.max(np.abs(us))), 3), "peak_i": round(float(np.max(np.abs(cur))), 3),
        "peak_x": round(peak_x, 4), "tail_V_rms": round(float(np.sqrt(np.mean(us[tail] ** 2))), 3) if finished else None,
        "tail_dev_deg": round(tail_dev, 4) if finished else None,
        "tail_x": round(float(np.max(np.abs(xs[tail, 0]))), 4) if finished else None,
    }
    if finished:
        bad = np.where(dev >= ps["upright_deg"])[0]
        if not len(bad):
            out["catch_t"] = 0.0
        elif bad[-1] + 1 < len(t):
            out["catch_t"] = round(float(t[bad[-1] + 1]), 3)
    if np.any(ph >= 2):
        out["t_phase2"] = round(float(t[np.argmax(ph >= 2)]), 3)
    return out


# ----------------------------------------------------------------------------- the runner
_CTRL: dict = {}


def run_job(job: dict) -> list[dict]:
    key = (job["spec"], json.dumps(job["opts"], sort_keys=True))
    if key not in _CTRL:
        _CTRL.clear()
        _CTRL[key] = load_factory(job["spec"])(lb.nominal(), **job["opts"])
    ctrl = _CTRL[key]
    out = []
    for sc in job["scenarios"]:
        raw = RAW / job["name"] / f"{sc}_{job['draw']}.npz" if job.get("raw", True) else None
        try:
            r = run_one(ctrl, job["p"], job["seed"], sc, raw)
        except Exception as e:  # a controller error is a failed run, reported
            r = {"scenario": sc, "seed": job["seed"], "finished": False, "ok": False, "ok_5p7": False,
                 "error": f"{type(e).__name__}: {e}"}
        r["draw"] = job["draw"]
        out.append(r)
    return out


def parse_draws(text: str | None, all_draws):
    if not text:
        return all_draws
    pick = set()
    for part in text.split(","):
        part = part.strip()
        if part == "nominal":
            pick.add("nominal")
        elif "-" in part:
            a, b = part.split("-")
            pick |= {f"mc{i:02d}" for i in range(int(a), int(b) + 1)}
        elif part:
            pick.add(f"mc{int(part):02d}")
    return [d for d in all_draws if d[0] in pick]


def run_controller(spec: str, name: str, opts: dict | None = None, scenarios=None, n_jobs: int = 8,
                   draw_sel: str | None = None, save: bool = True, verbose: bool = True) -> dict:
    """Run a controller on the test; returns (and with `save` merges into robustness_results.json) its entry."""
    scenarios = list(scenarios or SCORED)
    for s in scenarios:
        if s not in TEST["scenarios"]:
            raise SystemExit(f"unknown scenario {s!r}; the test has {list(TEST['scenarios'])}")
    sel = parse_draws(draw_sel, draws())
    jobs = [{"spec": spec, "opts": opts or {}, "name": name, "scenarios": scenarios, "draw": lab, "p": p, "seed": seed}
            for lab, p, seed in sel]
    t0 = time.time()
    n_jobs = max(1, min(n_jobs, 8, len(jobs)))
    if n_jobs <= 1:
        res = [run_job(j) for j in jobs]
    else:
        with mp.get_context("spawn").Pool(n_jobs) as pool:
            res = pool.map(run_job, jobs, chunksize=1)
    runs = [r for rr in res for r in rr]
    entry = {"controller": spec, "opts": opts or {}, "date": datetime.date.today().isoformat(),
             "wall_s": round(time.time() - t0, 1), "draws": [d[0] for d in sel], "summary": {}, "runs": {}}
    for sc in scenarios:
        rr = [r for r in runs if r["scenario"] == sc]
        entry["runs"][sc] = rr
        entry["summary"][sc] = summarise(rr, sc)
    if verbose:
        print_entry(name, entry)
    if save:
        doc = load_results()
        old = doc["controllers"].get(name)
        if old and old.get("controller") == spec and old.get("opts") == entry["opts"]:
            # keep the scenarios not rerun
            for sc, rr in old.get("runs", {}).items():
                if sc not in entry["runs"]:
                    entry["runs"][sc] = rr
                    entry["summary"][sc] = old["summary"][sc]
        doc["controllers"][name] = entry
        write_results(doc)
    return entry


def summarise(rr: list[dict], scenario: str) -> dict:
    mc = [r for r in rr if r["draw"] != "nominal"]
    nom = next((r for r in rr if r["draw"] == "nominal"), None)
    good = [r for r in mc if r["ok"]]

    def stat(key, fn, rows):
        v = [r[key] for r in rows if r.get(key) is not None]
        return round(float(fn(v)), 3) if v else None

    d = {"scored": bool(TEST["scenarios"][scenario].get("scored")),
         "nominal": None if nom is None else {k: nom.get(k) for k in ("ok", "ok_5p7", "catch_t", "peak_V", "peak_i", "peak_x",
                                                                        "tail_V_rms", "tail_dev_deg")},
         "mc_n": len(mc), "success": f"{len(good)}/{len(mc)}",
         "success_rate": round(len(good) / len(mc), 4) if mc else None,
         "success_5p7": f"{sum(r['ok_5p7'] for r in mc)}/{len(mc)}",
         "success_rate_5p7": round(sum(r["ok_5p7"] for r in mc) / len(mc), 4) if mc else None,
         "over_successes": {
             "catch_t_median": stat("catch_t", np.median, good), "catch_t_max": stat("catch_t", np.max, good),
             "peak_V_median": stat("peak_V", np.median, good), "peak_V_max": stat("peak_V", np.max, good),
             "peak_i_max": stat("peak_i", np.max, good), "peak_x_max": stat("peak_x", np.max, good),
             "tail_V_rms_median": stat("tail_V_rms", np.median, good), "tail_V_rms_max": stat("tail_V_rms", np.max, good),
             "tail_dev_deg_median": stat("tail_dev_deg", np.median, good), "tail_dev_deg_max": stat("tail_dev_deg", np.max, good)},
         "failures": [{"draw": r["draw"], "why": why(r)} for r in mc if not r["ok"]]}
    return d


def why(r: dict) -> str:
    if r.get("error"):
        return r["error"]
    if not r["finished"]:
        return f"diverged (peak x {r.get('peak_x', float('nan')):.2f} m)"
    if r["peak_x"] >= TEST["pass"]["rail_m"]:
        return f"rail: peak |x| {r['peak_x']:.3f} m"
    return f"tail deviation {r['tail_dev_deg']:.2f} deg"


def load_results() -> dict:
    if RESULTS.is_file():
        return json.loads(RESULTS.read_text(encoding="utf-8"))
    return {"format": "bgsim.robustness-results", "version": 1,
            "description": ("Results of the shared robustness test design/robustness_test.json (harness design/robustness.py): "
                            "one entry per controller, keyed by its name, with the per-draw runs per scenario and the summary. "
                            "success = the pass rule over the 64 Monte Carlo draws (the nominal draw is reported separately); "
                            "over_successes: statistics over the passing Monte Carlo runs. Units: s, V, A, m, deg."),
            "controllers": {}}


def write_results(doc: dict):
    RESULTS.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {RESULTS}")


def print_entry(name: str, e: dict):
    print(f"\n== {name}  ({e['controller']} {e['opts'] or ''}, {e['wall_s']} s)")
    for sc, s in e["summary"].items():
        nom = s["nominal"] or {}
        o = s["over_successes"]
        print(f"  {sc:18s} MC {s['success']:>6s} (5.7 deg {s['success_5p7']:>6s}) | nominal "
              f"{'ok' if nom.get('ok') else 'FAIL'} catch {nom.get('catch_t')} V {nom.get('peak_V')} x {nom.get('peak_x')} | "
              f"MC ok: catch med {o['catch_t_median']} max {o['catch_t_max']}, V max {o['peak_V_max']}, i max {o['peak_i_max']}, "
              f"x max {o['peak_x_max']}, tail V rms med {o['tail_V_rms_median']}")
        if s["failures"]:
            print("    failures:", ", ".join(f"{f['draw']} ({f['why']})" for f in s["failures"][:12]),
                  "..." if len(s["failures"]) > 12 else "")


def main(argv):
    def opt(flag, default=None):
        return argv[argv.index(flag) + 1] if flag in argv else default

    cmd = argv[0] if argv else ""
    n_jobs = int(opt("--jobs", 8))
    scen = opt("--scenarios")
    scen = scen.split(",") if scen else None
    if cmd == "nominal":
        for name, fac in (("nominal-diff", "robustness:nominal_diff"), ("nominal-ekf", "robustness:nominal_ekf")):
            run_controller(fac, name, scenarios=scen or list(TEST["scenarios"]), n_jobs=n_jobs, draw_sel=opt("--draws"))
    elif cmd == "run":
        spec, name = opt("--controller"), opt("--name")
        if not spec or not name:
            raise SystemExit(__doc__)
        opts = {}
        for i, a in enumerate(argv):
            if a == "--opt":
                k, _, v = argv[i + 1].partition("=")
                opts[k] = v
        if "--dry" in argv:
            run_controller(spec, name, opts, scen, 1, "nominal", save=False)
        else:
            run_controller(spec, name, opts, scen, n_jobs, opt("--draws"))
    elif cmd == "show":
        doc = load_results()
        for name, e in doc["controllers"].items():
            if opt("--name") in (None, name):
                print_entry(name, e)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
