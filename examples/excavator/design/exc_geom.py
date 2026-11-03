"""Excavator front geometry, kinematics and statics (the independent Python reference).

Planar, world x forward and y up, origin at the boom foot pin O. Joint frames:

* boom:   origin O, x along O -> C (the arm pin), absolute angle q1;
* arm:    origin C, x along C -> Q (the bucket pin), angle q2 relative to the boom line;
* bucket: origin Q, x along Q -> T (the tooth tip), angle q3 relative to the arm line.

Every attachment point is a constant in the frame of the body that carries it, so every
cylinder length is a kinematic result of the joint angles (and the bucket cylinder one of the
four-bar closure). Used by design.py (references, expected.json) and build_model.py (the
model parameters), so the two can never disagree on a number.
"""

from __future__ import annotations

import math

import numpy as np

# --------------------------------------------------------------------------- geometry (m)
L1, L2, L3 = 5.70, 2.90, 1.50          # boom O->C, arm C->Q, bucket Q->T
GEOM = {
    "A1": (0.104, -0.844),             # boom cylinder base pin, base frame
    "B1": (2.59, -0.227),              # boom cylinder rod pin, boom frame (underside)
    "A2": (2.75, 1.05),                # arm cylinder base pin, boom frame (top of the boom)
    "B2": (-0.80, -0.32),              # arm cylinder rod pin, arm frame (the arm tail)
    "A3": (0.277, 0.478),              # bucket cylinder base pin, arm frame
    "R": (2.54, 0.052),                # rocker (side link) pivot, arm frame
    "P": (0.193, 0.359),               # bucket link pin, bucket frame
    "lr": 0.725,                       # rocker R -> J
    "lc": 0.714,                       # H-link J -> P
}
FOUR_BAR_BRANCH = 1.0                  # J on the +y side of R->P

# ground and machine
Y_GROUND = -1.95                       # the track ground / soil surface, below the boom foot


def rot(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s], [s, c]])


def frames(q1: float, q2: float, q3: float) -> dict:
    """World origin and absolute angle of each joint frame."""
    O = np.zeros(2)
    a1 = q1
    C = O + rot(a1) @ np.array([L1, 0.0])
    a2 = a1 + q2
    Q = C + rot(a2) @ np.array([L2, 0.0])
    a3 = a2 + q3
    T = Q + rot(a3) @ np.array([L3, 0.0])
    return {"O": O, "a1": a1, "C": C, "a2": a2, "Q": Q, "a3": a3, "T": T}


def world(origin, angle, p) -> np.ndarray:
    return np.asarray(origin) + rot(angle) @ np.asarray(p, float)


def four_bar(q3: float) -> dict:
    """Bucket four-bar in the arm frame for the bucket angle q3: the link pin P, the
    rocker/H-link junction J, the rocker angle phi (of R->J) and k = dphi/dq3."""
    Q = np.array([L2, 0.0])
    R = np.array(GEOM["R"])
    P = Q + rot(q3) @ np.array(GEOM["P"])
    lr, lc = GEOM["lr"], GEOM["lc"]
    d = P - R
    dist = float(np.hypot(*d))
    a = (lr * lr - lc * lc + dist * dist) / (2 * dist)
    h2 = lr * lr - a * a
    if h2 < 0:
        raise ValueError(f"four-bar does not close at q3 = {q3}")
    h = math.sqrt(h2)
    e = d / dist
    n = np.array([-e[1], e[0]])
    J = R + a * e + FOUR_BAR_BRANCH * h * n
    phi = math.atan2(J[1] - R[1], J[0] - R[0])
    kz = lambda r: np.array([-r[1], r[0]])          # k x r
    JP = J - P
    k = float(JP @ kz(P - Q)) / float(JP @ kz(J - R))
    # transmission angle between the H-link and the rocker
    u, v = (J - R) / lr, (P - J) / lc
    mu = math.degrees(math.acos(max(-1.0, min(1.0, float(-u @ v)))))
    return {"P": P, "J": J, "phi": phi, "k": k, "mu": mu}


def cylinder(A, B, J):
    """Length, unit vector A->B and moment arm dL/dtheta of a cylinder whose end B turns
    about the pivot J relative to the body that carries A (all in one frame)."""
    A, B, J = map(np.asarray, (A, B, J))
    d = B - A
    L = float(np.hypot(*d))
    n = d / L
    r = B - J
    return L, n, float(-n[0] * r[1] + n[1] * r[0])


def cylinders(q1: float, q2: float, q3: float) -> dict:
    """World cylinder ends, lengths and moment arms (dL1/dq1, dL2/dq2, dL3/dq3)."""
    f = frames(q1, q2, q3)
    A1 = np.array(GEOM["A1"])
    B1 = world(f["O"], f["a1"], GEOM["B1"])
    L1c, _, r1 = cylinder(A1, B1, f["O"])
    A2 = world(f["O"], f["a1"], GEOM["A2"])
    B2 = world(f["C"], f["a2"], GEOM["B2"])
    L2c, _, r2 = cylinder(A2, B2, f["C"])
    fb = four_bar(q3)
    A3 = world(f["C"], f["a2"], GEOM["A3"])
    J = world(f["C"], f["a2"], fb["J"])
    Rw = world(f["C"], f["a2"], GEOM["R"])
    L3c, _, rr = cylinder(A3, J, Rw)
    return {"L": (L1c, L2c, L3c), "r": (r1, r2, rr * fb["k"]), "r_rocker": rr, "k": fb["k"],
            "ends": {"A1": A1, "B1": B1, "A2": A2, "B2": B2, "A3": A3, "J": J, "R": Rw,
                     "P": world(f["C"], f["a2"], fb["P"])},
            "frames": f, "mu": fb["mu"]}
