# Golden tests for the smooth signal sources `stdlib:sources/ExpSine`, `Exponentials` and
# `MultiSine`, and for the options added to `Ramp` (duration), `Pulse` (offset)
# and `Chirp` (amplitude, offset, start_phase, logarithmic sweep), through the real
# pipeline. Each source drives an Integrator.
#
# Reference: the analytic waveform; the integrals are the exact areas (Gauss-Legendre on
# pieces between the breakpoints). Tolerance: 1e-9 on the outputs, 1e-8 on the integrals.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
isdefined(@__MODULE__, :SourceGolden) || include(joinpath(@__DIR__, "source_helpers.jl"))
using Test
using .BondGraphGolden
using .SourceGolden

function _sg_check(block, cases, refs, breaks; t_end = 1.5, points = 151, atol_y = 1e-9,
        atol_area = 1e-8)
    columns, result = run_sources(block, cases; t_end = t_end, points = points)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test !any(d -> d.code == "W206", result.diagnostics)
    for i in eachindex(cases)
        ey, ea = source_errors(columns, i, refs[i], breaks[i]; t_end = t_end, points = points)
        @test ey < atol_y
        @test ea < atol_area
    end
    return columns
end

@testset "golden: smooth signal sources" begin
    @testset "ExpSine" begin
        A, w, ph, d, off, t0 = 1.5, 20.0, 0.3, 2.0, 0.1, 0.25
        ref(t) = t < t0 ? off : off + A * exp(-d * (t - t0)) * sin(w * (t - t0) + ph)
        _sg_check("ExpSine", [Dict("amplitude" => string(A), "frequency" => string(w),
                "phase" => string(ph), "damping" => string(d), "offset" => string(off),
                "t_start" => string(t0))], [ref], [[t0]])
    end

    @testset "Exponentials" begin
        A, tr, taur, tauf, off, t0 = 2.0, 0.4, 0.1, 0.2, -0.5, 0.23
        function ref(t)
            t < t0 && return off
            t < t0 + tr && return off + A * (1 - exp(-(t - t0) / taur))
            return off + A * (1 - exp(-tr / taur)) * exp(-(t - t0 - tr) / tauf)
        end
        _sg_check("Exponentials", [Dict("amplitude" => string(A), "rise_time" => string(tr),
                "tau_rise" => string(taur), "tau_fall" => string(tauf),
                "offset" => string(off), "t_start" => string(t0))], [ref], [[t0, t0 + tr]])
    end

    @testset "MultiSine" begin
        amps, ws, phs, off, t0 = [1.0, 0.5, 0.25], [2.0, 7.0, 13.0], [0.0, 0.5, -1.0], 0.2, 0.1
        ref(t) = t < t0 ? off : off + sum(amps[i] * sin(ws[i] * (t - t0) + phs[i]) for i in 1:3)
        vec(v) = "[" * join(v, ", ") * "]"
        _sg_check("MultiSine", [Dict("amplitudes" => vec(amps), "frequencies" => vec(ws),
                "phases" => vec(phs), "offset" => string(off), "t_start" => string(t0))],
            [ref], [[t0]])
    end

    @testset "ExpSine with zero damping is a delayed sine" begin
        A, w, ph, off, t0 = 2.0, 5.0, 0.4, 0.5, 0.3
        ref(t) = t < t0 ? off : off + A * sin(w * (t - t0) + ph)
        _sg_check("ExpSine", [Dict("amplitude" => string(A), "frequency" => string(w),
                "phase" => string(ph), "damping" => "0.0", "offset" => string(off),
                "t_start" => string(t0))], [ref], [[t0]])
    end

    @testset "Ramp duration" begin
        t0, k, y0, dur = 0.2, 3.0, -1.0, 0.5
        ref(t) = t < t0 ? y0 : y0 + k * min(t - t0, dur)
        _sg_check("Ramp", [Dict("t_start" => string(t0), "slope" => string(k),
                "initial" => string(y0), "duration" => string(dur))], [ref], [[t0, t0 + dur]])
    end

    @testset "Pulse offset" begin
        A, p, duty, t0, off = 2.0, 0.37, 0.25, 0.023, -0.5
        ref(t) = (t >= t0 && mod((t - t0) / p, 1.0) < duty) ? off + A : off
        breaks = vcat(edges(t0, p, 1.5), edges(t0 + duty * p, p, 1.5))
        _sg_check("Pulse", [Dict("amplitude" => string(A), "period" => string(p),
                "duty" => string(duty), "t_start" => string(t0), "offset" => string(off))],
            [ref], [breaks])
    end

    @testset "Chirp amplitude, offset, start_phase and the log sweep" begin
        f0, f1, T, A, off, ph = 1.0, 8.0, 1.0, 1.5, 0.25, 0.3
        lin(t) = t <= T ? f0 * t + (f1 - f0) * t^2 / (2T) : f0 * T + (f1 - f0) * T / 2 + f1 * (t - T)
        L = log(f1 / f0)
        lg(t) = t <= T ? f0 * T * (exp(L * t / T) - 1) / L : (f1 - f0) * T / L + f1 * (t - T)
        refs = [t -> off + A * sin(2pi * lin(t) + ph), t -> off + A * sin(2pi * lg(t) + ph)]
        cases = [Dict("f_start" => string(f0), "f_end" => string(f1), "duration" => string(T),
            "amplitude" => string(A), "offset" => string(off), "start_phase" => string(ph),
            "method" => string(m)) for m in (0, 1)]
        _sg_check("Chirp", cases, refs, [[T], [T]]; points = 301, atol_area = 1e-8)
        # The log sweep's instantaneous frequency f0*(f1/f0)^(t/T) is continuous at T.
        @test isapprox(f0 * exp(L), f1; rtol = 1e-14)
    end
end
