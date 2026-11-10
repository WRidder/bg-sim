# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Design data of the `ingenuity` example: everything the models need, derived from the published data
of `ingenuity_data.py` and checked against the published test and flight data.

1. Blade stations (Koning et al. 2018 Table 2) and solidity.
2. The profile-drag polar of the BEMT rotor model, fitted to the JPL 25-ft Space Simulator hover test
   (Koning et al. 2019 Fig. 25, digitised in `jpl_hover_test.json`). This is the ONLY fit.
3. Independent comparisons of the fitted rotor model (printed, and turned into checks by
   `build_model.py`): Flight One hover on Mars (density 0.0165, 2537 rpm: 210 W electrical rotor power,
   collectives 8.2 deg upper / 9.2 deg lower, NASA 2021), the cyclic torque steps of the JPL system
   identification (Grip et al. 2017 Fig. 15) and the CAMRAD II collective sweep at Mars condition 2
   (Dull et al. 2022 Fig. 4).
4. Mass properties (an estimate: component budget, README) and the roll/pitch apparent inertia.
5. Motor, rotor-speed governor and flight-controller gains.

Run: ``uv run examples/ingenuity/design/design.py`` (prints the derivation and writes design.json).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import brentq, least_squares

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ingenuity_data as D  # noqa: E402
import rotor_ref as RR  # noqa: E402

A_DISK = math.pi * D.RADIUS**2
SPIN_UPPER, SPIN_LOWER = -1.0, 1.0      # lower rotor counter-clockwise seen from above [EST: convention]


# ----------------------------------------------------------------------------- 1. blade
BLADE = RR.blade()


# ----------------------------------------------------------------------------- 2. the fit
def jpl_data():
    data = json.loads((HERE / "jpl_hover_test.json").read_text(encoding="utf-8"))
    return np.array(data["CT"]), np.array(data["CP"])


def cp_model(pol: RR.Polar, ct: float, rho: float, rpm: float) -> float:
    om = D.omega(rpm)
    vt = om * D.RADIUS
    t = RR.trim(BLADE, pol, ct * rho * A_DISK * vt**2, om, rho)
    return t["P_shaft"] / (rho * A_DISK * vt**3)


def fit_polar() -> tuple[RR.Polar, np.ndarray]:
    CT, CP = jpl_data()
    sel = CT > 0.008          # the three lowest points sit below the model's validity (near-zero thrust)

    def res(p):
        pol = RR.Polar(p[0], p[1], 0.25)
        return [cp_model(pol, ct, D.RHO_JPL, D.RPM_JPL) / cp - 1.0 for ct, cp in zip(CT[sel], CP[sel])]

    sol = least_squares(res, [0.04, 0.05])
    return RR.Polar(float(sol.x[0]), float(sol.x[1]), 0.25), np.array(sol.fun)


# ----------------------------------------------------------------------------- 4. mass properties
def mass_properties() -> dict:
    """Component budget [EST] around the published total mass, dimensions and blade mass."""
    z_bot = D.GROUND_CLEARANCE
    z_fuse = z_bot + D.FUSE_Z / 2.0
    z_top = z_bot + D.FUSE_Z
    z_lower = 0.327                                  # lower rotor plane above the ground [EST]
    z_upper = z_lower + D.ROTOR_SPACING_FRAC * D.RADIUS
    z_solar = 0.475                                  # solar panel [EST: overall height 0.49 m]
    # legs: from the fuselage top corners, along the fuselage diagonal, to the ground (Dull22: the legs
    # "emanate diagonally from the top of the airframe"); leg length and clearance published
    corner = np.array([D.FUSE_X / 2.0, D.FUSE_Y / 2.0])
    reach = math.sqrt(D.LEG_LENGTH**2 - z_top**2)
    foot = corner + reach * corner / np.linalg.norm(corner)
    m_blades = 4 * D.BLADE_MASS
    parts = {   # name: (mass kg, z m, [Ixx, Iyy, Izz] about the part's own centre)
        "fuselage": (None, z_fuse, None),
        "blades_lower": (2 * D.BLADE_MASS, z_lower, None),
        "blades_upper": (2 * D.BLADE_MASS, z_upper, None),
        "hubs_swashplates_servos": (0.25, 0.5 * (z_lower + z_upper), [0.0004, 0.0004, 0.0003]),
        "motors": (0.16, 0.5 * (z_lower + z_upper), [0.0002, 0.0002, 0.0002]),
        "mast_wiring": (0.06, 0.5 * (z_top + z_solar), [0.0005, 0.0005, 0.00001]),
        "solar_panel": (0.06, z_solar, None),
        "legs": (0.10, 0.5 * z_top, None),
    }
    m_rest = sum(v[0] for k, v in parts.items() if v[0] is not None)
    m_fuse = D.MASS - m_rest
    parts["fuselage"] = (m_fuse, z_fuse, [m_fuse * (D.FUSE_Y**2 + D.FUSE_Z**2) / 12.0,
                                          m_fuse * (D.FUSE_X**2 + D.FUSE_Z**2) / 12.0,
                                          m_fuse * (D.FUSE_X**2 + D.FUSE_Y**2) / 12.0])
    # blades: mass along the span in proportion to the chord
    y, c, w = BLADE.y, BLADE.c, BLADE.wd
    i_pol = D.BLADE_MASS * float(np.sum(c * y * y * w) / np.sum(c * w))      # one blade about the spin axis
    for k in ("blades_lower", "blades_upper"):
        parts[k] = (parts[k][0], parts[k][1], [i_pol, i_pol, 0.0])           # two blades: 2 * i_pol / 2 transverse
    sx, sy = 0.40, 0.165
    parts["solar_panel"] = (0.06, z_solar, [0.06 * sy**2 / 12.0, 0.06 * sx**2 / 12.0, 0.06 * (sx**2 + sy**2) / 12.0])
    # legs: four rods, centre at half the reach
    rl = 0.5 * (np.linalg.norm(corner) + np.linalg.norm(foot))
    parts["legs"] = (0.10, 0.5 * z_top, [0.10 * (0.5 * rl**2) + 0.10 * D.LEG_LENGTH**2 / 12 * 0.5,
                                          0.10 * (0.5 * rl**2) + 0.10 * D.LEG_LENGTH**2 / 12 * 0.5,
                                          0.10 * rl**2])
    m_tot = sum(v[0] for v in parts.values())
    z_cg = sum(v[0] * v[1] for v in parts.values()) / m_tot
    J = np.zeros(3)
    for m, z, Jc in parts.values():
        J += np.array(Jc) + m * np.array([(z - z_cg) ** 2, (z - z_cg) ** 2, 0.0])
    ja = 2.0 * i_pol + D.ROTOR_HUB_INERTIA
    return {"m": m_tot, "m_fuselage": m_fuse, "z_cg": z_cg, "J_rigid": J.tolist(),
            "J": [J[0] * D.APPARENT_INERTIA_FACTOR, J[1] * D.APPARENT_INERTIA_FACTOR, J[2]],
            "Ja": ja, "blade_polar_inertia": i_pol,
            "z_lower": z_lower, "z_upper": z_upper, "z_fuse": z_fuse, "z_top": z_top, "z_solar": z_solar,
            "foot": foot.tolist(), "corner": corner.tolist(), "m_blades": m_blades}


# ----------------------------------------------------------------------------- 5. control
def derivatives(pol, rho, rpm, thrust):
    om = D.omega(rpm)
    t = RR.trim(BLADE, pol, thrust, om, rho)
    ths, tha = 0.5 * (t["theta_u"] + t["theta_l"]), 0.5 * (t["theta_l"] - t["theta_u"])
    h = 1e-5

    def forces(s, a, vc=0.0):
        tu, qu, tl, ql, _ = RR.coax(BLADE, pol, s - a, s + a, om, vc, rho)
        # yaw torque on the airframe in steady spin: the motor reactions -spin Q of both rotors
        return tu + tl, -SPIN_UPPER * qu - SPIN_LOWER * ql

    T0, N0 = forces(ths, tha)
    Z_th = (forces(ths + h, tha)[0] - forces(ths - h, tha)[0]) / (2 * h)
    N_th = (forces(ths, tha + h)[1] - forces(ths, tha - h)[1]) / (2 * h)
    Z_w = (forces(ths, tha, h)[0] - forces(ths, tha, -h)[0]) / (2 * h)
    return {"trim": t, "th_s": ths, "th_a": tha, "Z_th": Z_th, "N_th": N_th, "Z_w": Z_w}


def pid_triple(p: float) -> tuple[float, float, float]:
    """PID on a double integrator with all three closed-loop poles at -p: (Kp, Kd, Ki)."""
    return 3.0 * p * p, 3.0 * p, p**3


def build() -> dict:
    pol, res = fit_polar()
    geo, sig_t = RR.solidity(BLADE)
    mp = mass_properties()
    W = mp["m"] * D.G_MARS
    rho, rpm = D.RHO_FLIGHT1, D.RPM_FLIGHT1
    om = D.omega(rpm)
    der = derivatives(pol, rho, rpm, W)
    trim = der["trim"]
    kc = RR.cyclic_moment_gain(BLADE, rho, om)
    ke = RR.edgewise_moment_gain(BLADE, rho, om) * D.EDGEWISE_GAIN
    k_q = D.LP_MQ_IDENTIFIED * mp["J"][0] / 2.0
    # motor: R_w so that the drive efficiency at hover is the published 78 %
    q_hover = 0.5 * (trim["Q_u"] + trim["Q_l"])
    i_hover = q_hover / D.MOTOR_KT
    p_loss = q_hover * om * (1.0 / D.DRIVE_EFFICIENCY - 1.0)
    R_w = p_loss / i_hover**2
    u_hover = D.MOTOR_KT * om + R_w * i_hover
    # governor: PI on speed, closed-loop bandwidth ~ 12 rad/s on Ja dw/dt = k_t (u - k_e w)/R_w - Q
    damping = D.MOTOR_KT**2 / R_w + 2.0 * q_hover / om
    wg = 12.0
    Kp_g = (mp["Ja"] * 2.0 * 0.9 * wg - damping) * R_w / D.MOTOR_KT
    Ki_g = mp["Ja"] * wg * wg * R_w / D.MOTOR_KT
    # ground idle: the collective at which the pair makes 10 % of the weight (rotor spinning, gear loaded)
    th_idle = brentq(lambda th: sum(RR.coax(BLADE, pol, th, th, om, 0.0, rho)[k] for k in (0, 2)) - 0.1 * W,
                     math.radians(-4.0), math.radians(10.0))
    gains = {
        "heave": pid_triple(3.5), "yaw": pid_triple(4.5), "att": pid_triple(6.0), "pos": pid_triple(1.0),
    }
    out = {
        "polar": {"d0": pol.d0, "d2": pol.d2, "clm": pol.clm, "fit_rms": float(np.sqrt(np.mean(res**2))),
                  "fit_max": float(np.max(np.abs(res)))},
        "solidity": {"geometric": geo, "thrust_weighted": sig_t},
        "blade": {"y": BLADE.y.tolist(), "c": BLADE.c.tolist(), "tw": BLADE.tw.tolist(),
                  "lf": (BLADE.wl / BLADE.wd).tolist(), "wd": BLADE.wd.tolist()},
        "mass": mp, "weight": W, "rho": rho, "rpm": rpm, "omega": om,
        "hover": {"theta_u_deg": math.degrees(trim["theta_u"]), "theta_l_deg": math.degrees(trim["theta_l"]),
                  "T_u": trim["T_u"], "T_l": trim["T_l"], "Q_u": trim["Q_u"], "Q_l": trim["Q_l"],
                  "P_shaft": trim["P_shaft"], "P_el": trim["P_shaft"] / D.DRIVE_EFFICIENCY, "v_u": trim["v_u"],
                  "th_s": der["th_s"], "th_a": der["th_a"]},
        "Z_th": der["Z_th"], "N_th": der["N_th"], "Z_w": der["Z_w"],
        "k_c": kc, "k_e": ke, "k_q": k_q,
        "motor": {"k_t": D.MOTOR_KT, "R_w": R_w, "i_hover": i_hover, "u_hover": u_hover, "Kp": Kp_g, "Ki": Ki_g},
        "th_idle": th_idle, "gains": gains,
    }
    return out


def comparisons(d: dict) -> dict:
    pol = RR.Polar(d["polar"]["d0"], d["polar"]["d2"], d["polar"]["clm"])
    # (a) Grip17 Fig. 15: 5 deg cyclic steps on the lower rotor, JPL conditions; measured about 0.55 N m
    cyc = RR.cyclic_moment_gain(BLADE, D.RHO_JPL, D.omega(D.RPM_JPL)) * math.radians(5.0)
    # (b) Dull22 Fig. 4, CAMRAD II at Mars condition 2 (rho 0.017, 2800 rpm), torque-trimmed sweep
    om2, rho2 = D.omega(2800.0), 0.017
    sweep = {}
    for th in (5.0, 10.0, 15.0):
        dl = brentq(lambda x: (lambda r: r[1] - r[3])(RR.coax(BLADE, pol, math.radians(th - x), math.radians(th + x), om2, 0.0, rho2)), -3, 3)
        r = RR.coax(BLADE, pol, math.radians(th - dl), math.radians(th + dl), om2, 0.0, rho2)
        sweep[th] = {"CT": (r[0] + r[2]) / (rho2 * A_DISK * (om2 * D.RADIUS) ** 2), "dcoll": dl}
    return {"cyclic_5deg_torque": cyc, "mc2_sweep": sweep}


def main() -> int:
    d = build()
    d["comparisons"] = comparisons(d)
    h = d["hover"]
    print(f"blade: geometric solidity {d['solidity']['geometric']:.4f}, thrust-weighted {d['solidity']['thrust_weighted']:.4f}")
    print(f"polar fit to the JPL hover test: d0 {d['polar']['d0']:.4f}, d2 {d['polar']['d2']:.4f}, "
          f"rms {100 * d['polar']['fit_rms']:.1f} %, max {100 * d['polar']['fit_max']:.1f} %")
    mp = d["mass"]
    print(f"mass {mp['m']:.3f} kg (fuselage {mp['m_fuselage']:.3f}), CoM {mp['z_cg']:.3f} m above ground, "
          f"J rigid {np.round(mp['J_rigid'], 4)}, J model {np.round(mp['J'], 4)}, Ja {mp['Ja']:.5f}")
    print(f"Flight One hover (rho {d['rho']}, {d['rpm']} rpm, W {d['weight']:.3f} N): upper {h['theta_u_deg']:.2f} deg "
          f"(flight 8.2), lower {h['theta_l_deg']:.2f} deg (flight 9.2); thrust {h['T_u']:.2f} + {h['T_l']:.2f} N; "
          f"shaft {h['P_shaft']:.1f} W, electrical {h['P_el']:.1f} W (flight 210 W)")
    print(f"Z_th {d['Z_th']:.2f} N/rad, N_th {d['N_th']:.3f} N m/rad, Z_w {d['Z_w']:.3f} N s/m, "
          f"k_c {d['k_c']:.3f} N m/rad, k_e {d['k_e']:.4f} N s, k_q {d['k_q']:.4f}")
    m = d["motor"]
    print(f"motor R_w {m['R_w']:.3f} Ohm, i {m['i_hover']:.2f} A, u {m['u_hover']:.2f} V; governor Kp {m['Kp']:.3f} Ki {m['Ki']:.3f}; "
          f"idle collective {math.degrees(d['th_idle']):.2f} deg")
    c = d["comparisons"]
    print(f"cyclic 5 deg, lower rotor, JPL conditions: {c['cyclic_5deg_torque']:.3f} N m (measured about 0.55)")
    for th, v in c["mc2_sweep"].items():
        print(f"MC2 collective {th:4.1f} deg: CT {v['CT']:.4f} (differential {v['dcoll']:.2f} deg)")
    (HERE / "design.json").write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
