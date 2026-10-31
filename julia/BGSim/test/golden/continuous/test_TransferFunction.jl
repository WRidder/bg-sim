# Golden test for `stdlib:continuous/TransferFunction`, through the real pipeline.
#
# Unit-step responses against the inverse Laplace transforms:
#   2/(s^2 + 3s + 2)        -> 1 - 2e^-t + e^-2t
#   s^2/(s^2 + 3s + 2)      -> -e^-t + 2e^-2t   (direct feedthrough: y(0+) = 1)
#   4/(2s + 2), order 1     -> 2(1 - e^-t)      (den[1] not 1)
#   (s + 3)/(s^3 + 5s^2 + 9s + 5) against the ZeroPole block with the same poles and zero.
if !isdefined(@__MODULE__, :sb_node)
    include(joinpath(@__DIR__, "signal_helpers.jl"))
end
using Test

@testset "golden: TransferFunction" begin
    tf(id, num, den; n = nothing) = sb_node(id, "continuous/TransferFunction";
        params = Dict("num" => num, "den" => den),
        consts = n === nothing ? Dict{String,Any}() : Dict{String,Any}("n" => n))
    columns, result, _ = sb_run("TransferFunctionSteps",
        [sb_step("S"), tf("A", "[0.0, 0.0, 2.0]", "[1.0, 3.0, 2.0]"),
            tf("B", "[1.0, 0.0, 0.0]", "[1.0, 3.0, 2.0]"),
            tf("C", "[0.0, 4.0]", "[2.0, 2.0]"; n = 1)],
        [("S", "y", "A", "u"), ("S", "y", "B", "u"), ("S", "y", "C", "u")]; t_end = 3.0)
    @test result.status == "done"
    for t in (0.1, 0.5, 1.0, 2.0, 3.0)
        @test isapprox(bg_value(columns, "A/y", t), 1 - 2exp(-t) + exp(-2t); atol = 1e-7)
        @test isapprox(bg_value(columns, "B/y", t), -exp(-t) + 2exp(-2t); atol = 1e-7)
        @test isapprox(bg_value(columns, "C/y", t), 2 * (1 - exp(-t)); atol = 1e-7)
    end
    # The canonical states: x[1] is the highest derivative of the internal signal z.
    @test isapprox(bg_value(columns, "A/x[2]", 1.0), 0.5 * (1 - 2exp(-1.0) + exp(-2.0)); atol = 1e-7)

    # Third order against ZeroPole: g(s + 3)/((s + 1)((s + 2)^2 + 1)) with g = 5/3 (DC gain 1).
    g = 5 / 3
    columns, result, _ = sb_run("TransferFunctionVsZeroPole",
        [sb_step("S"), tf("T", "[0.0, 0.0, $g, $(3g)]", "[1.0, 5.0, 9.0, 5.0]"; n = 3),
            sb_node("Z", "continuous/ZeroPole"; consts = Dict("n" => 3, "m" => 1),
                params = Dict("gain" => "$g", "zero_re" => "[-3.0, 0.0, 0.0]",
                    "zero_im" => "[0.0, 0.0, 0.0]", "pole_re" => "[-2.0, -2.0, -1.0]",
                    "pole_im" => "[1.0, -1.0, 0.0]"))],
        [("S", "y", "T", "u"), ("S", "y", "Z", "u")]; t_end = 8.0)
    @test result.status == "done"
    for t in (0.2, 1.0, 2.5, 8.0)
        @test isapprox(bg_value(columns, "T/y", t), bg_value(columns, "Z/y", t); atol = 1e-7)
    end
    @test isapprox(bg_value(columns, "T/y", 8.0), 1.0; atol = 2e-3)
end
