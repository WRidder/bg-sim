# Work package J-MB6: planar bodies, joints and pose handling (plan 6, row J-MB6).
#
# The acceptance is the plan 5.2 flat picture on the existing backend:
#   * `RigidBody2D` is a *composite* whose single port is the body's 1-junction; opening it
#     shows `IPlanar`, `CoriolisPlanar` (fed by `IPlanar/Pm`) and `GravityPlanar` (fed by the
#     composed pose), no opaque body;
#   * `Ground -> Revolute2D -> FixedJoint2D -> RigidBody2D` with the pose composed from `q`
#     reproduces the J-MB4 pendulum period and energy, through `simulate` and the worker;
#   * `FIX-MB-2`: the same joint runs at any link mounting angle (theta = 0, 0.3, pi/2) with
#     the same period, 6 compiled states and no dummy derivative (the J-MB4 slice only ran
#     near +-pi/2 because `FixedTransform2D` left the pivot x-force as a tearing variable);
#   * the compliant pivot converges to the rigid period as `kt -> Inf`; the rigid variant
#     (`Revolute2DRigid`) reports exactly two W201 by design (DEC-MB-2) and the compliant one
#     none;
#   * `Prismatic2D` carries a `Translation` drive (D-MB8), `Free2D`/`PoseIntegrator2D`
#     integrate a floating-base pose (D-MB6), and the friction/limit variants are per-joint
#     variants (D-MB9).
#
# All helpers are `_pm_`-prefixed: the test files share `Main`.
using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import BGSim.Library
import BGSim.Units
import BGSim.Flat
import JSON3
import ModelingToolkit
using Sockets
import BGSim: Worker

const _PM_FIXTURE = joinpath(@__DIR__, "fixtures", "planar", "pendulum.json")
const _PM_L = 0.5
const _PM_M = 1.0
const _PM_J = 1.0e-4
const _PM_G = 9.81
const _PM_KT = 1.0e8
const _PM_Q0 = 0.01
const _PM_L_EFF = _PM_L + _PM_M * _PM_G * cos(_PM_Q0) / _PM_KT
const _PM_T_SIMPLE = 2 * pi * sqrt(_PM_L / _PM_G)
const _PM_T_RIGID = 2 * pi * sqrt((_PM_J + _PM_M * _PM_L^2) / (_PM_M * _PM_G * _PM_L))
const _PM_T_LINEAR =
    2 * pi * sqrt((_PM_J + _PM_M * _PM_L_EFF^2) / (_PM_M * _PM_G * _PM_L_EFF))
const _PM_T_AMP = _PM_T_LINEAR * (1 + _PM_Q0^2 / 16)
const _PM_T_RIGID_AMP = _PM_T_RIGID * (1 + _PM_Q0^2 / 16)
const _PM_SWING = _PM_M * _PM_G * _PM_L * (1 - cos(_PM_Q0))

# ---------------------------------------------------------------------------------------
# Model-document helpers
# ---------------------------------------------------------------------------------------

_pm_ep(node, port) = port === nothing ? Dict{String,Any}("node" => node) :
                     Dict{String,Any}("node" => node, "port" => port)

function _pm_node(id, name, block; params = Dict{String,Any}(),
    starts = Dict{String,Any}())
    return Dict{String,Any}(
        "id" => id, "name" => name, "block" => block,
        "position" => Dict{String,Any}("x" => 0.0, "y" => 0.0),
        "params" => params, "constants" => Dict{String,Any}(), "starts" => starts,
    )
end

_pm_ref(r) = Dict{String,Any}("ref" => r)
_pm_junction(k) = Dict{String,Any}("junction" => k)
_pm_inline(source) = Dict{String,Any}("inline" => Dict{String,Any}("source" => source))

function _pm_conn(id, kind, from_node, from_port, to_node, to_port = nothing)
    return Dict{String,Any}("id" => id, "kind" => kind,
        "from" => _pm_ep(from_node, from_port), "to" => _pm_ep(to_node, to_port))
end

function _pm_doc(name, nodes, connections; t_end = 4.0, points = 4001,
    solver = "Rodas5P", reltol = 1.0e-9, abstol = 1.0e-11)
    return Dict{String,Any}(
        "format" => "bgsim.model", "language" => "0.1.0", "name" => name,
        "diagram" => Dict{String,Any}("nodes" => Any[nodes...],
            "connections" => Any[connections...], "subsystemPorts" => Any[],
            "annotations" => Any[]),
        "settings" => Dict{String,Any}("t_start" => 0.0, "t_end" => t_end,
            "solver" => solver, "reltol" => reltol, "abstol" => abstol,
            "max_step" => nothing,
            "output" => Dict{String,Any}("mode" => "points", "points" => points),
            "event_limit" => 10000),
        "plots" => Any[], "scene" => nothing, "bindings" => Any[],
    )
end

_pm_load() = JSON3.read(read(_PM_FIXTURE, String), Dict{String,Any})
_pm_flat(doc) = Compile.flatten(IR.parse_model(doc))
_pm_check(doc) = Compile.model_check(IR.parse_model(doc))
_pm_errors(result) = [d for d in result.diagnostics if d.severity == "error"]
_pm_has(result, code) = any(d -> d.code == code, result.diagnostics)
_pm_codes(result) = sort(unique(d.code for d in result.diagnostics))

function _pm_run(doc; t_end = 4.0, points = 4001, reltol = 1.0e-9, abstol = 1.0e-11)
    flat = _pm_flat(doc)
    dir = mktempdir()
    result = simulate(flat; run_dir = dir,
        settings = BGSim.RunSettings(t_start = 0.0, t_end = t_end,
            solver = get(doc["settings"], "solver", "Rodas5P"), reltol = reltol,
            abstol = abstol,
            output = Dict{String,Any}("mode" => "points", "points" => points)))
    return result, dir
end

"""The columns file as `id => Vector{Float64}`, plus `"time"`."""
function _pm_columns(dir)
    m = JSON3.read(read(joinpath(dir, "manifest.json"), String))
    n = Int(m.time.n)
    nsig = length(m.signals)
    raw = read(joinpath(dir, "columns.f64"))
    @test length(raw) == 8 * n * (nsig + 1)
    columns = reshape(reinterpret(Float64, raw), (n, nsig + 1))
    out = Dict{String,Vector{Float64}}("time" => collect(columns[:, 1]))
    for (j, signal) in enumerate(m.signals)
        out[String(signal.id)] = collect(columns[:, j + 1])
    end
    return out
end

function _pm_upward_crossings(t, y)
    out = Float64[]
    for i in 1:(length(y) - 1)
        if y[i] < 0 && y[i + 1] >= 0
            push!(out, t[i] + (t[i + 1] - t[i]) * (-y[i]) / (y[i + 1] - y[i]))
        end
    end
    return out
end

"""The period of one oscillation from the second and third upward zero crossings."""
function _pm_period(t, y)
    crossings = _pm_upward_crossings(t, y)
    length(crossings) >= 3 || return NaN
    return crossings[3] - crossings[2]
end

"""The released-from-rest pivot deflection in the child frame at `q0` (J-MB4, FIX-MB3)."""
function _pm_d0(q0; kt = _PM_KT)
    d1 = -_PM_M * _PM_G * _PM_J / (_PM_J + _PM_M * _PM_L^2) * sin(q0) / kt
    d2 = -_PM_M * _PM_G * cos(q0) / kt
    return [d1, d2]
end

const _PM_BASE_JOINT = Dict(
    "stdlib:multibond/Revolute2D" => Dict{String,Any}(),
    "stdlib:planar/Revolute2DCompliant" => Dict{String,Any}("k" => "0.0", "b" => "0.0",
        "qrest" => "0.0"),
    "stdlib:planar/Revolute2DFriction" => Dict{String,Any}("Fc" => "0.0", "Fv" => "0.0"),
    "stdlib:planar/Revolute2DLimit" => Dict{String,Any}("lower" => "-1.0e6",
        "upper" => "1.0e6"),
)

"""
    _pm_pendulum(; theta, joint, kt, q0, m, j, g0, tau, dstart, extra)

`Ground -> joint -> FixedJoint2D -> RigidBody2D`, with the link pose composed from the joint
pose and the local mounting pose (`ComposePose2D`) and a torque `Se` on the joint drive.
`dstart` defaults to the released-from-rest pivot deflection; `extra` overrides joint
parameters.
"""
function _pm_pendulum(; theta = 0.0, joint = "stdlib:multibond/Revolute2D", kt = _PM_KT,
    q0 = _PM_Q0, m = _PM_M, j = _PM_J, g0 = _PM_G, tau = 0.0, dstart = nothing,
    extra = Dict{String,Any}())
    params = merge(Dict{String,Any}("rx" => "0.0", "ry" => "0.0", "kt" => string(kt),
        "bt" => "0.0", "q0" => string(q0)), get(_PM_BASE_JOINT, joint,
        Dict{String,Any}()), extra)
    start = dstart === nothing ? _pm_d0(q0; kt = kt) : dstart
    return _pm_doc("PlanarPendulum",
        Any[
            _pm_node("n1", "World", _pm_ref("stdlib:multibond/GroundPlanar")),
            _pm_node("n2", "Joint", _pm_ref(joint); params = params,
                starts = Dict{String,Any}("d" => "[$(start[1]), $(start[2])]")),
            _pm_node("n3", "Link", _pm_ref("stdlib:planar/FixedJoint2D");
                params = Dict{String,Any}("x" => "0.0", "y" => "-0.5",
                    "theta" => string(theta))),
            _pm_node("n4", "Body", _pm_ref("stdlib:planar/RigidBody2D");
                params = Dict{String,Any}("m" => string(m), "J" => string(j),
                    "g0" => string(g0))),
            _pm_node("n5", "Local", _pm_ref("stdlib:planar/LocalPose2D");
                params = Dict{String,Any}("x" => "0.0", "y" => "-0.5",
                    "theta" => string(theta))),
            _pm_node("n6", "Compose", _pm_ref("stdlib:multibond/ComposePose2D")),
            _pm_node("n7", "Torque", _pm_ref("stdlib:bondgraph/Se");
                params = Dict{String,Any}("e" => string(tau))),
        ],
        Any[
            _pm_conn("c1", "bond", "n1", "p", "n2", "parent"),
            _pm_conn("c2", "bond", "n2", "child", "n3", "parent"),
            _pm_conn("c3", "bond", "n3", "child", "n4", "p"),
            _pm_conn("c4", "bond", "n7", "p", "n2", "drive"),
            _pm_conn("c5", "signal", "n2", "pose", "n6", "gp"),
            _pm_conn("c6", "signal", "n5", "g", "n6", "gl"),
            _pm_conn("c7", "signal", "n6", "g", "n4", "g"),
        ])
end

"""
    _pm_prismatic(; m, k, phi, q0)

`Ground -> Prismatic2D -> RigidBody2D` with a translational spring between the joint drive and
a fixed anchor. The drive is a `Translation` port, so the spring is joined through a
`Translation` 1-junction (a wire between two concrete scalar ports is a direct port-to-port
connection; the junction is what makes the spring effort oppose the drive).
"""
function _pm_prismatic(; m = 2.0, k = 200.0, phi = 0.0, q0 = 0.1, g0 = 0.0)
    return _pm_doc("PrismaticMassSpring",
        Any[
            _pm_node("n1", "World", _pm_ref("stdlib:multibond/GroundPlanar")),
            _pm_node("n2", "Joint", _pm_ref("stdlib:planar/Prismatic2D");
                params = Dict{String,Any}("phi" => string(phi), "kr" => "1.0e8",
                    "kd" => "1.0e8", "q0" => string(q0))),
            _pm_node("n3", "Body", _pm_ref("stdlib:planar/RigidBody2D");
                params = Dict{String,Any}("m" => string(m), "J" => "1.0e-4",
                    "g0" => string(g0))),
            _pm_node("n4", "Spring", _pm_ref("stdlib:translation/Spring");
                params = Dict{String,Any}("k" => string(k)),
                starts = Dict{String,Any}("x" => string(q0))),
            _pm_node("n5", "Anchor", _pm_ref("stdlib:translation/Fixed")),
            _pm_node("n6", "Axis", _pm_junction("1")),
            _pm_node("n7", "Pose", _pm_ref("stdlib:planar/LocalPose2D")),
        ],
        Any[
            _pm_conn("c1", "bond", "n1", "p", "n2", "parent"),
            _pm_conn("c2", "bond", "n2", "child", "n3", "p"),
            _pm_conn("c3", "bond", "n2", "drive", "n6"),
            _pm_conn("c4", "bond", "n4", "a", "n6"),
            _pm_conn("c5", "wire", "n4", "b", "n5", "a"),
            _pm_conn("c6", "signal", "n7", "g", "n3", "g"),
        ])
end

"""
    _pm_free(; P0, theta0, x0, y0, m, j)

A floating base (`Free2D`) with an initial body-frame momentum and a zero external wrench.
With no gravity the body-frame twist is constant, so the pose is the exact SE(2) screw motion
`g(t) = g0 * exp(V t)`.
"""
function _pm_free(; P0 = (0.2, 0.5, -0.3), theta0 = 0.4, x0 = 0.1, y0 = -0.2,
    m = 2.0, j = 0.5, g0 = 0.0)
    return _pm_doc("FreeBody2D",
        Any[
            _pm_node("n1", "Body", _pm_ref("stdlib:planar/Free2D");
                params = Dict{String,Any}("m" => string(m), "J" => string(j),
                    "g0" => string(g0), "theta0" => string(theta0), "x0" => string(x0),
                    "y0" => string(y0)),
                starts = Dict{String,Any}(
                    "body/inertia/P" => "[$(P0[1]), $(P0[2]), $(P0[3])]")),            _pm_node("n2", "Wrench", _pm_ref("stdlib:multibond/ExternalWrenchPlanar")),
            _pm_node("n3", "Zero", _pm_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "0.0")),
        ],
        Any[
            _pm_conn("c1", "bond", "n2", "p", "n1", "p"),
            _pm_conn("c2", "signal", "n3", "y", "n2", "wr"),
            _pm_conn("c3", "signal", "n3", "y", "n2", "wx"),
            _pm_conn("c4", "signal", "n3", "y", "n2", "wy"),
        ])
end

"""
    _pm_chain2(; q1, q2, g0, joint)

A two-link planar chain on the J-MB6 composites:

    Ground -> Joint1 -> Link1 -> BodyJ1 (1-junction: Body1 + Joint2) -> Link2 -> BodyJ2

`Link1` is a `FixedJoint2D` with `x = 0.2` (the lever arm from the shoulder pivot to the
link-1 centre of mass) and `Link2` the same from the elbow; the elbow pivot is `rx = 0.2` in
the link-1 CoM frame. The pose chain is the plan 5.5 fixed-base composition
`C1 = Joint1.pose * Link1.pose`, `C2 = C1 * Joint2.pose`, `C3 = C2 * Link2.pose`,
`Tip = C3 * (0.3, 0)`. `joint` selects the compliant (default) or the rigid revolute variant,
so the same topology serves the ODE and the DAE diagnostics test.
"""
function _pm_chain2(; q1 = 0.4, q2 = -0.6, g0 = 0.0,
    joint = "stdlib:planar/Revolute2DCompliant")
    rigid = joint == "stdlib:planar/Revolute2DRigid"
    function joint_params(rx, q0)
        base = Dict{String,Any}("rx" => string(rx), "ry" => "0.0", "q0" => string(q0))
        rigid && return base
        return merge(base, Dict{String,Any}("kt" => string(_PM_KT), "bt" => "0.0",
            "k" => "0.0", "b" => "0.0", "qrest" => "0.0"))
    end
    return _pm_doc("TwoLinkChain",
        Any[
            _pm_node("n1", "World", _pm_ref("stdlib:multibond/GroundPlanar")),
            _pm_node("n2", "J1", _pm_ref(joint); params = joint_params(0.0, q1)),
            _pm_node("n3", "L1", _pm_ref("stdlib:planar/FixedJoint2D");
                params = Dict{String,Any}("x" => "0.2", "y" => "0.0", "theta" => "0.0")),
            _pm_node("n4", "BJ1", _pm_junction("1")),
            _pm_node("n5", "B1", _pm_ref("stdlib:planar/RigidBody2D");
                params = Dict{String,Any}("m" => "2.0", "J" => "0.026",
                    "g0" => string(g0))),
            _pm_node("n6", "J2", _pm_ref(joint); params = joint_params(0.2, q2)),
            _pm_node("n7", "L2", _pm_ref("stdlib:planar/FixedJoint2D");
                params = Dict{String,Any}("x" => "0.2", "y" => "0.0", "theta" => "0.0")),
            _pm_node("n8", "BJ2", _pm_junction("1")),
            _pm_node("n9", "B2", _pm_ref("stdlib:planar/RigidBody2D");
                params = Dict{String,Any}("m" => "1.5", "J" => "0.015",
                    "g0" => string(g0))),
            _pm_node("n10", "C1", _pm_ref("stdlib:multibond/ComposePose2D")),
            _pm_node("n11", "C2", _pm_ref("stdlib:multibond/ComposePose2D")),
            _pm_node("n12", "C3", _pm_ref("stdlib:multibond/ComposePose2D")),
            _pm_node("n13", "TipLocal", _pm_ref("stdlib:planar/LocalPose2D");
                params = Dict{String,Any}("x" => "0.3", "y" => "0.0", "theta" => "0.0")),
            _pm_node("n14", "C4", _pm_ref("stdlib:multibond/ComposePose2D")),
            _pm_node("n15", "T1", _pm_ref("stdlib:bondgraph/Se");
                params = Dict{String,Any}("e" => "0.0")),
            _pm_node("n16", "T2", _pm_ref("stdlib:bondgraph/Se");
                params = Dict{String,Any}("e" => "0.0")),
        ],
        Any[
            _pm_conn("c1", "bond", "n1", "p", "n2", "parent"),
            _pm_conn("c2", "bond", "n2", "child", "n3", "parent"),
            _pm_conn("c3", "bond", "n3", "child", "n4"),
            _pm_conn("c4", "bond", "n5", "p", "n4"),
            _pm_conn("c5", "bond", "n6", "parent", "n4"),
            _pm_conn("c6", "bond", "n6", "child", "n7", "parent"),
            _pm_conn("c7", "bond", "n7", "child", "n8"),
            _pm_conn("c8", "bond", "n9", "p", "n8"),
            _pm_conn("c9", "signal", "n2", "pose", "n10", "gp"),
            _pm_conn("c10", "signal", "n3", "pose", "n10", "gl"),
            _pm_conn("c11", "signal", "n10", "g", "n5", "g"),
            _pm_conn("c12", "signal", "n10", "g", "n11", "gp"),
            _pm_conn("c13", "signal", "n6", "pose", "n11", "gl"),
            _pm_conn("c14", "signal", "n11", "g", "n12", "gp"),
            _pm_conn("c15", "signal", "n7", "pose", "n12", "gl"),
            _pm_conn("c16", "signal", "n12", "g", "n9", "g"),
            _pm_conn("c17", "signal", "n12", "g", "n14", "gp"),
            _pm_conn("c18", "signal", "n13", "g", "n14", "gl"),
            _pm_conn("c19", "bond", "n15", "p", "n2", "drive"),
            _pm_conn("c20", "bond", "n16", "p", "n6", "drive"),
        ])
end

"""
    _pm_elbow(; lever)

The two-link elbow topology of the X-MB2 note, in the two spellings of the offset:

* `lever = false` — the elbow is `Joint2` with `rx = 0.2` on `BodyJ1` (the supported route);
* `lever = true`  — the elbow is reached through a `FixedJoint2D` whose **parent** is on the
  body 1-junction (`Lever.parent` on `BodyJ1`, `Lever.child -> Joint2.parent`).

The second spelling is the structural limit FIX-MB-4 records: the fixed joint's causal
pairing (flow child -> parent, effort parent -> child) is the joint -> fixed -> body chain,
so using it as a frame extension off a body junction leaves two algebraic tearing unknowns.
"""
function _pm_elbow(; lever = false)
    joint_params = Dict{String,Any}("rx" => "0.0", "ry" => "0.0", "kt" => string(_PM_KT),
        "bt" => "0.0", "q0" => "0.0")
    lever_params = Dict{String,Any}("rx" => "0.2", "ry" => "0.0", "kt" => string(_PM_KT),
        "bt" => "0.0", "q0" => "0.0")
    nodes = Any[
        _pm_node("n1", "World", _pm_ref("stdlib:multibond/GroundPlanar")),
        _pm_node("n2", "J1", _pm_ref("stdlib:multibond/Revolute2D");
            params = Dict{String,Any}("rx" => "0.0", "ry" => "0.0", "kt" => string(_PM_KT),
                "bt" => "0.0", "q0" => "0.01")),
        _pm_node("n3", "L1", _pm_ref("stdlib:planar/FixedJoint2D");
            params = Dict{String,Any}("x" => "0.2", "y" => "0.0", "theta" => "0.0")),
        _pm_node("n4", "BJ1", _pm_junction("1")),
        _pm_node("n5", "B1", _pm_ref("stdlib:planar/RigidBody2D");
            params = Dict{String,Any}("m" => "2.0", "J" => "0.026", "g0" => "0.0")),
        _pm_node("n6", "Elbow", _pm_ref("stdlib:multibond/Revolute2D");
            params = lever ? joint_params : lever_params),
        _pm_node("n8", "BJ2", _pm_junction("1")),
        _pm_node("n9", "B2", _pm_ref("stdlib:planar/RigidBody2D");
            params = Dict{String,Any}("m" => "1.5", "J" => "0.015", "g0" => "0.0")),
        _pm_node("n10", "P1", _pm_ref("stdlib:planar/LocalPose2D")),
        _pm_node("n11", "P2", _pm_ref("stdlib:planar/LocalPose2D")),
        _pm_node("n12", "T1", _pm_ref("stdlib:bondgraph/Se");
            params = Dict{String,Any}("e" => "0.0")),
        _pm_node("n13", "T2", _pm_ref("stdlib:bondgraph/Se");
            params = Dict{String,Any}("e" => "0.0")),
    ]
    connections = Any[
        _pm_conn("c1", "bond", "n1", "p", "n2", "parent"),
        _pm_conn("c2", "bond", "n2", "child", "n3", "parent"),
        _pm_conn("c3", "bond", "n3", "child", "n4"),
        _pm_conn("c4", "bond", "n5", "p", "n4"),
        _pm_conn("c7", "bond", "n6", "child", "n8"),
        _pm_conn("c8", "bond", "n9", "p", "n8"),
        _pm_conn("c9", "signal", "n10", "g", "n5", "g"),
        _pm_conn("c10", "signal", "n11", "g", "n9", "g"),
        _pm_conn("c11", "bond", "n12", "p", "n2", "drive"),
        _pm_conn("c12", "bond", "n13", "p", "n6", "drive"),
    ]
    if lever
        # The frame extension: the lever's parent sits on the body 1-junction and its child is
        # the elbow's parent. `rx = 0` here so *only* the lever carries the offset; the test
        # asserts the diagnostics of the topology, not a trajectory.
        push!(nodes, _pm_node("n7", "Lever", _pm_ref("stdlib:planar/FixedJoint2D");
            params = Dict{String,Any}("x" => "0.2", "y" => "0.0", "theta" => "0.0")))
        push!(connections, _pm_conn("c5", "bond", "n7", "parent", "n4"))
        push!(connections, _pm_conn("c6", "bond", "n7", "child", "n6", "parent"))
    else
        push!(connections, _pm_conn("c5", "bond", "n6", "parent", "n4"))
    end
    return _pm_doc("TwoLinkElbow", nodes, connections)
end


function _pm_rigid_joint(; q0 = _PM_Q0, m = _PM_M, j = _PM_J)
    return _pm_doc("RigidJointPendulum",
        Any[
            _pm_node("n1", "World", _pm_ref("stdlib:multibond/GroundPlanar")),
            _pm_node("n2", "Joint", _pm_ref("stdlib:planar/Revolute2DRigid");
                params = Dict{String,Any}("rx" => "0.0", "ry" => "0.0", "q0" => string(q0))),
            _pm_node("n3", "Link", _pm_ref("stdlib:planar/FixedJoint2D");
                params = Dict{String,Any}("x" => "0.0", "y" => "-0.5", "theta" => "0.0")),
            _pm_node("n4", "Body", _pm_ref("stdlib:planar/RigidBody2D");
                params = Dict{String,Any}("m" => string(m), "J" => string(j),
                    "g0" => string(_PM_G))),
            _pm_node("n5", "Local", _pm_ref("stdlib:planar/LocalPose2D");
                params = Dict{String,Any}("x" => "0.0", "y" => "-0.5", "theta" => "0.0")),
            _pm_node("n6", "Compose", _pm_ref("stdlib:multibond/ComposePose2D")),
            _pm_node("n7", "Torque", _pm_ref("stdlib:bondgraph/Se");
                params = Dict{String,Any}("e" => "0.0")),
        ],
        Any[
            _pm_conn("c1", "bond", "n1", "p", "n2", "parent"),
            _pm_conn("c2", "bond", "n2", "child", "n3", "parent"),
            _pm_conn("c3", "bond", "n3", "child", "n4", "p"),
            _pm_conn("c4", "bond", "n7", "p", "n2", "drive"),
            _pm_conn("c5", "signal", "n2", "pose", "n6", "gp"),
            _pm_conn("c6", "signal", "n5", "g", "n6", "gl"),
            _pm_conn("c7", "signal", "n6", "g", "n4", "g"),
        ])
end

# ---------------------------------------------------------------------------------------
# The catalog and the flat picture
# ---------------------------------------------------------------------------------------

const _PM_REFS = [
    "stdlib:planar/FixedJoint2D",
    "stdlib:planar/Free2D",
    "stdlib:planar/JointPose2D",
    "stdlib:planar/LocalPose2D",
    "stdlib:planar/PoseIntegrator2D",
    "stdlib:planar/Prismatic2D",
    "stdlib:planar/Revolute2DCompliant",
    "stdlib:planar/Revolute2DFriction",
    "stdlib:planar/Revolute2DLimit",
    "stdlib:planar/Revolute2DRigid",
    "stdlib:planar/RigidBody2D",
]

@testset "J-MB6 planar mechanics" begin
    @testset "the catalog: 11 planar blocks, block.check clean, drive domains" begin
        blocks = Dict(b.ref => b for b in Library.load_stdlib())
        for ref in _PM_REFS
            @test haskey(blocks, ref)
            b = blocks[ref]
            @test b.group == "Planar mechanics"
            @test isempty(check_block(b.ast))          # 0 errors and 0 warnings
            if any(p -> p.domain == "Planar", b.interface.ports)
                @test b.interface.dimension == 2
            end
            for p in b.interface.ports
                @test haskey(p, :frame)
            end
        end

        # D-MB8: the drive domain follows the screw. A prismatic drive is a Translation port;
        # the revolute variants are Rotation. Never a hard-coded Rotation.
        drive_domain(ref) = only([p.domain for p in blocks[ref].interface.ports
                                  if p.name == "drive"])
        @test drive_domain("stdlib:planar/Prismatic2D") == "Translation"
        for ref in ("stdlib:planar/Revolute2DCompliant", "stdlib:planar/Revolute2DFriction",
            "stdlib:planar/Revolute2DLimit", "stdlib:planar/Revolute2DRigid")
            @test drive_domain(ref) == "Rotation"
        end

        # D-MB5 frames: the body's port is the body frame; the fixed joint bridges into the
        # body frame from a frame-neutral parent (the joint side); everything that exposes a
        # block port is frame-neutral.
        frames(ref) = [(p.name, p.frame) for p in blocks[ref].interface.ports]
        @test frames("stdlib:planar/RigidBody2D") == [("p", "body")]
        @test frames("stdlib:planar/FixedJoint2D") == [("parent", nothing), ("child", "body")]
        @test frames("stdlib:planar/Revolute2DRigid") ==
              [("parent", nothing), ("child", "body"), ("drive", nothing)]
        @test all(p -> p.frame === nothing,
            blocks["stdlib:planar/Revolute2DCompliant"].interface.ports)

        # Per-component Planar units still come from the domain table (J-MB2), on every
        # planar block including the composites' declared ports.
        for ref in _PM_REFS
            env = Units.unit_env(blocks[ref].ast)
            for p in blocks[ref].interface.ports
                p.domain == "Planar" || continue
                for k in 1:3
                    @test env.labels[Symbol(p.name, ".e[", string(k), "]")] ==
                          ["N*m", "N", "N"][k]
                    @test env.labels[Symbol(p.name, ".f[", string(k), "]")] ==
                          ["rad/s", "m/s", "m/s"][k]
                end
            end
            @test isempty([d for d in check_block(blocks[ref].ast) if d.code == "E006"])
        end

        # The pose signal blocks are signal-only (no power ports) with the documented shapes.
        @test isempty(blocks["stdlib:planar/PoseIntegrator2D"].interface.ports)
        @test only(blocks["stdlib:planar/PoseIntegrator2D"].interface.inputs).size == [3]
        @test only(blocks["stdlib:planar/PoseIntegrator2D"].interface.outputs).size == [3]
        @test only(blocks["stdlib:planar/LocalPose2D"].interface.outputs).size == [3]
        @test only(blocks["stdlib:planar/JointPose2D"].interface.inputs).unit == "rad"
    end

    @testset "RigidBody2D is the plan 5.2 flat picture, not an opaque body" begin
        doc = _pm_load()
        flat = _pm_flat(doc)
        @test isempty(flat.diagnostics)
        # The body's interior is a 1-junction with I, Coriolis, Gravity and the zero-power
        # twist tap; the model itself has no junction at all (the body's port *is* the
        # junction).
        junctions = Dict(j.path => j for j in flat.junctions)
        @test collect(keys(junctions)) == ["Body/node"]
        @test junctions["Body/node"].kind == 1
        @test length(junctions["Body/node"].bonds) == 5     # I, Coriolis, Gravity, Df, link
        instances = sort(unique(s.path for s in flat.signals))
        for path in ("Body/inertia", "Body/coriolis", "Body/gravity", "Body/flow")
            @test path in instances
        end
        ids = Set(s.id for s in flat.signals)
        for id in ("Body/inertia/P[1]", "Body/inertia/Pm[1]", "Body/inertia/p.f[3]",
            "Body/coriolis/p.e[2]", "Body/gravity/g[1]", "Body/gravity/p.e[3]",
            "Body/flow/y[1]", "Body/inertia/p.P", "Joint/qout", "Joint/qdout",
            "Joint/pose[1]", "Compose/g[2]", "Link/pose[1]", "Link/child.e[2]")
            @test id in ids
        end
        # No block in the model is an opaque body or joint: the flat graph is primitives.
        refs = Set(n["block"]["ref"] for n in doc["diagram"]["nodes"]
                   if haskey(n["block"], "ref"))
        @test refs == Set([
            "stdlib:multibond/GroundPlanar", "stdlib:multibond/Revolute2D",
            "stdlib:planar/FixedJoint2D", "stdlib:planar/RigidBody2D",
            "stdlib:planar/LocalPose2D", "stdlib:multibond/ComposePose2D",
            "stdlib:bondgraph/Se",
        ])
        # The composite's interior references only J-MB5 primitives.
        interior = Library.load_stdlib()
        body = only([b for b in interior if b.ref == "stdlib:planar/RigidBody2D"])
        @test [BGSim.component_block(c) for c in BGSim.components(body.ast)] ==
              [:Junction, :IPlanar, :CoriolisPlanar, :GravityPlanar, :DfPlanar]

        result = _pm_check(doc)
        @test isempty(_pm_errors(result))
        @test !_pm_has(result, "W201")
        @test !_pm_has(result, "W202")

        # The twist and momentum taps are the body's own signals (V[k] = IPlanar.p.f[k]) and
        # the body's port power is the composite face's derived power.
        run, dir = _pm_run(doc; t_end = 2.0, points = 2001)
        @test run.status == "done"
        data = _pm_columns(dir)
        for k in 1:3
            @test all(data["Body/flow/y[$k]"] .== data["Body/inertia/p.f[$k]"])
            @test all(data["Body/inertia/Pm[$k]"] .== data["Body/inertia/P[$k]"])
        end
        @test haskey(data, "Body/inertia/p.P")
    end

    @testset "FIX-MB-4: composite starts must be <component>/<variable> (E003)" begin
        # `RigidBody2D` has no variables of its own: `P` is an output and the momentum lives
        # in its `inertia` component. A bare key used to be dropped without a word; it is now
        # E003 with the hint that tells the user the spelling.
        doc = _pm_load()
        body = only([n for n in doc["diagram"]["nodes"] if n["name"] == "Body"])
        body["starts"]["P"] = "[0.0, 0.0, 0.0]"
        result = _pm_check(doc)
        errors = [d for d in result.diagnostics if d.code == "E003"]
        @test length(errors) == 1
        @test occursin("Body", errors[1].message)
        @test occursin("`P`", errors[1].message)
        @test occursin("use `<component>/<variable>`", errors[1].hint)

        # A junction component is not a variable holder either: same code and hint.
        doc = _pm_load()
        body = only([n for n in doc["diagram"]["nodes"] if n["name"] == "Body"])
        body["starts"]["node/x"] = "1.0"
        result = _pm_check(doc)
        errors = [d for d in result.diagnostics if d.code == "E003"]
        @test length(errors) == 1
        @test occursin("junction `node`", errors[1].message)
        @test occursin("use `<component>/<variable>`", errors[1].hint)

        # An unknown component still reports E003 with the same hint, and the correctly
        # spelled `inertia/P` start is accepted (the free-body test relies on it).
        doc = _pm_load()
        body = only([n for n in doc["diagram"]["nodes"] if n["name"] == "Body"])
        body["starts"]["nope/P"] = "[0.0, 0.0, 0.0]"
        result = _pm_check(doc)
        errors = [d for d in result.diagnostics if d.code == "E003"]
        @test length(errors) == 1
        @test occursin("unknown component `nope`", errors[1].message)
        @test occursin("use `<component>/<variable>`", errors[1].hint)

        doc = _pm_load()
        body = only([n for n in doc["diagram"]["nodes"] if n["name"] == "Body"])
        body["starts"]["inertia/P"] = "[0.0, 0.0, 0.0]"
        @test !any(d -> d.code == "E003", _pm_check(doc).diagnostics)
    end

    # -----------------------------------------------------------------------------------
    # The pendulum on the composite body/joint
    # -----------------------------------------------------------------------------------

    @testset "pendulum period and energy on the composite RigidBody2D/Revolute2D" begin
        BGSim.clear_compile_cache!()
        doc = _pm_load()
        run, dir = _pm_run(doc; t_end = 4.0, points = 4001)
        @test run.status == "done"
        @test isempty(_pm_errors(run))
        for code in ("E101", "E102", "E103", "E106", "E900", "E901", "W201")
            @test !_pm_has(run, code)
        end
        data = _pm_columns(dir)
        q = data["Joint/qout"]
        @test isapprox(q[1], _PM_Q0; atol = 1e-9)
        period = _pm_period(data["time"], q)
        @test isapprox(period, _PM_T_AMP; rtol = 1.0e-5)
        @test isapprox(period, _PM_T_AMP; rtol = 1.0e-6)   # measured 1.4e-13
        @test isapprox(period, _PM_T_SIMPLE; rtol = 1.0e-3)
        @test maximum(abs.(q)) ≈ _PM_Q0 rtol = 1e-3
        println("J-MB6 pendulum period = ", period, " s (amplitude-corrected physical ",
            _PM_T_AMP, ", simple ", _PM_T_SIMPLE, ", steps ", run.stats.steps, ")")

        # The pose composition is the CoM pose: the link's world position is the pivot plus
        # R(q) (0, -0.5), and the body frame angle is q + theta.
        g2 = data["Compose/g[2]"]
        g3 = data["Compose/g[3]"]
        @test all(isapprox.(g2, 0.5 .* sin.(q); atol = 1e-12))
        @test all(isapprox.(g3, -0.5 .* cos.(q); atol = 1e-12))
        @test all(isapprox.(data["Body/gravity/g[1]"], q; atol = 1e-12))
    end

    @testset "pendulum energy: constant, and the pivot strain is load-bearing" begin
        BGSim.clear_compile_cache!()
        doc = _pm_load()
        run, dir = _pm_run(doc; t_end = 10.0, points = 10001)
        @test run.status == "done"
        data = _pm_columns(dir)
        q = data["Joint/qout"]
        d1 = data["Joint/dout[1]"]
        d2 = data["Joint/dout[2]"]
        KE = 0.5 .* (data["Body/inertia/P[1]"] .^ 2 ./ _PM_J .+
                     data["Body/inertia/P[2]"] .^ 2 ./ _PM_M .+
                     data["Body/inertia/P[3]"] .^ 2 ./ _PM_M)
        h = data["Compose/g[3]"] .+ sin.(q) .* d1 .+ cos.(q) .* d2
        strain = 0.5 * _PM_KT .* (d1 .^ 2 .+ d2 .^ 2)
        E = KE .+ _PM_M * _PM_G .* h .+ strain
        drift = maximum(abs.(E .- E[1]))
        @test drift <= 1.0e-6 * _PM_SWING
        println("J-MB6 energy drift over 10 s = ", drift, " J of swing ", _PM_SWING,
            " (ratio ", drift / _PM_SWING, "); max pivot strain ", maximum(strain), " J")
    end

    @testset "the pivot strain term is load-bearing at a large amplitude" begin
        # `1/2 kt |d|^2` is nearly constant at q0 = 0.01 (the FIX-MB-2 note: dropping it still
        # passed at 1e-6). At q0 = 1 and kt = 1e6 the deflection tracks sin(q) and the term is
        # 1e-4 of the swing *in variation*, so omitting it must fail the same tolerance.
        BGSim.clear_compile_cache!()
        doc = _pm_pendulum(q0 = 1.0, kt = 1.0e6)
        run, dir = _pm_run(doc; t_end = 10.0, points = 10001)
        @test run.status == "done"
        data = _pm_columns(dir)
        q = data["Joint/qout"]
        d1 = data["Joint/dout[1]"]
        d2 = data["Joint/dout[2]"]
        KE = 0.5 .* (data["Body/inertia/P[1]"] .^ 2 ./ _PM_J .+
                     data["Body/inertia/P[2]"] .^ 2 ./ _PM_M .+
                     data["Body/inertia/P[3]"] .^ 2 ./ _PM_M)
        h = data["Compose/g[3]"] .+ sin.(q) .* d1 .+ cos.(q) .* d2
        strain = 0.5 * 1.0e6 .* (d1 .^ 2 .+ d2 .^ 2)
        swing = _PM_M * _PM_G * _PM_L * (1 - cos(1.0))
        with = KE .+ _PM_M * _PM_G .* h .+ strain
        without = KE .+ _PM_M * _PM_G .* h
        drift = maximum(abs.(with .- with[1]))
        dropped = maximum(abs.(without .- without[1]))
        @test drift <= 1.0e-6 * swing
        @test dropped > 1.0e-6 * swing
        println("large amplitude: drift with strain = ", drift, " J (ratio ",
            drift / swing, "), without it = ", dropped, " J (ratio ", dropped / swing, ")")
    end

    @testset "FIX-MB-2: arbitrary link mounting angles, same period, no dummy derivative" begin
        BGSim.clear_compile_cache!()
        periods = Float64[]
        for theta in (0.0, 0.3, pi / 2)
            doc = _pm_pendulum(theta = theta)
            flat = _pm_flat(doc)
            @test isempty(flat.diagnostics)
            @test !any(d -> d.code == "W201", _pm_check(doc).diagnostics)

            # The compiled model is an index-0 ODE with the six physical states (P[1:3],
            # d[1:2], q) and no dummy derivative / tearing variable (FIX-MB-2: the J-MB4
            # slice had `Link/b.e[2]` as a state and failed at theta = 0).
            lowered = BGSim.lower_model(flat; t_start = 0.0, t_end = 4.0)
            unknowns = ModelingToolkit.unknowns(lowered.model.system)
            @test length(unknowns) == 6
            @test isempty([string(u) for u in unknowns
                           if occursin(Char(0x02cd), string(u))])
            @test isempty([string(u) for u in unknowns if occursin("/child.e[", string(u))])
            @test isempty(Compile.post_compile_warnings(flat, lowered.model.system))

            run, dir = _pm_run(doc; t_end = 4.0, points = 4001)
            @test run.status == "done"
            @test !_pm_has(run, "W201")
            data = _pm_columns(dir)
            period = _pm_period(data["time"], data["Joint/qout"])
            push!(periods, period)
            @test isapprox(period, _PM_T_AMP; rtol = 1.0e-5)
            println("FIX-MB-2 theta = ", round(theta, digits = 4), " period = ", period,
                ", states = ", length(unknowns), ", steps = ", run.stats.steps)
        end
        @test length(periods) == 3
        @test maximum(periods) - minimum(periods) <= 1.0e-6 * _PM_T_AMP
    end

    @testset "FIX-MB-4: joint pivot offset rx/ry != 0 (same physics, exact pose)" begin
        # The pivot-offset terms `sin(q) rx - cos(q) ry` / `cos(q) rx + sin(q) ry` in the
        # relative twist and the parent effort were never exercised: every earlier fit had
        # rx = ry = 0, where they vanish. A rigid translation of the whole pendulum leaves the
        # period unchanged and shifts the composed pose by exactly (rx, ry).
        BGSim.clear_compile_cache!()
        for (rx, ry) in ((0.2, 0.1), (-0.3, 0.25))
            doc = _pm_pendulum(extra = Dict{String,Any}("rx" => string(rx),
                "ry" => string(ry)))
            result = _pm_check(doc)
            @test isempty(_pm_errors(result))
            @test !_pm_has(result, "W201")
            run, dir = _pm_run(doc; t_end = 4.0, points = 4001)
            @test run.status == "done"
            @test !_pm_has(run, "W201")
            data = _pm_columns(dir)
            q = data["Joint/qout"]
            period = _pm_period(data["time"], q)
            @test isapprox(period, _PM_T_AMP; rtol = 1.0e-5)
            @test all(isapprox.(data["Compose/g[2]"], rx .+ 0.5 .* sin.(q); atol = 1e-12))
            @test all(isapprox.(data["Compose/g[3]"], ry .- 0.5 .* cos.(q); atol = 1e-12))
            # The pivot-offset terms are load-bearing in the effort relation: check the
            # documented parent.e from child.e at samples across the swing.
            for i in (1, 500, 2000, 4000)
                ce = [data["Joint/child.e[$k]"][i] for k in 1:3]
                pe = [data["Joint/parent.e[$k]"][i] for k in 1:3]
                qq = q[i]
                @test isapprox(pe[1], -(ce[1] +
                                        (sin(qq) * rx - cos(qq) * ry) * ce[2] +
                                        (cos(qq) * rx + sin(qq) * ry) * ce[3]);
                    atol = 1e-10)
                @test isapprox(pe[2], -(cos(qq) * ce[2] - sin(qq) * ce[3]); atol = 1e-10)
                @test isapprox(pe[3], -(sin(qq) * ce[2] + cos(qq) * ce[3]); atol = 1e-10)
            end
            # And the joint still conserves power with the offset present.
            jp = [sum(data["Joint/parent.e[$k]"][i] * data["Joint/parent.f[$k]"][i]
                      for k in 1:3) for i in eachindex(q)]
            jc = [sum(data["Joint/child.e[$k]"][i] * data["Joint/child.f[$k]"][i]
                      for k in 1:3) for i in eachindex(q)]
            jd = data["Joint/drive.e"] .* data["Joint/drive.f"]
            spring = _PM_KT .* (data["Joint/dout[1]"] .* data["Joint/Vrelout[2]"] .+
                                data["Joint/dout[2]"] .* data["Joint/Vrelout[3]"])
            scale = max.(1.0, abs.(jp), abs.(jc))
            @test maximum(abs.(jp .+ jc .+ jd .- spring) ./ scale) <= 1e-9
            println("pivot offset rx=", rx, " ry=", ry, " period=", period,
                " (rel ", abs(period - _PM_T_AMP) / _PM_T_AMP, ")")
        end
    end

    @testset "kt sweep: the compliant pivot converges to the rigid period" begin
        BGSim.clear_compile_cache!()
        errors = Float64[]
        for kt in (1.0e6, 1.0e7, 1.0e8)
            doc = _pm_pendulum(kt = kt)
            run, dir = _pm_run(doc; t_end = 4.0, points = 4001)
            @test run.status == "done"
            data = _pm_columns(dir)
            period = _pm_period(data["time"], data["Joint/qout"])
            # The rigid limit is the amplitude-corrected period of the rigid rod; the residual
            # is the static pivot stretch mg/kt.
            push!(errors, abs(period - _PM_T_AMP) / _PM_T_AMP)
            println("kt sweep kt = ", kt, " period = ", period, " rel error vs rigid = ",
                errors[end])
        end
        @test errors[1] > errors[2] > errors[3]
        @test errors[3] <= 1.0e-6
        @test errors[1] <= 1.0e-4
    end

    @testset "FIX-MB-4: 2-link compliant chain: 12 states, no W201, tip pose" begin
        BGSim.clear_compile_cache!()
        doc = _pm_chain2(g0 = _PM_G)
        result = _pm_check(doc)
        @test isempty(_pm_errors(result))
        for code in ("E007", "E101", "E102", "E103", "W201", "W202")
            @test !_pm_has(result, code)
        end
        flat = _pm_flat(doc)
        @test isempty(flat.diagnostics)
        lowered = BGSim.lower_model(flat; t_start = 0.0, t_end = 0.2)
        unknowns = ModelingToolkit.unknowns(lowered.model.system)
        differential = ModelingToolkit.collect_differential_variables(lowered.model.system)
        # P[1:3] + d[1:2] + q per link, all differential: the compliant chain is an index-0
        # ODE (6 states per link on a 1-DOF joint).
        @test length(unknowns) == 12
        @test length(differential) == 12
        @test isempty([string(u) for u in unknowns if occursin(Char(0x02cd), string(u))])
        @test isempty(Compile.post_compile_warnings(flat, lowered.model.system))

        run, dir = _pm_run(doc; t_end = 0.2, points = 201)
        @test run.status == "done"
        @test !_pm_has(run, "W201")
        data = _pm_columns(dir)
        q1 = data["J1/qout"]
        q2 = data["J2/qout"]
        @test isapprox(q1[1], 0.4; atol = 1e-12)
        @test isapprox(q2[1], -0.6; atol = 1e-12)
        @test maximum(abs.(q1 .- 0.4)) > 1.0e-3      # the chain really moves
        # The composed fixed-base pose is the analytic forward kinematics of the measured
        # joint angles: link-1 CoM 0.2 m along q1, elbow 0.4 m, link-2 CoM 0.2 m and the tip
        # 0.3 m further along q1 + q2.
        @test all(isapprox.(data["C1/g[2]"], 0.2 .* cos.(q1); atol = 1e-12))
        @test all(isapprox.(data["C1/g[3]"], 0.2 .* sin.(q1); atol = 1e-12))
        @test all(isapprox.(data["C2/g[1]"], q1 .+ q2; atol = 1e-12))
        @test all(isapprox.(data["C2/g[2]"], 0.4 .* cos.(q1); atol = 1e-12))
        @test all(isapprox.(data["C2/g[3]"], 0.4 .* sin.(q1); atol = 1e-12))
        tip_x = 0.4 .* cos.(q1) .+ 0.5 .* cos.(q1 .+ q2)
        tip_y = 0.4 .* sin.(q1) .+ 0.5 .* sin.(q1 .+ q2)
        tip_error = max(maximum(abs.(data["C4/g[2]"] .- tip_x)),
            maximum(abs.(data["C4/g[3]"] .- tip_y)))
        @test tip_error <= 1.0e-12
        println("2-link compliant chain: 12 states, tip vs analytic FK = ", tip_error,
            " m, q1 ", q1[end], " q2 ", q2[end])
    end

    @testset "the rigid variant: two constrained translations, three momentum W201" begin
        rigid = _pm_rigid_joint()
        result = _pm_check(rigid)
        @test isempty(_pm_errors(result))
        flat = _pm_flat(rigid)
        @test isempty(_pm_errors(flat))          # the W201 is a warning, not an error
        # SCAP puts the inertia in derivative causality (the joint imposes the body twist).
        @test count(d -> d.code == "W201", result.diagnostics) == 1

        lowered = BGSim.lower_model(flat; t_start = 0.0, t_end = 1.0)
        warnings = Compile.post_compile_warnings(flat, lowered.model.system)
        w201 = [d for d in warnings if d.code == "W201"]
        println("rigid variant W201 = ", [(d.path, d.message) for d in w201])
        # The two hard constraints are the two pivot translations. MTK reports them as the two
        # dummy derivatives of the joint-frame velocity components (`xform/b.f[2]`, `[3]`);
        # the joint keeps exactly one rotational degree of freedom.
        unknown_names = string.(ModelingToolkit.unknowns(lowered.model.system))
        dummies = [n for n in unknown_names if occursin(Char(0x02cd), n)]
        println("rigid variant dummy derivatives = ", dummies)
        # FIX-MB-4: the achieved derivative-causal set. The two physical pivot translations
        # are dummy derivatives of the joint-frame velocity (`Joint/xform/b.f[2]`, `[3]`); the
        # third dummy is the first body twist tap component (`Body/flow/p.f[1]`).
        @test length(dummies) == 3
        @test count(n -> occursin("/xform/b.f[", n), dummies) == 2
        @test count(n -> occursin("Body/flow/p.f[1]", n), dummies) == 1
        differential = ModelingToolkit.collect_differential_variables(lowered.model.system)
        @test length(differential) == 2      # the joint angle and one velocity component
        # The momentum itself is eliminated in favour of the twist it is aliased to (IPlanar
        # defines `f = P/M`), so all three momentum components are reported as
        # derivative-causal: the count is a property of MTK's parametrisation, not of the
        # constraint structure. The physical signature of the two constraints is the pair of
        # dummy derivatives above; "exactly two W201" is not reachable without changing the
        # verified body (the `DfPlanar` tap lives inside `RigidBody2D`), so the acceptance is
        # the measured set: the two joint-frame translations are derivative-causal and MTK
        # reports them plus the three body momentum aliases. The run itself does not
        # initialise (DEC-MB-2's limit).
        @test length(w201) == 3
        @test all(d -> d.path == "Body/inertia", w201)
        for k in 1:3
            @test any(d -> occursin("P[$k]", d.message), w201)
        end
        run, _ = _pm_run(rigid; t_end = 0.5, points = 51)
        @test run.status == "failed"
        @test any(d -> d.code in ("E901", "E103"), run.diagnostics)
        println("rigid variant run: ", run.status, " ",
            [(d.code, d.message) for d in run.diagnostics])

        # The compliant joint on the same topology reports none, in model.check and the run.
        compliant = _pm_pendulum()
        @test !any(d -> d.code == "W201", _pm_check(compliant).diagnostics)
        run, _ = _pm_run(compliant; t_end = 1.0, points = 101)
        @test run.status == "done"
        @test !_pm_has(run, "W201")
        compliant_flat = _pm_flat(compliant)
        compliant_lowered = BGSim.lower_model(compliant_flat; t_start = 0.0, t_end = 1.0)
        @test !any(d -> d.code == "W201",
            Compile.post_compile_warnings(compliant_flat, compliant_lowered.model.system))
    end

    @testset "FIX-MB-4: rigid 2-link chain, the elbow is legal (frame-neutral parent)" begin
        # The same topology as the compliant chain, with `Revolute2DRigid` at both joints. The
        # elbow's parent used to declare `world`, so attaching it to the link-1 body
        # 1-junction was E007; it is frame-neutral now (its internal adjoint is TFAdNeutral).
        doc = _pm_chain2(joint = "stdlib:planar/Revolute2DRigid")
        result = _pm_check(doc)
        @test !_pm_has(result, "E007")
        @test isempty(_pm_errors(result))
        @test endswith(result.frames["c5"], "/body")    # Joint2.parent on BodyJ1
        @test count(d -> d.code == "W201", result.diagnostics) == 2
        flat = _pm_flat(doc)
        @test isempty(_pm_errors(flat))
        lowered = BGSim.lower_model(flat; t_start = 0.0, t_end = 0.5)
        unknowns = ModelingToolkit.unknowns(lowered.model.system)
        differential = ModelingToolkit.collect_differential_variables(lowered.model.system)
        # Two rigid joints: the joint angles and one velocity component survive as the four
        # differential unknowns; the rest is the DAE's algebraic/derivative-causal set.
        @test length(unknowns) == 15
        @test length(differential) == 4
        dummies = [n for n in string.(unknowns) if occursin(Char(0x02cd), n)]
        @test length(dummies) == 4
        @test count(n -> occursin("J1/xform/b.f[", n), dummies) == 2
        @test count(n -> occursin("flow/p.f[1]", n), dummies) == 2
        warnings = Compile.post_compile_warnings(flat, lowered.model.system)
        w201 = [d for d in warnings if d.code == "W201"]
        @test length(w201) == 6
        @test sort(unique(d.path for d in w201)) == ["B1/inertia", "B2/inertia"]
        for path in ("B1/inertia", "B2/inertia"), k in 1:3
            @test any(d -> d.path == path && occursin("P[$k]", d.message), w201)
        end
        # The chain is a DAE that does not initialise (DEC-MB-2's documented limit): assert
        # the diagnostics, not a trajectory.
        run, _ = _pm_run(doc; t_end = 0.5, points = 51)
        @test run.status == "failed"
        @test any(d -> d.code in ("E901", "E103"), run.diagnostics)
        println("rigid 2-link chain: ", length(unknowns), " unknowns / ",
            length(differential), " differential; W201 ", [(d.path) for d in w201],
            "; run ", run.status)
    end

    @testset "FIX-MB-4: FixedJoint2D lever arm and the reverse-causality limit" begin
        # (1) The supported orientation, which the X-MB2 arm uses: the fixed joint's *child*
        # is the body 1-junction and the lever arm is `x = 0.2`. The 2-link chain is exactly
        # this case (both links at 0.2 m), an index-0 ODE with 12 differential states.
        BGSim.clear_compile_cache!()
        doc = _pm_chain2(g0 = 0.0)
        lowered = BGSim.lower_model(_pm_flat(doc); t_start = 0.0, t_end = 0.1)
        @test length(ModelingToolkit.unknowns(lowered.model.system)) == 12
        @test length(ModelingToolkit.collect_differential_variables(lowered.model.system)) == 12

        # (2) The reverse orientation (the fixed joint's *parent* on the body 1-junction, its
        # child toward a downstream joint) is the structural limit recorded for J-MB7. The
        # block's causal pairing is flow child -> parent and effort parent -> child, i.e. the
        # joint -> fixed -> body chain; used as a frame extension the compiled model is a
        # 14-unknown DAE with exactly two algebraic tearing unknowns. This is not an `x != 0`
        # effect (the zero-offset lever has the same signature); it is the port orientation.
        lever = _pm_elbow(lever = true)
        result = _pm_check(lever)
        @test isempty(_pm_errors(result))
        flat = _pm_flat(lever)
        @test isempty(flat.diagnostics)
        lowered = BGSim.lower_model(flat; t_start = 0.0, t_end = 0.1)
        unknowns = ModelingToolkit.unknowns(lowered.model.system)
        differential = ModelingToolkit.collect_differential_variables(lowered.model.system)
        algebraic = [u for u in unknowns if !any(isequal(u), differential)]
        @test length(unknowns) == 14
        @test length(differential) == 12
        @test length(algebraic) == 2
        names = string.(algebraic)
        @test any(n -> occursin("Elbow/parent.f[2]", n), names)
        @test any(n -> occursin("Lever/parent.e[2]", n), names)
        @test !any(isnan, lowered.problem.u0)
        run, _ = _pm_run(lever; t_end = 0.1, points = 11)
        @test run.status == "done"
        println("FixedJoint2D reverse orientation: 14 unknowns / 12 differential, algebraic ",
            names, "; run ", run.status)

        # (3) The joint's `rx` offset is the index-0 spelling of the same elbow: 12 states.
        offset = _pm_elbow(lever = false)
        @test isempty(_pm_errors(_pm_check(offset)))
        flat = _pm_flat(offset)
        lowered = BGSim.lower_model(flat; t_start = 0.0, t_end = 0.1)
        @test length(ModelingToolkit.unknowns(lowered.model.system)) == 12
        @test length(ModelingToolkit.collect_differential_variables(lowered.model.system)) == 12
        @test !any(d -> d.code == "W201",
            Compile.post_compile_warnings(flat, lowered.model.system))
        run, _ = _pm_run(offset; t_end = 0.1, points = 11)
        @test run.status == "done"
    end

    # -----------------------------------------------------------------------------------
    # Compliance, friction and limits (D-MB9 variants)
    # -----------------------------------------------------------------------------------

    @testset "Revolute2DCompliant: the link settles at tau/k and the torsional mode" begin
        BGSim.clear_compile_cache!()
        # A locked actuator (a constant drive torque) with a damped torsional spring: the link
        # settles at q = qrest + tau/k. The pose is the geometric link angle (compliance
        # coordinate convention: q is the link-side angle).
        for (k, tau) in ((100.0, 2.0), (200.0, 2.0), (400.0, 2.0))
            doc = _pm_pendulum(joint = "stdlib:planar/Revolute2DCompliant", q0 = 0.0,
                g0 = 0.0, tau = tau, m = 1.0,
                extra = Dict{String,Any}("k" => string(k), "b" => "2.0", "qrest" => "0.1"))
            # The released-from-rest start with g0 = 0 is d = 0.
            doc["diagram"]["nodes"][2]["starts"]["d"] = "[0.0, 0.0]"
            run, dir = _pm_run(doc; t_end = 6.0, points = 601)
            @test run.status == "done"
            data = _pm_columns(dir)
            @test isapprox(data["Joint/qout"][end], 0.1 + tau / k; atol = 1.0e-4)
            @test abs(data["Joint/qdout"][end]) < 1.0e-4
            @test isapprox(data["Joint/tauout"][end], tau; atol = 1.0e-3)
            @test isapprox(data["Joint/pose[1]"][end], data["Joint/qout"][end];
                atol = 1.0e-14)
        end

        # The torsional mode period of the free link about the pivot: T = 2 pi sqrt(Jp/k) with
        # Jp = J + m L^2, so the joint's k sweep is the second compliance axis. k -> Inf makes
        # the joint rigid. `d` starts at the pivot deflection consistent with the initial
        # angular acceleration (a_t = alpha L, kt d1 = -m alpha L), so the 1e4 rad/s pivot mode
        # is not excited (the FIX-MB-3 lesson).
        periods = Float64[]
        for k in (25.0, 100.0, 400.0)
            alpha = 0.1 * k / (_PM_J + _PM_M * _PM_L^2)
            dstart = [-_PM_M * _PM_L * alpha / _PM_KT, 0.0]
            doc = _pm_pendulum(joint = "stdlib:planar/Revolute2DCompliant", q0 = 0.0,
                g0 = 0.0, dstart = dstart,
                extra = Dict{String,Any}("k" => string(k), "b" => "0.0",
                    "qrest" => "0.1"))
            run, dir = _pm_run(doc; t_end = 4.0, points = 4001)
            @test run.status == "done"
            data = _pm_columns(dir)
            q = data["Joint/qout"] .- 0.1
            period = _pm_period(data["time"], q)
            push!(periods, period)
            analytic = 2 * pi * sqrt((_PM_J + _PM_M * _PM_L^2) / k)
            @test isapprox(period, analytic; rtol = 2.0e-3)
            println("torsional mode k = ", k, " period = ", period, " analytic = ", analytic)
        end
        @test isapprox(periods[1] / periods[2], 2.0; rtol = 2.0e-3)
        @test isapprox(periods[2] / periods[3], 2.0; rtol = 2.0e-3)
    end

    @testset "Revolute2DFriction: monotone decay, terminal speed and stick" begin
        BGSim.clear_compile_cache!()
        # A torque above the Coulomb level: the link accelerates and approaches the terminal
        # rate (tau - Fc)/Fv, and the friction torque is always dissipative.
        doc = _pm_pendulum(joint = "stdlib:planar/Revolute2DFriction", q0 = 0.0, g0 = 0.0,
            tau = 2.0, dstart = [0.0, 0.0],
            extra = Dict{String,Any}("Fc" => "0.5", "Fv" => "0.1", "v_eps" => "1.0e-3"))
        # The link's inertia about the pivot is J + m L^2 = 0.2501, so the rate time constant
        # is 2.5 s: give it eight of them.
        run, dir = _pm_run(doc; t_end = 20.0, points = 1001)
        @test run.status == "done"
        data = _pm_columns(dir)
        w = data["Joint/qdout"]
        @test all(diff(w) .>= -1.0e-9)                 # monotone spin-up
        terminal = (2.0 - 0.5) / 0.1
        @test isapprox(w[end], terminal; rtol = 0.02)
        friction = data["Joint/tauout"]
        @test all(friction .>= -1.0e-12)
        @test all(friction .* w .>= -1.0e-12)          # never generates power
        @test isapprox(friction[end], 0.5 + 0.1 * w[end]; rtol = 0.02)
        println("friction terminal rate = ", w[end], " (analytic ", terminal,
            "), friction torque = ", friction[end])

        # A torque below the Coulomb level: the link sticks (the regularised model creeps at
        # v_eps*atanh(tau/Fc), which the test bounds).
        doc = _pm_pendulum(joint = "stdlib:planar/Revolute2DFriction", q0 = 0.0, g0 = 0.0,
            tau = 0.2, dstart = [0.0, 0.0],
            extra = Dict{String,Any}("Fc" => "0.5", "Fv" => "0.0", "v_eps" => "1.0e-3"))
        run, dir = _pm_run(doc; t_end = 1.0, points = 1001)
        @test run.status == "done"
        data = _pm_columns(dir)
        @test maximum(abs.(data["Joint/qdout"])) <= 1.0e-3
        @test maximum(abs.(data["Joint/qout"])) <= 1.0e-3
        @test isapprox(data["Joint/qdout"][end], 1.0e-3 * atanh(0.2 / 0.5); rtol = 0.05)
    end

    @testset "Revolute2DLimit: a one-sided stop outside the limits, free inside" begin
        BGSim.clear_compile_cache!()
        # Outside the upper limit with a constant drive torque: the stop balances the drive at
        # q = upper + tau/kL (a one-sided spring), and the damper settles it there.
        doc = _pm_pendulum(joint = "stdlib:planar/Revolute2DLimit", q0 = 0.05, g0 = 0.0,
            tau = 2.0, dstart = [0.0, 0.0],
            extra = Dict{String,Any}("lower" => "-1.0", "upper" => "0.02",
                "kL" => "100.0", "bL" => "5.0", "delta" => "1.0e-3"))
        run, dir = _pm_run(doc; t_end = 6.0, points = 601)
        @test run.status == "done"
        @test !_pm_has(run, "W206")
        data = _pm_columns(dir)
        @test isapprox(data["Joint/qout"][end], 0.02 + 2.0 / 100.0; atol = 1.0e-3)
        @test all(data["Joint/tauout"] .>= -1.0e-9)
        @test isapprox(data["Joint/tauout"][end], 2.0; atol = 1.0e-2)
        println("limit stop settles at q = ", data["Joint/qout"][end],
            " (upper + tau/kL = 0.04), stop torque = ", data["Joint/tauout"][end])

        # Inside the limits: no stop torque, and a free link stays where it is.
        doc = _pm_pendulum(joint = "stdlib:planar/Revolute2DLimit", q0 = 0.0, g0 = 0.0,
            dstart = [0.0, 0.0],
            extra = Dict{String,Any}("lower" => "-1.0", "upper" => "0.02",
                "kL" => "100.0", "bL" => "5.0"))
        run, dir = _pm_run(doc; t_end = 1.0, points = 101)
        @test run.status == "done"
        data = _pm_columns(dir)
        @test maximum(abs.(data["Joint/tauout"])) < 1.0e-6
        @test maximum(abs.(data["Joint/qout"])) < 1.0e-9
    end

    # -----------------------------------------------------------------------------------
    # Prismatic, free body and pose handling
    # -----------------------------------------------------------------------------------

    @testset "Prismatic2D: a mass on a spring with a Translation drive" begin
        BGSim.clear_compile_cache!()
        doc = _pm_prismatic()
        result = _pm_check(doc)
        @test isempty(_pm_errors(result))
        # D-MB8: the drive's per-component units are a force and a velocity, never a torque.
        prismatic_block = only([b for b in Library.load_stdlib()
                                if b.ref == "stdlib:planar/Prismatic2D"])
        drive = only([p for p in prismatic_block.interface.ports if p.name == "drive"])
        @test drive.domain == "Translation"
        env = Units.unit_env(prismatic_block.ast)
        @test env.labels[Symbol("drive.e")] == "N"
        @test env.labels[Symbol("drive.f")] == "m/s"
        flat = _pm_flat(doc)
        @test isempty(flat.diagnostics)
        run, dir = _pm_run(doc; t_end = 3.0, points = 3001)
        @test run.status == "done"
        @test isempty(_pm_errors(run))
        @test !_pm_has(run, "W201")
        data = _pm_columns(dir)
        q = data["Joint/qout"]
        @test isapprox(q[1], 0.1; atol = 1e-9)
        analytic = 2 * pi * sqrt(2.0 / 200.0)
        period = _pm_period(data["time"], q)
        @test isapprox(period, analytic; rtol = 1.0e-3)
        # Exact translation along the axis: the joint pose is (0, q, 0), and the compliant
        # perpendicular/rotational deflections stay at their (zero) equilibrium.
        @test all(isapprox.(data["Joint/pose[2]"], q; atol = 1.0e-12))
        @test all(abs.(data["Joint/pose[3]"]) .<= 1.0e-10)
        @test maximum(abs.(data["Joint/dout"])) <= 1.0e-8
        @test maximum(abs.(data["Joint/drout"])) <= 1.0e-8
        println("prismatic period = ", period, " s (analytic ", analytic, " s)")

        # A Rotation drive on a prismatic joint is refused (domain mismatch), so the
        # Translation domain is load-bearing.
        bad = _pm_prismatic()
        push!(bad["diagram"]["nodes"],
            _pm_node("n8", "Torque", _pm_ref("stdlib:rotation/TorqueSource");
                params = Dict{String,Any}("tau" => "1.0")))
        push!(bad["diagram"]["connections"],
            _pm_conn("c7", "bond", "n8", "shaft", "n2", "drive"))
        broken = _pm_check(bad)
        @test _pm_has(broken, "E102")
    end

    @testset "FIX-MB-4: prismatic axis at phi = 0.7 and pi/2 (the sin terms are live)" begin
        # At phi = 0 the `sin(phi)` terms of the pose, the relative twist and the child effort
        # vanish, so the earlier test never exercised them. A rigid rotation of the axis leaves
        # the mass-spring period unchanged and puts the pose at (0, q cos phi, q sin phi).
        BGSim.clear_compile_cache!()
        analytic = 2 * pi * sqrt(2.0 / 200.0)
        for phi in (0.7, pi / 2)
            doc = _pm_prismatic(phi = phi)
            result = _pm_check(doc)
            @test isempty(_pm_errors(result))
            @test !_pm_has(result, "W201")
            run, dir = _pm_run(doc; t_end = 3.0, points = 3001)
            @test run.status == "done"
            @test !_pm_has(run, "W201")
            data = _pm_columns(dir)
            q = data["Joint/qout"]
            @test isapprox(q[1], 0.1; atol = 1e-9)
            period = _pm_period(data["time"], q)
            @test isapprox(period, analytic; rtol = 1.0e-3)
            @test all(isapprox.(data["Joint/pose[2]"], q .* cos(phi); atol = 1e-12))
            @test all(isapprox.(data["Joint/pose[3]"], q .* sin(phi); atol = 1e-12))
            @test maximum(abs.(q .* sin(phi))) > 0.05       # the axis really moved
            @test maximum(abs.(data["Joint/dout"])) <= 1e-8
            @test maximum(abs.(data["Joint/drout"])) <= 1e-8
            println("prismatic phi = ", phi, " period = ", period, " (analytic ", analytic,
                ")")
        end
    end

    @testset "Free2D + PoseIntegrator2D: exact SE(2) screw motion, no pose drift" begin
        BGSim.clear_compile_cache!()
        # (1) A pure rotation about the centre of mass: the body-frame twist is constant, so the
        # pose is the exact SE(2) screw g(t) = g0 * exp(V t).
        g0 = BGSim.SE2(0.4, 0.1, -0.2)
        for (P0, label) in (((0.2, 0.0, 0.0), "pure rotation"),
            ((0.0, 0.5, -0.3), "pure translation"))
            doc = _pm_free(P0 = P0)
            flat = _pm_flat(doc)
            @test isempty(flat.diagnostics)
            run, dir = _pm_run(doc; t_end = 2.0, points = 2001)
            @test run.status == "done"
            @test !_pm_has(run, "W201")
            data = _pm_columns(dir)
            V = [P0[1] / 0.5, P0[2] / 2.0, P0[3] / 2.0]
            worst = 0.0
            for (i, tt) in enumerate(data["time"])
                exact = g0 * BGSim.exp(BGSim.Twist{3}(V[1] * tt, V[2] * tt, V[3] * tt))
                got = [data["Body/pose/g[1]"][i], data["Body/pose/g[2]"][i],
                       data["Body/pose/g[3]"][i]]
                worst = max(worst, maximum(abs.(got .- BGSim.Mech.chart(exact))))
            end
            @test worst <= 1.0e-6
            println("free body ", label, ": max pose error vs the exact screw = ", worst)
        end

        # (2) The general free case (omega != 0 and a CoM velocity): the body-frame momentum is
        # not constant, but the *spatial* one is, so the angular rate is constant and the CoM
        # moves on a straight line at constant speed. The pose integrator reproduces both to
        # integrator order, and the world momentum is conserved.
        doc = _pm_free()
        run, dir = _pm_run(doc; t_end = 2.0, points = 2001)
        @test run.status == "done"
        data = _pm_columns(dir)
        Vb = [0.2 / 0.5, 0.5 / 2.0, -0.3 / 2.0]
        theta = data["Body/pose/g[1]"]
        @test maximum(abs.(theta .- (0.4 .+ Vb[1] .* data["time"]))) <= 1.0e-9
        wv = BGSim.SE2(0.4)    # R(theta0) (0, 0)
        vs = [cos(0.4) * Vb[2] - sin(0.4) * Vb[3], sin(0.4) * Vb[2] + cos(0.4) * Vb[3]]
        @test maximum(abs.(data["Body/pose/g[2]"][2:end] .-
                           (0.1 .+ vs[1] .* data["time"][2:end]))) <= 1.0e-6
        @test maximum(abs.(data["Body/pose/g[3]"][2:end] .-
                           (-0.2 .+ vs[2] .* data["time"][2:end]))) <= 1.0e-6
        @test maximum(abs.(data["Body/body/inertia/P[1]"] .- 0.2)) <= 1e-10
        q = data["Body/pose/g[1]"]
        px = 2.0 .* (cos.(q) .* data["Body/body/inertia/p.f[2]"] .-
                     sin.(q) .* data["Body/body/inertia/p.f[3]"])
        py = 2.0 .* (sin.(q) .* data["Body/body/inertia/p.f[2]"] .+
                     cos.(q) .* data["Body/body/inertia/p.f[3]"])
        @test maximum(abs.(px .- px[1])) <= 1e-6
        @test maximum(abs.(py .- py[1])) <= 1e-6
        println("free body general: world momentum drift = ",
            max(maximum(abs.(px .- px[1])), maximum(abs.(py .- py[1]))),
            ", CoM straight-line error = ",
            maximum(abs.(data["Body/pose/g[3]"][2:end] .-
                        (-0.2 .+ vs[2] .* data["time"][2:end]))))

        # Fixed-base composition vs the integrated truth: the composed link pose and an
        # integrator fed the body twist agree (D-MB6: no pose drift on a fixed base).
        pend = _pm_pendulum()
        push!(pend["diagram"]["nodes"],
            _pm_node("n8", "Truth", _pm_ref("stdlib:planar/PoseIntegrator2D");
                params = Dict{String,Any}("theta0" => string(_PM_Q0),
                    "x0" => string(0.5 * sin(_PM_Q0)),
                    "y0" => string(-0.5 * cos(_PM_Q0)))))
        push!(pend["diagram"]["connections"],
            _pm_conn("c8", "signal", "n4", "V", "n8", "tw"))
        pend_flat = _pm_flat(pend)
        @test isempty(pend_flat.diagnostics)
        run, dir = _pm_run(pend; t_end = 4.0, points = 4001)
        @test run.status == "done"
        data = _pm_columns(dir)
        for k in 1:3
            @test maximum(abs.(data["Compose/g[$k]"] .- data["Truth/g[$k]"])) <= 1.0e-6
        end
        println("fixed-base composed vs integrated pose max diff = ",
            maximum(maximum(abs.(data["Compose/g[$k]"] .- data["Truth/g[$k]"]))
                    for k in 1:3))
    end

    @testset "FixedJoint2D: constant adjoint bridge and power continuity" begin
        theta, x, y = 0.3, 0.0, -0.5
        doc = _pm_pendulum(theta = theta)
        run, dir = _pm_run(doc; t_end = 2.0, points = 2001)
        @test run.status == "done"
        data = _pm_columns(dir)
        c, s = cos(theta), sin(theta)
        A = [1.0 0.0 0.0; y c -s; -x s c]
        for i in (1, 500, 1000)
            pe = [data["Link/parent.e[$k]"][i] for k in 1:3]
            pf = [data["Link/parent.f[$k]"][i] for k in 1:3]
            ce = [data["Link/child.e[$k]"][i] for k in 1:3]
            cf = [data["Link/child.f[$k]"][i] for k in 1:3]
            @test isapprox(pf, -A * cf; atol = 1e-10)
            @test isapprox(ce, transpose(A) * pe; atol = 1e-10)
            @test abs(sum(pe[k] * pf[k] + ce[k] * cf[k] for k in 1:3)) <=
                  1e-9 * max(1.0, maximum(abs, pe), maximum(abs, ce))
        end
        @test all(data["Link/pose[1]"] .== theta)
        @test all(data["Link/pose[3]"] .== y)
    end

    @testset "power identities on the pendulum run" begin
        BGSim.clear_compile_cache!()
        doc = _pm_load()
        run, dir = _pm_run(doc; t_end = 2.0, points = 2001)
        @test run.status == "done"
        data = _pm_columns(dir)
        for i in (1, 400, 800)
            # The body's 1-junction: equal flows, efforts summing to zero, so the total power
            # over its five bonds vanishes.
            bonds = (
                ("Body/inertia", :p), ("Body/gravity", :p), ("Body/coriolis", :p),
                ("Body/flow", :p), ("Link", :child),
            )
            total = 0.0
            for (path, port) in bonds
                total += sum(data["$path/$port.e[$k]"][i] * data["$path/$port.f[$k]"][i]
                             for k in 1:3)
            end
            @test abs(total) <= 1e-9 * max(1.0, abs(data["Body/inertia/p.P"][i]))
            # The joint: port power = the pivot spring rate (bt = 0 in the fixture).
            jp = sum(data["Joint/parent.e[$k]"][i] * data["Joint/parent.f[$k]"][i]
                     for k in 1:3)
            jc = sum(data["Joint/child.e[$k]"][i] * data["Joint/child.f[$k]"][i]
                     for k in 1:3)
            jd = data["Joint/drive.e"][i] * data["Joint/drive.f"][i]
            spring = _PM_KT * (data["Joint/dout[1]"][i] * data["Joint/Vrelout[2]"][i] +
                               data["Joint/dout[2]"][i] * data["Joint/Vrelout[3]"][i])
            @test abs(jp + jc + jd - spring) <= 1e-9 * max(1.0, abs(jp), abs(jc))
        end
    end

    # -----------------------------------------------------------------------------------
    # The worker run.start path (the same entry points as test_worker.jl)
    # -----------------------------------------------------------------------------------

    @testset "the composite pendulum runs through worker run.start" begin
        BGSim.clear_compile_cache!()
        mktempdir() do tmp
            listener = Sockets.listen(ip"127.0.0.1", 0)
            port = Int(Sockets.getsockname(listener)[2])
            server = @async begin
                sock = Sockets.accept(listener)
                Worker.serve(sock; log = devnull)
            end
            sock = Sockets.connect(ip"127.0.0.1", port)
            notes = Any[]
            function read_message()
                frame = Worker.read_frame(sock)
                frame === nothing && error("worker closed")
                return JSON3.read(String(frame.payload))
            end
            function wait_for(pred; timeout = 300.0)
                task = @async begin
                    while true
                        message = read_message()
                        pred(message) && return message
                        push!(notes, message)
                    end
                end
                if Base.timedwait(() -> istaskdone(task), timeout) == :timed_out
                    error("timed out waiting for the worker")
                end
                return fetch(task)
            end
            try
                run_id = "mb6-pendulum"
                run_dir = joinpath(tmp, run_id)
                doc = _pm_load()
                Worker.write_json_frame(sock, JSON3.write((; id = 1, method = "run.start",
                    params = (; runId = run_id, model = doc, runDir = run_dir,
                        projectDir = normpath(joinpath(@__DIR__, "..", "..", ".."))))))
                answer = wait_for(m -> get(m, :id, nothing) == 1)
                @test answer.result.accepted == true
                done = wait_for(m -> get(m, :method, "") == "run.done")
                @test done.params.status == "done"
                @test isempty([d for d in done.params.diagnostics
                               if d.severity == "error"])
                @test !any(d -> get(d, :code, "") == "W201", done.params.diagnostics)
                final = JSON3.read(read(joinpath(run_dir, "manifest.json"), String))
                @test final.status == "done"
                @test Int(final.time.n) == 4001
                data = _pm_columns(run_dir)
                period = _pm_period(data["time"], data["Joint/qout"])
                @test isapprox(period, _PM_T_AMP; rtol = 1.0e-5)
                println("J-MB6 worker-run period = ", period, " s")
            finally
                close(sock)
                try
                    wait(server)
                catch
                end
                close(listener)
            end
        end
    end
end
