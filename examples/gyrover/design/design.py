# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "sympy>=1.13"]
# ///
"""Parameters, numeric equations of motion and controller design of the `gyrover` example.

Reference: S.-J. Tsai, E. D. Ferreira and C. J. J. Paredis, *Control of the Gyrover, a
single-wheel gyroscopically stabilized robot*, IEEE/RSJ IROS 1999 (the "paper" below).

The paper gives the linearised dynamics about the upright rest, the tilt-servo model and the
two state-feedback gains, but no masses or inertias. ``PARAMS`` holds a physical parameter set
chosen by hand so that the linearisation of our own rolling model (``eom.py``)
reproduces the paper's matrices ``A1, B1, A2, B2``: a few entries of those matrices fix the
wheel radius, the first and second moments of the pendulum and the flywheel momentum, the rest
was set to plausible values (``paper_lin.py`` prints the comparison; docs page "Parameters").

Paper coordinates (section 2, table 1), expressed in ours (``eom.py``):

    theta0 - pi/2 = S0 * phi            lean, measured from upright
    omega0x       = S0 * phi'           roll rate
    omega0y       = SY * psi' cos(phi)  yaw rate (wheel-frame component)
    omega0z       = SP * (gamma' + psi' sin(phi))   wheel rate about the axle
    theta1        = SP * beta           pendulum swing in the lean frame
    w1            = SP * (beta' - gamma')           pendulum rate relative to the wheel
    theta2        = S2 * th2, w2 = S2 * th2'        tilt angle and rate
    tau1 (paper)  = ST * tau1 (ours)

Run ``uv run examples/gyrover/design/design.py`` to print the linearisation, the paper's
closed-loop poles on our model and the steady-turn table.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

G0 = 9.81
RPM = 2 * np.pi / 60
W3 = 15000 * RPM                    # flywheel speed relative to the gimbal (paper: about 15 000 rpm)
WC = 20 * np.pi                     # tilt servo bandwidth (paper eq. 7)

# Mass properties chosen so that our linearisation reproduces the paper's
# A1, B1 to about 1 % (B1[3]: 5 %) and A2, B2 to 5-17 %, except the tilt coupling of the yaw row
# (-16.5 against the paper's -28.3); docs page "Parameters".
PARAMS = dict(
    R=0.197, m_w=2.0, Jwa=0.0249, Jwt=0.0146,
    m_p=3.417, l_p=0.0939, a_p=0.7853981633974483, Jp1=0.0371, Jp2=0.0353, Jp3=0.0091,
    m_g=0.4, l_g=0.0, Jg1=8.7e-4, Jg2=6.0e-4, Jg3=7.0e-4,
    m_r=1.2, Jra=3.01e-3, Jrt=1.66e-3,
    g0=G0, bsp=0.0,
)

# Sign map between the paper's coordinates and ours (paper_lin.py picks it: the only one of the
# eight lateral combinations for which the paper's gain K2 stabilises our model).
S0, S2, SY, SP, ST = 1, -1, 1, 1, 1


@lru_cache(maxsize=1)
def _numeric():
    import sympy as sp

    import eom

    e = eom.derive()
    args = list(e["q"]) + list(e["u"]) + list(e["tau"]) + e["params"]
    M = sp.lambdify(args, e["M"], "numpy")
    f = sp.lambdify(args, e["f"], "numpy")
    vO = sp.lambdify(args, list(e["vO"]), "numpy")
    ke = sp.lambdify(args, e["ke"], "numpy")
    pe = sp.lambdify(args, e["pe"], "numpy")
    return M, f, vO, ke, pe


def pvec(p):
    import eom

    return [p[n] for n in eom.PARAM_NAMES]


def rhs(x, tau, p):
    """x = (psi, phi, gamma, beta, th2, u1..u6, xO, yO); returns dx/dt."""
    M, f, vO, _, _ = _numeric()
    args = list(x[:11]) + list(tau) + pvec(p)
    ud = np.linalg.solve(np.asarray(M(*args), float), np.asarray(f(*args), float).ravel())
    vx, vy = vO(*args)
    return np.concatenate([x[5:10], ud, [vx, vy]])


def energy(x, p):
    _, _, _, ke, pe = _numeric()
    args = list(x[:11]) + [0.0, 0.0, 0.0] + pvec(p)
    return float(ke(*args)), float(pe(*args))


def linearise(p, x0=None, h=1e-6):
    """Jacobians of u' about the upright rest: Aq (6x5), Au (6x6), Bt (6x3)."""
    if x0 is None:
        x0 = np.zeros(13)
        x0[10] = W3
    tau0 = np.zeros(3)
    base = lambda x, t: rhs(x, t, p)[5:11]
    Aq = np.zeros((6, 5))
    Au = np.zeros((6, 6))
    Bt = np.zeros((6, 3))
    for j in range(5):
        e = np.zeros(13); e[j] = h
        Aq[:, j] = (base(x0 + e, tau0) - base(x0 - e, tau0)) / (2 * h)
    for j in range(6):
        e = np.zeros(13); e[5 + j] = h
        Au[:, j] = (base(x0 + e, tau0) - base(x0 - e, tau0)) / (2 * h)
    for j in range(3):
        e = np.zeros(3); e[j] = h
        Bt[:, j] = (base(x0, tau0 + e) - base(x0, tau0 - e)) / (2 * h)
    return Aq, Au, Bt


def turn_constants(p=PARAMS, w3=W3):
    """(mgh, H, mh) of the small-angle steady turn psi' = -mgh tan(phi) / (H + mh v).

    mgh is the gravity moment per unit lean (whole robot about the contact line), H the
    flywheel's spin momentum, and mh v the centrifugal term plus the wheel's own spin
    momentum, (m_tot h + Jwa / R) v. The docs page "Steady turn" derives it.
    """
    m_tot = p["m_w"] + p["m_p"] + p["m_g"] + p["m_r"]
    mh0 = m_tot * p["R"] - p["m_p"] * p["l_p"] - (p["m_g"] + p["m_r"]) * p["l_g"]
    return p["g0"] * mh0, p["Jra"] * w3, mh0 + p["Jwa"] / p["R"]


def turn_rate_approx(phi, v, theta2=0.0, p=PARAMS, w3=W3):
    """Steady-turn heading rate from the lean-moment balance about the contact line:

        mgh sin(phi) + psi' (H cos(phi - theta2) + mh v cos(phi)) = 0

    (theta2 in the paper's sign; the terms in psi'^2 of the transverse inertias are dropped).
    """
    mgh, H, mh = turn_constants(p, w3)
    return -mgh * np.sin(phi) / (H * np.cos(phi + S2 * theta2) + mh * v * np.cos(phi))


def steady_turn(phi, v, theta2=0.0, p=PARAMS, w3=W3):
    """Exact steady turn of the reference model: lean phi, speed v (m/s), tilt held at theta2
    (paper sign) by its actuator.

    Unknowns: heading rate psi', pendulum pitch beta, drive torque tau1 and tilt torque tau2.
    Equations: psi'' = phi'' = gamma'' = beta'' = th2'' = 0, solved by least squares (five
    equations, four unknowns; the residual is returned and printed by ``__main__``).
    """
    from scipy.optimize import least_squares

    M, f, _, _, _ = _numeric()
    th = S2 * theta2

    def acc(z):
        psid, beta, tau1, tau2 = z
        gd = v / p["R"] - psid * np.sin(phi)
        x = [0.0, phi, 0.0, beta, th, psid, 0.0, gd, 0.0, 0.0, w3]
        args = x + [tau1, tau2, 0.0] + pvec(p)
        return np.linalg.solve(np.asarray(M(*args), float), np.asarray(f(*args), float).ravel())[:5]

    guess = turn_rate_approx(phi, v, theta2, p, w3)
    res = least_squares(acc, [guess, 0.0, 0.0, 0.0], xtol=1e-15, ftol=1e-15, gtol=1e-15)
    psid, beta, tau1, tau2 = res.x
    return dict(psid=float(psid), beta=float(beta), tau1=float(tau1), tau2=float(tau2),
                radius=float(v / psid), approx=float(guess), residual=float(np.abs(res.fun).max()))


if __name__ == "__main__":
    np.set_printoptions(precision=4, suppress=True, linewidth=150)
    print("steady turns (lean, speed): exact vs small-angle")
    for phi, v, th in ((0.05, 1.5, 0.0), (0.1, 1.0, 0.0), (0.1, 1.5, 0.0), (0.2, 1.5, 0.0),
                       (0.236452, 1.48749, 0.139568)):
        st = steady_turn(phi, v, th)
        print(f"  phi={phi:.4f} v={v:.4f} theta2={th:.4f}: psi'={st['psid']:+.6f} (approx {st['approx']:+.6f}) "
              f"radius={st['radius']:+.4f} m beta={st['beta']:+.2e} tau1={st['tau1']:+.2e} "
              f"tau2={st['tau2']:+.4f} residual={st['residual']:.1e}")
