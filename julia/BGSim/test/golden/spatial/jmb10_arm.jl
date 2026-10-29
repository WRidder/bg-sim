# Shared rig and reference for the J-MB10 golden tests (six-axis arm, spatial checks).
#
# Everything here is `_ja_`-prefixed because the test files share `Main`. It is included (guarded)
# by `test_six_axis_arm.jl` and `test_floating_base.jl`; it is not a test file itself, so the
# golden walk of `runtests.jl` (which includes only `test_*.jl`) does not run it on its own.
#
# The arm is a UR5-like six-axis serial arm built from the J-MB9 composites. Joint i rotates about
# the local z of its joint frame; its frame in the previous link's rotating frame is `N_i` (the
# standard-DH fixed part `Tz(d) Tx(a) Rx(alpha)` of the previous link), the link's centre of mass
# is `c_i` in the rotating frame and the inertia is principal about the centre of mass.
#
# The reference is an iterative Newton-Euler written with 3-vectors and rotation matrices (the
# Craig formulation): a different formulation from the 6-vector recursion of
# `test_mech_spatial.jl` and from the model, which carries spatial wrenches through the bonds.
using Test
using BGSim
import BGSim.IR
import BGSim.Compile
using LinearAlgebra

if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using .BondGraphGolden

const _JA_G = 9.81

_ja_Rz(q) = [cos(q) -sin(q) 0.0; sin(q) cos(q) 0.0; 0.0 0.0 1.0]
_ja_Rx(q) = [1.0 0.0 0.0; 0.0 cos(q) -sin(q); 0.0 sin(q) cos(q)]

"""Unit quaternion `(w, x, y, z)` of a rotation matrix (Shepperd's method)."""
function _ja_quat(R)
    t = R[1, 1] + R[2, 2] + R[3, 3]
    if t > 0
        s = 2 * sqrt(1 + t)
        return [s / 4, (R[3, 2] - R[2, 3]) / s, (R[1, 3] - R[3, 1]) / s, (R[2, 1] - R[1, 2]) / s]
    elseif R[1, 1] >= R[2, 2] && R[1, 1] >= R[3, 3]
        s = 2 * sqrt(1 + R[1, 1] - R[2, 2] - R[3, 3])
        return [(R[3, 2] - R[2, 3]) / s, s / 4, (R[1, 2] + R[2, 1]) / s, (R[1, 3] + R[3, 1]) / s]
    elseif R[2, 2] >= R[3, 3]
        s = 2 * sqrt(1 + R[2, 2] - R[1, 1] - R[3, 3])
        return [(R[1, 3] - R[3, 1]) / s, (R[1, 2] + R[2, 1]) / s, s / 4, (R[2, 3] + R[3, 2]) / s]
    end
    s = 2 * sqrt(1 + R[3, 3] - R[1, 1] - R[2, 2])
    return [(R[2, 1] - R[1, 2]) / s, (R[1, 3] + R[3, 1]) / s, (R[2, 3] + R[3, 2]) / s, s / 4]
end

"""Rotation matrix of the quaternion `(w, x, y, z)` (normalised)."""
function _ja_Rq(w, x, y, z)
    s = w * w + x * x + y * y + z * z
    return [
        (w * w + x * x - y * y - z * z) 2 * (x * y - w * z) 2 * (x * z + w * y)
        2 * (x * y + w * z) (w * w - x * x + y * y - z * z) 2 * (y * z - w * x)
        2 * (x * z - w * y) 2 * (y * z + w * x) (w * w - x * x - y * y + z * z)
    ] ./ s
end

_ja_vec(v) = "[" * join([string(x) for x in v], ", ") * "]"

function _ja_posepar(q, p)
    return Dict{String,Any}("qw" => string(q[1]), "qx" => string(q[2]), "qy" => string(q[3]),
        "qz" => string(q[4]), "x" => string(p[1]), "y" => string(p[2]), "z" => string(p[3]))
end

"""The inverse of the pose `(q, p)`."""
function _ja_inv(q, p)
    qc = [q[1], -q[2], -q[3], -q[4]]
    return qc, -(_ja_Rq(qc...) * p)
end

_ja_check(doc) = Compile.model_check(IR.parse_model(doc))
_ja_errors(result) = [d for d in result.diagnostics if d.severity == "error"]
_ja_w201(result) = count(d -> d.code == "W201", result.diagnostics)

# ---------------------------------------------------------------------------------------
# The arm: geometry, inertia, independent Newton-Euler reference
# ---------------------------------------------------------------------------------------

struct _JaLink
    RN::Matrix{Float64}      # joint frame i in the rotating frame of link i-1 (rotation)
    pN::Vector{Float64}      # ... and its origin
    c::Vector{Float64}       # centre of mass in the rotating frame of link i
    m::Float64
    J::Vector{Float64}       # principal moments about the centre of mass (axes = frame i)
end

"""UR5-like six-axis arm: standard-DH fixed parts, masses and inertias of the right order."""
function _ja_arm()
    d = [0.089159, 0.0, 0.0, 0.10915, 0.09465, 0.0823]
    a = [0.0, -0.425, -0.39225, 0.0, 0.0, 0.0]
    alpha = [pi / 2, 0.0, 0.0, pi / 2, -pi / 2, 0.0]
    cs = [[0.0, -0.026, 0.045], [-0.2125, 0.0, 0.1134], [-0.196, 0.0, 0.0265],
        [0.0, -0.0018, 0.055], [0.0, 0.0018, 0.047], [0.0, 0.0, 0.0412]]
    ms = [3.7, 8.393, 2.275, 1.219, 1.219, 0.74]
    Js = [[0.0103, 0.0103, 0.0067], [0.0151, 0.2269, 0.2269], [0.0041, 0.0494, 0.0494],
        [0.0025, 0.0025, 0.0021], [0.0025, 0.0025, 0.0021], [0.0004, 0.0004, 0.0005]]
    links = _JaLink[]
    for i in 1:6
        RN = i == 1 ? Matrix(1.0I, 3, 3) : _ja_Rx(alpha[i - 1])
        pN = i == 1 ? zeros(3) : [a[i - 1], 0.0, d[i - 1]]
        push!(links, _JaLink(RN, pN, cs[i], ms[i], Js[i]))
    end
    return links
end

"""
    _ja_rne(arm, q, qd, qdd; g) -> (tau, wrenches)

Iterative Newton-Euler. `tau[i]` is the generalised force along the z axis of joint i needed to
produce `qdd` (`n_i . z`), `wrenches[i] = (f, n)` the force and moment the previous link exerts
on link i at the origin of its rotating frame, in that frame. Gravity enters as a base
acceleration `+g z`.
"""
function _ja_rne(arm, q, qd, qdd; g = _JA_G)
    n = length(arm)
    ez = [0.0, 0.0, 1.0]
    w = zeros(3)
    al = zeros(3)
    a = [0.0, 0.0, g]
    Rs = Vector{Matrix{Float64}}(undef, n)       # Rs[i] maps frame i into frame i-1
    ws = Vector{Vector{Float64}}(undef, n)
    als = Vector{Vector{Float64}}(undef, n)
    acs = Vector{Vector{Float64}}(undef, n)
    for i in 1:n
        L = arm[i]
        Rz = _ja_Rz(q[i])
        R = L.RN * Rz
        Rs[i] = R
        wj = Rz' * (L.RN' * w)                   # parent rate in the rotated joint frame
        aj = Rz' * (L.RN' * al)
        wn = wj + ez * qd[i]
        aln = aj + cross(wj, ez * qd[i]) + ez * qdd[i]
        an = R' * (a + cross(al, L.pN) + cross(w, cross(w, L.pN)))
        w, al, a = wn, aln, an
        ws[i] = w
        als[i] = al
        acs[i] = a + cross(al, L.c) + cross(w, cross(w, L.c))
    end
    tau = zeros(n)
    wr = Vector{Tuple{Vector{Float64},Vector{Float64}}}(undef, n)
    f = zeros(3)
    nn = zeros(3)                                # wrench of link i+1 on link i, in frame i+1
    pnext = zeros(3)
    Rnext = Matrix(1.0I, 3, 3)
    for i in n:-1:1
        L = arm[i]
        F = L.m * acs[i]
        Jd = Diagonal(L.J)
        Nn = Jd * als[i] + cross(ws[i], Jd * ws[i])
        fi = Rnext * f + F
        ni = Nn + Rnext * nn + cross(L.c, F) + cross(pnext, Rnext * f)
        wr[i] = (fi, ni)
        tau[i] = ni[3]
        f, nn = fi, ni
        pnext = L.pN                             # origin of frame i in frame i-1
        Rnext = Rs[i]
    end
    return tau, wr
end

"""World centres of mass, the kinetic energy and the world frame of every link at `(q, qd)`."""
function _ja_kin(arm, q, qd)
    ez = [0.0, 0.0, 1.0]
    Rw = Matrix(1.0I, 3, 3)
    pw = zeros(3)
    w = zeros(3)
    v = zeros(3)
    ke = 0.0
    coms = Vector{Vector{Float64}}()
    for i in eachindex(arm)
        L = arm[i]
        Rz = _ja_Rz(q[i])
        R = L.RN * Rz
        pw = pw + Rw * L.pN
        Rw = Rw * R
        wj = Rz' * (L.RN' * w)
        v = R' * (v + cross(w, L.pN))
        w = wj + ez * qd[i]
        vc = v + cross(w, L.c)
        ke += 0.5 * L.m * dot(vc, vc) + 0.5 * dot(w, Diagonal(L.J) * w)
        push!(coms, pw + Rw * L.c)
    end
    return coms, ke
end

function _ja_energy(arm, q, qd; g = _JA_G)
    coms, ke = _ja_kin(arm, q, qd)
    return ke, sum(arm[i].m * g * coms[i][3] for i in eachindex(arm))
end

"""Mass matrix and bias force of the reference: `M qdd + h = tau`."""
function _ja_mh(arm, q, qd; g = _JA_G)
    n = length(arm)
    h, _ = _ja_rne(arm, q, qd, zeros(n); g = g)
    M = zeros(n, n)
    for j in 1:n
        e = zeros(n)
        e[j] = 1.0
        col, _ = _ja_rne(arm, q, zeros(n), e; g = 0.0)
        M[:, j] = col
    end
    return M, h
end

function _ja_fd(arm, q, qd, tau; g = _JA_G)
    M, h = _ja_mh(arm, q, qd; g = g)
    return M \ (tau .- h)
end

"""RK4 of `M qdd = tau(t) - h` from `(q0, qd0)`; the state at every `stride`-th step."""
function _ja_rk4(arm, tau, q0, qd0, dt, stride, t_end)
    n = length(arm)
    rhs(t, y) = vcat(y[(n + 1):(2n)], _ja_fd(arm, y[1:n], y[(n + 1):(2n)], tau(t)))
    y = vcat(q0, qd0)
    out = [copy(y)]
    for k in 1:round(Int, t_end / dt)
        t = (k - 1) * dt
        k1 = rhs(t, y)
        k2 = rhs(t + dt / 2, y .+ (dt / 2) .* k1)
        k3 = rhs(t + dt / 2, y .+ (dt / 2) .* k2)
        k4 = rhs(t + dt, y .+ dt .* k3)
        y = y .+ (dt / 6) .* (k1 .+ 2 .* k2 .+ 2 .* k3 .+ k4)
        k % stride == 0 && push!(out, copy(y))
    end
    return out
end

"""Joint deflections of a model released at rest with joint acceleration `qdd` (FIX-MB-3): the
model's child effort is minus the wrench the joint exerts on the link, and the deflection is that
effort over the stiffness, so the stiff modes are not excited by the start."""
function _ja_deflections(arm, q, qdd, kr, kt)
    n = length(arm)
    _, wr = _ja_rne(arm, q, zeros(n), qdd)
    return [([-wr[i][2][1], -wr[i][2][2]] ./ kr, -wr[i][1] ./ kt) for i in 1:n]
end

# ---------------------------------------------------------------------------------------
# The model. Per joint i: `T_i` (from the previous link's junction) -> J_i -> Link_i -> BJ_i, with
# the body B_i and T_{i+1} on the 1-junction BJ_i. Rig orientation rule: the transformers are
# `a.f = -Ad(g) b.f`, so `a` is on the joint port and `b` on the ground or body side, and g is the
# body-side pose in the joint-side frame.
# ---------------------------------------------------------------------------------------

"""
Drive of one joint. A flow source on the drive port cannot impose the motion: the joint takes the
drive **effort** and gives the flow (`drive => :flow_out`), so a flow source puts the joint in
derivative causality (W201, raised index) and the start does not initialise. The joint is
therefore driven through the effort port in two ways:

- `_ja_effort(offset, A, w)`: open loop, `tau = offset + A sin(w t)` (a modulated effort source).
- `_ja_servo(q0, A, w, kp, kd)`: a stiff tracking servo `tau = kp (q_r - q) + kd (qd_r - qd)` on
  the reference `q_r = q0 + A/w (1 - cos(w t))`, `qd_r = A sin(w t)`. The servo is the high
  stiffness variant of an imposed motion: with `M e'' + kd e' + kp e = tau_RNE(t)` for the tracking
  error `e`, the torque the servo applies differs from the Newton-Euler torque of the reference
  by `M e''`, which falls like `1/kp`.
"""
_ja_effort(offset, A, w) = (q0 = 0.0, amplitude = 0.0, frequency = 1.0, kp = 0.0, kd = 0.0, ffo = offset, ffa = A, ffw = w)
_ja_servo(q0, A, w, kp, kd) = (q0 = q0, amplitude = A, frequency = w, kp = kp, kd = kd, ffo = 0.0, ffa = 0.0, ffw = 1.0)

"""The servo law as an inline block (the stdlib has no multi-input PD)."""
const _JA_SERVO = """
@block Servo begin
    @parameters begin
        kp::Real = 1.0e6, [description = "Position gain"]
        kd::Real = 1.0e3, [description = "Rate gain"]
    end
    @inputs qr::Real
    @inputs qdr::Real
    @inputs q::Real
    @inputs qd::Real
    @inputs ff::Real
    @outputs tau::Real
    @equations begin
        tau ~ kp * (qr - q) + kd * (qdr - qd) + ff
    end
end
"""

"""Damping of the held directions, `zeta` of critical for the distal mass (translations) and for a
reference inertia of 0.3 kg m^2 (rotations): `(br, bt)` per joint."""
function _ja_damping(arm, kk, zeta)
    bt = [2 * zeta * sqrt(kk * sum(L.m for L in arm[i:end])) for i in eachindex(arm)]
    return fill(2 * zeta * sqrt(kk * 0.3), length(arm)), bt
end

"""
    _ja_arm_model(arm, drives; kk, zeta, q0, qdd0, t_end, points, g0)

The arm as a model document, released at rest at `q0`. `kk` is the translational and rotational
stiffness of the five held directions of every joint. The damping on them is `zeta` of critical for the
distal mass (translations) and for a reference inertia of 0.3 kg m^2 (rotations), so the stiff modes
die in milliseconds and keep the solver from taking tiny steps.
`qdd0` is the joint acceleration at `t = 0` the consistent deflection starts are built for.
"""
function _ja_arm_model(arm, drives; kk, zeta = 0.7, q0, qdd0 = zeros(length(arm)),
    t_end = 1.5, points = 301, g0 = _JA_G, name = "Arm6")
    n = length(arm)
    br, bt = _ja_damping(arm, kk, zeta)
    defl = _ja_deflections(arm, q0, qdd0, kk, kk)
    nodes = Any[]
    conns = Any[]
    cid = Ref(0)
    bond!(a, ap, b, bp) = push!(conns, bg_conn("c$(cid[] += 1)", "bond", a, ap, b, bp))
    sig!(a, ap, b, bp) = push!(conns, bg_conn("c$(cid[] += 1)", "signal", a, ap, b, bp))
    ident = [1.0, 0.0, 0.0, 0.0]
    push!(nodes, bg_node("ground", "World", bg_ref("stdlib:multibond/GroundSpatial")))
    push!(nodes, bg_node("mount", "Mount", bg_ref("stdlib:multibond/FixedTransform3DNeutral");
        params = _ja_posepar(ident, zeros(3))))
    push!(nodes, bg_node("mpose", "MountPose", bg_ref("stdlib:spatial/LocalPose3D");
        params = _ja_posepar(ident, zeros(3))))
    bond!("ground", "p", "mount", "b")
    wprev = "mpose"                              # pose of the joint-side frame in the world
    for i in 1:n
        L = arm[i]
        jn, bj, bn = "j$i", "bj$i", "b$i"
        if i > 1
            # the junction is the body-(i-1) frame (its centre of mass), so the joint frame sits at pN - c_{i-1}
            qi, pi_ = _ja_inv(_ja_quat(L.RN), L.pN - arm[i - 1].c)
            push!(nodes, bg_node("t$i", "T$i", bg_ref("stdlib:multibond/FixedTransform3DNeutral");
                params = _ja_posepar(qi, pi_)))
            bond!("t$i", "a", jn, "parent")
            bond!("t$i", "b", "bj$(i - 1)", nothing)
        else
            bond!("mount", "a", jn, "parent")
        end
        push!(nodes, bg_node(jn, "J$i", bg_ref("stdlib:spatial/Revolute3D");
            params = Dict{String,Any}("kt" => string(kk), "kr" => string(kk), "bt" => string(bt[i]),
                "br" => string(br[i]), "q0" => string(q0[i])),
            starts = Dict{String,Any}("dth" => _ja_vec(defl[i][1]), "dl" => _ja_vec(defl[i][2]))))
        push!(nodes, bg_node("link$i", "Link$i", bg_ref("stdlib:multibond/FixedTransform3DNeutral");
            params = _ja_posepar(ident, L.c)))
        push!(nodes, bg_node(bj, "BJ$i", bg_junction("1")))
        push!(nodes, bg_node(bn, "B$i", bg_ref("stdlib:spatial/RigidBody3D");
            params = Dict{String,Any}("m" => string(L.m), "J" => _ja_vec(L.J), "g0" => string(g0))))
        bond!(jn, "child", "link$i", "a")
        bond!("link$i", "b", bj, nothing)
        bond!(bn, "p", bj, nothing)
        dr = drives[i]
        sine(id, name; amplitude, offset, frequency, phase = 0.0) = bg_node(id, name, bg_ref("stdlib:sources/Sine");
            params = Dict{String,Any}("amplitude" => string(amplitude),
                "frequency" => string(frequency), "offset" => string(offset),
                "phase" => string(phase)))
        # One structure for every run (so the compile cache is hit): reference sines, the servo with
        # gains `kp`, `kd` and a feedforward sine, and the modulated effort source. Open-loop runs
        # set kp = kd = 0; the servo reference is q_r = q0 + A/w (1 - cos(wt)) = (q0 + A/w) -
        # (A/w) sin(wt + pi/2) and qd_r = A sin(wt).
        push!(nodes, bg_node("d$i", "D$i", bg_ref("stdlib:bondgraph/MSe")))
        A, w = dr.amplitude, dr.frequency
        push!(nodes, sine("sq$i", "Qr$i"; amplitude = -A / w, offset = dr.q0 + A / w, frequency = w, phase = pi / 2))
        push!(nodes, sine("sd$i", "Qdr$i"; amplitude = A, offset = 0.0, frequency = w))
        push!(nodes, sine("sf$i", "Ff$i"; amplitude = dr.ffa, offset = dr.ffo, frequency = dr.ffw))
        push!(nodes, bg_node("s$i", "S$i", Dict{String,Any}("inline" => Dict{String,Any}("source" => _JA_SERVO));
            params = Dict{String,Any}("kp" => string(dr.kp), "kd" => string(dr.kd))))
        sig!("sq$i", "y", "s$i", "qr")
        sig!("sd$i", "y", "s$i", "qdr")
        sig!("sf$i", "y", "s$i", "ff")
        sig!(jn, "qout", "s$i", "q")
        sig!(jn, "qdout", "s$i", "qd")
        sig!("s$i", "tau", "d$i", "u")
        bond!("d$i", "p", jn, "drive")
        # fixed-base poses: W_i = W_{i-1} o N_i o pose_i, body pose = W_i o c_i
        push!(nodes, bg_node("ln$i", "LN$i", bg_ref("stdlib:spatial/LocalPose3D");
            params = _ja_posepar(_ja_quat(L.RN), L.pN)))
        push!(nodes, bg_node("lc$i", "LC$i", bg_ref("stdlib:spatial/LocalPose3D");
            params = _ja_posepar(ident, L.c)))
        push!(nodes, bg_node("ca$i", "CA$i", bg_ref("stdlib:multibond/ComposePose3D")))
        push!(nodes, bg_node("cb$i", "W$i", bg_ref("stdlib:multibond/ComposePose3D")))
        push!(nodes, bg_node("cc$i", "P$i", bg_ref("stdlib:multibond/ComposePose3D")))
        sig!(wprev, "g", "ca$i", "gp")
        sig!("ln$i", "g", "ca$i", "gl")
        sig!("ca$i", "g", "cb$i", "gp")
        sig!(jn, "pose", "cb$i", "gl")
        sig!("cb$i", "g", "cc$i", "gp")
        sig!("lc$i", "g", "cc$i", "gl")
        sig!("cc$i", "g", bn, "g")
        wprev = "cb$i"
    end
    return bg_model(name, nodes, conns; t_end = t_end, points = points, reltol = 1.0e-9,
        abstol = 1.0e-11)
end

"""Run one document. Returns `(columns, result, flat, wall_seconds)`; checks the diagnostics (no
errors, no W201 in `model_check` or in the run) and that the run finished."""
function _ja_run(doc)
    checked = _ja_check(doc)
    @test isempty(_ja_errors(checked))
    @test _ja_w201(checked) == 0
    wall = @elapsed (c, r, flat) = bg_run(doc)
    @test r.status == "done"
    @test _ja_w201(r) == 0
    return c, r, flat, wall
end

"""Gate C numbers of a finished run: states of the compiled system, accepted steps, wall time of
the solve per simulated second (the structural compile cache makes `compile_s` zero on a hit)."""
function _ja_stats(r, flat, t_end)
    nstates = length(BGSim.lower_model(flat; t_end = t_end).problem.u0)
    return (states = nstates, steps = r.stats.steps, sim_per_s = r.stats.sim_s / t_end,
        compile_s = r.stats.compile_s)
end

