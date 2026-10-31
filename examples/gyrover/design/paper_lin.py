# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "sympy>=1.13"]
# ///
"""Our linearisation in the paper's coordinates, and the paper's controllers on it.

The paper (Tsai, Ferreira and Paredis, IROS 1999, section 4.1) linearises about the upright
rest with the flywheel at a constant 15 000 rpm, and models the tilt actuator as a servo
(its eq. 7). This module builds the same two subsystems from our nonlinear model:

* the flywheel speed is held (the spin torque that keeps ``w3`` constant is eliminated);
* the tilt follows the servo ``w2' = wc^2 (u2 - theta2) - sqrt(2) wc w2`` (the tilt torque
  that produces this acceleration is eliminated);

and returns ``A1, B1`` (states theta1, w1, omega0z; input tau1) and ``A2, B2`` (states
theta0, theta2, w2, omega0x, omega0y; input u2) in the paper's signs (``design.S*``).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import design as d  # noqa: E402

SQ2 = np.sqrt(2.0)

# The paper's matrices and gains (section 4.1); u = +K x.
A1_PAPER = np.array([[0, 1, 1], [-44.32, 0, 0], [-11.91, 0, 0]])
B1_PAPER = np.array([0, 14.52, -0.37])
A2_PAPER = np.array([
    [0, 0, 0, 1, 0],
    [0, 0, 1, 0, 0],
    [0, -400 * np.pi**2, -88.86, 0, 0],
    [51.5, -49.3, 6.5, -8.7, 23.37],
    [19.17, -28.3, 102.5, -103.7, 8.7],
])
B2_PAPER = np.array([0, 0, 400 * np.pi**2, 49.3, 28.3])
K1_PAPER = np.array([-18.44, -3.31, 1.16])
K2_PAPER = np.array([-0.0077, 1.001, 0.0019, 0.0179, -0.0022])


def full_linear(p):
    """x = (q1..q5, u1..u5), inputs (tau1, a2); flywheel held, tilt acceleration a2 prescribed."""
    Aq, Au, Bt = d.linearise(p)
    # rows 4 (th2'') and 5 (w3') of u' = Aq q + Au u + Bt tau, solved for (tau2, tau3)
    # with u5' = a2 and u6' = 0; u6 itself is the constant flywheel speed (deviation 0).
    Bs = Bt[[4, 5]][:, [1, 2]]
    Binv = np.linalg.inv(Bs)
    # tau23 = Binv ([a2, 0] - Aq[45] q - Au[45,:5] u - Bt[45,0] tau1)
    Tq = -Binv @ Aq[[4, 5]]
    Tu = -Binv @ Au[[4, 5]][:, :5]
    T1 = -Binv @ Bt[[4, 5], 0]
    Ta = Binv @ np.array([1.0, 0.0])
    Aqq = Aq[:5] + Bt[:5, 1:] @ Tq
    Auu = Au[:5, :5] + Bt[:5, 1:] @ Tu
    B1 = Bt[:5, 0] + Bt[:5, 1:] @ T1
    Ba = Bt[:5, 1:] @ Ta
    A = np.zeros((10, 10))
    A[:5, 5:] = np.eye(5)
    A[5:, :5] = Aqq
    A[5:, 5:] = Auu
    B = np.zeros((10, 2))
    B[5:, 0] = B1
    B[5:, 1] = Ba
    return A, B


def paper_matrices(p, signs=None):
    s0, s2, sy, sp_, st = signs if signs is not None else (d.S0, d.S2, d.SY, d.SP, d.ST)
    A, B = full_linear(p)
    # our state order: psi phi gamma beta th2 | u1 u2 u3 u4 u5
    # longitudinal: theta1 = sp beta, w1 = sp (u4 - u3), omega0z = sp u3 ; tau1_paper = st tau1
    T = np.array([
        [0, 0, 0, sp_, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, -sp_, sp_, 0],
        [0, 0, 0, 0, 0, 0, 0, sp_, 0, 0],
    ], float)
    # A1 = T A T^+ restricted to the longitudinal states (they are decoupled at rest)
    idx = [3, 7, 8]
    Tl = T[:, idx]
    A1 = Tl @ A[np.ix_(idx, idx)] @ np.linalg.inv(Tl)
    B1 = Tl @ B[idx, 0] * st
    # lateral: theta0 = s0 phi, theta2 = s2 th2, w2 = s2 u5, omega0x = s0 u2, omega0y = sy u1
    idx2 = [1, 4, 9, 6, 5]
    Tw = np.diag([s0, s2, s2, s0, sy]).astype(float)
    Alat = A[np.ix_(idx2, idx2)]
    Blat = B[idx2, 1]
    # the servo: a2 = wc^2 (u2 - th2) - sqrt2 wc th2'  (u2 in the paper's tilt sign)
    servo = np.zeros(5)
    servo[1] = -d.WC**2
    servo[2] = -SQ2 * d.WC
    Alat = Alat + np.outer(Blat, servo)
    Blat = Blat * d.WC**2
    A2 = Tw @ Alat @ np.linalg.inv(Tw)
    B2 = Tw @ Blat * s2
    return A1, B1, A2, B2


def report(p, signs=None):
    np.set_printoptions(precision=3, suppress=True, linewidth=160)
    A1, B1, A2, B2 = paper_matrices(p, signs)
    print("A1 ours\n", A1, "\nA1 paper\n", A1_PAPER)
    print("B1 ours", B1, " paper", B1_PAPER)
    print("A2 ours\n", A2, "\nA2 paper\n", A2_PAPER)
    print("B2 ours", B2, " paper", B2_PAPER)
    print("open loop long ", np.sort_complex(np.linalg.eigvals(A1)))
    print("open loop lat  ", np.sort_complex(np.linalg.eigvals(A2)))
    print("closed loop long (paper K1)", np.sort_complex(np.linalg.eigvals(A1 + np.outer(B1, K1_PAPER))))
    print("   paper model             ", np.sort_complex(np.linalg.eigvals(A1_PAPER + np.outer(B1_PAPER, K1_PAPER))))
    print("closed loop lat (paper K2)", np.sort_complex(np.linalg.eigvals(A2 + np.outer(B2, K2_PAPER))))
    print("   paper model            ", np.sort_complex(np.linalg.eigvals(A2_PAPER + np.outer(B2_PAPER, K2_PAPER))))


if __name__ == "__main__":
    report(d.PARAMS)
