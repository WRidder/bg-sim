# FEM flexible bodies: `stdlib:spatial/ModalBody3D` with a reduced-model file of
# julia/BGSimFEM (format `bgsim.modal-body`, docs/modal-body-format.md) on the real pipeline.
#
# The fixture `fixtures/fem/lbar.modal.json` is a small L of a soft test material (E = 70 MPa,
# modes 14 Hz to 1.4 kHz) with three interfaces (A root, B leg end, C on the arm), reduced by
# Craig-Bampton to 1 fixed-interface + 12 constraint modes; regenerate it with
# `julia --project=julia/BGSimFEM julia/BGSimFEM/bin/bgsim-fem.jl test/fixtures/fem/lbar.fem.json`.
#
#   * the loader: sizes, symmetric mass properties, the invariant identity
#     E_xx + E_yy + E_zz = diag(mk), E108 for a missing or foreign file, the compile key follows
#     the file content;
#   * energy: a free body spinning and vibrating conserves T + V without damping, with and
#     without the geometric-stiffening terms; a pendulum under gravity conserves T + V + U_g;
#   * the clamped body vibrates at the file's modal frequency;
#   * statics: a wrench at interfaces B and C gives kk q = PT' F + PR' M exactly (the
#     constraint modes), and poseB is the deformed interface.
using Test
using BGSim
using LinearAlgebra
import JSON3

if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using .BondGraphGolden
import BGSim.IR
import BGSim.Compile

const FEM_FX = joinpath(@__DIR__, "fixtures", "fem")
const FEM_DATA = JSON3.read(read(joinpath(FEM_FX, "lbar.modal.json"), String))
const FEM_NM = Int(FEM_DATA.nm)

_femv(v) = "[" * join(string.(Float64.(v)), ", ") * "]"
_fem_errors(flat) = [d for d in flat.diagnostics if d.severity == "error"]
_fem_drift(E) = (maximum(E) - minimum(E)) / maximum(abs.(E))
_fem_mat(rows) = permutedims(reduce(hcat, [Float64.(collect(r)) for r in rows]))

function _fem_body(id, name; file = "lbar.modal.json", stiffening = 1, zeta = 0.0, g0 = 0.0,
        starts = Dict{String,Any}())
    node = bg_node(id, name, bg_ref("stdlib:spatial/ModalBody3D");
        params = Dict{String,Any}("zeta" => string(zeta), "g0" => string(g0)), starts = starts)
    node["constants"] = Dict{String,Any}("file" => file, "stiffening" => stiffening)
    return node
end

"""Mean frequency (Hz) of a signal from its upward mean crossings."""
function _fem_freq(t, x)
    xm = x .- (maximum(x) + minimum(x)) / 2
    cr = Float64[]
    for i in 1:(length(x) - 1)
        if xm[i] < 0 && xm[i + 1] >= 0
            push!(cr, t[i] - xm[i] * (t[i + 1] - t[i]) / (xm[i + 1] - xm[i]))
        end
    end
    return (length(cr) - 1) / (cr[end] - cr[1])
end

# ---- rigs ----------------------------------------------------------------------------------

"""A free body, no gravity, no damping: frame momentum and modal displacements at t = 0."""
function _fem_free(; stiffening = 1, t_end = 0.1)
    q0 = zeros(FEM_NM)
    q0[1], q0[2], q0[4] = 2e-3, -1e-3, 5e-4
    P0 = [2e-4, -1e-4, 3e-4, 0.01, 0.0, -0.005]
    body = _fem_body("n1", "Body"; stiffening = stiffening,
        starts = Dict{String,Any}("core/q" => _femv(q0), "core/P" => _femv(P0)))
    nodes = Any[body, bg_node("n2", "Mount", bg_ref("stdlib:spatial/LocalPose3D"))]
    conns = Any[bg_conn("c1", "signal", "n2", "g", "n1", "gA")]
    return bg_model("FemFree", nodes, conns; t_end = t_end, points = 1001, reltol = 1e-10, abstol = 1e-13)
end

"""A pendulum: interface A on a compliant revolute (axis world y), released horizontal."""
function _fem_pendulum(; t_end = 0.3)
    s2 = sqrt(0.5)
    kk = 1.0e6
    nodes = Any[
        bg_node("n1", "World", bg_ref("stdlib:multibond/GroundSpatial")),
        bg_node("n2", "Axis", bg_ref("stdlib:multibond/FixedTransform3DNeutral");
            params = Dict{String,Any}("qw" => string(s2), "qx" => string(-s2))),
        bg_node("n3", "Hinge", bg_ref("stdlib:spatial/Revolute3D");
            params = Dict{String,Any}("kt" => string(kk), "kr" => string(kk))),
        _fem_body("n4", "Body"; g0 = 9.81),
        bg_node("n5", "AxisPose", bg_ref("stdlib:spatial/LocalPose3D");
            params = Dict{String,Any}("qw" => string(s2), "qx" => string(s2))),
        bg_node("n6", "PoseA", bg_ref("stdlib:multibond/ComposePose3D")),
        bg_node("n7", "Free", bg_ref("stdlib:bondgraph/Se"); params = Dict{String,Any}("e" => "0.0")),
    ]
    conns = Any[
        bg_conn("c1", "bond", "n1", "p", "n2", "b"),
        bg_conn("c2", "bond", "n2", "a", "n3", "parent"),
        bg_conn("c3", "bond", "n3", "child", "n4", "A"),
        bg_conn("c4", "signal", "n5", "g", "n6", "gp"),
        bg_conn("c5", "signal", "n3", "pose", "n6", "gl"),
        bg_conn("c6", "signal", "n6", "g", "n4", "gA"),
        bg_conn("c7", "bond", "n7", "p", "n3", "drive"),
    ]
    return bg_model("FemPendulum", nodes, conns; t_end = t_end, points = 1201, reltol = 1e-10, abstol = 1e-13)
end

"""Clamped at A (stiff CSpatial + RSpatial), with an optional constant wrench at B and C."""
function _fem_clamped(; q0 = zeros(FEM_NM), wB = zeros(6), wC = zeros(6), zeta = 0.0,
        stiffening = 1, t_end = 0.5, points = 2001)
    k, b = 1.0e9, 1.0e3
    nodes = Any[
        _fem_body("n1", "Body"; zeta = zeta, stiffening = stiffening,
            starts = Dict{String,Any}("core/q" => _femv(q0))),
        bg_node("n2", "Clamp", bg_ref("stdlib:multibond/CSpatial");
            params = Dict{String,Any}(p => string(k) for p in ("krx", "kry", "krz", "kx", "ky", "kz"))),
        bg_node("n3", "ClampR", bg_ref("stdlib:multibond/RSpatial");
            params = Dict{String,Any}(p => string(b) for p in ("brx", "bry", "brz", "bx", "by", "bz"))),
        bg_node("n5", "Mount", bg_ref("stdlib:spatial/LocalPose3D")),
    ]
    conns = Any[
        bg_conn("c1", "bond", "n1", "A", "n2", "p"),
        bg_conn("c2", "bond", "n1", "A", "n3", "p"),
        bg_conn("c4", "signal", "n5", "g", "n1", "gA"),
    ]
    for (tag, port, w) in (("B", "B", wB), ("C", "C", wC))
        any(!iszero, w) || continue
        push!(nodes, bg_node("L$tag", "Load$tag", bg_ref("stdlib:multibond/ExternalWrenchSpatial")))
        push!(conns, bg_conn("cl$tag", "bond", "L$tag", "p", "n1", port))
        for (i, (p, v)) in enumerate(zip(("tx", "ty", "tz", "fx", "fy", "fz"), w))
            push!(nodes, bg_node("k$tag$i", "W$tag$i", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => string(v))))
            push!(conns, bg_conn("w$tag$i", "signal", "k$tag$i", "y", "L$tag", p))
        end
    end
    return bg_model("FemClamped", nodes, conns; t_end = t_end, points = points, reltol = 1e-9, abstol = 1e-13)
end

# ---- tests ---------------------------------------------------------------------------------

@testset "FEM flexible body (ModalBody3D)" begin
    @testset "reduced-model file: loader, invariants, diagnostics, compile key" begin
        data = BGSim.load_modal_body(FEM_FX, Dict{String,Any}("file" => "lbar.modal.json"))
        d = Dict(data)
        @test first.(data)[1:3] == ["nm", "ni", "stiffening"]         # sizes first
        @test d["nm"] == FEM_NM && d["ni"] == 3 && d["stiffening"] == 1
        @test size(d["St"]) == (3, FEM_NM) && size(d["J1"]) == (6, FEM_NM)
        @test size(d["PT"]) == (12, FEM_NM) && size(d["Gd3"]) == (FEM_NM, FEM_NM)
        @test d["J0"] ≈ d["J0"]'
        @test d["mass"] ≈ 2700.0 * (0.08 * 0.012 * 0.006 + 0.006 * 0.012 * 0.04) rtol = 1e-9
        @test d["Exx"] + d["Eyy"] + d["Ezz"] ≈ Diagonal(d["mk"]) atol = 1e-9 * maximum(d["mk"])
        @test all(iszero, d["Gd1"])                                     # no interface D
        @test all(iszero, d["PT"][10:12, :]) && d["QP"][:, 4] == [1.0, 0, 0, 0]
        off = Dict(BGSim.load_modal_body(FEM_FX, Dict{String,Any}("file" => "lbar.modal.json", "stiffening" => 0)))
        @test off["stiffening"] == 0 && all(iszero, off["Gt1"])

        flat_of(dir, file) = Compile.flatten(IR.parse_model(bg_model("FemKey",
            Any[_fem_body("n1", "Body"; file = file), bg_node("n2", "Mount", bg_ref("stdlib:spatial/LocalPose3D"))],
            Any[bg_conn("c1", "signal", "n2", "g", "n1", "gA")])); project_dir = dir)
        missing_ = flat_of(FEM_FX, "nothere.modal.json")
        @test any(d -> d.code == "E108" && occursin("does not exist", d.message), missing_.diagnostics)
        dir = mktempdir()
        write(joinpath(dir, "bad.modal.json"), "{\"format\": \"something-else\"}")
        bad = flat_of(dir, "bad.modal.json")
        @test any(d -> d.code == "E108" && occursin("not a reduced-model file", d.message), bad.diagnostics)
        # the constants are folded literals: another file content is another compiled model
        cp(joinpath(FEM_FX, "lbar.modal.json"), joinpath(dir, "a.modal.json"))
        f1 = flat_of(dir, "a.modal.json")
        @test isempty(_fem_errors(f1))
        doc = JSON3.read(read(joinpath(dir, "a.modal.json"), String), Dict{String,Any})
        doc["mass"] *= 1.01
        write(joinpath(dir, "a.modal.json"), JSON3.write(doc))
        f2 = flat_of(dir, "a.modal.json")
        @test BGSim.compile_key(f1) != BGSim.compile_key(f2)
    end

    @testset "free body: T + V conserved, observables, open interfaces" begin
        for stiffening in (1, 0)
            cols, res, flat = bg_run(_fem_free(stiffening = stiffening); project_dir = FEM_FX)
            @test res.status == "done"
            @test !any(d -> d.code == "E101", flat.diagnostics)          # B, C, D open
            E = cols["Body/Ek"] .+ cols["Body/Ee"]
            @test _fem_drift(E) < 1e-6
            @test maximum(cols["Body/Ee"]) > 1e-3 * maximum(E)           # it really vibrates
            @test maximum(abs.(cols["Body/V[3]"])) > 1.0                  # and spins
            for k in 1:FEM_NM
                @test cols["Body/f[$k]"][1] ≈ FEM_DATA.frequency_hz[k] rtol = 1e-9
            end
            @test haskey(cols, "Body/poseC[7]") && haskey(cols, "Body/eta[$FEM_NM]")
        end
    end

    @testset "pendulum under gravity: T + V + U_g conserved" begin
        cols, res, _ = bg_run(_fem_pendulum(); project_dir = FEM_FX)
        @test res.status == "done"
        E = cols["Body/Ek"] .+ cols["Body/Ee"] .+ cols["Body/Eg"]
        swing = maximum(cols["Body/Ek"])
        @test swing > 1e-3
        @test maximum(abs.(cols["Body/eta[1]"])) > 1e-5
        @test (maximum(E) - minimum(E)) / swing < 1e-5
    end

    @testset "clamped body vibrates at the modal frequency" begin
        q0 = zeros(FEM_NM)
        q0[1] = 1e-4
        cols, res, _ = bg_run(_fem_clamped(q0 = q0, t_end = 0.5); project_dir = FEM_FX)
        @test res.status == "done"
        @test _fem_freq(cols["time"], cols["Body/eta[1]"]) ≈ FEM_DATA.frequency_hz[1] rtol = 2e-3
        @test maximum(abs.(cols["Body/eta[2]"])) < 1e-2 * 1e-4         # the modes decouple
    end

    @testset "statics: wrenches at B and C, the constraint modes are exact" begin
        wB = [0.0, 1e-5, 0.0, 0.002, -0.001, 0.003]   # (torque; force) at B
        wC = [2e-5, 0.0, 0.0, 0.0, 0.0, -0.002]
        cols, res, _ = bg_run(_fem_clamped(wB = wB, wC = wC, zeta = 0.7, stiffening = 0, t_end = 2.0,
            points = 201); project_dir = FEM_FX)
        @test res.status == "done"
        q = [cols["Body/eta[$k]"][end] for k in 1:FEM_NM]
        Q = zeros(FEM_NM)
        for (j, w) in ((2, wB), (3, wC))
            f = FEM_DATA.interfaces[j]
            Q .+= _fem_mat(f.translation)' * w[4:6] .+ _fem_mat(f.rotation)' * w[1:3]
        end
        qs = Q ./ Float64.(FEM_DATA.modal_stiffness)
        @test q ≈ qs rtol = 2e-3
        # poseB is the deformed interface B (A at the world origin, R = world)
        uB = _fem_mat(FEM_DATA.interfaces[2].translation) * qs
        xB = Float64.(collect(FEM_DATA.interfaces[2].position))
        @test [cols["Body/poseB[$(4 + a)]"][end] for a in 1:3] ≈ xB .+ uB rtol = 1e-3
        @test norm(uB) > 1e-4                                            # a visible deflection
    end
end
