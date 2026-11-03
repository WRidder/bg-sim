# Golden test for `stdlib:contact/RollingSphere` (a sphere on one spatial body rolling on a
# finite face fixed in another spatial body), through the real pipeline (`parse` -> `flatten`
# -> `simulate`, Rodas5P).
#
# The rig: a table (a `RigidBody3D` without gravity) on a `Revolute3D` about the world z axis,
# its drive either locked by a stiff C/R pair (a fixed table) or driven at a constant rate
# through a stiff C/R pair from an `Sf` (a turntable); a ball (a free `RigidBody3D` with its
# `PoseIntegrator3D`) bonded with the table to the contact. Every case has a closed form:
#
#   1. inclined face (the face normal of the locked table tilted by alpha about y): a solid
#      sphere released at rest rolls down at a = 5/7 g sin(alpha) (J = 2/5 m r^2) without slip,
#      the normal force is m g cos(alpha), the rotational share of the kinetic energy is 2/7 and
#      the energy book (ball energy + contact spring + integral of the dissipation) is constant;
#   2. rolling resistance crr on the same face: a = 5/7 g (sin(alpha) - crr cos(alpha)) (the
#      rolling moment crr r f_n opposes the rolling);
#   3. turntable at the constant rate W, the ball started rolling with the table (co-rotating
#      at radius rho): the friction of the moving face turns the ball's velocity at 2/7 W, so the
#      centre runs on a circle of radius 7 rho / 2 about (-5 rho / 2, 0) with the period 7 pi / W
#      (the classic ball on a turntable: dv/dt = J/(J + m r^2) W x v). The reaction goes into the
#      table: the drive torque integrates to the change of the angular momentum of table and ball.
#
# Tolerances: the regularised friction creeps at vs F_t / (mu f_n) (about 1e-4 m/s here), which
# sets the position tolerances; the integrators run at reltol 1e-9.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using BGSim
using LinearAlgebra
using .BondGraphGolden
import BGSim.Library

const RS_R = 0.02                     # ball radius (m)
const RS_M = 0.2                      # ball mass (kg)
const RS_J = 0.4 * RS_M * RS_R^2      # solid sphere
const RS_G0 = 9.81
const RS_K = 1.0e5                    # Hertz stiffness at xref (N/m)
const RS_XREF = 1.0e-4
const RS_JT = 10.0                    # table inertia about the axis (large: the rate stays put)

_rs(v) = string(Float64(v))
_rsv(v) = "[" * join(_rs.(collect(v)), ", ") * "]"
rs_delta(F) = (F * sqrt(RS_XREF) / RS_K)^(2 / 3)

"""
    rs_model(; alpha, crr, spin, rho, t_end, points)

The rig as a model document: the face is the table's plane z = 0, its normal tilted by
`alpha` about y. `spin = nothing` locks the table; `spin = W` drives it at W rad/s (the table
and the ball start rolling with it, the ball at (rho, 0)).
"""
function rs_model(; alpha = 0.0, crr = 0.0, spin = nothing, rho = 0.0, t_end = 1.0, points = 201)
    n = (sin(alpha), 0.0, cos(alpha))
    t1 = (cos(alpha), 0.0, -sin(alpha))
    F = RS_M * RS_G0 * cos(alpha)
    c0 = rho .* t1 .+ (RS_R - rs_delta(F)) .* n
    W = spin === nothing ? 0.0 : Float64(spin)
    # ball momentum (body frame = world at the start): turning with the table, W about z
    Pb = (0.0, 0.0, RS_J * W, -RS_M * W * c0[2], RS_M * W * c0[1], 0.0)
    nodes = Any[
        bg_node("w", "World", bg_ref("stdlib:multibond/GroundSpatial")),
        bg_node("j", "Bearing", bg_ref("stdlib:spatial/Revolute3D");
            params = Dict{String,Any}("kr" => "1.0e8", "kt" => "1.0e8", "br" => "100.0", "bt" => "1000.0")),
        bg_node("t", "Table", bg_ref("stdlib:spatial/RigidBody3D");
            params = Dict{String,Any}("m" => "2.0", "J" => _rsv((5.0, 5.0, RS_JT)), "g0" => "0.0"),
            starts = Dict{String,Any}("inertia/P" => _rsv((0, 0, RS_JT * W, 0, 0, 0)))),
        bg_node("b", "Ball", bg_ref("stdlib:spatial/RigidBody3D");
            params = Dict{String,Any}("m" => _rs(RS_M), "J" => _rsv((RS_J, RS_J, RS_J)), "g0" => _rs(RS_G0)),
            starts = Dict{String,Any}("inertia/P" => _rsv(Pb))),
        bg_node("pose", "Pose", bg_ref("stdlib:multibond/PoseIntegrator3D");
            starts = Dict{String,Any}("px" => _rs(c0[1]), "py" => _rs(c0[2]), "pz" => _rs(c0[3]))),
        bg_node("c", "Contact", bg_ref("stdlib:contact/RollingSphere");
            params = Dict{String,Any}("r" => _rs(RS_R), "nx" => _rs(n[1]), "ny" => "0.0", "nz" => _rs(n[3]),
                "tx" => _rs(t1[1]), "ty" => "0.0", "tz" => _rs(t1[3]), "w1" => "1.0", "w2" => "1.0",
                "k" => _rs(RS_K), "xref" => _rs(RS_XREF), "c" => "20.0", "mu" => "0.5", "vs" => "1.0e-3",
                "crr" => _rs(crr), "eps" => "1.0e-7")),
        bg_node("lk", "Lock", bg_junction(1)),
        bg_node("sp", "Spring", bg_ref("stdlib:bondgraph/C"); params = Dict{String,Any}("c" => "1.0e-6")),
        bg_node("dp", "Damper", bg_ref("stdlib:bondgraph/R"); params = Dict{String,Any}("r" => "500.0")),
    ]
    conns = Any[
        bg_conn("b1", "bond", "w", "p", "j", "parent"),
        bg_conn("b2", "bond", "j", "child", "t", "p"),
        bg_conn("b3", "bond", "t", "p", "c", "a"),
        bg_conn("b4", "bond", "b", "p", "c", "b"),
        bg_conn("b5", "bond", "lk", nothing, "sp", "p"),
        bg_conn("b6", "bond", "lk", nothing, "dp", "p"),
        bg_conn("s1", "signal", "j", "pose", "t", "g"),
        bg_conn("s2", "signal", "b", "V", "pose", "tw"),
        bg_conn("s3", "signal", "pose", "g", "b", "g"),
        bg_conn("s4", "signal", "j", "pose", "c", "ga"),
        bg_conn("s5", "signal", "pose", "g", "c", "gb"),
    ]
    if spin === nothing
        push!(conns, bg_conn("b7", "bond", "j", "drive", "lk", nothing))
    else
        # Sf -> 0 -> drive, 0 -> lock (the C/R pair carries the drive torque)
        push!(nodes, bg_node("sf", "Spin", bg_ref("stdlib:bondgraph/Sf"); params = Dict{String,Any}("f" => _rs(-W))))
        push!(nodes, bg_node("z", "Hub", bg_junction(0)))
        append!(conns, Any[
            bg_conn("b7", "bond", "sf", "p", "z", nothing),
            bg_conn("b8", "bond", "z", nothing, "j", "drive"),
            bg_conn("b9", "bond", "z", nothing, "lk", nothing),
        ])
    end
    return bg_model("RollingSphereRig", nodes, conns; t_end = t_end, points = points,
        reltol = 1.0e-9, abstol = 1.0e-11)
end

"""Cumulative trapezoid integral."""
rs_cumint(t, y) = [0.0; cumsum([0.5 * (y[k] + y[k + 1]) * (t[k + 1] - t[k]) for k in 1:length(t) - 1])]

@testset "RollingSphere (golden)" begin
    blocks = Dict(b.ref => b for b in Library.load_stdlib())

    @testset "catalog: Contact group, clean block, ports and units" begin
        b = blocks["stdlib:contact/RollingSphere"]
        @test b.group == "Contact"
        @test b.icon == "ct-rolling-sphere"
        @test !isempty(b.description)
        @test isempty(check_block(b.ast))
        bal = block_balance(b.ast)
        @test bal.unknowns == bal.equations
        @test [(p.name, p.domain) for p in b.interface.ports] == [("a", "Spatial"), ("b", "Spatial")]
        for d in b.interface.parameters
            @test !isempty(d.description)
        end
        env = BGSim.Units.unit_env(b.ast)
        for port in ("a", "b"), k in 1:3
            @test env.labels[Symbol(port, ".e[", k, "]")] == "N*m"
            @test env.labels[Symbol(port, ".e[", k + 3, "]")] == "N"
        end
    end

    @testset "inclined face: 5/7 g sin(alpha), no slip, 2/7 rotational energy, energy book" begin
        alpha = 0.05
        cols, res, _ = bg_run(rs_model(alpha = alpha, t_end = 1.0, points = 201))
        @test res.status == "done"
        t = cols["time"]
        a = 5 / 7 * RS_G0 * sin(alpha)
        for tk in (0.5, 1.0)
            @test bg_value(cols, "Contact/u1", tk) ≈ 0.5 * a * tk^2 rtol = 2e-3
        end
        @test bg_value(cols, "Contact/f_n", 1.0) ≈ RS_M * RS_G0 * cos(alpha) rtol = 1e-4
        @test maximum(bg_all(cols, "Contact/slip")[t .> 0.05]) < 1e-4
        V = [bg_value(cols, "Pose/tw[$k]", 1.0) for k in 1:6]
        P = [bg_value(cols, "Ball/inertia/P[$k]", 1.0) for k in 1:6]
        Ek = 0.5 * dot(P, V)
        @test 0.5 * dot(P[1:3], V[1:3]) / Ek ≈ 2 / 7 rtol = 2e-3
        # energy book: ball kinetic + potential + contact spring + dissipated
        n = length(t)
        E = [0.5 * sum(cols["Ball/inertia/P[$k]"][i] * cols["Pose/tw[$k]"][i] for k in 1:6) +
             RS_M * RS_G0 * cols["Pose/g[7]"][i] + cols["Contact/Ec"][i] for i in 1:n]
        Eb = E .+ rs_cumint(t, cols["Contact/Pd"])
        win = t .> 0.05
        @test maximum(Eb[win]) - minimum(Eb[win]) < 1e-4 * Ek
    end

    @testset "rolling resistance: 5/7 g (sin(alpha) - crr cos(alpha))" begin
        alpha, crr = 0.05, 0.02
        cols, res, _ = bg_run(rs_model(alpha = alpha, crr = crr, t_end = 1.0, points = 201))
        @test res.status == "done"
        a = 5 / 7 * RS_G0 * (sin(alpha) - crr * cos(alpha))
        @test bg_value(cols, "Contact/u1", 1.0) ≈ 0.5 * a rtol = 5e-3
        @test maximum(bg_all(cols, "Contact/Pd")) > 0          # the rolling moment dissipates
    end

    @testset "turntable: the ball circles at 2/7 of the table rate; the table feels the reaction" begin
        W, rho = 2pi, 0.04
        T = 7pi / W                                           # 3.5 s
        cols, res, _ = bg_run(rs_model(spin = W, rho = rho, t_end = T, points = 701))
        @test res.status == "done"
        t = cols["time"]
        C = (-2.5rho, 0.0)
        Rc = 3.5rho
        for frac in (0.25, 0.5, 1.0)
            ph = 2pi * frac
            x = C[1] + Rc * cos(ph)
            y = C[2] + Rc * sin(ph)
            tk = round(frac * T; digits = 3)
            @test bg_value(cols, "Pose/g[5]", tk) ≈ x atol = 2e-3
            @test bg_value(cols, "Pose/g[6]", tk) ≈ y atol = 2e-3
        end
        @test bg_value(cols, "Bearing/qdout", T) ≈ W rtol = 1e-3
        @test maximum(bg_all(cols, "Contact/slip")[t .> 0.05]) < 1e-3
        @test bg_value(cols, "Contact/f_n", T / 2) ≈ RS_M * RS_G0 rtol = 1e-3
        # angular momentum about the axis: table + ball (orbital + spin; J isotropic)
        function Lz(i)
            q = [cols["Pose/g[$k]"][i] for k in 1:4]
            w = [cols["Pose/tw[$k]"][i] for k in 1:3]
            # world z of the body-frame spin: third row of R(q)
            r3 = (2 * (q[2] * q[4] - q[1] * q[3]), 2 * (q[3] * q[4] + q[1] * q[2]),
                  q[1]^2 - q[2]^2 - q[3]^2 + q[4]^2)
            x, y = cols["Pose/g[5]"][i], cols["Pose/g[6]"][i]
            pw = [cols["Ball/inertia/P[$k]"][i] for k in 4:6]
            # world linear momentum: R(q) * body momentum
            R = [q[1]^2+q[2]^2-q[3]^2-q[4]^2 2*(q[2]*q[3]-q[1]*q[4]) 2*(q[2]*q[4]+q[1]*q[3]);
                 2*(q[2]*q[3]+q[1]*q[4]) q[1]^2-q[2]^2+q[3]^2-q[4]^2 2*(q[3]*q[4]-q[1]*q[2]);
                 r3[1] r3[2] r3[3]]
            p = R * pw
            return RS_JT * cols["Bearing/qdout"][i] + x * p[2] - y * p[1] + RS_J * dot(collect(r3), w)
        end
        tau = rs_cumint(t, cols["Spring/p.e"])
        dL = [Lz(i) - Lz(1) for i in eachindex(t)]
        scale = maximum(abs.(dL)) + RS_M * W * rho^2
        @test maximum(abs.(dL .- tau)) < 1e-3 * scale || maximum(abs.(dL .+ tau)) < 1e-3 * scale
    end
end
