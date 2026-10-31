# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "sympy>=1.13"]
# ///
"""Equations of motion of the Gyrover with exact rolling (the reference model).

Own derivation (Kane's method, ``sympy.physics.mechanics``) of the system Tsai, Ferreira and
Paredis model in *Control of the Gyrover* (IROS 1999, section 2): a knife-edge wheel rolling
without slipping on a horizontal plane, a pendulum swinging about the wheel axle, a tilt
gimbal on the pendulum and a flywheel spinning in the gimbal. The rolling constraint is
imposed exactly: the generalized speeds are the six independent rates, and the velocity of
the wheel centre is written as ``w_W x (R e_up)`` (the contact point has zero velocity), so
the contact force does no work and never appears.

Frames (all right-handed, z of the world up):

    N   world
    A   N rotated by the heading psi about N.z      A.x = direction of travel
    B   A rotated by the lean phi about A.x         B.y = wheel axle, B.z = contact -> centre
    W   B rotated by gamma about B.y                wheel (rim + domes)
    P   B rotated by beta about B.y                 pendulum, beta = absolute pitch in B
    G   P rotated by theta2 about P.x               tilt gimbal (P.x = fore-aft tilt axis)
    rotor spins about G.y relative to G at u6 (gyrostat: axisymmetric, so its inertia is
        written in the G basis and its spin angle never appears)

Generalized coordinates ``q = (psi, phi, gamma, beta, th2)`` (+ the centre position ``x, y``
and the rotor angle, which do not enter the dynamics) and speeds ``u = (psi', phi', gamma',
beta', th2', w3)`` with ``w3`` the rotor rate relative to the gimbal. The joint angle of the
axle (pendulum relative to wheel) is ``theta1 = beta - gamma``.

Loads: gravity on the four centres of mass; the drive torque ``tau1`` on the pendulum about
B.y and its reaction on the wheel; the tilt torque ``tau2`` on the gimbal about P.x and its
reaction on the pendulum; the spin torque ``tau3`` on the rotor about G.y and its reaction on
the gimbal; the drilling friction of the tyre, ``-bsp (w_W . N.z)`` about the ground normal (the
``bsp`` of ``RollingDisk``; 0 makes the model conservative).

``derive()`` returns the mass matrix ``M(q)`` (6 x 6) and the forcing ``f(q, u, tau)`` with
``M u' = f``, plus the centre velocity and the energies. The result is cached in
``_eom_cache.pkl`` next to this file (delete it after changing the derivation).
"""

from __future__ import annotations

import pickle
from pathlib import Path

import sympy as sp
import sympy.physics.mechanics as me

HERE = Path(__file__).resolve().parent
CACHE = HERE / "_eom_cache.pkl"

# Parameter symbols, in the order the numeric helpers expect them.
PARAM_NAMES = [
    "R",                       # wheel radius (m)
    "m_w", "Jwa", "Jwt",       # wheel: mass, axial and transverse inertia about its centre
    "m_p", "l_p", "a_p",       # pendulum: mass, CoM below the axle (m), principal-axis pitch (rad)
    "Jp1", "Jp2", "Jp3",       # pendulum principal inertias about its CoM (x', y' = axle, z')
    "m_g", "l_g",              # gimbal frame mass, gimbal centre below the axle (m)
    "Jg1", "Jg2", "Jg3",       # gimbal frame inertia about its centre in G (x = tilt axis, y = spin axis, z)
    "m_r", "Jra", "Jrt",       # flywheel: mass, axial (spin) and transverse inertia
    "g0",                      # gravity (m/s^2)
    "bsp",                     # tyre spin (drilling) damping about the ground normal (N m s/rad)
]


def derive():
    if CACHE.is_file():
        with CACHE.open("rb") as fh:
            return pickle.load(fh)
    psi, phi, gam, beta, th2 = me.dynamicsymbols("psi phi gamma beta th2")
    u1, u2, u3, u4, u5, u6 = me.dynamicsymbols("u1:7")
    tau1, tau2, tau3 = sp.symbols("tau1 tau2 tau3")
    P = {n: sp.Symbol(n) for n in PARAM_NAMES}
    R, g0 = P["R"], P["g0"]

    N = me.ReferenceFrame("N")
    A = N.orientnew("A", "Axis", [psi, N.z])
    B = A.orientnew("B", "Axis", [phi, A.x])
    W = B.orientnew("W", "Axis", [gam, B.y])
    Pf = B.orientnew("Pf", "Axis", [beta, B.y])
    Pp = Pf.orientnew("Pp", "Axis", [P["a_p"], Pf.y])      # pendulum principal axes
    G = Pf.orientnew("G", "Axis", [th2, Pf.x])

    # Angular velocities in terms of the generalized speeds.
    A.set_ang_vel(N, u1 * N.z)
    B.set_ang_vel(A, u2 * A.x)
    W.set_ang_vel(B, u3 * B.y)
    Pf.set_ang_vel(B, u4 * B.y)
    Pp.set_ang_vel(Pf, 0 * Pf.y)
    G.set_ang_vel(Pf, u5 * Pf.x)
    Rt = G.orientnew("Rt", "Axis", [0, G.y])                  # rotor frame (spin angle irrelevant)
    Rt.set_ang_vel(G, u6 * G.y)

    O = me.Point("O")                                           # wheel centre
    wW = W.ang_vel_in(N)
    vO = wW.cross(R * B.z)                                      # rolling without slip
    O.set_vel(N, vO)
    Pc = O.locatenew("Pc", -P["l_p"] * Pf.z)
    Gc = O.locatenew("Gc", -P["l_g"] * Pf.z)
    Pc.v2pt_theory(O, N, Pf)
    Gc.v2pt_theory(O, N, Pf)

    I_w = me.inertia(B, P["Jwt"], P["Jwa"], P["Jwt"])          # axisymmetric about B.y
    I_p = me.inertia(Pp, P["Jp1"], P["Jp2"], P["Jp3"])
    I_g = me.inertia(G, P["Jg1"], P["Jg2"], P["Jg3"])
    I_r = me.inertia(G, P["Jrt"], P["Jra"], P["Jrt"])          # axisymmetric about G.y
    wheel = me.RigidBody("wheel", O, W, P["m_w"], (I_w, O))
    pend = me.RigidBody("pend", Pc, Pp, P["m_p"], (I_p, Pc))
    gimb = me.RigidBody("gimb", Gc, G, P["m_g"], (I_g, Gc))
    rotor = me.RigidBody("rotor", Gc, Rt, P["m_r"], (I_r, Gc))
    bodies = [wheel, pend, gimb, rotor]

    loads = [
        (O, -P["m_w"] * g0 * N.z), (Pc, -P["m_p"] * g0 * N.z),
        (Gc, -(P["m_g"] + P["m_r"]) * g0 * N.z),
        (Pf, tau1 * B.y), (W, -tau1 * B.y),
        (G, tau2 * Pf.x), (Pf, -tau2 * Pf.x),
        (Rt, tau3 * G.y), (G, -tau3 * G.y),
        (W, -P["bsp"] * wW.dot(N.z) * N.z),                     # tyre drilling friction
    ]
    q = [psi, phi, gam, beta, th2]
    u = [u1, u2, u3, u4, u5, u6]
    kd = [q[i].diff() - u[i] for i in range(5)]
    km = me.KanesMethod(N, q_ind=q, u_ind=u, kd_eqs=kd)
    fr, frstar = km.kanes_equations(bodies, loads)
    M = km.mass_matrix
    f = km.forcing
    # Energies (the wheel's kinetic energy uses its true angular velocity).
    ke = sum(b.kinetic_energy(N) for b in bodies)
    pe = g0 * (P["m_w"] * O.pos_from(O).dot(N.z) + 0)
    zO = R * B.z.dot(N.z)                                       # centre height above the contact
    pe = g0 * (P["m_w"] * zO + P["m_p"] * (zO + Pc.pos_from(O).dot(N.z))
               + (P["m_g"] + P["m_r"]) * (zO + Gc.pos_from(O).dot(N.z)))
    vOx, vOy = vO.dot(N.x), vO.dot(N.y)

    # Replace the dynamicsymbols by plain symbols for code generation.
    qs = sp.symbols("psi phi gamma beta th2")
    us = sp.symbols("u1:7")
    rep = {**{qi.diff(): ui for qi, ui in zip(q, u)}, **dict(zip(u, us)), **dict(zip(q, qs))}

    def plain(e):
        return sp.sympify(e).subs(rep)

    out = {
        "M": sp.Matrix(M).applyfunc(plain),
        "f": sp.Matrix(f).applyfunc(plain),
        "vO": (plain(vOx), plain(vOy)),
        "ke": plain(ke),
        "pe": plain(pe),
        "q": qs, "u": us, "tau": (tau1, tau2, tau3),
        "params": [P[n] for n in PARAM_NAMES],
    }
    with CACHE.open("wb") as fh:
        pickle.dump(out, fh)
    return out


if __name__ == "__main__":
    import time

    t0 = time.time()
    e = derive()
    print(f"derived in {time.time() - t0:.1f} s; M free symbols: {sorted(map(str, e['M'].free_symbols))}")
    print("f ops:", sp.count_ops(e["f"]), " M ops:", sp.count_ops(e["M"]))
