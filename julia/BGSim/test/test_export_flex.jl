# The flexible beams in the C export (plan/EXPORT_PLAN.md): `stdlib:spatial/FlexibleBeam3D`
# (2 + 2 bending modes and a torsion mode, spinning and vibrating freely) and
# `stdlib:planar/FlexibleBeam2D` (3 bending modes, spinning and vibrating under gravity, which
# runs the G1 foreshortening field). Each rig exports with RK4, builds with
# -std=c99 -Wall -Wextra -Werror, runs, matches the Julia simulation at the common grid times,
# repeats bit for bit after a reset, and its FMU does not allocate after instantiate.
#
# The modal frequencies decide the step of an explicit method: RK4 is stable for
# dt * omega_max < 2.83 (its stability bound on the imaginary axis), and its phase error is
# about (dt * omega)^5 / 120 per step. A free beam vibrates at its free-free frequencies, which
# lie above the clamped-free ones of its basis: the steel rod's first free torsion mode is
# pi c / L = 1.0e4 rad/s (twice the clamped-free 5.0e3 rad/s), its highest planar bending mode
# about 1.6e3 rad/s. The steps below keep dt * omega_max at 0.05 (3D) and 0.04 (2D), so the
# C run follows the adaptive simulation to the 1e-4 tolerance below; at dt * omega = 1 the
# run is stable but the torsion phase is lost within 40 periods.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using Test
using BGSim
using .BondGraphGolden
import BGSim.IR
import BGSim.Compile

if !isdefined(@__MODULE__, :_fb_free3)
    # the rigs of test_flex_beam.jl, without its testsets
    let src = read(joinpath(@__DIR__, "test_flex_beam.jl"), String)
        cut = findfirst("@testset \"flexible bodies: beam dynamics\"", src)
        include_string(@__MODULE__, src[1:(first(cut) - 1)], "test_flex_beam.jl (rigs)")
    end
end
if !isdefined(@__MODULE__, :_fem_free)
    # the rigs of test_fem_body.jl (the FEM flexible body), without its testsets
    let src = read(joinpath(@__DIR__, "test_fem_body.jl"), String)
        cut = findfirst("@testset \"FEM flexible body (ModalBody3D)\"", src)
        include_string(@__MODULE__, src[1:(first(cut) - 1)], "test_fem_body.jl (rigs)")
    end
end

const _EXF = BGSim.Export

const _EXF_RUNNER = raw"""
#include <stdio.h>
#include <stdlib.h>
#include "model.h"
static bg_model m;
int main(int argc, char **argv) {
    long n = argc > 1 ? atol(argv[1]) : 100;
    long stride = argc > 2 ? atol(argv[2]) : 1;
    bg_reset(&m, 0.0);
    for (long k = 0; k <= n; ++k) {
        if (k > 0 && bg_step(&m) != 0) return 2;
        if (k % stride != 0) continue;
        bg_update_outputs(&m);
        printf("%.17g", m.t);
        for (int i = 0; i < BG_NX; ++i) printf(" %.17g", m.x[i]);
        for (int i = 0; i < BG_NY; ++i) printf(" %.17g", m.y[i]);
        printf("\n");
    }
    return 0;
}
"""

function _exf_files(src; fmu = false)
    names = ["model.c", "bg_solver.c", "bg_intrinsics.c", "bg_mech.c"]
    fmu && push!(names, "fmi2_cs.c")
    return [joinpath(src, f) for f in names if isfile(joinpath(src, f))]
end

function _exf_run_c(cc, dir, report, n, stride)
    src = joinpath(dir, "sources")
    runner = joinpath(dir, "runner.c")
    write(runner, _EXF_RUNNER)
    exe = joinpath(dir, Sys.iswindows() ? "runner.exe" : "runner")
    run(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -I $src $(_exf_files(src)) $runner -o $exe -lm`)
    rows = [parse.(Float64, split(l)) for l in eachline(`$exe $n $stride`)]
    model_c = read(joinpath(src, "model.c"), String)
    xnames = [String(m.captures[2]) for m in eachmatch(r"/\* x\[(\d+)\] = (\S+) \*/", model_c)]
    ynames = vcat([o["name"] for o in report["outputs"]], String.(report["locals"]))
    return permutedims(reduce(hcat, rows)), xnames, ynames
end

"""Export `doc` with RK4 at `dt`, build and run it for `t_end`, and compare every C state and
local that the simulation also recorded at every `stride`-th step (the C runner prints only
those), relative to the signal's range. Returns name => error (or nothing without gcc)."""
function _exf_check(doc; dt, t_end, stride, project_dir = nothing)
    flat = Compile.flatten(IR.parse_model(doc); project_dir = project_dir)
    @test isempty([d for d in flat.diagnostics if d.severity == "error"])
    dir = mktempdir()
    r = _EXF.export_model(flat, dir;
        settings = _EXF.ExportSettings(t_end = t_end, step = dt, dt = dt, method = :rk4, expose_all = true))
    @test r.ok
    errors = [d for d in r.diagnostics if d.severity == "error"]
    @test isempty(errors)
    isempty(errors) || foreach(d -> @info("export error", d.code, d.message), errors)
    r.ok || return nothing
    cc = Sys.which("gcc")
    if cc === nothing
        @info "flex export: no gcc on PATH, the compile-and-run checks are skipped"
        return nothing
    end
    n = round(Int, t_end / dt)
    rows, xn, yn = _exf_run_c(cc, dir, r.report, n, stride)
    @test size(rows, 1) == n ÷ stride + 1
    @test rows[:, 1] ≈ (0:stride:n) .* dt
    @test all(isfinite, rows)
    columns, result, _ = bg_run(doc; project_dir = project_dir)
    @test result.status == "done"
    t = rows[:, 1]
    errs = Dict{String,Float64}()
    ks = 1:size(rows, 1)
    sims = Dict{String,Vector{Float64}}()
    for name in vcat(xn, yn)
        haskey(columns, name) && (sims[name] = [bg_value(columns, name, round(t[k] / dt) * dt) for k in ks])
    end
    # A matrix entry is scaled by the largest entry of its matrix: the off-diagonal entries of
    # the inverse rotational inertia of a straight beam are roundoff (1e-10 against 7e5).
    matrix(name) = replace(name, r"\[\d+,\d+\]$" => "")
    mscale = Dict{String,Float64}()
    for (name, sim) in sims
        mscale[matrix(name)] = max(get(mscale, matrix(name), 0.0), maximum(abs, sim))
    end
    for (j, name) in enumerate(vcat(xn, yn))
        haskey(sims, name) || continue
        sim = sims[name]
        scale = max(maximum(abs, sim), 1e-6 * mscale[matrix(name)], 1e-9)
        errs[name] = maximum(abs(rows[k, 1 + j] - s) for (k, s) in zip(ks, sim)) / scale
    end
    if get(ENV, "BG_EXF_DEBUG", "") != ""
        println("states: ", join(xn, ", "))
        for (k, v) in sort(collect(errs); by = last)
            println(rpad(k, 28), " ", v)
        end
    end
    # a second run (bg_reset, as fmi2Reset) repeats the first bit for bit
    rows2, _, _ = _exf_run_c(cc, dir, r.report, n, stride)
    @test rows2 == rows
    src = joinpath(dir, "sources")
    files = _exf_files(src; fmu = true)
    for f in files
        @test success(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -I $src -c $f -o $(joinpath(dir, "x.o"))`)
    end
    harness = joinpath(_EXF.RUNTIME_DIR, "alloc_check.c")
    exe = joinpath(dir, Sys.iswindows() ? "check.exe" : "check")
    @test success(`$cc -std=c11 -O2 -I $src $harness $files -o $exe -lm`)
    out = read(`$exe 1 1000`, String)
    @test occursin("after instantiate 0", out)
    return errs
end

function _exf_assert(errs, prefixes, tol)
    errs === nothing && return
    for prefix in prefixes
        mine = [(k, v) for (k, v) in errs if startswith(k, prefix * "/")]
        @test !isempty(mine)
        worst = isempty(mine) ? 0.0 : maximum(last, mine)
        worst <= tol || @info "flex export vs simulation" prefix worst tol sort(mine; by = last)[end]
        @test worst <= tol
    end
end

@testset "flexible beams in the C export" begin
    @testset "FlexibleBeam3D: free, spinning, bending and twisting (RK4)" begin
        errs = _exf_check(_fb_free3(); dt = 5.0e-6, t_end = 0.05, stride = 200)
        _exf_assert(errs, ("Beam",), 1.0e-4)
        if errs !== nothing
            # the modal coordinates and the observables are among the compared signals
            @test any(k -> startswith(k, "Beam/eta_y"), keys(errs))
            @test any(k -> startswith(k, "Beam/eta_t"), keys(errs))
        end
    end

    @testset "FlexibleBeam2D: free, spinning, under gravity (RK4)" begin
        doc = _fb_free2()
        beam = only(n for n in doc["diagram"]["nodes"] if n["name"] == "Beam")
        beam["params"]["g0"] = "9.81"
        errs = _exf_check(doc; dt = 2.5e-5, t_end = 0.2, stride = 80)
        _exf_assert(errs, ("Beam",), 1.0e-4)
        errs === nothing || @test any(k -> startswith(k, "Beam/eta_y"), keys(errs))
    end

    @testset "ModalBody3D: FEM body from its reduced-model file, free, spinning (RK4)" begin
        # the soft test L of test_fem_body.jl: 13 modes up to 1.4 kHz clamped (about 2 kHz
        # free), so dt * omega_max is about 0.05; the reduced matrices are literals in model.c
        errs = _exf_check(_fem_free(t_end = 0.02); dt = 4.0e-6, t_end = 0.02, stride = 100,
            project_dir = FEM_FX)
        _exf_assert(errs, ("Body",), 1.0e-4)
        errs === nothing || @test any(k -> startswith(k, "Body/eta"), keys(errs))
    end
end
