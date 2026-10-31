# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "sympy>=1.13"]
# ///
"""Writes ``library/GyroverRef.jl``: the reference model of the example as a bg-sim block.

The block is the equation-based twin of the bond graph: the exact-rolling equations of
``eom.py`` (Kane's method, our own derivation), generated as code. The mass matrix ``M(q)``
and the forcing ``f(q, u, tau)`` come out of SymPy with common subexpressions shared
(``cse``), and ``M u' = f`` is solved in the block by an explicit LDL^T elimination (``M`` is
symmetric positive definite), so the equations stay small and no symbolic inverse is formed.

The inputs and outputs are in the paper's coordinates (``design.S*``), exactly like the
bond graph's sensor block ``GyroSense``, so the same ``GyroCtrl`` drives both models.

    uv run examples/gyrover/design/gen_ref.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import sympy as sp

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import design as d  # noqa: E402
import eom  # noqa: E402

OUT = HERE.parent / "library" / "GyroverRef.jl"

UNITS = dict(R="m", m_w="kg", Jwa="kg*m^2", Jwt="kg*m^2", m_p="kg", l_p="m", a_p="rad", Jp1="kg*m^2",
             Jp2="kg*m^2", Jp3="kg*m^2", m_g="kg", l_g="m", Jg1="kg*m^2", Jg2="kg*m^2", Jg3="kg*m^2",
             m_r="kg", Jra="kg*m^2", Jrt="kg*m^2", g0="m/s^2", bsp="N*m*s/rad")
DESC = dict(
    R="Wheel radius", m_w="Wheel mass (rim, tyre, domes)", Jwa="Wheel axial inertia",
    Jwt="Wheel transverse inertia", m_p="Pendulum mass (drive unit, battery)",
    l_p="Pendulum centre of mass below the axle", a_p="Pitch of the pendulum's principal axes",
    Jp1="Pendulum principal inertia 1", Jp2="Pendulum principal inertia 2 (axle)",
    Jp3="Pendulum principal inertia 3", m_g="Gimbal frame mass", l_g="Gimbal centre below the axle",
    Jg1="Gimbal inertia about the tilt axis", Jg2="Gimbal inertia about the spin axis",
    Jg3="Gimbal inertia about its third axis", m_r="Flywheel mass", Jra="Flywheel axial (spin) inertia",
    Jrt="Flywheel transverse inertia", g0="Gravitational acceleration",
    bsp="Tyre drilling damping about the ground normal",
)


class JuliaPrinter(sp.printing.str.StrPrinter):
    def _print_Pow(self, expr):
        b, e = expr.as_base_exp()
        if e == sp.Rational(1, 2):
            return f"sqrt({self._print(b)})"
        if e == -1:
            return f"(1 / {self.parenthesize(b, 100)})"
        if e.is_Integer and e > 0:
            return f"{self.parenthesize(b, 100)}^{int(e)}"
        return f"{self.parenthesize(b, 100)}^({self._print(e)})"

    def _print_Rational(self, expr):
        return f"({float(expr)!r})"

    def _print_Float(self, expr):
        return repr(float(expr))

    def _print_Integer(self, expr):
        return f"{int(expr)}.0"


def jl(expr) -> str:
    return JuliaPrinter().doprint(expr)


def main() -> None:
    e = eom.derive()
    qs, us = e["q"], e["u"]
    t1, t2, t3 = e["tau"]
    # inputs in the paper's signs: tau_ours = S tau_paper
    tin = sp.symbols("tau1_in tau2_in tau3_in")
    sub_tau = {t1: d.ST * tin[0], t2: d.S2 * tin[1], t3: tin[2]}
    M, f = e["M"], e["f"].subs(sub_tau)
    n = 6
    entries = [M[i, j] for i in range(n) for j in range(i, n)] + [f[i] for i in range(n)]
    entries += [e["vO"][0], e["vO"][1], e["ke"], e["pe"]]
    reps, red = sp.cse(entries, symbols=sp.numbered_symbols("c"), optimizations="basic")
    names_M = [f"M{i + 1}{j + 1}" for i in range(n) for j in range(i, n)]
    names_f = [f"F{i + 1}" for i in range(n)]
    names = names_M + names_f + ["vx", "vy", "KE", "PE"]
    # rename q/u symbols to the block's variable names
    qn = ["psi", "phi", "gam", "beta", "tlt"]
    un = [f"u{i + 1}" for i in range(n)]
    # The tilt is carried in the paper's sign (tlt = S2 th2, u5 = S2 th2'), so that the outputs
    # th2 and w2 are plain aliases of states (bg-sim follows start values along plain aliases).
    sgn = {4: d.S2}
    ren = {**{a: sgn.get(i, 1) * sp.Symbol(b) for i, (a, b) in enumerate(zip(qs, qn))},
           **{a: sgn.get(i, 1) * sp.Symbol(b) for i, (a, b) in enumerate(zip(us, un))},
           **{a: sp.Symbol(str(a).replace("_in", "")) for a in tin}}

    def J(x):
        return jl(sp.sympify(x).xreplace(ren))

    var_lines, eq_lines = [], []
    for sym, val in reps:
        var_lines.append(f"        {sym}::Real = 0.0")
        eq_lines.append(f"        {sym} ~ {J(val)}")
    for name, val in zip(names, red):
        var_lines.append(f"        {name}::Real = 0.0")
        eq_lines.append(f"        {name} ~ {J(val)}")
    # LDL^T of M and the solve M ud = F
    Mn = lambda i, j: f"M{min(i, j) + 1}{max(i, j) + 1}"
    for j in range(n):
        s = " - ".join([Mn(j, j)] + [f"L{j + 1}{k + 1}^2 * D{k + 1}" for k in range(j)])
        var_lines.append(f"        D{j + 1}::Real = 1.0")
        eq_lines.append(f"        D{j + 1} ~ {s}")
        for i in range(j + 1, n):
            s = " - ".join([Mn(i, j)] + [f"L{i + 1}{k + 1} * L{j + 1}{k + 1} * D{k + 1}" for k in range(j)])
            var_lines.append(f"        L{i + 1}{j + 1}::Real = 0.0")
            eq_lines.append(f"        L{i + 1}{j + 1} ~ ({s}) / D{j + 1}")
    for i in range(n):
        s = " - ".join([f"F{i + 1}"] + [f"L{i + 1}{k + 1} * z{k + 1}" for k in range(i)])
        var_lines.append(f"        z{i + 1}::Real = 0.0")
        eq_lines.append(f"        z{i + 1} ~ {s}")
    for i in reversed(range(n)):
        s = " - ".join([f"z{i + 1} / D{i + 1}"] + [f"L{k + 1}{i + 1} * ud{k + 1}" for k in range(i + 1, n)])
        var_lines.append(f"        ud{i + 1}::Real = 0.0")
        eq_lines.append(f"        ud{i + 1} ~ {s}")

    S0, S2, SY, SP = d.S0, d.S2, d.SY, d.SP
    sg = lambda s: "" if s == 1 else "-"
    params = "\n".join(
        f"        {k}::Real = {d.PARAMS[k]!r}, [unit = \"{UNITS[k]}\", description = \"{DESC[k]}\"]"
        for k in eom.PARAM_NAMES)
    text = f'''@block GyroverRef begin
    # Reference model of the Gyrover (generated by design/gen_ref.py; do not edit by hand).
    #
    # The exact-rolling equations of design/eom.py: a knife-edge wheel that rolls without
    # slipping on the ground plane, a pendulum on the axle, a tilt gimbal on the pendulum and a
    # flywheel in the gimbal, derived with Kane's method. The rolling constraint is built into
    # the generalised speeds, so there is no contact force, no penetration and no slip; the
    # bond graph (RollingDisk on a compliant contact) is compared with this block.
    #
    # Coordinates: heading psi, lean phi, wheel angle gam, pendulum pitch beta (absolute, in the
    # lean frame), tilt tlt (the paper's theta2), speeds u1..u5 their rates and u6 the flywheel rate relative to
    # the gimbal; x, y the wheel centre. M u' = F is solved by an LDL^T elimination below.
    #
    # Inputs and outputs use the paper's coordinates and signs (Tsai, Ferreira and Paredis,
    # IROS 1999), the same as GyroSense on the bond graph: tau1 drives the pendulum against the
    # wheel, tau2 the tilt gimbal against the pendulum, tau3 the flywheel against the gimbal.
    @parameters begin
{params}
    end
    @inputs begin
        tau1::Real
        tau2::Real
        tau3::Real
    end
    @variables begin
        psi::Real = 0.0, [unit = "rad", state = :prefer, description = "Heading"]
        phi::Real = 0.0, [unit = "rad", state = :prefer, description = "Lean (0 = upright)"]
        gam::Real = 0.0, [unit = "rad", state = :prefer, description = "Wheel angle"]
        beta::Real = 0.0, [unit = "rad", state = :prefer, description = "Pendulum pitch in the lean frame"]
        tlt::Real = 0.0, [unit = "rad", state = :prefer, description = "Tilt angle (paper theta2)"]
        u1::Real = 0.0, [unit = "rad/s", state = :prefer, description = "Heading rate"]
        u2::Real = 0.0, [unit = "rad/s", state = :prefer, description = "Lean rate"]
        u3::Real = 0.0, [unit = "rad/s", state = :prefer, description = "Wheel rate"]
        u4::Real = 0.0, [unit = "rad/s", state = :prefer, description = "Pendulum rate"]
        u5::Real = 0.0, [unit = "rad/s", state = :prefer, description = "Tilt rate"]
        u6::Real = 1570.7963267948965, [unit = "rad/s", state = :prefer, description = "Flywheel rate relative to the gimbal"]
        x::Real = 0.0, [unit = "m", state = :prefer, description = "Wheel centre x"]
        y::Real = 0.0, [unit = "m", state = :prefer, description = "Wheel centre y"]
{chr(10).join(var_lines)}
    end
    @outputs begin
        lean::Real, [unit = "rad", description = "Lean from upright (paper theta0 - pi/2)"]
        heading::Real, [unit = "rad", description = "Heading psi"]
        th1::Real, [unit = "rad", description = "Pendulum angle (paper theta1)"]
        w1::Real, [unit = "rad/s", description = "Pendulum rate relative to the wheel (paper w1)"]
        wz::Real, [unit = "rad/s", description = "Wheel rate about the axle (paper omega0z)"]
        th2::Real, [unit = "rad", description = "Tilt angle (paper theta2)"]
        w2::Real, [unit = "rad/s", description = "Tilt rate (paper w2)"]
        wx::Real, [unit = "rad/s", description = "Roll rate (paper omega0x)"]
        wy::Real, [unit = "rad/s", description = "Yaw rate in the wheel plane (paper omega0y)"]
        yaw_rate::Real, [unit = "rad/s", description = "Heading rate"]
        w3::Real, [unit = "rad/s", description = "Flywheel rate relative to the gimbal"]
        v::Real, [unit = "m/s", description = "Forward speed R wz"]
        xc::Real, [unit = "m", description = "Wheel centre x"]
        yc::Real, [unit = "m", description = "Wheel centre y"]
        E::Real, [unit = "J", description = "Total energy (kinetic + gravity)"]
        Ek::Real, [unit = "J", description = "Kinetic energy"]
        Ep::Real, [unit = "J", description = "Gravity potential energy (contact point at 0)"]
    end
    @equations begin
        ddt(psi) ~ u1
        ddt(phi) ~ u2
        ddt(gam) ~ u3
        ddt(beta) ~ u4
        ddt(tlt) ~ u5
{chr(10).join(eq_lines)}
        ddt(u1) ~ ud1
        ddt(u2) ~ ud2
        ddt(u3) ~ ud3
        ddt(u4) ~ ud4
        ddt(u5) ~ {sg(S2)}ud5
        ddt(u6) ~ ud6
        ddt(x) ~ vx
        ddt(y) ~ vy
        lean ~ {sg(S0)}phi
        heading ~ psi
        th1 ~ {sg(SP)}beta
        w1 ~ {sg(SP)}(u4 - u3)
        wz ~ {sg(SP)}(u3 + u1 * sin(phi))
        th2 ~ tlt
        w2 ~ u5
        wx ~ {sg(S0)}u2
        wy ~ {sg(SY)}u1 * cos(phi)
        yaw_rate ~ u1
        w3 ~ u6
        v ~ R * (u3 + u1 * sin(phi))
        xc ~ x
        yc ~ y
        Ek ~ KE
        Ep ~ PE
        E ~ KE + PE
    end
end
'''
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT} ({len(reps)} shared subexpressions, {len(text.splitlines())} lines)")


if __name__ == "__main__":
    main()
