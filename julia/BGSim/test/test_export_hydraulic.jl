# The hydraulic components in the C export (plan/EXPORT_PLAN.md): every hydraulic block
# added with the valves/pump/motor/accumulator/pipe set exports, compiles with
# -std=c99 -Wall -Wextra -Werror, runs, matches the Julia simulation of the same model and
# does not allocate after instantiate.
#
# Two circuits cover the blocks:
#   * supply: a FixedDisplacementPump driven at 150 rad/s fills a Volume protected by a
#     PressureReliefValve; from that rail a CheckValve feeds a second volume drained by a
#     Pipe (a 1.5 mm drain line), a two-segment turbulent Pipe charges an Accumulator, and a
#     PressureCompensatedFlowControl feeds a HydraulicMotor that spins an inertia against
#     a damper;
#   * actuator: a VariableDisplacementPump with a sine stroke command feeds a volume
#     relieved at 50 bar by a PressureReliefValve, and a DirectionalValve43 between a
#     100 bar supply and the tank moves a HydraulicCylinder with a 50 kg load from a
#     cosine spool command.
# The hydraulic laws are smooth (no ifelse), so they add no W203 frozen-mode condition (the
# only one is the Sine start): the C code and the simulation agree to the integration error
# of the fixed step.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using Test
using BGSim
using .BondGraphGolden
import BGSim.IR
import BGSim.Compile

const _EXH = BGSim.Export

const _EXH_RUNNER = raw"""
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

const _EXH_FILES = ("model.c", "bg_solver.c", "bg_intrinsics.c", "bg_mech.c")

function _exh_run_c(cc, dir, report, n)
    src = joinpath(dir, "sources")
    runner = joinpath(dir, "runner.c")
    write(runner, _EXH_RUNNER)
    exe = joinpath(dir, Sys.iswindows() ? "runner.exe" : "runner")
    files = [joinpath(src, f) for f in _EXH_FILES if isfile(joinpath(src, f))]
    run(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -I $src $files $runner -o $exe -lm`)
    rows = [parse.(Float64, split(l)) for l in eachline(`$exe $n`)]
    ynames = vcat([o["name"] for o in report["outputs"]], String.(report["locals"]))
    model_c = read(joinpath(src, "model.c"), String)
    nx = length(collect(eachmatch(r"/\* x\[(\d+)\] = (\S+) \*/", model_c)))
    return permutedims(reduce(hcat, rows)), nx, ynames
end

_exh_const(id, name, v) = bg_node(id, name, bg_ref("stdlib:sources/Constant");
    params = Dict{String,Any}("value" => string(v)))
_exh_node(id, name, ref; kw...) = bg_node(id, name, bg_ref("stdlib:" * ref);
    params = Dict{String,Any}((string(k) => string(v)) for (k, v) in kw))

function _exh_supply()
    pipe = _exh_node("pl", "PL", "hydraulic/Pipe"; L = 1.0, d = 6.0e-3, f_t = 0.03)
    pipe["constants"] = Dict{String,Any}("N" => 2)
    nodes = Any[
        _exh_const("c1", "One", 1.0),
        _exh_node("w1", "W1", "rotation/SpeedSource"; w = 150.0),
        _exh_node("pu", "Pump", "converters/FixedDisplacementPump"),
        _exh_node("tk", "TK", "hydraulic/Tank"),
        _exh_node("v1", "V1", "hydraulic/Volume"; V = 2.0e-4),
        _exh_node("rv", "RV", "hydraulic/PressureReliefValve"),
        _exh_node("cv", "CV", "hydraulic/CheckValve"),
        _exh_node("v3", "V3", "hydraulic/Volume"; V = 1.0e-5),
        _exh_node("dr", "Drain", "hydraulic/Pipe"; L = 0.5, d = 1.5e-3),
        pipe,
        _exh_node("ac", "ACC", "hydraulic/Accumulator"; p0 = 3.0e6, V0 = 2.0e-4),
        _exh_const("c2", "FlowCmd", 0.5),
        _exh_node("fc", "FC", "hydraulic/PressureCompensatedFlowControl"),
        _exh_node("v4", "V4", "hydraulic/Volume"; V = 1.0e-5),
        _exh_node("mo", "Motor", "converters/HydraulicMotor"),
        _exh_node("j1", "J1", "rotation/Inertia"; J = 0.01),
        _exh_node("d1", "D1", "rotation/RotationalDamper"; d = 0.1),
        _exh_node("g1", "G1", "rotation/FixedShaft"),
        _exh_node("g2", "G2", "rotation/FixedShaft"),
        _exh_node("ps", "PSens", "converters/PressureSensor"),
        bg_node("y1", "Y1", bg_ref("stdlib:converters/ExportOutput")),
    ]
    conns = Any[
        bg_conn("s1", "signal", "c1", "y", "w1", "u"),
        bg_conn("w01", "wire", "w1", "a", "pu", "shaft"),
        bg_conn("w02", "wire", "tk", "a", "pu", "a"),
        bg_conn("w03", "wire", "pu", "b", "v1", "a"),
        bg_conn("w04", "wire", "v1", "a", "rv", "a"),
        bg_conn("w05", "wire", "rv", "b", "tk", "a"),
        bg_conn("w06", "wire", "v1", "a", "cv", "a"),
        bg_conn("w07", "wire", "cv", "b", "v3", "a"),
        bg_conn("w08", "wire", "v3", "a", "dr", "a"),
        bg_conn("w09", "wire", "dr", "b", "tk", "a"),
        bg_conn("w10", "wire", "v1", "a", "pl", "a"),
        bg_conn("w11", "wire", "pl", "b", "ac", "a"),
        bg_conn("s2", "signal", "c2", "y", "fc", "u"),
        bg_conn("w12", "wire", "v1", "a", "fc", "a"),
        bg_conn("w13", "wire", "fc", "b", "v4", "a"),
        bg_conn("w14", "wire", "v4", "a", "mo", "a"),
        bg_conn("w15", "wire", "mo", "b", "tk", "a"),
        bg_conn("w16", "wire", "mo", "shaft", "j1", "a"),
        bg_conn("w17", "wire", "j1", "b", "g1", "a"),
        bg_conn("w18", "wire", "j1", "a", "d1", "a"),
        bg_conn("w19", "wire", "d1", "b", "g2", "a"),
        bg_conn("w20", "wire", "v1", "a", "ps", "a"),
        bg_conn("s3", "signal", "ps", "y", "y1", "u"),
    ]
    signals = ["V1/p", "V3/p", "V4/p", "ACC/V_f", "ACC/p", "PL/qa", "PL/q[2]", "J1/w",
        "Pump/Q", "Pump/T", "RV/Q", "CV/Q", "FC/Q", "Motor/Q", "Motor/T"]
    return bg_model("HydraulicSupplyExport", nodes, conns; t_end = 0.5, points = 51),
    signals
end

function _exh_actuator()
    nodes = Any[
        _exh_const("c1", "One", 1.0),
        _exh_node("w1", "W1", "rotation/SpeedSource"; w = 150.0),
        _exh_node("sw", "Stroke", "sources/Sine"; amplitude = 0.5, frequency = 20.0,
            offset = 0.5),
        _exh_node("vp", "VPump", "converters/VariableDisplacementPump"),
        _exh_node("tk", "TK", "hydraulic/Tank"),
        _exh_node("v2", "V2", "hydraulic/Volume"; V = 5.0e-4),
        _exh_node("rv", "RV2", "hydraulic/PressureReliefValve"; p_set = 5.0e6),
        _exh_node("ps", "PS", "hydraulic/PressureSource"; p = 1.0e7),
        _exh_node("sp", "Spool", "sources/Sine"; amplitude = 0.2, frequency = 5.0,
            phase = pi / 2),
        _exh_node("dv", "DV", "hydraulic/DirectionalValve43"),
        _exh_node("cy", "Cyl", "converters/HydraulicCylinder"),
        _exh_node("m1", "Load", "translation/Mass"; m = 50.0),
        _exh_node("d1", "Damp", "translation/Damper"; d = 2000.0),
        _exh_node("f1", "F1", "translation/Fixed"),
        _exh_node("f2", "F2", "translation/Fixed"),
        _exh_node("ps2", "PSens", "converters/PressureSensor"),
        bg_node("y1", "Y1", bg_ref("stdlib:converters/ExportOutput")),
    ]
    conns = Any[
        bg_conn("s1", "signal", "c1", "y", "w1", "u"),
        bg_conn("s2", "signal", "c1", "y", "ps", "u"),
        bg_conn("s3", "signal", "sw", "y", "vp", "u"),
        bg_conn("s4", "signal", "sp", "y", "dv", "u"),
        bg_conn("w01", "wire", "w1", "a", "vp", "shaft"),
        bg_conn("w02", "wire", "tk", "a", "vp", "a"),
        bg_conn("w03", "wire", "vp", "b", "v2", "a"),
        bg_conn("w04", "wire", "v2", "a", "rv", "a"),
        bg_conn("w05", "wire", "rv", "b", "tk", "a"),
        bg_conn("w06", "wire", "ps", "a", "dv", "P"),
        bg_conn("w07", "wire", "dv", "T", "tk", "a"),
        bg_conn("w08", "wire", "dv", "A", "cy", "A"),
        bg_conn("w09", "wire", "dv", "B", "cy", "B"),
        bg_conn("w10", "wire", "cy", "rod", "m1", "a"),
        bg_conn("w11", "wire", "m1", "b", "f1", "a"),
        bg_conn("w12", "wire", "m1", "a", "d1", "a"),
        bg_conn("w13", "wire", "d1", "b", "f2", "a"),
        bg_conn("w14", "wire", "cy", "A", "ps2", "a"),
        bg_conn("s5", "signal", "ps2", "y", "y1", "u"),
    ]
    signals = ["V2/p", "VPump/Q", "VPump/T", "Cyl/x", "Cyl/pA", "Cyl/pB", "Load/v",
        "DV/Q_PA", "DV/Q_BT", "DV/Q_PB", "DV/Q_AT"]
    return bg_model("HydraulicActuatorExport", nodes, conns; t_end = 0.5, points = 51),
    signals
end

@testset "hydraulic components in the C export" begin
    cc = Sys.which("gcc")
    for (label, (doc, signals)) in (("supply", _exh_supply()), ("actuator", _exh_actuator()))
        @testset "$label" begin
            flat = Compile.flatten(IR.parse_model(doc))
            @test isempty([d for d in flat.diagnostics if d.severity == "error"])
            dir = mktempdir()
            r = _EXH.export_model(flat, dir;
                settings = _EXH.ExportSettings(t_end = 0.5, step = 1.0e-3, expose_all = true))
            @test r.ok
            @test isempty([d for d in r.diagnostics if d.severity == "error"])
            # Smooth laws: no frozen-mode condition from a hydraulic block (the only W203
            # allowed is the actuator's Sine start `t >= t_start`).
            @test !any(d -> d.code == "W203" && d.block !== nothing &&
                            !startswith(d.block, "stdlib:sources/"), r.diagnostics)
            r.ok || continue
            if cc === nothing
                @info "export: no gcc on PATH, the hydraulic compile-and-run checks are skipped"
                continue
            end
            dt = r.report["dt"]
            @info "hydraulic export" label method = r.report["method"] dt
            n = round(Int, 0.5 / dt)
            rows, nx, yn = _exh_run_c(cc, dir, r.report, n)
            @test size(rows, 1) == n + 1
            t = rows[:, 1]
            columns, result, _ = bg_run(doc)
            @test result.status == "done"
            @test isempty([e for e in result.diagnostics if e.severity == "error"])
            grid = [k for k in 1:n+1 if abs(t[k] * 100 - round(t[k] * 100)) < 1e-6]
            @test length(grid) == 51
            for s in signals
                iy = findfirst(==(s), yn)
                @test iy !== nothing
                iy === nothing && continue
                c = rows[grid, 1 + nx + iy]
                j = [bg_value(columns, s, t[k]) for k in grid]
                scale = maximum(abs.(j))
                err = maximum(abs.(c .- j))
                @test err <= 2e-3 * scale
                err > 2e-3 * scale && @info "export mismatch" label s err scale
            end
            # A second run (bg_reset, as fmi2Reset) repeats the first bit for bit.
            rows2, _, _ = _exh_run_c(cc, dir, r.report, n)
            @test rows2 == rows

            src = joinpath(dir, "sources")
            files = [joinpath(src, f) for f in (_EXH_FILES..., "fmi2_cs.c")
                     if isfile(joinpath(src, f))]
            for f in files
                @test success(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -I $src -c $f -o $(joinpath(dir, "x.o"))`)
            end
            harness = joinpath(_EXH.RUNTIME_DIR, "alloc_check.c")
            exe = joinpath(dir, Sys.iswindows() ? "check.exe" : "check")
            @test success(`$cc -std=c11 -O2 -I $src $harness $files -o $exe -lm`)
            out = read(`$exe 1 1000`, String)
            @test occursin("after instantiate 0", out)
        end
    end
end
