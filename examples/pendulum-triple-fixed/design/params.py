"""Parameters of pendulum-triple-fixed: the plant, the scenario and the controller design settings.

Used by design.py (controller tables) and build_model.py (model documents). The plant extends
pendulum-double-fixed with a third link of similar construction (a lighter, longer tip rod).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parents[1] / "pendulum-double-fixed" / "design"))

import numpy as np

from pendulum_common import Plant

EXAMPLE = "pendulum-triple-fixed"
CTRL_BLOCK = "TriplePendCtrl"

PLANT = Plant(
    name="triple",
    m=(0.22, 0.14, 0.10),
    L=(0.26, 0.30, 0.34),
    lc=(0.13, 0.15, 0.17),
    b=(0.002, 0.0008, 0.0006),
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
    t_on=1.0,
    T_s=3.5,
    nk=140,
    u_to=11.0,
    dt_tab=0.01,
    Q=np.diag([100.0, 100.0, 100.0, 1.0, 1.0, 1.0]),  # x = [q1, q2, q3, qd1, qd2, qd3]
    R=1.0,
    catch_before_end=0.2,
    hold=3.5,
    F=0.1,
    pulse_len=0.05,
    pulse_period=100.0,
    settle=3.0,
    recovery=1.2,
    bt=2000.0,
    free_q0=(-math.pi / 2 + 1.2, 0.8, -0.6),
    free_t_end=3.0,
    free_points=3001,
    points=5251,
    scene="pendulum-triple-fixed",
)
CFG["t_dist"] = CFG["t_on"] + CFG["T_s"] + CFG["hold"]
CFG["t_end"] = round(CFG["t_dist"] + CFG["pulse_len"] + CFG["recovery"] + CFG["settle"], 3)
