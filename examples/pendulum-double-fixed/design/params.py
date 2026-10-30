"""Parameters of pendulum-double-fixed: the plant, the scenario and the controller design settings.

Used by design.py (controller tables) and build_model.py (model documents).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import numpy as np

from pendulum_common import Plant

EXAMPLE = "pendulum-double-fixed"
CTRL_BLOCK = "DoublePendCtrl"

# Two aluminium rods of different length (link 1 is the motor-driven one, link 2 the free tip link).
# The COM is at the rod middle and the yaw inertia is m L^2 / 12. The joint friction is the bearing
# friction (viscous). The motor is a small coreless DC gearmotor (assumed values, no datasheet part).
PLANT = Plant(
    name="double",
    m=(0.22, 0.14),
    L=(0.30, 0.36),
    lc=(0.15, 0.18),
    b=(0.002, 0.0008),
    N=5.0,
    kt=0.030,
    Rw=2.5,
    Lw=5.0e-4,
    Jm=5.0e-6,
    bm=0.0,
    ks=5.0e3,
    ds=0.2,
    umax=12.0,
)

CFG = dict(
    t_on=1.0,  # swing-up starts (s)
    T_s=2.5,  # swing-up duration of the optimised trajectory (s)
    nk=100,  # collocation intervals
    u_to=11.0,  # voltage limit of the optimisation (V), the rest of the 12 V is the feedback margin
    dt_tab=0.01,  # spacing of the controller tables (s)
    Q=np.diag([100.0, 100.0, 1.0, 1.0]),  # LQR / TVLQR state weights, x = [q1, q2, qd1, qd2]
    R=1.0,  # input weight (1/V^2)
    catch_before_end=0.2,  # V_catch is V(x_nominal) this long before the end of the trajectory (s)
    hold=3.5,  # stable balance before the disturbance (s) (>= 3 s)
    F=0.4,  # tip force of the disturbance (N)
    pulse_len=0.05,  # duration of the force pulse (s)
    pulse_period=100.0,  # Pulse source period (only one pulse in the run)
    settle=3.0,  # simulation after the recovery (s)
    recovery=0.5,  # allowance for the recovery after the pulse (s)
    bt=2000.0,  # pivot translational damping of the compliant revolute (N s/m)
    free_q0=(-math.pi / 2 + 1.2, 1.0),  # initial joint angles of the free-swing check
    free_t_end=3.0,
    free_points=3001,
    points=5251,
    scene="pendulum-double-fixed",
)
CFG["t_dist"] = CFG["t_on"] + CFG["T_s"] + CFG["hold"]
CFG["t_end"] = round(CFG["t_dist"] + CFG["pulse_len"] + CFG["recovery"] + CFG["settle"], 3)
