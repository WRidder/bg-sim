# /// script
# requires-python = ">=3.11"
# dependencies = ["casadi>=3.6", "numpy>=2.0", "scipy>=1.13"]
# ///
"""Design of the `pendulum-double-cart-lab` example: the double-cart lab rig, swing-up, TVLQR, LQR, margins.

The rig of `pendulum-double-cart` (motor, gearbox, pulley, belt and cart carriage) with two 0.35 m links built
as a lab would build them (aluminium tubes with clamp hubs, a bearing head, encoders and a cable: 0.248 and
0.200 kg) on a +-1.0 m rail with soft end stops. Every value comes from `design/realism.json` (the nominal
column; `lablib.design_plant`). The scenario of the swing-up model is

    0 .. 1 s        hanging down at rest, motor voltage 0
    1 s             swing-up: feed-forward from an offline direct-collocation optimisation (Hermite-Simpson,
                    IPOPT, |x| <= 0.8 m, |V| <= 16.8 V = 70 % of the supply) tracked by a time-varying LQR,
                    T_s = 3.0 s
    4.0 s           catch: switch to the 1 kHz infinite-horizon (discrete) LQR balance controller
    7.5 s           a 40 ms force pulse on the tip link (3.5 s of balance before it)
    ..              recovery; the run ends 12.5 s

and of the balance model: balance from a 2 deg lean of both links, a larger 40 ms push at 2 s, end 6 s.

The mathematics (design model, collocation, TVLQR, LQR, table writer) and the model generator are those of
`examples/pendulum-double-cart/design/` (`cartpend.py`, `cartmodel.py`). The firmware replica, the robustness
cases and the largest push run on the twin of `lablib.py` (the quadlib twin with the voltage-driven motor).

    uv run examples/pendulum-double-cart-lab/design/design.py [--write] [--robust] [--compare-free <run dir>]

Without options it prints the design closed loop. `--robust` adds the robustness table (masses, lengths,
friction, cart mass, delay, quantised encoders), the largest recovered push and the belt-mode check, and
stores them in `design/design.json`. `--write` writes `library/DoubleCartLab{Traj,Ctrl}.jl`, the three models
and `design/design.json` (tables, gains, design closed loops, free-swing reference, metrics).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lablib as lb  # noqa: E402

cp, ql = lb.cp, lb.ql
ROOT = HERE.parent
DESIGN_JSON = HERE / "design.json"

# ----------------------------------------------------------------------------- the rig and the scenario
P_NOM = lb.nominal()
PLANT = lb.design_plant(P_NOM)

DOC = """
Firmware of the double-cart lab rig, 1 kHz. Three phases, latched in `mode`:
  0  hold: the motor voltage is 0 until t_on (the pendulum hangs at rest).
  1  swing-up from t_on: u = u_ff(tau) - K(tau) (z - z*(tau)), tau = t - t_on. The feed-forward voltage u_ff,
     the nominal state z* and the time-varying LQR gain K come from the offline trajectory optimisation;
     the block `DoubleCartLabTraj` looks them up in 10 ms tables and this block samples them at every tick.
  2  balance from tau >= T_s (the nominal ends upright, at rest): u = -K_lqr z, the discrete
     infinite-horizon LQR of the 1 ms sampled linearisation at the upright. A t_on below -T_s starts in
     balance (the balance model).
z = [x, th_1, th_2, v, w_1, w_2] with the absolute link angles th_i from the upward vertical and their
rates w_i (sums of the joint encoder angles and rates). The output is clamped to +-u_max.
design/design.py writes the gains: do not edit them by hand.
"""

T_S = 3.0
U_PLAN = 0.7 * P_NOM["u_max"]          # 16.8 V
X_PLAN = 0.8
PUSH_SWING = 0.45                      # N, 40 ms, in the swing-up model (half the largest recovered push)
SCENARIO = cp.Scenario(
    prefix="DoubleCartLab", model="pendulum-double-cart-lab", root=ROOT, plant=PLANT,
    t_on=1.0, t_s=T_S, k_int=75, u_lim=U_PLAN, x_lim=X_PLAN, dt_tab=0.01,
    t_dist=7.5, dist_dur=0.04, dist_amp=PUSH_SWING, t_end=12.5,
    Q=np.diag([300.0, 400.0, 400.0, 10.0, 8.0, 8.0]), R=0.3,      # [x, th1, th2, v, w1, w2], 1/V^2
    free_th0=[-2.2, -1.2], free_x0=0.05, free_t=2.0,
    doc=DOC, scene="scenes/pendulum-double-cart-lab.sdf",
)
BALANCE = {"th0_deg": [2.0, 2.0], "t_push": 2.0, "amp": 0.70, "dur": 0.04, "t_end": 6.0}   # 0.70 N: 78 % of the largest push

DESCRIPTION = (
    "The double-cart lab rig: the motor, gearbox, pulley, belt and cart of pendulum-double-cart with two 0.35 m links "
    "built from aluminium tubes with clamp hubs, a bearing head, encoders and a cable (0.248 / 0.200 kg, centres of mass "
    "0.229 / 0.176 m) on a +-1.0 m rail with soft end stops; all values from design/realism.json. 1 kHz firmware "
    "(library/DoubleCartLabCtrl.jl with the tables of library/DoubleCartLabTraj.jl, written by design/design.py): 0 V until "
    "1 s, a direct-collocation swing-up (T_s = 3.0 s, planned inside |x| <= 0.8 m and |V| <= 16.8 V = 70 % of 24 V) "
    "tracked by a time-varying LQR, the discrete LQR from 4.0 s and a 40 ms tip push at 7.5 s; the balance model "
    "starts leaning 2 deg and takes a larger push at 2 s; the -free model releases the plant from rest with the "
    "motor shorted and is compared with the design ODE. The reference numbers are design.py's closed loop of "
    "the design model under the same sampled firmware."
)


# ----------------------------------------------------------------------------- design and replica runs
def design(verbose=True):
    return cp.design(SCENARIO, verbose=verbose)


def tables_from(dz: dict) -> cp.Tables:
    return cp.Tables(t_on=dz["t_on"], T_s=dz["t_s"], tk=np.array(dz["tk"]), uff=np.array(dz["uff"]),
                     xs=np.array(dz["xs"]), Ks=np.array(dz["Ks"]), Klqr=np.array(dz["Klqr"]), u_max=dz["u_max"])


def load_tables() -> cp.Tables:
    return tables_from(json.loads(DESIGN_JSON.read_text(encoding="utf-8")))


def balance_x0(th0_deg) -> np.ndarray:
    z = np.zeros(6)
    z[1:3] = np.radians(th0_deg)
    return z


def push_force(t0, dur, amp):
    return lambda t: amp if t0 <= t < t0 + dur else 0.0


def run(tab: cp.Tables, scenario: str = "swingup", p: dict | None = None, setup=None, fw_kw: dict | None = None,
        amp: float | None = None, t_end: float | None = None, x0=None, sub: int = 4):
    """One closed loop of the firmware replica on the twin. `setup`: a lablib.setup result (realistic truth and
    firmware options); else the twin of `p` (default: the nominal design model) with ideal sensors and `fw_kw`."""
    if setup is None:
        step = lb.twin(p or lb.effects_only(P_NOM, ()), sub)[1]
        kw, tau_act = dict(fw_kw or {}), 0.0
    else:
        step, kw, tau_act = setup.step, setup.fw_kw | (fw_kw or {}), setup.tau_act
    if scenario == "swingup":
        fw = lb.firmware(tab, **kw)
        z0 = x0 if x0 is not None else (ql.rest_state(setup.plant) if setup is not None else PLANT_hang())
        a = SCENARIO.dist_amp if amp is None else amp
        force = push_force(SCENARIO.t_dist, SCENARIO.dist_dur, a)
        T = SCENARIO.t_end if t_end is None else t_end
    else:
        fw = lb.firmware(tab, balance_only=True, **kw)
        z0 = balance_x0(BALANCE["th0_deg"]) if x0 is None else x0
        a = BALANCE["amp"] if amp is None else amp
        force = push_force(BALANCE["t_push"], BALANCE["dur"], a)
        T = BALANCE["t_end"] if t_end is None else t_end
    ts, xs, us, ph, st = ql.closed_loop(step, fw, z0, T, force=force, tau_act=tau_act)
    return ts, xs, us, ph


def PLANT_hang():
    return cp.hang_state(PLANT)


def metrics(ts, xs, us, ph, scenario: str = "swingup", p: dict | None = None) -> dict:
    """Numbers of one replica run: ok (finished, inside the rail, every link within 1 deg over the last second),
    catch, peaks of voltage, current and travel, push deflection and recovery."""
    p = p or P_NOM
    fin = np.all(np.isfinite(xs), axis=1)
    k = int(np.max(np.where(fin)[0]))
    t, x, u = ts[: k + 1], xs[: k + 1], us[: k + 1]
    dev = np.degrees(np.max(np.abs(x[:, 1:3]), axis=1))
    t_p = SCENARIO.t_dist if scenario == "swingup" else BALANCE["t_push"]
    tail = t >= ts[-1] - 1.0
    cur = lb.current(p, u, x[:, 3])
    out = {
        "finished": bool(fin.all()),
        "peak_u": float(np.max(np.abs(u))), "peak_i": float(np.max(np.abs(cur))),
        "peak_x": float(np.max(np.abs(x[:, 0]))),
        "tail_dev_deg": float(np.max(dev[tail])) if fin.all() else math.inf,
        "tail_x": float(np.max(np.abs(x[tail, 0]))) if fin.all() else math.inf,
        "push_dev_deg": float(np.max(dev[t >= t_p])) if np.any(t >= t_p) else math.nan,
        "push_x": float(np.max(np.abs(x[t >= t_p, 0]))) if np.any(t >= t_p) else math.nan,
    }
    bad = np.where((t > t_p + 0.05) & (dev > 0.5))[0]
    out["t_rec"] = float(t[bad[-1] + 1] - t_p) if len(bad) and bad[-1] + 1 < len(t) else (0.0 if not len(bad) else math.inf)
    if scenario == "swingup":
        out["t_catch"] = float(t[np.argmax(ph[: k + 1] > 1.5)]) if np.any(ph[: k + 1] > 1.5) else math.nan
        pre = t < t_p
        out["peak_u_swing"] = float(np.max(np.abs(u[pre])))
        out["peak_i_swing"] = float(np.max(np.abs(cur[pre])))
        out["peak_x_swing"] = float(np.max(np.abs(x[pre, 0])))
        bad = np.where(pre & (t > SCENARIO.t_on) & (dev > 2.0))[0]
        out["t_up"] = float(t[bad[-1] + 1] - SCENARIO.t_on) if len(bad) else math.nan
        sel = (t > out["t_catch"] + 0.1) & pre
        out["band_deg"] = float(np.max(dev[sel])) if np.any(sel) else math.nan
    out["ok"] = bool(out["finished"] and out["peak_x"] < p["x_rail"] and out["tail_dev_deg"] < 1.0)
    return out


# ----------------------------------------------------------------------------- robustness and margins
def scaled(p: dict, mass: float = 1.0, length: float = 1.0, fjoint: float = 1.0, fcart: float = 1.0,
           cart: float = 1.0) -> dict:
    """The nominal design model with every link part mass x mass, the link lengths x length, the joint viscous
    friction x fjoint, the carriage friction x fcart, the cart mass x cart."""
    q = dict(p)
    for k in ("m_tube1", "m_tube2", "m_hub1", "m_head1", "m_hub2", "m_tip2", "m_enc_board", "m_enc_magnet", "rho_cable"):
        q[k] = p[k] * mass
    q["L1"], q["L2"] = p["L1"] * length, p["L2"] * length
    q["b_joint1"], q["b_joint2"] = p["b_joint1"] * fjoint, p["b_joint2"] * fjoint
    q["b_carriage"] = p["b_carriage"] * fcart
    q["m_cart"] = p["m_cart"] * cart
    return q


QUANT = {"quant": True, "res_q": 2 * math.pi / 2**14, "res_s": P_NOM["base_res"], "tau_f": 0.002}
CASES = [
    ("nominal", {}, {}),
    ("link masses -5 %", {"mass": 0.95}, {}),
    ("link masses +5 %", {"mass": 1.05}, {}),
    ("link lengths +1 %", {"length": 1.01}, {}),
    ("link lengths -1 %", {"length": 0.99}, {}),
    ("joint friction x3", {"fjoint": 3.0}, {}),
    ("carriage friction x3", {"fcart": 3.0}, {}),
    ("cart mass +10 %", {"cart": 1.1}, {}),
    ("delay 1 ms", {}, {"delay": 1}),
    ("delay 2 ms", {}, {"delay": 2}),
    ("quantised encoders (14 bit, 8.4 um, 2 ms rate filter)", {}, QUANT),
    ("quantised encoders + 2 ms delay", {}, QUANT | {"delay": 2}),
    ("masses +5 %, lengths +1 %, friction x3, 2 ms delay, quantised", {"mass": 1.05, "length": 1.01, "fjoint": 3.0, "fcart": 3.0},
     QUANT | {"delay": 2}),
]


def robustness(tab: cp.Tables) -> list:
    base = lb.effects_only(P_NOM, ())
    rows = []
    for name, pk, fk in CASES:
        p = scaled(base, **pk)
        a = metrics(*run(tab, "swingup", p=p, fw_kw=fk), "swingup", p)
        b = metrics(*run(tab, "balance", p=p, fw_kw=fk), "balance", p)
        rows.append({"case": name, "swingup": a, "balance": b})
        print(f"  {name:62s} swing-up {'ok ' if a['ok'] else 'FAIL'} u {a['peak_u']:5.2f} V x {a['peak_x']:.3f} m "
              f"tail {a['tail_dev_deg']:.3f} deg | balance {'ok ' if b['ok'] else 'FAIL'} push {b['push_dev_deg']:.2f} deg "
              f"x {b['peak_x']:.3f} m", flush=True)
    return rows


def max_push(tab: cp.Tables, fw_kw: dict | None = None, lo: float = 0.0, hi: float = 2.0, x_lim: float | None = None) -> dict:
    """Largest 40 ms tip push (N) the balance controller recovers from upright at rest (bisection to 1 mN): the
    run stays inside the rail (or `x_lim`) and ends within 1 deg."""
    x_lim = x_lim or P_NOM["x_rail"]
    z0 = np.zeros(6)

    def good(a):
        m = metrics(*run(tab, "balance", amp=a, x0=z0, fw_kw=fw_kw, t_end=6.0), "balance")
        return m["ok"] and m["peak_x"] < x_lim, m

    while hi - lo > 1e-3:
        mid = 0.5 * (lo + hi)
        if good(mid)[0]:
            lo = mid
        else:
            hi = mid
    ok, m = good(lo)
    return {"amp": round(lo, 3), "peak_dev_deg": m["push_dev_deg"], "peak_x": m["peak_x"], "peak_u": m["peak_u"]}


def belt_check(tab: cp.Tables) -> dict:
    """Closed-loop poles with the belt compliance (discrete LQR on the 8-state linearisation with the motor and
    the cart joined by the belt), nominal and softest belt, 0 to 2 samples of delay: the largest real part of
    all poles, and the frequency and damping ratio of the belt mode (the pole pair with the largest imaginary
    part below the Nyquist frequency)."""
    out = {}
    for kb in (P_NOM["k_belt"], spec_min("k_belt")):
        for db in (P_NOM["d_belt"], spec_min("d_belt")):
            for d in (0, 1, 2):
                poles = lb.belt_poles(P_NOM | {"k_belt": kb, "d_belt": db}, tab.Klqr, d)
                osc = poles[(poles.imag > 2 * math.pi * 20) & (poles.imag < 0.99 * math.pi / lb.TS)]
                s = osc[np.argmax(osc.imag)]
                out[f"k{kb:g}_d{db:g}_delay{d}"] = {"max_real": float(np.max(poles.real)),
                                                    "belt_mode_hz": float(s.imag / (2 * math.pi)),
                                                    "belt_zeta": float(-s.real / abs(s))}
    return out


def spec_min(k):
    return lb.spec()[k]["min"]


# ----------------------------------------------------------------------------- writing
def write_models(tab: cp.Tables):
    import cartmodel
    P = PLANT
    sc = SCENARIO
    cp.write_controller(ROOT / "library", sc.prefix, P, tab, sc.doc)
    push = {"amplitude": sc.dist_amp, "t_start": sc.t_dist, "duration": sc.dist_dur}
    full = cartmodel.build(P, sc.prefix, t_end=sc.t_end, points=int(round(sc.t_end / 0.005)) + 1, push=push,
                           scene=sc.scene, title=sc.model)
    bal = cartmodel.build(P, sc.prefix, th0=list(np.radians(BALANCE["th0_deg"])), t_end=BALANCE["t_end"],
                          points=int(round(BALANCE["t_end"] / 0.002)) + 1, ctrl_params={"t_on": "-10.0"},
                          push={"amplitude": BALANCE["amp"], "t_start": BALANCE["t_push"], "duration": BALANCE["dur"]},
                          scene=sc.scene, title=sc.model + "-balance")
    free = cartmodel.build(P, sc.prefix, free=True, th0=sc.free_th0, x0=sc.free_x0, t_end=sc.free_t,
                           points=int(round(sc.free_t / 0.002)) + 1, scene=sc.scene, title=sc.model + "-free")
    cartmodel.write(ROOT / "models" / f"{sc.model}.bgmodel.json", full)
    cartmodel.write(ROOT / "models" / f"{sc.model}-balance.bgmodel.json", bal)
    cartmodel.write(ROOT / "models" / f"{sc.model}-free.bgmodel.json", free)


def design_record(dyn, traj, tab, res, resb) -> dict:
    P = PLANT
    sc = SCENARIO
    A, _ = dyn.lin(np.zeros(6))
    m, c, J = lb.link_props(P_NOM)
    tf = np.round(np.arange(0.0, sc.free_t + 1e-9, 0.25), 6)
    zf = cp.free_swing(sc, dyn, tf)
    dec = lambda r: {"t": r[::2, 0].round(6).tolist(), "u": r[::2, 1].round(5).tolist(), "z": r[::2, 3:].round(7).tolist()}  # noqa: E731
    return {
        "format": "bgsim.design", "rig": "pendulum-double-cart-lab", "model": sc.model,
        "t_on": sc.t_on, "t_s": sc.t_s, "k_int": sc.k_int, "u_lim": sc.u_lim, "x_lim": sc.x_lim, "u_max": P.u_max,
        "x_rail": P.x_rail, "Q": np.diag(sc.Q).tolist(), "R": sc.R,
        "tk": tab.tk.round(9).tolist(), "uff": tab.uff.tolist(), "xs": tab.xs.tolist(), "Ks": tab.Ks.tolist(),
        "Klqr": tab.Klqr.tolist(),
        "plant": {"L": P.L, "m": m, "c": c, "J": J, "b": P.b, "m_cart": P.m_cart, "m_eff": P.m_eff, "alpha": P.alpha,
                  "beta": P.beta, "open_loop_poles": sorted(np.linalg.eigvals(A).real.round(6).tolist()),
                  "E_swing": 2 * cp.G0 * (m[0] * c[0] + m[1] * (P.L[0] + c[1]))},
        "swingup": {"t_dist": sc.t_dist, "dist_dur": sc.dist_dur, "dist_amp": sc.dist_amp, "t_end": sc.t_end,
                    "traj_peak_u": float(np.abs(traj["U"]).max()), "traj_peak_x": float(np.abs(traj["Z"][0]).max()),
                    "closed_loop": dec(res)},
        "balance": BALANCE | {"closed_loop": dec(resb)},
        "free": {"th0": sc.free_th0, "x0": sc.free_x0, "t_end": sc.free_t, "t": tf.tolist(), "z": zf.tolist()},
    }


def design_closed_loops(dyn, tab):
    """The design closed loops of cartpend (RK4 on the design model, 0.25 ms): the swing-up scenario and the
    balance scenario (balance from the lean, the push)."""
    sc = SCENARIO
    res = cp.run_scenario(sc, dyn, tab)
    tabb = cp.Tables(t_on=-10.0, T_s=tab.T_s, tk=tab.tk, uff=tab.uff, xs=tab.xs, Ks=tab.Ks, Klqr=tab.Klqr, u_max=tab.u_max)
    resb = cp.simulate(PLANT, dyn, tabb, BALANCE["t_end"], balance_x0(BALANCE["th0_deg"]),
                       dist=lambda t: cp.disturbance(t, BALANCE["t_push"], BALANCE["dur"], BALANCE["amp"]))
    return res, resb


def main(argv):
    dyn, traj, tab = design()
    P = PLANT
    A, _ = dyn.lin(np.zeros(6))
    print(f"links m = {[round(v, 4) for v in P.m]} kg, c = {[round(v, 4) for v in P.c]} m, J = {[f'{v:.4g}' for v in P.J]} kg m^2; "
          f"m_eff = {P.m_eff:.4f} kg; open-loop poles {np.sort(np.linalg.eigvals(A).real).round(3)}")
    print(f"twin vs design model: {lb.check_twin():.1e} (relative)")
    res, resb = design_closed_loops(dyn, tab)
    cp.report(SCENARIO, res)
    t, u, z = resb[:, 0], resb[:, 1], resb[:, 3:]
    print(f"balance scenario: push {BALANCE['amp']:g} N -> {np.degrees(np.abs(z[t > BALANCE['t_push'], 1:3]).max(0)).round(2)} deg, "
          f"peak |u| {np.abs(u).max():.2f} V, |x| {np.abs(z[:, 0]).max():.3f} m")
    m = metrics(*run(tab, "swingup"), "swingup")
    mb = metrics(*run(tab, "balance"), "balance")
    print("replica swing-up:", {k: round(v, 4) if isinstance(v, float) else v for k, v in m.items()})
    print("replica balance :", {k: round(v, 4) if isinstance(v, float) else v for k, v in mb.items()})
    rec = design_record(dyn, traj, tab, res, resb)
    rec["metrics"] = {"swingup": m, "balance": mb}
    old = json.loads(DESIGN_JSON.read_text(encoding="utf-8")) if DESIGN_JSON.is_file() else {}
    for k in ("robustness", "push_max", "belt"):
        if k in old:
            rec[k] = old[k]
    if "--robust" in argv:
        print("robustness (firmware replica on the twin):")
        rec["robustness"] = robustness(tab)
        rec["push_max"] = {"ideal": max_push(tab), "delay_2ms": max_push(tab, {"delay": 2}),
                           "inside_0p8m": max_push(tab, x_lim=X_PLAN)}
        print("largest 40 ms push recovered:", rec["push_max"])
        rec["belt"] = belt_check(tab)
        print("belt check (max real part, belt mode Hz, zeta):",
              {k: (round(v["max_real"], 3), round(v["belt_mode_hz"], 1), round(v["belt_zeta"], 3)) for k, v in rec["belt"].items()})
    if "--write" in argv or "--robust" in argv:
        DESIGN_JSON.write_text(json.dumps(rec) + "\n", encoding="utf-8", newline="\n")
        print("wrote", DESIGN_JSON)
    if "--write" in argv:
        write_models(tab)
        print(f"wrote library/{SCENARIO.prefix}Traj.jl, {SCENARIO.prefix}Ctrl.jl and models/{SCENARIO.model}*.bgmodel.json")
    if "--compare-free" in argv:
        cp.compare_free(SCENARIO, dyn, argv[argv.index("--compare-free") + 1])
    return dyn, tab


if __name__ == "__main__":
    main(sys.argv[1:])
