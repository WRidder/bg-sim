# Work package J-MB10: a floating base with an attached link (plan 6, row J-MB10).
#
# `test_mech_spatial.jl` (J-MB9) already covers the spherical pendulum (quaternion norm, world
# angular momentum), the single `Free3D` body against the `PoseIntegrator3D` reference and the
# fixed-base chains. What it does not cover is a floating base that **carries a joint and a
# link**: the base is a `Free3D` joint on the ground, a `Revolute3D` is mounted on the base body
# and a second `RigidBody3D` hangs on it, so the base motion, the internal reaction and the
# fixed-base style pose composition (`free.pose o N o joint.pose o c`) act together.
#
# Free fall of the whole system under gravity has exact invariants that need no integrator
# reference: the centre of mass follows `X0 + V0 t - g t^2/2`, the angular momentum about the
# centre of mass is constant, and (without actuation) the energy `KE + PE + strain` is constant.
# With a sinusoidal torque in the joint (an internal action-reaction pair) the first two still
# hold, and the energy changes exactly by the work `int tau qdot dt`.
using Test
using BGSim
using LinearAlgebra

if !isdefined(@__MODULE__, :_ja_arm_model)
    include(joinpath(@__DIR__, "jmb10_arm.jl"))
end

const _JF_M0 = 3.0
const _JF_J0 = [0.05, 0.06, 0.04]
const _JF_M1 = 2.0
const _JF_J1 = [0.01, 0.04, 0.045]
const _JF_C1 = [0.3, 0.05, 0.0]                  # link centre of mass in the joint child frame
const _JF_RN = _ja_Rx(pi / 2)                   # joint frame in the base frame
const _JF_PN = [0.25, 0.0, 0.1]

"""The floating-base-plus-link model. `tau` is `(offset, amplitude, frequency)` of the joint
torque (zero for the free-swinging variant), `qd0` the initial joint rate."""
function _jf_model(; kk = 1.0e7, q0 = 0.4, qd0 = 1.0, tau = (0.0, 0.0, 1.0),
    qb = [0.9, 0.2, -0.3, 0.1], pb = [0.1, -0.2, 0.3], w0 = [0.5, -0.3, 0.8], v0 = [0.6, -0.2, 1.0],
    t_end = 1.5, points = 601)
    qn = qb ./ norm(qb)
    ident = [1.0, 0.0, 0.0, 0.0]
    # initial momenta: the base twist (w0, v0) in the base frame, the link carries it rigidly plus
    # the joint rate about the joint axis
    R = _JF_RN * _ja_Rz(q0)
    pcom = _JF_PN + R * _JF_C1
    w1 = R' * w0 + [0.0, 0.0, qd0]
    v1 = R' * (v0 + cross(w0, pcom) + qd0 * cross(_JF_RN * [0.0, 0.0, 1.0], R * _JF_C1))
    P0 = vcat(_JF_J0 .* w0, _JF_M0 .* v0)
    P1 = vcat(_JF_J1 .* w1, _JF_M1 .* v1)
    qi, pi_ = _ja_inv(_ja_quat(_JF_RN), _JF_PN)
    zeta = 0.7
    nodes = Any[
        bg_node("ground", "World", bg_ref("stdlib:multibond/GroundSpatial")),
        bg_node("free", "Free", bg_ref("stdlib:spatial/Free3D");
            starts = Dict{String,Any}("qw" => string(qn[1]), "qx" => string(qn[2]), "qy" => string(qn[3]),
                "qz" => string(qn[4]), "px" => string(pb[1]), "py" => string(pb[2]), "pz" => string(pb[3]))),
        bg_node("bj0", "BJ0", bg_junction("1")),
        bg_node("b0", "B0", bg_ref("stdlib:spatial/RigidBody3D");
            params = Dict{String,Any}("m" => string(_JF_M0), "J" => _ja_vec(_JF_J0), "g0" => string(_JA_G)),
            starts = Dict{String,Any}("inertia/P" => _ja_vec(P0))),
        bg_node("t1", "T1", bg_ref("stdlib:multibond/FixedTransform3DNeutral"); params = _ja_posepar(qi, pi_)),
        bg_node("j1", "J1", bg_ref("stdlib:spatial/Revolute3D");
            params = Dict{String,Any}("kt" => string(kk), "kr" => string(kk),
                "bt" => string(2 * zeta * sqrt(kk * _JF_M1)), "br" => string(2 * zeta * sqrt(kk * 0.05)),
                "q0" => string(q0))),
        bg_node("link", "Link", bg_ref("stdlib:multibond/FixedTransform3DNeutral");
            params = _ja_posepar(ident, _JF_C1)),
        bg_node("bj1", "BJ1", bg_junction("1")),
        bg_node("b1", "B1", bg_ref("stdlib:spatial/RigidBody3D");
            params = Dict{String,Any}("m" => string(_JF_M1), "J" => _ja_vec(_JF_J1), "g0" => string(_JA_G)),
            starts = Dict{String,Any}("inertia/P" => _ja_vec(P1))),
        bg_node("sine", "S", bg_ref("stdlib:sources/Sine");
            params = Dict{String,Any}("offset" => string(tau[1]), "amplitude" => string(tau[2]),
                "frequency" => string(tau[3]))),
        bg_node("drive", "D", bg_ref("stdlib:bondgraph/MSe")),
        bg_node("ln", "LN", bg_ref("stdlib:spatial/LocalPose3D"); params = _ja_posepar(_ja_quat(_JF_RN), _JF_PN)),
        bg_node("lc", "LC", bg_ref("stdlib:spatial/LocalPose3D"); params = _ja_posepar(ident, _JF_C1)),
        bg_node("c1", "C1", bg_ref("stdlib:multibond/ComposePose3D")),
        bg_node("c2", "C2", bg_ref("stdlib:multibond/ComposePose3D")),
        bg_node("c3", "C3", bg_ref("stdlib:multibond/ComposePose3D")),
    ]
    conns = Any[
        bg_conn("k1", "bond", "ground", "p", "free", "parent"),
        bg_conn("k2", "bond", "free", "child", "bj0", nothing),
        bg_conn("k3", "bond", "b0", "p", "bj0", nothing),
        bg_conn("k4", "bond", "t1", "b", "bj0", nothing),
        bg_conn("k5", "bond", "t1", "a", "j1", "parent"),
        bg_conn("k6", "bond", "j1", "child", "link", "a"),
        bg_conn("k7", "bond", "link", "b", "bj1", nothing),
        bg_conn("k8", "bond", "b1", "p", "bj1", nothing),
        bg_conn("k9", "signal", "sine", "y", "drive", "u"),
        bg_conn("k10", "bond", "drive", "p", "j1", "drive"),
        bg_conn("k11", "signal", "free", "pose", "b0", "g"),
        bg_conn("k12", "signal", "free", "pose", "c1", "gp"),
        bg_conn("k13", "signal", "ln", "g", "c1", "gl"),
        bg_conn("k14", "signal", "c1", "g", "c2", "gp"),
        bg_conn("k15", "signal", "j1", "pose", "c2", "gl"),
        bg_conn("k16", "signal", "c2", "g", "c3", "gp"),
        bg_conn("k17", "signal", "lc", "g", "c3", "gl"),
        bg_conn("k18", "signal", "c3", "g", "b1", "g"),
    ]
    for (k, port) in enumerate(("drive1", "drive2", "drive3", "drive4", "drive5", "drive6"))
        push!(nodes, bg_node("fd$k", "FD$k", bg_ref("stdlib:bondgraph/Se"); params = Dict{String,Any}("e" => "0.0")))
        push!(conns, bg_conn("kf$k", "bond", "fd$k", "p", "free", port))
    end
    return bg_model("FloatingBase", nodes, conns; t_end = t_end, points = points, reltol = 1.0e-9,
        abstol = 1.0e-11)
end

"""World-frame invariants of a run: centre of mass, linear momentum, angular momentum about the
centre of mass and the mechanical energy (without the joint strain)."""
function _jf_invariants(c)
    n = length(c["time"])
    M = _JF_M0 + _JF_M1
    X = zeros(3, n); L = zeros(3, n); H = zeros(3, n); E = zeros(n); KE = zeros(n)
    for i in 1:n
        pos = Vector{Vector{Float64}}()
        lin = Vector{Vector{Float64}}()
        ang = Vector{Vector{Float64}}()
        for (body, pose, m, J) in (("B0", "Free/pose", _JF_M0, _JF_J0), ("B1", "C3/g", _JF_M1, _JF_J1))
            Rk = _ja_Rq(c["$pose[1]"][i], c["$pose[2]"][i], c["$pose[3]"][i], c["$pose[4]"][i])
            push!(pos, [c["$pose[5]"][i], c["$pose[6]"][i], c["$pose[7]"][i]])
            P = [c["$body/inertia/P[$k]"][i] for k in 1:6]
            push!(ang, Rk * P[1:3])
            push!(lin, Rk * P[4:6])
            KE[i] += 0.5 * (sum(P[1:3] .^ 2 ./ J) + sum(P[4:6] .^ 2) / m)
            E[i] += _JA_G * m * pos[end][3]
        end
        X[:, i] = (_JF_M0 .* pos[1] .+ _JF_M1 .* pos[2]) ./ M
        L[:, i] = lin[1] .+ lin[2]
        Ho = ang[1] .+ ang[2] .+ cross(pos[1], lin[1]) .+ cross(pos[2], lin[2])
        H[:, i] = Ho .- cross(X[:, i], L[:, i])
    end
    return X, L, H, E .+ KE
end

@testset "J-MB10 floating base with an attached link" begin
    M = _JF_M0 + _JF_M1
    for (label, tau) in (("free swing", (0.0, 0.0, 1.0)), ("sinusoidal joint torque", (0.5, 3.0, 6.0)))
        @testset "$label: centre of mass, angular momentum, energy" begin
            kk = 1.0e7
            doc = _jf_model(kk = kk, tau = tau)
            c, r, flat, wall = _ja_run(doc)
            st = _ja_stats(r, flat, 1.5)
            X, L, H, E = _jf_invariants(c)
            t = c["time"]
            # the centre of mass is a parabola: X(t) = X0 + (L0/M) t - g t^2/2 z
            Xref = X[:, 1] .+ (L[:, 1] ./ M) .* t' .- 0.5 * _JA_G .* [zeros(length(t))'; zeros(length(t))'; (t .^ 2)']
            eX = maximum(abs.(X .- Xref))
            Lref = L[:, 1] .- [0.0, 0.0, M * _JA_G] .* t'
            eL = maximum(abs.(L .- Lref)) / norm(L[:, 1])
            eH = maximum(norm(H[:, i] - H[:, 1]) for i in eachindex(t)) / norm(H[:, 1])
            q = c["J1/qout"]
            @test maximum(q) - minimum(q) > 0.3                  # the link really swings
            strain = 0.5 * kk .* (c["J1/dang[1]"] .^ 2 .+ c["J1/dang[2]"] .^ 2 .+ c["J1/dlin[1]"] .^ 2 .+
                                  c["J1/dlin[2]"] .^ 2 .+ c["J1/dlin[3]"] .^ 2)
            Et = E .+ strain
            if tau[2] == 0
                eE = maximum(abs.(Et .- Et[1])) / abs(Et[1])
                @test eE <= 1.0e-8
            else
                # the energy changes by the work of the joint torque int tau qdot dt (trapezoid)
                tq = (tau[1] .+ tau[2] .* sin.(tau[3] .* t)) .* c["J1/qdout"]
                work = vcat(0.0, cumsum(0.5 .* (tq[1:(end - 1)] .+ tq[2:end]) .* diff(t)))
                eE = maximum(abs.(Et .- Et[1] .- work)) / maximum(abs.(work))
                @test maximum(abs.(work)) > 0.1
                @test eE <= 1.0e-4
            end
            @test eX <= 1.0e-8
            @test eL <= 1.0e-8
            @test eH <= 1.0e-8
            nrm = sqrt.(c["Free/qrel[1]"] .^ 2 .+ c["Free/qrel[2]"] .^ 2 .+ c["Free/qrel[3]"] .^ 2 .+ c["Free/qrel[4]"] .^ 2)
            @test maximum(abs.(nrm .- 1)) <= 1.0e-9
            println("J-MB10 floating base ", label, ": CoM ", eX, ", linear momentum ", eL,
                ", angular momentum about the CoM ", eH, ", energy ", eE, ", norm drift ",
                maximum(abs.(nrm .- 1)), "; states ", st.states, ", steps ", st.steps,
                ", wall ", round(wall; digits = 1), " s")
        end
    end
end
