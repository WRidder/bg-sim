"""The bg-sim side of the Beaver: principal axes and start values of the multibond rigid body.

The FDC state x = [V alpha beta p q r psi theta phi xe ye H] (body FRD, Euler angles of a
north-east-down world) becomes the starts of `stdlib:spatial/Free3D` (pose of the principal frame P
in the bg-sim world: x north, y west, z up) and of `stdlib:spatial/RigidBody3D` (momentum in P).
"""

from __future__ import annotations

import math

import numpy as np

import beaver_data as D

MASS = D.MASS
G0 = 9.80665       # the rigid body's uniform gravity; BeaverWrench adds m (g(H) - G0)


def principal_axes():
    """Inertia in the geometric body frame B (x forward, y left, z up): the FRD tensor
    [[Ix, 0, -Jxz], [0, Iy, 0], [-Jxz, 0, Iz]] becomes [[Ix, 0, Jxz], [0, Iy, 0], [Jxz, 0, Iz]] in FLU.
    Returns (J principal, eps, R_BP): B = R_y(eps) P."""
    I_b = np.array([[D.IX, 0.0, D.JXZ], [0.0, D.IY, 0.0], [D.JXZ, 0.0, D.IZ]])
    eps = 0.5 * math.atan2(2.0 * D.JXZ, D.IZ - D.IX)
    c, s = math.cos(eps), math.sin(eps)
    R = np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])
    Jp = R.T @ I_b @ R
    assert abs(Jp[0, 2]) < 1e-9 * D.IZ
    return np.array([Jp[0, 0], Jp[1, 1], Jp[2, 2]]), eps, R


J_PRINCIPAL, EPS, R_BP = principal_axes()
Q_BP = np.array([math.cos(EPS / 2), 0.0, math.sin(EPS / 2), 0.0])


def quat_mul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
                     w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                     w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def quat_from_euler_ned(phi, theta, psi):
    """Quaternion of R_WB for the bg-sim world (x north, y west, z up) and body FLU from NED/FRD
    Euler angles: the NED quaternion (w, x, y, z) becomes (w, x, -y, -z)."""
    cphi, sphi = math.cos(phi / 2), math.sin(phi / 2)
    cth, sth = math.cos(theta / 2), math.sin(theta / 2)
    cpsi, spsi = math.cos(psi / 2), math.sin(psi / 2)
    w = cphi * cth * cpsi + sphi * sth * spsi
    x = sphi * cth * cpsi - cphi * sth * spsi
    y = cphi * sth * cpsi + sphi * cth * spsi
    z = cphi * cth * spsi - sphi * sth * cpsi
    return np.array([w, x, -y, -z])


def starts(x):
    """Free3D pose starts and RigidBody3D momentum starts for the FDC state x (no wind)."""
    V, alpha, beta, p, q, r, psi, theta, phi, xe, ye, H = [float(v) for v in x[:12]]
    q_wp = quat_mul(quat_from_euler_ned(phi, theta, psi), Q_BP)
    u = V * math.cos(alpha) * math.cos(beta)
    v = V * math.sin(beta)
    w = V * math.sin(alpha) * math.cos(beta)
    v_p = R_BP.T @ np.array([u, -v, -w])
    w_p = R_BP.T @ np.array([p, -q, -r])
    P = np.concatenate([J_PRINCIPAL * w_p, MASS * v_p])
    pose = {"qw": q_wp[0], "qx": q_wp[1], "qy": q_wp[2], "qz": q_wp[3], "px": xe, "py": -ye, "pz": H}
    return {k: float(v) for k, v in pose.items()}, [float(v) for v in P]
