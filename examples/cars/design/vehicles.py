"""The two vehicles of the `cars` example: parameters and the quantities derived from them.

Frames: world z up; vehicle (chassis) frame x forward, y left, z up, origin at the centre of
gravity of the SPRUNG mass. Corners FL, FR, RL, RR. Every number is SI.

The race car is a single-seater of Formula 3 size (about 740 kg with the driver, 2.8 m wheelbase,
a 260 kW electric motor on the rear axle, slick tyres, wings). The buggy is an off-road buggy
(930 kg, 2.7 m wheelbase, long-travel suspension, 33 inch tyres, four-wheel drive with a 60 kW
motor per axle). Both run on a 400 V battery pack with regenerative braking.
"""

from __future__ import annotations

import math
from copy import deepcopy

G0 = 9.81
RHO = 1.225
CORNERS = ("FL", "FR", "RL", "RR")

TYRE_SLICK = {
    "R0": 0.330, "kz": 2.6e5, "cz": 400.0, "Fz0": 2200.0, "mux": 1.65, "muy": 1.60, "dmu": -0.12,
    "Kx": 25.0, "Cx": 1.6, "Ex": 0.3, "Ky": 22.0, "Ky2": 2.5, "Cy": 1.45, "Ey": 0.2,
    "cx": 3.0e5, "cy": 1.8e5, "dx": 1500.0, "dy": 1200.0, "frr": 0.015, "wrr": 1.0, "vN": 0.2,
}
TYRE_OFFROAD = {
    "R0": 0.420, "kz": 1.6e5, "cz": 400.0, "Fz0": 2500.0, "mux": 1.00, "muy": 0.95, "dmu": -0.08,
    "Kx": 16.0, "Cx": 1.5, "Ex": 0.0, "Ky": 12.0, "Ky2": 2.2, "Cy": 1.35, "Ey": -0.2,
    "cx": 2.0e5, "cy": 1.2e5, "dx": 1500.0, "dy": 1200.0, "frr": 0.022, "wrr": 1.0, "vN": 0.2,
}

RACECAR = {
    "name": "racecar",
    "title": "Race car",
    "m_s": 620.0,                       # sprung mass, with the driver
    "J_s": [120.0, 650.0, 700.0],       # principal inertias of the sprung mass (roll, pitch, yaw)
    "L": 2.80,                          # wheelbase
    "track": [1.60, 1.55],              # front, rear
    "front_share": 0.43,                # static share of the total weight on the front axle
    "h_s": 0.30,                        # sprung CG height over the ground at the static ride height
    # unsprung: the carrier (wheel + hub, at the wheel centre) and, at the front, the steered
    # upright between the strut and the steering joint
    "m_carrier": 22.0, "J_carrier": [0.55, 0.55, 0.55], "Jw": 1.0,
    "m_upright": 8.0, "J_upright": [0.25, 0.25, 0.20],
    "tyre": TYRE_SLICK,
    # suspension (wheel rates; travel from the static position: bump +, droop -)
    "k": [60000.0, 72000.0], "c_bump": [3500.0, 4000.0], "c_reb": [5000.0, 5500.0],
    "bump": [0.045, 0.045], "droop": [0.060, 0.060], "k_stop": 4.0e7, "k_arb": [40000.0, 22000.0],
    # joints: stiffness and damping of the held directions (bushings)
    "joint": {"kr": 4.0e5, "br": 200.0, "kt": 4.0e7, "bt": 1.5e4},
    # steering: road-wheel angle at full lock, Ackermann share, the steering servo
    "steer_max": math.radians(20.0), "ackermann": 1.0, "k_steer": 1.0e5, "c_steer": 300.0,
    # aerodynamics: drag area, downforce area, front share of the downforce, drag height
    "CdA": 0.95, "ClA": 2.6, "aero_front": 0.42, "h_drag": 0.35, "CyA": 1.5,
    # electric drive: one motor on the rear axle (fixed reduction, open differential with a
    # viscous limited slip); torque/power envelope, regeneration limits, rotor inertia and drag,
    # the torsional stiffness and damping of the shaft from the rotor to the reduction
    "drive": "rwd", "motors": ["R"],
    "motor": {"T_max": 300.0, "P_max": 260.0e3, "w_max": 2094.0, "w_cut": 20.0, "T_regen": 300.0,
              "P_regen": 200.0e3, "w_fade": 30.0, "J": 0.04, "b": 0.002, "n": 7.0,
              "k_shaft": 1500.0, "d_shaft": 8.0},
    # battery pack: 40 kWh, 340..403 V open circuit, internal resistance, start charge
    "battery": {"Q": 100.0, "V_empty": 340.0, "V_full": 403.0, "R": 0.06, "soc0": 0.9},
    "lsd": 40.0,                        # viscous limited slip of the rear differential (N m s/rad)
    "brake_max": [1900.0, 1300.0],      # brake torque per wheel at full pedal, front and rear
    "brake_w_eps": 2.0, "handbrake_max": 0.0,
}

BUGGY = {
    "name": "buggy",
    "title": "Buggy",
    "m_s": 750.0,
    "J_s": [300.0, 900.0, 1000.0],
    "L": 2.70,
    "track": [1.75, 1.75],
    "front_share": 0.45,
    "h_s": 0.75,
    "m_carrier": 34.0, "J_carrier": [1.4, 1.4, 1.4], "Jw": 2.4,
    "m_upright": 11.0, "J_upright": [0.4, 0.4, 0.3],
    "tyre": TYRE_OFFROAD,
    "k": [14000.0, 17000.0], "c_bump": [1400.0, 1600.0], "c_reb": [2200.0, 2500.0],
    "bump": [0.20, 0.20], "droop": [0.17, 0.17], "k_stop": 4.0e7, "k_arb": [6000.0, 0.0],
    "joint": {"kr": 4.0e5, "br": 300.0, "kt": 4.0e7, "bt": 2.0e4},
    "steer_max": math.radians(30.0), "ackermann": 1.0, "k_steer": 1.0e5, "c_steer": 400.0,
    "CdA": 1.30, "ClA": 0.0, "aero_front": 0.5, "h_drag": 0.9, "CyA": 2.5,
    # electric four-wheel drive: one motor per axle (each with its reduction and an open axle
    # differential with a viscous coupling), the same motor front and rear
    "drive": "awd", "motors": ["F", "R"],
    "motor": {"T_max": 150.0, "P_max": 60.0e3, "w_max": 1257.0, "w_cut": 20.0, "T_regen": 150.0,
              "P_regen": 50.0e3, "w_fade": 30.0, "J": 0.03, "b": 0.002, "n": 10.0,
              "k_shaft": 1200.0, "d_shaft": 6.0},
    "battery": {"Q": 60.0, "V_empty": 340.0, "V_full": 403.0, "R": 0.08, "soc0": 0.9},
    "lsd": 25.0,                        # viscous coupling of each axle differential
    "brake_max": [1600.0, 1100.0],
    "brake_w_eps": 2.0, "handbrake_max": 1800.0,
}


def derived(v: dict) -> dict:
    """Corner positions, static loads, spring preloads and ride heights (a copy of `v` plus)."""
    v = deepcopy(v)
    ty = v["tyre"]
    L = v["L"]
    m_u_front = v["m_carrier"] + v["m_upright"]          # per front corner
    m_u_rear = v["m_carrier"]                            # per rear corner (no steering upright)
    m_tot = v["m_s"] + 2 * m_u_front + 2 * m_u_rear
    # sprung CG from the front axle so that the total weight splits front_share : 1 - front_share
    a_tot = (1.0 - v["front_share"]) * L                 # total CG behind the front axle
    a = (m_tot * a_tot - 2 * m_u_rear * L) / v["m_s"]    # sprung CG behind the front axle
    b = L - a
    # static loads: sprung corner loads (springs) and tyre loads
    Ws = v["m_s"] * G0
    spring = [Ws * b / L / 2, Ws * b / L / 2, Ws * a / L / 2, Ws * a / L / 2]
    m_u = [m_u_front, m_u_front, m_u_rear, m_u_rear]
    Fz = [spring[i] + m_u[i] * G0 for i in range(4)]
    defl = [Fz[i] / ty["kz"] for i in range(4)]
    tf, tr = v["track"]
    pos = {"FL": (a, tf / 2), "FR": (a, -tf / 2), "RL": (-b, tr / 2), "RR": (-b, -tr / 2)}
    corners = {}
    for i, c in enumerate(CORNERS):
        ax = 0 if i < 2 else 1
        zc = ty["R0"] - defl[i]                          # wheel centre height at rest
        corners[c] = {
            "x": pos[c][0], "y": pos[c][1], "z": zc - v["h_s"],     # wheel centre in the chassis frame
            "z_world": zc, "spring": spring[i], "Fz": Fz[i], "defl": defl[i], "m_u": m_u[i],
            "k": v["k"][ax], "c_bump": v["c_bump"][ax], "c_reb": v["c_reb"][ax],
            "bump": v["bump"][ax], "droop": v["droop"][ax], "front": i < 2, "left": i % 2 == 0,
            "steered": i < 2, "driven": (v["drive"] == "awd") or (i >= 2),
            "brake": v["brake_max"][ax], "handbrake": v["handbrake_max"] if i >= 2 else 0.0,
        }
    v.update({"m_tot": m_tot, "a": a, "b": b, "corners": corners, "W": m_tot * G0})
    return v


def vehicles() -> dict[str, dict]:
    return {"racecar": derived(RACECAR), "buggy": derived(BUGGY)}


if __name__ == "__main__":
    for name, v in vehicles().items():
        print(name, f"m_tot {v['m_tot']:.1f} kg, a {v['a']:.4f} m, b {v['b']:.4f} m")
        for c, k in v["corners"].items():
            print(f"  {c}: x {k['x']:+.3f} y {k['y']:+.3f} z {k['z']:+.4f}  spring {k['spring']:.1f} N  Fz {k['Fz']:.1f} N")
