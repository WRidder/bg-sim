# D-MB7 experiment: the rigid spatial revolute joint `stdlib:spatial/Revolute3DRigid` (hard
# velocity constraints, Lagrange-multiplier reactions) reduced by `mtkcompile`'s index
# reduction to near-minimal coordinates (plan/MULTIBOND_PLAN.md, "Rigid joints through index
# reduction").
#
# What is checked, on the real pipeline (`parse_model -> flatten -> simulate`):
#   * a single and a non-planar double 3D pendulum compile to exactly two differential states
#     per joint (the joint angle and the joint rate: `Joint/qdot` is kept by the `state =
#     :prefer` priority), with every body twist and reaction algebraic;
#   * both agree with the independent rigid recursive Newton-Euler / RK4 of
#     `test_mech_spatial.jl` and conserve the energy;
#   * the compliant `Revolute3D` at k = 1e8 converges to the rigid joint, with and without a
#     drive torque (the drive sign convention is the compliant joint's);
#   * the conservative compile (W201 => `allow_parameter = false`, priorities) survives a cache
#     hit (the rebuilt initialization).
using Test
using BGSim
import BGSim.IR
import BGSim.Compile
using LinearAlgebra
import ModelingToolkit

if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using .BondGraphGolden

if !isdefined(@__MODULE__, :_msp_double)
    # the helpers (rigs and the RNE reference) of test_mech_spatial.jl, without its testsets
    let src = read(joinpath(@__DIR__, "test_mech_spatial.jl"), String)
        cut = findfirst("@testset \"J-MB9 spatial body", src)
        include_string(@__MODULE__, src[1:(first(cut) - 1)], "test_mech_spatial.jl (helpers)")
    end
end

const _RSP_JOINT = "stdlib:spatial/Revolute3DRigid"

"""Swap every compliant `Revolute3D` of a document for the rigid joint (drop the held-direction
parameters and the deflection starts)."""
function _rsp_rigidify!(doc)
    for n in doc["diagram"]["nodes"]
        b = n["block"]
        if b isa AbstractDict && get(b, "ref", "") == "stdlib:spatial/Revolute3D"
            b["ref"] = _RSP_JOINT
            for k in ("kr", "kt", "br", "bt")
                delete!(n["params"], k)
            end
            n["starts"] = Dict{String,Any}()
        end
    end
    return doc
end

function _rsp_structure(doc; t_end)
    flat = Compile.flatten(IR.parse_model(doc))
    lowered = BGSim.lower_model(flat; t_start = 0.0, t_end = t_end)
    sys = lowered.model.system
    diffv = sort(string.(collect(ModelingToolkit.collect_differential_variables(sys))))
    return flat, diffv, length(ModelingToolkit.unknowns(sys))
end

@testset "D-MB7 rigid spatial revolute (index reduction)" begin
    @testset "catalog: the rigid joint loads clean and balanced" begin
        block = only(b for b in BGSim.Library.load_stdlib() if b.ref == _RSP_JOINT)
        @test !BGSim.Library.has_errors(block)
    end

    @testset "single pendulum: 2 states, RNE reference, energy" begin
        q0 = 0.6
        doc = _rsp_rigidify!(_msp_pendulum(q0 = q0, deflect = false, t_end = 2.0, points = 201))
        BGSim.clear_compile_cache!()
        flat, diffv, nunk = _rsp_structure(doc; t_end = 2.0)
        @test any(d -> d.code == "W201", flat.diagnostics)      # derivative causality, by design
        @test length(diffv) == 2
        @test any(n -> occursin("Joint/qdot", n), diffv)
        columns, result, _ = bg_run(doc)                          # a cache hit: rebuilt init
        @test result.status == "done"
        ref = _msp_rk4(_msp_pend_chain(), [q0], [0.0], 1.0e-4, 100, 2.0)
        @test maximum(abs(columns["Joint/qout"][i] - ref[i][1]) for i in eachindex(ref)) < 1.0e-8
        @test maximum(abs(columns["Joint/qdout"][i] - ref[i][2]) for i in eachindex(ref)) < 1.0e-7
        ke = _msp_ke(columns, "Body", _MSP_PJ, _MSP_PM)
        E = ke .+ _MSP_G .* _MSP_PM .* columns["C2/g[7]"]
        @test maximum(abs.(E .- E[1])) < 1.0e-8 * maximum(ke)
        # the reactions are the joint wrench of the released rigid chain (the RNE reference's
        # `child.e`, which the compliant joint carries as `kt dl` and `kr dth`)
        kk = 1.0
        d0 = _msp_d0(_msp_pend_chain(), [q0], kk, kk)[1]
        f0 = [columns["Joint/fout[$k]"][1] for k in 1:3]
        m0 = [columns["Joint/mout[$k]"][1] for k in 1:2]
        @test isapprox(f0, d0[2]; rtol = 1.0e-8, atol = 1.0e-10)
        @test isapprox(m0, d0[1]; rtol = 1.0e-8, atol = 1.0e-10)
    end

    @testset "non-planar double pendulum: 4 states, RNE reference, energy" begin
        q1, q2 = 0.4, 0.6
        doc = _rsp_rigidify!(_msp_double(1.0e7; q1 = q1, q2 = q2, t_end = 1.5, points = 151))
        flat, diffv, nunk = _rsp_structure(doc; t_end = 1.5)
        @test length(diffv) == 4
        @test count(n -> occursin("/qdot", n), diffv) == 2
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        ref = _msp_rk4(_msp_dp_chain(), [q1, q2], [0.0, 0.0], 1.0e-4, 100, 1.5)
        for (j, name) in enumerate(("J1", "J2"))
            @test maximum(abs(columns["$name/qout"][i] - ref[i][j]) for i in eachindex(ref)) < 1.0e-8
            @test maximum(abs(columns["$name/qdout"][i] - ref[i][2 + j]) for i in eachindex(ref)) < 1.0e-7
        end
        p = _MSP_DP
        ke = _msp_ke(columns, "B1", p.J1, p.m1) .+ _msp_ke(columns, "B2", p.J2, p.m2)
        E = ke .+ _MSP_G .* (p.m1 .* columns["C2/g[7]"] .+ p.m2 .* columns["C5/g[7]"])
        @test maximum(abs.(E .- E[1])) < 1.0e-8 * maximum(ke)
    end

    # D-EX13: the index-reduced DAE keeps every body twist and reaction algebraic, and MTK's
    # order of the algebraic equations leaves zeros on the diagonal of W = M - hγJ. The row
    # matching gives every algebraic row a structural pivot, so the static sparse LU passes
    # its check (no W211), and the C code follows the simulation.
    @testset "the rigid double pendulum exports with the row-matched sparse LU" begin
        q1, q2 = 0.4, 0.6
        doc = _rsp_rigidify!(_msp_double(1.0e7; q1 = q1, q2 = q2, t_end = 0.5, points = 51))
        flat = Compile.flatten(IR.parse_model(doc))
        X = BGSim.Export
        dir = mktempdir()
        r = X.export_model(flat, dir; settings = X.ExportSettings(t_end = 0.5, step = 1.0e-2,
            dt = 1.0e-3, method = :rodas4p, sparse_threshold = 4, expose_all = true))
        @test r.ok
        la = r.report["linearAlgebra"]
        @test r.report["algebraic"] > 0
        @test !la["matching"]["structuralDiagonal"]           # the identity has zero pivots
        @test la["matching"]["used"] && la["matching"]["rowsPermuted"] > 0
        @test la["linearSolver"] == "sparse" && la["pivotCheck"]["ok"]
        @test !any(d -> d.code == "W211", r.diagnostics)
        @test la["luFlops"] < la["denseLuFlops"] / 4
        cc = Sys.which("gcc")
        if cc === nothing
            @info "rigid export: no gcc on PATH, the C run is skipped"
        else
            src = joinpath(dir, "sources")
            write(joinpath(dir, "driver.c"), """
                #include <stdio.h>
                #include <stdlib.h>
                #include "model.h"
                static bg_model g_m;
                int main(int argc, char **argv) {
                    long n = argc > 1 ? atol(argv[1]) : 0;
                    bg_reset(&g_m, 0.0);
                    for (long k = 0; k < n; ++k)
                        if (bg_step(&g_m) != 0) { printf("step failed at %ld\\n", k); return 3; }
                    bg_update_outputs(&g_m);
                    for (int i = 0; i < BG_NY; ++i) printf("%.17g\\n", g_m.y[i]);
                    return 0;
                }
                """)
            exe = joinpath(dir, Sys.iswindows() ? "driver.exe" : "driver")
            files = [joinpath(src, f) for f in ("model.c", "bg_solver.c")]
            @test success(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -c $(files[1]) -I $src -o $(joinpath(dir, "m.o"))`)
            @test success(`$cc -std=c99 -O2 -I $src $(joinpath(dir, "driver.c")) $files -o $exe -lm`)
            y = parse.(Float64, split(strip(read(`$exe 500`, String))))
            names = r.report["locals"]
            columns, result, _ = bg_run(doc)
            @test result.status == "done"
            for name in ("J1/qout", "J2/qout", "J1/qdout", "J2/qdout")
                k = findfirst(==(name), names)
                @test k !== nothing
                # Rodas4P at 1 ms against the simulation's adaptive solve
                @test abs(y[k] - columns[name][end]) < 1.0e-5 * max(1.0, abs(columns[name][end]))
            end
        end
    end

    @testset "the compliant joint converges to the rigid one (with a drive torque)" begin
        for tau in (0.0, 1.5)
            efforts = Dict("drive" => tau)
            comp = _msp_pendulum(q0 = 0.3, kt = 1.0e8, kr = 1.0e8, t_end = 1.0, points = 101,
                efforts = efforts)
            rigid = _rsp_rigidify!(_msp_pendulum(q0 = 0.3, deflect = false, t_end = 1.0,
                points = 101, efforts = efforts))
            cc, cr, _ = bg_run(comp)
            rc, rr, _ = bg_run(rigid)
            @test cr.status == "done"
            @test rr.status == "done"
            @test maximum(abs.(cc["Joint/qout"] .- rc["Joint/qout"])) < 1.0e-5
            tau != 0.0 && @test abs(rc["Joint/qout"][end] - cc["Joint/qout"][end]) < 1.0e-5
        end
    end
end
