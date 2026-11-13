# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""The landing gear of the f16-sim model: its data, and an independent pitch-plane reference.

    uv run examples/f16/design/gear.py          # writes design/gear.json

`build_model.py` reads `gear.json` for the gear parameters, the runway start, the scenarios and
the reference values of `expected.json`. Nothing here touches `design.json`.

Data (see README, "Landing gear", for every source):

* contact points, spring and damping rates, friction coefficients, retraction time and the gear's
  drag coefficient: JSBSim `aircraft/f16/f16.xml` (Erik Hofman, F-16A Block 32; public-domain
  facts of an aircraft, the file itself is GPL: the numbers are transcribed with attribution);
* mass, inertia, tables, engine: the Stevens & Lewis model of this example.

The model's CG is a fraction `xcg` of the mean chord; JSBSim's AERORP (station 189.5 in) is the
aerodynamic reference, the book's xcgr = 0.35. So at xcg = 0.35 the CG is at station 189.5 and
every contact point is measured from there; moving the CG aft by d moves the gear forward by d
relative to the CG (`rx` below; the model has the same expression over the global `xcg`).

Reference: a rigid aircraft in the vertical plane (x, h, theta, the velocities), the book's
coefficients (`f16_ref`), the book's engine lag, the stabilator servo, the pitch law with the
weight-on-wheels hand-over (`PitchFBW`), and per axle the strut and tyre laws written from
geometry (the penetration of the contact point, not a state as in the bond graph). It shares
the coefficient tables with the bg-sim model and nothing of its structure, so a sign or a lever
arm wrong in the diagram shows up as a difference.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import fsolve

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import f16_ref as F  # noqa: E402
import f16_si as SI  # noqa: E402
import fbw  # noqa: E402
import sim3  # noqa: E402

IN = 0.0254
LBF_FT = SI.LBF / SI.FT                 # lbf/ft -> N/m (and lbf/(ft/s) -> N s/m)
RTOD = 180.0 / math.pi
XCG = 0.35

# JSBSim's damping is a linear coefficient: at 2 m/s of sink its force alone is 2.4 weights on each main wheel
# (a real oleo meters its oil and a tyre sits in series). Half of it gives a damping ratio of about 0.5 on the
# heave mode and a sensible touchdown (README, "Landing gear").
B_SCALE = 0.5
# JSBSim f16.xml, stations in inches (x grows aft, z up)
AERORP_X = -189.5
CG_Z = -5.1
LEGS = {
    "nose": {"x": -299.6, "y": 0.0, "z": -72.0, "k": 17250.0, "b": 4250.0 * B_SCALE},
    "left": {"x": -158.6, "y": 48.0, "z": -71.6, "k": 37500.0, "b": 7500.0 * B_SCALE},
    "right": {"x": -158.6, "y": -48.0, "z": -71.6, "k": 37500.0, "b": 7500.0 * B_SCALE},
}
MU_R = 0.02          # rolling_friction
MU_S = 0.8           # static_friction: the tyre's side-force peak
MU_BRAKE = 0.5       # dynamic_friction, as the braked coefficient: an anti-skid stop stays near it (see README)
T_GEAR = 5.0         # s, gear/gear-pos-norm travels 0 .. 1 in 5 s (kinematic fcs/gear-control)
CD_GEAR = 0.0270     # aero/coefficient/CDgear: CD = 0.0270 gear-pos-norm
# Nose-wheel steering: JSBSim's schedule fcs/scheduled-steer-pos-deg over ground speed (10, 50,
# 150 ft/s -> 80, 15, 2 deg), with the 80 deg capped at the 32 deg the real leg has.
# The narrow track and a high CG tip the aircraft over at about 0.75 g of lateral acceleration (track/2 over
# CG height), and a tyre at mu 0.8 can reach that, so the steering angle falls with speed to keep full pedal
# near 0.35 g: a model choice. The 32 deg at taxi speed is an assumption.
STEER_V = [10.0 * SI.FT, 20.0 * SI.FT, 30.0 * SI.FT, 50.0 * SI.FT, 150.0 * SI.FT]
STEER_DEG = [32.0, 16.0, 7.0, 3.0, 0.5]
# Ours (no source: choices of the model)
L_RETRACT = 3.0      # m, how far the contact point moves up: more than the CG height, so a retracted gear
                     # never reaches the ground before the airframe does (ground_contact stays the crash)
Z_DRAG = 1.2         # m, the gear's drag acts this far below the CG (the middle of the legs)
F0_WOW, F1_WOW = 500.0, 0.1 * SI.MASS * SI.G0  # N on the main wheels: the laws hand over between these
T_TRACK = 0.1        # s, the law's integrators follow the ground command this fast
STROKE_MAX = 0.40    # m, compression at which a leg bottoms and the airframe is on the ground
V_FLOOR = 1.0        # m/s, the airspeed floor of the air data (`F16AirData`), as the Cessna's V_FLOOR
GEAR_EPS, GEAR_FEPS, V_ROLL, V_SIDE = 1.0e-3, 1.0, 0.2, 2.0   # as the Cessna's smoothing
V_APPROACH, GAMMA_APPROACH = 76.0, -1.9   # m/s (148 kt), deg: the checked approach
SINK_LIMIT = 10.0 * SI.FT   # m/s, the design limit sink rate usually quoted for a land-based fighter


def geometry(xcg: float = XCG) -> dict:
    out = {}
    for nm, l in LEGS.items():
        out[nm] = {"rx": (AERORP_X - l["x"]) * IN + (xcg - 0.35) * SI.CBAR,
                   "ry": l["y"] * IN, "rz": (l["z"] - CG_Z) * IN,
                   "k": l["k"] * LBF_FT, "b": l["b"] * LBF_FT}
    return out


def sp(x: float, eps: float) -> tuple[float, float]:
    """The smooth positive part of StrutSpring/StrutDamper and its root."""
    r = math.sqrt(x * x + eps * eps)
    return (0.5 * eps * eps / (r - x) if x < 0.0 else 0.5 * (x + r)), r


def static(xcg: float = XCG, mass: float = SI.MASS) -> dict:
    """The rest on the gear: CG height and pitch where the springs carry the weight (no aero)."""
    geo = geometry(xcg)
    legs = [geo["nose"], geo["left"], geo["right"]]

    def res(z):
        h, th = z
        fz, m = 0.0, 0.0
        for l in legs:
            d = -(h + math.sin(th) * l["rx"] + math.cos(th) * l["rz"])
            f = l["k"] * sp(d, GEAR_EPS)[0]
            fz += f
            m += (math.cos(th) * l["rx"] - math.sin(th) * l["rz"]) * f
        return [fz - mass * SI.G0, m / 10.0]

    h, th = fsolve(res, [1.6, 0.0], xtol=1e-13)
    fn = {}
    q = {}
    for nm, l in geo.items():
        q[nm] = -(h + math.sin(th) * l["rx"] + math.cos(th) * l["rz"])
        fn[nm] = l["k"] * sp(q[nm], GEAR_EPS)[0]
    return {"h": float(h), "theta_deg": float(th * RTOD), "fn": fn, "q": q,
            "nose_share": fn["nose"] / sum(fn.values())}


class Scenario:
    """Everything the planar reference needs, as the model's globals and stimulus."""

    def __init__(self, **kw):
        self.t_end = 20.0
        self.vt0, self.h0, self.theta0, self.gamma0 = 0.0, 0.0, 0.0, 0.0
        self.alpha0, self.el0, self.thtl0 = 0.0, 0.0, 0.0
        self.gear0, self.gear_set, self.gear_t = 1.0, 1.0, 1.0
        self.throttle_set, self.throttle_t, self.throttle2_d, self.throttle2_t = None, 1.0, 0.0, 1.0
        self.brake_set, self.brake_t = 0.0, 1.0
        self.pitch_amp, self.pitch_t, self.pitch_dur = 0.0, 1.0, 1.0
        self.__dict__.update(kw)


FAST, THR_RAMP = 0.05, 0.2      # the model's edges (stick, brake, gear: 0.05 s; throttle: 0.2 s)


def ramp(t, t0, tau):
    return min(1.0, max(0.0, (t - t0) / tau))


class Plane:
    def __init__(self, des, sc: Scenario, xcg=XCG, mass=SI.MASS):
        self.des, self.sc, self.xcg, self.m = des, sc, xcg, mass
        self.geo = geometry(xcg)
        self.jy = SI.JYY
        self.th_set = sc.thtl0 if sc.throttle_set is None else sc.throttle_set

    def controls(self, t):
        s = self.sc
        stick = s.pitch_amp * (ramp(t, s.pitch_t, FAST) - ramp(t, s.pitch_t + s.pitch_dur, FAST))
        thr = (s.thtl0 + (self.th_set - s.thtl0) * ramp(t, s.throttle_t, THR_RAMP)
               + s.throttle2_d * ramp(t, s.throttle2_t, THR_RAMP))
        brake = s.brake_set * ramp(t, s.brake_t, FAST)
        cmd = s.gear0 + (s.gear_set - s.gear0) * ramp(t, s.gear_t, FAST)
        return stick, thr, brake, cmd

    def legs(self, X, dpos):
        """Normal and rolling force, and the world vector to the contact, of nose and left (= right)."""
        x, h, th, vx, vz, q = X[:6]
        pos = X[9]
        st, ct = math.sin(th), math.cos(th)
        out = []
        for nm in ("nose", "left", "right"):
            l = self.geo[nm]
            dx, dz = ct * l["rx"] - st * l["rz"], st * l["rx"] + ct * l["rz"]
            dq = -(h + dz) - L_RETRACT * (1.0 - pos)
            vcx = vx - dz * q          # the contact point's velocity (q > 0 nose up about -y)
            vcz = vz + dx * q
            ddq = -vcz + L_RETRACT * dpos
            xp, r = sp(dq, GEAR_EPS)
            sig = xp / r
            fk = l["k"] * xp
            fb = l["b"] * ddq * sig
            zp = sp(-fk - fb, GEAR_FEPS)[0]
            fn = fk + fb + sig * zp
            out.append((fn, vcx, dx, dz, dq))
        return out

    def rhs(self, t, X):
        x, h, th, vx, vz, q, power, el, xi, pos, cy, cf = X
        stick, thr, brake, cmd = self.controls(t)
        st, ct = math.sin(th), math.cos(th)
        ub, wb = vx * ct + vz * st, vx * st - vz * ct
        v2 = ub * ub + wb * wb
        dv = max(V_FLOOR * V_FLOOR - v2, 0.0)
        vt = math.sqrt(v2 + dv)
        alpha = math.atan2(wb, ub + dv / V_FLOOR)
        a_deg = alpha * RTOD
        vt_ft, alt_ft = vt / SI.FT, h / SI.FT
        mach, qbar_psf = F.adc(vt_ft, alt_ft)
        qbar = qbar_psf * SI.PSF
        cxt, _, czt, _, cmt, _ = F.coefficients(vt_ft, a_deg, 0.0, 0.0, q, 0.0, el, 0.0, 0.0, self.xcg)
        thrust = F.thrust(power, alt_ft, mach) * SI.LBF
        qs = qbar * SI.S
        dg = pos * CD_GEAR * qs
        fx_b = qs * cxt + thrust - dg * math.cos(alpha)
        fz_b = qs * czt - dg * math.sin(alpha)           # FRD: down
        m_b = qs * SI.CBAR * cmt - dg * math.cos(alpha) * Z_DRAG   # nose up +
        nz = -qs * czt / (self.m * SI.G0)
        # the gear: the weight on wheels reads the main struts' springs (no d pos/dt in it)
        p = self._spring_load(X)
        w = min(1.0, max(0.0, (p - F0_WOW) / (F1_WOW - F0_WOW)))
        c = min(1.0, max(0.0, cmd))
        tgt = c + (1.0 - c) * w
        dpos = min(1.0 / T_GEAR, max(-1.0 / T_GEAR, 5.0 * (tgt - pos)))
        legs = self.legs(X, dpos)
        fgx, fgz, mg = 0.0, 0.0, 0.0
        for k, (fn, vcx, dx, dz, _) in enumerate(legs):
            mu = MU_R + (0.0 if k == 0 else min(1.0, max(0.0, brake))) * (MU_BRAKE - MU_R)
            fr = mu * fn * math.tanh(vcx / V_ROLL)
            fgx -= fr
            fgz += fn
            mg += dx * fn + dz * fr
        ax = (fx_b * ct + fz_b * st + fgx) / self.m       # body x forward, body z down, at pitch th
        az = (fx_b * st - fz_b * ct + fgz) / self.m - SI.G0
        dq = (m_b + mg) / self.jy
        # the pitch law (PitchCommand, PitchFBW with the ground hand-over)
        cfg = self._cfg
        gamma = math.asin(min(1.0, max(-1.0, (ub * st - wb * ct) / vt)))
        q_deg = q * RTOD
        q_cmd, _, _ = sim3.pitch_command(cfg, stick, vt, a_deg, nz, gamma, 0.0, th)
        ka = sim3.table(self.des, "Ka", qbar, mach)
        kq = sim3.table(self.des, "Kq", qbar, mach)
        ki = sim3.table(self.des, "Ki", qbar, mach)
        u_raw = ka * (a_deg - self.sc.alpha0) + kq * (q_deg - fbw.KFF * q_cmd) + xi
        u = min(fbw.ACT_POS, max(-fbw.ACT_POS, u_raw))
        u_g = -fbw.ACT_POS * stick
        y = (1.0 - w) * u + w * u_g
        dxi = (1.0 - w) * (ki * (q_deg - q_cmd) + (u - u_raw) / fbw.T_AW) + w * (u_g - u_raw) / T_TRACK
        dcy, dcf = sim3.stab_comp(y, cy, cf, w)          # the phase-compensated rate limiter
        del_ = sim3.servo("el", cy, el)
        dpow = F.pdot(power, F.tgear(thr))
        return np.array([vx, vz, q, ax, az, dq, dpow, del_, dxi, dpos, dcy, dcf]), {
            "w": w, "fn": [l[0] for l in legs], "q": [l[4] for l in legs], "vt": vt, "alpha": a_deg, "nz": nz,
            "thrust": thrust}

    def _spring_load(self, X):
        ls = self.legs(X, 0.0)
        return sum(self.geo[nm]["k"] * sp(ls[k][4], GEAR_EPS)[0] for k, nm in ((1, "left"), (2, "right")))

    def start(self):
        s = self.sc
        th = (s.alpha0 + s.gamma0) / RTOD
        gam = s.gamma0 / RTOD
        X = np.array([0.0, s.h0, th, s.vt0 * math.cos(gam), s.vt0 * math.sin(gam), 0.0, 64.94 * s.thtl0, s.el0, s.el0,
                      s.gear0, s.el0, s.el0])
        return X

    def run(self, dt=1e-3, every=10):
        self._cfg = sim3.Config()
        F.CLAMP_AB = True
        X = self.start()
        n = int(round(self.sc.t_end / dt))
        rec = {k: [] for k in ("t", "x", "h", "theta", "vx", "vz", "q", "el", "pos", "fn_nose", "fn_left", "q_left",
                               "q_nose", "w", "vt", "alpha", "pow", "thrust")}
        for k in range(n + 1):
            t = k * dt
            k1, a = self.rhs(t, X)
            if k % every == 0:
                for key, v in (("t", t), ("x", X[0]), ("h", X[1]), ("theta", X[2] * RTOD), ("vx", X[3]), ("vz", X[4]),
                               ("q", X[5] * RTOD), ("el", X[7]), ("pos", X[9]), ("fn_nose", a["fn"][0]),
                               ("fn_left", a["fn"][1]), ("q_left", a["q"][1]), ("q_nose", a["q"][0]), ("w", a["w"]),
                               ("vt", a["vt"]), ("alpha", a["alpha"]), ("pow", X[6]), ("thrust", a["thrust"])):
                    rec[key].append(float(v))
            if k == n:
                break
            k2, _ = self.rhs(t + dt / 2, X + dt / 2 * k1)
            k3, _ = self.rhs(t + dt / 2, X + dt / 2 * k2)
            k4, _ = self.rhs(t + dt, X + dt * k3)
            X = X + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        return rec


def trim_approach(des, vt, gamma_deg, h=100.0, xcg=XCG):
    """Steady descent with the gear down: alpha (deg), stabilator (deg) and throttle."""
    F.CLAMP_AB = True
    gam = gamma_deg / RTOD

    def res(z):
        a_deg, el, thr = z
        sc = Scenario(vt0=vt, h0=h, alpha0=a_deg, gamma0=gamma_deg, el0=el, thtl0=thr, gear0=1.0, gear_set=1.0)
        pl = Plane(des, sc, xcg)
        pl._cfg = sim3.Config()
        X = pl.start()
        X[6] = F.tgear(thr)
        d, _ = pl.rhs(0.0, X)
        return [d[3] * math.cos(gam) + d[4] * math.sin(gam), -d[3] * math.sin(gam) + d[4] * math.cos(gam), d[5]]

    z = fsolve(res, [13.0, -2.0, 0.25], xtol=1e-12)
    return {"vt0": vt, "gamma0": gamma_deg, "alpha0": float(z[0]), "el0": float(z[1]), "thtl0": float(z[2])}


def summary(rec: dict) -> dict:
    t = np.array(rec["t"])
    fn = np.array(rec["fn_left"])
    fnn = np.array(rec["fn_nose"])
    on = np.nonzero(2 * fn + fnn > 100.0)[0]
    out = {"max_fn_left": float(fn.max()), "max_fn_nose": float(fnn.max()), "max_q_left": float(np.max(rec["q_left"])),
           "max_q_nose": float(np.max(rec["q_nose"])), "max_theta": float(np.max(rec["theta"])),
           "end": {k: float(rec[k][-1]) for k in ("t", "x", "h", "theta", "vx", "pos", "fn_nose", "fn_left", "alpha")}}
    if len(on):
        out["t_first_contact"] = float(t[on[0]])
        out["t_last_contact"] = float(t[on[-1]])
    return out


def steer_check(st: dict) -> dict:
    """Half pedal at a rolling 5 m/s: the kinematic yaw rate of a tricycle. The speed at the check
    is estimated from the idle thrust less the rolling resistance."""
    v0, pedal, t = 5.0, 0.5, 5.0
    a = (F.T_IDLE[0, 0] * SI.LBF - MU_R * SI.MASS * SI.G0) / SI.MASS
    v = v0 + a * t
    steer = pedal * float(np.interp(v, STEER_V, STEER_DEG)) / RTOD
    legs = geometry()
    wheelbase = legs["nose"]["rx"] - legs["left"]["rx"]
    r = v * math.tan(steer) / wheelbase * RTOD
    return {"v": v, "pedal": pedal, "t": t, "t_end": 6.0, "steer_deg": steer * RTOD, "wheelbase": wheelbase, "r_dps": r,
            "overrides": {"global:vt0": v0, "global:h0": st["h"], "global:alpha0": st["theta_deg"], "global:el0": 0.0,
                          "global:thtl0": 0.0, "global:throttle_set": 0.0, "global:gear0": 1.0, "global:gear_set": 1.0,
                          "global:roll_amp": 0.0, "global:pedal_amp": pedal, "global:pedal_dur": 100.0}}


def main() -> int:
    design = json.loads((HERE / "design.json").read_text(encoding="utf-8"))
    des = design["fbw"]
    st = static()
    w = SI.MASS * SI.G0
    print(f"static: h {st['h']:.4f} m, theta {st['theta_deg']:.4f} deg, nose {st['fn']['nose'] / 1e3:.2f} kN "
          f"({100 * st['nose_share']:.1f} %), mains {st['fn']['left'] / 1e3:.2f} kN each, "
          f"compression nose {st['q']['nose'] * 100:.2f} cm, mains {st['q']['left'] * 100:.2f} cm")
    rest = dict(h0=st["h"], alpha0=st["theta_deg"], el0=0.0, thtl0=0.0, gear0=1.0, gear_set=1.0)
    ap = trim_approach(des, V_APPROACH, GAMMA_APPROACH)
    print("approach trim:", ap)
    h_app = st["h"] + 30.0        # the wheels start about 30 m up
    specs = {
        # rest on the gear, idle, brakes set: settles at the static solution moved by the idle thrust
        "rest": Scenario(**{**rest, "t_end": 5.0, "brake_set": 1.0, "brake_t": 0.0}),
        # taxi power from rest, then idle and full brakes
        "taxi": Scenario(**{**rest, "t_end": 30.0, "throttle_set": 0.25, "throttle_t": 1.0, "throttle2_d": -0.25,
                            "throttle2_t": 14.0, "brake_set": 1.0, "brake_t": 15.0}),
        # full afterburner from rest, full aft stick to rotate, stick released, gear up
        "takeoff": Scenario(**{**rest, "t_end": 26.0, "throttle_set": 1.0, "throttle_t": 1.0, "pitch_amp": 1.0,
                               "pitch_t": 12.0, "pitch_dur": 1.8, "gear_set": 0.0, "gear_t": 16.0}),
        # a steady approach with the gear down, idle just before the wheels touch, no flare; the nose
        # comes down by itself, then full brakes
        "landing": Scenario(**{**ap, "h0": h_app, "t_end": 46.0, "throttle_set": 0.0, "throttle_t": 12.0,
                               "brake_set": 1.0, "brake_t": 17.0}),
    }
    out = {"source": "JSBSim aircraft/f16/f16.xml (E. Hofman, F-16A Block 32)", "legs": geometry(), "mu_r": MU_R,
           "mu_s": MU_S, "mu_brake": MU_BRAKE, "t_gear": T_GEAR, "cd_gear": CD_GEAR, "steer_v": STEER_V,
           "steer_deg": STEER_DEG, "l_retract": L_RETRACT, "z_drag": Z_DRAG, "f0_wow": F0_WOW, "f1_wow": F1_WOW,
           "t_track": T_TRACK, "stroke_max": STROKE_MAX, "v_floor": V_FLOOR, "gear_eps": GEAR_EPS, "gear_feps": GEAR_FEPS,
           "v_roll": V_ROLL, "v_side": V_SIDE, "sink_limit": SINK_LIMIT, "static": st, "approach": ap, "weight": w,
           "scenarios": {}}
    for nm, sc in specs.items():
        rec = Plane(des, sc).run()
        s = summary(rec)
        spec = {k: v for k, v in sc.__dict__.items() if v is not None}
        out["scenarios"][nm] = {"spec": spec, **s, "series": rec}
        print(f"{nm}: {json.dumps({k: v for k, v in s.items()}, default=float)}")
    land = out["scenarios"]["landing"]
    k = next(i for i, f in enumerate(land["series"]["fn_left"]) if f > 100.0)
    out["touchdown_sink"] = -land["series"]["vz"][k]
    out["touchdown_v"] = land["series"]["vx"][k]
    print(f"touchdown: sink {out['touchdown_sink']:.2f} m/s at {out['touchdown_v']:.1f} m/s, pitch {land['series']['theta'][k]:.1f} deg")
    out["steer"] = steer_check(st)
    print("steer:", out["steer"])
    for sc in out["scenarios"].values():      # 0.1 s is what the checks read, at 8 digits
        sc["series"] = {k: [float(f"{x:.8g}") for x in v[::10]] for k, v in sc["series"].items()}
    (HERE / "gear.json").write_text(json.dumps(out, indent=0) + "\n", encoding="utf-8", newline="\n")
    print("wrote gear.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
