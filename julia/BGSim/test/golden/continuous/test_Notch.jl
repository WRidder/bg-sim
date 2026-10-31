# Golden test for `stdlib:continuous/Notch`, through the real pipeline.
#
# H(s) = k (s^2 + depth*bw*s + w0^2) / (s^2 + bw*s + w0^2): the steady-state amplitude of a
# unit sine at w is |H(jw)| (least-squares fit over the last 10 s of a 30 s run). At w0 the
# gain is k*depth (0 for an ideal notch); at the band edges of depth 0, w = sqrt(w0^2 +
# bw^2/4) -/+ bw/2, it is k/sqrt(2).
if !isdefined(@__MODULE__, :sb_node)
    include(joinpath(@__DIR__, "signal_helpers.jl"))
end
using Test

_notch_gain(k, w0, bw, depth, w) =
    k * abs(complex(w0^2 - w^2, depth * bw * w)) / abs(complex(w0^2 - w^2, bw * w))

@testset "golden: Notch" begin
    w0, bw = 10.0, 2.0
    edge = sqrt(w0^2 + bw^2 / 4) + bw / 2
    cases = [("A", w0, 1.0, 0.0), ("B", w0, 2.0, 0.1), ("C", edge, 1.0, 0.0), ("D", 3.0, 1.5, 0.0),
        ("E", 25.0, 1.0, 0.3)]
    nodes = Any[]
    wires = Any[]
    for (id, w, k, depth) in cases
        push!(nodes, sb_sine("S" * id, "$w"))
        push!(nodes, sb_node(id, "continuous/Notch";
            params = Dict("w0" => "$w0", "bandwidth" => "$bw", "k" => "$k", "depth" => "$depth")))
        push!(wires, ("S" * id, "y", id, "u"))
    end
    columns, result, _ = sb_run("NotchAmplitudes", nodes, wires; t_end = 30.0, points = 6001)
    @test result.status == "done"
    for (id, w, k, depth) in cases
        @test isapprox(sb_amplitude(columns, id * "/y", w, 20.0), _notch_gain(k, w0, bw, depth, w);
            atol = 1e-6)
    end
    @test _notch_gain(1.0, w0, bw, 0.0, edge) ≈ 1 / sqrt(2)
end
