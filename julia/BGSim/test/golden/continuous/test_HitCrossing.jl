# Golden test for `stdlib:continuous/HitCrossing`, through the real pipeline.
#
# u = sin(3t) against level 0.5 on [0, 5]: rising crossings at 3t = pi/6 + 2k*pi
# (t = 0.1745, 2.2689, 4.3633), falling ones at 3t = 5pi/6 + 2k*pi (t = 0.8727, 2.9671).
# Each crossing is an exact event: the counts step exactly there and the flag y turns 1 at
# the first crossing in the selected direction. A sine that starts above the level needs
# the start of `side` at 1 to count its first falling crossing.
if !isdefined(@__MODULE__, :sb_node)
    include(joinpath(@__DIR__, "signal_helpers.jl"))
end
using Test

@testset "golden: HitCrossing" begin
    rising = [pi / 18, pi / 18 + 2pi / 3, pi / 18 + 4pi / 3]
    falling = [5pi / 18, 5pi / 18 + 2pi / 3]
    hc(id, dir; starts = Dict{String,Any}()) = sb_node(id, "continuous/HitCrossing";
        params = Dict("level" => "0.5", "direction" => "$dir"), starts = starts)
    columns, result, _ = sb_run("HitCrossingSine",
        [sb_sine("S", "3.0"), hc("E", 0), hc("R", 1), hc("F", 2),
            sb_node("C", "sources/Sine"; params = Dict("frequency" => "3.0", "phase" => "1.5707963267948966")),
            hc("A", 0; starts = Dict{String,Any}("side" => "1.0"))],
        [("S", "y", "E", "u"), ("S", "y", "R", "u"), ("S", "y", "F", "u"), ("C", "y", "A", "u")];
        t_end = 5.0, points = 501)
    @test result.status == "done"
    count(times, t) = Float64(sum(times .< t))
    for t in 0.0:0.01:5.0
        nr, nf = count(rising, t), count(falling, t)
        @test bg_value(columns, "R/n", t) == nr
        @test bg_value(columns, "F/n", t) == nf
        @test bg_value(columns, "E/n", t) == nr + nf
        @test bg_value(columns, "E/n_up", t) == nr
        @test bg_value(columns, "E/n_down", t) == nf
        @test bg_value(columns, "R/y", t) == min(nr, 1.0)
        @test bg_value(columns, "F/y", t) == min(nf, 1.0)
    end
    # The events are located: the run records rows at the crossing instants.
    for tc in vcat(rising, falling)
        @test any(abs.(columns["time"] .- tc) .< 1e-8)
    end
    # cos(3t) starts above 0.5 (side = 1): falling at 3t = pi/3 + 2k*pi, rising at 5pi/3 + 2k*pi.
    @test bg_value(columns, "A/n_down", 0.5) == 1.0
    @test bg_value(columns, "A/n_up", 2.0) == 1.0
    @test bg_value(columns, "A/n", 5.0) == 5.0
end
