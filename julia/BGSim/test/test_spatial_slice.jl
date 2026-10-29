# Work package J-MB8: spatial vector primitives and pose integration (plan 6, row J-MB8).
#
# The spatial element set of the plan lives in `stdlib/multibond/` beside the planar one:
#
#   I, Coriolis, C, R, Se, Sf, TF (diagonal), TFMat (6x6), GY (6x6), MTF, MGY, Gravity,
#   Ground, ExternalWrench, FixedTransform3D, JointTransform3D, ComposePose3D, De, Df,
#   PoseIntegrator3D
#
# Every block is driven through the **real pipeline** (`IR.parse_model` -> `Compile.flatten`
# -> `simulate`, Rodas5P, reltol 1e-9, abstol 1e-11) and the plan 9.1/9.2 checks are:
#
#   * a free body with a diagonal inertia: world momentum (linear and angular) and kinetic
#     energy conserved over 10 s, plus the **Dzhanibekov** flip from an asymmetric diagonal
#     inertia (spin about the intermediate principal axis is unstable, world H constant);
#   * a floating base at a constant body twist against the analytic SE(3) `exp` reference,
#     over 10 s, and the quaternion norm drift of `PoseIntegrator3D`;
#   * fixed-base pose composition (`ComposePose3D`) against a `PoseIntegrator3D` on the same
#     twist, and the floating-base-only rule (a fixed-base chain has no pose state);
#   * random power continuity of TF/TFMat/GY/MTF/MGY and `V^T ad(V)^T P = 0`, per-component
#     units (`N*m` x3 then `N` x3, `rad/s` x3 then `m/s` x3), and `block.check` 0/0 for every
#     new block.
#
# Tolerances follow plan 9.1: relative 1e-9 for algebraic identities and 1e-6 over 10 s for
# integrated trajectories. Every helper is `_mb8_`-prefixed because the test files share
# `Main`.
using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import BGSim.Library
import BGSim.Units
import JSON3
using LinearAlgebra

if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using .BondGraphGolden

const _MB8_NEW_REFS = [
    "stdlib:multibond/CSpatial",
    "stdlib:multibond/ComposePose3D",
    "stdlib:multibond/CoriolisSpatial",
    "stdlib:multibond/DeSpatial",
    "stdlib:multibond/DfSpatial",
    "stdlib:multibond/ExternalWrenchSpatial",
    "stdlib:multibond/FixedTransform3D",
    "stdlib:multibond/FixedTransform3DNeutral",
    "stdlib:multibond/GYSpatial",
    "stdlib:multibond/GravitySpatial",
    "stdlib:multibond/GroundSpatial",
    "stdlib:multibond/ISpatial",
    "stdlib:multibond/JointTransform3D",
    "stdlib:multibond/MGYSpatial",
    "stdlib:multibond/MTFSpatial",
    "stdlib:multibond/PoseIntegrator3D",
    "stdlib:multibond/RSpatial",
    "stdlib:multibond/SeSpatial",
    "stdlib:multibond/SfSpatial",
    "stdlib:multibond/TFSpatial",
    "stdlib:multibond/TFSpatialMat",
]

const _MB8_E_UNITS = ["N*m", "N*m", "N*m", "N", "N", "N"]
const _MB8_F_UNITS = ["rad/s", "rad/s", "rad/s", "m/s", "m/s", "m/s"]

# ---------------------------------------------------------------------------------------
# Inline signal sources (parameters are set on the instance, so a value sweep is a
# compile-cache hit: parameter values are not in the structural key, D4).
# ---------------------------------------------------------------------------------------

const _MB8_VEC6_CONST = """
@block Vec6Const begin
    @parameters begin
        c1::Real = 0.0, [description = "Component 1"]
        c2::Real = 0.0, [description = "Component 2"]
        c3::Real = 0.0, [description = "Component 3"]
        c4::Real = 0.0, [description = "Component 4"]
        c5::Real = 0.0, [description = "Component 5"]
        c6::Real = 0.0, [description = "Component 6"]
    end
    @outputs y::Vec{6}
    @equations begin
        y[1] ~ c1
        y[2] ~ c2
        y[3] ~ c3
        y[4] ~ c4
        y[5] ~ c5
        y[6] ~ c6
    end
end
"""

# A constant pose chart `Vec{7}`: the local mounting pose of a fixed-base link.
const _MB8_POSE_CONST = """
@block PoseConst begin
    @parameters begin
        qw::Real = 1.0, [unit = "1", description = "Quaternion w"]
        qx::Real = 0.0, [unit = "1", description = "Quaternion x"]
        qy::Real = 0.0, [unit = "1", description = "Quaternion y"]
        qz::Real = 0.0, [unit = "1", description = "Quaternion z"]
        x::Real = 0.0, [unit = "m", description = "Position x"]
        y::Real = 0.0, [unit = "m", description = "Position y"]
        z::Real = 0.0, [unit = "m", description = "Position z"]
    end
    @outputs g::Vec{7}
    @equations begin
        g[1] ~ qw
        g[2] ~ qx
        g[3] ~ qy
        g[4] ~ qz
        g[5] ~ x
        g[6] ~ y
        g[7] ~ z
    end
end
"""

# A one-DOF joint pose `g(q)`: a rotation about x through the parent origin. `g(q)` is a
# one-parameter subgroup, so `g(q0) exp(S qdot t) = g(q0 + qdot t)` exactly; it is the
# kinematic branch of the fixed-base composition test.
const _MB8_POSE_JOINT = """
@block PoseJointX begin
    @parameters begin
        rate::Real = 1.0, [unit = "rad/s", description = "Joint rate"]
        q0::Real = 0.0, [unit = "rad", description = "Initial joint angle"]
    end
    @variables q::Real = 0.0, [unit = "rad", state = :prefer, description = "Joint angle increment"]
    @outputs g::Vec{7}
    @equations begin
        ddt(q) ~ rate
        g[1] ~ cos(0.5 * (q0 + q))
        g[2] ~ sin(0.5 * (q0 + q))
        g[3] ~ 0.0
        g[4] ~ 0.0
        g[5] ~ 0.0
        g[6] ~ 0.0
        g[7] ~ 0.0
    end
end
"""

# A 6x6 constant matrix signal: the modulated gyrator's `G` input.
const _MB8_MAT6_CONST = let
    decl = join(["        g$i$j::Real = $(i == j ? 1.0 : 0.0), [description = \"Entry $i,$j\"]"
                 for i in 1:6 for j in 1:6], "\n")
    eqs = join(["        G[$i, $j] ~ g$i$j" for i in 1:6 for j in 1:6], "\n")
    """
    @block Mat6Const begin
        @parameters begin
    $decl
        end
        @outputs G::Mat{6,6}
        @equations begin
    $eqs
        end
    end
    """
end

# ---------------------------------------------------------------------------------------
# Model-document helpers
# ---------------------------------------------------------------------------------------

_mb8_inline(source) = Dict{String,Any}("inline" => Dict{String,Any}("source" => source))

"""A `Vec{6}` constant source node (`Vec6Const`) with the six values as instance parameters."""
function _mb8_vec6(id, name, values)
    return bg_node(id, name, _mb8_inline(_MB8_VEC6_CONST);
        params = Dict{String,Any}("c$k" => string(values[k]) for k in 1:6))
end

"""The instance/default text of a 6x6 matrix (`[r1c1 r1c2 ...; ...]`)."""
_mb8_mat_text(M) = "[" * join([join([string(M[i, j]) for j in 1:6], " ") for i in 1:6], "; ") * "]"

function _mb8_mat6(id, name, M)
    return bg_node(id, name, _mb8_inline(_MB8_MAT6_CONST);
        params = Dict{String,Any}("g$i$j" => string(M[i, j]) for i in 1:6 for j in 1:6))
end

_mb8_check(doc) = Compile.model_check(IR.parse_model(doc))
_mb8_errors(result) = [d for d in result.diagnostics if d.severity == "error"]
_mb8_w201(result) = count(d -> d.code == "W201", result.diagnostics)

"""A deterministic uniform generator in `[lo, hi)`; the tests are reproducible and need no
`Random` dependency."""
function _mb8_rng(seed::Integer, lo::Float64 = -1.0, hi::Float64 = 1.0)
    state = Ref{UInt64}(UInt64(seed) * 0x9e3779b97f4a7c15 + 0x1234_5678)
    return function ()
        state[] = state[] * 6364136223846793005 + 1442695040888963407
        u = Float64((state[] >> 11) & 0x1fffffffffffff) / 9.007199254740992e15
        return lo + (hi - lo) * u
    end
end

"""The chart value `g[1:7]` of a node at sample `i` as `(Quat, SVector{3})`."""
function _mb8_pose(columns, prefix, i)
    q = BGSim.Quat(columns["$prefix[1]"][i], columns["$prefix[2]"][i],
        columns["$prefix[3]"][i], columns["$prefix[4]"][i])
    p = BGSim.SVector(columns["$prefix[5]"][i], columns["$prefix[6]"][i],
        columns["$prefix[7]"][i])
    return q, p
end

"""The relative SE(3) component error of two charts: the rotation-matrix entries and the
translation. The quaternion sign is not part of it (a chart canonicalises `q_w >= 0`, an
integrated quaternion does not)."""
function _mb8_pose_error(qg, pg, qx, px)
    dR = maximum(abs.(Matrix(BGSim.quat_to_matrix(qg)) .-
                     Matrix(BGSim.quat_to_matrix(qx))))
    dp = maximum(abs.(pg .- px))
    return max(dR, dp)
end

"""The relative power residual of a two-port element at sample `i`
(`|a.e.a.f + b.e.b.f| / max(1, |a.e.a.f|, |b.e.b.f|)`)."""
function _mb8_power_residual(columns, pa, pb, i)
    ae = [columns["$pa.e[$k]"][i] for k in 1:6]
    af = [columns["$pa.f[$k]"][i] for k in 1:6]
    be = [columns["$pb.e[$k]"][i] for k in 1:6]
    bf = [columns["$pb.f[$k]"][i] for k in 1:6]
    lhs = sum(ae[k] * af[k] for k in 1:6)
    rhs = sum(be[k] * bf[k] for k in 1:6)
    return abs(lhs + rhs) / max(1.0, abs(lhs), abs(rhs))
end

_mb8_vec(columns, prefix, i) = [columns["$prefix[$k]"][i] for k in 1:6]

"""
    _mb8_free(; J, m, P0, pose0, g0, wrench, t_end, points)

A free spatial body: a 1-junction with `ISpatial` + `CoriolisSpatial` + `GravitySpatial` and
`PoseIntegrator3D` driven by the body's own twist. `wrench = nothing` omits
`ExternalWrenchSpatial`; otherwise its six inputs are six `Constant` sources.
"""
function _mb8_free(; J = (1.0, 2.0, 3.0), m = 2.0,
    P0 = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    pose0 = (1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0), g0 = 0.0, wrench = nothing,
    t_end = 10.0, points = 10001)
    nodes = Any[
        bg_node("n1", "Node", bg_junction("1")),
        bg_node("n2", "I", bg_ref("stdlib:multibond/ISpatial");
            params = Dict{String,Any}("J" => "[$(J[1]), $(J[2]), $(J[3])]",
                "m" => string(m)),
            starts = Dict{String,Any}("P" =>
                "[$(P0[1]), $(P0[2]), $(P0[3]), $(P0[4]), $(P0[5]), $(P0[6])]")),
        bg_node("n3", "Cor", bg_ref("stdlib:multibond/CoriolisSpatial")),
        bg_node("n4", "Grav", bg_ref("stdlib:multibond/GravitySpatial");
            params = Dict{String,Any}("m" => string(m), "g0" => string(g0))),
        bg_node("n5", "Pose", bg_ref("stdlib:multibond/PoseIntegrator3D");
            starts = Dict{String,Any}("qw" => string(pose0[1]), "qx" => string(pose0[2]),
                "qy" => string(pose0[3]), "qz" => string(pose0[4]),
                "px" => string(pose0[5]), "py" => string(pose0[6]),
                "pz" => string(pose0[7]))),
    ]
    conns = Any[
        bg_conn("c1", "bond", "n2", "p", "n1", nothing),
        bg_conn("c2", "bond", "n3", "p", "n1", nothing),
        bg_conn("c3", "bond", "n4", "p", "n1", nothing),
        bg_conn("c4", "signal", "n2", "Pm", "n3", "P"),
        bg_conn("c5", "signal", "n2", "twout", "n5", "tw"),
        bg_conn("c6", "signal", "n5", "g", "n4", "g"),
    ]
    if wrench !== nothing
        push!(nodes, bg_node("n6", "W", bg_ref("stdlib:multibond/ExternalWrenchSpatial")))
        push!(conns, bg_conn("c7", "bond", "n6", "p", "n1", nothing))
        for (k, name) in enumerate(("tx", "ty", "tz", "fx", "fy", "fz"))
            push!(nodes, bg_node("w$k", "W$name", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => string(wrench[k]))))
            push!(conns, bg_conn("cw$k", "signal", "w$k", "y", "n6", name))
        end
    end
    return bg_model("FreeBody3D", nodes, conns; t_end = t_end, points = points,
        reltol = 1.0e-9, abstol = 1.0e-11)
end

"""The fixed-base composition model: a joint pose and a constant local pose composed into the
link pose, and (when `truth`) a `PoseIntegrator3D` on the same CoM twist."""
function _mb8_pose_compose(; L = 0.5, rate = 2 * pi / 5, q0 = 0.3, truth = true,
    t_end = 10.0, points = 10001)
    gl = (1.0, 0.0, 0.0, 0.0, 0.0, 0.0, -L)
    # The CoM twist of the link: Ad(inv(gl)) applied to the joint screw S*rate, S = unit
    # rotation about x at the pivot. Ad(inv(gl)) = [[I, 0], [p_inv_hat, I]], p_inv = (0,0,L),
    # so v = (0, L rate, 0).
    Vb = [rate, 0.0, 0.0, 0.0, L * rate, 0.0]
    # g(0) = R_x(q0) composed with the local translation.
    g0 = BGSim.SE3(BGSim.quat_exp(BGSim.SVector(q0, 0.0, 0.0)), BGSim.SVector(0.0, 0.0, 0.0)) *
         BGSim.SE3(BGSim.Quat(), BGSim.SVector(0.0, 0.0, -L))
    ch = BGSim.Mech.chart(g0)
    nodes = Any[
        bg_node("n1", "Joint", _mb8_inline(_MB8_POSE_JOINT);
            params = Dict{String,Any}("rate" => string(rate), "q0" => string(q0))),
        bg_node("n2", "Local", _mb8_inline(_MB8_POSE_CONST);
            params = Dict{String,Any}("qw" => "1.0", "qx" => "0.0", "qy" => "0.0",
                "qz" => "0.0", "x" => "0.0", "y" => "0.0", "z" => string(-L))),
        bg_node("n3", "Compose", bg_ref("stdlib:multibond/ComposePose3D")),
    ]
    conns = Any[
        bg_conn("c1", "signal", "n1", "g", "n3", "gp"),
        bg_conn("c2", "signal", "n2", "g", "n3", "gl"),
    ]
    if truth
        push!(nodes, _mb8_vec6("n4", "Twist", Vb))
        push!(nodes, bg_node("n5", "Truth", bg_ref("stdlib:multibond/PoseIntegrator3D");
            starts = Dict{String,Any}("qw" => string(ch[1]), "qx" => string(ch[2]),
                "qy" => string(ch[3]), "qz" => string(ch[4]), "px" => string(ch[5]),
                "py" => string(ch[6]), "pz" => string(ch[7]))))
        push!(conns, bg_conn("c3", "signal", "n4", "y", "n5", "tw"))
    end
    return bg_model("PoseCompose3D", nodes, conns; t_end = t_end, points = points,
        reltol = 1.0e-9, abstol = 1.0e-11)
end

"""The compiled differential states of a flattened model (`length(problem.u0)`): the compiled
set, not the manifest's `stats.states` (which counts only a `ddt` whose argument is a bare
name, so the component-wise `ddt(P[k])` states are not in it)."""
function _mb8_states(flat)
    lowered = BGSim.lower_model(flat; t_start = 0.0, t_end = 1.0)
    return length(lowered.problem.u0)
end

@testset "J-MB8 spatial vector primitives and pose integration" begin
    blocks = Dict(b.ref => b for b in Library.load_stdlib())

    # -----------------------------------------------------------------------------------
    # Catalog contract: clean, dimension 3, per-component units, frames
    # -----------------------------------------------------------------------------------
    @testset "catalog: clean, dimension 3, per-component units, frames" begin
        @test length(blocks) == length(ALL_REFS)   # the full catalog list lives in test_library.jl
        for ref in _MB8_NEW_REFS
            b = blocks[ref]
            @test b.group == "Multibond"
            @test isempty(check_block(b.ast))          # 0 errors and 0 warnings
            bal = block_balance(b.ast)
            @test bal.unknowns == bal.equations
            @test !isempty(b.description)
            @test !isempty(b.icon)
            spatial = any(p -> p.domain == "Spatial", b.interface.ports)
            if spatial
                @test b.interface.dimension == 3
            else
                @test get(b.interface, :dimension, nothing) === nothing
            end
            for d in b.interface.parameters
                @test !isempty(d.description)
            end
            # Every Spatial port carries the authoritative per-component units (D-MB2/
            # D-MB10) and a `frame` field (null = frame-neutral, D-MB5).
            env = Units.unit_env(b.ast)
            for p in b.interface.ports
                @test haskey(p, :frame)
                p.domain == "Spatial" || continue
                @test p.size == [6]
                for k in 1:6
                    @test env.labels[Symbol(p.name, ".e[", string(k), "]")] ==
                          _MB8_E_UNITS[k]
                    @test env.labels[Symbol(p.name, ".f[", string(k), "]")] ==
                          _MB8_F_UNITS[k]
                end
            end
            @test isempty([d for d in check_block(b.ast) if d.code == "E006"])
        end

        # The inertia is genuinely component-wise: a `Vec{3}` principal inertia (one unit)
        # and a mass, with the six momentum components left open (D-MB3/D-MB10).
        i = blocks["stdlib:multibond/ISpatial"]
        @test [d.name for d in i.interface.parameters] == ["J", "m"]
        @test i.interface.parameters[1].unit == "kg*m^2"
        @test i.interface.parameters[1].default == "[0.1, 0.1, 0.1]"
        @test i.interface.parameters[2].unit == "kg"
        # The mass is a divisor; the positive floor is a parameter attribute (a runtime E108
        # positivity check does not exist yet, so J[k] > 0 is documented in the block).
        @test i.interface.parameters[2].min == 1.0e-12
        @test [(d.name, d.size) for d in i.interface.variables] == [("P", [6])]
        @test i.interface.variables[1].unit === nothing
        @test i.interface.causality ==
              [(ports = ["p"], kind = "preferred", value = "flow_out")]

        # Storage and dissipation keep the per-component units of the stiffnesses.
        c = blocks["stdlib:multibond/CSpatial"]
        @test [d.unit for d in c.interface.parameters[1:6]] ==
              ["N*m/rad", "N*m/rad", "N*m/rad", "N/m", "N/m", "N/m"]
        @test [d.unit for d in c.interface.variables] ==
              ["rad", "rad", "rad", "m", "m", "m"]
        @test c.interface.causality ==
              [(ports = ["p"], kind = "preferred", value = "effort_out")]
        r = blocks["stdlib:multibond/RSpatial"]
        @test [d.unit for d in r.interface.parameters[1:6]] ==
              ["N*m*s/rad", "N*m*s/rad", "N*m*s/rad", "N*s/m", "N*s/m", "N*s/m"]
        @test isempty(r.interface.causality)          # free, exactly like the scalar R

        # The external wrench is the physical wrench: three torques and three forces with
        # distinct units, so no unit-homogeneous vector signal could carry it.
        ew = blocks["stdlib:multibond/ExternalWrenchSpatial"]
        @test [d.unit for d in ew.interface.inputs] ==
              ["N*m", "N*m", "N*m", "N", "N", "N"]
        @test length(unique([d.unit for d in ew.interface.inputs[1:3]])) == 1
        @test ew.interface.inputs[1].unit != ew.interface.inputs[4].unit
        @test ew.interface.causality ==
              [(ports = ["p"], kind = "fixed", value = "effort_out")]

        se = blocks["stdlib:multibond/SeSpatial"]
        @test [(d.name, d.size) for d in se.interface.inputs] == [("u", [6])]
        @test se.interface.causality ==
              [(ports = ["p"], kind = "fixed", value = "effort_out")]
        sf = blocks["stdlib:multibond/SfSpatial"]
        @test [(d.name, d.size) for d in sf.interface.inputs] == [("u", [6])]
        @test sf.interface.causality ==
              [(ports = ["p"], kind = "fixed", value = "flow_out")]

        # The diagonal TF modulus is dimensionless (so the checker still proves each port
        # component keeps its own unit); the matrix forms carry no single unit.
        tf = blocks["stdlib:multibond/TFSpatial"]
        @test tf.interface.parameters[1].unit == "1"
        @test count(==(','), tf.interface.parameters[1].default) == 5   # six components
        @test tf.interface.causality ==
              [(ports = ["a", "b"], kind = "transformer", value = nothing)]
        tfm = blocks["stdlib:multibond/TFSpatialMat"]
        @test tfm.interface.parameters[1].unit === nothing
        @test count(==(';'), tfm.interface.parameters[1].default) == 5   # six rows
        @test tfm.interface.causality ==
              [(ports = ["a", "b"], kind = "transformer", value = nothing)]
        gy = blocks["stdlib:multibond/GYSpatial"]
        @test gy.interface.parameters[1].unit === nothing
        @test count(==(';'), gy.interface.parameters[1].default) == 5
        @test gy.interface.causality ==
              [(ports = ["a", "b"], kind = "gyrator", value = nothing)]
        mtf = blocks["stdlib:multibond/MTFSpatial"]
        @test mtf.interface.inputs[1].unit == "1"
        @test [(d.name, d.size) for d in mtf.interface.inputs] == [("u", [6])]
        mgy = blocks["stdlib:multibond/MGYSpatial"]
        @test mgy.interface.inputs[1].unit === nothing
        @test [(d.name, d.size) for d in mgy.interface.inputs] == [("G", [6, 6])]

        # The transforms keep the DEC-MB-1 frame semantics: the world/body bridge, and the
        # joint-role pair parent/child (D-MB5).
        ft = blocks["stdlib:multibond/FixedTransform3D"]
        @test [p.frame for p in ft.interface.ports] == ["world", "body"]
        @test [d.unit for d in ft.interface.parameters] ==
              ["1", "1", "1", "1", "m", "m", "m"]
        # The neutral mount is the body -> body form: both sides neutral (TFAdNeutral's
        # spatial sibling), so each side adopts its adjacent frame.
        ftn = blocks["stdlib:multibond/FixedTransform3DNeutral"]
        @test all(p -> p.frame === nothing, ftn.interface.ports)
        @test [d.name for d in ftn.interface.parameters] ==
              [d.name for d in ft.interface.parameters]
        @test ftn.interface.causality ==
              [(ports = ["a", "b"], kind = "transformer", value = nothing)]
        jt = blocks["stdlib:multibond/JointTransform3D"]
        # The joint transform is frame-neutral on purpose: a joint composite bonds `a`/`b`
        # to `ISpatial` (`body`) or `GroundSpatial` (`world`), and a named role frame would
        # make every such bond E007. The two ports stay separate unions (see the frame test).
        @test all(p -> p.frame === nothing, jt.interface.ports)
        @test [(d.name, d.size) for d in jt.interface.inputs] == [("g", [7])]
        @test jt.interface.causality ==
              [(ports = ["a", "b"], kind = "transformer", value = nothing)]
        gnd = blocks["stdlib:multibond/GroundSpatial"]
        @test [p.frame for p in gnd.interface.ports] == ["world"]
        gr = blocks["stdlib:multibond/GravitySpatial"]
        @test [d.unit for d in gr.interface.parameters] == ["kg", "m/s^2"]
        cp = blocks["stdlib:multibond/ComposePose3D"]
        @test [(d.name, d.size) for d in cp.interface.inputs] ==
              [("gp", [7]), ("gl", [7])]
        @test [(d.name, d.size) for d in cp.interface.outputs] == [("g", [7])]
        pi = blocks["stdlib:multibond/PoseIntegrator3D"]
        @test [(d.name, d.size) for d in pi.interface.inputs] == [("tw", [6])]
        @test [(d.name, d.size) for d in pi.interface.outputs] == [("g", [7])]
        @test [(d.name, d.unit) for d in pi.interface.variables[1:4]] ==
              [("qw", "1"), ("qx", "1"), ("qy", "1"), ("qz", "1")]
        @test [(d.name, d.unit) for d in pi.interface.variables[5:7]] ==
              [("px", "m"), ("py", "m"), ("pz", "m")]
        for ref in ("stdlib:multibond/DeSpatial", "stdlib:multibond/DfSpatial")
            @test [(d.name, d.size) for d in blocks[ref].interface.outputs] == [("y", [6])]
        end
    end

    # -----------------------------------------------------------------------------------
    # Free body: momentum, energy, Dzhanibekov
    # -----------------------------------------------------------------------------------
    @testset "free body: world momentum, kinetic energy, Dzhanibekov flip" begin
        m = 2.0
        J = (1.0, 2.0, 3.0)
        P0 = (0.3, 1.5, -0.7, 0.6, -0.4, 0.9)
        doc = _mb8_free(J = J, m = m, P0 = P0)
        checked = _mb8_check(doc)
        @test isempty(_mb8_errors(checked))
        @test _mb8_w201(checked) == 0
        columns, result, flat = bg_run(doc)
        @test result.status == "done"
        @test isempty(_mb8_errors(result))
        @test _mb8_w201(result) == 0
        # Six momentum states plus the seven pose states; the model is an index-0 ODE.
        @test _mb8_states(flat) == 13
        t = columns["time"]
        h = [columns["I/P[$k]"] for k in 1:3]
        pl = [columns["I/P[$k]"] for k in 4:6]

        # Kinetic energy 1/2 (h.J^-1 h + p.m^-1 p) and the world momentum (R h, R p) are
        # conserved: no external wrench acts (g0 = 0, no ExternalWrenchSpatial).
        ke = 0.5 .* (sum(h[k] .^ 2 ./ J[k] for k in 1:3) .+ sum(pl[k] .^ 2 ./ m for k in 1:3))
        ke_drift = maximum(abs.(ke .- ke[1])) / abs(ke[1])
        hw = zeros(length(t), 3)
        pw = zeros(length(t), 3)
        for i in eachindex(t)
            q, _ = _mb8_pose(columns, "Pose/g", i)
            R = BGSim.quat_to_matrix(q)
            hw[i, :] = R * [h[k][i] for k in 1:3]
            pw[i, :] = R * [pl[k][i] for k in 1:3]
        end
        hw_drift = maximum(abs.(hw .- reshape(hw[1, :], 1, 3))) / max(1.0, maximum(abs.(hw)))
        pw_drift = maximum(abs.(pw .- reshape(pw[1, :], 1, 3))) / max(1.0, maximum(abs.(pw)))
        @test ke_drift <= 1.0e-6                       # plan 9.1 target
        @test hw_drift <= 1.0e-6
        @test pw_drift <= 1.0e-6
        # The quaternion state stays on the unit sphere without a projection callback.
        qn = sqrt.(sum(columns["Pose/g[$k]"] .^ 2 for k in 1:4))
        @test maximum(abs.(qn .- 1.0)) <= 1.0e-9
        println("J-MB8 free body: KE drift = ", ke_drift, ", world H drift = ", hw_drift,
            ", world P drift = ", pw_drift, ", quat norm drift = ",
            maximum(abs.(qn .- 1.0)))

        # Dzhanibekov: spin about the *intermediate* principal axis (J2 between J1 and J3)
        # with a small perturbation. The body frame flips; the world angular momentum and
        # the energy do not move.
        @test J[1] < J[2] < J[3]
        w0 = (0.05, 3.0, 0.0)
        P0d = (J[1] * w0[1], J[2] * w0[2], J[3] * w0[3], 0.0, 0.0, 0.0)
        docd = _mb8_free(J = J, m = m, P0 = P0d)
        @test _mb8_w201(_mb8_check(docd)) == 0
        cd, rd, _ = bg_run(docd)
        @test rd.status == "done"
        @test _mb8_w201(rd) == 0
        wy = cd["I/twout[2]"]
        @test maximum(wy) >= 0.9 * w0[2]
        @test minimum(wy) <= -0.9 * w0[2]              # the spin axis reversed: a flip
        flips = count(i -> wy[i] * wy[i + 1] < 0, 1:(length(wy) - 1))
        @test flips >= 1
        hd = [cd["I/P[$k]"] for k in 1:3]
        ked = 0.5 .* sum(hd[k] .^ 2 ./ J[k] for k in 1:3)
        hwd = zeros(length(cd["time"]), 3)
        for i in eachindex(cd["time"])
            q, _ = _mb8_pose(cd, "Pose/g", i)
            hwd[i, :] = BGSim.quat_to_matrix(q) * [hd[k][i] for k in 1:3]
        end
        hwd_drift = maximum(abs.(hwd .- reshape(hwd[1, :], 1, 3))) /
                    max(1.0, maximum(abs.(hwd)))
        ked_drift = maximum(abs.(ked .- ked[1])) / abs(ked[1])
        @test hwd_drift <= 1.0e-6
        @test ked_drift <= 1.0e-6
        println("J-MB8 Dzhanibekov: w_y in [", minimum(wy), ", ", maximum(wy),
            "], sign changes = ", flips, ", world H drift = ", hwd_drift,
            ", KE drift = ", ked_drift)
    end

    # -----------------------------------------------------------------------------------
    # Floating-base screw motion and the quaternion norm
    # -----------------------------------------------------------------------------------
    @testset "floating base: constant-twist screw vs analytic SE(3) exp" begin
        J = (1.0, 2.0, 3.0)
        m = 2.0
        # A screw about x (a principal axis) with pitch h = 0.5: v = h*w. That is a
        # constant *body* twist and a free motion (ad(V)^T P = 0), so the pose is exactly
        # g(t) = g(0) exp(V t).
        V = BGSim.Twist{6}(1.5, 0.0, 0.0, 0.75, 0.0, 0.0)
        P0 = (J[1] * V[1], J[2] * V[2], J[3] * V[3], m * V[4], m * V[5], m * V[6])
        g0 = BGSim.SE3(BGSim.quat_exp(BGSim.SVector(0.3, -0.5, 0.2)),
            BGSim.SVector(0.4, -0.2, 0.7))
        ch = BGSim.Mech.chart(g0)
        doc = _mb8_free(J = J, m = m, P0 = P0, pose0 = Tuple(ch))
        checked = _mb8_check(doc)
        @test isempty(_mb8_errors(checked))
        @test _mb8_w201(checked) == 0
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        @test _mb8_w201(result) == 0
        t = columns["time"]
        worst = 0.0
        worst_q = 0.0
        for i in eachindex(t)
            exact = g0 * BGSim.exp(BGSim.Twist{6}(V[1] * t[i], V[2] * t[i], V[3] * t[i],
                V[4] * t[i], V[5] * t[i], V[6] * t[i]))
            qg, pg = _mb8_pose(columns, "Pose/g", i)
            che = BGSim.Mech.chart(exact)
            qe = BGSim.Quat(che[1], che[2], che[3], che[4])
            pe = BGSim.translation(exact)
            worst = max(worst, _mb8_pose_error(qg, pg, qe, pe))
            # A chart canonicalises q_w >= 0 and an integrated q does not: compare up to sign.
            dq = min(norm([qg.w, qg.x, qg.y, qg.z] - [qe.w, qe.x, qe.y, qe.z]),
                norm([qg.w, qg.x, qg.y, qg.z] + [qe.w, qe.x, qe.y, qe.z]))
            worst_q = max(worst_q, dq)
        end
        @test worst <= 1.0e-6
        @test worst_q <= 1.0e-6
        # The body twist really is the input: no momentum drift along the screw.
        @test maximum(maximum(abs.(columns["I/twout[$k]"] .- V[k])) for k in 1:6) <= 1.0e-9
        qn = sqrt.(sum(columns["Pose/g[$k]"] .^ 2 for k in 1:4))
        drift = maximum(abs.(qn .- 1.0))
        @test drift <= 1.0e-9
        println("J-MB8 screw: max pose error over 10 s = ", worst,
            " (quaternion ", worst_q, "), quat norm drift = ", drift)
    end

    # -----------------------------------------------------------------------------------
    # Fixed-base pose composition vs integrated truth; floating-base-only rule
    # -----------------------------------------------------------------------------------
    @testset "fixed-base composition vs integrated truth, floating base only" begin
        L = 0.5
        rate = 2 * pi / 5
        q0 = 0.3
        doc = _mb8_pose_compose(L = L, rate = rate, q0 = q0, truth = true)
        checked = _mb8_check(doc)
        @test isempty(_mb8_errors(checked))
        @test _mb8_w201(checked) == 0
        columns, result, flat = bg_run(doc)
        @test result.status == "done"
        @test _mb8_w201(result) == 0
        # Seven pose states (the truth integrator) + one joint angle.
        @test _mb8_states(flat) == 8
        t = columns["time"]
        # The composed pose is the analytic forward kinematics g(q) composed with gl.
        q = q0 .+ rate .* t
        @test maximum(abs.(columns["Compose/g[6]"] .- L .* sin.(q))) <= 1e-12
        @test maximum(abs.(columns["Compose/g[7]"] .+ L .* cos.(q))) <= 1e-12
        @test maximum(abs.(columns["Compose/g[1]"] .- cos.(q ./ 2))) <= 1e-12
        @test maximum(abs.(columns["Compose/g[2]"] .- sin.(q ./ 2))) <= 1e-12
        # ... and it agrees with the pose integrated from the same CoM twist.
        worst = 0.0
        for i in eachindex(t)
            qc, pc = _mb8_pose(columns, "Compose/g", i)
            qt, pt = _mb8_pose(columns, "Truth/g", i)
            worst = max(worst, _mb8_pose_error(qc, pc, qt, pt))
        end
        @test worst <= 1.0e-6
        qn = sqrt.(sum(columns["Truth/g[$k]"] .^ 2 for k in 1:4))
        @test maximum(abs.(qn .- 1.0)) <= 1.0e-9
        println("J-MB8 fixed-base pose: composed vs integrated max error over 10 s = ", worst,
            ", quat norm drift = ", maximum(abs.(qn .- 1.0)))

        # The floating-base-only rule (D-MB6): a fixed-base chain composes its pose and
        # holds no pose state at all. Only the joint coordinate is integrated.
        docf = _mb8_pose_compose(L = L, rate = rate, q0 = q0, truth = false,
            t_end = 10.0, points = 1001)
        cf, rf, flatf = bg_run(docf)
        @test rf.status == "done"
        @test _mb8_states(flatf) == 1
        @test flatf.stats.instances == 3
        @test maximum(abs.(cf["Compose/g[6]"] .- L .* sin.(q0 .+ rate .* cf["time"]))) <= 1e-6
        @test maximum(abs.(cf["Compose/g[7]"] .+ L .* cos.(q0 .+ rate .* cf["time"]))) <= 1e-6
        println("J-MB8 fixed-base chain: differential states = ", _mb8_states(flatf),
            " (no pose integrator), composed pose exact to ",
            maximum(abs.(cf["Compose/g[6]"] .- L .* sin.(q0 .+ rate .* cf["time"]))))
    end

    # -----------------------------------------------------------------------------------
    # Two-port elements: random power continuity and the Coriolis/ad identity
    # -----------------------------------------------------------------------------------
    @testset "TF/TFMat/GY/MTF/MGY: random power continuity (relative 1e-9)" begin
        rng = _mb8_rng(824)
        worst = 0.0
        for case in 1:2
            E = [rng(), rng(), rng(), rng(), rng(), rng()]
            F = [rng(), rng(), rng(), rng(), rng(), rng()]
            n = [0.5 + abs(rng()) for _ in 1:6]
            M = [rng() for _ in 1:6, _ in 1:6]
            G = [rng() for _ in 1:6, _ in 1:6]
            for i in 1:6
                M[i, i] += 2.0
                G[i, i] += 2.0
            end
            cases = [
                ("TFSpatial", "stdlib:multibond/TFSpatial",
                    Dict{String,Any}("n" => "[" * join(string.(n), ", ") * "]")),
                ("TFSpatialMat", "stdlib:multibond/TFSpatialMat",
                    Dict{String,Any}("M" => _mb8_mat_text(M))),
            ]
            for (label, ref, params) in cases
                doc = bg_model("TF$(label)$case", Any[
                    _mb8_vec6("n1", "Ue", E),
                    _mb8_vec6("n2", "Uf", F),
                    bg_node("n3", "A", bg_ref("stdlib:multibond/SeSpatial")),
                    bg_node("n4", "B", bg_ref("stdlib:multibond/SfSpatial")),
                    bg_node("n5", "T", bg_ref(ref); params = params),
                ], Any[
                    bg_conn("c1", "signal", "n1", "y", "n3", "u"),
                    bg_conn("c2", "signal", "n2", "y", "n4", "u"),
                    bg_conn("c3", "bond", "n3", "p", "n5", "a"),
                    bg_conn("c4", "bond", "n5", "b", "n4", "p"),
                ]; t_end = 0.01, points = 2, reltol = 1.0e-10, abstol = 1.0e-12)
                @test isempty(_mb8_errors(_mb8_check(doc)))
                columns, result, _ = bg_run(doc)
                @test result.status == "done"
                ae = _mb8_vec(columns, "T/a.e", 1)
                af = _mb8_vec(columns, "T/a.f", 1)
                be = _mb8_vec(columns, "T/b.e", 1)
                bf = _mb8_vec(columns, "T/b.f", 1)
                @test isapprox(ae, E; atol = 1e-11)
                @test isapprox(bf, -F; atol = 1e-11)
                if label == "TFSpatial"
                    @test isapprox(af, n .* bf; atol = 1e-11)
                    @test isapprox(be, -n .* ae; atol = 1e-11)
                else
                    @test isapprox(af, M * bf; atol = 1e-11)
                    @test isapprox(be, -transpose(M) * ae; atol = 1e-11)
                end
                @test maximum(abs.(af)) > 1e-2            # the test is not vacuous
                res = _mb8_power_residual(columns, "T/a", "T/b", 1)
                worst = max(worst, res)
                @test res <= 1.0e-9
            end

            # The modulated TF: the modulus is a signal.
            doc = bg_model("TFMTFSpatial$case", Any[
                _mb8_vec6("n1", "Ue", E),
                _mb8_vec6("n2", "Uf", F),
                bg_node("n3", "A", bg_ref("stdlib:multibond/SeSpatial")),
                bg_node("n4", "B", bg_ref("stdlib:multibond/SfSpatial")),
                bg_node("n5", "T", bg_ref("stdlib:multibond/MTFSpatial")),
                _mb8_vec6("mod", "Uu", n),
            ], Any[
                bg_conn("c1", "signal", "n1", "y", "n3", "u"),
                bg_conn("c2", "signal", "n2", "y", "n4", "u"),
                bg_conn("c3", "bond", "n3", "p", "n5", "a"),
                bg_conn("c4", "bond", "n5", "b", "n4", "p"),
                bg_conn("c5", "signal", "mod", "y", "n5", "u"),
            ]; t_end = 0.01, points = 2, reltol = 1.0e-10, abstol = 1.0e-12)
            @test isempty(_mb8_errors(_mb8_check(doc)))
            columns, result, _ = bg_run(doc)
            @test result.status == "done"
            ae = _mb8_vec(columns, "T/a.e", 1)
            af = _mb8_vec(columns, "T/a.f", 1)
            be = _mb8_vec(columns, "T/b.e", 1)
            bf = _mb8_vec(columns, "T/b.f", 1)
            @test isapprox(ae, E; atol = 1e-11)
            @test isapprox(bf, -F; atol = 1e-11)
            @test isapprox(af, n .* bf; atol = 1e-11)
            @test isapprox(be, -n .* ae; atol = 1e-11)
            res = _mb8_power_residual(columns, "T/a", "T/b", 1)
            worst = max(worst, res)
            @test res <= 1.0e-9

            # The gyrators define a.e from b.f, so the load on b is a resistor (free
            # causality), exactly like the planar GY test: b.e = -r.*b.f and b.e = -G^T a.f
            # give b.f = (G^T a.f)./r, and a.e = G b.f then fixes a.f.
            r = [0.7 + abs(rng()), 0.9 + abs(rng()), 1.1 + abs(rng()),
                0.8 + abs(rng()), 1.2 + abs(rng()), 0.6 + abs(rng())]
            gys = [
                ("GYSpatial", "stdlib:multibond/GYSpatial", Dict{String,Any}(),
                    Dict{String,Any}("G" => _mb8_mat_text(G)), nothing),
                ("MGYSpatial", "stdlib:multibond/MGYSpatial", Dict{String,Any}(),
                    Dict{String,Any}(), _mb8_mat6("mod", "Ug", G)),
            ]
            for (label, ref, params, extra, modnode) in gys
                nodes = Any[
                    _mb8_vec6("n1", "Ue", E),
                    bg_node("n2", "A", bg_ref("stdlib:multibond/SeSpatial")),
                    bg_node("n3", "T", bg_ref(ref);
                        params = merge(params, extra)),
                    bg_node("n4", "R", bg_ref("stdlib:multibond/RSpatial");
                        params = Dict{String,Any}("brx" => string(r[1]),
                            "bry" => string(r[2]), "brz" => string(r[3]),
                            "bx" => string(r[4]), "by" => string(r[5]),
                            "bz" => string(r[6]))),
                ]
                conns = Any[
                    bg_conn("c1", "signal", "n1", "y", "n2", "u"),
                    bg_conn("c2", "bond", "n2", "p", "n3", "a"),
                    bg_conn("c3", "bond", "n4", "p", "n3", "b"),
                ]
                if modnode !== nothing
                    push!(nodes, modnode)
                    push!(conns, bg_conn("c4", "signal", "mod", "G", "n3", "G"))
                end
                doc = bg_model("GY$(label)$case", nodes, conns; t_end = 0.01,
                    points = 2, reltol = 1.0e-10, abstol = 1.0e-12)
                @test isempty(_mb8_errors(_mb8_check(doc)))
                columns, result, _ = bg_run(doc)
                @test result.status == "done"
                ae = _mb8_vec(columns, "T/a.e", 1)
                af = _mb8_vec(columns, "T/a.f", 1)
                be = _mb8_vec(columns, "T/b.e", 1)
                bf = _mb8_vec(columns, "T/b.f", 1)
                @test isapprox(ae, E; atol = 1e-11)
                @test isapprox(ae, G * bf; atol = 1e-10)
                @test isapprox(be, -transpose(G) * af; atol = 1e-10)
                @test isapprox(bf, (transpose(G) * af) ./ r; atol = 1e-10)
                expected_af = inv(G * Diagonal(1.0 ./ r) * transpose(G)) * E
                @test isapprox(af, expected_af; atol = 1e-10)
                @test norm(af) > 1e-3
                res = _mb8_power_residual(columns, "T/a", "T/b", 1)
                worst = max(worst, res)
                @test res <= 1.0e-9
            end
        end
        println("J-MB8 two-port power residual (random, 10 models) = ", worst)
    end

    @testset "CoriolisSpatial: e = -ad(V)^T P and V^T ad(V)^T P = 0" begin
        rng = _mb8_rng(31415)
        worst = 0.0
        for case in 1:2
            V = [rng(), rng(), rng(), rng(), rng(), rng()]
            P = [rng(), rng(), rng(), rng(), rng(), rng()]
            # The Lie identity, numeric (plan 9.2: random V and random P).
            adV = BGSim.ad(BGSim.Twist{6}(V...))
            @test abs(dot(V, transpose(adV) * P)) <=
                  1.0e-12 * max(1.0, norm(V) * norm(transpose(adV) * P))
            # The block: a flow source on a direct bond drives the port, the momentum is a
            # signal. Its recorded own flow is the source twist with the bond's sign.
            doc = bg_model("Coriolis$case", Any[
                _mb8_vec6("n1", "Uv", V),
                _mb8_vec6("n2", "Up", P),
                bg_node("n3", "S", bg_ref("stdlib:multibond/SfSpatial")),
                bg_node("n4", "Cor", bg_ref("stdlib:multibond/CoriolisSpatial")),
            ], Any[
                bg_conn("c1", "signal", "n1", "y", "n3", "u"),
                bg_conn("c2", "bond", "n3", "p", "n4", "p"),
                bg_conn("c3", "signal", "n2", "y", "n4", "P"),
            ]; t_end = 0.01, points = 2, reltol = 1.0e-10, abstol = 1.0e-12)
            @test isempty(_mb8_errors(_mb8_check(doc)))
            columns, result, _ = bg_run(doc)
            @test result.status == "done"
            f = _mb8_vec(columns, "Cor/p.f", 1)
            e = _mb8_vec(columns, "Cor/p.e", 1)
            @test isapprox(f, -V; atol = 1e-12)
            adf = BGSim.ad(BGSim.Twist{6}(f...))
            expected = -transpose(adf) * P
            @test isapprox(e, expected; atol = 1e-11)
            # The element's own power is zero: the structure is power-continuous.
            res = abs(dot(e, f)) / max(1.0, norm(e) * norm(f))
            worst = max(worst, res)
            @test res <= 1.0e-9
        end
        println("J-MB8 CoriolisSpatial: worst |e.f| relative = ", worst)
    end

    # -----------------------------------------------------------------------------------
    # One-port elements: C, R, Ground, De, Df
    # -----------------------------------------------------------------------------------
    @testset "one-port elements: C, R, Ground, De, Df" begin
        F = [-0.4, 0.7, 0.35, 0.2, -0.1, 0.5]
        k = [2.0, 3.0, 4.0, 10.0, 20.0, 30.0]
        doc = bg_model("CSpatialDrive", Any[
            _mb8_vec6("n1", "U", F),
            bg_node("n2", "S", bg_ref("stdlib:multibond/SfSpatial")),
            bg_node("n3", "C", bg_ref("stdlib:multibond/CSpatial");
                params = Dict{String,Any}("krx" => "2.0", "kry" => "3.0", "krz" => "4.0",
                    "kx" => "10.0", "ky" => "20.0", "kz" => "30.0")),
        ], Any[
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "bond", "n2", "p", "n3", "p"),
        ]; t_end = 0.5, points = 3, reltol = 1.0e-10, abstol = 1.0e-12)
        @test isempty(_mb8_errors(_mb8_check(doc)))
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        t = columns["time"]
        # ddt(q[k]) = p.f[k] and p.e[k] = k[k]*q[k]: the port flow is the source's -F, so
        # q[k] = -F[k]*t and the effort is -k[k]*F[k]*t.
        for kk in 1:6
            @test isapprox(columns["C/p.f[$kk]"], -F[kk] .* ones(length(t)); atol = 1e-12)
            @test maximum(abs.(columns["C/p.e[$kk]"] .- (-k[kk] * F[kk] .* t))) <= 1e-11
        end

        E = [1.1, -0.9, 0.6, 2.0, -3.0, 1.5]
        b = [1.1, 1.3, 1.7, 2.0, 3.0, 4.0]
        doc = bg_model("RSpatialDrive", Any[
            _mb8_vec6("n1", "U", E),
            bg_node("n2", "S", bg_ref("stdlib:multibond/SeSpatial")),
            bg_node("n3", "R", bg_ref("stdlib:multibond/RSpatial");
                params = Dict{String,Any}("brx" => "1.1", "bry" => "1.3", "brz" => "1.7",
                    "bx" => "2.0", "by" => "3.0", "bz" => "4.0")),
        ], Any[
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "bond", "n2", "p", "n3", "p"),
        ]; t_end = 0.1, points = 2, reltol = 1.0e-10, abstol = 1.0e-12)
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        e = _mb8_vec(columns, "R/p.e", 1)
        f = _mb8_vec(columns, "R/p.f", 1)
        # Bond relativity: the effort is shared and the flow flips, so the resistor sees the
        # source effort and the reciprocal flow.
        @test isapprox(e, E; atol = 1e-12)
        @test isapprox(f, E ./ b; atol = 1e-12)
        # Dissipative: p.e . p.f = sum b f^2 >= 0.
        @test dot(e, f) > 0.0
        @test isapprox(dot(e, f), sum(b .* f .^ 2); rtol = 1e-12)

        # GroundSpatial holds a zero twist: bonded to DfSpatial it reads zero and the effort
        # is zero too (Df imposes e = 0).
        doc = bg_model("GroundDf", Any[
            bg_node("n1", "Gnd", bg_ref("stdlib:multibond/GroundSpatial")),
            bg_node("n2", "D", bg_ref("stdlib:multibond/DfSpatial")),
        ], Any[bg_conn("c1", "bond", "n1", "p", "n2", "p")];
            t_end = 0.1, points = 2, reltol = 1.0e-10, abstol = 1.0e-12)
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        @test all(iszero, _mb8_vec(columns, "D/y", 1))

        # DeSpatial reads a wrench on a 0-junction; DfSpatial reads a twist on a 1-junction.
        doc = bg_model("DeSpatialDrive", Any[
            _mb8_vec6("n1", "U", E),
            bg_node("n2", "S", bg_ref("stdlib:multibond/SeSpatial")),
            bg_node("n3", "J", bg_junction("0")),
            bg_node("n4", "D", bg_ref("stdlib:multibond/DeSpatial")),
        ], Any[
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "bond", "n2", "p", "n3", nothing),
            bg_conn("c3", "bond", "n4", "p", "n3", nothing),
        ]; t_end = 0.1, points = 2, reltol = 1.0e-10, abstol = 1.0e-12)
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        @test isapprox(_mb8_vec(columns, "D/y", 1), E; atol = 1e-12)

        doc = bg_model("DfSpatialDrive", Any[
            _mb8_vec6("n1", "U", F),
            bg_node("n2", "S", bg_ref("stdlib:multibond/SfSpatial")),
            bg_node("n3", "J", bg_junction("1")),
            bg_node("n4", "D", bg_ref("stdlib:multibond/DfSpatial")),
        ], Any[
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "bond", "n2", "p", "n3", nothing),
            bg_conn("c3", "bond", "n4", "p", "n3", nothing),
        ]; t_end = 0.1, points = 2, reltol = 1.0e-10, abstol = 1.0e-12)
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        @test isapprox(_mb8_vec(columns, "D/y", 1), F; atol = 1e-12)
    end

    @testset "GravitySpatial and ExternalWrenchSpatial: signs and units" begin
        m = 2.0
        g0 = 9.81
        theta = 0.7
        # A body released from rest at a pose rotated by theta about x: gravity in the body
        # frame is -m g0 R[3,:] = -m g0 (0, sin theta, cos theta), so P_lin(t) moves that way.
        doc = _mb8_free(m = m, g0 = g0,
            pose0 = (cos(theta / 2), sin(theta / 2), 0.0, 0.0, 0.0, 0.0, 0.0),
            t_end = 1.0, points = 2001)
        checked = _mb8_check(doc)
        @test isempty(_mb8_errors(checked))
        @test _mb8_w201(checked) == 0
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        t = columns["time"]
        @test maximum(abs.(columns["I/P[4]"])) <= 1e-12
        @test maximum(abs.(columns["I/P[5]"] .- (-m * g0 * sin(theta) .* t))) <= 1e-9
        @test maximum(abs.(columns["I/P[6]"] .- (-m * g0 * cos(theta) .* t))) <= 1e-9
        @test maximum(abs.(columns["I/P[1]"])) <= 1e-12       # gravity acts at the CoM
        println("J-MB8 gravity: P_y(1 s) = ", columns["I/P[5]"][end], " (analytic ",
            -m * g0 * sin(theta), "), P_z = ", columns["I/P[6]"][end], " (analytic ",
            -m * g0 * cos(theta), ")")

        # ExternalWrenchSpatial: the inputs are the physical wrench. A force-only case moves
        # only the linear momentum, a torque-only case only the angular one: torque and
        # force keep their own units and their own momentum components all the way to the
        # state. (A combined case is not a straight line: with w != 0 the body-frame linear
        # momentum also carries the Coriolis term w x p.)
        fx, fy, fz = 1.2, -0.8, -2.3
        doc = _mb8_free(m = m, g0 = 0.0, wrench = (0.0, 0.0, 0.0, fx, fy, fz),
            t_end = 2.0, points = 2001)
        checked = _mb8_check(doc)
        @test isempty(_mb8_errors(checked))
        @test _mb8_w201(checked) == 0
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        t = columns["time"]
        @test maximum(abs.(columns["I/P[4]"] .- fx .* t)) <= 1e-9
        @test maximum(abs.(columns["I/P[5]"] .- fy .* t)) <= 1e-9
        @test maximum(abs.(columns["I/P[6]"] .- fz .* t)) <= 1e-9
        @test maximum(maximum(abs.(columns["I/P[$k]"])) for k in (1, 2, 3)) <= 1e-12
        # The port effort is -W_ext: the element supplies the negative of the physical wrench
        # to the 1-junction, and the inertia feels +W_ext.
        @test isapprox(columns["W/p.e[4]"][1], -fx; atol = 1e-12)
        @test isapprox(columns["W/p.e[6]"][1], -fz; atol = 1e-12)

        tau = 1.4
        doc = _mb8_free(m = m, J = (0.5, 1.0, 1.5), g0 = 0.0,
            wrench = (tau, 0.0, 0.0, 0.0, 0.0, 0.0), t_end = 2.0, points = 2001)
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        t = columns["time"]
        @test maximum(abs.(columns["I/P[1]"] .- tau .* t)) <= 1e-9
        @test maximum(maximum(abs.(columns["I/P[$k]"])) for k in (2, 3, 4, 5, 6)) <= 1e-12
        println("J-MB8 wrench: P_ang_x(2 s) = ", columns["I/P[1]"][end],
            " (tau*t = ", 2 * tau, "), P_lin_z(2 s) = ",
            _mb8_vec(columns, "I/P", 1)[6], " / earlier force run (F*t = ", 2 * fz, ")")
    end

    # -----------------------------------------------------------------------------------
    # FixedTransform3D / JointTransform3D: the adjoint pair, power-continuous
    # -----------------------------------------------------------------------------------
    @testset "FixedTransform3D/JointTransform3D: a.f = -Ad(g) b.f, b.e = Ad(g)^T a.e" begin
        rng = _mb8_rng(2718)
        g = BGSim.SE3(BGSim.quat_exp(BGSim.SVector(0.4, -0.9, 0.6)),
            BGSim.SVector(0.3, -1.1, 0.7))
        ch = BGSim.Mech.chart(g)
        E = [rng(), rng(), rng(), rng(), rng(), rng()]
        F = [rng(), rng(), rng(), rng(), rng(), rng()]
        pose_params = Dict{String,Any}("qw" => string(ch[1]), "qx" => string(ch[2]),
            "qy" => string(ch[3]), "qz" => string(ch[4]), "x" => string(ch[5]),
            "y" => string(ch[6]), "z" => string(ch[7]))
        for (label, ref) in (("Fixed", "stdlib:multibond/FixedTransform3D"),
            ("Joint", "stdlib:multibond/JointTransform3D"))
            nodes = Any[
                _mb8_vec6("n1", "Ue", E),
                _mb8_vec6("n2", "Uf", F),
                bg_node("n3", "A", bg_ref("stdlib:multibond/SeSpatial")),
                bg_node("n4", "B", bg_ref("stdlib:multibond/SfSpatial")),
                bg_node("n5", "T", bg_ref(ref);
                    params = label == "Fixed" ? pose_params : Dict{String,Any}()),
            ]
            conns = Any[
                bg_conn("c1", "signal", "n1", "y", "n3", "u"),
                bg_conn("c2", "signal", "n2", "y", "n4", "u"),
                bg_conn("c3", "bond", "n3", "p", "n5", "a"),
                bg_conn("c4", "bond", "n4", "p", "n5", "b"),
            ]
            if label == "Joint"
                push!(nodes, bg_node("n6", "Pose", _mb8_inline(_MB8_POSE_CONST);
                    params = pose_params))
                push!(conns, bg_conn("c5", "signal", "n6", "g", "n5", "g"))
            end
            doc = bg_model("Transform$label", nodes, conns; t_end = 0.01, points = 2,
                reltol = 1.0e-10, abstol = 1.0e-12)
            @test isempty(_mb8_errors(_mb8_check(doc)))
            columns, result, _ = bg_run(doc)
            @test result.status == "done"
            ae = _mb8_vec(columns, "T/a.e", 1)
            af = _mb8_vec(columns, "T/a.f", 1)
            be = _mb8_vec(columns, "T/b.e", 1)
            bf = _mb8_vec(columns, "T/b.f", 1)
            Adg = Matrix(BGSim.Ad(g))
            @test isapprox(ae, E; atol = 1e-11)
            @test isapprox(bf, -F; atol = 1e-11)
            @test isapprox(af, -Adg * bf; atol = 1e-10)
            @test isapprox(be, transpose(Adg) * ae; atol = 1e-10)
            @test _mb8_power_residual(columns, "T/a", "T/b", 1) <= 1e-9
        end
    end

    # -----------------------------------------------------------------------------------
    # Frames end to end: the world -> body bridge, the neutral mount, E007
    # -----------------------------------------------------------------------------------
    @testset "frames: world->body bridge, neutral body->body mount, E007" begin
        # (1) The checked world -> body mount is E007-clean: Ground (world) -> FixedTransform3D
        # -> ISpatial (body). The frame union of each bond is the *body* on the far side, so
        # the transform really bridges the two named frames.
        doc = bg_model("WorldBodyBridge", Any[
            bg_node("n1", "Gnd", bg_ref("stdlib:multibond/GroundSpatial")),
            bg_node("n2", "Mount", bg_ref("stdlib:multibond/FixedTransform3D");
                params = Dict{String,Any}("z" => "-0.5")),
            bg_node("n3", "I", bg_ref("stdlib:multibond/ISpatial")),
        ], Any[
            bg_conn("c1", "bond", "n1", "p", "n2", "a"),
            bg_conn("c2", "bond", "n2", "b", "n3", "p"),
        ]; t_end = 0.1, points = 2, reltol = 1.0e-9, abstol = 1.0e-11)
        checked = _mb8_check(doc)
        @test isempty(_mb8_errors(checked))
        @test checked.frames["c1"] == "Mount/world"
        @test checked.frames["c2"] == "I/body"
        # A rigidly clamped inertia is the document DEC-MB-2 DAE (the momentum is in
        # derivative causality); that is the *attachment*, not the frame, and the run fails
        # with E901 exactly as the planar rigid joint does. The runnable mount model is the
        # forward transformer direction asserted below.
        @test _mb8_w201(checked) == 1
        columns, result, _ = bg_run(doc)
        @test result.status == "failed"
        @test _mb8_w201(result) >= 1
        @test any(d -> d.code in ("E901", "E103"), result.diagnostics)

        # (2) The negative: a direct Ground (world) -> I (body) bond is E007.
        doc = bg_model("WorldBodyDirect", Any[
            bg_node("n1", "Gnd", bg_ref("stdlib:multibond/GroundSpatial")),
            bg_node("n2", "I", bg_ref("stdlib:multibond/ISpatial")),
        ], Any[bg_conn("c1", "bond", "n1", "p", "n2", "p")];
            t_end = 0.1, points = 2, reltol = 1.0e-9, abstol = 1.0e-11)
        direct = _mb8_check(doc)
        @test count(d -> d.code == "E007", direct.diagnostics) == 1
        @test occursin("world", only(d.message for d in direct.diagnostics
                                     if d.code == "E007"))
        @test occursin("body", only(d.message for d in direct.diagnostics
                                    if d.code == "E007"))

        # (3) The body -> body mount: both sides of FixedTransform3DNeutral are neutral, so
        # each adopts its adjacent body and the two body unions are separate (bridged, never
        # unified). The mount itself is a rigid two-body constraint, so the model is a DAE
        # (W201) - the frame question is what is asserted here.
        doc = bg_model("BodyBodyMount", Any[
            bg_node("na", "NodeA", bg_junction("1")),
            bg_node("ia", "IA", bg_ref("stdlib:multibond/ISpatial")),
            bg_node("nb", "NodeB", bg_junction("1")),
            bg_node("ib", "IB", bg_ref("stdlib:multibond/ISpatial")),
            bg_node("mo", "Mount", bg_ref("stdlib:multibond/FixedTransform3DNeutral");
                params = Dict{String,Any}("z" => "-0.5")),
        ], Any[
            bg_conn("c1", "bond", "ia", "p", "na", nothing),
            bg_conn("c2", "bond", "mo", "a", "na", nothing),
            bg_conn("c3", "bond", "ib", "p", "nb", nothing),
            bg_conn("c4", "bond", "mo", "b", "nb", nothing),
        ]; t_end = 0.1, points = 2, reltol = 1.0e-9, abstol = 1.0e-11)
        mounted = _mb8_check(doc)
        @test !any(d -> d.code in ("E006", "E007", "E101", "E102"), mounted.diagnostics)
        @test mounted.frames["c2"] == "IA/body"
        @test mounted.frames["c4"] == "IB/body"
        @test mounted.frames["c2"] != mounted.frames["c4"]      # two unions, one bridge
        @test _mb8_w201(mounted) >= 1                           # the rigid mount is a DAE

        # (4) JointTransform3D is frame-neutral for the same reason: a joint composite bonds
        # it to two bodies (formerly E007 on both sides). The two body unions stay separate.
        doc = bg_model("BodyJointBody", Any[
            bg_node("na", "NodeA", bg_junction("1")),
            bg_node("ia", "IA", bg_ref("stdlib:multibond/ISpatial")),
            bg_node("nb", "NodeB", bg_junction("1")),
            bg_node("ib", "IB", bg_ref("stdlib:multibond/ISpatial")),
            bg_node("jt", "Joint", bg_ref("stdlib:multibond/JointTransform3D")),
            bg_node("po", "Pose", _mb8_inline(_MB8_POSE_CONST);
                params = Dict{String,Any}("z" => "-0.5")),
        ], Any[
            bg_conn("c1", "bond", "ia", "p", "na", nothing),
            bg_conn("c2", "bond", "jt", "a", "na", nothing),
            bg_conn("c3", "bond", "ib", "p", "nb", nothing),
            bg_conn("c4", "bond", "jt", "b", "nb", nothing),
            bg_conn("c5", "signal", "po", "g", "jt", "g"),
        ]; t_end = 0.1, points = 2, reltol = 1.0e-9, abstol = 1.0e-11)
        jointed = _mb8_check(doc)
        @test !any(d -> d.code in ("E006", "E007", "E101", "E102"), jointed.diagnostics)
        @test jointed.frames["c2"] == "IA/body"
        @test jointed.frames["c4"] == "IB/body"
        @test jointed.frames["c2"] != jointed.frames["c4"]

        # (5) The runnable mount model: the transformer's forward direction (effort in at a,
        # flow in at b). The a side is in `world`, the b side in `body`, and the model runs.
        rng = _mb8_rng(1618)
        E = [rng(), rng(), rng(), rng(), rng(), rng()]
        F = [rng(), rng(), rng(), rng(), rng(), rng()]
        doc = bg_model("WorldBodyRun", Any[
            _mb8_vec6("n1", "Ue", E),
            _mb8_vec6("n2", "Uf", F),
            bg_node("n3", "A", bg_ref("stdlib:multibond/SeSpatial")),
            bg_node("n4", "B", bg_ref("stdlib:multibond/SfSpatial")),
            bg_node("n5", "T", bg_ref("stdlib:multibond/FixedTransform3D");
                params = Dict{String,Any}("z" => "-0.5")),
        ], Any[
            bg_conn("c1", "signal", "n1", "y", "n3", "u"),
            bg_conn("c2", "signal", "n2", "y", "n4", "u"),
            bg_conn("c3", "bond", "n3", "p", "n5", "a"),
            bg_conn("c4", "bond", "n4", "p", "n5", "b"),
        ]; t_end = 0.01, points = 2, reltol = 1.0e-10, abstol = 1.0e-12)
        runcheck = _mb8_check(doc)
        @test isempty(_mb8_errors(runcheck))
        @test runcheck.frames["c3"] == "T/world"
        @test runcheck.frames["c4"] == "T/body"
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        @test isapprox(_mb8_vec(columns, "T/a.e", 1), E; atol = 1e-11)
        @test isapprox(_mb8_vec(columns, "T/b.f", 1), -F; atol = 1e-11)
        @test _mb8_power_residual(columns, "T/a", "T/b", 1) <= 1e-9
        println("J-MB8 frames: world/body bridge E007", count(d -> d.code == "E007",
                direct.diagnostics), " (direct), clamped mount W201 = ",
            _mb8_w201(checked), ", runnable mount status = ", result.status)
    end

    # -----------------------------------------------------------------------------------
    # A fixed-base composed pose drives gravity (the planar suite's analogue)
    # -----------------------------------------------------------------------------------
    @testset "fixed-base ComposedPose3D drives GravitySpatial" begin
        L = 0.5
        rate = 2 * pi / 5
        q0 = 0.3
        m = 2.0
        g0 = 9.81
        # The body has no pose state: its pose is the composed chain g(q) composed with the
        # local mount, and `GravitySpatial` reads exactly that chart.
        doc = bg_model("ComposedGravity", Any[
            bg_node("n1", "Joint", _mb8_inline(_MB8_POSE_JOINT);
                params = Dict{String,Any}("rate" => string(rate), "q0" => string(q0))),
            bg_node("n2", "Local", _mb8_inline(_MB8_POSE_CONST);
                params = Dict{String,Any}("z" => string(-L))),
            bg_node("n3", "Compose", bg_ref("stdlib:multibond/ComposePose3D")),
            bg_node("n4", "Node", bg_junction("1")),
            bg_node("n5", "I", bg_ref("stdlib:multibond/ISpatial");
                params = Dict{String,Any}("J" => "[0.5, 1.0, 1.5]", "m" => string(m))),
            bg_node("n6", "G", bg_ref("stdlib:multibond/GravitySpatial");
                params = Dict{String,Any}("m" => string(m), "g0" => string(g0))),
            bg_node("n7", "Cor", bg_ref("stdlib:multibond/CoriolisSpatial")),
        ], Any[
            bg_conn("c1", "signal", "n1", "g", "n3", "gp"),
            bg_conn("c2", "signal", "n2", "g", "n3", "gl"),
            bg_conn("c3", "bond", "n5", "p", "n4", nothing),
            bg_conn("c4", "bond", "n6", "p", "n4", nothing),
            bg_conn("c5", "bond", "n7", "p", "n4", nothing),
            bg_conn("c6", "signal", "n3", "g", "n6", "g"),
            bg_conn("c7", "signal", "n5", "Pm", "n7", "P"),
        ]; t_end = 1.0, points = 101, reltol = 1.0e-9, abstol = 1.0e-11)
        checked = _mb8_check(doc)
        @test isempty(_mb8_errors(checked))
        @test _mb8_w201(checked) == 0
        columns, result, flat = bg_run(doc)
        @test result.status == "done"
        @test _mb8_w201(result) == 0
        # The fixed-base chain holds a *composed* pose, not an integrated one: only the joint
        # angle is a named-`ddt` state (the momentum uses the component-wise `ddt(P[k])` that
        # the manifest statistic does not count), so a `PoseIntegrator3D` here would show up
        # as seven more states and fail this line.
        @test flat.stats.states == 1
        @test all(all(columns["G/g[$k]"] .== columns["Compose/g[$k]"]) for k in 1:7)
        t = columns["time"]
        q = q0 .+ rate .* t
        # The composed pose is the analytic rotation about x, so the gravity port effort is
        # e = [0, 0, 0, 0, m g0 sin q, m g0 cos q] (GravityPlanar's spatial form).
        @test maximum(maximum(abs.(columns["G/p.e[$k]"])) for k in 1:4) <= 1e-12
        @test maximum(abs.(columns["G/p.e[5]"] .- m * g0 .* sin.(q))) <= 1e-9
        @test maximum(abs.(columns["G/p.e[6]"] .- m * g0 .* cos.(q))) <= 1e-9
        println("J-MB8 composed gravity: e[5] error = ",
            maximum(abs.(columns["G/p.e[5]"] .- m * g0 .* sin.(q))),
            ", e[6] error = ",
            maximum(abs.(columns["G/p.e[6]"] .- m * g0 .* cos.(q))),
            ", states = ", flat.stats.states)
    end

    # -----------------------------------------------------------------------------------
    # Per-component units on the produced run
    # -----------------------------------------------------------------------------------
    @testset "per-component units on the produced run" begin
        doc = _mb8_free(P0 = (0.3, 1.5, -0.7, 0.6, -0.4, 0.9),
            wrench = (1.4, 0.0, 0.0, 0.0, 0.0, -2.3), t_end = 0.1, points = 3)
        dir = mktempdir()
        parsed = IR.parse_model(doc)
        result = simulate(Compile.flatten(parsed); run_dir = dir,
            settings = BGSim.RunSettings(parsed.settings))
        @test result.status == "done"
        manifest = JSON3.read(read(joinpath(dir, "manifest.json"), String))
        labels = Dict{String,String}()
        for s in manifest.signals
            u = get(s, :unit, nothing)
            labels[String(s.id)] = u === nothing ? "" : String(u)
        end
        for k in 1:6
            @test labels["I/p.e[$k]"] == _MB8_E_UNITS[k]
            @test labels["I/p.f[$k]"] == _MB8_F_UNITS[k]
        end
        @test labels["I/p.P"] == "W"
        for k in 1:3
            @test labels["I/p.e[$k]"] != labels["I/p.e[$(k + 3)]"]   # torque vs force
            @test labels["I/p.f[$k]"] != labels["I/p.f[$(k + 3)]"]   # rad/s vs m/s
        end
        # The derived port power is the component sum on the produced run, and a 1-junction
        # conserves it: P_I + P_W = 0 (the Coriolis power is identically zero).
        columns = BondGraphGolden.bg_columns(dir)
        direct_i = [sum(columns["I/p.e[$k]"][i] * columns["I/p.f[$k]"][i] for k in 1:6)
                    for i in eachindex(columns["time"])]
        direct_w = [sum(columns["W/p.e[$k]"][i] * columns["W/p.f[$k]"][i] for k in 1:6)
                    for i in eachindex(columns["time"])]
        scale = max(1.0, maximum(abs.(direct_i)))
        @test maximum(abs.(columns["I/p.P"] .- direct_i)) <= 1e-12 * scale
        @test maximum(abs.(columns["W/p.P"] .- direct_w)) <= 1e-12 * scale
        @test maximum(abs.(columns["I/p.P"] .+ columns["W/p.P"])) <= 1e-9 * scale
        println("J-MB8 port power: max |P_I + P_W| = ",
            maximum(abs.(columns["I/p.P"] .+ columns["W/p.P"])),
            " of ", scale, " W, derivative is 0 to ",
            maximum(abs.(columns["I/p.P"] .- direct_i)))
    end
end
