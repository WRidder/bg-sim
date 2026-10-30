# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "casadi>=3.6", "matplotlib>=3.8", "httpx>=0.28"]
# ///
"""Design of `pendulum-double-rotary` (X5.13): a Quanser-style rotary double inverted pendulum.

    uv run examples/pendulum-double-rotary/design/design.py [--plot]

Writes `design/design.json`; then `uv run examples/pendulum-double-rotary/design/build_model.py`
turns it into the model, the controller block and the scene. The method is in `rotary_design.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import rotary_design as rd  # noqa: E402

CFG = {
    "example": "pendulum-double-rotary",
    "t_on": 1.0,
    "t_s": 4.0,
    "stable_s": 3.5,
    "after_s": 3.5,
    "vmax_steps": [10.0, 9.0],
    "refine": [160, 320],
    "theta_max": 2.0,
    "nk": 80,
    "rate_weight": 0.05,
    "smooth": 0.2,
    "guess_amp": 6.0,
    "guess_freq": 1.0,
    "dt_tab": 0.01,
    # state weights [arm, link1, link2, rates]; R in 1/V^2
    "qdiag": [5.0, 200.0, 200.0, 1.0, 2.0, 2.0],
    "r": 0.2,
    "r_tv": 0.2,
    "catch_w": [1.0, 1.0, 1.0, 0.1, 0.1, 0.1],
    "catch_tol": 0.5,
    "dist_force": 0.35,
    "dist_duration": 0.05,
    "free_start": [0.25, 2.4, -0.9],
    "t_free": 3.0,
    "comment": (
        "X5.13: Quanser-style rotary double inverted pendulum on the spatial multibond stdlib. World -> Mount -> J1 "
        "(Revolute3D about world z, the arm) -> arm bar (RigidBody3D) -> J2 (Revolute3D about the arm axis, the "
        "lower link) -> J3 (upper link), every body a RigidBody3D with a distributed mass (COM at the bar middle). "
        "The arm is driven by an SRV02-like servo: Motor (ElectricDrive, voltage input) -> Shaft (ElasticShaft) -> "
        "Gear (IdealGear, 70:1) -> J1.drive. The 1 kHz firmware Ctrl (phases: idle, TVLQR swing-up along the "
        "collocation trajectory, latched LQR balance) reads the joint angles and rates. Dist is a force pulse on the "
        "tip of the upper link. Joint compliance kt = kr = 1e6 (N/m, N m/rad); every state is integral."
    ),
    "comment_free": (
        "X5.13 design check: the same bond graph released at rest from a non-trivial pose with the controller "
        "disabled (t_on far in the future, no disturbance). design.py integrates its Lagrangian model from the same "
        "pose; expected.json compares the link angles."
    ),
}

if __name__ == "__main__":
    rd.run(HERE.parent, 2, CFG, sys.argv[1:])
