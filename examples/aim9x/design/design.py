# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Reference numbers of the AIM-9X example.

The checks in `expected.json` are analytic identities of the same laws the model uses (thrust,
mass budget, lift and drag, seeker range and irradiance, the PN gain) plus a linearised
short-period mode of the airframe and the ideal rocket delta-v. They are computed here, not
read back from a run, so a model change that breaks a law is caught.

Run: ``uv run examples/aim9x/design/design.py`` (writes design.json).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import data as d


def interp(x, xs, ys):
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for k in range(len(xs) - 1):
        if x <= xs[k + 1]:
            f = (x - xs[k]) / (xs[k + 1] - xs[k])
            return ys[k] + f * (ys[k + 1] - ys[k])
    return ys[-1]


def main() -> int:
    out = {}
    # atmosphere and lift at the airframe start
    _, _, rho0, a0 = d.atmosphere(d.H_TEST)
    v0 = d.V_TEST
    qbar0 = 0.5 * rho0 * v0 * v0
    alpha = math.radians(2.0)
    cna = interp(v0 / a0, d.MACH_TAB, d.CN_ALPHA_TAB)
    cn = cna * alpha + d.CN3 * alpha**3
    cd = interp(v0 / a0, d.MACH_TAB, d.CD0_TAB) + d.K_INDUCED * cn * cn
    nz0 = qbar0 * d.S_REF * cn / (d.MASS_0 * d.G0)
    out["airframe"] = {
        "h": d.H_TEST, "v": v0, "rho": rho0, "qbar": qbar0, "mach": v0 / a0,
        "cn": cn, "cd": cd, "nz": nz0, "cna": cna,
    }

    # motor: the flow profile is a 0.05 s rise, a plateau and a 0.15 s tail-off; the burned mass
    # is the area under it. Thrust at a given ambient pressure is mdot c - p A_e.
    burned = d.MDOT * (d.T_BURN - d.TAU_IGN / 2.0 - d.TAU_TAIL / 2.0)
    m_f = d.MASS_0 - burned
    _, p1, _, _ = d.atmosphere(d.H_TEST)
    mdot_1 = d.MDOT  # plateau at t = 1 s
    thrust_1 = mdot_1 * d.C_VAC - p1 * d.EXIT_AREA
    out["motor"] = {
        "burned": burned, "m_f": m_f, "mdot": d.MDOT, "thrust_1": thrust_1,
        "thrust_vac": d.MDOT * d.C_VAC, "isp_vac": d.ISP_VAC,
        "delta_v_ideal": d.C_VAC * math.log(d.MASS_0 / m_f),
    }
    _, p_launch, _, _ = d.atmosphere(d.P_M0[2])
    out["motor"]["thrust_1_launch"] = d.MDOT * d.C_VAC - p_launch * d.EXIT_AREA

    # short-period mode of the airframe, linearised about the start (alpha, q), with the
    # standard missile short-period form:
    #   alpha' = q - (qbar S cna / (m V)) alpha
    #   q'     = (qbar S d CM_RATIO cna / J) alpha + (qbar S d CM_Q d / (2 V) / J) q
    zaa = qbar0 * d.S_REF * cna / (d.MASS_0 * v0)
    maa = qbar0 * d.S_REF * d.DIAMETER * d.CM_RATIO * cna / d.J_0[1]
    mqq = qbar0 * d.S_REF * d.DIAMETER * d.CM_Q * d.DIAMETER / (2.0 * v0) / d.J_0[1]
    A = [[-zaa, 1.0], [maa, mqq]]
    tr = A[0][0] + A[1][1]
    det = A[0][0] * A[1][1] - A[0][1] * A[1][0]
    disc = tr * tr - 4.0 * det
    if disc < 0:
        wn = math.sqrt(det)
        zeta = -tr / (2.0 * wn)
        out["mode"] = {"wn": wn, "zeta": zeta, "real": tr / 2.0, "imag": math.sqrt(-disc) / 2.0}
    else:
        l1 = (tr + math.sqrt(disc)) / 2.0
        l2 = (tr - math.sqrt(disc)) / 2.0
        out["mode"] = {"l1": l1, "l2": l2, "wn": math.sqrt(abs(det)), "zeta": float("nan")}

    # a second linearisation at the mean condition of the 1.2..3.8 s fit window (qbar 500 kPa,
    # 1050 m/s, 70 kg, J 47 kg m^2), where the measured ring-down is read
    qf, vf, mf, jf = 500000.0, 1050.0, 70.0, 47.0
    cnaf = interp(vf / 340.0, d.MACH_TAB, d.CN_ALPHA_TAB)
    zf = qf * d.S_REF * cnaf / (mf * vf)
    maf = qf * d.S_REF * d.DIAMETER * d.CM_RATIO * cnaf / jf
    mqf = qf * d.S_REF * d.DIAMETER * d.CM_Q * d.DIAMETER / (2.0 * vf) / jf
    trf = -zf + mqf
    detf = (-zf) * mqf - maf
    out["mode_fit"] = {
        "wn": math.sqrt(detf) if detf > 0 else math.sqrt(-detf),
        "zeta": -trf / (2.0 * math.sqrt(detf)) if detf > 0 else float("nan"),
        "qbar": qf, "v": vf, "m": mf,
    }

    # seeker geometry and irradiance at launch
    dx = [d.P_T0[k] - d.P_M0[k] for k in range(3)]
    r0 = math.sqrt(sum(x * x for x in dx))
    ux = [x / r0 for x in dx]
    v_t = [d.V_T0 * math.cos(math.radians(d.PSI_T0)), d.V_T0 * math.sin(math.radians(d.PSI_T0)), 0.0]
    v_m = [d.V_M0, 0.0, 0.0]
    vrel = [v_t[k] - v_m[k] for k in range(3)]
    closing = -sum(ux[k] * vrel[k] for k in range(3))
    vhat = [v_t[k] / d.V_T0 for k in range(3)]
    rear = 0.5 * (1.0 - sum(-ux[k] * vhat[k] for k in range(3)))
    ir_t = d.IR_TARGET * (1.0 + d.IR_REAR_FACTOR * rear) / (r0 * r0) * math.exp(-d.IR_ATTEN * r0)
    out["seeker"] = {
        "range": r0, "closing": closing, "rear": rear, "ir": ir_t,
        "pn_gain": d.N_PN * closing, "a_y_ideal": d.N_PN * closing * 0.0,
    }

    out["globals"] = {"m0": d.MASS_0, "m_dry": d.MASS_DRY, "t_burn": d.T_BURN}

    (HERE / "design.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
