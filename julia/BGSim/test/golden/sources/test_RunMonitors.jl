# Golden test for `stdlib:sources/StopSimulation` and `stdlib:sources/Assertion`, through the
# real pipeline.
#
# StopSimulation on u = sin(2t) with threshold 0.5 ends the run at the located crossing
# t = pi/12: the recorded rows end there, status "done", and one W217 warning names the
# block and the time. An Assertion on u = cos(2t) with threshold 0.5 fails at t = pi/6:
# status "failed" and one E902 error. An input already past the threshold ends the run at
# t = 0. A copy of the block under another reference is an ordinary block (no monitor).
if !isdefined(@__MODULE__, :sb_node)
    include(joinpath(@__DIR__, "..", "continuous", "signal_helpers.jl"))
end
using Test

@testset "golden: StopSimulation and Assertion" begin
    cosine = sb_node("C", "sources/Sine"; params = Dict("frequency" => "2.0", "phase" => "1.5707963267948966"))
    cases = [
        ("StopSimulation", sb_sine("S", "2.0"), pi / 12, "W217", "done", "warning"),
        ("Assertion", cosine, pi / 6, "E902", "failed", "error"),
    ]
    for (block, src, tc, code, status, severity) in cases
        @testset "$block" begin
            columns, result, _ = sb_run(block * "Run",
                [src, sb_node("Check", "sources/" * block), sb_node("I", "continuous/Integrator")],
                [(src["id"], "y", "Check", "u"), (src["id"], "y", "I", "u")]; t_end = 2.0, points = 201)
            @test result.status == status
            d = only([d for d in result.diagnostics if d.code == code])
            @test d.severity == severity
            @test d.path == "Check"
            @test occursin("`Check`", d.message)
            t_msg = parse(Float64, match(r"t = ([0-9.eE+-]+)", d.message).captures[1])
            @test isapprox(t_msg, tc; atol = 1e-8)
            @test isapprox(columns["time"][end], tc; atol = 1e-8)
            # The integral of the input up to the stop: (1 - cos 2t)/2 resp. sin(2t)/2.
            ref = block == "StopSimulation" ? (1 - cos(2tc)) / 2 : sin(2tc) / 2
            @test isapprox(columns["I/y"][end], ref; atol = 1e-7)
        end
    end

    @testset "triggered at the start" begin
        columns, result, _ = sb_run("StopAtStart",
            [sb_const("K", "1.0"), sb_node("Check", "sources/StopSimulation"), sb_node("I", "continuous/Integrator")],
            [("K", "y", "Check", "u"), ("K", "y", "I", "u")]; t_end = 1.0)
        @test result.status == "done"
        @test only([d for d in result.diagnostics if d.code == "W217"]).path == "Check"
        @test columns["time"][end] == 0.0
        columns, result, _ = sb_run("AssertAtStart",
            [sb_const("K", "0.0"), sb_node("Check", "sources/Assertion"), sb_node("I", "continuous/Integrator")],
            [("K", "y", "Check", "u"), ("K", "y", "I", "u")]; t_end = 1.0)
        @test result.status == "failed"
        @test only([d for d in result.diagnostics if d.code == "E902"]).path == "Check"
    end

    @testset "not triggered" begin
        columns, result, _ = sb_run("NoStop",
            [sb_sine("S", "2.0"; amplitude = "0.4"), sb_node("Stop", "sources/StopSimulation"),
                sb_node("Ok", "sources/Assertion"; params = Dict("threshold" => "-0.5")),
                sb_node("I", "continuous/Integrator")],
            [("S", "y", "Stop", "u"), ("S", "y", "Ok", "u"), ("S", "y", "I", "u")]; t_end = 2.0)
        @test result.status == "done"
        @test !any(d -> d.code in ("W217", "E902"), result.diagnostics)
        @test columns["time"][end] == 2.0
    end
end
