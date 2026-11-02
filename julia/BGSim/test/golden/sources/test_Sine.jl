# Golden test for `stdlib:sources/Sine` (Modelica Sources.Sine semantics), through the real
# pipeline. Each Sine drives an Integrator, so the model has a state and the edge at t_start
# is a real event.
#
#   y(t) = offset                                           for t < t_start,
#   y(t) = offset + amplitude*sin(frequency*(t - t_start) + phase)   from t_start on.
#
# Reference: the analytic waveform; the integrals are the exact areas (Gauss-Legendre on the
# pieces either side of t_start). Tolerance: 1e-9 on the outputs, 1e-8 on the integrals.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
isdefined(@__MODULE__, :SourceGolden) || include(joinpath(@__DIR__, "source_helpers.jl"))
using Test
using .BondGraphGolden
using .SourceGolden

@testset "golden: Sine" begin
    @testset "default t_start = 0 is the plain sine, without events" begin
        A, w, ph, off = 2.0, 7.0, 0.4, 0.1
        ref(t) = off + A * sin(w * t + ph)
        columns, result = run_sources("Sine", [Dict("amplitude" => string(A),
                "frequency" => string(w), "phase" => string(ph), "offset" => string(off))];
            t_end = 1.5, points = 151)
        @test result.status == "done"
        @test isempty([d for d in result.diagnostics if d.severity == "error"])
        # The condition t >= 0 holds from the first row on: no event and no extra rows.
        @test result.stats.events == 0
        @test columns["time"] == collect(range(0.0, 1.5; length = 151))
        ey, ea = source_errors(columns, 1, ref, Float64[]; t_end = 1.5, points = 151)
        @test ey < 1e-9
        @test ea < 1e-8
    end

    @testset "t_start on an output time, with a phase jump" begin
        # t_start = 0.3 is an output-grid time (0.01 s grid). The edge is landed exactly once
        # (one event, no W206), and the phase makes the output jump there from offset to
        # offset + amplitude*sin(phase).
        A, w, ph, off, t0 = 2.0, 5.0, 0.4, 0.5, 0.3
        ref(t) = t < t0 ? off : off + A * sin(w * (t - t0) + ph)
        columns, result = run_sources("Sine", [Dict("amplitude" => string(A),
                "frequency" => string(w), "phase" => string(ph), "offset" => string(off),
                "t_start" => string(t0))]; t_end = 1.0, points = 101)
        @test result.status == "done"
        @test isempty([d for d in result.diagnostics if d.severity == "error"])
        @test !any(d -> d.code == "W206", result.diagnostics)
        @test result.stats.events == 1
        times = columns["time"]
        y = bg_all(columns, "S1/y")
        # The solver lands exactly on t_start: the event pair plus the grid row, all at the
        # value after the jump (the condition t >= t_start already holds there, as for a
        # Step on an output time). Every row before t_start is the offset, exactly. The grid
        # row holds the values 1e-12 s after t_start (the run steps past the switching root on
        # it, `_snap_target`), so it is within A * w * 1e-12 of the value at t_start.
        rows = findall(==(t0), times)
        @test length(rows) == 3
        @test all(isapprox.(y[rows], off + A * sin(ph); atol = 1e-10))
        @test all(y[times .< t0] .== off)
        @test y[rows[1] - 1] == off
        ey, ea = source_errors(columns, 1, ref, [t0]; t_end = 1.0, points = 101)
        @test ey < 1e-9
        @test ea < 1e-8
    end

    @testset "t_start between output times, continuous start" begin
        # phase = 0: the output is continuous at t_start (only its slope jumps).
        A, w, off, t0 = 1.5, 20.0, -0.2, 0.2345
        ref(t) = t < t0 ? off : off + A * sin(w * (t - t0))
        columns, result = run_sources("Sine", [Dict("amplitude" => string(A),
                "frequency" => string(w), "offset" => string(off),
                "t_start" => string(t0))]; t_end = 1.0, points = 101)
        @test result.status == "done"
        @test !any(d -> d.code == "W206", result.diagnostics)
        @test result.stats.events == 1
        rows = findall(==(t0), columns["time"])
        @test length(rows) == 2
        @test bg_all(columns, "S1/y")[rows] == [off, off]
        ey, ea = source_errors(columns, 1, ref, [t0]; t_end = 1.0, points = 101)
        @test ey < 1e-9
        @test ea < 1e-8
    end

    @testset "negative t_start shifts the sine" begin
        A, w, ph, t0 = 1.0, 3.0, 0.2, -0.25
        ref(t) = A * sin(w * (t - t0) + ph)
        columns, result = run_sources("Sine", [Dict("amplitude" => string(A),
                "frequency" => string(w), "phase" => string(ph),
                "t_start" => string(t0))]; t_end = 1.0, points = 101)
        @test result.status == "done"
        @test result.stats.events == 0
        ey, ea = source_errors(columns, 1, ref, Float64[]; t_end = 1.0, points = 101)
        @test ey < 1e-9
        @test ea < 1e-8
    end
end
