# The motion profiles and drive electronics (stdlib/motion) in the C export
# (plan/EXPORT_PLAN.md). One model holds every block of the group:
#   * the five profiles, each velocity integrated (in C the `ifelse` switches are frozen
#     per step for the derivatives, W203, but `bg_outputs` evaluates them at the sample
#     instant, so the published profile outputs equal the closed form at every step);
#   * PWM (10 Hz, duty 0.3, exact edges in simulation) and PWMAverage, each integrated;
#   * an Encoder on the S-curve position, an ADC on a sine and a code-mode DAC on the ADC
#     code (sampled and quantized: C and simulation agree exactly at the common ticks);
#   * a PowerAmplifier commanded through PWMAverage into an RL load, and an HBridge on a
#     24 V bus into an RL load, both continuous states of the C solver.
# The export compiles with gcc -std=c99 -Wall -Wextra -Werror, runs, matches the Julia
# simulation (discrete and quantized signals bit for bit, continuous ones within the
# fixed-step tolerance), repeats bit for bit after bg_reset, and the FMU does not allocate
# after instantiate.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using Test
using BGSim
using .BondGraphGolden
import BGSim.IR
import BGSim.Compile

const _EXM = BGSim.Export

const _EXM_RUNNER = raw"""
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

function _exm_run_c(cc, dir, report, n)
    src = joinpath(dir, "sources")
    runner = joinpath(dir, "runner.c")
    write(runner, _EXM_RUNNER)
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

# The profiles: block, parameters, its closed form q(t) and its switch times.
function _exm_profiles()
    cyc(t) = t < 0.1 ? 0.0 : t >= 0.7 ? 1.0 :
             (x = (t - 0.1) / 0.6; x - sin(2pi * x) / 2pi)
    quint(t) = t < 0.2 ? 0.5 : t >= 0.8 ? -0.5 : (x = (t - 0.2) / 0.6; 0.5 - (10x^3 - 15x^4 + 6x^5))
    harm(t) = t < 0.05 ? 0.0 : t >= 0.55 ? 2.0 : 1.0 - cos(pi * (t - 0.05) / 0.5)
    # Trapezoid 0 -> 1, v_max 2, a_max 8 from 0.1: T_acc 0.25, cruise 0.25.
    trap(t) = t < 0.1 ? 0.0 : t < 0.35 ? 4.0 * (t - 0.1)^2 :
              t < 0.6 ? 0.25 + 2.0 * (t - 0.35) : t < 0.85 ? 1.0 - 4.0 * (0.85 - t)^2 : 1.0
    return [
        ("TrapezoidalProfile", Dict("q_end" => "1.0", "t_start" => "0.1", "v_max" => "2.0",
            "a_max" => "8.0"), trap, [0.1, 0.35, 0.6, 0.85]),
        ("SCurveProfile", Dict("q_end" => "6.0", "v_max" => "10.0", "a_max" => "40.0",
            "j_max" => "400.0", "t_start" => "0.05"), nothing,
            [0.05, 0.15, 0.3, 0.4, 0.65, 0.75, 0.9, 1.0]),
        ("CycloidalProfile", Dict("t_start" => "0.1", "duration" => "0.6"), cyc, [0.1, 0.7]),
        ("PolynomialProfile", Dict("q_start" => "0.5", "q_end" => "-0.5", "t_start" => "0.2",
            "duration" => "0.6"), quint, [0.2, 0.8]),
        ("HarmonicProfile", Dict("q_end" => "2.0", "t_start" => "0.05", "duration" => "0.5"),
            harm, [0.05, 0.55]),
    ]
end

function _exm_model()
    nodes, conns = Any[], Any[]
    node(id, name, ref; p...) = push!(nodes, bg_node(id, name, bg_ref(ref);
        params = Dict{String,Any}(String(k) => v for (k, v) in p)))
    conn(id, kind, a, pa, b, pb) = push!(conns, bg_conn(id, kind, a, pa, b, pb))
    for (i, (block, params, _, _)) in enumerate(_exm_profiles())
        push!(nodes, bg_node("p$i", "P$i", bg_ref("stdlib:motion/" * block);
            params = Dict{String,Any}(params)))
        node("iv$i", "IV$i", "stdlib:continuous/Integrator")
        conn("cv$i", "signal", "p$i", "v", "iv$i", "u")
    end
    # PWM and its average on the same constant duty.
    node("duty", "DUTY", "stdlib:sources/Constant"; value = "0.3")
    node("pwm", "PWM1", "stdlib:motion/PWM"; frequency = "10.0")
    node("ipwm", "IPWM", "stdlib:continuous/Integrator")
    node("avg", "AVG", "stdlib:motion/PWMAverage"; low = "-1.0", high = "1.0")
    node("iavg", "IAVG", "stdlib:continuous/Integrator")
    conn("cd1", "signal", "duty", "y", "pwm", "u")
    conn("cd2", "signal", "pwm", "y", "ipwm", "u")
    conn("cd3", "signal", "duty", "y", "avg", "u")
    conn("cd4", "signal", "avg", "y", "iavg", "u")
    # Encoder on the S-curve (6 rad), ADC on a sine, DAC on the ADC code.
    node("enc", "ENC", "stdlib:motion/Encoder"; cpr = "64")
    conn("ce", "signal", "p2", "q", "enc", "u")
    node("sine", "SINE", "stdlib:sources/Sine"; amplitude = "1.2", frequency = "9.0")
    node("adc", "ADC1", "stdlib:motion/ADC"; bits = "4", u_min = "-1.0", u_max = "1.0")
    node("dac", "DAC1", "stdlib:motion/DAC"; bits = "4", y_min = "-1.0", y_max = "1.0", input = "1")
    conn("ca1", "signal", "sine", "y", "adc", "u")
    conn("ca2", "signal", "adc", "code", "dac", "u")
    # The amplifier on the PWM average into R + L, with the current limit active.
    node("amp", "AMP", "stdlib:motion/PowerAmplifier"; gain = "12.0", V_max = "10.0",
        R_out = "0.2", I_max = "2.0", R_limit = "20.0")
    node("la", "LA", "stdlib:electrical/Inductor"; L = "0.01")
    node("ra", "RA", "stdlib:electrical/Resistor"; R = "2.0")
    node("g", "G", "stdlib:electrical/Ground")
    conn("cm1", "signal", "avg", "y", "amp", "u")
    conn("cm2", "wire", "amp", "p", "la", "p")
    conn("cm3", "wire", "la", "n", "ra", "p")
    conn("cm4", "wire", "ra", "n", "g", "p")
    conn("cm5", "wire", "amp", "n", "g", "p")
    # The H-bridge on a 24 V bus, its duty the cycloidal position (0 .. 1).
    node("one", "ONE", "stdlib:sources/Constant")
    node("vb", "VBUS", "stdlib:electrical/VoltageSource"; V = "24.0")
    node("hb", "HB", "stdlib:motion/HBridge")
    node("lh", "LH", "stdlib:electrical/Inductor"; L = "0.02")
    node("rh", "RH", "stdlib:electrical/Resistor"; R = "4.0")
    conn("ch1", "signal", "one", "y", "vb", "u")
    conn("ch2", "wire", "vb", "p", "hb", "dc_p")
    conn("ch3", "wire", "vb", "n", "g", "p")
    conn("ch4", "wire", "hb", "dc_n", "g", "p")
    conn("ch5", "wire", "hb", "out_n", "g", "p")
    conn("ch6", "signal", "p3", "q", "hb", "duty")
    conn("ch7", "wire", "hb", "out_p", "lh", "p")
    conn("ch8", "wire", "lh", "n", "rh", "p")
    conn("ch9", "wire", "rh", "n", "g", "p")
    # One ExportOutput, so the FMU wrapper has an output for the allocation harness.
    node("y1", "Y1", "stdlib:converters/ExportOutput")
    conn("cy", "signal", "amp", "i", "y1", "u")
    return bg_model("MotionExport", nodes, conns; t_end = 1.0, points = 101)
end

@testset "motion profiles and drive electronics in the C export" begin
    doc = _exm_model()
    flat = Compile.flatten(IR.parse_model(doc))
    @test isempty([d for d in flat.diagnostics if d.severity == "error"])

    dir = mktempdir()
    r = _EXM.export_model(flat, dir;
        settings = _EXM.ExportSettings(t_end = 1.0, dt = 1e-3, expose_all = true))
    @test r.ok
    @test isempty([d for d in r.diagnostics if d.severity == "error"])
    @test any(d -> d.code == "W203", r.diagnostics)

    cc = Sys.which("gcc")
    if cc === nothing
        @info "export: no gcc on PATH, the motion compile-and-run checks are skipped"
    else
        n = 1000
        rows, xn, yn = _exm_run_c(cc, dir, r.report, n)
        @test size(rows, 1) == n + 1
        t = rows[:, 1]
        @test t ≈ (0:n) .* 1e-3
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        @test !any(d -> d.code == "W206", result.diagnostics)
        col(name) = (j = findfirst(==(name), yn); j === nothing ? nothing : rows[:, 1 + length(xn) + j])
        xcol(prefix) = rows[:, 1 + findfirst(n -> startswith(n, prefix), xn)]
        grid = 1:10:n + 1                                  # the simulation's 0.01 s grid
        for (i, (block, _, ref, breaks)) in enumerate(_exm_profiles())
            @testset "$block" begin
                away(tk) = all(abs(tk - b) > 1e-9 for b in breaks)
                for out in ("q", "v", "a")
                    y = col("P$i/$out")
                    @test y !== nothing
                    # C and the simulation agree at the common grid times.
                    @test maximum(abs(y[k] - bg_value(columns, "P$i/$out", t[k]))
                                  for k in grid if away(t[k])) < 1e-9
                end
                if ref !== nothing
                    q = col("P$i/q")
                    @test maximum(abs(q[k] - ref(t[k])) for k in 1:n + 1 if away(t[k])) < 1e-9
                end
                # The end position is exact in C as well.
                @test col("P$i/q")[end] == bg_value(columns, "P$i/q", 1.0)
                # The integral of v is q - q_start within the frozen-mode error.
                q0 = col("P$i/q")[1]
                @test maximum(abs.(xcol("IV$i/") .- (col("P$i/q") .- q0))) < 2e-3
            end
        end
        @testset "PWM and PWMAverage" begin
            y = col("PWM1/y")
            frac(tk) = tk / 0.1 - floor(tk / 0.1 + 1e-9)
            edges = sort(vcat(0:0.1:1, 0.03:0.1:1))
            away = [k for k in 1:n + 1 if all(abs(t[k] - e) > 1e-9 for e in edges)]
            @test all(y[k] == (frac(t[k]) < 0.3 ? 1.0 : 0.0) for k in away)
            @test all(y[k] == bg_value(columns, "PWM1/y", t[k]) for k in grid if k in away)
            # The duty over a second: 0.3 in simulation, within one step per edge in C.
            @test bg_value(columns, "IPWM/y", 1.0) ≈ 0.3 atol = 1e-8
            @test abs(xcol("IPWM/")[end] - 0.3) < 20 * 1e-3
            @test maximum(abs.(col("AVG/y") .+ 0.4)) < 1e-15
            @test xcol("IAVG/")[end] ≈ -0.4 atol = 1e-12
        end
        @testset "Encoder, ADC and DAC (exact)" begin
            for name in ("ENC/counts", "ENC/y", "ENC/index", "ADC1/code", "ADC1/y", "DAC1/y")
                y = col(name)
                @test y !== nothing
                @test all(y[k] == bg_value(columns, name, t[k]) for k in grid)
            end
            @test col("ENC/counts")[end] == floor(6.0 * 64 / 6.283185307179586)
            @test col("DAC1/y") == col("ADC1/y")
            @test maximum(col("ADC1/code")) == 15.0 && minimum(col("ADC1/code")) == 0.0
        end
        @testset "PowerAmplifier and HBridge (continuous)" begin
            for name in ("AMP/i", "AMP/v", "HB/i", "HB/i_dc")
                y = col(name)
                @test y !== nothing
                scale = maximum(abs.(y))
                @test maximum(abs(y[k] - bg_value(columns, name, t[k])) for k in grid) < 1e-2 * scale
            end
            # -0.4*12 = -4.8 V into 2.2 Ohm would be -2.18 A: the fold-back limit holds it.
            @test col("AMP/i")[end] ≈ (-4.8 - 20.0 * 2.0) / 22.2 rtol = 1e-3
            @test col("HB/i")[end] ≈ 24.0 / 4.01 rtol = 1e-3
        end
        # A second run of the C model (bg_reset, as fmi2Reset) repeats the first bit for bit.
        rows2, _, _ = _exm_run_c(cc, dir, r.report, n)
        @test rows2 == rows

        @testset "builds with -Werror and does not allocate after instantiate" begin
            src = joinpath(dir, "sources")
            files = [joinpath(src, f) for f in ("model.c", "bg_solver.c", "bg_intrinsics.c",
                "bg_mech.c", "fmi2_cs.c") if isfile(joinpath(src, f))]
            for f in files
                @test success(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -I $src -c $f -o $(joinpath(dir, "x.o"))`)
            end
            harness = joinpath(_EXM.RUNTIME_DIR, "alloc_check.c")
            exe = joinpath(dir, Sys.iswindows() ? "check.exe" : "check")
            @test success(`$cc -std=c11 -O2 -I $src $harness $files -o $exe -lm`)
            out = read(`$exe 1 1000`, String)
            @test occursin("after instantiate 0", out)
        end
    end
end
