"""Parameters of the suction-cup example, shared by the model builder, the scene and the analysis.

Every value here becomes a global parameter of the models (``build_model.py``), so the editor's
Equations manager, the dashboard and ``analysis.py`` all change the same numbers.

One bellows suction cup (the 1.5-fold, 32 mm cup of the fanuc-pick example, with the nonlinear
bellows of ``stdlib:contact/SuctionCup`` switched on) hangs from a tool that follows a prescribed
motion and carries a small box.
"""

from __future__ import annotations

import math

G0 = 9.81
P_ATM = 101325.0

# ------------------------------------------------------------------ the cup (fanuc-pick's cup)
CUP = dict(
    L0=0.030,         # m      mount-to-lip rest length
    A_eff=5.0e-4,     # m^2    effective suction area (25 mm effective diameter)
    D_lip=0.032,      # m      lip diameter
    k_ax=2500.0,      # N/m    bellows axial stiffness
    d_ax=8.0,         # N s/m
    k_lat=1500.0,     # N/m    bellows lateral stiffness
    d_lat=5.0,        # N s/m
    k_tilt=1.0,       # N m/rad
    k_tor=1.5,        # N m/rad
    d_rot=0.005,      # N m s/rad
    mu=0.5,           # lip friction on the box surface
    V_cup=8.0e-6,     # m^3    cup chamber and hose
    A_lip0=1.5e-8,    # m^2    sealed-lip roughness leak
    F_min=0.1,        # N      residual friction capacity of a free lip
    # nonlinear bellows. ESTIMATES for a 1.5-fold bellows cup with a 32-33 mm lip (the class of
    # e.g. Schmalz FSGA 33 / Piab BL30-2), as in examples/fanuc-pick
    s_bot=0.006,      # m      compression stroke before the folds bottom
    k_bot=2.5e4,      # N/m    bottoming stiffness scale
    n_bot=3.0,        # 1      bottoming exponent
    x_bot=1.0e-3,     # m      reference over-stroke
    A_fold=1.7e-4,    # m^2    folded annulus: lift stroke A_fold dp / k_ax
    c_vac=1.0,        # 1      lateral/tilt stiffness x (1 + c_vac dp/p_atm)
    c_ext=3.0,        # 1      lateral/tilt stiffness x exp(-c_ext ext/L0)
)
#: the nonlinear bellows parameters (0 for k_bot, A_fold, c_vac, c_ext gives the linear cup)
CUP_NL = ("s_bot", "k_bot", "n_bot", "x_bot", "A_fold", "c_vac", "c_ext")
LINEAR_OFF = {"k_bot": 0.0, "A_fold": 0.0, "c_vac": 0.0, "c_ext": 0.0}

# ------------------------------------------------------------------ vacuum: one compact ejector
VACUUM = dict(
    dp_max=6.0e4,     # Pa     ejector end vacuum (the "vacuum level" slider)
    Q_max=2.0e-4,     # m^3/s  12 l/min free air
    G_rel=2.0e-7,     # m^3/(s Pa) release (vent) conductance
    perm=0.0,         # m/(s Pa) the box surface is sealed (coated carton, plastic)
)

# ------------------------------------------------------------------ payload: a small flat box
BOX = dict(m_p=0.6, L_p=0.12, W_p=0.12, H_p=0.04, cx=0.0, cy=0.0, cz=0.0)

#: the box on the table (four corner contacts)
FLOOR = dict(k=2.0e5, xref=1.0e-3, c=5.0, mu=0.5, vs=1.0e-3)

# ------------------------------------------------------------------ motion
MOTION = dict(
    motion=1.0,       # 1 hold, 2 vertical bounce, 3 horizontal steps, 4 tilt swing, 5 lateral chirp
    H_lift=0.06,      # m      lift height after the pick (and lower height at the place)
    v_lift=0.4, a_lift=3.0, j_lift=60.0,   # lift / lower S-curve
    t_lift=0.40,      # s      lift start (the vacuum is on from t = 0)
    T_exc=1.0,        # s      length of the excitation window (set per motion)
    # 2: vertical bounce: a quick step down (ring-down of the axial mode), then a chirp
    A_st=0.004, T_st=0.04,          # m, s   step size and duration
    T_ring=0.8,                     # s      free ring-down after the step
    A_z=1.7e-3, f0_z=3.0, f1_z=20.0, T_cz=5.0,   # m, Hz, Hz, s   vertical chirp
    # 3: horizontal acceleration steps (three moves, rising acceleration, alternating direction)
    a_s=4.5, T_p=0.15, T_c=0.60, tau_s=0.008,     # m/s^2, s, s, s
    # 4: tilt swing about the cup mount (quasi-static to th_A and back, then a fast swing)
    th_A=30.0, T_sw=0.8, T_h=0.6,   # deg, s, s
    th_B=10.0, f_sw=1.5, N_sw=3.0,  # deg, Hz, cycles
    # 5: lateral chirp (transmissibility)
    A_x=4.0e-4, f0_x=1.5, f1_x=20.0, T_cx=10.0,  # m, Hz, Hz, s
    a0=0.3,           # 1      start amplitude of a chirp as a share of its end amplitude
    T_env=0.25,       # s      chirp fade-in/out
    w_lp=6.0,         # rad/s  low-pass of the transmissibility demodulator (two poles)
)


MOTION_NAMES = {1: "hold", 2: "vertical bounce", 3: "horizontal steps", 4: "tilt swing", 5: "lateral chirp"}


def rest_penetration(mass: float) -> float:
    """Corner penetration of the ContactPoint law k x sqrt(x/xref) = m g / 4."""
    f = mass * G0 / 4.0
    return (f * math.sqrt(FLOOR["xref"]) / FLOOR["k"]) ** (2.0 / 3.0)
