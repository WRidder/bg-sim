# The rolling contact and the rotor (stdlib:contact/RollingDisk, stdlib:spatial/Rotor3D) in the
# C export (plan/EXPORT_PLAN.md): a leaning wheel rolling on the plane with a flywheel on its
# axle, the flywheel torque an export input. The export builds with -std=c99 -Wall -Wextra
# -Werror, matches the Julia simulation, repeats bit for bit after bg_reset and does not
# allocate after fmi2Instantiate. The model is the core of the `gyrover` example (a stiff
# Hertz contact, the regularised friction with its sqrt, the lowest-rim-point geometry and the
# gyroscopic coupling of the rotor).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :_rr_wheel)
    include(joinpath(@__DIR__, "golden", "contact", "rolling_rig.jl"))
end
using Test
using BGSim
using .BondGraphGolden
import BGSim.IR
import BGSim.Compile

const _EXR = BGSim.Export

const _EXR_RUNNER = raw"""
#include <stdio.h>
#include <stdlib.h>
#include "model.h"
static bg_model m;
int main(int argc, char **argv) {
    long n = argc > 1 ? atol(argv[1]) : 100;
    long sub = argc > 2 ? atol(argv[2]) : 1;   /* bg_step advances BG_DT, a fraction of the step */
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

function _exr_run_c(cc, dir, report, n)
    sub = Int(report["substeps"])
    src = joinpath(dir, "sources")
    runner = joinpath(dir, "runner.c")
    write(runner, _EXR_RUNNER)
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

const _EXR_T_END = 0.5

_exr_model() = _rr_wheel(; v = 1.5, lean = 0.05, rotor = true, h0 = 0.5, tau = 0.02, tau_input = true,
    mu = 0.8, c = 2.0, t_end = _EXR_T_END, points = 51, reltol = 1.0e-10, abstol = 1.0e-12,
    outputs = (("f_n", "c", "f_n"), ("camber", "c", "camber"), ("w_rel", "r", "w_rel"),
        ("x", "c", "xc")), name = "RollingExport")

@testset "RollingDisk and Rotor3D in the C export" begin
    doc = _exr_model()
    flat = Compile.flatten(IR.parse_model(doc))
    @test isempty([d for d in flat.diagnostics if d.severity == "error"])

    dir = mktempdir()
    step = 1.0e-3
    r = _EXR.export_model(flat, dir;
        settings = _EXR.ExportSettings(t_end = _EXR_T_END, step = step, expose_all = true))
    @test r.ok
    @test isempty([d for d in r.diagnostics if d.severity == "error"])
    @test [i["name"] for i in r.report["inputs"]] == ["tau"]
    @test sort([o["name"] for o in r.report["outputs"]]) == ["camber", "f_n", "w_rel", "x"]

    cc = Sys.which("gcc")
    if cc === nothing
        @info "export: no gcc on PATH, the rolling compile-and-run checks are skipped"
    else
        n = round(Int, _EXR_T_END / step)
        rows, xn, yn = _exr_run_c(cc, dir, r.report, n)
        @test size(rows, 1) == n + 1
        t = rows[:, 1]
        @test isapprox(t, (0:n) .* step; atol = 1e-9)
        col(name) = 1 + length(xn) + findfirst(==(name), yn)
        columns, result, _ = bg_run(doc)
        @test result.status == "done"

        # C against the simulation on the simulation grid (10 ms). The C side is the export's
        # fixed-step method at 1 ms, the Julia side an adaptive solve at reltol 1e-10; the
        # bounds are 1e-4 of each signal's scale (weight 20 N, lean 0.05 rad, 170 rad/s,
        # 0.75 m).
        grid = 1:round(Int, 0.01 / step):n + 1
        for (cname, sname, scale) in (("f_n", "Tyre/f_n", 20.0),
                ("camber", "Tyre/camber", 0.05),
                ("w_rel", "Rotor/w_rel", 170.0),
                ("x", "Tyre/xc", 0.75))
            ic = col(cname)
            err = maximum(abs(rows[k, ic] - bg_value(columns, sname, t[k])) for k in grid)
            @test err < 1e-4 * scale
        end
        # The wheel rolls on (it neither falls nor stops) and the motor spins the rotor up.
        @test rows[end, col("x")] > 0.7
        @test abs(rows[end, col("camber")]) < 0.2
        @test rows[end, col("f_n")] > 10.0

        # bg_reset repeats the run bit for bit.
        rows2, _, _ = _exr_run_c(cc, dir, r.report, n)
        @test rows2 == rows

        @testset "builds with -Werror and does not allocate after instantiate" begin
            src = joinpath(dir, "sources")
            files = [joinpath(src, f) for f in ("model.c", "bg_solver.c", "bg_intrinsics.c",
                "bg_mech.c", "fmi2_cs.c") if isfile(joinpath(src, f))]
            for f in files
                @test success(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -I $src -c $f -o $(joinpath(dir, "x.o"))`)
            end
            harness = joinpath(_EXR.RUNTIME_DIR, "alloc_check.c")
            exe = joinpath(dir, Sys.iswindows() ? "check.exe" : "check")
            @test success(`$cc -std=c11 -O2 -I $src $harness $files -o $exe -lm`)
            out = read(`$exe 1 1000`, String)
            @test occursin("after instantiate 0", out)
        end
    end
end
