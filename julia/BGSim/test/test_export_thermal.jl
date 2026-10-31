# The Thermal domain in the C export (plan/EXPORT_PLAN.md): a heated winding and a housing
# that cools by convection and radiation export, build with -std=c99 -Wall -Wextra -Werror,
# match the Julia simulation and do not allocate after fmi2Instantiate.
#
# The model is nonlinear in the temperatures (R(T) of the heated resistor, T^4 of the
# radiation) and mixes an algebraic electrical loop with the thermal states, so it exercises
# the same paths as an electro-thermal plant on a real-time target. The C runner prints the
# states and the exposed locals every communication step; the simulation's grid points are
# the reference, and the first law of the winding is checked on the C trajectory too.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using Test
using BGSim
using .BondGraphGolden
import BGSim.IR
import BGSim.Compile

const _EXT = BGSim.Export

const _EXT_RUNNER = raw"""
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

function _ext_model()
    p(kv...) = Dict{String,Any}(kv...)
    nodes = Any[
        bg_node("n1", "voltage", bg_ref("stdlib:converters/ExportInput");
            params = p("value" => "24.0")),
        bg_node("n2", "Supply", bg_ref("stdlib:electrical/VoltageSource");
            params = p("V" => "1.0")),
        bg_node("n3", "Gnd", bg_ref("stdlib:electrical/Ground")),
        bg_node("n4", "Heater", bg_ref("stdlib:thermal/ResistorHeated");
            params = p("R0" => "4.0", "alpha" => "0.004", "T0" => "293.15")),
        bg_node("n5", "Winding", bg_ref("stdlib:thermal/HeatCapacitor");
            params = p("C" => "20.0"), starts = p("T" => "293.15")),
        bg_node("n6", "Insulation", bg_ref("stdlib:thermal/ThermalConductor");
            params = p("G" => "0.8")),
        bg_node("n7", "Housing", bg_ref("stdlib:thermal/HeatCapacitor");
            params = p("C" => "300.0"), starts = p("T" => "293.15")),
        bg_node("n8", "Film", bg_ref("stdlib:thermal/Convection");
            params = p("h" => "15.0", "A" => "0.08")),
        bg_node("n9", "Rad", bg_ref("stdlib:thermal/BodyRadiation");
            params = p("epsilon" => "0.85", "A" => "0.08")),
        bg_node("n10", "Ambient", bg_ref("stdlib:thermal/FixedTemperature");
            params = p("T" => "298.15")),
        bg_node("n11", "ProbeW", bg_ref("stdlib:thermal/TemperatureSensor")),
        bg_node("n12", "T_winding", bg_ref("stdlib:converters/ExportOutput")),
        bg_node("n13", "Loss", bg_ref("stdlib:thermal/HeatFlowSensor")),
        bg_node("n14", "P_loss", bg_ref("stdlib:converters/ExportOutput")),
    ]
    conns = Any[
        bg_conn("c1", "signal", "n1", "y", "n2", "u"),
        bg_conn("c2", "wire", "n2", "p", "n4", "p"),
        bg_conn("c3", "wire", "n4", "n", "n3", "p"),
        bg_conn("c4", "wire", "n2", "n", "n3", "p"),
        bg_conn("c5", "wire", "n4", "heat", "n13", "a"),
        bg_conn("c6", "wire", "n13", "b", "n5", "a"),
        bg_conn("c7", "wire", "n5", "a", "n6", "a"),
        bg_conn("c8", "wire", "n6", "b", "n7", "a"),
        bg_conn("c9", "wire", "n7", "a", "n8", "solid"),
        bg_conn("c10", "wire", "n8", "fluid", "n10", "a"),
        bg_conn("c11", "wire", "n7", "a", "n9", "a"),
        bg_conn("c12", "wire", "n9", "b", "n10", "a"),
        bg_conn("c13", "wire", "n11", "a", "n5", "a"),
        bg_conn("c14", "signal", "n11", "y", "n12", "u"),
        bg_conn("c15", "signal", "n13", "y", "n14", "u"),
    ]
    return bg_model("ThermalExport", nodes, conns; t_end = 60.0, points = 61)
end

function _ext_run_c(cc, dir, report, n)
    src = joinpath(dir, "sources")
    runner = joinpath(dir, "runner.c")
    write(runner, _EXT_RUNNER)
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

@testset "Thermal domain in the C export" begin
    doc = _ext_model()
    flat = Compile.flatten(IR.parse_model(doc))
    @test isempty([d for d in flat.diagnostics if d.severity == "error"])
    @test flat.stats.states == 2                 # winding and housing temperatures

    dir = mktempdir()
    step = 0.05
    r = _EXT.export_model(flat, dir;
        settings = _EXT.ExportSettings(t_end = 60.0, step = step, expose_all = true))
    @test r.ok
    @test isempty([d for d in r.diagnostics if d.severity == "error"])
    @test [i["name"] for i in r.report["inputs"]] == ["voltage"]
    @test sort([o["name"] for o in r.report["outputs"]]) == ["P_loss", "T_winding"]

    cc = Sys.which("gcc")
    if cc === nothing
        @info "export: no gcc on PATH, the thermal compile-and-run checks are skipped"
    else
        n = round(Int, 60.0 / step)
        rows, xn, yn = _ext_run_c(cc, dir, r.report, n)
        @test size(rows, 1) == n + 1
        t = rows[:, 1]
        @test isapprox(t, (0:n) .* step; atol = 1e-9)
        col(name) = 1 + length(xn) + findfirst(==(name), yn)
        columns, result, _ = bg_run(doc)
        @test result.status == "done"

        # C against the simulation at every simulation grid time (1 s), for the published
        # outputs and the exposed temperatures and heat flows. The C side is the export's
        # fixed-step method (measured: 5e-4 K on the winding, 2e-6 relative), the Julia side
        # an adaptive solve at reltol 1e-10, so the bound is 1e-5 of the signal's scale.
        grid = 1:round(Int, 1.0 / step):n + 1
        for (cname, sname, scale) in (("T_winding", "ProbeW/y", 300.0),
                ("P_loss", "Loss/y", 150.0),
                ("Housing/T", "Housing/T", 300.0),
                ("Rad/Q", "Rad/Q", 10.0),
                ("Heater/R", "Heater/R", 4.0))
            ic = col(cname)
            err = maximum(abs(rows[k, ic] - bg_value(columns, sname, t[k])) for k in grid)
            @test err < 1e-5 * scale
        end
        # The plant really heats: the winding is well above ambient, its resistance rose.
        @test rows[end, col("T_winding")] > 330.0
        @test rows[end, col("Heater/R")] > 4.0 * (1 + 0.004 * 30.0)

        # First law of the winding on the C trajectory (trapezoid over the fixed steps):
        # integral of the loss = C*(T - T0) + integral of the conducted heat.
        loss = rows[:, col("P_loss")]
        cond = rows[:, col("Insulation/Q")]
        trap(v) = step * (sum(v) - (v[1] + v[end]) / 2)
        stored = 20.0 * (rows[end, col("T_winding")] - 293.15)
        @test isapprox(trap(loss), stored + trap(cond); rtol = 1e-4)

        # bg_reset repeats the run bit for bit.
        rows2, _, _ = _ext_run_c(cc, dir, r.report, n)
        @test rows2 == rows

        @testset "builds with -Werror and does not allocate after instantiate" begin
            src = joinpath(dir, "sources")
            files = [joinpath(src, f) for f in ("model.c", "bg_solver.c", "bg_intrinsics.c",
                "bg_mech.c", "fmi2_cs.c") if isfile(joinpath(src, f))]
            for f in files
                @test success(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -I $src -c $f -o $(joinpath(dir, "x.o"))`)
            end
            harness = joinpath(_EXT.RUNTIME_DIR, "alloc_check.c")
            exe = joinpath(dir, Sys.iswindows() ? "check.exe" : "check")
            @test success(`$cc -std=c11 -O2 -I $src $harness $files -o $exe -lm`)
            out = read(`$exe 1 1000`, String)
            @test occursin("after instantiate 0", out)
        end
    end
end
