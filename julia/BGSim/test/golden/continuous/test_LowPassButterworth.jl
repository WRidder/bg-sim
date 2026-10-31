# Golden test for `stdlib:continuous/LowPassButterworth`, through the real pipeline.
#
# The steady-state amplitude of a unit sine through the filter is |H(jw)| =
# 1/sqrt(1 + (w/wc)^(2n)) for every order n: 1/sqrt(2) at the cutoff and
# 1/sqrt(1 + 4^n) at twice the cutoff. The amplitude is a least-squares fit over the last
# 10 s of a 40 s run, when the slowest pole (real part -wc sin(pi/2n)) has decayed. The DC
# gain is k: a step settles at k.
if !isdefined(@__MODULE__, :sb_node)
    include(joinpath(@__DIR__, "signal_helpers.jl"))
end
using Test

@testset "golden: LowPassButterworth" begin
    wc = 4.0
    orders = (1, 2, 3, 4, 5, 8)
    nodes = Any[sb_sine("S1", "$wc"), sb_sine("S2", "$(2wc)")]
    wires = Any[]
    for n in orders, (j, src) in enumerate(("S1", "S2"))
        id = "F$(n)_$j"
        push!(nodes, sb_node(id, "continuous/LowPassButterworth"; params = Dict("wc" => "$wc"),
            consts = Dict("n" => n)))
        push!(wires, (src, "y", id, "u"))
    end
    columns, result, _ = sb_run("ButterworthAmplitudes", nodes, wires; t_end = 40.0, points = 4001)
    @test result.status == "done"
    for n in orders
        @test isapprox(sb_amplitude(columns, "F$(n)_1/y", wc, 30.0), 1 / sqrt(2); rtol = 1e-5)
        @test isapprox(sb_amplitude(columns, "F$(n)_2/y", 2wc, 30.0), 1 / sqrt(1 + 4.0^n); rtol = 1e-4)
    end

    columns, result, _ = sb_run("ButterworthStep",
        [sb_step("S"), sb_node("F", "continuous/LowPassButterworth";
            params = Dict("wc" => "10.0", "k" => "2.5"), consts = Dict("n" => 6))],
        [("S", "y", "F", "u")]; t_end = 10.0)
    @test result.status == "done"
    @test isapprox(bg_value(columns, "F/y", 10.0), 2.5; atol = 1e-6)
    # A Butterworth step overshoots (about 14 % at order 6).
    @test 0.10 < maximum(columns["F/y"]) / 2.5 - 1 < 0.20
end
