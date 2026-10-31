# Golden test for `stdlib:continuous/LowPassBessel`, through the real pipeline.
#
# Reference, independent of the block's pole table: the Bessel filter of order n is
# H(s) = theta_n(0) / theta_n(s/w0), theta_n the reverse Bessel polynomial with coefficients
# a_k = (2n - k)! / (2^(n-k) k! (n - k)!), and w0 = c*wc with c chosen so that
# |H(j wc)| = 1/sqrt(2) (the -3 dB normalization). The steady-state amplitude of a sine at
# wc and at 2wc must match |H(jw)| (least-squares fit over the last 10 s of a 40 s run). A
# Bessel step barely overshoots (under 1 % for every order) and settles at the DC gain k.
if !isdefined(@__MODULE__, :sb_node)
    include(joinpath(@__DIR__, "signal_helpers.jl"))
end
using Test

function _bessel_gain(n, w)
    a = [factorial(big(2n - k)) / (big(2)^(n - k) * factorial(big(k)) * factorial(big(n - k))) for k in 0:n]
    a = Float64.(a)
    theta(s) = sum(a[k + 1] * s^k for k in 0:n)
    return abs(theta(0.0) / theta(im * w))
end

# The frequency where |H| = 1/sqrt(2) for w0 = 1, by bisection.
function _bessel_c(n)
    lo, hi = 1.0e-3, 10.0
    for _ in 1:200
        mid = (lo + hi) / 2
        _bessel_gain(n, mid) > 1 / sqrt(2) ? (lo = mid) : (hi = mid)
    end
    return (lo + hi) / 2
end

@testset "golden: LowPassBessel" begin
    wc = 4.0
    orders = (1, 2, 3, 4, 6, 8)
    nodes = Any[sb_sine("S1", "$wc"), sb_sine("S2", "$(2wc)")]
    wires = Any[]
    for n in orders, (j, src) in enumerate(("S1", "S2"))
        id = "F$(n)_$j"
        push!(nodes, sb_node(id, "continuous/LowPassBessel"; params = Dict("wc" => "$wc"),
            consts = Dict("n" => n)))
        push!(wires, (src, "y", id, "u"))
    end
    columns, result, _ = sb_run("BesselAmplitudes", nodes, wires; t_end = 40.0, points = 4001)
    @test result.status == "done"
    for n in orders
        c = _bessel_c(n)
        @test isapprox(sb_amplitude(columns, "F$(n)_1/y", wc, 30.0), 1 / sqrt(2); rtol = 1e-5)
        @test isapprox(sb_amplitude(columns, "F$(n)_2/y", 2wc, 30.0), _bessel_gain(n, 2c); rtol = 1e-4)
    end

    nodes = Any[sb_step("S")]
    wires = Any[]
    for n in (2, 3, 5, 8)
        push!(nodes, sb_node("F$n", "continuous/LowPassBessel";
            params = Dict("wc" => "10.0", "k" => "2.5"), consts = Dict("n" => n)))
        push!(wires, ("S", "y", "F$n", "u"))
    end
    columns, result, _ = sb_run("BesselSteps", nodes, wires; t_end = 10.0, points = 2001)
    @test result.status == "done"
    for n in (2, 3, 5, 8)
        @test isapprox(bg_value(columns, "F$n/y", 10.0), 2.5; atol = 1e-6)
        @test maximum(columns["F$n/y"]) / 2.5 - 1 < 0.01
    end
end
