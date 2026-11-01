# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.11"]
# ///
"""Design data and the analytic grip-force sizing of the `gripper` example.

Everything the model, the scene, the docs and the checks need is computed here once:

    uv run examples/gripper/design/design.py        # prints the sizing and the predictions

`build_model.py` imports this module and writes the model documents and the 3D scene from it.
All values are SI. Sources and assumptions are stated next to each number (see the README).
"""

from __future__ import annotations

import math

import numpy as np
from scipy.integrate import solve_ivp

G0 = 9.81                                  # m/s^2

# ----------------------------------------------------------------------------- the parts
RHO_STEEL = 7850.0                         # kg/m^3
RHO_ALU = 2700.0
BALL_D = 0.050                             # m, polished bearing-steel ball, 50 mm
BALL_R = BALL_D / 2
BALL_M = RHO_STEEL * math.pi / 6 * BALL_D**3          # 0.5137 kg
BALL_J = 0.4 * BALL_M * BALL_R**2                     # solid sphere

# machined aluminium block 40 (x, gripped) x 40 (y) x 80 (z) mm, gripped 25 mm above its centre
BLOCK = (0.040, 0.040, 0.080)
BLOCK_M = RHO_ALU * BLOCK[0] * BLOCK[1] * BLOCK[2]   # 0.3456 kg
BLOCK_J = (BLOCK_M * (BLOCK[1] ** 2 + BLOCK[2] ** 2) / 12,
           BLOCK_M * (BLOCK[0] ** 2 + BLOCK[2] ** 2) / 12,
           BLOCK_M * (BLOCK[0] ** 2 + BLOCK[1] ** 2) / 12)
BLOCK_E = 0.028                            # m, grip line above the centre of mass (lever of a_h)
PAD_PT = 0.006                             # m, block contact points at (+-6, +-6) mm on each pad (a narrow pad land)
PAD_R = math.sqrt(2) * PAD_PT              # torsion lever of the four points

# ----------------------------------------------------------------------------- jaw pads and table
# Polyurethane-faced jaw inserts (Shore 90A, E* ~ 57 MPa): Hertz F = 4/3 E* sqrt(R) x^1.5 for the
# 50 mm ball gives K = 1.2e7 N/m^1.5, written as k x sqrt(x/xref) with xref = 0.1 mm.
PAD = {"k": 1.2e5, "xref": 1.0e-4, "c": 5.0, "mu": 0.25, "vs": 1.0e-3, "eps": 1.0e-6, "feps": 1.0e-6}
PAD_W = 0.012                              # m, half-width of the flat pad face (24 x 24 mm pad)
PAD_WE = 5.0e-4                            # m, edge smoothing
# Flat-on-flat pad against the block: a stiffer, linearised patch per point (4 points per pad).
PAD_BLOCK = {"k": 3.0e5, "xref": 1.0e-4, "c": 5.0, "mu": 0.25, "vs": 1.0e-3, "eps": 1.0e-6, "feps": 1.0e-6}
TABLE = {"k": 1.0e6, "xref": 1.0e-4, "c": 5.0, "mu": 0.3, "vs": 1.0e-3, "eps": 1.0e-6, "feps": 1.0e-6}
MU = PAD["mu"]
GAP = 0.006                                # m, jaw clearance per side when open

# ----------------------------------------------------------------------------- drive train
K_T = 0.012                                # N m/A, small brushed DC motor with gearhead
J_M = 1.5e-6                               # kg m^2, rotor + gearhead input
B_M = 1.0e-6                               # N m s/rad
I_MAX = 2.5                                # A
N_GEAR = 3.0                               # gearhead ratio
LEAD = 0.003                               # m per spindle revolution
ETA = 0.7                                  # gearhead + spindle + wedge sliding, forward
ETA_BACK = 2.0 - 1.0 / ETA                 # screw-thread relation, 0.571: not self-locking
W_EPS = 1.0e-3                             # rad/s, thread-friction direction smoothing
I_W = 0.5                                  # wedge hook: jaw speed / nut speed (26.6 deg)
G_IDEAL = N_GEAR * 2 * math.pi / LEAD / (2 * I_W)    # N per jaw per N m of motor torque = 6283
GUIDE = {"Fs": 4.0, "Fc": 3.0, "Fv": 10.0, "v_s": 0.005, "v_eps": 1.0e-4}   # both jaw guides together
# Effective mass of the jaw node (both jaws, closing coordinate): the rotor inertia reflected.
M_NODE = J_M * (N_GEAR * 2 * math.pi / LEAD / I_W) ** 2            # 237 kg

CTRL = {"t_close": 0.05, "t_open": 1.85, "x_close": 0.020, "v_close": 0.030, "v_open": 0.05,
        "v_grip": 0.003, "x_pre": 0.0057, "x_band": 0.001, "Kp": 30.0, "Kv": 3000.0}
# The block: its four stiff point contacts per pad turn the closing energy into much more force than
# the soft ball contact does (the locked-in impact, see impact()), so it is gripped at 1 mm/s from
# 0.1 mm before the face. Kv v_grip = 3 A stays above the largest grip current, so the speed
# loop still saturates at I_grip.
BLOCK_CTRL = {"v_grip": 0.001, "x_pre": 0.0059}

# ----------------------------------------------------------------------------- the move
LIFT = {"q_end": 0.10, "t_start": 0.55, "v_max": 0.6, "a_max": 4.0, "j_max": 80.0}
TRANSFER = {"q_end": 0.40, "t_start": 0.95, "v_max": 2.0, "a_max": 20.0, "j_max": 600.0}
# The place height leaves PLACE_CLEAR between ball and target: setting the part down with the
# jaws still closed would push it up through the grip (a forced slip, not a grip failure).
PLACE_CLEAR = 0.5e-3
LOWER = {"q_end": -(0.10 - PLACE_CLEAR), "t_start": 1.40, "v_max": 0.6, "a_max": 4.0, "j_max": 80.0}
RETREAT = {"q_end": 0.10, "t_start": 2.20, "v_max": 0.6, "a_max": 4.0, "j_max": 80.0}
T_END = 2.7
S_SAFETY = 2.0


def hertz_x(F, k, xref):
    """Penetration of `F = k x sqrt(x/xref)`."""
    return (F * math.sqrt(xref) / k) ** (2.0 / 3.0)


# rest height of the ball centre on the table (the carriage starts at the ball centre)
BALL_Z0 = BALL_R - hertz_x(BALL_M * G0, TABLE["k"], TABLE["xref"])
# rest height of the block centre of mass on its four bottom corners
BLOCK_Z0 = BLOCK[2] / 2 - hertz_x(BLOCK_M * G0 / 4, TABLE["k"], TABLE["xref"])


def required_grip(m, a_h, a_v, mu=MU):
    """Grip force per jaw (S = 1) for a friction grip between two jaws: m |a - g| / (2 mu)."""
    return m * math.hypot(a_h, G0 + a_v) / (2 * mu)


def required_grip_moment(m, a_h, a_v, e, r, mu=MU, ellipse=False):
    """Two pads of four points at lever r carrying the force F_t and the moment M = m a_h e about the
    jaw axis (CoM e below the grip line). Linear rule (the sizing rule): |F_t| + M / r <= 2 mu F, the
    friction of every point used by the worst-aligned sum of its force and torsion shares, safe for
    any direction. `ellipse=True`: the limit-surface estimate sqrt(F_t^2 + (M/r)^2) <= 2 mu F of a
    pad that slides as a whole (less conservative; the simulation lies near it)."""
    Ft = m * math.hypot(a_h, G0 + a_v)
    M = m * abs(a_h) * e
    if ellipse:
        return math.hypot(Ft, M / r) / (2 * mu)
    return (Ft + M / r) / (2 * mu)


def grip_current(F, eta=ETA):
    """Motor current that makes the grip force F per jaw while the drive closes (forward efficiency)."""
    return F / (eta * K_T * G_IDEAL)


# Sizing (the transfer acceleration dominates; lift and transfer do not overlap in time)
F_STATIC = required_grip(BALL_M, 0.0, 0.0)
F_LIFT = required_grip(BALL_M, 0.0, LIFT["a_max"])
F_TRANSFER = required_grip(BALL_M, TRANSFER["a_max"], 0.0)
F_SIZED = math.ceil(S_SAFETY * max(F_LIFT, F_TRANSFER))         # 46 N
F_UNDER = 12.0                                                  # holds statically and in the lift, not in the transfer

BLOCK_F_FORCE_ONLY = required_grip(BLOCK_M, TRANSFER["a_max"], 0.0)
BLOCK_F_MOMENT = required_grip_moment(BLOCK_M, TRANSFER["a_max"], 0.0, BLOCK_E, PAD_R)
BLOCK_F_SIZED_FORCE = math.ceil(S_SAFETY * BLOCK_F_FORCE_ONLY)  # sized without the moment
BLOCK_F_SIZED = math.ceil(S_SAFETY * BLOCK_F_MOMENT)            # sized with the moment
BLOCK_F_ELLIPSE = required_grip_moment(BLOCK_M, TRANSFER["a_max"], 0.0, BLOCK_E, PAD_R, ellipse=True)


# ----------------------------------------------------------------------------- closing impact
def impact(v_grip, F_set, k=PAD["k"], xref=PAD["xref"], c=PAD["c"], eta=ETA, m_node=M_NODE):
    """Closing impact on the resting, centred ball: the reduced 1-DOF model of the closing.

    The jaw node (both jaws, closing travel x from first contact) carries the reflected rotor
    inertia m_node. Driving forward, only eta of the motor torque and of the rotor's inertia
    torque reaches the jaws, so eta m_node x'' = 2 eta G k_t i - 2 f_pad - F_guide, with the
    speed loop of the controller in the grip zone, i = clamp(Kv (v_grip - x'), -I_max, I_grip),
    two Hunt-Crossley pads f_pad = K x^1.5 (1 + c x') and the guide friction (Coulomb plus
    viscous, both jaws). Integrated from contact at the approach speed v_grip until the jaws stop.
    Returns (peak pad force, pad force when the jaws stop, the friction band top G k_t I_grip /
    eta_back). Below the band top the drive cannot be back-driven, so the stop force stays: it is
    the grip force the gripper holds (the impact is locked in)."""
    K = k / math.sqrt(xref)
    i_grip = grip_current(F_set)
    m_eff = eta * m_node

    def rhs(_t, y):
        x, v = y
        xp = max(x, 0.0)
        f = K * xp**1.5 * (1 + c * v)
        i = min(max(CTRL["Kv"] * (v_grip - v), -I_MAX), i_grip)
        guide = GUIDE["Fc"] * math.tanh(v / GUIDE["v_eps"]) + GUIDE["Fv"] * v
        return [v, (2 * eta * G_IDEAL * K_T * i - 2 * f - guide) / m_eff]

    def stop(_t, y):
        return y[1]

    stop.terminal = True
    stop.direction = -1
    sol = solve_ivp(rhs, (0, 2.0), [0.0, v_grip], max_step=1e-4, rtol=1e-9, atol=1e-12, events=stop)
    x, v = sol.y
    f = K * np.maximum(x, 0) ** 1.5 * (1 + c * v)
    return float(f.max()), float(K * max(x[-1], 0.0) ** 1.5), G_IDEAL * K_T * i_grip / ETA_BACK


IMPACT_SPEEDS = (0.003, 0.010, 0.020, 0.030)


# ----------------------------------------------------------------------------- slip threshold
def slip_detect_force(ramp, s_th, m=BALL_M, mu=MU, vs=PAD["vs"]):
    """Grip force at which the held ball's slip speed reaches s_th while the grip force falls.

    The ball hangs between the jaws, so m s' = m g0 - 2 mu F(t) tanh(s/vs) (both jaws slip
    alike and their friction torques cancel, so it does not spin). The grip force falls at the
    rate of a back-driven drive, F' = -ramp / (eta eta_back) for a setting falling at `ramp` N/s:
    the friction band top G k_t I / eta_back follows the current. Starting at 2 F* in the creep
    equilibrium, this returns the force at s = s_th: below the static threshold F* = m g0/(2 mu)
    by the time the ball needs to accelerate to s_th, above it by the creep of the regularised
    friction (s = vs atanh(F*/F) while held). Returns (F at s_th, F*)."""
    F_star = m * G0 / (2 * mu)
    rate = ramp / (ETA * ETA_BACK)
    F0 = 2.0 * F_star
    s0 = vs * math.atanh(F_star / F0)

    def rhs(t, y):
        F = F0 - rate * t
        return [G0 - 2 * mu * F * math.tanh(y[0] / vs) / m]

    def hit(_t, y):
        return y[0] - s_th

    hit.terminal = True
    sol = solve_ivp(rhs, (0, 2 * F0 / rate), [s0], max_step=1e-4, rtol=1e-10, atol=1e-12, events=hit)
    return F0 - rate * float(sol.t_events[0][0]), F_star


SLIP_RAMP = 10.0                           # N/s, setting ramp of the slip-threshold run
SLIP_S_TH = 0.002                          # m/s, slip speed that counts as sliding (2 vs)


def summary() -> str:
    lines = [
        f"ball: d = {BALL_D * 1e3:.0f} mm, m = {BALL_M:.4f} kg, J = {BALL_J:.4e} kg m^2, rest z = {BALL_Z0 * 1e3:.4f} mm",
        f"block: {BLOCK} m, m = {BLOCK_M:.4f} kg, J = {tuple(round(j, 7) for j in BLOCK_J)}",
        f"mu = {MU}, S = {S_SAFETY}",
        f"required grip per jaw (S=1): static {F_STATIC:.3f} N, lift (a_v={LIFT['a_max']}) {F_LIFT:.3f} N, "
        f"transfer (a_h={TRANSFER['a_max']}) {F_TRANSFER:.3f} N",
        f"sized grip F = {F_SIZED} N (S_transfer = {F_SIZED / F_TRANSFER:.3f}), under-grip {F_UNDER} N "
        f"(S_static {F_UNDER / F_STATIC:.2f}, S_lift {F_UNDER / F_LIFT:.2f}, S_transfer {F_UNDER / F_TRANSFER:.2f})",
        f"block: force only {BLOCK_F_FORCE_ONLY:.3f} N, with moment {BLOCK_F_MOMENT:.3f} N; sized "
        f"{BLOCK_F_SIZED_FORCE} N (force only) / {BLOCK_F_SIZED} N (with moment); limit-surface estimate (S=1) {BLOCK_F_ELLIPSE:.3f} N",
        f"drive: G = {G_IDEAL:.2f} N/(N m) per jaw, {K_T * G_IDEAL:.3f} N/A ideal, {ETA * K_T * G_IDEAL:.3f} N/A at eta",
        f"  eta_back = {ETA_BACK:.4f}; grip current {F_SIZED} N -> {grip_current(F_SIZED):.4f} A, "
        f"{F_UNDER} N -> {grip_current(F_UNDER):.4f} A; max force {ETA * K_T * G_IDEAL * I_MAX:.1f} N at {I_MAX} A",
        f"  friction band at rest for the sized current: [{ETA * K_T * G_IDEAL * grip_current(F_SIZED):.2f}, "
        f"{K_T * G_IDEAL * grip_current(F_SIZED) / ETA_BACK:.2f}] N",
        f"  jaw node effective mass {M_NODE:.2f} kg",
    ]
    for v in IMPACT_SPEEDS:
        pk, stop, top = impact(v, F_SIZED)
        lines.append(f"impact v = {v * 1e3:.0f} mm/s: peak {pk:.2f} N, at the stop {stop:.2f} N (band top {top:.1f} N)")
    pk, stop, top = impact(CTRL["v_grip"], F_UNDER)
    lines.append(f"under-grip {F_UNDER} N at {CTRL['v_grip'] * 1e3:.0f} mm/s: peak {pk:.2f} N, at the stop {stop:.2f} N")
    Fd, Fs = slip_detect_force(SLIP_RAMP, SLIP_S_TH)
    lines.append(f"slip threshold F* = {Fs:.4f} N; detected at s_th = {SLIP_S_TH} m/s with the setting falling at "
                 f"{SLIP_RAMP} N/s: {Fd:.4f} N ({(Fd / Fs - 1) * 100:+.2f} %)")
    lines.append(f"  creep while held at util u: s = vs atanh(u); at u = 0.5: {PAD['vs'] * math.atanh(0.5) * 1e3:.4f} mm/s")
    return "\n".join(lines)


if __name__ == "__main__":
    print(summary())
