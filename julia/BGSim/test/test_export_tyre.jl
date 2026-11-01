# The vehicle tyre and the terrain (stdlib:contact/Tyre, stdlib:contact/TerrainSurface) in the C
# export (plan/EXPORT_PLAN.md): a free wheel (carrier body, Rotor3D, Tyre) rolling down a 25 %
# TerrainSurface plane with a brake torque as an export input. The export builds with
# -std=c99 -Wall -Wextra -Werror, matches the Julia simulation, repeats bit for bit after
# bg_reset and does not allocate after fmi2Instantiate. This is the corner of the `cars`
# example's vehicles (the smooth contact spring, the Magic Formula with its atan/sin, the
# first-order patch deflection and the tangent plane of the height field).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :_ty_kinematic)
    include(joinpath(@__DIR__, "golden", "contact", "tyre_rig.jl"))
end
using Test
using BGSim
using .BondGraphGolden
import BGSim.IR
import BGSim.Compile

const _EXT_RUNNER = raw"""
#include <stdio.h>
#include <stdlib.h>
#include "model.h"
static bg_model m;
int main(int argc, char **argv) {
    long n = argc > 1 ? atol(argv[1]) : 100;
    long sub = argc > 2 ? atol(argv[2]) : 1;
    bg_reset(&m, 0.0);
    for (long k = 0; k <= n * sub; ++k) {
        if (k > 0 && bg_step(&m) != 0) return 2;
        if (k % sub != 0) continue;
        bg_update_outputs(&m);
        printf("%.17g", m.t);
        for (int i = 0; i < BG_NX; ++i) printf(" %.17g", m.x[i]);
        for (int i = 0; i < BG_NY; ++i) printf(" %.17g", m.y[i]);
        printf("\n");
    }
    return 0;
}
"""

function _ext_run_c(cc, dir, report, n)
    sub = Int(report["substeps"])
    src = joinpath(dir, "sources")
    runner = joinpath(dir, "runner.c")
    write(runner, _EXT_RUNNER)
    exe = joinpath(dir, Sys.iswindows() ? "runner.exe" : "runner")
    files = [joinpath(src, f) for f in ("model.c", "bg_solver.c", "bg_intrinsics.c", "bg_mech.c")
             if isfile(joinpath(src, f))]
    run(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -I $src $files $runner -o $exe -lm`)
    rows = [parse.(Float64, split(l)) for l in eachline(`$exe $n $sub`)]
    model_c = read(joinpath(src, "model.c"), String)
    xnames = [String(m.captures[2]) for m in eachmatch(r"/\* x\[(\d+)\] = (\S+) \*/", model_c)]
    ynames = vcat([o["name"] for o in report["outputs"]], String.(report["locals"]))
    return permutedims(reduce(hcat, rows)), xnames, ynames
end

const _EXT_T_END = 1.0

_ext_model() = _ty_wheel(; v = 3.0, slope = 0.25, t_end = _EXT_T_END, points = 101, brake_input = true,
    outputs = (("Fz", "t", "Fz"), ("Fx", "t", "Fx"), ("kappa", "t", "kappa"), ("x", "t", "xc"),
        ("omega", "t", "omega")), name = "TyreExport")

@testset "Tyre and TerrainSurface in the C export" begin
    doc = _ext_model()
    flat = Compile.flatten(IR.parse_model(doc))
    @test isempty([d for d in flat.diagnostics if d.severity == "error"])

    dir = mktempdir()
    step = 1.0e-3
    r = BGSim.Export.export_model(flat, dir;
        settings = BGSim.Export.ExportSettings(t_end = _EXT_T_END, step = step, expose_all = true))
    @test r.ok
    @test isempty([d for d in r.diagnostics if d.severity == "error"])
    @test [i["name"] for i in r.report["inputs"]] == ["brake"]
    @test sort([o["name"] for o in r.report["outputs"]]) == ["Fx", "Fz", "kappa", "omega", "x"]

    cc = Sys.which("gcc")
    if cc === nothing
        @info "export: no gcc on PATH, the tyre compile-and-run checks are skipped"
    else
        n = round(Int, _EXT_T_END / step)
        rows, xn, yn = _ext_run_c(cc, dir, r.report, n)
        @test size(rows, 1) == n + 1
        t = rows[:, 1]
        col(name) = 1 + length(xn) + findfirst(==(name), yn)
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        # C (the export's fixed-step method at 1 ms) against the adaptive simulation on its
        # 10 ms grid; bounds are 1e-4 of each signal's scale (load 2.9 kN, traction 700 N, 3 m,
        # 20 rad/s; the slip of a free wheel stays near zero, so it gets 1e-4 absolute). Over
        # the first 0.15 s only: a single wheel on a free carrier
        # is not upright-stable at 3 m/s, it starts to tip and wobble (the load swings between
        # 2 and 5.5 kN by 1 s), and two integrators of that motion part at about 1e-3 by 0.25 s.
        grid = 1:round(Int, 0.01 / step):round(Int, 0.15 / step) + 1
        for (cname, sname, scale) in (("Fz", "Tyre/Fz", 2900.0), ("Fx", "Tyre/Fx", 700.0),
                ("kappa", "Tyre/kappa", 1.0), ("x", "Tyre/xc", 3.0), ("omega", "Tyre/omega", 20.0))
            ic = col(cname)
            err = maximum(abs(rows[k, ic] - bg_value(columns, sname, t[k])) for k in grid)
            @test err < 1e-4 * scale
        end
        # it starts at 3 m/s up the slope (+x) and rolls on, slowing on its weight
        @test rows[1, col("omega")] > 10.0
        @test rows[end, col("x")] > rows[1, col("x")] + 1.0
        @test rows[end, col("omega")] < rows[1, col("omega")] - 5.0
        @test rows[end, col("Fz")] > 1000.0

        rows2, _, _ = _ext_run_c(cc, dir, r.report, n)
        @test rows2 == rows

        @testset "builds with -Werror and does not allocate after instantiate" begin
            src = joinpath(dir, "sources")
            files = [joinpath(src, f) for f in ("model.c", "bg_solver.c", "bg_intrinsics.c",
                "bg_mech.c", "fmi2_cs.c") if isfile(joinpath(src, f))]
            for f in files
                @test success(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -I $src -c $f -o $(joinpath(dir, "x.o"))`)
            end
            harness = joinpath(BGSim.Export.RUNTIME_DIR, "alloc_check.c")
            exe = joinpath(dir, Sys.iswindows() ? "check.exe" : "check")
            @test success(`$cc -std=c11 -O2 -I $src $harness $files -o $exe -lm`)
            out = read(`$exe 1 1000`, String)
            @test occursin("after instantiate 0", out)
        end
    end
end
