# Golden test for `stdlib:continuous/ZeroPole`, through the real pipeline.
#
# Unit-step responses against the inverse Laplace transforms:
#   6(s + 1)/((s + 2)(s + 3))          (the defaults)  -> 1 + 3e^-2t - 4e^-3t
#   5/((s + 1 - 2j)(s + 1 + 2j))       (a complex pair) -> 1 - e^-t (cos 2t + sin(2t)/2)
#   (s - j)(s + j)/((s + 1)(s + 2))    (m = n, imaginary zeros, direct feedthrough)
#                                                       -> 1/2 - 2e^-t + 5/2 e^-2t
if !isdefined(@__MODULE__, :sb_node)
    include(joinpath(@__DIR__, "..", "continuous", "signal_helpers.jl"))
end
using Test

@testset "golden: ZeroPole" begin
    columns, result, _ = sb_run("ZeroPoleSteps",
        [sb_step("S"), sb_node("A", "continuous/ZeroPole"),
            sb_node("B", "continuous/ZeroPole"; consts = Dict("n" => 2, "m" => 0),
                params = Dict("gain" => "5.0", "pole_re" => "[-1.0, -1.0]", "pole_im" => "[2.0, -2.0]")),
            sb_node("C", "continuous/ZeroPole"; consts = Dict("n" => 2, "m" => 2),
                params = Dict("gain" => "1.0", "zero_re" => "[0.0, 0.0]", "zero_im" => "[1.0, -1.0]",
                    "pole_re" => "[-1.0, -2.0]", "pole_im" => "[0.0, 0.0]"))],
        [("S", "y", "A", "u"), ("S", "y", "B", "u"), ("S", "y", "C", "u")]; t_end = 4.0)
    @test result.status == "done"
    for t in (0.0, 0.1, 0.5, 1.0, 2.0, 4.0)
        @test isapprox(bg_value(columns, "A/y", t), 1 + 3exp(-2t) - 4exp(-3t); atol = 1e-7)
        @test isapprox(bg_value(columns, "B/y", t), 1 - exp(-t) * (cos(2t) + sin(2t) / 2); atol = 1e-7)
        t > 0 && @test isapprox(bg_value(columns, "C/y", t), 0.5 - 2exp(-t) + 2.5exp(-2t); atol = 1e-7)
    end
end
