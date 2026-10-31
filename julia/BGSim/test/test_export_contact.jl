# MovingPlaneContact in the C export (plan/EXPORT_PLAN.md): the clamp rig of the golden test
# (a ball held between two jaw faces on one slide node, the slide force ramped down until the
# ball slides) exported with `expose_all`, compiled with gcc -std=c99 -Wall -Wextra -Werror,
# run, and compared with the Julia simulation: the jaw normal forces, the slide position and the
# ball height. The model is smooth (tanh/sqrt, no kinks) apart from the Ramp's time switch, so
# the fixed-step C solver follows the variable-step reference closely. A second run after
# bg_reset repeats bit for bit, and the FMU does not allocate after instantiate.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :MovingContactRigs)
    include(joinpath(@__DIR__, "golden", "contact", "moving_contact_helpers.jl"))
end
using Test
using BGSim
using .BondGraphGolden
using .MovingContactRigs
import BGSim.IR
import BGSim.Compile

const _EXC = BGSim.Export

const _EXC_RUNNER = raw"""
#include <stdio.h>
#include <stdlib.h>
#include "model.h"
static bg_model m;
int main(int argc, char **argv) {
    long n = argc > 1 ? atol(argv[1]) : 100;
    bg_reset(&m, 0.0);
    for (long k = 0; k <= n; ++k) {
        if (k > 0 && bg_step(&m) != 0) return 2;
        bg_update_outputs(&m);
        printf("%.17g", m.t);
        for (int i = 0; i < BG_NX; ++i) printf(" %.17g", m.x[i]);
        for (int i = 0; i < BG_NY; ++i) printf(" %.17g", m.y[i]);
        printf("\n");
    }
    return 0;
}
"""

function _exc_run_c(cc, dir, report, n)
    src = joinpath(dir, "sources")
    runner = joinpath(dir, "runner.c")
    write(runner, _EXC_RUNNER)
    exe = joinpath(dir, Sys.iswindows() ? "runner.exe" : "runner")
    files = [joinpath(src, f) for f in ("model.c", "bg_solver.c", "bg_intrinsics.c", "bg_mech.c")
             if isfile(joinpath(src, f))]
    run(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -I $src $files $runner -o $exe -lm`)
    rows = [parse.(Float64, split(l)) for l in eachline(`$exe $n`)]
    model_c = read(joinpath(src, "model.c"), String)
    xnames = [String(m.captures[2]) for m in eachmatch(r"/\* x\[(\d+)\] = (\S+) \*/", model_c)]
    ynames = vcat([o["name"] for o in report["outputs"]], String.(report["locals"]))
    return permutedims(reduce(hcat, rows)), xnames, ynames
end

@testset "MovingPlaneContact in the C export" begin
    t_end = 1.5
    doc = mpc_clamp_model(t_end = t_end, points = 1501)
    flat = Compile.flatten(IR.parse_model(doc))
    @test isempty([d for d in flat.diagnostics if d.severity == "error"])

    dir = mktempdir()
    r = _EXC.export_model(flat, dir;
        settings = _EXC.ExportSettings(t_end = t_end, dt = 1e-4, expose_all = true))
    @test r.ok
    @test isempty([d for d in r.diagnostics if d.severity == "error"])

    cc = Sys.which("gcc")
    if cc === nothing
        @info "export: no gcc on PATH, the contact compile-and-run checks are skipped"
    else
        n = round(Int, t_end / 1e-4)
        rows, xn, yn = _exc_run_c(cc, dir, r.report, n)
        @test size(rows, 1) == n + 1
        t = rows[:, 1]
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        col(name) = (j = findfirst(==(name), yn); j === nothing ? nothing : rows[:, 1 + length(xn) + j])
        grid = 1:10:n + 1                                      # the simulation's 1 ms grid
        for (name, tol) in (("JawA/f_n", 2e-3), ("JawB/f_n", 2e-3), ("JawA/delta", 2e-3),
                            ("JawA/slip", 2e-2))
            y = col(name)
            @test y !== nothing
            y === nothing && continue
            scale = maximum(abs.(y))
            # away from the ramp start (a time switch inside a C step)
            err = maximum(abs(y[k] - bg_value(columns, name, t[k])) for k in grid if t[k] < 1.2)
            @test err < tol * scale
        end
        z = col("Pose/g[7]")
        if z !== nothing
            @test maximum(abs(z[k] - bg_value(columns, "Pose/g[7]", t[k])) for k in grid) < 2e-3
        end
        # A second run of the C model (bg_reset, as fmi2Reset) repeats the first bit for bit.
        rows2, _, _ = _exc_run_c(cc, dir, r.report, n)
        @test rows2 == rows

        @testset "builds with -Werror and does not allocate after instantiate" begin
            src = joinpath(dir, "sources")
            files = [joinpath(src, f) for f in ("model.c", "bg_solver.c", "bg_intrinsics.c",
                "bg_mech.c", "fmi2_cs.c") if isfile(joinpath(src, f))]
            for f in files
                @test success(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -I $src -c $f -o $(joinpath(dir, "x.o"))`)
            end
            harness = joinpath(_EXC.RUNTIME_DIR, "alloc_check.c")
            exe = joinpath(dir, Sys.iswindows() ? "check.exe" : "check")
            @test success(`$cc -std=c11 -O2 -I $src $harness $files -o $exe -lm`)
            out = read(`$exe 1 1000`, String)
            @test occursin("after instantiate 0", out)
        end
    end
end
