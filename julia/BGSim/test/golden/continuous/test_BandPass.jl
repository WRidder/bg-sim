# Golden test for `stdlib:continuous/BandPass`, through the real pipeline.
#
# H(s) = k*bw*s / (s^2 + bw*s + w0^2): the steady-state amplitude of a unit sine at w is
# |H(jw)| (least-squares fit over the last 10 s of a 30 s run). The gain is k at w0 and
# k/sqrt(2) at both band edges sqrt(w0^2 + bw^2/4) -/+ bw/2, which are bw apart. A step has
# no DC response: the output returns to zero.
if !isdefined(@__MODULE__, :sb_node)
    include(joinpath(@__DIR__, "signal_helpers.jl"))
end
using Test

_bp_gain(k, w0, bw, w) = k * bw * w / abs(complex(w0^2 - w^2, bw * w))

@testset "golden: BandPass" begin
    w0, bw = 10.0, 2.0
    lo, hi = sqrt(w0^2 + bw^2 / 4) - bw / 2, sqrt(w0^2 + bw^2 / 4) + bw / 2
    cases = [("A", w0, 1.0), ("B", w0, 3.0), ("C", lo, 1.0), ("D", hi, 1.0), ("E", 2.0, 1.0)]
    nodes = Any[sb_step("St"), sb_node("F", "continuous/BandPass"; params = Dict("w0" => "$w0"))]
    wires = Any[("St", "y", "F", "u")]
    for (id, w, k) in cases
        push!(nodes, sb_sine("S" * id, "$w"))
        push!(nodes, sb_node(id, "continuous/BandPass";
            params = Dict("w0" => "$w0", "bandwidth" => "$bw", "k" => "$k")))
        push!(wires, ("S" * id, "y", id, "u"))
    end
    columns, result, _ = sb_run("BandPassAmplitudes", nodes, wires; t_end = 30.0, points = 6001)
    @test result.status == "done"
    for (id, w, k) in cases
        @test isapprox(sb_amplitude(columns, id * "/y", w, 20.0), _bp_gain(k, w0, bw, w); atol = 1e-6)
    end
    @test hi - lo ≈ bw
    @test _bp_gain(1.0, w0, bw, lo) ≈ 1 / sqrt(2)
    @test _bp_gain(1.0, w0, bw, hi) ≈ 1 / sqrt(2)
    @test abs(bg_value(columns, "F/y", 30.0)) < 1e-9
end
