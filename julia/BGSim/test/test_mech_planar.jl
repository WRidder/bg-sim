# Work package J-MB7: the planar mechanics test suite (plan 6, row J-MB7; Gate B).
#
# This file closes Phase B with the plan 9.1/9.2 acceptance for the planar composites:
#
#   * a single pendulum on `RigidBody2D` + `Revolute2DCompliant`: period against the
#     amplitude-corrected physical period and `2π√(L/g)`, energy, `q`/`qdot` by path;
#   * a two-link double pendulum with two compliant joints, compared against an **independent**
#     two-link Lagrangian integrated by a small RK4 written here (not derived from the model).
#     The model's error against the rigid reference decreases with `kt`; the ratios are
#     reported;
#   * `Prismatic2D` carrying a `Translation` drive, a damped mass-spring period and a static
#     equilibrium under a constant force;
#   * a free body at a constant body twist = the exact SE(2) screw, plus the world momentum
#     invariants of the general free case, over 10 s;
#   * `ExternalWrenchPlanar` (the physical `W_ext`) on a free body: `a = F/m`, `α = τ/J`,
#     `P(t) = P0 + W t` (FIX-MB-4's sign);
#   * `Revolute2DFriction`: a spinning body decays monotonically and only dissipates; a
#     stick/slide threshold case;
#   * `Revolute2DLimit`: zero effort inside `[lower, upper]`, the one-sided stop outside with
#     the expected sign, an elastic rebound, no W206;
#   * **no W201 with compliance** for every model above, and the rigid variant's documented
#     diagnostic set in one place (DEC-MB-2);
#   * fixed-base pose composition (`JointPose2D` + `ComposePose2D`) against a
#     `PoseIntegrator2D` on the same twist over 10 s, with gravity reading the composed pose.
#
# Tolerances follow plan 9.1: relative 1e-9 for algebraic identities and 1e-6 over 10 s for
# integrated trajectories at the stated solver settings (Rodas5P, reltol 1e-9, abstol 1e-11).
# Every helper is `_mp7_`-prefixed because the test files share `Main`.
using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import BGSim.Library
import BGSim.Units
import ModelingToolkit

if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using .BondGraphGolden

# ---------------------------------------------------------------------------------------
# Model documents and analytic helpers
# ---------------------------------------------------------------------------------------

const _MP7_PI = pi
const _MP7_L = 0.5                 # m, pivot to centre of mass
const _MP7_M = 1.0                 # kg
const _MP7_J = 1.0e-4              # kg*m^2 about the CoM
const _MP7_G = 9.81                # m/s^2
const _MP7_KT = 1.0e8              # N/m, the planar composites' working pivot stiffness
const _MP7_Q0 = 0.01               # rad, small-amplitude pendulum release angle

"""The amplitude-corrected physical pendulum period with the static pivot stretch."""
function _mp7_amp_period(; q0 = _MP7_Q0, kt = _MP7_KT, m = _MP7_M, j = _MP7_J,
    l = _MP7_L, g = _MP7_G)
    l_eff = l + m * g * cos(q0) / kt
    return 2 * pi * sqrt((j + m * l_eff^2) / (m * g * l_eff)) * (1 + q0^2 / 16)
end

const _MP7_T_SIMPLE = 2 * pi * sqrt(_MP7_L / _MP7_G)
const _MP7_T_AMP = _mp7_amp_period()
const _MP7_SWING = _MP7_M * _MP7_G * _MP7_L * (1 - cos(_MP7_Q0))

"""The released-from-rest pivot deflection of the single pendulum (J-MB6, FIX-MB-3)."""
function _mp7_pivot_d0(q0; kt = _MP7_KT, m = _MP7_M, j = _MP7_J, g = _MP7_G, l = _MP7_L)
    return [-m * g * j / (j + m * l^2) * sin(q0) / kt, -m * g * cos(q0) / kt]
end

"""Upward zero crossings of `y`, linearly interpolated."""
function _mp7_upward(t, y)
    out = Float64[]
    for i in 1:(length(y) - 1)
        if y[i] < 0 && y[i + 1] >= 0
            push!(out, t[i] + (t[i + 1] - t[i]) * (-y[i]) / (y[i + 1] - y[i]))
        end
    end
    return out
end

"""The period from the second and third upward zero crossings (NaN if there are fewer)."""
function _mp7_period(t, y)
    crossings = _mp7_upward(t, y)
    length(crossings) >= 3 || return NaN
    return crossings[3] - crossings[2]
end

_mp7_check(doc) = Compile.model_check(IR.parse_model(doc))
_mp7_errors(result) = [d for d in result.diagnostics if d.severity == "error"]
_mp7_has(result, code) = any(d -> d.code == code, result.diagnostics)
_mp7_w201(result) = count(d -> d.code == "W201", result.diagnostics)

"""`Ground -> joint -> FixedJoint2D -> RigidBody2D` with the link pose composed from `q`."""
function _mp7_pendulum(; joint = "stdlib:planar/Revolute2DCompliant", kt = _MP7_KT,
    q0 = _MP7_Q0, theta = 0.0, m = _MP7_M, j = _MP7_J, g0 = _MP7_G, tau = 0.0,
    t_end = 4.0, points = 4001, starts = Dict{String,Any}(),
    extra = Dict{String,Any}(), posechain = false)
    params = merge(Dict{String,Any}("rx" => "0.0", "ry" => "0.0", "kt" => string(kt),
        "bt" => "0.0", "k" => "0.0", "b" => "0.0", "qrest" => "0.0", "q0" => string(q0)),
        extra)
    nodes = Any[
        bg_node("n1", "World", bg_ref("stdlib:multibond/GroundPlanar")),
        bg_node("n2", "Joint", bg_ref(joint); params = params, starts = starts),
        bg_node("n3", "Link", bg_ref("stdlib:planar/FixedJoint2D");
            params = Dict{String,Any}("x" => "0.0", "y" => "-0.5", "theta" => string(theta))),
        bg_node("n4", "Body", bg_ref("stdlib:planar/RigidBody2D");
            params = Dict{String,Any}("m" => string(m), "J" => string(j), "g0" => string(g0))),
        bg_node("n5", "Local", bg_ref("stdlib:planar/LocalPose2D");
            params = Dict{String,Any}("x" => "0.0", "y" => "-0.5", "theta" => string(theta))),
        bg_node("n6", "Compose", bg_ref("stdlib:multibond/ComposePose2D")),
        bg_node("n7", "Torque", bg_ref("stdlib:bondgraph/Se");
            params = Dict{String,Any}("e" => string(tau))),
    ]
    conns = Any[
        bg_conn("c1", "bond", "n1", "p", "n2", "parent"),
        bg_conn("c2", "bond", "n2", "child", "n3", "parent"),
        bg_conn("c3", "bond", "n3", "child", "n4", "p"),
        bg_conn("c4", "bond", "n7", "p", "n2", "drive"),
        bg_conn("c5", "signal", "n2", "pose", "n6", "gp"),
        bg_conn("c6", "signal", "n5", "g", "n6", "gl"),
        bg_conn("c7", "signal", "n6", "g", "n4", "g"),
    ]
    if posechain
        # The plan 5.5 fixed-base composition through the explicit `JointPose2D`: the joint
        # coordinate `q` is the only state, and the pose is `g_joint(q) ∘ g_local`.
        push!(nodes, bg_node("n8", "JointPose", bg_ref("stdlib:planar/JointPose2D");
            params = Dict{String,Any}("rx" => "0.0", "ry" => "0.0", "theta0" => "0.0")))
        conns[5] = bg_conn("c5", "signal", "n2", "qout", "n8", "q")
        push!(conns, bg_conn("c8", "signal", "n8", "g", "n6", "gp"))
    end
    return bg_model("Pendulum2D", nodes, conns; t_end = t_end, points = points,
        reltol = 1.0e-9, abstol = 1.0e-11)
end

# The double pendulum's physical parameters. Both links are uniform rods of length 0.4 m with
# `J = m L^2 / 12` about their centres of mass, the CoM at half the link, and the elbow at
# link 1's distal end (`rx = l1 - r1` in the link-1 CoM frame; the supported `Joint2` route).
const _MP7_DP = (m1 = 2.0, m2 = 1.5, l1 = 0.4, r1 = 0.2, l2 = 0.4, r2 = 0.2,
    j1 = 2.0 * 0.4^2 / 12, j2 = 1.5 * 0.4^2 / 12, g = 9.81)
const _MP7_DP_Q1 = -pi / 2 + 0.4
const _MP7_DP_Q2 = 0.6
const _MP7_DP_T = 1.5
const _MP7_DP_POINTS = 301
const _MP7_DP_DT = 1.0e-5

"""The rigid two-link mass matrix `M(q2)` of the standard planar Lagrangian."""
function _mp7_dp_mass(q2; p = _MP7_DP)
    c = cos(q2)
    m11 = p.j1 + p.m1 * p.r1^2 + p.j2 +
          p.m2 * (p.l1^2 + p.r2^2 + 2 * p.l1 * p.r2 * c)
    m12 = p.j2 + p.m2 * (p.r2^2 + p.l1 * p.r2 * c)
    m22 = p.j2 + p.m2 * p.r2^2
    return m11, m12, m22
end

"""`(q1dot, q2dot, q1ddot, q2ddot)` from the hand-coded two-link equations of motion.

    M(q) q̈ + C(q, q̇) q̇ + ∂V/∂q = 0
    C q̇ = [-h (2 q̇1 q̇2 + q̇2²); h q̇1²],  h = m2 l1 r2 sin q2
    V    = m1 g r1 sin q1 + m2 g (l1 sin q1 + r2 sin(q1 + q2))

The angles are measured from the world +x axis (the arm convention of the composites), so
`V` is the potential of gravity along -y. This is written from the Lagrangian, not from the
model's equations."""
function _mp7_dp_rhs(y; p = _MP7_DP)
    q1, q2, q1d, q2d = y
    m11, m12, m22 = _mp7_dp_mass(q2; p = p)
    h = p.m2 * p.l1 * p.r2 * sin(q2)
    c1 = -h * (2 * q1d * q2d + q2d^2)
    c2 = h * q1d^2
    g1 = p.m1 * p.g * p.r1 * cos(q1) +
         p.m2 * p.g * (p.l1 * cos(q1) + p.r2 * cos(q1 + q2))
    g2 = p.m2 * p.g * p.r2 * cos(q1 + q2)
    det = m11 * m22 - m12^2
    a1 = (m22 * (-(c1 + g1)) - m12 * (-(c2 + g2))) / det
    a2 = (m11 * (-(c2 + g2)) - m12 * (-(c1 + g1))) / det
    return q1d, q2d, a1, a2
end

"""Classical RK4 of the reference, sampled every `stride` steps (one output per `dt_out`)."""
function _mp7_dp_integrate(dt, stride; q1 = _MP7_DP_Q1, q2 = _MP7_DP_Q2,
    t_end = _MP7_DP_T, p = _MP7_DP)
    steps = round(Int, t_end / dt)
    @assert steps % stride == 0
    y = [q1, q2, 0.0, 0.0]
    out = NTuple{4,Float64}[(y[1], y[2], y[3], y[4])]
    for k in 1:steps
        k1 = collect(_mp7_dp_rhs(y; p = p))
        k2 = collect(_mp7_dp_rhs(y .+ (0.5 * dt) .* k1; p = p))
        k3 = collect(_mp7_dp_rhs(y .+ (0.5 * dt) .* k2; p = p))
        k4 = collect(_mp7_dp_rhs(y .+ dt .* k3; p = p))
        y = y .+ (dt / 6) .* (k1 .+ 2 .* k2 .+ 2 .* k3 .+ k4)
        k % stride == 0 && push!(out, (y[1], y[2], y[3], y[4]))
    end
    return out
end

"""The independent reference on the run's output grid and its own convergence check."""
function _mp7_dp_reference()
    dt_out = _MP7_DP_T / (_MP7_DP_POINTS - 1)
    stride = round(Int, dt_out / _MP7_DP_DT)
    ref = _mp7_dp_integrate(_MP7_DP_DT, stride)
    finer = _mp7_dp_integrate(_MP7_DP_DT / 2, 2 * stride)
    @assert length(ref) == _MP7_DP_POINTS
    convergence = maximum(maximum(abs.(ref[k] .- finer[k])) for k in eachindex(ref))
    return ref, convergence
end

"""`Ground -> J1 -> L1 -> (B1 + J2) -> L2 -> B2`, both joints `Revolute2DCompliant`."""
function _mp7_double(; kt = _MP7_KT, p = _MP7_DP, q1 = _MP7_DP_Q1, q2 = _MP7_DP_Q2,
    t_end = _MP7_DP_T, points = _MP7_DP_POINTS)
    d1 = _mp7_dp_d0(q1, q2; kt = kt, p = p)[1]
    d2 = _mp7_dp_d0(q1, q2; kt = kt, p = p)[2]
    function joint(id, name, rx, q0, d)
        return bg_node(id, name, bg_ref("stdlib:planar/Revolute2DCompliant");
            params = Dict{String,Any}("rx" => string(rx), "ry" => "0.0", "kt" => string(kt),
                "bt" => "0.0", "k" => "0.0", "b" => "0.0", "qrest" => "0.0",
                "q0" => string(q0)),
            starts = Dict{String,Any}("d" => "[$(d[1]), $(d[2])]"))
    end
    j1 = joint("n2", "J1", 0.0, q1, d1)
    j2 = joint("n6", "J2", p.l1 - p.r1, q2, d2)
    return bg_model("DoublePendulum2D", Any[
        bg_node("n1", "World", bg_ref("stdlib:multibond/GroundPlanar")),
        j1,
        bg_node("n3", "L1", bg_ref("stdlib:planar/FixedJoint2D");
            params = Dict{String,Any}("x" => string(p.r1), "y" => "0.0", "theta" => "0.0")),
        bg_node("n4", "BJ1", bg_junction("1")),
        bg_node("n5", "B1", bg_ref("stdlib:planar/RigidBody2D");
            params = Dict{String,Any}("m" => string(p.m1), "J" => string(p.j1),
                "g0" => string(p.g))),
        j2,
        bg_node("n7", "L2", bg_ref("stdlib:planar/FixedJoint2D");
            params = Dict{String,Any}("x" => string(p.r2), "y" => "0.0", "theta" => "0.0")),
        bg_node("n8", "BJ2", bg_junction("1")),
        bg_node("n9", "B2", bg_ref("stdlib:planar/RigidBody2D");
            params = Dict{String,Any}("m" => string(p.m2), "J" => string(p.j2),
                "g0" => string(p.g))),
        bg_node("n10", "C1", bg_ref("stdlib:multibond/ComposePose2D")),
        bg_node("n11", "C2", bg_ref("stdlib:multibond/ComposePose2D")),
        bg_node("n12", "C3", bg_ref("stdlib:multibond/ComposePose2D")),
        bg_node("n13", "T1", bg_ref("stdlib:bondgraph/Se");
            params = Dict{String,Any}("e" => "0.0")),
        bg_node("n14", "T2", bg_ref("stdlib:bondgraph/Se");
            params = Dict{String,Any}("e" => "0.0")),
    ], Any[
        bg_conn("c1", "bond", "n1", "p", "n2", "parent"),
        bg_conn("c2", "bond", "n2", "child", "n3", "parent"),
        bg_conn("c3", "bond", "n3", "child", "n4", nothing),
        bg_conn("c4", "bond", "n5", "p", "n4", nothing),
        bg_conn("c5", "bond", "n6", "parent", "n4", nothing),
        bg_conn("c6", "bond", "n6", "child", "n7", "parent"),
        bg_conn("c7", "bond", "n7", "child", "n8", nothing),
        bg_conn("c8", "bond", "n9", "p", "n8", nothing),
        bg_conn("c9", "signal", "n2", "pose", "n10", "gp"),
        bg_conn("c10", "signal", "n3", "pose", "n10", "gl"),
        bg_conn("c11", "signal", "n10", "g", "n5", "g"),
        bg_conn("c12", "signal", "n10", "g", "n11", "gp"),
        bg_conn("c13", "signal", "n6", "pose", "n11", "gl"),
        bg_conn("c14", "signal", "n11", "g", "n12", "gp"),
        bg_conn("c15", "signal", "n7", "pose", "n12", "gl"),
        bg_conn("c16", "signal", "n12", "g", "n9", "g"),
        bg_conn("c17", "bond", "n13", "p", "n2", "drive"),
        bg_conn("c18", "bond", "n14", "p", "n6", "drive"),
    ]; t_end = t_end, points = points, reltol = 1.0e-9, abstol = 1.0e-11)
end

"""The released-from-rest pivot deflections of the two-link chain, in each joint's frame.

For the shoulder, `F = m1 (a1 - g) + m2 (a2 - g)` in the link-1 frame; for the elbow,
`F = m2 (a2 - g)` in the elbow frame. `d = -F/kt` is the deflection whose spring force is
exactly the force the rigid reference needs at `t = 0`, so the stiff pivot mode is not
excited by the release (the FIX-MB-3 lesson, generalised to the chain)."""
function _mp7_dp_d0(q1, q2; kt = _MP7_KT, p = _MP7_DP, g = p.g)
    m11, m12, m22 = _mp7_dp_mass(q2; p = p)
    g1 = p.m1 * g * p.r1 * cos(q1) +
         p.m2 * g * (p.l1 * cos(q1) + p.r2 * cos(q1 + q2))
    g2 = p.m2 * g * p.r2 * cos(q1 + q2)
    det = m11 * m22 - m12^2
    a1 = -(m22 * g1 - m12 * g2) / det
    a2 = -(m11 * g2 - m12 * g1) / det
    # body-1 frame: CoM1 at (r1, 0), CoM2 at (l1, 0) + r2 (cos q2, sin q2)
    a1b = (0.0, a1 * p.r1)
    a2b1 = (-(a1 + a2) * p.r2 * sin(q2), a1 * p.l1 + (a1 + a2) * p.r2 * cos(q2))
    gb1 = (-g * sin(q1), -g * cos(q1))
    fsh = p.m1 .* (a1b .- gb1) .+ p.m2 .* (a2b1 .- gb1)
    d1 = (-fsh[1] / kt, -fsh[2] / kt)
    # body-2 frame
    a2b2 = (a1 * p.l1 * sin(q2), a1 * p.l1 * cos(q2) + (a1 + a2) * p.r2)
    gb2 = (-g * sin(q1 + q2), -g * cos(q1 + q2))
    fel = p.m2 .* (a2b2 .- gb2)
    d2 = (-fel[1] / kt, -fel[2] / kt)
    return d1, d2
end

"""The chain's total mechanical energy: both bodies' KE, the CoM potential including the pivot
deflections (the composed pose is the *nominal* pose), and both pivot strain terms."""
function _mp7_dp_energy(columns, kt; p = _MP7_DP)
    KE = 0.5 .* (columns["B1/inertia/P[1]"] .^ 2 ./ p.j1 .+
                 columns["B1/inertia/P[2]"] .^ 2 ./ p.m1 .+
                 columns["B1/inertia/P[3]"] .^ 2 ./ p.m1) .+
         0.5 .* (columns["B2/inertia/P[1]"] .^ 2 ./ p.j2 .+
                 columns["B2/inertia/P[2]"] .^ 2 ./ p.m2 .+
                 columns["B2/inertia/P[3]"] .^ 2 ./ p.m2)
    e1, e2 = columns["J1/dout[1]"], columns["J1/dout[2]"]
    f1, f2 = columns["J2/dout[1]"], columns["J2/dout[2]"]
    q1, q2 = columns["J1/qout"], columns["J2/qout"]
    sh_y = sin.(q1) .* e1 .+ cos.(q1) .* e2
    el_y = sin.(q1 .+ q2) .* f1 .+ cos.(q1 .+ q2) .* f2
    PE = p.m1 * p.g .* (columns["C1/g[3]"] .+ sh_y) .+
         p.m2 * p.g .* (columns["C3/g[3]"] .+ sh_y .+ el_y)
    strain = 0.5 * kt .* (e1 .^ 2 .+ e2 .^ 2 .+ f1 .^ 2 .+ f2 .^ 2)
    return KE .+ PE .+ strain
end

"""The swing energy scale: the release potential energy above the hanging configuration."""
function _mp7_dp_swing(; p = _MP7_DP, q1 = _MP7_DP_Q1, q2 = _MP7_DP_Q2)
    v0 = p.m1 * p.g * p.r1 * sin(q1) +
         p.m2 * p.g * (p.l1 * sin(q1) + p.r2 * sin(q1 + q2))
    vmin = -(p.m1 * p.g * p.r1 + p.m2 * p.g * (p.l1 + p.r2))
    return v0 - vmin
end

"""A prismatic mass on a `SpringDamper`, optionally driven by a constant axial force."""
function _mp7_prismatic(; m = 2.0, k = 200.0, dmp = 0.0, force = nothing, phi = 0.0,
    q0 = 0.1, g0 = 0.0, t_end = 3.0, points = 3001)
    nodes = Any[
        bg_node("n1", "World", bg_ref("stdlib:multibond/GroundPlanar")),
        bg_node("n2", "Joint", bg_ref("stdlib:planar/Prismatic2D");
            params = Dict{String,Any}("phi" => string(phi), "kr" => "1.0e8",
                "kd" => "1.0e8", "q0" => string(q0))),
        bg_node("n3", "Body", bg_ref("stdlib:planar/RigidBody2D");
            params = Dict{String,Any}("m" => string(m), "J" => "1.0e-4", "g0" => string(g0))),
        bg_node("n4", "Spring", bg_ref("stdlib:translation/SpringDamper");
            params = Dict{String,Any}("k" => string(k), "d" => string(dmp)),
            starts = Dict{String,Any}("x" => string(q0))),
        bg_node("n5", "Anchor", bg_ref("stdlib:translation/Fixed")),
        bg_node("n6", "Axis", bg_junction("1")),
        bg_node("n7", "Pose", bg_ref("stdlib:planar/LocalPose2D")),
    ]
    conns = Any[
        bg_conn("c1", "bond", "n1", "p", "n2", "parent"),
        bg_conn("c2", "bond", "n2", "child", "n3", "p"),
        bg_conn("c3", "bond", "n2", "drive", "n6", nothing),
        bg_conn("c4", "bond", "n4", "a", "n6", nothing),
        bg_conn("c5", "wire", "n4", "b", "n5", "a"),
        bg_conn("c6", "signal", "n7", "g", "n3", "g"),
    ]
    if force !== nothing
        push!(nodes, bg_node("n8", "One", bg_ref("stdlib:sources/Constant");
            params = Dict{String,Any}("value" => "1.0")))
        push!(nodes, bg_node("n9", "Force", bg_ref("stdlib:translation/ForceSource");
            params = Dict{String,Any}("F" => string(force))))
        push!(nodes, bg_node("n10", "FAnchor", bg_ref("stdlib:translation/Fixed")))
        push!(conns, bg_conn("c7", "signal", "n8", "y", "n9", "u"))
        push!(conns, bg_conn("c8", "bond", "n9", "a", "n6", nothing))
        push!(conns, bg_conn("c9", "wire", "n9", "b", "n10", "a"))
    end
    return bg_model("PrismaticMassSpring", nodes, conns; t_end = t_end, points = points,
        reltol = 1.0e-9, abstol = 1.0e-11)
end

const _MP7_VEC_CONST = """
@block VecConst begin
    @parameters begin
        c1::Real = 0.0, [description = "Component 1"]
        c2::Real = 0.0, [description = "Component 2"]
        c3::Real = 0.0, [description = "Component 3"]
    end
    @outputs y::Vec{3}
    @equations begin
        y[1] ~ c1
        y[2] ~ c2
        y[3] ~ c3
    end
end
"""

"""A kinematic prismatic joint on a rotating parent: prescribed parent/child twists.

The parent spins at `omega`; the child is co-rotating at the equilibrium perpendicular
deflection `d` (so its velocity at the offset is `omega x (d m) = -omega*d*n`). No axial force
acts. `qdot` must then be 0: the parent-rotation transport term cancels the lever velocity
`-omega*d` in `n . Vrel`. Without it `qdot = -omega*d` and `q` drifts, which is the regression
this test pins."""
function _mp7_prismatic_rotating(; omega = 2.0, d = 1.0e-3, t_end = 0.1, points = 3)
    return bg_model("PrismaticRotatingParent", Any[
        bg_node("n1", "Up", Dict{String,Any}("inline" => Dict{String,Any}(
                "source" => _MP7_VEC_CONST));
            params = Dict{String,Any}("c1" => string(omega), "c2" => "0.0", "c3" => "0.0")),
        bg_node("n2", "Uc", Dict{String,Any}("inline" => Dict{String,Any}(
                "source" => _MP7_VEC_CONST));
            params = Dict{String,Any}("c1" => string(omega),
                "c2" => string(-omega * d), "c3" => "0.0")),
        bg_node("n3", "Sp", bg_ref("stdlib:multibond/SfPlanar")),
        bg_node("n4", "Sc", bg_ref("stdlib:multibond/SfPlanar")),
        bg_node("n5", "Joint", bg_ref("stdlib:planar/Prismatic2D");
            params = Dict{String,Any}("phi" => "0.0", "kr" => "1.0e6", "kd" => "0.0",
                "q0" => "0.0"),
            starts = Dict{String,Any}("d" => string(d))),
        bg_node("n6", "Axis", bg_junction("1")),
        bg_node("n7", "NoForce", bg_ref("stdlib:translation/ForceSource");
            params = Dict{String,Any}("F" => "0.0")),
        bg_node("n8", "Zero", bg_ref("stdlib:sources/Constant");
            params = Dict{String,Any}("value" => "0.0")),
        bg_node("n9", "Anchor", bg_ref("stdlib:translation/Fixed")),
    ], Any[
        bg_conn("c1", "signal", "n1", "y", "n3", "u"),
        bg_conn("c2", "signal", "n2", "y", "n4", "u"),
        bg_conn("c3", "bond", "n3", "p", "n5", "parent"),
        bg_conn("c4", "bond", "n4", "p", "n5", "child"),
        bg_conn("c5", "bond", "n5", "drive", "n6", nothing),
        bg_conn("c6", "bond", "n7", "a", "n6", nothing),
        bg_conn("c7", "wire", "n7", "b", "n9", "a"),
        bg_conn("c8", "signal", "n8", "y", "n7", "u"),
    ]; t_end = t_end, points = points, reltol = 1.0e-9, abstol = 1.0e-11)
end

"""A floating base with a zero or constant `ExternalWrenchPlanar` and no gravity."""
function _mp7_free(; P0 = (0.2, 0.5, -0.3), theta0 = 0.4, x0 = 0.1, y0 = -0.2,
    m = 2.0, j = 0.5, g0 = 0.0, wrench = (0.0, 0.0, 0.0), t_end = 10.0, points = 10001)
    return bg_model("FreeBody2D", Any[
        bg_node("n1", "Body", bg_ref("stdlib:planar/Free2D");
            params = Dict{String,Any}("m" => string(m), "J" => string(j), "g0" => string(g0),
                "theta0" => string(theta0), "x0" => string(x0), "y0" => string(y0)),
            starts = Dict{String,Any}("body/inertia/P" => "[$(P0[1]), $(P0[2]), $(P0[3])]")),
        bg_node("n2", "Wrench", bg_ref("stdlib:multibond/ExternalWrenchPlanar")),
        bg_node("n3", "Wr", bg_ref("stdlib:sources/Constant");
            params = Dict{String,Any}("value" => string(wrench[1]))),
        bg_node("n4", "Wx", bg_ref("stdlib:sources/Constant");
            params = Dict{String,Any}("value" => string(wrench[2]))),
        bg_node("n5", "Wy", bg_ref("stdlib:sources/Constant");
            params = Dict{String,Any}("value" => string(wrench[3]))),
    ], Any[
        bg_conn("c1", "bond", "n2", "p", "n1", "p"),
        bg_conn("c2", "signal", "n3", "y", "n2", "wr"),
        bg_conn("c3", "signal", "n4", "y", "n2", "wx"),
        bg_conn("c4", "signal", "n5", "y", "n2", "wy"),
    ]; t_end = t_end, points = points, reltol = 1.0e-9, abstol = 1.0e-11)
end

"""A pendulum on `Revolute2DFriction` with an initial body-frame momentum and zero gravity."""
function _mp7_friction(; P0 = (5.0e-4, 2.5, 0.0), fc = 0.0, fv = 0.1, tau = 0.0,
    t_end = 10.0, points = 1001)
    return bg_model("FrictionSpin", Any[
        bg_node("n1", "World", bg_ref("stdlib:multibond/GroundPlanar")),
        bg_node("n2", "Joint", bg_ref("stdlib:planar/Revolute2DFriction");
            params = Dict{String,Any}("rx" => "0.0", "ry" => "0.0", "kt" => "1.0e8",
                "bt" => "0.0", "Fc" => string(fc), "Fv" => string(fv),
                "v_eps" => "1.0e-3", "q0" => "0.0")),
        bg_node("n3", "Link", bg_ref("stdlib:planar/FixedJoint2D");
            params = Dict{String,Any}("x" => "0.0", "y" => "-0.5", "theta" => "0.0")),
        bg_node("n4", "Body", bg_ref("stdlib:planar/RigidBody2D");
            params = Dict{String,Any}("m" => "1.0", "J" => "1.0e-4", "g0" => "0.0"),
            starts = Dict{String,Any}("inertia/P" => "[$(P0[1]), $(P0[2]), $(P0[3])]")),
        bg_node("n5", "Torque", bg_ref("stdlib:bondgraph/Se");
            params = Dict{String,Any}("e" => string(tau))),
        bg_node("n6", "Pose", bg_ref("stdlib:planar/LocalPose2D")),
    ], Any[
        bg_conn("c1", "bond", "n1", "p", "n2", "parent"),
        bg_conn("c2", "bond", "n2", "child", "n3", "parent"),
        bg_conn("c3", "bond", "n3", "child", "n4", "p"),
        bg_conn("c4", "bond", "n5", "p", "n2", "drive"),
        bg_conn("c5", "signal", "n6", "g", "n4", "g"),
    ]; t_end = t_end, points = points, reltol = 1.0e-9, abstol = 1.0e-11)
end

"""A gravity-driven pendulum with a one-sided joint limit."""
function _mp7_limit(; q0 = 0.6, lower = -0.3, upper = 0.7, kl = 100.0, bl = 0.0,
    g0 = _MP7_G, t_end = 3.0, points = 3001)
    return bg_model("LimitPendulum", Any[
        bg_node("n1", "World", bg_ref("stdlib:multibond/GroundPlanar")),
        bg_node("n2", "Joint", bg_ref("stdlib:planar/Revolute2DLimit");
            params = Dict{String,Any}("rx" => "0.0", "ry" => "0.0", "kt" => "1.0e8",
                "bt" => "0.0", "lower" => string(lower), "upper" => string(upper),
                "kL" => string(kl), "bL" => string(bl), "delta" => "1.0e-3",
                "q0" => string(q0))),
        bg_node("n3", "Link", bg_ref("stdlib:planar/FixedJoint2D");
            params = Dict{String,Any}("x" => "0.0", "y" => "-0.5", "theta" => "0.0")),
        bg_node("n4", "Body", bg_ref("stdlib:planar/RigidBody2D");
            params = Dict{String,Any}("m" => "1.0", "J" => "1.0e-4", "g0" => string(g0))),
        bg_node("n5", "Local", bg_ref("stdlib:planar/LocalPose2D");
            params = Dict{String,Any}("x" => "0.0", "y" => "-0.5", "theta" => "0.0")),
        bg_node("n6", "Compose", bg_ref("stdlib:multibond/ComposePose2D")),
        bg_node("n7", "Torque", bg_ref("stdlib:bondgraph/Se");
            params = Dict{String,Any}("e" => "0.0")),
    ], Any[
        bg_conn("c1", "bond", "n1", "p", "n2", "parent"),
        bg_conn("c2", "bond", "n2", "child", "n3", "parent"),
        bg_conn("c3", "bond", "n3", "child", "n4", "p"),
        bg_conn("c4", "bond", "n7", "p", "n2", "drive"),
        bg_conn("c5", "signal", "n2", "pose", "n6", "gp"),
        bg_conn("c6", "signal", "n5", "g", "n6", "gl"),
        bg_conn("c7", "signal", "n6", "g", "n4", "g"),
    ]; t_end = t_end, points = points, reltol = 1.0e-9, abstol = 1.0e-11)
end

"""The rigid revolute variant on the same topology (DEC-MB-2's diagnostic set)."""
function _mp7_rigid_pendulum(; q0 = _MP7_Q0)
    return bg_model("RigidJointPendulum", Any[
        bg_node("n1", "World", bg_ref("stdlib:multibond/GroundPlanar")),
        bg_node("n2", "Joint", bg_ref("stdlib:planar/Revolute2DRigid");
            params = Dict{String,Any}("rx" => "0.0", "ry" => "0.0", "q0" => string(q0))),
        bg_node("n3", "Link", bg_ref("stdlib:planar/FixedJoint2D");
            params = Dict{String,Any}("x" => "0.0", "y" => "-0.5", "theta" => "0.0")),
        bg_node("n4", "Body", bg_ref("stdlib:planar/RigidBody2D");
            params = Dict{String,Any}("m" => "1.0", "J" => "1.0e-4", "g0" => "9.81")),
        bg_node("n5", "Local", bg_ref("stdlib:planar/LocalPose2D");
            params = Dict{String,Any}("x" => "0.0", "y" => "-0.5", "theta" => "0.0")),
        bg_node("n6", "Compose", bg_ref("stdlib:multibond/ComposePose2D")),
        bg_node("n7", "Torque", bg_ref("stdlib:bondgraph/Se");
            params = Dict{String,Any}("e" => "0.0")),
    ], Any[
        bg_conn("c1", "bond", "n1", "p", "n2", "parent"),
        bg_conn("c2", "bond", "n2", "child", "n3", "parent"),
        bg_conn("c3", "bond", "n3", "child", "n4", "p"),
        bg_conn("c4", "bond", "n7", "p", "n2", "drive"),
        bg_conn("c5", "signal", "n2", "pose", "n6", "gp"),
        bg_conn("c6", "signal", "n5", "g", "n6", "gl"),
        bg_conn("c7", "signal", "n6", "g", "n4", "g"),
    ]; t_end = 0.5, points = 51, reltol = 1.0e-9, abstol = 1.0e-11)
end

"""A fixed-base pendulum whose pose chain goes through `JointPose2D`, plus an integrated
truth (`PoseIntegrator2D` fed the body twist)."""
function _mp7_pose_truth(; q0 = 0.6, kt = _MP7_KT, t_end = 10.0, points = 10001)
    d = _mp7_pivot_d0(q0; kt = kt)
    return bg_model("PoseTruth", Any[
        bg_node("n1", "World", bg_ref("stdlib:multibond/GroundPlanar")),
        bg_node("n2", "Joint", bg_ref("stdlib:planar/Revolute2DCompliant");
            params = Dict{String,Any}("rx" => "0.0", "ry" => "0.0", "kt" => string(kt),
                "bt" => "0.0", "k" => "0.0", "b" => "0.0", "qrest" => "0.0",
                "q0" => string(q0)),
            starts = Dict{String,Any}("d" => "[$(d[1]), $(d[2])]")),
        bg_node("n3", "Link", bg_ref("stdlib:planar/FixedJoint2D");
            params = Dict{String,Any}("x" => "0.0", "y" => "-0.5", "theta" => "0.0")),
        bg_node("n4", "Body", bg_ref("stdlib:planar/RigidBody2D");
            params = Dict{String,Any}("m" => "1.0", "J" => "1.0e-4", "g0" => "9.81")),
        bg_node("n5", "JointPose", bg_ref("stdlib:planar/JointPose2D");
            params = Dict{String,Any}("rx" => "0.0", "ry" => "0.0", "theta0" => "0.0")),
        bg_node("n6", "Local", bg_ref("stdlib:planar/LocalPose2D");
            params = Dict{String,Any}("x" => "0.0", "y" => "-0.5", "theta" => "0.0")),
        bg_node("n7", "Compose", bg_ref("stdlib:multibond/ComposePose2D")),
        bg_node("n8", "Truth", bg_ref("stdlib:planar/PoseIntegrator2D");
            params = Dict{String,Any}("theta0" => string(q0),
                "x0" => string(0.5 * sin(q0)), "y0" => string(-0.5 * cos(q0)))),
        bg_node("n9", "Torque", bg_ref("stdlib:bondgraph/Se");
            params = Dict{String,Any}("e" => "0.0")),
    ], Any[
        bg_conn("c1", "bond", "n1", "p", "n2", "parent"),
        bg_conn("c2", "bond", "n2", "child", "n3", "parent"),
        bg_conn("c3", "bond", "n3", "child", "n4", "p"),
        bg_conn("c4", "bond", "n9", "p", "n2", "drive"),
        bg_conn("c5", "signal", "n2", "qout", "n5", "q"),
        bg_conn("c6", "signal", "n5", "g", "n7", "gp"),
        bg_conn("c7", "signal", "n6", "g", "n7", "gl"),
        bg_conn("c8", "signal", "n7", "g", "n4", "g"),
        bg_conn("c9", "signal", "n4", "V", "n8", "tw"),
    ]; t_end = t_end, points = points, reltol = 1.0e-9, abstol = 1.0e-11)
end

# ---------------------------------------------------------------------------------------
# The suite
# ---------------------------------------------------------------------------------------

@testset "J-MB7 planar mechanics" begin
    @testset "single pendulum: period, energy, q/qdot by path, no W201" begin
        starts = Dict{String,Any}("d" => "[$(_mp7_pivot_d0(_MP7_Q0)[1]), " *
                                              "$(_mp7_pivot_d0(_MP7_Q0)[2])]")
        doc = _mp7_pendulum(starts = starts, t_end = 10.0, points = 10001)
        checked = _mp7_check(doc)
        @test isempty(_mp7_errors(checked))
        @test _mp7_w201(checked) == 0

        columns, result, flat = bg_run(doc)
        @test result.status == "done"
        @test isempty(_mp7_errors(result))
        @test _mp7_w201(result) == 0
        for code in ("E101", "E102", "E103", "E106", "E900", "E901", "W201")
            @test !_mp7_has(result, code)
        end
        @test flat.stats.instances >= 3

        # `q` and `qdot` are recorded by path and are the joint's own states; `q` is the
        # integral of `qdot` from `q0`.
        q = columns["Joint/qout"]
        qdot = columns["Joint/qdout"]
        t = columns["time"]
        @test length(q) == 10001
        @test isapprox(q[1], _MP7_Q0; atol = 1e-9)
        @test isapprox(qdot[1], 0.0; atol = 1e-12)
        increments = (t[2:end] .- t[1:(end - 1)]) .* 0.5 .* (qdot[2:end] .+ qdot[1:(end - 1)])
        integral = vcat(_MP7_Q0, _MP7_Q0 .+ cumsum(increments))
        @test maximum(abs.(q .- integral)) <= 1.0e-6
        @test maximum(abs.(q)) ≈ _MP7_Q0 rtol = 1.0e-3

        # Period: amplitude-corrected physical (1e-5) and simple 2π√(L/g) (1e-3).
        period = _mp7_period(t, q)
        @test isapprox(period, _MP7_T_AMP; rtol = 1.0e-5)
        @test isapprox(period, _MP7_T_SIMPLE; rtol = 1.0e-3)
        # The peak rate is the energy-consistent ω_max of the physical pendulum.
        omega_max = sqrt(2 * _MP7_G * _MP7_L * (1 - cos(_MP7_Q0)) /
                         (_MP7_J + _MP7_M * _MP7_L^2))
        @test maximum(abs.(qdot)) ≈ omega_max rtol = 1.0e-5

        # Energy: KE from the recorded momentum, the CoM height including the pivot
        # deflection, and the pivot strain.
        d1 = columns["Joint/dout[1]"]
        d2 = columns["Joint/dout[2]"]
        KE = 0.5 .* (columns["Body/inertia/P[1]"] .^ 2 ./ _MP7_J .+
                     columns["Body/inertia/P[2]"] .^ 2 ./ _MP7_M .+
                     columns["Body/inertia/P[3]"] .^ 2 ./ _MP7_M)
        h = columns["Compose/g[3]"] .+ sin.(q) .* d1 .+ cos.(q) .* d2
        E = KE .+ _MP7_M * _MP7_G .* h .+ 0.5 * _MP7_KT .* (d1 .^ 2 .+ d2 .^ 2)
        drift = maximum(abs.(E .- E[1]))
        @test drift <= 1.0e-6 * _MP7_SWING
        println("J-MB7 pendulum: period = ", period, " s (amplitude-corrected ",
            _MP7_T_AMP, ", simple ", _MP7_T_SIMPLE, "), energy drift = ", drift,
            " J = ", drift / _MP7_SWING, " of the swing")
    end

    @testset "double pendulum: compliance converges to the independent Lagrangian" begin
        ref, reference_convergence = _mp7_dp_reference()
        @test reference_convergence <= 1.0e-9
        swing = _mp7_dp_swing()
        @test swing > 2.0

        # Structural signature of the chain: 12 differential states, no dummy derivative.
        flat = Compile.flatten(IR.parse_model(_mp7_double(kt = 1.0e8)))
        @test isempty(flat.diagnostics)
        lowered = BGSim.lower_model(flat; t_start = 0.0, t_end = 0.1)
        unknowns = ModelingToolkit.unknowns(lowered.model.system)
        @test length(unknowns) == 12
        @test length(ModelingToolkit.collect_differential_variables(lowered.model.system)) == 12
        @test isempty([string(u) for u in unknowns if occursin(Char(0x02cd), string(u))])

        errors = Float64[]
        at_one = Float64[]
        ratios = Float64[]
        drift = Float64[]
        for kt in (1.0e6, 1.0e7, 1.0e8)
            doc = _mp7_double(kt = kt)
            checked = _mp7_check(doc)
            @test isempty(_mp7_errors(checked))
            @test _mp7_w201(checked) == 0
            columns, result, _ = bg_run(doc)
            @test result.status == "done"
            @test _mp7_w201(result) == 0

            t = columns["time"]
            @test maximum(abs.(t .- range(0.0, _MP7_DP_T; length = _MP7_DP_POINTS))) <= 1e-12
            q1 = columns["J1/qout"]
            q2 = columns["J2/qout"]
            # The model really is the reference chain: the composed poses are the analytic
            # forward kinematics of the measured joint angles.
            x1 = _MP7_DP.r1 .* cos.(q1)
            y1 = _MP7_DP.r1 .* sin.(q1)
            x2 = _MP7_DP.l1 .* cos.(q1) .+ _MP7_DP.r2 .* cos.(q1 .+ q2)
            y2 = _MP7_DP.l1 .* sin.(q1) .+ _MP7_DP.r2 .* sin.(q1 .+ q2)
            @test maximum(abs.(columns["C1/g[2]"] .- x1)) <= 1e-12
            @test maximum(abs.(columns["C1/g[3]"] .- y1)) <= 1e-12
            @test maximum(abs.(columns["C3/g[2]"] .- x2)) <= 1e-12
            @test maximum(abs.(columns["C3/g[3]"] .- y2)) <= 1e-12

            # The rigid reference error over the trajectory and at the fixed time t = 1 s.
            err = max(maximum(abs.(q1 .- [y[1] for y in ref])),
                maximum(abs.(q2 .- [y[2] for y in ref])))
            i1 = findfirst(x -> abs(x - 1.0) < 1e-12, t)
            err1 = max(abs(q1[i1] - ref[i1][1]), abs(q2[i1] - ref[i1][2]))
            push!(errors, err)
            push!(at_one, err1)

            E = _mp7_dp_energy(columns, kt)
            push!(drift, maximum(abs.(E .- E[1])))
            println("J-MB7 double: kt = ", kt, " trajectory error = ", err,
                " rad, t = 1 s error = ", err1, ", energy drift = ", drift[end],
                " J = ", drift[end] / swing, " of the swing")
        end
        for k in 1:2
            push!(ratios, errors[k] / errors[k + 1])
            @test errors[k + 1] < errors[k]
            @test 8.0 <= ratios[k] <= 12.0          # the error is O(1/kt): one decade, 10x
            @test at_one[k + 1] < at_one[k]
            @test 8.0 <= at_one[k] / at_one[k + 1] <= 12.0
        end
        @test errors[end] <= 1.0e-5
        for ratio in ratios
            println("J-MB7 double: error ratio per decade = ", ratio)
        end

        # One decade stiffer reaches the plan's 1e-6 integrated tolerance.
        doc = _mp7_double(kt = 1.0e9)
        @test _mp7_w201(_mp7_check(doc)) == 0
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        @test _mp7_w201(result) == 0
        q1 = columns["J1/qout"]
        q2 = columns["J2/qout"]
        err9 = max(maximum(abs.(q1 .- [y[1] for y in ref])),
            maximum(abs.(q2 .- [y[2] for y in ref])))
        @test err9 <= 1.0e-6
        @test err9 < errors[end]

        # Energy: the deflection-corrected budget (momentum KE, CoM potential at the nominal
        # composed pose plus the pivot deflections propagated through the chain, and
        # 1/2 kt |d|^2). This is also the regression for the joint's `d` kinematics: `d` lives
        # in the rotating child frame, so its transport term must use the child's **absolute**
        # angular rate `child.f[1]`, not the relative joint rate. With the relative rate the
        # second link integrated the wrong displacement and this budget drifted by 2.1e-5 of
        # the swing at kt = 1e6; the single pendulum cannot see it (its parent is ground).
        @test all(drift .<= 1.0e-6 * swing)
        E9 = _mp7_dp_energy(columns, 1.0e9)
        @test maximum(abs.(E9 .- E9[1])) <= 1.0e-6 * swing
        println("J-MB7 double: reference RK4 convergence = ", reference_convergence,
            ", swing = ", swing, " J, energy drift ratio at kt = 1e6..1e9 = ",
            [d / swing for d in drift], " / ", maximum(abs.(E9 .- E9[1])) / swing,
            ", kt = 1e9 trajectory error = ", err9)
    end

    @testset "prismatic: Translation drive, mass-spring period and force equilibrium" begin
        # D-MB8: the drive carries a force and a velocity, never a torque.
        block = only([b for b in Library.load_stdlib()
                      if b.ref == "stdlib:planar/Prismatic2D"])
        drive = only([p for p in block.interface.ports if p.name == "drive"])
        @test drive.domain == "Translation"
        env = Units.unit_env(block.ast)
        @test env.labels[Symbol("drive.e")] == "N"
        @test env.labels[Symbol("drive.f")] == "m/s"

        # Undamped: x(t) = A cos(ω t) with ω = √(k/m), exact for a linear spring.
        doc = _mp7_prismatic(k = 200.0, dmp = 0.0, t_end = 3.0, points = 3001)
        checked = _mp7_check(doc)
        @test isempty(_mp7_errors(checked))
        @test !_mp7_has(checked, "E006")
        @test _mp7_w201(checked) == 0
        columns, result, flat = bg_run(doc)
        @test result.status == "done"
        @test isempty(_mp7_errors(result))
        @test _mp7_w201(result) == 0
        @test flat.stats.equations > 0
        period = _mp7_period(columns["time"], columns["Joint/qout"])
        analytic = 2 * pi * sqrt(2.0 / 200.0)
        @test isapprox(period, analytic; rtol = 1.0e-3)
        @test all(isapprox.(columns["Joint/pose[2]"], columns["Joint/qout"]; atol = 1e-12))
        @test all(abs.(columns["Joint/pose[3]"]) .<= 1e-10)
        @test maximum(abs.(columns["Joint/dout"])) <= 1e-8
        @test maximum(abs.(columns["Joint/drout"])) <= 1e-8

        # Damped and loaded: a constant force F shifts the equilibrium to q = -F/k (the drive
        # effort is `drive.e = -tau`, so a positive physical force pushes the coordinate
        # negative) and the damped period is 2π/√(k/m - (c/2m)²).
        force = 20.0
        doc = _mp7_prismatic(k = 200.0, dmp = 4.0, force = force, t_end = 20.0, points = 2001)
        checked = _mp7_check(doc)
        @test isempty(_mp7_errors(checked))
        @test _mp7_w201(checked) == 0
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        @test _mp7_w201(result) == 0
        q = columns["Joint/qout"]
        @test isapprox(q[end], -force / 200.0; atol = 1.0e-4)
        @test abs(columns["Joint/qdout"][end]) <= 1.0e-5
        shift = q .+ force / 200.0
        damped = 2 * pi / sqrt(200.0 / 2.0 - (4.0 / (2 * 2.0))^2)
        measured = _mp7_period(columns["time"], shift)
        @test isapprox(measured, damped; rtol = 1.0e-3)
        println("J-MB7 prismatic: period = ", period, " s (analytic ", analytic,
            "), damped period = ", measured, " (analytic ", damped, "), q_ss = ", q[end],
            " (analytic ", -force / 200.0, ")")
    end

    @testset "prismatic on a spinning parent: no axial drift from the deflection" begin
        # Regression for the transport term: the qdot projection must add back the lever
        # velocity `parent.f[1]*d` of the perpendicular deflection, or q drifts at -omega*d.
        doc = _mp7_prismatic_rotating()
        checked = _mp7_check(doc)
        @test isempty(_mp7_errors(checked))
        @test _mp7_w201(checked) == 0
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        @test _mp7_w201(result) == 0
        drift = maximum(abs.(columns["Joint/qout"]))
        rate = maximum(abs.(columns["Joint/qdout"]))
        d = columns["Joint/dout"]
        println("J-MB7 rotating-parent prismatic: max |q| = ", drift, ", max |qdot| = ", rate,
            ", d = ", sum(d) / length(d), " (start 1e-3)")
        @test rate <= 1.0e-9
        @test abs(sum(d) / length(d) - 1.0e-3) <= 1.0e-12   # the deflection is held
        @test drift <= 1.0e-9
    end

    @testset "free body: exact SE(2) screw and world momentum over 10 s" begin
        g0 = BGSim.SE2(0.4, 0.1, -0.2)
        # Pure rotation and pure translation have a constant *body* twist, so the pose is
        # exactly g(t) = g0 exp(V t).
        for (P0, label) in (((0.2, 0.0, 0.0), "rotation"), ((0.0, 0.5, -0.3), "translation"))
            doc = _mp7_free(P0 = P0, t_end = 10.0, points = 10001)
            @test _mp7_w201(_mp7_check(doc)) == 0
            columns, result, _ = bg_run(doc)
            @test result.status == "done"
            @test _mp7_w201(result) == 0
            V = (P0[1] / 0.5, P0[2] / 2.0, P0[3] / 2.0)
            worst = 0.0
            for (i, tt) in enumerate(columns["time"])
                exact = g0 * BGSim.exp(BGSim.Twist{3}(V[1] * tt, V[2] * tt, V[3] * tt))
                got = (columns["Body/pose/g[1]"][i], columns["Body/pose/g[2]"][i],
                    columns["Body/pose/g[3]"][i])
                worst = max(worst, maximum(abs.(got .- BGSim.Mech.chart(exact))))
            end
            @test worst <= 1.0e-6
            println("J-MB7 free body (", label, ") over 10 s: max pose error = ", worst)
        end

        # General case: the body twist is not constant, but the *world* linear momentum is,
        # so theta advances uniformly and the CoM travels a straight line at constant speed;
        # the world angular momentum about the origin is conserved too.
        doc = _mp7_free(t_end = 10.0, points = 10001)
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        t = columns["time"]
        theta = columns["Body/pose/g[1]"]
        vb = (0.2 / 0.5, 0.5 / 2.0, -0.3 / 2.0)
        vx = cos(0.4) * vb[2] - sin(0.4) * vb[3]
        vy = sin(0.4) * vb[2] + cos(0.4) * vb[3]
        @test maximum(abs.(theta .- (0.4 .+ vb[1] .* t))) <= 1.0e-9
        @test maximum(abs.(columns["Body/pose/g[2]"] .- (0.1 .+ vx .* t))) <= 1.0e-6
        @test maximum(abs.(columns["Body/pose/g[3]"] .- (-0.2 .+ vy .* t))) <= 1.0e-6
        px = 2.0 .* (cos.(theta) .* columns["Body/body/inertia/p.f[2]"] .-
                     sin.(theta) .* columns["Body/body/inertia/p.f[3]"])
        py = 2.0 .* (sin.(theta) .* columns["Body/body/inertia/p.f[2]"] .+
                     cos.(theta) .* columns["Body/body/inertia/p.f[3]"])
        H = 0.5 .* columns["Body/body/inertia/p.f[1]"] .+
            columns["Body/pose/g[2]"] .* py .- columns["Body/pose/g[3]"] .* px
        @test maximum(abs.(px .- px[1])) <= 1.0e-9
        @test maximum(abs.(py .- py[1])) <= 1.0e-9
        @test maximum(abs.(H .- H[1])) <= 1.0e-9
        # The free body's gravity reads the *integrated* pose, not a copy.
        @test all(all(columns["Body/body/gravity/g[$k]"] .== columns["Body/pose/g[$k]"])
                  for k in 1:3)
        println("J-MB7 free body: world momentum drift px/py/H = ",
            maximum(abs.(px .- px[1])), " / ", maximum(abs.(py .- py[1])), " / ",
            maximum(abs.(H .- H[1])))
    end

    @testset "applied wrench: a = F/m, alpha = tau/J, P(t) = P0 + W_ext t" begin
        # Force-only case: a constant physical wrench (0, 3, -1) N on a 2 kg, J = 0.5 body.
        theta0 = 0.3
        doc = _mp7_free(P0 = (0.0, 0.0, 0.0), theta0 = theta0, x0 = 0.1, y0 = -0.2,
            wrench = (0.0, 3.0, -1.0), t_end = 2.0, points = 2001)
        @test _mp7_w201(_mp7_check(doc)) == 0
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        @test _mp7_w201(result) == 0
        t = columns["time"]
        # FIX-MB-4's sign: the input is the physical wrench and dP/dt = +W_ext.
        @test isapprox(columns["Body/body/inertia/P[2]"][end], 3.0 * 2.0; rtol = 1e-9)
        @test isapprox(columns["Body/body/inertia/P[3]"][end], -1.0 * 2.0; rtol = 1e-9)
        @test isapprox(columns["Body/body/inertia/P[1]"][end], 0.0; atol = 1e-12)
        ax = 3.0 / 2.0 * cos(theta0) - (-1.0 / 2.0) * sin(theta0)
        ay = 3.0 / 2.0 * sin(theta0) + (-1.0 / 2.0) * cos(theta0)
        @test all(isapprox.(columns["Body/pose/g[1]"], theta0; atol = 1e-12))
        @test isapprox(columns["Body/pose/g[2]"][end], 0.1 + 0.5 * ax * 2.0^2; atol = 1e-9)
        @test isapprox(columns["Body/pose/g[3]"][end], -0.2 + 0.5 * ay * 2.0^2; atol = 1e-9)
        # The linear momentum is exactly P0 + W t at every sample.
        @test maximum(abs.(columns["Body/body/inertia/P[2]"] .- 3.0 .* t)) <= 1e-9
        @test maximum(abs.(columns["Body/body/inertia/P[3]"] .- (-1.0) .* t)) <= 1e-9

        # Torque-only case: alpha = tau/J = 4 rad/s^2, theta = theta0 + 1/2 alpha t^2, and
        # the position does not move.
        doc = _mp7_free(P0 = (0.0, 0.0, 0.0), theta0 = theta0, x0 = 0.1, y0 = -0.2,
            wrench = (2.0, 0.0, 0.0), t_end = 2.0, points = 2001)
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        t = columns["time"]
        @test isapprox(columns["Body/body/inertia/P[1]"][end], 2.0 * 2.0; rtol = 1e-9)
        @test maximum(abs.(columns["Body/body/inertia/P[1]"] .- 2.0 .* t)) <= 1e-9
        @test isapprox(columns["Body/pose/g[1]"][end],
            theta0 + 0.5 * (2.0 / 0.5) * 2.0^2; rtol = 1e-10)
        @test all(isapprox.(columns["Body/pose/g[2]"], 0.1; atol = 1e-12))
        @test all(isapprox.(columns["Body/pose/g[3]"], -0.2; atol = 1e-12))
        println("J-MB7 wrench: a = ", ax, " / ", ay, " m/s^2 (F/m), alpha = ",
            2.0 / 0.5, " rad/s^2, theta(2) = ", columns["Body/pose/g[1]"][end])
    end

    @testset "friction: monotone decay, dissipative sign, stick/slide threshold" begin
        # A link spun at 5 rad/s about its pivot: the body momentum is consistent with the
        # rigid rotation (v_CoM = ω × r), so there is no pivot shock.
        Jp = 1.0e-4 + 1.0 * 0.25
        doc = _mp7_friction(P0 = (5.0e-4, 2.5, 0.0), fv = 0.1, fc = 0.0, t_end = 10.0,
            points = 1001)
        @test _mp7_w201(_mp7_check(doc)) == 0
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        @test _mp7_w201(result) == 0
        w = columns["Joint/qdout"]
        t = columns["time"]
        @test isapprox(w[1], 5.0; atol = 1e-9)
        @test all(diff(w) .<= 0.0)                      # monotone decay
        @test isapprox(w[end], 5.0 * exp(-0.1 * 10.0 / Jp); rtol = 1e-3)
        tau_f = columns["Joint/tauout"]
        @test all(tau_f .>= -1.0e-12)
        @test all(tau_f .* w .>= -1.0e-12)              # τ_f has the sign of ω
        @test all(-tau_f .* w .<= 1.0e-12)              # dissipated power -τ_f ω ≤ 0
        KE = 0.5 .* (columns["Body/inertia/P[1]"] .^ 2 ./ 1.0e-4 .+
                     columns["Body/inertia/P[2]"] .^ 2 ./ 1.0 .+
                     columns["Body/inertia/P[3]"] .^ 2 ./ 1.0)
        strain = 0.5 * 1.0e8 .* (columns["Joint/dout[1]"] .^ 2 .+
                                 columns["Joint/dout[2]"] .^ 2)
        energy = KE .+ strain
        @test energy[end] < energy[1]
        @test maximum(diff(energy)) <= 1.0e-9 * energy[1]
        println("J-MB7 friction (viscous): omega(10 s) = ", w[end], " (analytic ",
            5.0 * exp(-0.1 * 10.0 / Jp), "), energy ", energy[1], " -> ", energy[end])

        # Viscous + regularised Coulomb: still monotone and dissipative, and it stops sooner.
        doc = _mp7_friction(P0 = (5.0e-4, 2.5, 0.0), fv = 0.1, fc = 0.5, t_end = 10.0,
            points = 1001)
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        wc = columns["Joint/qdout"]
        @test isapprox(wc[1], 5.0; atol = 1e-9)
        @test all(diff(wc) .<= 1e-9)
        @test wc[end] < w[end]
        @test all(columns["Joint/tauout"] .>= -1.0e-12)
        @test all(-columns["Joint/tauout"] .* wc .<= 1.0e-9)

        # Stick/slide: a torque below Fc holds the link (regularised creep v_eps atanh(τ/Fc)),
        # above Fc it slips. Fv = 0 so the Coulomb term is the whole friction.
        doc = _mp7_friction(P0 = (0.0, 0.0, 0.0), fv = 0.0, fc = 0.5, tau = 0.4,
            t_end = 2.0, points = 2001)
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        @test maximum(abs.(columns["Joint/qdout"])) <= 5.0e-3
        @test maximum(abs.(columns["Joint/qout"])) <= 5.0e-3
        creep = 1.0e-3 * atanh(0.4 / 0.5)
        @test isapprox(columns["Joint/qdout"][end], creep; rtol = 0.05)
        doc = _mp7_friction(P0 = (0.0, 0.0, 0.0), fv = 0.0, fc = 0.5, tau = 0.6,
            t_end = 3.0, points = 3001)
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        @test columns["Joint/qdout"][end] > 1.0        # slips and accelerates
        println("J-MB7 friction: stick creep = ", creep, " rad/s, slide rate(2 s) = ",
            columns["Joint/qdout"][end])
    end

    @testset "limits: zero effort inside, one-sided stop outside, elastic rebound" begin
        lower, upper, kl = -0.3, 0.7, 100.0
        doc = _mp7_limit(q0 = 0.6, lower = lower, upper = upper, kl = kl, bl = 0.0,
            t_end = 3.0, points = 3001)
        checked = _mp7_check(doc)
        @test isempty(_mp7_errors(checked))
        @test _mp7_w201(checked) == 0
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        @test _mp7_w201(result) == 0
        @test !_mp7_has(result, "W206")
        q = columns["Joint/qout"]
        tau = columns["Joint/tauout"]

        # Inside [lower, upper] the stop contributes exactly zero.
        inside = (q .> lower + 0.05) .& (q .< upper - 0.05)
        @test all(abs.(tau[inside]) .<= 1.0e-12)
        # The swing reaches the lower stop and the stop torque is negative there.
        @test minimum(q) < lower
        contact = q .< lower - 0.01
        @test any(contact)
        @test all(tau[contact] .< 0.0)
        # Outside the stop, tau = kL (q - lower) (bL = 0): the one-sided spring.
        @test maximum(abs.(tau[contact] .- kl .* (q[contact] .- lower))) <=
              0.02 * maximum(abs.(tau[contact]))
        @test isapprox(tau[argmin(q)], kl * (minimum(q) - lower); rtol = 0.02)

        # Elastic rebound (bL = 0): the body comes back above the limit and re-reaches the
        # release angle, i.e. the stop returns the energy.
        first_contact = findfirst(x -> x < lower, q)
        @test first_contact !== nothing
        @test maximum(q[first_contact:end]) > 0.5
        @test abs(maximum(q[first_contact:end]) - 0.6) <= 1.0e-4
        println("J-MB7 limit: q range = ", (minimum(q), maximum(q)), ", stop torque range = ",
            (minimum(tau), maximum(tau)), ", rebound to ", maximum(q[first_contact:end]))
    end

    @testset "W201: absent with compliance; the rigid set in one place" begin
        # Every compliant model of this suite: no W201 in model.check and none in the run.
        compliant = Dict(
            "pendulum" => _mp7_pendulum(starts = Dict{String,Any}(
                "d" => "[$(_mp7_pivot_d0(_MP7_Q0)[1]), $(_mp7_pivot_d0(_MP7_Q0)[2])]"),
                t_end = 1.0, points = 101),
            "double" => _mp7_double(kt = 1.0e8, t_end = 0.4, points = 41),
            "prismatic" => _mp7_prismatic(force = 20.0, t_end = 1.0, points = 101),
            "free" => _mp7_free(t_end = 1.0, points = 101),
            "wrench" => _mp7_free(wrench = (1.0, 2.0, 3.0), t_end = 1.0, points = 101),
            "friction" => _mp7_friction(t_end = 1.0, points = 101),
            "limit" => _mp7_limit(t_end = 1.0, points = 101),
            "pose" => _mp7_pose_truth(t_end = 1.0, points = 101),
            "posechain" => _mp7_pendulum(posechain = true, t_end = 1.0, points = 101),
        )
        for (name, doc) in compliant
            checked = _mp7_check(doc)
            @test isempty(_mp7_errors(checked))
            @test _mp7_w201(checked) == 0
            columns, result, _ = bg_run(doc)
            @test result.status == "done"
            @test _mp7_w201(result) == 0
        end
        println("J-MB7 W201: 0 in model.check and 0 in the run for ",
            length(compliant), " compliant models")

        # The rigid variant with 1 DOF on a 3-DOF body: DEC-MB-2's measured set.
        rigid = _mp7_rigid_pendulum()
        checked = _mp7_check(rigid)
        @test isempty(_mp7_errors(checked))
        @test _mp7_w201(checked) == 1               # one diagnostic, all three components
        flat = Compile.flatten(IR.parse_model(rigid))
        @test isempty(_mp7_errors(flat))
        lowered = BGSim.lower_model(flat; t_start = 0.0, t_end = 0.5)
        warnings = [d for d in Compile.post_compile_warnings(flat, lowered.model.system)
                    if d.code == "W201"]
        @test length(warnings) == 3
        @test all(d -> d.path == "Body/inertia", warnings)
        for k in 1:3
            @test any(d -> occursin("P[$k]", d.message), warnings)
        end
        unknown_names = string.(ModelingToolkit.unknowns(lowered.model.system))
        dummies = [n for n in unknown_names if occursin(Char(0x02cd), n)]
        @test length(dummies) == 3
        @test count(n -> occursin("Joint/xform/b.f[", n), dummies) == 2
        @test count(n -> occursin("Body/flow/p.f[1]", n), dummies) == 1
        @test length(ModelingToolkit.collect_differential_variables(lowered.model.system)) == 2
        columns, result, _ = bg_run(rigid)
        @test result.status == "failed"
        @test any(d -> d.code in ("E103", "E901"), result.diagnostics)
        println("J-MB7 rigid variant: 1 model-check W201, 3 post-compile W201 (",
            [d.message for d in warnings], "), dummies ", dummies, ", run ",
            result.status)
    end

    @testset "fixed-base pose composition vs integrated truth over 10 s" begin
        doc = _mp7_pose_truth(q0 = 0.6, kt = _MP7_KT, t_end = 10.0, points = 10001)
        checked = _mp7_check(doc)
        @test isempty(_mp7_errors(checked))
        @test _mp7_w201(checked) == 0
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        @test _mp7_w201(result) == 0
        q = columns["Joint/qout"]
        # The composed pose (JointPose2D ∘ LocalPose2D) is the analytic CoM pose.
        @test maximum(abs.(columns["Compose/g[1]"] .- q)) <= 1e-12
        @test maximum(abs.(columns["Compose/g[2]"] .- 0.5 .* sin.(q))) <= 1e-12
        @test maximum(abs.(columns["Compose/g[3]"] .+ 0.5 .* cos.(q))) <= 1e-12
        # The integrated truth on the body twist agrees over the whole 10 s: no drift.
        errors = [maximum(abs.(columns["Compose/g[$k]"] .- columns["Truth/g[$k]"]))
                  for k in 1:3]
        @test maximum(errors) <= 1.0e-6
        @test maximum(abs.(columns["Compose/g[$k]"][end] - columns["Truth/g[$k]"][end])
                      for k in 1:3) <= 1.0e-6
        # Gravity reads the composed pose in the fixed-base chain (and the integrated pose in
        # the free body, asserted above).
        @test all(all(columns["Body/gravity/g[$k]"] .== columns["Compose/g[$k]"])
                  for k in 1:3)
        println("J-MB7 pose: composed vs integrated max diff over 10 s = ",
            maximum(errors), " (per component ", errors, ")")
    end
end
