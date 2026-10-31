"""Parameters of the suction-gripper example, shared by the model builder and the design script.

Every value here becomes a global parameter of the models (``build_model.py``), so the editor's
Equations manager, the dashboard and the design sweep all change the same numbers.
"""

from __future__ import annotations

import math

G0 = 9.81
P_ATM = 101325.0
RHO_AIR = 1.2

# ------------------------------------------------------------------ parcel (a closed carton)
PARCEL = dict(m_p=10.0, L_p=0.50, W_p=0.30, H_p=0.30, cx=0.0, cy=0.0, cz=0.0)

# ------------------------------------------------------------------ cups: 2 x 3 bellows cups, diameter 50 mm
CUP = dict(
    L0=0.04,          # m      mount-to-lip rest length
    A_eff=1.4e-3,     # m^2    effective suction area (42 mm effective diameter)
    D_lip=0.05,       # m      lip diameter
    k_ax=5000.0,      # N/m    bellows axial stiffness
    d_ax=15.0,        # N s/m
    k_lat=2500.0,     # N/m    bellows lateral stiffness
    d_lat=8.0,        # N s/m
    k_tilt=3.0,       # N m/rad
    k_tor=5.0,        # N m/rad
    d_rot=0.01,       # N m s/rad
    mu=0.5,           # lip friction on cardboard
    V_cup=2.0e-5,     # m^3    cup chamber
    A_lip0=3.0e-8,    # m^2    sealed-lip roughness leak (about a 0.2 mm hole)
)
#: cup centres in the gripper frame G (2 x 3, long side along G x); cup 1..6
PX, PY = 0.18, 0.08
CUPS = [(-PX, PY), (-PX, -PY), (0.0, PY), (0.0, -PY), (PX, PY), (PX, -PY)]

#: air permeance of the parcel material, m/(s Pa): flow per cup = perm * A_eff * vacuum
PERM = {"sealed": 0.0, "cardboard": 4.0e-7, "porous": 2.0e-6}

# ------------------------------------------------------------------ vacuum supply
SUPPLY = dict(
    dp_max=6.0e4,     # Pa     ejector end vacuum
    Q_max=1.0e-3,     # m^3/s  60 l/min free air at zero vacuum
    n_gen=1.0,        # linear (ejector) curve
    V_man=1.0e-4,     # m^3    manifold and hoses
    A_line=7.0e-6,    # m^2    3 mm line per cup
    r_rev=1.0,        # no check valves
    dp_close=1.0e9,   # no flow valves
    bleed=0.02,
)

# ------------------------------------------------------------------ motion
MOTION = dict(
    L_move=1.0,       # m      transfer length (world x)
    H_lift=0.15,      # m      lift and lower height
    d_press=0.002,    # m      press depth at the place position
    H_ret=0.10,       # m      retract after the release
    a_lift=2.5, v_lift=0.6, j_lift=40.0,   # lift / lower S-curve (m/s^2, m/s, m/s^3)
    t_lift=0.35,      # s      lift start (the vacuum valve opens at t = 0)
    dwell=0.05,       # s      pause between the segments
    T_move=1.75,      # s      transfer time (the shortest safe S-curve move for cardboard, design.py)
    kind=2.0,         # 1 trapezoid, 2 S-curve, 3 polynomial 3-4-5, 4 cycloidal
    lam=0.3,          # S-curve: jerk phase as a fraction of the acceleration phase
    psi=0.0,          # rad    yaw of the cup pattern relative to the path
    k_tilt=0.0,       # tilt gain (waiter's tray)
    th_max=0.35,      # rad    largest tilt
    w_tilt=15.0,      # rad/s  tilt servo bandwidth (critically damped, previewed by 2/w_tilt)
)

SAFETY = 2.0          # required safety factor on the holding capacity (U <= 1/S)

# Floor (table) contact under the parcel corners.
FLOOR = dict(k=2.0e5, xref=1.0e-3, c=5.0, mu=0.5, vs=1.0e-3)


def scurve_time(dist: float, v: float, a: float, j: float) -> float:
    """Duration of the stdlib SCurveProfile move (same formulas as the block)."""
    a_v = min(a, math.sqrt(v * j))
    dist_v = v * (a_v / j + v / a_v)
    if dist >= dist_v:
        a_peak, v_peak = a_v, v
    else:
        a_peak = min(a, (dist * j * j / 2.0) ** (1.0 / 3.0))
        tj = a_peak / j
        v_peak = a_peak * (math.sqrt(tj * tj + 4.0 * dist / a_peak) - tj) / 2.0
    t_acc = a_peak / j + v_peak / a_peak
    t_cruise = max(dist / v - t_acc, 0.0) if dist >= dist_v else 0.0
    return 2.0 * t_acc + t_cruise


def rest_penetration(load: float) -> float:
    """Corner penetration of the ContactPoint law k x sqrt(x/xref) = load."""
    return (load / FLOOR["k"] * math.sqrt(FLOOR["xref"])) ** (2.0 / 3.0)


#: peak acceleration of each transfer profile as a multiple of L/T^2 (S-curve with ``lam``)
def peak_coeff(kind: int, lam: float = MOTION["lam"]) -> float:
    return {1: 4.5, 2: 4.5 / (1.0 - lam), 3: 5.773502691896258, 4: 2.0 * math.pi}[kind]


PROFILE_NAMES = {1: "trapezoidal", 2: "S-curve", 3: "polynomial 3-4-5", 4: "cycloidal"}
