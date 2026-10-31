# The vacuum gripping blocks (`stdlib:contact/SuctionCup`, `stdlib:contact/VacuumGenerator`)
# in the C export: a cup fixed to the ground holds a 2 kg part through a neutral mount; the
# part starts at the unstretched bellows length, off-centre and with a lateral bellows
# deflection, so it bounces axially, sways laterally and tilts while a pump-like generator
# (n = 2) holds the porous part's vacuum against the lip and material leaks. The model
# exports, compiles with -std=c99 -Wall -Wextra -Werror, runs, matches the Julia simulation,
# repeats bit for bit after a reset and does not allocate after instantiate. The cup's seal
# latch (`h > h_lost => reinit(lost, 1)`) is an `@events` entry, exported as an event with a
# W203 note.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using Test
using BGSim
using .BondGraphGolden
import BGSim.IR
import BGSim.Compile

const _EXS = BGSim.Export

const _EXS_RUNNER = raw"""
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

const _EXS_FILES = ("model.c", "bg_solver.c", "bg_intrinsics.c", "bg_mech.c")

function _exs_run_c(cc, dir, report, n)
    src = joinpath(dir, "sources")
    runner = joinpath(dir, "runner.c")
    write(runner, _EXS_RUNNER)
    exe = joinpath(dir, Sys.iswindows() ? "runner.exe" : "runner")
    files = [joinpath(src, f) for f in _EXS_FILES if isfile(joinpath(src, f))]
    run(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -I $src $files $runner -o $exe -lm`)
    rows = [parse.(Float64, split(l)) for l in eachline(`$exe $n`)]
    ynames = vcat([o["name"] for o in report["outputs"]], String.(report["locals"]))
    model_c = read(joinpath(src, "model.c"), String)
    nx = length(collect(eachmatch(r"/\* x\[(\d+)\] = (\S+) \*/", model_c)))
    return permutedims(reduce(hcat, rows)), nx, ynames
end

_exs_str(d) = Dict{String,Any}(String(k) => string(v) for (k, v) in d)

function _exs_rig()
    dx, e0 = 0.01, 2.0e-3
    nodes = Any[
        bg_node("gr", "Ground", bg_ref("stdlib:multibond/GroundSpatial")),
        bg_node("gm", "GMount", bg_ref("stdlib:multibond/FixedTransform3DNeutral")),
        bg_node("cu", "Cup", bg_ref("stdlib:contact/SuctionCup");
            params = _exs_str(Dict("perm" => 4.0e-7)),
            starts = _exs_str(Dict("rx" => e0, "rz" => -0.04, "ex" => e0, "p" => -4.0e4))),
        bg_node("pm", "PMount", bg_ref("stdlib:multibond/FixedTransform3DNeutral");
            params = _exs_str(Dict("x" => dx, "z" => -0.1))),
        bg_node("b", "Part", bg_ref("stdlib:spatial/RigidBody3D");
            params = Dict{String,Any}("m" => "2.0", "J" => "[0.01, 0.01, 0.01]", "g0" => "9.81"),
            starts = Dict{String,Any}("inertia/P" => "[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]")),
        bg_node("po", "Pose", bg_ref("stdlib:multibond/PoseIntegrator3D");
            starts = _exs_str(Dict("px" => e0 + dx, "pz" => -0.14))),
        bg_node("ge", "Gen", bg_ref("stdlib:contact/VacuumGenerator");
            params = _exs_str(Dict("n" => 2.0))),
        bg_node("on", "On", bg_ref("stdlib:sources/Constant"); params = _exs_str(Dict("value" => 1.0))),
    ]
    conns = Any[
        bg_conn("c1", "bond", "gr", "p", "gm", "b"),
        bg_conn("c2", "bond", "gm", "a", "cu", "a"),
        bg_conn("c3", "bond", "b", "p", "pm", "b"),
        bg_conn("c4", "bond", "pm", "a", "cu", "b"),
        bg_conn("c5", "signal", "b", "V", "po", "tw"),
        bg_conn("c6", "signal", "po", "g", "b", "g"),
        bg_conn("c7", "wire", "ge", "a", "cu", "vac"),
        bg_conn("c8", "signal", "on", "y", "ge", "u"),
    ]
    signals = ["Cup/T", "Cup/ext", "Cup/dp", "Cup/F_lat", "Cup/M_tilt", "Cup/U", "Cup/Q_por",
        "Cup/Q_leak", "Gen/Q", "Pose/pz", "Pose/px"]
    return bg_model("SuctionCupExport", nodes, conns; t_end = 0.5, points = 51), signals
end

@testset "vacuum gripping blocks in the C export" begin
    cc = Sys.which("gcc")
    doc, signals = _exs_rig()
    flat = Compile.flatten(IR.parse_model(doc))
    @test isempty([d for d in flat.diagnostics if d.severity == "error"])
    dir = mktempdir()
    r = _EXS.export_model(flat, dir;
        settings = _EXS.ExportSettings(t_end = 0.5, step = 2.5e-4, expose_all = true))
    @test r.ok
    @test isempty([d for d in r.diagnostics if d.severity == "error"])
    if r.ok && cc === nothing
        @info "export: no gcc on PATH, the suction compile-and-run checks are skipped"
    elseif r.ok
        dt = r.report["dt"]
        @info "suction export" method = r.report["method"] dt
        n = round(Int, 0.5 / dt)
        rows, nx, yn = _exs_run_c(cc, dir, r.report, n)
        @test size(rows, 1) == n + 1
        t = rows[:, 1]
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        grid = [k for k in 1:n+1 if abs(t[k] * 100 - round(t[k] * 100)) < 1e-6]
        @test length(grid) == 51
        # The run holds: the seal latch never trips, so C and Julia follow the same branch.
        @test maximum(bg_all(columns, "Cup/h")) < 1.0e-4
        for s in signals
            iy = findfirst(==(s), yn)
            @test iy !== nothing
            iy === nothing && continue
            c = rows[grid, 1 + nx + iy]
            j = [bg_value(columns, s, t[k]) for k in grid]
            scale = maximum(abs.(j))
            err = maximum(abs.(c .- j))
            @test err <= 2e-3 * scale
            err > 2e-3 * scale && @info "export mismatch" s err scale
        end
        rows2, _, _ = _exs_run_c(cc, dir, r.report, n)
        @test rows2 == rows

        src = joinpath(dir, "sources")
        files = [joinpath(src, f) for f in (_EXS_FILES..., "fmi2_cs.c") if isfile(joinpath(src, f))]
        for f in files
            @test success(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -I $src -c $f -o $(joinpath(dir, "x.o"))`)
        end
        harness = joinpath(_EXS.RUNTIME_DIR, "alloc_check.c")
        exe = joinpath(dir, Sys.iswindows() ? "check.exe" : "check")
        @test success(`$cc -std=c11 -O2 -I $src $harness $files -o $exe -lm`)
        out = read(`$exe 1 1000`, String)
        @test occursin("after instantiate 0", out)
    end
end
