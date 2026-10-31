# Work package J-EX9: seeded noise and the delay ring in simulation and in the exported C code
# (plan/EXPORT_PLAN.md, J-EX9; spec "Seeded noise and delay").
#
# 1. Golden, bitwise: `bg_noise_uniform`/`bg_noise_normal` of bg_intrinsics.c against the
#    Julia functions the simulator runs, for several seeds (zero, negative, large) and sample
#    ranges (the first samples, negative and large indices). The acceptance of J-EX9 is a
#    bit-identical sequence, so the comparison is `==` on the bit patterns, not a tolerance.
# 2. A model with a Noise source, an IntegerDelay of the noise and the delay differential
#    equation x' = -x(t - 0.5) (Integrator, TransportDelay, Gain) is simulated, exported,
#    compiled with -std=c99 -Wall -Wextra -Werror (and model.c as C++17), and stepped in C:
#    the held noise sample and the delayed noise equal the simulation bit for bit at every
#    millisecond, and the continuous DDE state matches the simulation and the method-of-steps
#    solution within the integrator's tolerance.
# 3. fmi2Reset (bg_reset) empties the rings: a second run repeats the first bit for bit.

if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using Test
using BGSim
using .BondGraphGolden

const _JX = BGSim.Export

_jxhex(x) = string(reinterpret(UInt64, Float64(x)); base = 16, pad = 16)
_jxval(s) = reinterpret(Float64, parse(UInt64, s; base = 16))

const _JX_STEPPER = """
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "model.h"
static bg_model m;
static void put(double x) {
    uint64_t b;
    memcpy(&b, &x, sizeof b);
    printf(" %016llx", (unsigned long long)b);
}
/* stepper <steps per print> <prints> <runs>: prints every output after each block of steps;
   each run starts with bg_reset, as fmi2Reset does. */
int main(int argc, char **argv) {
    long per = 1, prints = 0, runs = 1, r, k, j;
    int i;
    if (argc > 3) { sscanf(argv[1], "%ld", &per); sscanf(argv[2], "%ld", &prints); sscanf(argv[3], "%ld", &runs); }
    for (r = 0; r < runs; ++r) {
        bg_reset(&m, 0.0);
        for (k = 0; k <= prints; ++k) {
            if (k > 0) {
                for (j = 0; j < per; ++j) {
                    if (bg_step(&m) != 0) { printf("step failed\\n"); return 3; }
                }
            }
            bg_update_outputs(&m);
            printf("%ld", k);
            for (i = 0; i < BG_NY; ++i) put(m.y[i]);
            printf("\\n");
        }
    }
    return 0;
}
"""

function _jx_model()
    noise = bg_node("n1", "Noise1", bg_ref("stdlib:sources/Noise");
        params = Dict{String,Any}("mean" => "0.3", "std" => "2.0", "seed" => "7"))
    noise["constants"] = Dict{String,Any}("sample_time" => 1.0e-3)
    id = bg_node("n2", "ID", bg_ref("stdlib:discrete/IntegerDelay"))
    id["constants"] = Dict{String,Any}("N" => 4, "sample_period" => 1.0e-3)
    td = bg_node("n4", "TD", bg_ref("stdlib:continuous/TransportDelay");
        params = Dict{String,Any}("initial" => "1.0"))
    td["constants"] = Dict{String,Any}("delay_time" => 0.5, "sample_period" => 1.0e-3)
    nodes = Any[
        noise, id,
        bg_node("n3", "I", bg_ref("stdlib:continuous/Integrator");
            starts = Dict{String,Any}("x" => "1.0")),
        td,
        bg_node("n5", "G", bg_ref("stdlib:continuous/Gain");
            params = Dict{String,Any}("k" => "-1.0")),
        bg_node("n6", "Y1", bg_ref("stdlib:converters/ExportOutput")),
        bg_node("n7", "Y2", bg_ref("stdlib:converters/ExportOutput")),
    ]
    conns = Any[
        bg_conn("c1", "signal", "n1", "y", "n2", "u"),
        bg_conn("c2", "signal", "n3", "y", "n4", "u"),
        bg_conn("c3", "signal", "n4", "y", "n5", "u"),
        bg_conn("c4", "signal", "n5", "y", "n3", "u"),
        bg_conn("c5", "signal", "n2", "y", "n6", "u"),
        bg_conn("c6", "signal", "n3", "y", "n7", "u"),
    ]
    return bg_model("NoiseAndDelay", nodes, conns; t_end = 1.0, points = 1001)
end

function _jx_dde(t)
    t <= 0.5 && return 1.0 - t
    s = t - 0.5
    return 0.5 - s + s^2 / 2
end

@testset "export noise and delay (J-EX9)" begin
    cc = Sys.which("gcc")
    if cc === nothing
        @info "export noise and delay: no gcc on PATH, the C tests are skipped"
    else
        dir = mktempdir()
        rt = _JX.RUNTIME_DIR

        @testset "golden: the noise streams are bit-identical in C" begin
            exe = joinpath(dir, Sys.iswindows() ? "driver.exe" : "driver")
            @test success(`$cc -std=c99 -O2 -Wall -Wextra -Werror -fno-math-errno -I $rt
                $(joinpath(@__DIR__, "export_intrinsics_driver.c")) $(joinpath(rt, "bg_intrinsics.c"))
                $(joinpath(rt, "bg_mech.c")) -o $exe -lm`)
            seeds = (0, 1, 7, -1, 123456789, -(2^40) + 3, 2^62 + 2048)  # exact as doubles
            ranges = (0:4999, -50:-1, (2^52 - 100):(2^52 - 1), 10^12:(10^12 + 49))
            cases = Tuple{String,Float64}[]
            for s in seeds, r in ranges, k in r
                push!(cases, ("bg_noise_normal $(_jxhex(s)) $(_jxhex(k))", BGSim.bg_noise_normal(s, k)))
                k in 0:999 && push!(cases,
                    ("bg_noise_uniform $(_jxhex(s)) $(_jxhex(k))", BGSim.bg_noise_uniform(s, k)))
            end
            # Not an integer: NaN in both.
            push!(cases, ("bg_noise_normal $(_jxhex(1.5)) $(_jxhex(0))", NaN))
            push!(cases, ("bg_noise_uniform $(_jxhex(1)) $(_jxhex(Inf))", NaN))
            input = joinpath(dir, "noise.txt")
            open(io -> foreach(c -> println(io, c[1]), cases), input, "w")
            lines = split(chomp(read(pipeline(`$exe`; stdin = input), String)), '\n')
            @test length(lines) == length(cases)
            mismatch = 0
            tails = 0
            for (k, (line, ref)) in enumerate(cases)
                c = _jxval(strip(lines[k]))
                same = isnan(ref) ? isnan(c) : reinterpret(UInt64, c) == reinterpret(UInt64, ref)
                same || (mismatch += 1)
                abs(ref) > 3.3 && (tails += 1)  # the log branch of AS 241 is exercised
            end
            @info "export noise: $(length(cases)) samples compared bitwise, $(mismatch) differ, $(tails) in the tails"
            @test mismatch == 0
            @test tails > 0
        end

        @testset "a model with noise and delays exports and matches bit for bit" begin
            columns, result, flat = bg_run(_jx_model())
            @test result.status == "done"
            out = joinpath(dir, "model")
            r = _JX.export_model(flat, out; settings = _JX.ExportSettings(t_end = 1.0,
                dt = 1.0e-4, step = 1.0e-3, expose_all = true, method = :rk4))
            @test r.ok
            if r.ok
                src = joinpath(out, "sources")
                model_h = read(joinpath(src, "model.h"), String)
                model_c = read(joinpath(src, "model.c"), String)
                @test occursin("#define BG_NRING 503", model_h)    # IntegerDelay 4 + TransportDelay 499
                @test occursin("#define BG_NRINGS 2", model_h)
                @test occursin("bg_noise_normal(", model_c)
                @test occursin("bg_delay_ring(m->ring + ", model_c)
                files = [joinpath(src, f) for f in ("model.c", "bg_solver.c", "bg_intrinsics.c",
                    "bg_mech.c", "fmi2_cs.c")]
                for f in files
                    @test success(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -fno-math-errno -I $src -c $f -o $(joinpath(dir, "x.o"))`)
                end
                cxx = Sys.which("g++")
                if cxx !== nothing
                    @test success(`$cxx -x c++ -std=c++17 -fsyntax-only -Wall -Werror -I $src $(joinpath(src, "model.c"))`)
                end
                stepper = joinpath(dir, "stepper.c")
                write(stepper, _JX_STEPPER)
                sexe = joinpath(dir, Sys.iswindows() ? "stepper.exe" : "stepper")
                @test success(`$cc -std=c99 -O2 -I $src $stepper $(files[1:4]) -o $sexe -lm`)
                per = round(Int, 1.0e-3 / r.report["dt"])
                rows = split(chomp(read(`$sexe $per 1000 2`, String)), '\n')
                @test length(rows) == 2 * 1001
                names = vcat([o["id"] for o in r.report["outputs"]], r.report["locals"])
                col(name) = findfirst(==(name), names)
                iz, iid, ix = col("Noise1/z"), col("Y1/u"), col("Y2/u")
                @test iz !== nothing && iid !== nothing && ix !== nothing
                vals = [_jxval.(split(row)[2:end]) for row in rows]
                bits_noise = 0
                bits_delay = 0
                worst_sim = 0.0
                worst_exact = 0.0
                repeat_differs = 0
                for k in 0:1000
                    t = k * 1.0e-3
                    v = vals[k + 1]
                    # Held values: equal to the simulation (and the specification) bitwise.
                    zs = k == 0 ? 0.0 : BGSim.bg_noise_normal(7, k - 1)
                    v[iz] == zs && v[iz] == bg_value(columns, "Noise1/z", t) && (bits_noise += 1)
                    v[iid] == bg_value(columns, "ID/y", t) && (bits_delay += 1)
                    worst_sim = max(worst_sim, abs(v[ix] - bg_value(columns, "I/y", t)))
                    worst_exact = max(worst_exact, abs(v[ix] - _jx_dde(t)))
                    # The second run (after bg_reset, i.e. fmi2Reset) repeats the first.
                    vals[k + 1] == vals[k + 1002] || (repeat_differs += 1)
                end
                @info "export noise and delay: $(bits_noise)/1001 noise and $(bits_delay)/1001 delayed samples bit-identical; DDE state max |C - sim| = $(worst_sim), |C - exact| = $(worst_exact)"
                @test bits_noise == 1001
                @test bits_delay == 1001
                @test repeat_differs == 0
                @test worst_sim < 2.0e-6
                @test worst_exact < 2.0e-6
                # The delayed noise really is the noise of 4 ticks ago.
                @test bg_value(columns, "ID/y", 0.010) == 0.3 + 2.0 * BGSim.bg_noise_normal(7, 5)
            end
        end
    end
end
