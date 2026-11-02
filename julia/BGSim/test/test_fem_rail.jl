# FEM flexible body with a rail (`stdlib:spatial/ModalBody3D`, ports E and S): a carriage
# slides along a moving interface on the deformed part.
#
# The fixture `fixtures/fem/rbar.modal.json` is a bar 200 x 20 x 10 mm of a soft test material
# (E = 70 MPa; first mode 6.5 Hz) clamped at A, with a rail along its top face from x = 20 to
# 180 mm and one rail load mode at mid-rail; regenerate it with
# `julia --project=julia/BGSimFEM julia/BGSimFEM/bin/bgsim-fem.jl julia/BGSim/test/fixtures/fem/rbar.fem.json`.
#
#   * the loader: nr, nc and the Chebyshev tables;
#   * statics: a carriage's weight at s gives kk q = PT(s)' F (the rail tables), and at the
#     load-mode station the full FE deflection (the file's `validation.rail`);
#   * the carriage rides the deformed rail: moving it along the sagging bar, the guide's
#     transverse deflection stays at the bearing's own (F / kt), far below the sag;
#   * energy: undamped, the bar, the slider, the carriage and the springs conserve their sum.
using Test
using BGSim
using LinearAlgebra
import JSON3

isdefined(@__MODULE__, :_fem_free) || include(joinpath(@__DIR__, "fem_body_rigs.jl"))

const RAIL_FILE = "rbar.modal.json"
const RAIL_DATA = JSON3.read(read(joinpath(FEM_FX, RAIL_FILE), String), Dict{String,Any})
const RAIL_C = Dict(BGSim.load_modal_body(FEM_FX, Dict{String,Any}("file" => RAIL_FILE)))
const RAIL_NM = RAIL_C["nm"]

"""PT(s) (3 x nm, R) from the file's Chebyshev tables."""
function _rail_pt(s)
    r = RAIL_DATA["rail"]
    L, nc = Float64(r["length"]), Int(r["chebyshev"])
    x = 2s / L - 1
    T = zeros(nc)
    T[1] = 1.0
    T[2] = x
    for n in 3:nc
        T[n] = 2x * T[n - 1] - T[n - 2]
    end
    return reduce(vcat, [(RAIL_C["CT$a"] * T)' for a in 1:3])
end

const RAIL_MC, RAIL_JC = 0.02, 2.0e-6          # carriage: 20 g, about a 20 mm cube
const RAIL_KT, RAIL_KR = 3.0e5, 50.0           # guide: about 100 times the bar at mid-rail
const RAIL_KD = 3.0e5                           # drive stiffness (slider to carriage)
const RAIL_MS = 0.01                            # slider

"""
The bar clamped at A (as `_fem_clamped`), a carriage (RigidBody3D) on a Prismatic3D at E whose
drive is held by a stiff spring, the slider S on a spring to a velocity source (`v` m/s from
t = 0; 0 holds it at s0). `damp` scales every damper (0: undamped)."""
function _fem_rail(; s0 = 0.08, v = 0.0, zeta = 0.0, damp = 1.0, g_car = 9.81, t_end = 1.0,
        points = 2001, starts = Dict{String,Any}(), fc = 3000.0)
    wc = 2pi * fc
    inertia = vcat(LinearAlgebra.diag(RAIL_C["J0"]), fill(RAIL_C["mass"], 3))
    k = inertia .* wc^2
    b = damp .* 2 .* inertia .* wc
    names_k = ("krx", "kry", "krz", "kx", "ky", "kz")
    names_b = ("brx", "bry", "brz", "bx", "by", "bz")
    zg = damp * 0.5
    body = bg_node("n1", "Body", bg_ref("stdlib:spatial/ModalBody3D");
        params = Dict{String,Any}("zeta" => string(zeta), "g0" => "0.0", "ms" => string(RAIL_MS),
            "s0" => string(s0)), starts = starts)
    body["constants"] = Dict{String,Any}("file" => RAIL_FILE, "stiffening" => 0)
    ks = 100.0
    nodes = Any[
        body,
        bg_node("n2", "Clamp", bg_ref("stdlib:multibond/CSpatial");
            params = Dict{String,Any}(p => string(x) for (p, x) in zip(names_k, k))),
        bg_node("n3", "ClampR", bg_ref("stdlib:multibond/RSpatial");
            params = Dict{String,Any}(p => string(x) for (p, x) in zip(names_b, b))),
        bg_node("n4", "Mount", bg_ref("stdlib:spatial/LocalPose3D")),
        bg_node("n5", "Guide", bg_ref("stdlib:spatial/Prismatic3D");
            params = Dict{String,Any}("kt" => string(RAIL_KT), "kr" => string(RAIL_KR),
                "bt" => string(2zg * sqrt(RAIL_KT * RAIL_MC)), "br" => string(2zg * sqrt(RAIL_KR * RAIL_JC)))),
        bg_node("n6", "Car", bg_ref("stdlib:spatial/RigidBody3D");
            params = Dict{String,Any}("m" => string(RAIL_MC), "J" => "[$RAIL_JC, $RAIL_JC, $RAIL_JC]",
                "g0" => string(g_car))),
        bg_node("n7", "PCar", bg_ref("stdlib:multibond/ComposePose3D")),
        bg_node("n8", "DriveGround", bg_ref("stdlib:translation/Fixed")),
        bg_node("n9", "DriveSpring", bg_ref("stdlib:translation/Spring"); params = Dict{String,Any}("k" => string(RAIL_KD))),
        bg_node("n10", "DriveDamper", bg_ref("stdlib:translation/Damper");
            params = Dict{String,Any}("d" => string(2zg * sqrt(RAIL_KD * RAIL_MC)))),
        bg_node("n11", "Feed", bg_ref("stdlib:translation/VelocitySource"); params = Dict{String,Any}("v" => string(v))),
        bg_node("n12", "One", bg_ref("stdlib:sources/Constant"); params = Dict{String,Any}("value" => "1.0")),
        bg_node("n13", "SlideSpring", bg_ref("stdlib:translation/Spring"); params = Dict{String,Any}("k" => string(ks))),
        bg_node("n14", "SlideDamper", bg_ref("stdlib:translation/Damper");
            params = Dict{String,Any}("d" => string(2zg * sqrt(ks * (RAIL_MS + RAIL_MC))))),
    ]
    conns = Any[
        bg_conn("c1", "bond", "n1", "A", "n2", "p"),
        bg_conn("c2", "bond", "n1", "A", "n3", "p"),
        bg_conn("c3", "signal", "n4", "g", "n1", "gA"),
        bg_conn("c4", "bond", "n5", "parent", "n1", "E"),
        bg_conn("c5", "bond", "n5", "child", "n6", "p"),
        bg_conn("c6", "signal", "n1", "poseE", "n7", "gp"),
        bg_conn("c7", "signal", "n5", "pose", "n7", "gl"),
        bg_conn("c8", "signal", "n7", "g", "n6", "g"),
        bg_conn("c9", "wire", "n8", "a", "n9", "a"),
        bg_conn("c10", "wire", "n9", "b", "n5", "drive"),
        bg_conn("c11", "wire", "n8", "a", "n10", "a"),
        bg_conn("c12", "wire", "n10", "b", "n5", "drive"),
        bg_conn("c13", "signal", "n12", "y", "n11", "u"),
        bg_conn("c14", "wire", "n11", "a", "n13", "a"),
        bg_conn("c15", "bond", "n13", "b", "n1", "S"),
        bg_conn("c16", "wire", "n11", "a", "n14", "a"),
        bg_conn("c17", "bond", "n14", "b", "n1", "S"),
    ]
    return bg_model("FemRail", nodes, conns; t_end = t_end, points = points, solver = "Rodas5P",
        reltol = 1e-9, abstol = 1e-13)
end

@testset "FEM flexible body with a rail (ModalBody3D E, S)" begin
    @testset "loader: rail tables" begin
        data = BGSim.load_modal_body(FEM_FX, Dict{String,Any}("file" => RAIL_FILE))
        @test first.(data)[1:6] == ["nm", "stiffening", "ns", "nh", "nr", "nc"]
        @test RAIL_C["nr"] == 1 && RAIL_C["nc"] == RAIL_DATA["rail"]["chebyshev"]
        @test size(RAIL_C["CT1"]) == (RAIL_NM, RAIL_C["nc"]) && size(RAIL_C["CR3"]) == (RAIL_NM, RAIL_C["nc"])
        @test RAIL_C["RL"] ≈ 0.16 && RAIL_C["XR"] ≈ [0.02, 0.0, 0.005]
        @test RAIL_C["RR"][:, 3] ≈ [1.0, 0.0, 0.0]               # z of the rail frame along the bar
        # a file without a rail: nr = 0, the ports carry no flow
        lb = Dict(BGSim.load_modal_body(FEM_FX, Dict{String,Any}("file" => "lbar.modal.json")))
        @test lb["nr"] == 0 && all(iszero, lb["CT1"])
        v = RAIL_DATA["validation"]["rail"]
        mid = [c for c in v["cases"] if c["fraction"] == 0.5]
        @test all(c -> abs(c["rel_error"]) < 1e-2, mid)           # the load-mode station
    end

    @testset "statics: the carriage's weight at s, kk q = PT(s)' F" begin
        for s0 in (0.08, 0.13)
            cols, res, _ = bg_run(_fem_rail(s0 = s0, zeta = 0.7, t_end = 1.5, points = 301); project_dir = FEM_FX)
            @test res.status == "done"
            q = [cols["Body/eta[$k]"][end] for k in 1:RAIL_NM]
            F = [0.0, 0.0, -RAIL_MC * 9.81]
            qs = (_rail_pt(s0)' * F) ./ Float64.(RAIL_C["kk"])
            @test q ≈ qs rtol = 5e-3
            # the deformed rail slopes under the carriage, so its weight has a small component
            # along the rail that the slide spring (100 N/m) takes: m g slope / k, tens of um
            @test cols["Body/s"][end] ≈ s0 atol = 1e-4
            # poseE is the deformed rail frame: its height is the sag under the carriage
            sag = (_rail_pt(s0) * qs)[3]
            @test cols["Body/poseE[7]"][end] - 0.005 ≈ sag rtol = 1e-2
            @test sag < -2e-4
        end
    end

    @testset "the carriage rides the deformed rail" begin
        # from s = 20 mm to 140 mm at 50 mm/s under its own weight: the bar sags under it
        # (0.2 to 0.7 mm); the guide's transverse deflection stays at the bearing's (F / kt)
        cols, res, _ = bg_run(_fem_rail(s0 = 0.02, v = 0.05, zeta = 0.3, t_end = 2.4, points = 1201); project_dir = FEM_FX)
        @test res.status == "done"
        t = cols["time"]
        @test cols["Body/s"][end] ≈ 0.02 + 0.05 * 2.4 atol = 2e-3
        sag = maximum(abs.(cols["Body/poseE[7]"] .- 0.005))
        @test sag > 3e-4
        dl = maximum(maximum(abs.(cols["Guide/dlin[$i]"])) for i in 1:2)
        @test dl < 0.02 * sag
        @test dl < 5 * RAIL_MC * 9.81 / RAIL_KT
    end

    @testset "energy: undamped bar, slider, carriage and springs" begin
        cols, res, _ = bg_run(_fem_rail(s0 = 0.04, v = 0.0, damp = 0.0, t_end = 0.6, points = 1201,
            starts = Dict{String,Any}("core/psl" => string(RAIL_MS * 0.5))); project_dir = FEM_FX)
        @test res.status == "done"
        n = length(cols["time"])
        kc = vcat(LinearAlgebra.diag(RAIL_C["J0"]), fill(RAIL_C["mass"], 3)) .* (2pi * 3000.0)^2
        Ec = [0.5 * sum(kc[i] * cols["Clamp/$c"][j]^2 for (i, c) in enumerate(("qrx", "qry", "qrz", "qx", "qy", "qz")))
              for j in 1:n]
        Ecar = [0.5 * sum(cols["Car/flow/y[$i]"][j] * cols["Car/inertia/Pm[$i]"][j] for i in 1:6) +
                RAIL_MC * 9.81 * cols["PCar/g[7]"][j] for j in 1:n]
        Eg = [0.5 * RAIL_KR * sum(cols["Guide/dang[$i]"][j]^2 for i in 1:3) +
              0.5 * RAIL_KT * sum(cols["Guide/dlin[$i]"][j]^2 for i in 1:2) for j in 1:n]
        Es = 0.5 * RAIL_KD .* cols["DriveSpring/x"] .^ 2 .+ 0.5 * 100.0 .* cols["SlideSpring/x"] .^ 2
        H = cols["Body/Ek"] .+ cols["Body/Ee"] .+ Ecar .+ Eg .+ Es .+ Ec
        scale = maximum(abs, cols["Body/Ek"] .+ cols["Body/Ee"])
        @test scale > 1e-5
        @test maximum(abs.(H .- H[1])) < 1e-3 * scale
        @test maximum(cols["Body/s"]) > 0.04 + 1e-3               # it slid
    end
end
