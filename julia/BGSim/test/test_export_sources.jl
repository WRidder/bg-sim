# The signal sources in the C export (plan/EXPORT_PLAN.md): every new periodic and smooth
# source, and the options added to Sine, Ramp, Pulse and Chirp, exports, compiles with
# -Werror and runs. In C the `ifelse` conditions are frozen per step for the derivatives
# (W203) but `bg_outputs` evaluates them at the sample instant, so the published source
# outputs equal the analytic waveform at every step, and the integrals of the sources stay
# within the frozen-mode error of one step per edge.
#
# Each source is also compared against the Julia simulation of the same model at the
# common grid times (the right limit at an edge, as the recorder keeps it).
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

@testset "signal sources in the C export" begin
    cases = _exs_cases()
    nodes, conns = Any[], Any[]
    for (i, (block, params, _, _, _)) in enumerate(cases)
        push!(nodes, bg_node("s$i", "S$i", bg_ref("stdlib:sources/" * block);
            params = Dict{String,Any}(params)))
        push!(nodes, bg_node("i$i", "I$i", bg_ref("stdlib:continuous/Integrator")))
        push!(conns, bg_conn("c$i", "signal", "s$i", "y", "i$i", "u"))
    end
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
    end
end
