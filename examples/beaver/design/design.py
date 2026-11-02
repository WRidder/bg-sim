# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Design and reference numbers of the `beaver` example.

    uv run examples/beaver/design/design.py

Writes `design/design.json`: every number the models, the checks and the docs use. Then
`uv run examples/beaver/design/build_model.py` writes the models, the scenes and `expected.json`.

1. Validation of the scipy model (`beaver_ref.py`, written from the FDC equations) in the exact
   source mode (rpm prescribed, power algebraic): the trim against [THESIS] Table 5-1 and FDC's
   data/cr4560.lin and cr4520.lin; the linearisation against FDC's A and B matrices; the modes
   against [THESIS] Table 5-3 (and the thesis' own beta-dot sign, see the README).
2. The coupled modes and eigenvectors the beaver-modes airframes are released on.
3. The drivetrain (ours): governor gains, and how much the shaft dynamics change the modes.
4. Reference runs: the open-loop steps (beaver-steps), the mode releases (beaver-modes) and the
   flyable demo (beaver-sim, `beaver_sim.py`), with the drivetrain on and off.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import beaver_data as D  # noqa: E402
import beaver_ref as R  # noqa: E402
import beaver_si as SI  # noqa: E402
import beaver_sim as S  # noqa: E402

D2R = math.pi / 180.0
NAMES = ["V", "alpha", "beta", "p", "q", "r", "psi", "theta", "phi", "xe", "ye", "H"]
UNAMES = ["de", "da", "dr", "df", "n", "pz"]
FAST = 0.05          # s, the edges of the block-shaped inputs
T_STEPS = 60.0


def cplx(z):
    return [float(z.real), float(z.imag)]


# --------------------------------------------------------------------------- 1. validation
def validate():
    fdc = json.loads((HERE / "fdc_lin.json").read_text(encoding="utf-8"))
    out = {}
    for tag, H, ref, lin in (("6000ft", 1828.8, D.TRIM_6000, fdc["cr4560.lin"]),
                             ("2000ft", 609.6, D.TRIM_2000, fdc["cr4520.lin"])):
        x, u = R.trim(45.0, H)
        Am, Bm = R.linearise(x, u)
        A_f, B_f = np.array(lin["A"]), np.array(lin["B"])
        # FDC's B columns: [de da dr df n pz] (aero inputs, then the engine inputs)
        trim = {"alpha": x[1], "beta": x[2], "theta": x[7], "de": u[0], "da": u[1], "dr": u[2], "pz": u[5]}
        fdc_trim = {"alpha": lin["xinco"][1], "beta": lin["xinco"][2], "theta": lin["xinco"][7],
                    "de": lin["uaero0"][0], "da": lin["uaero0"][1], "dr": lin["uaero0"][2], "pz": lin["uprop0"][1]}
        fdc_res = np.max(np.abs(R.xdot(np.array(lin["xinco"]), np.array(lin["uaero0"] + lin["uprop0"]))[:6]))
        rec = {"trim": {k: float(v) for k, v in trim.items()}, "fdc_trim": fdc_trim,
               "trim_residual": float(np.max(np.abs(R.xdot(x, u)[:6]))), "fdc_trim_residual": float(fdc_res),
               "max_dA": float(np.max(np.abs(Am - A_f))), "max_dB": float(np.max(np.abs(Bm - B_f))),
               "max_A": float(np.max(np.abs(A_f))),
               "modes": {k: (cplx(v) if isinstance(v, complex) else float(v)) for k, v in R.modes(Am).items()},
               "modes_fdcA": {k: (cplx(v) if isinstance(v, complex) else float(v)) for k, v in R.modes(A_f).items()}}
        if tag == "6000ft":
            rec["thesis_trim"] = ref["thesis"]
            rec["thesis_modes"] = {k: (cplx(v) if isinstance(v, complex) else float(v)) for k, v in D.MODES_THESIS.items()}
            # The 1993 thesis model applied the beta-dot correction the other way round: its beta row
            # is ours times (1 - k)/(1 + k), k = cos(beta) rho b S CYbdot/(4 m) (see the README).
            k = R.kbdot(R.atmosphere(H)[0], x[2])
            A2 = Am.copy()
            A2[2, :] *= (1 - k) / (1 + k)
            rec["kbdot"] = float(k)
            rec["modes_thesis_bdot"] = {kk: (cplx(v) if isinstance(v, complex) else float(v))
                                        for kk, v in R.modes(A2).items()}
            rec["A_asym_thesis_bdot"] = A2[np.ix_(R.LAT, R.LAT)].tolist()
            rec["A_sym"] = Am[np.ix_(R.LON, R.LON)].tolist()
        out[tag] = rec
    return out


# --------------------------------------------------------------------------- 2. coupled modes
DYN = [0, 1, 2, 3, 4, 5, 7, 8, 11]   # the states that feed back: V a b p q r theta phi H


def coupled(Am):
    """Eigen-analysis of the coupled 9-state model (psi, xe, ye do not feed back)."""
    A9 = Am[np.ix_(DYN, DYN)]
    lam, vec = np.linalg.eig(A9)
    return lam, vec


def pick(lam, vec, target):
    k = int(np.argmin(np.abs(lam - target)))
    return lam[k], vec[:, k]


def release(x0, Am, target, comp, amp):
    """Trim + the real part of the eigenvector nearest `target`, scaled so that state `comp`
    deviates by `amp`. psi follows from its kinematic row (it does not feed back)."""
    lam, vec = coupled(Am)
    l, v = pick(lam, vec, target)
    v = v / v[DYN.index(comp)] * amp
    dx = np.zeros(12)
    dx[DYN] = v.real
    full = np.zeros(12, dtype=complex)
    full[DYN] = v
    dpsi = (Am[6, :] @ full) / l
    dx[6] = dpsi.real
    return complex(l), x0 + dx


# --------------------------------------------------------------------------- 3. drivetrain
def drivetrain_modes(x0, u0, gov):
    """Modes of the 14-state model (airframe + shaft speed + governor integrator), with the
    drivetrain's thrust (1) and with the source's algebraic power (0)."""
    z0 = np.concatenate([x0, [u0[4] / R.RPM, gov["Cq0"]]])
    h = np.concatenate([R.XH, [1e-4, 1e-8]])
    out = {}
    for dt in (0, 1):
        J = R.jacobian(lambda z: R.xdot_ext(z, u0, gov, dt), z0, h)
        keep = DYN + [12, 13]
        lam = np.linalg.eigvals(J[np.ix_(keep, keep)])
        out[dt] = lam
    return out


def match_modes(lam_list, ref):
    res = {}
    for name, target in ref.items():
        k = int(np.argmin(np.abs(np.asarray(lam_list) - target)))
        res[name] = complex(lam_list[k])
    return res


# --------------------------------------------------------------------------- 4. reference runs
def ramp(t, t0, dur):
    return S.ramp(t, t0, dur)


STEPS = [  # (label, input index, kind, amplitude, t0, duration) -- [THESIS] figures 5-2 .. 5-7
    ("Elevator", 0, "block", 3.0 * D2R, 1.0, 2.0),
    ("Aileron", 1, "block", 3.0 * D2R, 1.0, 2.0),
    ("Rudder", 2, "block", 3.0 * D2R, 1.0, 2.0),
    ("Flap", 3, "ramp", 3.0 * D2R, 1.0, 3.0),
    ("Rpm", 4, "ramp", 200.0, 1.0, 4.0),
    ("Manifold", 5, "ramp", 2.0, 1.0, 2.0),
]


def step_input(u0, idx, kind, amp, t0, dur):
    def u(t):
        uu = np.array(u0, dtype=float)
        if kind == "block":
            uu[idx] += amp * (ramp(t, t0, FAST) - ramp(t, t0 + dur, FAST))
        else:
            uu[idx] += amp * ramp(t, t0, dur)
        return uu
    return u


def run_open(x0, ufun, t_end, breaks, dt_out=0.5, gov=None, drivetrain=0, u0=None):
    """Open-loop run of the airframe; with gov, of the 14-state model."""
    ts = np.round(np.arange(0.0, t_end + 1e-9, dt_out), 10)
    pts = sorted({0.0, t_end, *[b for b in breaks if 0.0 < b < t_end]})
    if gov is None:
        f = lambda t, x: R.xdot(x, ufun(t))  # noqa: E731
        z = np.array(x0, dtype=float)
    else:
        f = lambda t, z: R.xdot_ext(z, ufun(t), gov, drivetrain)  # noqa: E731
        z = np.concatenate([x0, [u0[4] / R.RPM, gov["Cq0"]]])
    out = np.zeros((len(ts), len(z)))
    for a, b in zip(pts[:-1], pts[1:]):
        sol = solve_ivp(f, (a, b), z, method="DOP853", rtol=1e-11, atol=1e-11, dense_output=True)
        for tt in ts[(ts >= a - 1e-12) & (ts <= b + 1e-12)]:
            out[int(round(tt / dt_out))] = sol.sol(tt)
        z = sol.y[:, -1]
    return ts, out


def record(ts, Z, extra=None):
    rec = {"t": ts.tolist()}
    for k, nm in enumerate(NAMES):
        rec[nm] = Z[:, k].tolist()
    deg = {"alpha": "alpha_deg", "beta": "beta_deg", "p": "p_deg", "q": "q_deg", "r": "r_deg",
           "theta": "theta_deg", "phi": "phi_deg", "psi": "psi_deg"}
    for nm, dn in deg.items():
        rec[dn] = (Z[:, NAMES.index(nm)] / D2R).tolist()
    if Z.shape[1] > 12:
        rec["rpm"] = (Z[:, 12] * R.RPM).tolist()
    if extra:
        rec.update(extra)
    return rec


def phidot(x):
    p, q, r, th, ph = x[3], x[4], x[5], x[7], x[8]
    return p + math.tan(th) * (q * math.sin(ph) + r * math.cos(ph))


# --------------------------------------------------------------------------- the flyable demo
DEMO = {  # the defaults of the beaver-sim globals (the demo); times in s
    "t_climb": 5.0, "climb_pz": 25.0, "climb_rpm": 2000.0, "climb_dtheta": 4.0, "t_turn": 30.0,
    "turn_psi": 90.0, "t_level": 70.0, "level_dh": 150.0, "t_power": 85.0, "edge": 3.0, "t_end": 150.0,
}


def demo_inputs(tr, spec):
    th0 = tr["theta0"]

    def inputs(t):
        rc = ramp(t, spec["t_climb"], spec["edge"])
        rp = ramp(t, spec["t_power"], spec["edge"])
        return {"col_pitch": 0.0, "col_roll": 0.0, "pedals": 0.0, "flaps": 0.0, "elev_trim": tr["de0"],
                "ail_trim": tr["da0"], "rud_trim": tr["dr0"],
                "pz": tr["pz0"] + (spec["climb_pz"] - tr["pz0"]) * (rc - rp),
                "rpm": tr["n0"] + (spec["climb_rpm"] - tr["n0"]) * (rc - rp),
                "ap_pitch": 2.0 if t >= spec["t_level"] else 1.0, "ap_roll": 2.0 if t >= spec["t_turn"] else 1.0,
                "theta_ref": th0 + spec["climb_dtheta"] * rc, "phi_ref": 0.0, "psi_ref": spec["turn_psi"],
                "h_ref": tr["H0"] + spec["level_dh"]}
    breaks = [spec["t_climb"], spec["t_climb"] + spec["edge"], spec["t_turn"], spec["t_level"],
              spec["t_power"], spec["t_power"] + spec["edge"]]
    return inputs, breaks


def demo_run(x0, u0, gov, tr, spec, drivetrain):
    inputs, breaks = demo_inputs(tr, spec)
    ts, Z = S.simulate(inputs, S.initial(x0, u0, gov), spec["t_end"], breaks, gov, x0[7], drivetrain, dt_out=0.5)
    rec = record(ts, Z[:, :13])
    rec["psi_deg"] = [((v + 180.0) % 360.0) - 180.0 for v in rec["psi_deg"]]
    rec["h_rel"] = (Z[:, 11] - tr["H0"]).tolist()
    for k, nm in enumerate(("servo_e", "servo_a", "servo_r")):
        rec[nm + "_deg"] = (Z[:, 14 + k] / D2R).tolist()
    return rec


def main() -> int:
    np.set_printoptions(precision=6, linewidth=160)
    val = validate()
    v6 = val["6000ft"]
    print("trim 6000 ft  ours vs FDC cr4560.lin vs thesis Table 5-1")
    for k in ("alpha", "beta", "theta", "de", "da", "dr", "pz"):
        print(f"  {k:6s} {v6['trim'][k]:+.9f} {v6['fdc_trim'][k]:+.9f} {v6['thesis_trim'][k]:+.4f}")
    for tag, rec in val.items():
        print(f"{tag}: residual ours {rec['trim_residual']:.1e}, FDC {rec['fdc_trim_residual']:.1e}; "
              f"max|dA| {rec['max_dA']:.2e}, max|dB| {rec['max_dB']:.2e}")
        for m, v in rec["modes"].items():
            print(f"   {m:13s} ours {v}  FDC A {rec['modes_fdcA'][m]}"
                  + (f"  thesis {rec['thesis_modes'][m]}  thesis-bdot {rec['modes_thesis_bdot'][m]}" if tag == "6000ft" else ""))

    # ---- the model's point: 45 m/s, 6000 ft, flaps up, 1800 rpm
    x0, u0 = R.trim(45.0, 1828.8)
    Am, Bm = R.linearise(x0, u0)
    gov = R.drive_gains(x0, u0)
    lam9, _ = coupled(Am)
    dec = R.modes(Am)
    coupled_modes = match_modes(lam9, {k: complex(v) for k, v in dec.items()})
    print("coupled modes:", coupled_modes)
    # releases: (label, mode, state, amplitude)
    rel_spec = [("Phugoid", "phugoid", 0, 2.0, 150.0), ("ShortPeriod", "short_period", 1, 1.0 * D2R, 150.0),
                ("DutchRoll", "dutch_roll", 2, 1.0 * D2R, 150.0), ("Roll", "roll", 8, 2.0 * D2R, 150.0),
                ("Spiral", "spiral", 8, 2.0 * D2R, 150.0)]
    releases = []
    for lab, mode, comp, amp, t_end in rel_spec:
        lam, xr = release(x0, Am, coupled_modes[mode], comp, amp)
        ts, Z = run_open(xr, lambda t: u0, t_end, [], dt_out=0.5, gov=gov, drivetrain=0, u0=u0)
        rec = record(ts, Z)
        rec["lambda_phi"] = [phidot(z) / z[8] if abs(z[8]) > 1e-14 else None for z in Z]
        pose, P = SI.starts(xr)
        releases.append({"label": lab, "mode": mode, "lambda": cplx(lam), "x0": xr.tolist(), "start_pose": pose,
                         "start_P": P, "run": rec, "props": R.mode_props(lam)})
        print(f"release {lab}: lambda {lam:.6f}")
    # drivetrain
    dm = drivetrain_modes(x0, u0, gov)
    ref = {k: complex(v) for k, v in coupled_modes.items()}
    dmodes = {dt: match_modes(dm[dt], ref) for dt in (0, 1)}
    shaft = {dt: sorted([complex(l) for l in dm[dt]],
                        key=lambda z: abs(z)) for dt in (0, 1)}
    print("drivetrain 0:", dmodes[0], "other:", shaft[0])
    print("drivetrain 1:", dmodes[1], "other:", shaft[1])
    # open-loop steps (exact source mode)
    steps = []
    for lab, idx, kind, amp, t0, dur in STEPS:
        ufun = step_input(u0, idx, kind, amp, t0, dur)
        brk = [t0, t0 + FAST, t0 + dur, t0 + dur + FAST] if kind == "block" else [t0, t0 + dur]
        ts, Z = run_open(x0, ufun, T_STEPS, brk, dt_out=0.5, gov=gov, drivetrain=0, u0=u0)
        steps.append({"label": lab, "input": UNAMES[idx], "kind": kind, "amp": amp, "t0": t0, "dur": dur,
                      "run": record(ts, Z)})
        print(f"step {lab}: V(60) {Z[-1, 0]:.3f} phi(60) {Z[-1, 8] / D2R:.2f} deg")
    # the drivetrain on the rpm step (shaft lag instead of the prescribed rpm)
    lab, idx, kind, amp, t0, dur = STEPS[4]
    ts, Z = run_open(x0, step_input(u0, idx, kind, amp, t0, dur), T_STEPS, [t0, t0 + dur], dt_out=0.5,
                     gov=gov, drivetrain=1, u0=u0)
    rpm_dt = record(ts, Z)
    # flyable demo
    tr = {"theta0": x0[7] / D2R, "de0": u0[0] / D2R, "da0": u0[1] / D2R, "dr0": u0[2] / D2R, "pz0": u0[5],
          "n0": u0[4], "H0": x0[11], "V0": x0[0], "alpha0": x0[1] / D2R, "beta0": x0[2] / D2R}
    demo = {dt: demo_run(x0, u0, gov, tr, DEMO, dt) for dt in (1, 0)}
    for dt in (1, 0):
        d = demo[dt]
        print(f"demo drivetrain={dt}: H(150) {d['h_rel'][-1]:.2f} psi(150) {d['psi_deg'][-1]:.2f} V(150) {d['V'][-1]:.2f} "
              f"max h_rel {max(d['h_rel']):.2f}")
    pose0, P0 = SI.starts(x0)
    design = {
        "validation": val,
        "point": {"V": 45.0, "H": 1828.8, "x0": x0.tolist(), "u0": u0.tolist(), "start_pose": pose0, "start_P": P0,
                  **{k: float(v) for k, v in tr.items()}},
        "si": {"mass": D.MASS, "J_principal": SI.J_PRINCIPAL.tolist(), "eps": SI.EPS, "q_bp": SI.Q_BP.tolist(),
               "g0": SI.G0, "S": D.S_WING, "b": D.SPAN, "c": D.CBAR},
        "aero": D.AERO, "prop": D.PROP, "dpt": [D.DPT_C1, D.DPT_C2], "power": D.POWER,
        "drive": {**R.DRIVE, **{k: float(v) for k, v in gov.items()}},
        "servo": {"tau": S.TAU_SERVO, "poly": S.SERVO_POLY, "dc": S.SERVO_DC, "t_aw": S.T_AW, "t_off": S.T_OFF},
        "pilot": S.PILOT,
        "modes": {"decoupled": {k: (cplx(v) if isinstance(v, complex) else float(v)) for k, v in dec.items()},
                  "coupled": {k: cplx(v) for k, v in coupled_modes.items()},
                  "drivetrain_off": {k: cplx(v) for k, v in dmodes[0].items()},
                  "drivetrain_on": {k: cplx(v) for k, v in dmodes[1].items()},
                  "shaft_off": [cplx(v) for v in shaft[0]], "shaft_on": [cplx(v) for v in shaft[1]],
                  "props": {k: R.mode_props(v) for k, v in coupled_modes.items()},
                  "props_on": {k: R.mode_props(v) for k, v in dmodes[1].items()}},
        "releases": releases,
        "steps": steps, "fast": FAST, "t_steps": T_STEPS, "rpm_step_drivetrain": rpm_dt,
        "demo_spec": DEMO, "demo": {"drivetrain_on": demo[1], "drivetrain_off": demo[0]},
    }
    (HERE / "design.json").write_text(json.dumps(design, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("wrote design.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
