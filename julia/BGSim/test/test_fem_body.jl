# FEM flexible bodies: `stdlib:spatial/ModalBody3D` with a reduced-model file of
# julia/BGSimFEM (format `bgsim.modal-body`, docs/modal-body-format.md) on the real pipeline.
#
# The fixture and the rigs are in fem_body_rigs.jl.
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
import BGSim.IR
import BGSim.Compile

isdefined(@__MODULE__, :_fem_free) || include(joinpath(@__DIR__, "fem_body_rigs.jl"))

# ---- tests ---------------------------------------------------------------------------------

@testset "FEM flexible body (ModalBody3D)" begin
    @testset "reduced-model file: loader, invariants, diagnostics, compile key" begin
        data = BGSim.load_modal_body(FEM_FX, Dict{String,Any}("file" => "lbar.modal.json"))
        d = Dict(data)
        @test first.(data)[1:2] == ["nm", "stiffening"]               # sizes first
        @test d["nm"] == FEM_NM && !haskey(d, "ni") && d["stiffening"] == 1
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
        @test [cols["Body/poseB[$(4 + a)]"][end] for a in 1:3] .- xB ≈ uB rtol = 5e-3
        @test norm(uB) > 2e-5                                     # 50 um, 0.06 % of the part
    end
end
