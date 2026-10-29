# Work package J-MB9: the spatial body and joint composites (plan 6, row J-MB9; design
# correction of 2026-10-29 in plan/wps/M3-remaining-orchestration.md).
#
# The composites live in `stdlib/spatial/` beside the J-MB8 primitives:
#
#   RigidBody3D, LocalPose3D, Revolute3D (+ Compliant/Friction/Limit), Prismatic3D (+ the same
#   three), Helical3D, Cylindrical3D, Universal3D, Spherical3D, Planar3D, Free3D
#
# Every joint is a **fixed-structure typed joint** (no `JointBasis`, no zero screw column, no
# `ifelse` guard, no Gram inverse): the joint axis is the local z of the joint frame, the
# compliance sits on the complement `N`, and (J-MB9 review) the deflection chart is exact: both
# adjoints use the actual deflected pose `H`, the chart rates are the closed-form inverse of its
# Jacobian (a Gibbs vector for the vector deflections, an angle for the scalar one) and the
# wrench is the transpose, so the port power closes identically and the pose is the integral of
# the twists. The energy of a chain with a rotating parent is then exact at every stiffness.
#
# Every model runs through the real pipeline (`IR.parse_model` -> `Compile.flatten` ->
# `simulate`, Rodas5P, reltol 1e-9, abstol 1e-11). Tolerances follow plan 9.1: relative 1e-9 for
# algebraic identities, 1e-6 over 10 s for integrated trajectories. The chain references are an
# independent recursive Newton-Euler / RK4 written in this file. Every helper is `_msp_`-prefixed
# because the test files share `Main`.
using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import BGSim.Library
import BGSim.Units
using LinearAlgebra

if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using .BondGraphGolden

const _MSP_REFS = [
    "stdlib:spatial/Cylindrical3D",
    "stdlib:spatial/Free3D",
    "stdlib:spatial/Helical3D",
    "stdlib:spatial/LocalPose3D",
    "stdlib:spatial/Planar3D",
    "stdlib:spatial/Prismatic3D",
    "stdlib:spatial/Prismatic3DCompliant",
    "stdlib:spatial/Prismatic3DFriction",
    "stdlib:spatial/Prismatic3DLimit",
    "stdlib:spatial/Revolute3D",
    "stdlib:spatial/Revolute3DCompliant",
    "stdlib:spatial/Revolute3DFriction",
    "stdlib:spatial/Revolute3DLimit",
    "stdlib:spatial/RigidBody3D",
    "stdlib:spatial/Spherical3D",
    "stdlib:spatial/Universal3D",
]

const _MSP_E_UNITS = ["N*m", "N*m", "N*m", "N", "N", "N"]
const _MSP_F_UNITS = ["rad/s", "rad/s", "rad/s", "m/s", "m/s", "m/s"]

# ---------------------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------------------

_msp_check(doc) = Compile.model_check(IR.parse_model(doc))
_msp_errors(result) = [d for d in result.diagnostics if d.severity == "error"]
_msp_has(result, code) = any(d -> d.code == code, result.diagnostics)
_msp_w201(result) = count(d -> d.code == "W201", result.diagnostics)
_msp_vec(v) = "[" * join([string(x) for x in v], ", ") * "]"

_msp_hat(v) = [0.0 -v[3] v[2]; v[3] 0.0 -v[1]; -v[2] v[1] 0.0]
_msp_Rz(q) = [cos(q) -sin(q) 0.0; sin(q) cos(q) 0.0; 0.0 0.0 1.0]
_msp_Rx(q) = [1.0 0.0 0.0; 0.0 cos(q) -sin(q); 0.0 sin(q) cos(q)]
_msp_Ry(q) = [cos(q) 0.0 sin(q); 0.0 1.0 0.0; -sin(q) 0.0 cos(q)]

"""Rodrigues `exp([w])`."""
function _msp_expR(w)
    th = norm(w)
    th < 1.0e-14 && return Matrix(1.0I, 3, 3)
    K = _msp_hat(w ./ th)
    return Matrix(1.0I, 3, 3) + sin(th) * K + (1 - cos(th)) * K * K
end

"""Rotation matrix of the quaternion `(w, x, y, z)` (normalised)."""
function _msp_Rq(w, x, y, z)
    s = w * w + x * x + y * y + z * z
    return [
        (w * w + x * x - y * y - z * z) 2 * (x * y - w * z) 2 * (x * z + w * y)
        2 * (x * y + w * z) (w * w - x * x + y * y - z * z) 2 * (y * z - w * x)
        2 * (x * z - w * y) 2 * (y * z + w * x) (w * w - x * x - y * y + z * z)
    ] ./ s
end

"""Hamilton product."""
_msp_qmul(a, b) = [
    a[1] * b[1] - a[2] * b[2] - a[3] * b[3] - a[4] * b[4],
    a[1] * b[2] + a[2] * b[1] + a[3] * b[4] - a[4] * b[3],
    a[1] * b[3] - a[2] * b[4] + a[3] * b[1] + a[4] * b[2],
    a[1] * b[4] + a[2] * b[3] - a[3] * b[2] + a[4] * b[1],
]

"""The pose `(R, p)` of a model pose chart `prefix[1:7]` at sample `i`."""
function _msp_pose(columns, prefix, i)
    R = _msp_Rq(columns["$prefix[1]"][i], columns["$prefix[2]"][i],
        columns["$prefix[3]"][i], columns["$prefix[4]"][i])
    p = [columns["$prefix[5]"][i], columns["$prefix[6]"][i], columns["$prefix[7]"][i]]
    return R, p
end

"""Max entry error of a model pose against the reference `(R, p)` at sample `i`."""
function _msp_pose_err(columns, prefix, i, Rref, pref)
    R, p = _msp_pose(columns, prefix, i)
    return max(maximum(abs.(R .- Rref)), maximum(abs.(p .- pref)))
end

"""A pose parameter dict for `FixedTransform3DNeutral`/`LocalPose3D` from `(quaternion, position)`."""
function _msp_posepar(q, p)
    return Dict{String,Any}("qw" => string(q[1]), "qx" => string(q[2]), "qy" => string(q[3]),
        "qz" => string(q[4]), "x" => string(p[1]), "y" => string(p[2]), "z" => string(p[3]))
end

"""The inverse of the pose `(q, p)` (the pose of the world in the frame)."""
function _msp_inv(q, p)
    qc = [q[1], -q[2], -q[3], -q[4]]
    return qc, -(_msp_Rq(qc...) * p)
end

"""Upward zero crossings of `y`, linearly interpolated."""
function _msp_upward(t, y)
    out = Float64[]
    for i in 1:(length(y) - 1)
        if y[i] < 0 && y[i + 1] >= 0
            push!(out, t[i] + (t[i + 1] - t[i]) * (-y[i]) / (y[i + 1] - y[i]))
        end
    end
    return out
end

function _msp_period(t, y)
    c = _msp_upward(t, y)
    length(c) >= 3 || return NaN
    return c[3] - c[2]
end

"""A `Vec{6}` constant signal source (the imposed twists)."""
const _MSP_VEC6 = """
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

function _msp_vec6(id, name, v)
    return bg_node(id, name, Dict{String,Any}("inline" => Dict{String,Any}("source" => _MSP_VEC6));
        params = Dict{String,Any}("c1" => string(v[1]), "c2" => string(v[2]), "c3" => string(v[3]),
            "c4" => string(v[4]), "c5" => string(v[5]), "c6" => string(v[6])))
end

# The drive ports of every joint (name => domain).
const _MSP_PORTS = Dict(
    "stdlib:spatial/Revolute3D" => ["drive"],
    "stdlib:spatial/Revolute3DCompliant" => ["drive"],
    "stdlib:spatial/Revolute3DFriction" => ["drive"],
    "stdlib:spatial/Revolute3DLimit" => ["drive"],
    "stdlib:spatial/Prismatic3D" => ["drive"],
    "stdlib:spatial/Prismatic3DCompliant" => ["drive"],
    "stdlib:spatial/Prismatic3DFriction" => ["drive"],
    "stdlib:spatial/Prismatic3DLimit" => ["drive"],
    "stdlib:spatial/Helical3D" => ["drive"],
    "stdlib:spatial/Cylindrical3D" => ["drive1", "drive2"],
    "stdlib:spatial/Universal3D" => ["drive1", "drive2"],
    "stdlib:spatial/Spherical3D" => ["drive1", "drive2", "drive3"],
    "stdlib:spatial/Planar3D" => ["drive1", "drive2", "drive3"],
    "stdlib:spatial/Free3D" => ["drive1", "drive2", "drive3", "drive4", "drive5", "drive6"],
)

"""Append a zero-effort `Se` on every drive port of node `jid`."""
function _msp_drives!(nodes, conns, jid, ports; efforts = Dict{String,Float64}())
    for (k, port) in enumerate(ports)
        id = "d$(jid)_$k"
        push!(nodes, bg_node(id, "D_$(jid)_$(port)", bg_ref("stdlib:bondgraph/Se");
            params = Dict{String,Any}("e" => string(get(efforts, port, 0.0)))))
        push!(conns, bg_conn("cd$(jid)_$k", "bond", id, "p", jid, port))
    end
    return nothing
end

# ---------------------------------------------------------------------------------------
# Rigs. The transformers are written `a.f = -Ad(g) b.f`, `b.e = Ad(g)^T a.e` (flows from b to a,
# efforts from a to b), so `a` always attaches to the joint port and `b` to the ground or the
# body, and `g` is the pose of the body-side frame in the joint-side frame.
# ---------------------------------------------------------------------------------------

const _MSP_S2 = sqrt(0.5)
const _MSP_G = 9.81
const _MSP_Q_Y90 = [_MSP_S2, 0.0, _MSP_S2, 0.0]      # Ry(pi/2): the joint z axis is the world x

"""
    _msp_rig(; joint, params, starts, mount, body_pose, m, J, g0, P0, t_end, points, efforts)

`GroundSpatial -> mount -> joint -> link -> RigidBody3D`, with the body pose
`mount_pose o joint.pose o body_pose` composed from the joint's `pose` chart (fixed-base link
pose, D-MB6) and fed to the body's gravity. `mount = (q, p)` is the pose of the joint frame in
the world; `body_pose = (q, p)` the body frame (the centre of mass) in the joint child frame.
`P0` sets the body momentum through the composite start `inertia/P`.
"""
function _msp_rig(; joint, params = Dict{String,Any}(), starts = Dict{String,Any}(),
    mount = (_MSP_Q_Y90, zeros(3)), body_pose = ([1.0, 0.0, 0.0, 0.0], [0.5, 0.0, 0.0]),
    m = 1.0, J = (1.0e-3, 2.0e-3, 3.0e-3), g0 = _MSP_G, P0 = nothing,
    t_end = 1.0, points = 101, efforts = Dict{String,Float64}(), body_starts = Dict{String,Any}())
    bstarts = copy(body_starts)
    P0 === nothing || (bstarts["inertia/P"] = _msp_vec(P0))
    qi, pi_ = _msp_inv(mount...)
    nodes = Any[
        bg_node("n1", "World", bg_ref("stdlib:multibond/GroundSpatial")),
        bg_node("n2", "Mount", bg_ref("stdlib:multibond/FixedTransform3DNeutral");
            params = _msp_posepar(qi, pi_)),
        bg_node("n3", "Joint", bg_ref(joint); params = params, starts = starts),
        bg_node("n4", "Link", bg_ref("stdlib:multibond/FixedTransform3DNeutral");
            params = _msp_posepar(body_pose...)),
        bg_node("n5", "Body", bg_ref("stdlib:spatial/RigidBody3D");
            params = Dict{String,Any}("m" => string(m), "J" => _msp_vec(J), "g0" => string(g0)),
            starts = bstarts),
        bg_node("n6", "MountPose", bg_ref("stdlib:spatial/LocalPose3D"); params = _msp_posepar(mount...)),
        bg_node("n7", "LinkPose", bg_ref("stdlib:spatial/LocalPose3D"); params = _msp_posepar(body_pose...)),
        bg_node("n8", "C1", bg_ref("stdlib:multibond/ComposePose3D")),
        bg_node("n9", "C2", bg_ref("stdlib:multibond/ComposePose3D")),
    ]
    conns = Any[
        bg_conn("c1", "bond", "n1", "p", "n2", "b"),
        bg_conn("c2", "bond", "n2", "a", "n3", "parent"),
        bg_conn("c3", "bond", "n3", "child", "n4", "a"),
        bg_conn("c4", "bond", "n4", "b", "n5", "p"),
        bg_conn("c5", "signal", "n6", "g", "n8", "gp"),
        bg_conn("c6", "signal", "n3", "pose", "n8", "gl"),
        bg_conn("c7", "signal", "n8", "g", "n9", "gp"),
        bg_conn("c8", "signal", "n7", "g", "n9", "gl"),
        bg_conn("c9", "signal", "n9", "g", "n5", "g"),
    ]
    _msp_drives!(nodes, conns, "n3", _MSP_PORTS[joint]; efforts = efforts)
    return bg_model("Rig", nodes, conns; t_end = t_end, points = points,
        reltol = 1.0e-9, abstol = 1.0e-11)
end

"""
    _msp_kin(; joint, params, starts, child, parent, t_end, points)

A **kinematic** rig: the child port is bonded to an `SfSpatial` that imposes the child twist
`child` (a bond flips the flow sign, so the source is fed `-child`) (and the parent to another, or to the ground, so `parent = nothing` is the ground), and
every drive port to a zero `Se`. With the twist along the screw the deflections stay zero, so
the pose and the coordinates follow the analytic forward kinematics exactly.
"""
function _msp_kin(; joint, params = Dict{String,Any}(), starts = Dict{String,Any}(),
    child, parent = nothing, t_end = 2.0, points = 21)
    nodes = Any[
        bg_node("n3", "Joint", bg_ref(joint); params = params, starts = starts),
        _msp_vec6("n4", "Uc", -1 .* collect(child)),
        bg_node("n5", "Sc", bg_ref("stdlib:multibond/SfSpatial")),
    ]
    conns = Any[
        bg_conn("c1", "signal", "n4", "y", "n5", "u"),
        bg_conn("c2", "bond", "n5", "p", "n3", "child"),
    ]
    if parent === nothing
        push!(nodes, bg_node("n1", "World", bg_ref("stdlib:multibond/GroundSpatial")))
        push!(conns, bg_conn("c3", "bond", "n1", "p", "n3", "parent"))
    else
        push!(nodes, _msp_vec6("n6", "Up", -1 .* collect(parent)))
        push!(nodes, bg_node("n7", "Sp", bg_ref("stdlib:multibond/SfSpatial")))
        push!(conns, bg_conn("c3", "signal", "n6", "y", "n7", "u"))
        push!(conns, bg_conn("c4", "bond", "n7", "p", "n3", "parent"))
    end
    _msp_drives!(nodes, conns, "n3", _MSP_PORTS[joint])
    return bg_model("Kin", nodes, conns; t_end = t_end, points = points,
        reltol = 1.0e-9, abstol = 1.0e-11)
end

# ---------------------------------------------------------------------------------------
# Independent rigid-chain reference: recursive Newton-Euler + RK4 (written here, not derived
# from the model). A serial chain of revolute joints about the joint-frame z axis:
#   B_i = B_{i-1} o N_i o Rz(q_i) o M_i,  N_i = joint frame in the previous body, M_i = body in C_i.
# ---------------------------------------------------------------------------------------

_msp_Ad(R, p) = [R zeros(3, 3); _msp_hat(p) * R R]
_msp_ad(V) = [_msp_hat(V[1:3]) zeros(3, 3); _msp_hat(V[4:6]) _msp_hat(V[1:3])]
_msp_inert(m, J) = Matrix(Diagonal([J[1], J[2], J[3], m, m, m]))

struct _MspLink
    RN::Matrix{Float64}
    pN::Vector{Float64}
    RM::Matrix{Float64}
    pM::Vector{Float64}
    m::Float64
    J::NTuple{3,Float64}
end

"""Inverse dynamics: `(tau, f, poses)`. `f[i]` is the wrench the joint exerts on body `i` (body
frame, at the body origin), `poses[i] = (R, p)` the world pose of body `i`."""
function _msp_id(chain, q, qd, qdd; g = _MSP_G)
    n = length(chain)
    Vs = Vector{Vector{Float64}}(undef, n)
    As = Vector{Vector{Float64}}(undef, n)
    Ss = Vector{Vector{Float64}}(undef, n)
    Xs = Vector{Tuple{Matrix{Float64},Vector{Float64}}}(undef, n)
    Fs = Vector{Vector{Float64}}(undef, n)
    poses = Vector{Tuple{Matrix{Float64},Vector{Float64}}}(undef, n)
    Vp = zeros(6)
    Ap = [0.0, 0.0, 0.0, 0.0, 0.0, g]                  # gravity as a base acceleration
    Rw, pw = Matrix(1.0I, 3, 3), zeros(3)
    for i in 1:n
        L = chain[i]
        Rj = L.RN * _msp_Rz(q[i])
        pj = L.pN
        R = Rj * L.RM
        p = pj + Rj * L.pM
        Xs[i] = (R, p)
        Adinv = inv(_msp_Ad(R, p))
        # The screw of the coordinate: the twist of B_i about the z of C_i, in the body frame.
        S = inv(_msp_Ad(L.RM, L.pM)) * [0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
        Ss[i] = S
        Vs[i] = Adinv * Vp + S * qd[i]
        As[i] = Adinv * Ap + S * qdd[i] + _msp_ad(Vs[i]) * (S * qd[i])
        I6 = _msp_inert(L.m, L.J)
        Fs[i] = I6 * As[i] - _msp_ad(Vs[i])' * (I6 * Vs[i])
        Vp, Ap = Vs[i], As[i]
        Rw, pw = Rw * R, pw + Rw * p
        poses[i] = (copy(Rw), copy(pw))
    end
    f = [copy(F) for F in Fs]
    for i in n:-1:2
        f[i - 1] += inv(_msp_Ad(Xs[i]...))' * f[i]
    end
    tau = [dot(Ss[i], f[i]) for i in 1:n]
    return tau, f, poses, Vs
end

function _msp_fd(chain, q, qd; g = _MSP_G)
    n = length(chain)
    bias, = _msp_id(chain, q, qd, zeros(n); g = g)
    M = zeros(n, n)
    for j in 1:n
        e = zeros(n)
        e[j] = 1.0
        col, = _msp_id(chain, q, zeros(n), e; g = 0.0)
        M[:, j] = col
    end
    return M \ (-bias)
end

function _msp_rk4(chain, q0, qd0, dt, stride, t_end)
    n = length(chain)
    steps = round(Int, t_end / dt)
    rhs(y) = vcat(y[(n + 1):(2n)], _msp_fd(chain, y[1:n], y[(n + 1):(2n)]))
    y = vcat(q0, qd0)
    out = [copy(y)]
    for k in 1:steps
        k1 = rhs(y)
        k2 = rhs(y .+ (0.5 * dt) .* k1)
        k3 = rhs(y .+ (0.5 * dt) .* k2)
        k4 = rhs(y .+ dt .* k3)
        y = y .+ (dt / 6) .* (k1 .+ 2 .* k2 .+ 2 .* k3 .+ k4)
        k % stride == 0 && push!(out, copy(y))
    end
    return out
end

"""KE and PE of the rigid chain at `(q, qd)`."""
function _msp_chain_energy(chain, q, qd; g = _MSP_G)
    _, _, poses, Vs = _msp_id(chain, q, qd, zeros(length(chain)); g = g)
    ke = sum(0.5 * dot(Vs[i], _msp_inert(chain[i].m, chain[i].J) * Vs[i]) for i in eachindex(chain))
    pe = sum(chain[i].m * g * poses[i][2][3] for i in eachindex(chain))
    return ke, pe
end

"""The released-from-rest joint deflections of the chain: `child.e = -Ad(M)^-T f` and
`d = child.e / K` (so the stiff modes are not excited by the release, FIX-MB-3)."""
function _msp_d0(chain, q, kr, kt)
    n = length(chain)
    qdd = _msp_fd(chain, q, zeros(n))
    _, f, = _msp_id(chain, q, zeros(n), qdd)
    out = Vector{Tuple{Vector{Float64},Vector{Float64},Float64}}()
    for i in 1:n
        L = chain[i]
        e = -(inv(_msp_Ad(L.RM, L.pM))' * f[i])
        push!(out, ([e[1] / kr, e[2] / kr], e[4:6] ./ kt, e[3]))
    end
    return out
end

# ---------------------------------------------------------------------------------------
# Dynamic rigs: the single pendulum and the non-planar two-link chain
# ---------------------------------------------------------------------------------------

const _MSP_L = 0.5                       # m, joint to centre of mass
const _MSP_PM = 1.0                      # kg
const _MSP_PJ = (1.0e-3, 2.0e-3, 3.0e-3) # kg*m^2, principal moments (Jz about the joint axis)
const _MSP_I3 = Matrix(1.0I, 3, 3)
const _MSP_QI = [1.0, 0.0, 0.0, 0.0]

"""The rigid reference chain of the single pendulum (joint axis = world x, hanging along -z)."""
_msp_pend_chain(; L = _MSP_L, m = _MSP_PM, J = _MSP_PJ) =
    [_MspLink(_msp_Ry(pi / 2), zeros(3), _MSP_I3, [L, 0.0, 0.0], m, J)]

"""KE of a `RigidBody3D` from its recorded momentum."""
function _msp_ke(c, prefix, J, m)
    return 0.5 .* (c["$prefix/inertia/P[1]"] .^ 2 ./ J[1] .+ c["$prefix/inertia/P[2]"] .^ 2 ./ J[2] .+
                   c["$prefix/inertia/P[3]"] .^ 2 ./ J[3] .+ c["$prefix/inertia/P[4]"] .^ 2 ./ m .+
                   c["$prefix/inertia/P[5]"] .^ 2 ./ m .+ c["$prefix/inertia/P[6]"] .^ 2 ./ m)
end

"""Strain energy of a joint's deflections: `1/2 kr |rotational|^2 + 1/2 kt |translational|^2`
over whichever deflection outputs the joint has (`dang`, `ddef`, `dlin`, `dzout`)."""
function _msp_strain(c, joint, kr, kt)
    s = zeros(length(c["time"]))
    for k in 1:3
        haskey(c, "$joint/dang[$k]") && (s .+= 0.5 * kr .* c["$joint/dang[$k]"] .^ 2)
        haskey(c, "$joint/dlin[$k]") && (s .+= 0.5 * kt .* c["$joint/dlin[$k]"] .^ 2)
    end
    haskey(c, "$joint/ddef") && (s .+= 0.5 * kr .* c["$joint/ddef"] .^ 2)
    haskey(c, "$joint/dzout") && (s .+= 0.5 * kt .* c["$joint/dzout"] .^ 2)
    return s
end

"""
    _msp_pendulum(; joint, q0, kt, kr, extra, ...)

`GroundSpatial -> mount (joint z = world x) -> joint -> link (x = L) -> RigidBody3D`, released at
rest at the joint angle `q0`; the deflection starts are the released-from-rest values of the rigid
reference (`_msp_d0`) so the stiff modes are not excited. `truth = true` adds a `PoseIntegrator3D`
fed the body twist, started at the analytic initial pose.
"""
function _msp_pendulum(; joint = "stdlib:spatial/Revolute3D", q0 = 0.01, kt = 1.0e8, kr = 1.0e8,
    extra = Dict{String,Any}(), t_end = 4.0, points = 401, truth = false, deflect = true,
    g0 = _MSP_G, L = _MSP_L, efforts = Dict{String,Float64}(), P0 = nothing,
    body_starts = Dict{String,Any}())
    d0 = _msp_d0(_msp_pend_chain(L = L), [q0], kr, kt)[1]
    starts = deflect ? Dict{String,Any}("dth" => _msp_vec(d0[1]), "dl" => _msp_vec(d0[2])) :
             Dict{String,Any}()
    params = merge(Dict{String,Any}("kt" => string(kt), "kr" => string(kr), "q0" => string(q0)), extra)
    doc = _msp_rig(; joint = joint, params = params, starts = starts,
        mount = (_MSP_Q_Y90, zeros(3)), body_pose = (_MSP_QI, [L, 0.0, 0.0]), m = _MSP_PM,
        J = _MSP_PJ, g0 = g0, t_end = t_end, points = points, efforts = efforts, P0 = P0,
        body_starts = body_starts)
    if truth
        qz = _msp_qmul(_MSP_Q_Y90, [cos(q0 / 2), 0.0, 0.0, sin(q0 / 2)])
        p0 = _msp_Ry(pi / 2) * (_msp_Rz(q0) * [L, 0.0, 0.0])
        push!(doc["diagram"]["nodes"], bg_node("n10", "Truth", bg_ref("stdlib:multibond/PoseIntegrator3D");
            starts = Dict{String,Any}("qw" => string(qz[1]), "qx" => string(qz[2]),
                "qy" => string(qz[3]), "qz" => string(qz[4]), "px" => string(p0[1]),
                "py" => string(p0[2]), "pz" => string(p0[3]))))
        push!(doc["diagram"]["connections"], bg_conn("ct", "signal", "n5", "V", "n10", "tw"))
    end
    return doc
end

# The non-planar two-link chain: joint 1 about the world x, joint 2 about the y axis of link 1
# (perpendicular to joint 1 and to the link), so the second link leaves the first link's plane
# and the gyroscopic couplings are all active. Rods along the local x, unequal principal moments.
const _MSP_DP = (m1 = 2.0, m2 = 1.5, r1 = 0.2, l1 = 0.4, r2 = 0.2,
    J1 = (0.002, 0.0267, 0.0275), J2 = (0.0015, 0.02, 0.0205))

function _msp_dp_chain(p = _MSP_DP)
    return [
        _MspLink(_msp_Ry(pi / 2), zeros(3), _MSP_I3, [p.r1, 0.0, 0.0], p.m1, p.J1),
        _MspLink(_msp_Rx(-pi / 2), [p.l1 - p.r1, 0.0, 0.0], _MSP_I3, [p.r2, 0.0, 0.0], p.m2, p.J2),
    ]
end

"""`Ground -> mount -> J1 -> L1 -> (B1 + T2) -> J2 -> L2 -> B2`, both joints `Revolute3D` at
stiffness `kk` (rotational and translational), released at rest at `(q1, q2)` with the
consistent deflections. The second joint's parent is body 1, which rotates."""
function _msp_double(kk; q1 = 0.4, q2 = 0.6, t_end = 1.5, points = 301, p = _MSP_DP,
    joint = "stdlib:spatial/Revolute3D")
    chain = _msp_dp_chain(p)
    d0 = _msp_d0(chain, [q1, q2], kk, kk)
    function jnode(id, name, q0, d)
        return bg_node(id, name, bg_ref(joint);
            params = Dict{String,Any}("kt" => string(kk), "kr" => string(kk), "q0" => string(q0)),
            starts = Dict{String,Any}("dth" => _msp_vec(d[1]), "dl" => _msp_vec(d[2])))
    end
    qi, pi_ = _msp_inv(_MSP_Q_Y90, zeros(3))
    n2q = [_MSP_S2, -_MSP_S2, 0.0, 0.0]               # Rx(-pi/2): joint 2 frame in body 1
    n2p = [p.l1 - p.r1, 0.0, 0.0]
    n2qi, n2pi = _msp_inv(n2q, n2p)
    body(id, name, m, J) = bg_node(id, name, bg_ref("stdlib:spatial/RigidBody3D");
        params = Dict{String,Any}("m" => string(m), "J" => _msp_vec(J), "g0" => string(_MSP_G)))
    nodes = Any[
        bg_node("n1", "World", bg_ref("stdlib:multibond/GroundSpatial")),
        bg_node("n2", "Mount", bg_ref("stdlib:multibond/FixedTransform3DNeutral"); params = _msp_posepar(qi, pi_)),
        jnode("n3", "J1", q1, d0[1]),
        bg_node("n4", "Link1", bg_ref("stdlib:multibond/FixedTransform3DNeutral");
            params = _msp_posepar(_MSP_QI, [p.r1, 0.0, 0.0])),
        bg_node("n5", "BJ1", bg_junction("1")),
        body("n6", "B1", p.m1, p.J1),
        bg_node("n7", "T2", bg_ref("stdlib:multibond/FixedTransform3DNeutral"); params = _msp_posepar(n2qi, n2pi)),
        jnode("n8", "J2", q2, d0[2]),
        bg_node("n9", "Link2", bg_ref("stdlib:multibond/FixedTransform3DNeutral");
            params = _msp_posepar(_MSP_QI, [p.r2, 0.0, 0.0])),
        bg_node("n10", "BJ2", bg_junction("1")),
        body("n11", "B2", p.m2, p.J2),
        bg_node("n12", "LPm", bg_ref("stdlib:spatial/LocalPose3D"); params = _msp_posepar(_MSP_Q_Y90, zeros(3))),
        bg_node("n13", "LPM1", bg_ref("stdlib:spatial/LocalPose3D"); params = _msp_posepar(_MSP_QI, [p.r1, 0.0, 0.0])),
        bg_node("n14", "LPN2", bg_ref("stdlib:spatial/LocalPose3D"); params = _msp_posepar(n2q, n2p)),
        bg_node("n15", "LPM2", bg_ref("stdlib:spatial/LocalPose3D"); params = _msp_posepar(_MSP_QI, [p.r2, 0.0, 0.0])),
        bg_node("n16", "C1", bg_ref("stdlib:multibond/ComposePose3D")),
        bg_node("n17", "C2", bg_ref("stdlib:multibond/ComposePose3D")),
        bg_node("n18", "C3", bg_ref("stdlib:multibond/ComposePose3D")),
        bg_node("n19", "C4", bg_ref("stdlib:multibond/ComposePose3D")),
        bg_node("n20", "C5", bg_ref("stdlib:multibond/ComposePose3D")),
    ]
    conns = Any[
        bg_conn("c1", "bond", "n1", "p", "n2", "b"),
        bg_conn("c2", "bond", "n2", "a", "n3", "parent"),
        bg_conn("c3", "bond", "n3", "child", "n4", "a"),
        bg_conn("c4", "bond", "n4", "b", "n5", nothing),
        bg_conn("c5", "bond", "n6", "p", "n5", nothing),
        bg_conn("c6", "bond", "n7", "b", "n5", nothing),
        bg_conn("c7", "bond", "n7", "a", "n8", "parent"),
        bg_conn("c8", "bond", "n8", "child", "n9", "a"),
        bg_conn("c9", "bond", "n9", "b", "n10", nothing),
        bg_conn("c10", "bond", "n11", "p", "n10", nothing),
        bg_conn("c11", "signal", "n12", "g", "n16", "gp"),
        bg_conn("c12", "signal", "n3", "pose", "n16", "gl"),
        bg_conn("c13", "signal", "n16", "g", "n17", "gp"),
        bg_conn("c14", "signal", "n13", "g", "n17", "gl"),
        bg_conn("c15", "signal", "n17", "g", "n6", "g"),
        bg_conn("c16", "signal", "n17", "g", "n18", "gp"),
        bg_conn("c17", "signal", "n14", "g", "n18", "gl"),
        bg_conn("c18", "signal", "n18", "g", "n19", "gp"),
        bg_conn("c19", "signal", "n8", "pose", "n19", "gl"),
        bg_conn("c20", "signal", "n19", "g", "n20", "gp"),
        bg_conn("c21", "signal", "n15", "g", "n20", "gl"),
        bg_conn("c22", "signal", "n20", "g", "n11", "g"),
    ]
    _msp_drives!(nodes, conns, "n3", ["drive"])
    _msp_drives!(nodes, conns, "n8", ["drive"])
    return bg_model("DoublePendulum3D", nodes, conns; t_end = t_end, points = points,
        reltol = 1.0e-9, abstol = 1.0e-11)
end

"""The two-link chain's total energy: both KEs, the potential of the **actual** body origins (the
composed pose includes the deflections) and both joints' strain."""
function _msp_dp_energy(c, kk; p = _MSP_DP)
    ke = _msp_ke(c, "B1", p.J1, p.m1) .+ _msp_ke(c, "B2", p.J2, p.m2)
    pe = _MSP_G .* (p.m1 .* c["C2/g[7]"] .+ p.m2 .* c["C5/g[7]"])
    return ke .+ pe .+ _msp_strain(c, "J1", kk, kk) .+ _msp_strain(c, "J2", kk, kk)
end

# ---------------------------------------------------------------------------------------
# More rigs: prismatic mass-spring, a driven (rotating) parent, the free-body pair
# ---------------------------------------------------------------------------------------

"""A prismatic mass on a `SpringDamper` (optionally with a constant axial force) on the drive."""
function _msp_prismatic(; m = 2.0, k = 200.0, dmp = 0.0, force = nothing, q0 = 0.1,
    t_end = 3.0, points = 3001, joint = "stdlib:spatial/Prismatic3D",
    extra = Dict{String,Any}(), P0 = nothing, with_spring = true)
    bstarts = P0 === nothing ? Dict{String,Any}() : Dict{String,Any}("inertia/P" => _msp_vec(P0))
    nodes = Any[
        bg_node("n1", "World", bg_ref("stdlib:multibond/GroundSpatial")),
        bg_node("n2", "Joint", bg_ref(joint);
            params = merge(Dict{String,Any}("kr" => "1.0e8", "kt" => "1.0e8", "q0" => string(q0)), extra)),
        bg_node("n3", "Body", bg_ref("stdlib:spatial/RigidBody3D");
            params = Dict{String,Any}("m" => string(m), "J" => "[0.1, 0.1, 0.1]", "g0" => "0.0"),
            starts = bstarts),
        bg_node("n6", "Axis", bg_junction("1")),
        bg_node("n7", "Pose", bg_ref("stdlib:spatial/LocalPose3D")),
    ]
    conns = Any[
        bg_conn("c1", "bond", "n1", "p", "n2", "parent"),
        bg_conn("c2", "bond", "n2", "child", "n3", "p"),
        bg_conn("c3", "bond", "n2", "drive", "n6", nothing),
        bg_conn("c6", "signal", "n7", "g", "n3", "g"),
    ]
    if with_spring
        push!(nodes, bg_node("n4", "Spring", bg_ref("stdlib:translation/SpringDamper");
            params = Dict{String,Any}("k" => string(k), "d" => string(dmp)),
            starts = Dict{String,Any}("x" => string(q0))))
        push!(nodes, bg_node("n5", "Anchor", bg_ref("stdlib:translation/Fixed")))
        push!(conns, bg_conn("c4", "bond", "n4", "a", "n6", nothing))
        push!(conns, bg_conn("c5", "wire", "n4", "b", "n5", "a"))
    else
        push!(nodes, bg_node("n4", "Free", bg_ref("stdlib:bondgraph/Se");
            params = Dict{String,Any}("e" => "0.0")))
        push!(conns, bg_conn("c4", "bond", "n4", "p", "n6", nothing))
    end
    if force !== nothing
        push!(nodes, bg_node("n8", "One", bg_ref("stdlib:sources/Constant");
            params = Dict{String,Any}("value" => "1.0")))
        push!(nodes, bg_node("n10", "Force", bg_ref("stdlib:translation/ForceSource");
            params = Dict{String,Any}("F" => string(force))))
        push!(nodes, bg_node("n11", "FAnchor", bg_ref("stdlib:translation/Fixed")))
        push!(conns, bg_conn("c7", "signal", "n8", "y", "n10", "u"))
        push!(conns, bg_conn("c8", "bond", "n10", "a", "n6", nothing))
        push!(conns, bg_conn("c9", "wire", "n10", "b", "n11", "a"))
    end
    return bg_model("PrismaticMassSpring", nodes, conns; t_end = t_end, points = points,
        reltol = 1.0e-9, abstol = 1.0e-11)
end

"""A joint whose **parent is driven** at the constant twist `parent` (an `SfSpatial`), the child a
`RigidBody3D` with its centre of mass at `offset` in the child frame (no gravity). The parent
source does the work, so the joint's port-power identity is the check."""
function _msp_driven_parent(; joint, params = Dict{String,Any}(), starts = Dict{String,Any}(),
    parent, offset = (0.0, 0.0, 0.0), m = 1.0, J = (0.05, 0.06, 0.07), t_end = 1.0,
    points = 201, efforts = Dict{String,Float64}(), P0 = nothing)
    bstarts = P0 === nothing ? Dict{String,Any}() : Dict{String,Any}("inertia/P" => _msp_vec(P0))
    nodes = Any[
        _msp_vec6("n6", "Up", -1 .* collect(parent)),
        bg_node("n7", "Sp", bg_ref("stdlib:multibond/SfSpatial")),
        bg_node("n3", "Joint", bg_ref(joint); params = params, starts = starts),
        bg_node("n4", "Link", bg_ref("stdlib:multibond/FixedTransform3DNeutral");
            params = _msp_posepar(_MSP_QI, collect(offset))),
        bg_node("n5", "Body", bg_ref("stdlib:spatial/RigidBody3D");
            params = Dict{String,Any}("m" => string(m), "J" => _msp_vec(J), "g0" => "0.0"),
            starts = bstarts),
        bg_node("n8", "Pose", bg_ref("stdlib:spatial/LocalPose3D")),
    ]
    conns = Any[
        bg_conn("c1", "signal", "n6", "y", "n7", "u"),
        bg_conn("c2", "bond", "n7", "p", "n3", "parent"),
        bg_conn("c3", "bond", "n3", "child", "n4", "a"),
        bg_conn("c4", "bond", "n4", "b", "n5", "p"),
        bg_conn("c5", "signal", "n8", "g", "n5", "g"),
    ]
    _msp_drives!(nodes, conns, "n3", _MSP_PORTS[joint]; efforts = efforts)
    return bg_model("DrivenParent", nodes, conns; t_end = t_end, points = points,
        reltol = 1.0e-9, abstol = 1.0e-11)
end

"""`max |lhs - rhs| / max |lhs|` of the joint's port-power identity on a run: `lhs` is the sum of
the recorded port powers (parent, child, drive) and `rhs` the strain-energy rate, the damping
power and the joint-coordinate effort power, `sum F_k xdot_k + ts qdot`, with the chart rates
`xdot = B V_rel` rebuilt here from the recorded relative twist and the deflection outputs (the
exact Gibbs-chart inverse Jacobian of the joint header, not the block's own rate variables)."""
function _msp_power_residual(c; kind, kr, kt, br, bt)
    col(n) = c["Joint/$n"]
    V(k) = col("Vrelout[$k]")
    lhs = col("parent.P") .+ col("child.P") .+ col("drive.P")
    qdot = col("qdout")
    ts = haskey(c, "Joint/tauout") ? col("tauout") : zeros(length(lhs))
    rhs = ts .* qdot
    if kind == :revolute
        d1, d2 = col("dang[1]"), col("dang[2]")
        gx, gy = 0.5 .* d1, 0.5 .* d2
        l = [col("dlin[$k]") for k in 1:3]
        # dth' = B23 w, dl' = v - w x dl
        t1 = (1 .+ gx .^ 2 .- gy .^ 2) .* V(1) .+ 2 .* gx .* gy .* V(2) .+ 2 .* gy .* V(3)
        t2 = 2 .* gx .* gy .* V(1) .+ (1 .- gx .^ 2 .+ gy .^ 2) .* V(2) .- 2 .* gx .* V(3)
        ld = [V(4) .- (V(2) .* l[3] .- V(3) .* l[2]),
              V(5) .- (V(3) .* l[1] .- V(1) .* l[3]),
              V(6) .- (V(1) .* l[2] .- V(2) .* l[1])]
        rhs = rhs .+ (kr .* d1 .+ br .* t1) .* t1 .+ (kr .* d2 .+ br .* t2) .* t2
        for k in 1:3
            rhs = rhs .+ (kt .* l[k] .+ bt .* ld[k]) .* ld[k]
        end
    else # prismatic
        d = [col("dang[$k]") for k in 1:3]
        g = [0.5 .* d[k] for k in 1:3]
        l = [col("dlin[1]"), col("dlin[2]")]
        # dth' = w + g x w + g (g . w), (dl_x', dl_y') = (Rg v)_xy with Rg = R(1, g) / (1 + |g|^2)
        gw = g[1] .* V(1) .+ g[2] .* V(2) .+ g[3] .* V(3)
        td = [V(1) .+ (g[2] .* V(3) .- g[3] .* V(2)) .+ g[1] .* gw,
              V(2) .+ (g[3] .* V(1) .- g[1] .* V(3)) .+ g[2] .* gw,
              V(3) .+ (g[1] .* V(2) .- g[2] .* V(1)) .+ g[3] .* gw]
        D = 1 .+ g[1] .^ 2 .+ g[2] .^ 2 .+ g[3] .^ 2
        ld = [((1 .+ g[1] .^ 2 .- g[2] .^ 2 .- g[3] .^ 2) .* V(4) .+ 2 .* (g[1] .* g[2] .- g[3]) .* V(5) .+
               2 .* (g[1] .* g[3] .+ g[2]) .* V(6)) ./ D,
              (2 .* (g[1] .* g[2] .+ g[3]) .* V(4) .+ (1 .- g[1] .^ 2 .+ g[2] .^ 2 .- g[3] .^ 2) .* V(5) .+
               2 .* (g[2] .* g[3] .- g[1]) .* V(6)) ./ D]
        for k in 1:3
            rhs = rhs .+ (kr .* d[k] .+ br .* td[k]) .* td[k]
        end
        for k in 1:2
            rhs = rhs .+ (kt .* l[k] .+ bt .* ld[k]) .* ld[k]
        end
    end
    return maximum(abs.(lhs .- rhs)) / max(maximum(abs.(lhs)), 1.0e-12)
end

"""Reference free body: `RigidBody3D` + `PoseIntegrator3D` (the J-MB8 floating base) at an initial
pose and momentum."""
function _msp_free_reference(; q = [0.9, 0.2, -0.3, 0.1], p = [0.1, -0.2, 0.3], P0, g0 = _MSP_G,
    m = 2.0, J = (0.3, 0.5, 0.7), t_end = 10.0, points = 1001)
    qn = q ./ norm(q)
    bs = Dict{String,Any}("inertia/P" => _msp_vec(P0))
    return bg_model("FreeReference", Any[
        bg_node("n1", "Body", bg_ref("stdlib:spatial/RigidBody3D");
            params = Dict{String,Any}("m" => string(m), "J" => _msp_vec(J), "g0" => string(g0)),
            starts = bs),
        _msp_vec6("n3", "Zero", (0, 0, 0, 0, 0, 0)),
        bg_node("n4", "NoWrench", bg_ref("stdlib:multibond/SeSpatial")),
        bg_node("n2", "Pose", bg_ref("stdlib:multibond/PoseIntegrator3D");
            starts = Dict{String,Any}("qw" => string(qn[1]), "qx" => string(qn[2]),
                "qy" => string(qn[3]), "qz" => string(qn[4]), "px" => string(p[1]),
                "py" => string(p[2]), "pz" => string(p[3]))),
    ], Any[
        bg_conn("c1", "signal", "n1", "V", "n2", "tw"),
        bg_conn("c2", "signal", "n2", "g", "n1", "g"),
        bg_conn("c3", "signal", "n3", "y", "n4", "u"),
        bg_conn("c4", "bond", "n4", "p", "n1", "p"),
    ]; t_end = t_end, points = points, reltol = 1.0e-9, abstol = 1.0e-11)
end

"""`Ground -> Free3D -> RigidBody3D`: the same floating body through the 6-DOF joint."""
function _msp_free_joint(; q = [0.9, 0.2, -0.3, 0.1], p = [0.1, -0.2, 0.3], P0, g0 = _MSP_G,
    m = 2.0, J = (0.3, 0.5, 0.7), t_end = 10.0, points = 1001)
    qn = q ./ norm(q)
    nodes = Any[
        bg_node("n0", "World", bg_ref("stdlib:multibond/GroundSpatial")),
        bg_node("n1", "Body", bg_ref("stdlib:spatial/RigidBody3D");
            params = Dict{String,Any}("m" => string(m), "J" => _msp_vec(J), "g0" => string(g0)),
            starts = Dict{String,Any}("inertia/P" => _msp_vec(P0))),
        bg_node("n2", "Joint", bg_ref("stdlib:spatial/Free3D");
            starts = Dict{String,Any}("qw" => string(qn[1]), "qx" => string(qn[2]),
                "qy" => string(qn[3]), "qz" => string(qn[4]), "px" => string(p[1]),
                "py" => string(p[2]), "pz" => string(p[3]))),
    ]
    conns = Any[
        bg_conn("c1", "bond", "n0", "p", "n2", "parent"),
        bg_conn("c2", "bond", "n2", "child", "n1", "p"),
        bg_conn("c3", "signal", "n2", "pose", "n1", "g"),
    ]
    _msp_drives!(nodes, conns, "n2", _MSP_PORTS["stdlib:spatial/Free3D"])
    return bg_model("FreeJoint", nodes, conns; t_end = t_end, points = points,
        reltol = 1.0e-9, abstol = 1.0e-11)
end

# ---------------------------------------------------------------------------------------
@testset "J-MB9 spatial body and joint composites" begin
    blocks = Dict(b.ref => b for b in Library.load_stdlib())

    # ---------------------------------------------------------------------------------
    # Catalog: clean, balanced, group, per-component Spatial units and the drive domains
    # ---------------------------------------------------------------------------------
    @testset "catalog: clean blocks, balanced, drive domain from the screw" begin
        @test all(ref -> haskey(blocks, ref), _MSP_REFS)
        # The generic 6x6-basis joint and its pose helper are dropped (J-MB9 correction).
        @test !haskey(blocks, "stdlib:spatial/JointBasis")
        @test !haskey(blocks, "stdlib:spatial/JointPose3D")
        @test sort([r for r in keys(blocks) if startswith(r, "stdlib:spatial/")]) == sort(_MSP_REFS)
        for ref in _MSP_REFS
            b = blocks[ref]
            @test b.group == "Spatial mechanics"
            @test isempty(check_block(b.ast))
            if ref != "stdlib:spatial/RigidBody3D"
                bal = BGSim.block_balance(b.ast)
                @test bal.unknowns == bal.equations
            end
            @test !isempty(b.description)
            @test !isempty(b.icon)
            for d in b.interface.parameters
                @test !isempty(d.description)
            end
            env = Units.unit_env(b.ast)
            for p in b.interface.ports
                p.domain == "Spatial" || continue
                @test p.size == [6]
                for k in 1:6
                    @test env.labels[Symbol(p.name, ".e[", string(k), "]")] == _MSP_E_UNITS[k]
                    @test env.labels[Symbol(p.name, ".f[", string(k), "]")] == _MSP_F_UNITS[k]
                end
            end
            @test isempty([d for d in check_block(b.ast) if d.code == "E006"])
        end

        # One scalar port per axis, the domain from the screw (D-MB8): a prismatic drive is
        # Translation (N, m/s), never Rotation; a helical coordinate is an angle (Rotation).
        rot = "Rotation"
        tra = "Translation"
        drives = Dict(
            "stdlib:spatial/Revolute3D" => [("drive", rot)],
            "stdlib:spatial/Revolute3DCompliant" => [("drive", rot)],
            "stdlib:spatial/Revolute3DFriction" => [("drive", rot)],
            "stdlib:spatial/Revolute3DLimit" => [("drive", rot)],
            "stdlib:spatial/Prismatic3D" => [("drive", tra)],
            "stdlib:spatial/Prismatic3DCompliant" => [("drive", tra)],
            "stdlib:spatial/Prismatic3DFriction" => [("drive", tra)],
            "stdlib:spatial/Prismatic3DLimit" => [("drive", tra)],
            "stdlib:spatial/Helical3D" => [("drive", rot)],
            "stdlib:spatial/Cylindrical3D" => [("drive1", rot), ("drive2", tra)],
            "stdlib:spatial/Universal3D" => [("drive1", rot), ("drive2", rot)],
            "stdlib:spatial/Spherical3D" => [("drive1", rot), ("drive2", rot), ("drive3", rot)],
            "stdlib:spatial/Planar3D" => [("drive1", rot), ("drive2", tra), ("drive3", tra)],
            "stdlib:spatial/Free3D" => [("drive1", rot), ("drive2", rot), ("drive3", rot),
                ("drive4", tra), ("drive5", tra), ("drive6", tra)],
        )
        @test sort(collect(keys(drives))) == sort(collect(keys(_MSP_PORTS)))
        for (ref, want) in drives
            ports = Dict(p.name => p.domain for p in blocks[ref].interface.ports)
            env = Units.unit_env(blocks[ref].ast)
            @test length(ports) == length(want) + 2        # parent, child and the drives
            for (name, domain) in want
                @test ports[name] == domain
                @test env.labels[Symbol(name, ".e")] == (domain == rot ? "N*m" : "N")
                @test env.labels[Symbol(name, ".f")] == (domain == rot ? "rad/s" : "m/s")
            end
        end
        @test [p.name for p in blocks["stdlib:spatial/RigidBody3D"].interface.ports] == ["p"]
        @test isempty(blocks["stdlib:spatial/LocalPose3D"].interface.ports)
    end

    # ---------------------------------------------------------------------------------
    # Typed joints under an imposed screw motion: pose = analytic FK, S columns, rates, power
    # ---------------------------------------------------------------------------------
    @testset "typed joints: forward kinematics, S columns and coordinate rates" begin
        T = 2.0
        pts = 21
        w, v, h = 1.3, 0.7, 0.02
        rowmax(c, names) = maximum(maximum(abs.(c[n])) for n in names)
        function run_kin(; kwargs...)
            doc = _msp_kin(; t_end = T, points = pts, kwargs...)
            checked = _msp_check(doc)
            @test isempty(_msp_errors(checked))
            @test _msp_w201(checked) == 0
            c, r, _ = bg_run(doc)
            @test r.status == "done"
            @test _msp_w201(r) == 0
            # a motion along S loads no deflection, so the joint takes exactly zero power
            P = c["Joint/parent.P"] .+ c["Joint/child.P"]
            for n in ("Joint/drive.P", "Joint/drive1.P", "Joint/drive2.P", "Joint/drive3.P",
                "Joint/drive4.P", "Joint/drive5.P", "Joint/drive6.P")
                haskey(c, n) && (P = P .+ c[n])
            end
            @test maximum(abs.(P)) <= 1.0e-9
            return c
        end
        function errs(c, ref)
            e = 0.0
            for i in 1:pts
                R, p = ref(c["time"][i])
                e = max(e, _msp_pose_err(c, "Joint/pose", i, R, p))
            end
            return e
        end
        worst = 0.0

        # Revolute (the variants share the kinematics): q = q0 + w t about the joint z.
        for ref in ("Revolute3D", "Revolute3DCompliant")
            c = run_kin(joint = "stdlib:spatial/$ref",
                params = Dict{String,Any}("q0" => "0.3"), child = (0, 0, w, 0, 0, 0))
            e = errs(c, t -> (_msp_Rz(0.3 + w * t), zeros(3)))
            @test e <= 1.0e-9
            @test maximum(abs.(c["Joint/qout"] .- (0.3 .+ w .* c["time"]))) <= 1.0e-9
            @test maximum(abs.(c["Joint/qdout"] .- w)) <= 1.0e-9
            @test rowmax(c, ["Joint/dang[1]", "Joint/dang[2]", "Joint/dlin[1]", "Joint/dlin[2]", "Joint/dlin[3]"]) <= 1.0e-12
            @test maximum(abs.(c["Joint/drive.f"] .- w)) <= 1.0e-9
            worst = max(worst, e)
        end
        # Prismatic: p = (0, 0, q0 + v t), rate v, units m/s.
        c = run_kin(joint = "stdlib:spatial/Prismatic3D", params = Dict{String,Any}("q0" => "0.2"),
            child = (0, 0, 0, 0, 0, v))
        e = errs(c, t -> (Matrix(1.0I, 3, 3), [0.0, 0.0, 0.2 + v * t]))
        @test e <= 1.0e-9
        @test maximum(abs.(c["Joint/qdout"] .- v)) <= 1.0e-9
        @test maximum(abs.(c["Joint/drive.f"] .- v)) <= 1.0e-9
        worst = max(worst, e)
        # Helical: the pitch is inside S; the twist (w e_z, h w e_z) loads no deflection.
        c = run_kin(joint = "stdlib:spatial/Helical3D",
            params = Dict{String,Any}("h" => string(h), "q0" => "0.4"), child = (0, 0, w, 0, 0, h * w))
        e = errs(c, t -> (_msp_Rz(0.4 + w * t), [0.0, 0.0, h * (0.4 + w * t)]))
        @test e <= 1.0e-9
        @test maximum(abs.(c["Joint/qdout"] .- w)) <= 1.0e-9
        @test rowmax(c, ["Joint/dlin[3]", "Joint/dang[1]"]) <= 1.0e-12
        worst = max(worst, e)
        # Cylindrical: rotation about and translation along z.
        c = run_kin(joint = "stdlib:spatial/Cylindrical3D",
            params = Dict{String,Any}("q10" => "0.1", "q20" => "0.3"), child = (0, 0, w, 0, 0, v))
        e = errs(c, t -> (_msp_Rz(0.1 + w * t), [0.0, 0.0, 0.3 + v * t]))
        @test e <= 1.0e-9
        @test maximum(abs.(c["Joint/qd1out"] .- w)) <= 1.0e-9
        @test maximum(abs.(c["Joint/qd2out"] .- v)) <= 1.0e-9
        worst = max(worst, e)
        # Universal: S1 = [0, sin q2, cos q2 | 0] depends on q2, S2 = [1, 0, 0 | 0]. (a) The child
        # twist wq S1(q20) rotates q1 only (q2 stays q20); (b) the twist (w1, 0, 0) rotates q2 only.
        wq, w1 = 1.4, 0.9
        c = run_kin(joint = "stdlib:spatial/Universal3D",
            params = Dict{String,Any}("q10" => "0.2", "q20" => "0.5"),
            child = (0, wq * sin(0.5), wq * cos(0.5), 0, 0, 0))
        e = errs(c, t -> (_msp_Rz(0.2 + wq * t) * _msp_Rx(0.5), zeros(3)))
        @test e <= 1.0e-9
        @test maximum(abs.(c["Joint/qd1out"] .- wq)) <= 1.0e-9
        @test maximum(abs.(c["Joint/qd2out"])) <= 1.0e-9
        @test maximum(abs.(c["Joint/ddef"])) <= 1.0e-12
        worst = max(worst, e)
        c = run_kin(joint = "stdlib:spatial/Universal3D",
            params = Dict{String,Any}("q10" => "0.2", "q20" => "0.5"), child = (w1, 0, 0, 0, 0, 0))
        e = errs(c, t -> (_msp_Rz(0.2) * _msp_Rx(0.5 + w1 * t), zeros(3)))
        @test e <= 1.0e-9
        @test maximum(abs.(c["Joint/qd2out"] .- w1)) <= 1.0e-9
        @test maximum(abs.(c["Joint/qd1out"])) <= 1.0e-9
        # the order of the two rotations matters (the second axis follows the first): Rz Rx != Rx Rz
        @test maximum(abs.(_msp_Rz(0.2) * _msp_Rx(0.5 + w1 * T) .- _msp_Rx(0.5 + w1 * T) * _msp_Rz(0.2))) > 0.1
        worst = max(worst, e)
        # Spherical: the body-frame rate integrates to exp([w] t) in the stored quaternion.
        om = [0.5, -0.8, 0.6]
        c = run_kin(joint = "stdlib:spatial/Spherical3D", child = (om[1], om[2], om[3], 0, 0, 0))
        e = errs(c, t -> (_msp_expR(om .* t), zeros(3)))
        @test e <= 1.0e-8
        nrm = sqrt.(c["Joint/qrel[1]"] .^ 2 .+ c["Joint/qrel[2]"] .^ 2 .+ c["Joint/qrel[3]"] .^ 2 .+ c["Joint/qrel[4]"] .^ 2)
        @test maximum(abs.(nrm .- 1)) <= 1.0e-9
        for k in 1:3
            @test maximum(abs.(c["Joint/drive$k.f"] .- om[k])) <= 1.0e-9
        end
        worst = max(worst, e)
        # Planar3D: rotation about z, translations along the parent x/y (S2, S3 rotate with q1).
        vx, vy = 0.6, -0.4
        c = run_kin(joint = "stdlib:spatial/Planar3D",
            params = Dict{String,Any}("q10" => "0.2", "q20" => "0.1", "q30" => "-0.2"),
            child = (0, 0, w, vx, vy, 0))
        q1f2(t) = 0.2 + w * t
        xf(t) = 0.1 + (vx * (sin(q1f2(t)) - sin(0.2)) + vy * (cos(q1f2(t)) - cos(0.2))) / w
        yf(t) = -0.2 + (-vx * (cos(q1f2(t)) - cos(0.2)) + vy * (sin(q1f2(t)) - sin(0.2))) / w
        e = errs(c, t -> (_msp_Rz(q1f2(t)), [xf(t), yf(t), 0.0]))
        @test e <= 1.0e-8
        tt = c["time"]
        @test maximum(abs.(c["Joint/qd2out"] .- (cos.(q1f2.(tt)) .* vx .- sin.(q1f2.(tt)) .* vy))) <= 1.0e-9
        @test maximum(abs.(c["Joint/qd3out"] .- (sin.(q1f2.(tt)) .* vx .+ cos.(q1f2.(tt)) .* vy))) <= 1.0e-9
        @test maximum(abs.(c["Joint/dzout"])) <= 1.0e-12
        worst = max(worst, e)
        # Free3D: the constant body twist is the exact SE(3) screw exp(V t).
        Vt = [0.4, -0.3, 0.5, 0.2, 0.1, -0.35]
        c = run_kin(joint = "stdlib:spatial/Free3D", child = Tuple(Vt))
        function screw(t)
            wv, vv = Vt[1:3], Vt[4:6]
            th = norm(wv)
            K = _msp_hat(wv ./ th)
            phi = th * t
            pp = (Matrix(1.0I, 3, 3) * phi + (1 - cos(phi)) * K + (phi - sin(phi)) * K * K) * (vv ./ th)
            return _msp_expR(wv .* t), pp
        end
        e = errs(c, screw)
        @test e <= 1.0e-8
        nrm = sqrt.(c["Joint/qrel[1]"] .^ 2 .+ c["Joint/qrel[2]"] .^ 2 .+ c["Joint/qrel[3]"] .^ 2 .+ c["Joint/qrel[4]"] .^ 2)
        @test maximum(abs.(nrm .- 1)) <= 1.0e-9
        for k in 1:6
            @test maximum(abs.(c["Joint/drive$k.f"] .- Vt[k])) <= 1.0e-9
        end
        worst = max(worst, e)
        println("J-MB9 kinematics: worst pose error over the 8 joint types = ", worst)
    end

    # ---------------------------------------------------------------------------------
    # The spatial pendulum: period, energy, composed pose, gravity, fixed-base truth
    # ---------------------------------------------------------------------------------
    @testset "spatial pendulum: period, energy, composed pose, W201" begin
        m, L, Jz = _MSP_PM, _MSP_L, _MSP_PJ[3]
        q0 = 0.01
        doc = _msp_pendulum(q0 = q0, t_end = 10.0, points = 2001)
        checked = _msp_check(doc)
        @test isempty(_msp_errors(checked))
        @test _msp_w201(checked) == 0
        c, r, _ = bg_run(doc)
        @test r.status == "done"
        @test _msp_w201(r) == 0
        t, q = c["time"], c["Joint/qout"]
        Tmeas = _msp_period(t, q)
        Tan = 2 * pi * sqrt((Jz + m * L^2) / (m * _MSP_G * L)) * (1 + q0^2 / 16)
        @test isapprox(Tmeas, Tan; rtol = 1.0e-6)
        # energy over 10 s (KE + potential of the actual origin + strain)
        E = _msp_ke(c, "Body", _MSP_PJ, m) .+ m * _MSP_G .* c["C2/g[7]"] .+
            _msp_strain(c, "Joint", 1.0e8, 1.0e8)
        swing = m * _MSP_G * L * (1 - cos(q0))
        drift = maximum(abs.(E .- E[1])) / swing
        @test drift <= 1.0e-6
        # the composed pose is the forward kinematics: origin (0, L sin q, -L cos q)
        @test maximum(abs.(c["C2/g[7]"] .+ L .* cos.(q))) <= 1.0e-6
        @test maximum(abs.(c["C2/g[6]"] .- L .* sin.(q))) <= 1.0e-6
        @test maximum(abs.(c["C2/g[5]"])) <= 1.0e-6
        # gravity reads the composed pose (it is the same signal, exactly)
        for k in 1:7
            @test maximum(abs.(c["Body/gravity/g[$k]"] .- c["C2/g[$k]"])) <= 1.0e-12
        end
        @test maximum(abs.(c["Joint/qdout"])) > 0.04      # it really swings
        println("J-MB9 pendulum: period ", Tmeas, " vs ", Tan, " (rel ", abs(Tmeas - Tan) / Tan,
            "), energy drift ", drift, " of the swing")
    end

    @testset "fixed-base composed pose vs the integrated truth over 10 s" begin
        # A large swing (0.6 rad): the pose composed from the joint chart (no pose state) must
        # agree with the pose integrated from the body twist by PoseIntegrator3D.
        doc = _msp_pendulum(q0 = 0.6, t_end = 10.0, points = 2001, truth = true)
        c, r, flat = bg_run(doc)
        @test r.status == "done"
        @test _msp_w201(r) == 0
        e = 0.0
        for i in eachindex(c["time"])
            Rc, pc = _msp_pose(c, "C2/g", i)
            Rt, pt = _msp_pose(c, "Truth/g", i)
            e = max(e, maximum(abs.(Rc .- Rt)), maximum(abs.(pc .- pt)))
        end
        @test e <= 1.0e-6
        q = c["Joint/qout"]
        @test maximum(abs.(q)) > 0.55                     # a real large-amplitude swing
        # a fixed-base chain holds one coordinate state (+ deflections), the pose is algebraic
        println("J-MB9 fixed-base pose vs integrated truth over 10 s: ", e)
    end

    # ---------------------------------------------------------------------------------
    # The non-planar two-link chain: independent RNE/RK4 reference, stiffness sweep, energy
    # ---------------------------------------------------------------------------------
    @testset "two-link spatial chain: rotating parent, stiffness sweep, energy and convergence" begin
        p = _MSP_DP
        chain = _msp_dp_chain()
        q1, q2 = 0.4, 0.6
        t_end, pts = 1.5, 301
        dt_out = t_end / (pts - 1)
        dt = 2.0e-4
        stride = round(Int, dt_out / dt)
        ref = _msp_rk4(chain, [q1, q2], zeros(2), dt, stride, t_end)
        fine = _msp_rk4(chain, [q1, q2], zeros(2), dt / 2, 2 * stride, t_end)
        @test length(ref) == pts
        conv = maximum(maximum(abs.(ref[k] .- fine[k])) for k in eachindex(ref))
        @test conv <= 1.0e-8                              # the reference itself is converged
        pes = [_msp_chain_energy(chain, y[1:2], y[3:4])[2] for y in ref]
        kes = [_msp_chain_energy(chain, y[1:2], y[3:4])[1] for y in ref]
        swing = maximum(pes) - minimum(pes)
        @test swing > 1.0                                 # a real swing
        # the rigid reference conserves its own energy (it validates the RNE/RK4 pair)
        Er = kes .+ pes
        @test maximum(abs.(Er .- Er[1])) / swing <= 1.0e-8
        @test maximum(abs.(getindex.(ref, 4))) > 0.5      # joint 2 moves: a rotating parent
        errs = Float64[]
        drifts = Float64[]
        ks = (1.0e5, 1.0e6, 1.0e7, 1.0e8, 1.0e9)
        for kk in ks
            doc = _msp_double(kk; q1 = q1, q2 = q2, t_end = t_end, points = pts)
            checked = _msp_check(doc)
            @test isempty(_msp_errors(checked))
            @test _msp_w201(checked) == 0
            c, r, _ = bg_run(doc)
            @test r.status == "done"
            @test _msp_w201(r) == 0
            e1 = maximum(abs.(c["J1/qout"] .- getindex.(ref, 1)))
            e2 = maximum(abs.(c["J2/qout"] .- getindex.(ref, 2)))
            E = _msp_dp_energy(c, kk)
            drift = maximum(abs.(E .- E[1])) / swing
            push!(errs, max(e1, e2))
            push!(drifts, drift)
            # the out-of-plane deflection of joint 2 really is excited (the transport is exercised)
            @test maximum(abs.(c["J2/dang[1]"])) > 0 || maximum(abs.(c["J2/dang[2]"])) > 0
            println("J-MB9 two-link chain kt=kr=", kk, ": coordinate error ", max(e1, e2),
                ", energy drift ", drift, " of the swing")
        end
        # Energy: the joint's port power is exact AND its pose is exactly the integral of the
        # twists it produces (the exact Gibbs chart in both adjoints), so gravity reading the
        # composed pose closes the budget to the solver floor at every stiffness, including the
        # softest. The first-order chart (nominal adjoint, small-angle deflection) leaked
        # O(1/k): 2.6e-6, 2.6e-7, 2.6e-8, 2.6e-9 of the swing at 1e5..1e8, all from the
        # gravity-vs-pose mismatch while the joint identity closed to 1e-10.
        @test all(drifts .<= 1.0e-8)
        # the error against the rigid reference falls with the stiffness, one decade per decade
        ratios = errs[2:(end - 1)] ./ errs[3:end]
        @test all(r -> 8.0 <= r <= 12.5, ratios)
        println("J-MB9 two-link chain error ratios per decade: ", ratios)
    end

    # ---------------------------------------------------------------------------------
    # Prismatic: Translation drive, spring-mass period, loaded equilibrium
    # ---------------------------------------------------------------------------------
    @testset "prismatic: Translation drive (N, m/s), spring-mass period, loaded equilibrium" begin
        m, k = 2.0, 200.0
        doc = _msp_prismatic(m = m, k = k, q0 = 0.1)
        checked = _msp_check(doc)
        @test isempty(_msp_errors(checked))
        @test !_msp_has(checked, "E006")                 # no unit mismatch on a Translation drive
        @test _msp_w201(checked) == 0
        c, r, _ = bg_run(doc)
        @test r.status == "done"
        @test _msp_w201(r) == 0
        t, q = c["time"], c["Joint/qout"]
        T = _msp_period(t, q)
        @test isapprox(T, 2 * pi * sqrt(m / k); rtol = 1.0e-6)
        @test isapprox(maximum(q), 0.1; rtol = 1.0e-6)
        # the drive port carries a force (N) and a velocity (m/s): at release the spring pulls with k q0
        @test isapprox(abs(c["Joint/drive.e"][1]), k * 0.1; rtol = 1.0e-6)
        @test maximum(abs.(c["Joint/drive.f"] .- c["Joint/qdout"])) <= 1.0e-12
        # a constant force on the damped drive: the equilibrium displacement is -F/k
        F = 20.0
        doc = _msp_prismatic(m = m, k = k, dmp = 40.0, force = F, q0 = 0.1, t_end = 8.0, points = 801)
        c, r, _ = bg_run(doc)
        @test r.status == "done"
        @test isapprox(c["Joint/qout"][end], -F / k; rtol = 1.0e-5)
        # at equilibrium the spring balances the force, so the joint carries no axial load
        @test abs(c["Joint/drive.e"][end]) <= 1.0e-8
        println("J-MB9 prismatic: period ", T, " vs ", 2 * pi * sqrt(m / k), ", q_ss ",
            c["Joint/qout"][end], " vs ", -F / k)
    end

    # ---------------------------------------------------------------------------------
    # Rotating-parent regressions: the 3-D deflection transport and the prismatic lever
    # ---------------------------------------------------------------------------------
    @testset "rotating parent: prismatic axial rate lever and the deflection transport" begin
        om = [0.8, -0.6, 1.1]
        # Prismatic: q0 = 0.3, perpendicular deflection (d1, d2). The child co-rotates with the parent
        # at the deflected origin (q ez + dl): its twist is (om, om x (d1, d2, q)). No axial force acts
        # and kt = 0, so qdot must be exactly 0 (the lever term cancels the lever velocity
        # ez.(om x dl) in V_rel[6]) and dl must stay constant (the transport cancels om_z x dl).
        d1, d2, q0 = 1.0e-3, 2.0e-3, 0.3
        lin = [om[2] * q0 - om[3] * d2, om[3] * d1 - om[1] * q0, om[1] * d2 - om[2] * d1]
        doc = _msp_kin(joint = "stdlib:spatial/Prismatic3D",
            params = Dict{String,Any}("kr" => "1.0e6", "kt" => "0.0", "q0" => string(q0)),
            starts = Dict{String,Any}("dl" => _msp_vec([d1, d2])),
            parent = (om[1], om[2], om[3], 0, 0, 0), child = (om[1], om[2], om[3], lin[1], lin[2], lin[3]),
            t_end = 1.0, points = 11)
        c, r, _ = bg_run(doc)
        @test r.status == "done"
        @test maximum(abs.(c["Joint/qdout"])) <= 1.0e-12
        @test maximum(abs.(c["Joint/qout"] .- q0)) <= 1.0e-12
        @test maximum(abs.(c["Joint/dlin[1]"] .- d1)) <= 1.0e-12
        @test maximum(abs.(c["Joint/dlin[2]"] .- d2)) <= 1.0e-12
        # the lever velocity the lever term must cancel is O(om d): without it qdot ~ 2e-3 m/s
        @test abs(om[1] * d2 - om[2] * d1) > 1.0e-3
        # Revolute: the joint rotates at q0 about its z; the child co-rotates with the parent (so
        # qdot = 0) and sits at the translational offset dl in the child frame. Its linear twist is
        # w_c x dl with w_c = Rz^T om. The deflection must stay constant: ddt(dl) = V_rel - w_c x dl.
        qj = 0.4
        wc = _msp_Rz(qj)' * om
        dl = [2.0e-3, -1.0e-3, 3.0e-3]
        lin = cross(wc, dl)
        doc = _msp_kin(joint = "stdlib:spatial/Revolute3D",
            params = Dict{String,Any}("kr" => "1.0e6", "kt" => "0.0", "q0" => string(qj)),
            starts = Dict{String,Any}("dl" => _msp_vec(dl)),
            parent = (om[1], om[2], om[3], 0, 0, 0), child = (wc[1], wc[2], wc[3], lin[1], lin[2], lin[3]),
            t_end = 1.0, points = 11)
        c, r, _ = bg_run(doc)
        @test r.status == "done"
        @test maximum(abs.(c["Joint/qdout"])) <= 1.0e-12
        for k in 1:3
            @test maximum(abs.(c["Joint/dlin[$k]"] .- dl[k])) <= 1.0e-12
        end
        # a relative-rate transport (qdot instead of the absolute child rate) would drift at om x dl
        @test norm(cross(om, dl)) > 5.0e-4
    end

    # ---------------------------------------------------------------------------------
    # Exact chart: the pose output is the integral of the relative twist, with large
    # deflections and a rotating parent (the first-order chart misses O(dth x w_p) here)
    # ---------------------------------------------------------------------------------
    @testset "exact chart: pose = integral of the relative twist with deflections" begin
        Vp = [0.8, -0.6, 1.1, 0.3, -0.2, 0.4]
        Vc = [0.5, 0.9, -0.7, -0.4, 0.6, 0.2]
        t_end, pts = 0.5, 2001
        dt = t_end / (pts - 1)                        # central differences: O(dt^2 |V|^3) ~ 2e-7
        cases = [
            ("Revolute3D", Dict{String,Any}("dth" => _msp_vec([0.04, -0.03]), "dl" => _msp_vec([0.01, 0.02, -0.01]))),
            ("Prismatic3D", Dict{String,Any}("dth" => _msp_vec([0.03, -0.02, 0.04]), "dl" => _msp_vec([0.01, -0.02]))),
            ("Helical3D", Dict{String,Any}("dth" => _msp_vec([-0.03, 0.02]), "dl" => _msp_vec([0.02, 0.01, 0.015]))),
            ("Cylindrical3D", Dict{String,Any}("dth" => _msp_vec([0.02, 0.03]), "dl" => _msp_vec([-0.01, 0.02]))),
            ("Universal3D", Dict{String,Any}("dt" => "0.03", "dl" => _msp_vec([0.01, -0.02, 0.02]))),
            ("Planar3D", Dict{String,Any}("dth" => _msp_vec([-0.02, 0.04]), "dz" => "0.015")),
            ("Spherical3D", Dict{String,Any}("dl" => _msp_vec([0.02, -0.01, 0.01]))),
            ("Free3D", Dict{String,Any}()),
        ]
        worst = 0.0
        for (name, starts) in cases
            params = name == "Helical3D" ? Dict{String,Any}("h" => "0.05") : Dict{String,Any}()
            doc = _msp_kin(joint = "stdlib:spatial/$name", params = params, starts = starts,
                parent = Tuple(Vp), child = Tuple(Vc), t_end = t_end, points = pts)
            c, r, _ = bg_run(doc)
            @test r.status == "done"
            e = 0.0
            for i in 2:(pts - 1)
                R, p = _msp_pose(c, "Joint/pose", i)
                Rm, pm = _msp_pose(c, "Joint/pose", i - 1)
                Rp, pp = _msp_pose(c, "Joint/pose", i + 1)
                Om = R' * ((Rp .- Rm) ./ (2dt))           # R^T Rdot: the body angular velocity, skew
                vb = R' * ((pp .- pm) ./ (2dt))           # R^T pdot: the body linear velocity
                w_pred = Vc[1:3] .- R' * Vp[1:3]
                v_pred = Vc[4:6] .- R' * (Vp[4:6] .+ cross(Vp[1:3], p))
                e = max(e, maximum(abs.(Om .+ Om')),
                    maximum(abs.([Om[3, 2], Om[1, 3], Om[2, 1]] .- w_pred)), maximum(abs.(vb .- v_pred)))
            end
            @test e <= 1.0e-6
            worst = max(worst, e)
            # the deflections really are large and really change (not a small-angle regime)
            defl = [k for k in keys(c) if startswith(k, "Joint/dang") || startswith(k, "Joint/dlin") ||
                    k == "Joint/ddef" || k == "Joint/dzout"]
            if !isempty(defl)
                @test maximum(maximum(abs.(c[k])) for k in defl) > 0.1
            end
        end
        println("J-MB9 exact chart: worst twist-integral error over the 8 joint types = ", worst)
    end

    # ---------------------------------------------------------------------------------
    # Port-power identity of every 1-axis variant, on a joint whose parent is driven
    # ---------------------------------------------------------------------------------
    @testset "joint power identity: parent.P + child.P + drive.P = strain rate + dissipation" begin
        par = (1.5, -0.7, 0.9, 0, 0, 0)
        rev = [
            ("Revolute3D", Dict{String,Any}()),
            ("Revolute3DCompliant", Dict{String,Any}("k" => "5.0", "b" => "0.3", "qrest" => "0.1")),
            ("Revolute3DFriction", Dict{String,Any}("Fc" => "0.3", "Fv" => "0.2", "v_eps" => "0.01")),
            ("Revolute3DLimit", Dict{String,Any}("lower" => "-0.2", "upper" => "0.5", "kL" => "200.0",
                "bL" => "0.5", "delta" => "0.01")),
        ]
        res = Float64[]
        for (name, extra) in rev
            params = merge(Dict{String,Any}("kr" => "1.0e4", "kt" => "1.0e4", "br" => "2.0",
                "bt" => "5.0", "q0" => "0.2"), extra)
            doc = _msp_driven_parent(joint = "stdlib:spatial/$name", params = params, parent = par,
                offset = (0.3, -0.2, 0.15), t_end = 1.0, points = 401,
                P0 = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0))
            checked = _msp_check(doc)
            @test _msp_w201(checked) == 0
            c, r, _ = bg_run(doc)
            @test r.status == "done"
            @test _msp_w201(r) == 0
            e = _msp_power_residual(c; kind = :revolute, kr = 1.0e4, kt = 1.0e4, br = 2.0, bt = 5.0)
            @test e <= 1.0e-9
            @test maximum(abs.(c["Joint/parent.P"])) > 1.0e-3     # the parent source really works
            push!(res, e)
        end
        pri = [
            ("Prismatic3D", Dict{String,Any}()),
            ("Prismatic3DCompliant", Dict{String,Any}("k" => "20.0", "b" => "0.5", "qrest" => "0.05")),
            ("Prismatic3DFriction", Dict{String,Any}("Fc" => "0.5", "Fv" => "0.4", "v_eps" => "0.01")),
            ("Prismatic3DLimit", Dict{String,Any}("lower" => "-0.2", "upper" => "0.4", "kL" => "500.0",
                "bL" => "1.0", "delta" => "0.01")),
        ]
        for (name, extra) in pri
            params = merge(Dict{String,Any}("kr" => "1.0e4", "kt" => "1.0e4", "br" => "2.0",
                "bt" => "5.0", "q0" => "0.1"), extra)
            doc = _msp_driven_parent(joint = "stdlib:spatial/$name", params = params, parent = par,
                offset = (0.1, 0.05, 0.0), t_end = 1.0, points = 401)
            checked = _msp_check(doc)
            @test _msp_w201(checked) == 0
            c, r, _ = bg_run(doc)
            @test r.status == "done"
            @test _msp_w201(r) == 0
            e = _msp_power_residual(c; kind = :prismatic, kr = 1.0e4, kt = 1.0e4, br = 2.0, bt = 5.0)
            @test e <= 1.0e-9
            @test maximum(abs.(c["Joint/parent.P"])) > 1.0e-3
            push!(res, e)
        end
        println("J-MB9 joint power identity residuals (8 variants, rotating parent): ", res)
    end

    # ---------------------------------------------------------------------------------
    # Variants: compliance, friction, limits
    # ---------------------------------------------------------------------------------
    @testset "variants: torsion spring, friction dissipates, one-sided limits" begin
        # Revolute3DCompliant: a torsion oscillator about qrest (CoM on the axis, no gravity).
        Jz, k = 0.5, 50.0
        doc = _msp_rig(joint = "stdlib:spatial/Revolute3DCompliant",
            params = Dict{String,Any}("kr" => "1.0e6", "kt" => "1.0e6", "k" => string(k), "b" => "0.0",
                "qrest" => "0.1", "q0" => "0.3"),
            mount = (_MSP_QI, zeros(3)), body_pose = (_MSP_QI, zeros(3)), J = (0.1, 0.1, Jz),
            g0 = 0.0, t_end = 4.0, points = 4001)
        c, r, _ = bg_run(doc)
        @test r.status == "done"
        @test _msp_w201(r) == 0
        @test isapprox(_msp_period(c["time"], c["Joint/qout"] .- 0.1), 2 * pi * sqrt(Jz / k); rtol = 1.0e-6)
        E = _msp_ke(c, "Body", (0.1, 0.1, Jz), 1.0) .+ 0.5 * k .* (c["Joint/qout"] .- 0.1) .^ 2
        @test maximum(abs.(E .- E[1])) / E[1] <= 1.0e-8

        # Prismatic3DCompliant: a spring-mass on the joint coordinate.
        m, kp = 2.0, 200.0
        doc = _msp_prismatic(m = m, joint = "stdlib:spatial/Prismatic3DCompliant", with_spring = false,
            extra = Dict{String,Any}("k" => string(kp), "b" => "0.0", "qrest" => "0.05"), q0 = 0.15,
            t_end = 3.0, points = 3001)
        c, r, _ = bg_run(doc)
        @test r.status == "done"
        @test isapprox(_msp_period(c["time"], c["Joint/qout"] .- 0.05), 2 * pi * sqrt(m / kp); rtol = 1.0e-6)

        # Revolute3DFriction: a spinning body decays monotonically, friction only dissipates.
        w0, fv = 5.0, 0.1
        doc = _msp_rig(joint = "stdlib:spatial/Revolute3DFriction",
            params = Dict{String,Any}("kr" => "1.0e6", "kt" => "1.0e6", "Fc" => "0.0", "Fv" => string(fv),
                "v_eps" => "1.0e-3", "q0" => "0.0"),
            mount = (_MSP_QI, zeros(3)), body_pose = (_MSP_QI, zeros(3)), J = (0.1, 0.1, Jz),
            g0 = 0.0, P0 = (0.0, 0.0, Jz * w0, 0.0, 0.0, 0.0), t_end = 10.0, points = 1001)
        c, r, _ = bg_run(doc)
        @test r.status == "done"
        @test _msp_w201(r) == 0
        w = c["Joint/qdout"]
        @test isapprox(w[1], w0; atol = 1.0e-9)
        @test all(diff(w) .<= 0.0)
        @test isapprox(w[end], w0 * exp(-fv * 10.0 / Jz); rtol = 1.0e-4)
        tf = c["Joint/tauout"]
        @test all(tf .>= -1.0e-12)
        @test all(-tf .* w .<= 1.0e-12)                       # the dissipated power is never negative
        Ef = _msp_ke(c, "Body", (0.1, 0.1, Jz), 1.0) .+ _msp_strain(c, "Joint", 1.0e6, 1.0e6)
        @test maximum(diff(Ef)) <= 1.0e-9 * Ef[1]
        @test Ef[end] < Ef[1]
        println("J-MB9 friction (viscous): omega(10 s) = ", w[end], " vs ", w0 * exp(-fv * 10.0 / Jz))
        doc = _msp_rig(joint = "stdlib:spatial/Revolute3DFriction",
            params = Dict{String,Any}("kr" => "1.0e6", "kt" => "1.0e6", "Fc" => "0.5", "Fv" => string(fv),
                "v_eps" => "1.0e-3", "q0" => "0.0"),
            mount = (_MSP_QI, zeros(3)), body_pose = (_MSP_QI, zeros(3)), J = (0.1, 0.1, Jz),
            g0 = 0.0, P0 = (0.0, 0.0, Jz * w0, 0.0, 0.0, 0.0), t_end = 10.0, points = 1001)
        c, r, _ = bg_run(doc)
        wc = c["Joint/qdout"]
        @test r.status == "done"
        @test all(diff(wc) .<= 1.0e-9)
        @test wc[end] < w[end]
        @test all(-c["Joint/tauout"] .* wc .<= 1.0e-9)
        # stick: a drive torque below Fc holds the joint (creep v_eps atanh(tau/Fc)), above it slips
        doc = _msp_rig(joint = "stdlib:spatial/Revolute3DFriction",
            params = Dict{String,Any}("kr" => "1.0e6", "kt" => "1.0e6", "Fc" => "0.5", "Fv" => "0.0",
                "v_eps" => "1.0e-3", "q0" => "0.0"),
            mount = (_MSP_QI, zeros(3)), body_pose = (_MSP_QI, zeros(3)), J = (0.1, 0.1, Jz),
            g0 = 0.0, efforts = Dict("drive" => 0.4), t_end = 2.0, points = 2001)
        c, r, _ = bg_run(doc)
        @test r.status == "done"
        @test maximum(abs.(c["Joint/qdout"])) <= 5.0e-3
        @test isapprox(c["Joint/qdout"][end], 1.0e-3 * atanh(0.4 / 0.5); rtol = 0.05)
        doc = _msp_rig(joint = "stdlib:spatial/Revolute3DFriction",
            params = Dict{String,Any}("kr" => "1.0e6", "kt" => "1.0e6", "Fc" => "0.5", "Fv" => "0.0",
                "v_eps" => "1.0e-3", "q0" => "0.0"),
            mount = (_MSP_QI, zeros(3)), body_pose = (_MSP_QI, zeros(3)), J = (0.1, 0.1, Jz),
            g0 = 0.0, efforts = Dict("drive" => 0.6), t_end = 2.0, points = 2001)
        c, r, _ = bg_run(doc)
        # above Fc it slips: (0.6 - 0.5) / Jz * 2 s
        @test isapprox(c["Joint/qdout"][end], 0.4; rtol = 0.02)

        # Prismatic3DFriction: a sliding mass decays as exp(-Fv t / m).
        m, fvp, v0 = 2.0, 1.0, 3.0
        doc = _msp_prismatic(m = m, joint = "stdlib:spatial/Prismatic3DFriction", with_spring = false,
            extra = Dict{String,Any}("Fc" => "0.0", "Fv" => string(fvp), "v_eps" => "1.0e-3"),
            q0 = 0.0, P0 = (0.0, 0.0, 0.0, 0.0, 0.0, m * v0), t_end = 3.0, points = 601)
        c, r, _ = bg_run(doc)
        @test r.status == "done"
        vs = c["Joint/qdout"]
        @test all(diff(vs) .<= 0.0)
        @test isapprox(vs[end], v0 * exp(-fvp * 3.0 / m); rtol = 1.0e-4)
        @test all(-c["Joint/tauout"] .* vs .<= 1.0e-12)

        # Revolute3DLimit: zero effort inside, a one-sided stop outside, an elastic rebound.
        lower, upper, kl = -0.3, 0.7, 100.0
        doc = _msp_pendulum(joint = "stdlib:spatial/Revolute3DLimit", q0 = 0.6,
            extra = Dict{String,Any}("lower" => string(lower), "upper" => string(upper),
                "kL" => string(kl), "bL" => "0.0", "delta" => "1.0e-3"), t_end = 3.0, points = 3001)
        checked = _msp_check(doc)
        @test isempty(_msp_errors(checked))
        @test _msp_w201(checked) == 0
        c, r, _ = bg_run(doc)
        @test r.status == "done"
        @test _msp_w201(r) == 0
        @test !_msp_has(r, "W206")
        q, tau = c["Joint/qout"], c["Joint/tauout"]
        inside = (q .> lower + 0.03) .& (q .< upper - 0.03)
        @test any(inside) && all(tau[inside] .== 0.0)
        below = q .< lower - 0.03
        @test any(below)
        @test maximum(abs.(tau[below] .- kl .* (q[below] .- lower))) <= 1.0e-9
        @test all(tau[below] .< 0)                              # a lower stop pushes the angle up
        imin = argmin(q)
        @test -0.5 < q[imin] < lower - 0.02
        @test maximum(q[imin:end]) > 0.59                       # elastic rebound to ~ the release angle
        println("J-MB9 revolute limit: q_min ", q[imin], ", rebound max ", maximum(q[imin:end]))

        # Prismatic3DLimit: a mass at v0 hits the upper stop: penetration ~ v0 sqrt(m/kL), then rebounds.
        m, v0, kL = 2.0, 1.0, 1.0e4
        doc = _msp_prismatic(m = m, joint = "stdlib:spatial/Prismatic3DLimit", with_spring = false,
            extra = Dict{String,Any}("lower" => "-1.0", "upper" => "0.2", "kL" => string(kL),
                "bL" => "0.0", "delta" => "1.0e-3"),
            q0 = 0.0, P0 = (0.0, 0.0, 0.0, 0.0, 0.0, m * v0), t_end = 1.0, points = 2001)
        c, r, _ = bg_run(doc)
        @test r.status == "done"
        @test !_msp_has(r, "W206")
        q, tau = c["Joint/qout"], c["Joint/tauout"]
        @test isapprox(maximum(q), 0.2 + v0 * sqrt(m / kL); atol = 1.0e-3)
        # exactly zero well inside; the smooth ramp dips by at most ~0.15 kL delta just inside the stop
        @test all(tau[q .< 0.17] .== 0.0)
        @test minimum(tau) >= -0.2 * kL * 1.0e-3
        @test maximum(tau) > 100.0                            # the upper stop effort is positive (it opposes q)
        @test isapprox(c["Joint/qdout"][end], -v0; rtol = 1.0e-3)
        println("J-MB9 prismatic limit: q_max ", maximum(q), " vs ", 0.2 + v0 * sqrt(m / kL))
    end

    # ---------------------------------------------------------------------------------
    # Every joint type under gravity at a tilted mount: energy with the strain
    # ---------------------------------------------------------------------------------
    @testset "every typed joint: gravity at a tilted mount conserves KE + PE + strain" begin
        qm = [0.8, 0.3, -0.4, 0.33]
        qm = qm ./ norm(qm)
        pm = [0.1, 0.2, 0.3]
        kk = Dict{String,Any}("kt" => "1.0e7", "kr" => "1.0e7")
        cases = [
            ("Revolute3D", kk),
            ("Prismatic3D", kk),
            ("Helical3D", merge(kk, Dict{String,Any}("h" => "0.05"))),
            ("Cylindrical3D", kk),
            ("Universal3D", kk),
            ("Spherical3D", Dict{String,Any}("kt" => "1.0e7")),
            ("Planar3D", kk),
            ("Free3D", Dict{String,Any}()),
        ]
        P0 = (0.05, -0.04, 0.06, 0.1, -0.08, 0.07)
        out = String[]
        for (name, params) in cases
            doc = _msp_rig(joint = "stdlib:spatial/$name", params = params,
                mount = (qm, pm), body_pose = (_MSP_QI, [0.3, -0.2, 0.1]), P0 = P0,
                m = 1.0, J = _MSP_PJ, g0 = _MSP_G, t_end = 0.5, points = 201)
            checked = _msp_check(doc)
            @test isempty(_msp_errors(checked))
            @test _msp_w201(checked) == 0
            c, r, _ = bg_run(doc)
            @test r.status == "done"
            @test _msp_w201(r) == 0
            ke = _msp_ke(c, "Body", _MSP_PJ, 1.0)
            pe = _MSP_G .* c["C2/g[7]"]
            E = ke .+ pe .+ _msp_strain(c, "Joint", 1.0e7, 1.0e7)
            scale = maximum(ke) + (maximum(pe) - minimum(pe))
            drift = maximum(abs.(E .- E[1])) / scale
            # The rig starts with momentum and zero deflection, so the stiff modes are excited;
            # the residual is the solver's error on them and GROWS with k (Revolute3D: 8.7e-10,
            # 4.1e-9, 1.7e-8 at k = 1e5, 1e6, 1e7), the opposite of a kinematic O(1/k) leak.
            @test drift <= 1.0e-7
            @test scale > 0.05                                  # it really moves
            push!(out, "$name $(round(drift, sigdigits = 3))")
        end
        println("J-MB9 energy drift / scale, gravity at a tilted mount: ", join(out, ", "))
    end

    @testset "spherical pendulum: quaternion pose storage, norm and world angular momentum" begin
        m, L = _MSP_PM, 0.4
        w0 = 2.0
        # a conical swing: the body offset (L, 0, 0) from the ball joint at the origin, spun about the
        # vertical so the CoM velocity w x r is consistent (no impulsive start).
        P0 = (0.0, 0.0, _MSP_PJ[3] * w0, 0.0, m * w0 * L, 0.0)
        doc = _msp_rig(joint = "stdlib:spatial/Spherical3D",
            params = Dict{String,Any}("kt" => "1.0e9"), mount = (_MSP_QI, zeros(3)),
            body_pose = (_MSP_QI, [L, 0.0, 0.0]), P0 = P0, m = m, J = _MSP_PJ, g0 = _MSP_G,
            t_end = 3.0, points = 601)
        checked = _msp_check(doc)
        @test _msp_w201(checked) == 0
        c, r, _ = bg_run(doc)
        @test r.status == "done"
        @test _msp_w201(r) == 0
        # the relative orientation is stored as a quaternion state: unit norm to solver accuracy
        nrm = sqrt.(c["Joint/qrel[1]"] .^ 2 .+ c["Joint/qrel[2]"] .^ 2 .+ c["Joint/qrel[3]"] .^ 2 .+
                    c["Joint/qrel[4]"] .^ 2)
        @test maximum(abs.(nrm .- 1)) <= 1.0e-9
        z = c["C2/g[7]"]
        @test maximum(z) - minimum(z) > 0.05                    # the body really falls and swings
        # world angular momentum about the pivot, component along the vertical (gravity has no
        # vertical torque): H = R (J w) + p x (m R v)
        Jd = collect(_MSP_PJ)
        Lz = zeros(length(z))
        for i in eachindex(z)
            R, p = _msp_pose(c, "C2/g", i)
            wb = [c["Body/flow/y[$k]"][i] for k in 1:3]
            vb = [c["Body/flow/y[$k]"][i] for k in 4:6]
            H = R * (Jd .* wb) .+ cross(p, m .* (R * vb))
            Lz[i] = H[3]
        end
        @test abs(Lz[1]) > 1.0e-3
        @test maximum(abs.(Lz .- Lz[1])) <= 1.0e-6 * abs(Lz[1]) + 1.0e-7
        E = _msp_ke(c, "Body", _MSP_PJ, m) .+ m * _MSP_G .* z .+ _msp_strain(c, "Joint", 1.0e9, 1.0e9)
        @test maximum(abs.(E .- E[1])) <= 1.0e-6 * (maximum(z) - minimum(z)) * m * _MSP_G
        println("J-MB9 spherical pendulum: norm drift ", maximum(abs.(nrm .- 1)), ", Lz drift ",
            maximum(abs.(Lz .- Lz[1])) / abs(Lz[1]))
    end

    @testset "Free3D floating body vs the J-MB8 free-body reference (PoseIntegrator3D)" begin
        P0 = (0.4, -0.2, 0.5, 0.3, 0.1, -0.2)
        ref_doc = _msp_free_reference(P0 = P0)
        jnt_doc = _msp_free_joint(P0 = P0)
        checked = _msp_check(jnt_doc)
        @test isempty(_msp_errors(checked))
        @test _msp_w201(checked) == 0
        cr, rr, _ = bg_run(ref_doc)
        cj, rj, _ = bg_run(jnt_doc)
        @test rr.status == "done" && rj.status == "done"
        @test _msp_w201(rj) == 0
        scale = maximum(abs.(cr["Pose/g[7]"])) + 1.0
        e = 0.0
        for i in eachindex(cr["time"])
            Rr, pr = _msp_pose(cr, "Pose/g", i)
            Rj, pj = _msp_pose(cj, "Joint/pose", i)
            e = max(e, maximum(abs.(Rr .- Rj)), maximum(abs.(pr .- pj)) / scale)
        end
        @test e <= 1.0e-6
        ep = maximum(maximum(abs.(cr["Body/inertia/P[$k]"] .- cj["Body/inertia/P[$k]"])) for k in 1:6)
        @test ep <= 1.0e-6
        # the joint's own invariants: unit norm and conserved energy KE + m g z
        nrm = sqrt.(cj["Joint/qrel[1]"] .^ 2 .+ cj["Joint/qrel[2]"] .^ 2 .+ cj["Joint/qrel[3]"] .^ 2 .+
                    cj["Joint/qrel[4]"] .^ 2)
        @test maximum(abs.(nrm .- 1)) <= 1.0e-9
        Ej = _msp_ke(cj, "Body", (0.3, 0.5, 0.7), 2.0) .+ 2.0 * _MSP_G .* cj["Joint/pose[7]"]
        @test maximum(abs.(Ej .- Ej[1])) <= 1.0e-6 * max(abs(Ej[1]), 1.0)
        println("J-MB9 Free3D vs PoseIntegrator3D over 10 s: pose ", e, ", momentum ", ep,
            ", norm drift ", maximum(abs.(nrm .- 1)))
    end
end
