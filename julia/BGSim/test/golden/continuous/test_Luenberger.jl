# Golden test for `stdlib:continuous/Luenberger`, through the real pipeline.
#
# The plant is the StateSpace block (A = [0 1; -1 -2], B = [0, 1], C = [1, 0], D = 0, the
# Luenberger defaults), driven by u = sin(5t) from x(0) = 0. The observer starts at
# x_hat(0) = [1, -1], so the estimation error e = x - x_hat obeys e' = (A - L C') e with
# e(0) = [-1, 1]: e(t) = exp((A - L C') t) e(0). With the default gain L = [9, 11] the
# error poles are -5 and -6, and the estimate converges to the plant state.
if !isdefined(@__MODULE__, :sb_node)
    include(joinpath(@__DIR__, "signal_helpers.jl"))
end
using Test
using LinearAlgebra

@testset "golden: Luenberger" begin
    columns, result, _ = sb_run("LuenbergerObserver",
        [sb_sine("S", "5.0"), sb_node("P", "continuous/StateSpace"),
            sb_node("O", "continuous/Luenberger"; starts = Dict("x" => "[1.0, -1.0]"))],
        [("S", "y", "P", "u"), ("S", "y", "O", "u"), ("P", "y", "O", "y")]; t_end = 3.0, points = 301)
    @test result.status == "done"
    A = [0.0 1.0; -1.0 -2.0]
    L = [9.0, 11.0]
    C = [1.0, 0.0]
    M = A - L * C'
    @test sort(real.(eigvals(M))) ≈ [-6.0, -5.0]
    for t in (0.0, 0.1, 0.3, 0.7, 1.5, 3.0)
        e = exp(M * t) * [-1.0, 1.0]
        @test isapprox(bg_value(columns, "P/x[1]", t) - bg_value(columns, "O/x_hat[1]", t), e[1]; atol = 1e-7)
        @test isapprox(bg_value(columns, "P/x[2]", t) - bg_value(columns, "O/x_hat[2]", t), e[2]; atol = 1e-7)
        @test isapprox(bg_value(columns, "P/y", t) - bg_value(columns, "O/y_hat", t), e[1]; atol = 1e-7)
    end
end
