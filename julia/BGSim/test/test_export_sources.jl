# The signal sources in the C export (plan/EXPORT_PLAN.md): every new periodic and smooth
# source, and the options added to Sine, Ramp, Pulse and Chirp, exports, compiles with
# -Werror and runs. In C the `ifelse` conditions are frozen per step for the derivatives
# (W203) but `bg_outputs` evaluates them at the sample instant, so the published source
# outputs equal the analytic waveform at every step, and the integrals of the sources stay
# within the frozen-mode error of one step per edge.
#
# Each source is also compared against the Julia simulation of the same model at the
# common grid times (the right limit at an edge, as the recorder keeps it). The random
# sources (UniformNoise, BandLimitedWhiteNoise, PRBS, RandomWalk) are bit-identical: C,
# simulation and the specification of noise_uniform/noise_normal. The FMU sources build with
# -std=c99 -Wall -Wextra -Werror and do not allocate after instantiate. W216 (random
# sources sharing a seed) is tested at the end.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
isdefined(@__MODULE__, :SourceGolden) ||
    include(joinpath(@__DIR__, "golden", "sources", "source_helpers.jl"))
using Test
using BGSim
using .BondGraphGolden
using .SourceGolden
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

function _exs_run_c(cc, dir, report, n)
    src = joinpath(dir, "sources")
    runner = joinpath(dir, "runner.c")
    write(runner, _EXS_RUNNER)
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

vecstr(v) = "[" * join(v, ", ") * "]"

# Each case: block, parameters, the analytic reference, its breakpoints in [0, 1] (where
# the output may jump or kink) and the tolerance of the integral against the exact area.
function _exs_cases()
    cases = Any[]
    saw(t) = t < 0.0235 ? -1.0 : -1.0 + 2.0 * period_phase(t, 0.0235, 0.1)[2]
    push!(cases, ("Sawtooth", Dict("amplitude" => "2.0", "period" => "0.1",
            "offset" => "-1.0", "t_start" => "0.0235"), saw,
        edges(0.0235, 0.1, 1.0), 12 * 2.0 * 1e-3))
    saw_grid(t) = t < 0.3 ? 0.0 : period_phase(t, 0.3, 0.1)[2]
    push!(cases, ("Sawtooth", Dict("period" => "0.1", "t_start" => "0.3"), saw_grid,
        edges(0.3, 0.1, 1.0), 8 * 1e-3))
    function tri(t)
        t < 0.1 && return 0.5
        f = period_phase(t, 0.1, 0.2)[2]
        return 0.5 + 2.0 * (f < 0.5 ? 2f : 2(1 - f))
    end
    push!(cases, ("Triangle", Dict("amplitude" => "2.0", "period" => "0.2",
            "offset" => "0.5", "t_start" => "0.1"), tri,
        vcat(edges(0.1, 0.2, 1.0), edges(0.2, 0.2, 1.0)), 1e-4))
    function trap(t)
        t < 0.05 && return -0.5
        n, f = period_phase(t, 0.05, 0.1)
        n >= 7 && return -0.5
        s = snap(f * 0.1, (0.02, 0.05, 0.06))
        s < 0.02 && return -0.5 + 2.0 * s / 0.02
        s < 0.05 && return 1.5
        s < 0.06 && return -0.5 + 2.0 * (1 - (s - 0.05) / 0.01)
        return -0.5
    end
    push!(cases, ("Trapezoid", Dict("amplitude" => "2.0", "rising" => "0.02",
            "width" => "0.03", "falling" => "0.01", "period" => "0.1", "n_periods" => "7",
            "offset" => "-0.5", "t_start" => "0.05"), trap,
        reduce(vcat, [edges(0.05 + b, 0.1, 1.0) for b in (0.0, 0.02, 0.05, 0.06)]), 1e-3))
    pulse(t) = t < 0.0 ? 0.0 : (period_phase(t, 0.0, 0.1)[2] < 0.5 - 1e-9 ? 1.0 : 0.0)
    push!(cases, ("Trapezoid", Dict("width" => "0.05", "period" => "0.1"), pulse,
        vcat(edges(0.0, 0.1, 1.0), edges(0.05, 0.1, 1.0)), 20 * 1e-3))
    vals = [0.0, 1.0, -0.5, 2.0, 0.25, -1.0, 1.5, 0.75]
    for method in (0, 1)
        function table(t)
            t < 0.0115 && return vals[1]
            s = period_phase(t, 0.0115, 8 * 0.0371)[2] * 8
            j = round(s)
            abs(s - j) < 1e-9 && (s = j)
            i = min(floor(Int, s), 7)
            method == 0 && return vals[i + 1]
            nxt = i == 7 ? vals[1] : vals[i + 2]
            return vals[i + 1] + (nxt - vals[i + 1]) * (s - i)
        end
        push!(cases, ("RepeatingTable", Dict("t_start" => "0.0115", "sample_time" => "0.0371",
                "values" => vecstr(vals), "method" => string(method)), table,
            reduce(vcat, [edges(0.0115 + k * 0.0371, 8 * 0.0371, 1.0) for k in 0:7]),
            method == 0 ? 27 * 3.0 * 1e-3 : 1e-3))
    end
    push!(cases, ("ExpSine", Dict("amplitude" => "1.5", "frequency" => "20.0",
            "phase" => "0.3", "damping" => "2.0", "offset" => "0.1", "t_start" => "0.2505"),
        t -> t < 0.2505 ? 0.1 : 0.1 + 1.5 * exp(-2 * (t - 0.2505)) * sin(20 * (t - 0.2505) + 0.3),
        [0.2505], 3e-3))
    push!(cases, ("Exponentials", Dict("amplitude" => "2.0", "rise_time" => "0.4",
            "tau_rise" => "0.1", "tau_fall" => "0.2", "offset" => "-0.5", "t_start" => "0.2305"),
        t -> t < 0.2305 ? -0.5 : t < 0.6305 ? -0.5 + 2 * (1 - exp(-(t - 0.2305) / 0.1)) :
             -0.5 + 2 * (1 - exp(-4.0)) * exp(-(t - 0.6305) / 0.2),
        [0.2305, 0.6305], 1e-4))
    push!(cases, ("MultiSine", Dict("amplitudes" => vecstr([1.0, 0.5, 0.25]),
            "frequencies" => vecstr([2.0, 7.0, 13.0]), "phases" => vecstr([0.0, 0.5, -1.0]),
            "offset" => "0.2", "t_start" => "0.1005"),
        t -> t < 0.1005 ? 0.2 : 0.2 + sum([1.0, 0.5, 0.25][i] *
            sin([2.0, 7.0, 13.0][i] * (t - 0.1005) + [0.0, 0.5, -1.0][i]) for i in 1:3),
        [0.1005], 3e-3))
    push!(cases, ("Sine", Dict("amplitude" => "2.0", "frequency" => "5.0", "phase" => "0.4",
            "offset" => "0.5", "t_start" => "0.3005"),
        t -> t < 0.3005 ? 0.5 : 0.5 + 2 * sin(5 * (t - 0.3005) + 0.4), [0.3005], 3e-3))
    push!(cases, ("Ramp", Dict("t_start" => "0.2", "slope" => "3.0", "initial" => "-1.0",
            "duration" => "0.5"), t -> t < 0.2 ? -1.0 : -1.0 + 3 * min(t - 0.2, 0.5),
        [0.2, 0.7], 1e-5))
    L = log(8.0)
    lg(t) = t <= 1.0 ? (exp(L * t) - 1) / L : 7 / L + 8 * (t - 1)
    push!(cases, ("Chirp", Dict("f_start" => "1.0", "f_end" => "8.0", "duration" => "1.0",
            "amplitude" => "1.5", "offset" => "0.25", "start_phase" => "0.3", "method" => "1"),
        t -> 0.25 + 1.5 * sin(2pi * lg(t) + 0.3), Float64[], 1e-6))
    pulse_off(t) = (t >= 0.0235 && mod((t - 0.0235) / 0.37, 1.0) < 0.25) ? 1.5 : -0.5
    push!(cases, ("Pulse", Dict("amplitude" => "2.0", "period" => "0.37", "duty" => "0.25",
            "t_start" => "0.0235", "offset" => "-0.5"), pulse_off,
        vcat(edges(0.0235, 0.37, 1.0), edges(0.0235 + 0.0925, 0.37, 1.0)), 6 * 2.0 * 1e-3))
    return cases
end

# The random sources: block, parameters, the held variable, and that variable after tick n of
# the source's clock straight from the specification (spec "Seeded noise and delay").
function _exs_walk(seed, step, n)
    w = 0.0
    for i in 0:n - 1
        w = w + step * BGSim.bg_noise_normal(seed, i)
    end
    return w
end
const _EXS_RANDOM = [
    ("UniformNoise", Dict("y_min" => "-2.0", "y_max" => "3.0", "seed" => "11"), "u",
        n -> n == 0 ? 0.5 : BGSim.bg_noise_uniform(11, n - 1)),
    ("BandLimitedWhiteNoise", Dict("noise_power" => "0.02", "seed" => "12"), "z",
        n -> n == 0 ? 0.0 : BGSim.bg_noise_normal(12, n - 1)),
    ("PRBS", Dict("amplitude" => "1.5", "offset" => "0.5", "bit_ticks" => "3", "seed" => "13"),
        "s", n -> n == 0 ? 0.0 : (BGSim.bg_noise_uniform(13, div(n - 1, 3)) < 0.5 ? -1.0 : 1.0)),
    ("RandomWalk", Dict("step_std" => "0.1", "initial" => "1.0", "seed" => "14"), "w",
        n -> _exs_walk(14, 0.1, n)),
]
# The clock of each random source (the blocks' default sample_time).
const _EXS_RANDOM_TS = [1e-3, 1e-3, 1e-2, 1e-3]

@testset "signal sources in the C export" begin
    cases = _exs_cases()
    nodes, conns = Any[], Any[]
    for (i, (block, params, _, _, _)) in enumerate(cases)
        push!(nodes, bg_node("s$i", "S$i", bg_ref("stdlib:sources/" * block);
            params = Dict{String,Any}(params)))
        push!(nodes, bg_node("i$i", "I$i", bg_ref("stdlib:continuous/Integrator")))
        push!(conns, bg_conn("c$i", "signal", "s$i", "y", "i$i", "u"))
    end
    for (i, (block, params, _, _)) in enumerate(_EXS_RANDOM)
        push!(nodes, bg_node("r$i", "R$i", bg_ref("stdlib:sources/" * block);
            params = Dict{String,Any}(params)))
        push!(nodes, bg_node("ri$i", "RI$i", bg_ref("stdlib:continuous/Integrator")))
        push!(conns, bg_conn("rc$i", "signal", "r$i", "y", "ri$i", "u"))
    end
    # One ExportOutput, so the FMU wrapper has an output for the allocation harness.
    push!(nodes, bg_node("y1", "Y1", bg_ref("stdlib:converters/ExportOutput")))
    push!(conns, bg_conn("cy", "signal", "r1", "y", "y1", "u"))
    doc = bg_model("SourcesExport", nodes, conns; t_end = 1.0, points = 101)
    flat = Compile.flatten(IR.parse_model(doc))
    @test isempty([d for d in flat.diagnostics if d.severity == "error"])

    dir = mktempdir()
    r = _EXS.export_model(flat, dir;
        settings = _EXS.ExportSettings(t_end = 1.0, dt = 1e-3, expose_all = true))
    @test r.ok
    @test isempty([d for d in r.diagnostics if d.severity == "error"])
    # The edges are frozen-mode conditions in C, reported once per site (W203).
    @test any(d -> d.code == "W203", r.diagnostics)

    cc = Sys.which("gcc")
    if cc === nothing
        @info "export: no gcc on PATH, the signal-source compile-and-run checks are skipped"
    else
        n = 1000
        rows, xn, yn = _exs_run_c(cc, dir, r.report, n)
        @test size(rows, 1) == n + 1
        t = rows[:, 1]
        @test t ≈ (0:n) .* 1e-3
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        @test !any(d -> d.code == "W206", result.diagnostics)
        for (i, (block, params, ref, breaks, tol)) in enumerate(cases)
            @testset "$block $i" begin
                iy = 1 + length(xn) + findfirst(==("S$i/y"), yn)
                ix = 1 + findfirst(n -> startswith(n, "I$i/"), xn)
                # The output at every step equals the waveform, away from the instants
                # where a decimal edge and the step time round differently.
                away(tk) = all(abs(tk - b) > 1e-9 for b in breaks)
                ks = [k for k in 1:n + 1 if away(t[k])]
                @test maximum(abs(rows[k, iy] - ref(t[k])) for k in ks) < 1e-9
                # C and the Julia simulation agree at the common grid times (0.01 s).
                @test maximum(abs(rows[k, iy] - bg_value(columns, "S$i/y", t[k]))
                              for k in 1:10:n + 1 if away(t[k])) < 1e-9
                # The integral: within the frozen-mode error of one step per edge.
                area = [gl_area(ref, 0.0, tk, breaks) for tk in t[1:10:end]]
                @test maximum(abs.(rows[1:10:end, ix] .- area)) < tol
            end
        end
        # The random sources: the held sample and the output are bit-identical between C,
        # the simulation and the specification at every step of C and every grid time of
        # the simulation; the integrals agree to rounding.
        for (i, (block, params, var, spec)) in enumerate(_EXS_RANDOM)
            @testset "$block (bit for bit)" begin
                iv = 1 + length(xn) + findfirst(==("R$i/$var"), yn)
                iy = 1 + length(xn) + findfirst(==("R$i/y"), yn)
                ix = 1 + findfirst(n -> startswith(n, "RI$i/"), xn)
                ticks(tk) = div(round(Int, tk * 1e9), round(Int, _EXS_RANDOM_TS[i] * 1e9))
                @test all(rows[k, iv] == spec(ticks(t[k])) for k in 1:n + 1)
                @test all(rows[k, iv] == bg_value(columns, "R$i/$var", t[k]) for k in 1:10:n + 1)
                @test all(rows[k, iy] == bg_value(columns, "R$i/y", t[k]) for k in 1:10:n + 1)
                @test maximum(abs(rows[k, ix] - bg_value(columns, "RI$i/y", t[k]))
                              for k in 1:10:n + 1) < 1e-12
            end
        end
        # A second run of the C model (bg_reset, as fmi2Reset) repeats the first bit for bit.
        rows2, _, _ = _exs_run_c(cc, dir, r.report, n)
        @test rows2 == rows

        @testset "builds with -Werror and does not allocate after instantiate" begin
            src = joinpath(dir, "sources")
            files = [joinpath(src, f) for f in ("model.c", "bg_solver.c", "bg_intrinsics.c",
                "bg_mech.c", "fmi2_cs.c") if isfile(joinpath(src, f))]
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
end

@testset "W216: random sources that share a seed" begin
    function seeds_model(seeds)
        blocks = ["Noise", "UniformNoise", "BandLimitedWhiteNoise", "PRBS", "RandomWalk"]
        nodes = Any[bg_node("n$i", "R$i", bg_ref("stdlib:sources/" * blocks[i]);
            params = Dict{String,Any}("seed" => string(seeds[i]))) for i in eachindex(seeds)]
        return Compile.flatten(IR.parse_model(bg_model("Seeds", nodes, Any[])))
    end
    w216(flat) = [d for d in flat.diagnostics if d.code == "W216"]
    @test isempty(w216(seeds_model([1, 2, 3, 4, 5])))
    ds = w216(seeds_model([7, 2, 7, 4, 7]))
    @test length(ds) == 1
    d = only(ds)
    @test d.severity == "warning"
    @test d.path == "R1"
    @test occursin("`R1`, `R3`, `R5` share seed 7", d.message)
    @test [r.path for r in d.related] == ["R3", "R5"]
    @test occursin("its own `seed`", d.hint)
    # Two groups give two warnings.
    ds = w216(seeds_model([2, 1, 1, 2, 3]))
    @test length(ds) == 2
    @test count(d -> occursin("`R2`, `R3` share seed 1,", d.message), ds) == 1
    @test count(d -> occursin("`R1`, `R4` share seed 2,", d.message), ds) == 1
    # Deterministic sources have no seed and never count.
    @test isempty(w216(Compile.flatten(IR.parse_model(bg_model("NoSeeds",
        Any[bg_node("a", "A", bg_ref("stdlib:sources/Sine")),
            bg_node("b", "B", bg_ref("stdlib:sources/Sawtooth"))], Any[])))))
end
