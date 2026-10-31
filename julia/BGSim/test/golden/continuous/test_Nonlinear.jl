# Golden test for `stdlib:continuous/Polynomial`, `WrapToPi` and `Rounding`, through the real
# pipeline: memoryless maps of a ramp u = -4 + 8t on [0, 1] and of constants, against Julia's
# evalpoly, rem2pi and floor/ceil/round/trunc. The jumps of WrapToPi and Rounding are exact
# events, so every grid value away from a jump equals the reference exactly or to rounding.
if !isdefined(@__MODULE__, :sb_node)
    include(joinpath(@__DIR__, "signal_helpers.jl"))
end
using Test

@testset "golden: Polynomial, WrapToPi, Rounding" begin
    modes = (0 => floor, 1 => ceil, 2 => x -> round(x, RoundNearestTiesAway), 3 => trunc)
    nodes = Any[sb_ramp("R", "8.0", "-4.0"),
        sb_node("P", "continuous/Polynomial"; consts = Dict("N" => 4),
            params = Dict("p" => "[0.5, -1.0, 2.0, -3.0]")),
        sb_node("W", "continuous/WrapToPi")]
    wires = Any[("R", "y", "P", "u"), ("R", "y", "W", "u")]
    for (m, _) in modes
        push!(nodes, sb_node("Q$m", "continuous/Rounding"; params = Dict("mode" => "$m")))
        push!(wires, ("R", "y", "Q$m", "u"))
    end
    columns, result, _ = sb_run("NonlinearMaps", nodes, wires; t_end = 1.0, points = 101)
    @test result.status == "done"
    for t in 0.0:0.01:1.0
        u = -4 + 8t
        @test isapprox(bg_value(columns, "P/y", t), evalpoly(u, (-3.0, 2.0, -1.0, 0.5)); atol = 1e-12)
        abs(abs(u) - pi) > 1e-6 && @test isapprox(bg_value(columns, "W/y", t), rem2pi(u, RoundNearest); atol = 1e-12)
        for (m, f) in modes
            # Away from the jumps (the integers, and the half-integers for round).
            abs(u - round(u)) > 1e-9 && abs(abs(u - floor(u)) - 0.5) > 1e-9 &&
                @test bg_value(columns, "Q$m/y", t) == f(u)
        end
    end
    @test all(-pi .< columns["W/y"] .<= pi)

    # Edges: WrapToPi maps both pi and -pi to pi; the rounding modes on -2.5 and 2.5.
    values = ("3.141592653589793", "-3.141592653589793", "-2.5", "2.5", "7.0")
    nodes = Any[sb_node("Int", "continuous/Integrator"), sb_const("One", "1.0")]
    wires = Any[("One", "y", "Int", "u")]
    for (i, v) in enumerate(values)
        push!(nodes, sb_const("C$i", v), sb_node("W$i", "continuous/WrapToPi"))
        push!(wires, ("C$i", "y", "W$i", "u"))
        for (m, _) in modes
            push!(nodes, sb_node("Q$(i)_$m", "continuous/Rounding"; params = Dict("mode" => "$m")))
            push!(wires, ("C$i", "y", "Q$(i)_$m", "u"))
        end
    end
    columns, result, _ = sb_run("NonlinearEdges", nodes, wires)
    @test result.status == "done"
    @test bg_value(columns, "W1/y", 0.5) == Float64(pi)
    @test bg_value(columns, "W2/y", 0.5) == Float64(pi)
    @test isapprox(bg_value(columns, "W5/y", 0.5), 7.0 - 2pi; atol = 1e-14)
    @test [bg_value(columns, "Q3_$m/y", 0.5) for m in 0:3] == [-3.0, -2.0, -3.0, -2.0]
    @test [bg_value(columns, "Q4_$m/y", 0.5) for m in 0:3] == [2.0, 3.0, 3.0, 2.0]
end
