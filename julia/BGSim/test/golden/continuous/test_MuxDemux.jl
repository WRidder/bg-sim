# Golden test for `stdlib:continuous/Mux2..4`, `Demux2..4` and `MultiportSwitch`, through the
# real pipeline.
#
# Mux packs scalars into a vector and Demux unpacks it unchanged, so every element arrives
# exactly. MultiportSwitch passes u[k], k = index rounded to the nearest integer (halves up)
# and clamped to 1..N: with index = 0.5 + 1.5 t on [0, 2], u[1] until t = 2/3 (index 1.5),
# u[2] until t = 4/3 (index 2.5), then u[3]; each switch is an exact event, so the output
# equals the selected input at every grid time.
if !isdefined(@__MODULE__, :sb_node)
    include(joinpath(@__DIR__, "signal_helpers.jl"))
end
using Test

@testset "golden: Mux, Demux and MultiportSwitch" begin
    nodes = Any[sb_ramp("R", "1.0", "0.0"), sb_sine("S", "2.0"), sb_const("K", "-3.0"),
        sb_const("L", "7.5"), sb_ramp("I", "1.5", "0.5")]
    wires = Any[]
    for n in 2:4
        push!(nodes, sb_node("M$n", "continuous/Mux$n"))
        push!(nodes, sb_node("D$n", "continuous/Demux$n"))
        for (i, src) in enumerate(("R", "S", "K", "L")[1:n])
            push!(wires, (src, "y", "M$n", "u$i"))
        end
        push!(wires, ("M$n", "y", "D$n", "u"))
    end
    push!(nodes, sb_node("W", "continuous/MultiportSwitch"))
    push!(wires, ("I", "y", "W", "index"), ("M3", "y", "W", "u"))
    # Sum takes the Mux vector directly.
    push!(nodes, sb_node("Sum", "continuous/Sum"; consts = Dict("N" => 4),
        params = Dict("signs" => "[1.0, 1.0, 1.0, 1.0]")))
    push!(wires, ("M4", "y", "Sum", "u"))
    columns, result, _ = sb_run("MuxDemuxSwitch", nodes, wires; t_end = 2.0, points = 201)
    @test result.status == "done"
    ref(i, t) = (t, sin(2t), -3.0, 7.5)[i]
    for t in (0.0, 0.33, 1.0, 1.77, 2.0), n in 2:4, i in 1:n
        @test bg_value(columns, "D$n/y$i", t) == ref(i, t)
        @test bg_value(columns, "M$n/y[$i]", t) == ref(i, t)
    end
    @test bg_value(columns, "Sum/y", 1.0) ≈ 1.0 + sin(2.0) - 3.0 + 7.5
    for t in 0.0:0.01:2.0
        k = t < 2 / 3 ? 1 : t < 4 / 3 ? 2 : 3
        abs(t - 2 / 3) < 1e-9 || abs(t - 4 / 3) < 1e-9 || @test bg_value(columns, "W/y", t) == ref(k, t)
    end

    # Clamping: an index below 1 selects u[1], one above N selects u[N].
    columns, result, _ = sb_run("MultiportSwitchClamp",
        [sb_const("A", "1.0"), sb_const("B", "2.0"), sb_const("Lo", "-4.0"), sb_const("Hi", "9.0"),
            sb_node("M", "continuous/Mux2"),
            sb_node("W1", "continuous/MultiportSwitch"; consts = Dict("N" => 2)),
            sb_node("W2", "continuous/MultiportSwitch"; consts = Dict("N" => 2)),
            sb_node("Int", "continuous/Integrator")],
        [("A", "y", "M", "u1"), ("B", "y", "M", "u2"), ("Lo", "y", "W1", "index"), ("Hi", "y", "W2", "index"),
            ("M", "y", "W1", "u"), ("M", "y", "W2", "u"), ("A", "y", "Int", "u")])
    @test result.status == "done"
    @test bg_value(columns, "W1/y", 0.5) == 1.0
    @test bg_value(columns, "W2/y", 0.5) == 2.0
end
