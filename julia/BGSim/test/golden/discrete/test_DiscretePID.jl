# Golden test for `stdlib:discrete/DiscretePID` (plan section 8, M2 row: Discrete PID),
# through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: six PIDs on a 1 ms clock, all with Kp = 1, Ti = 0.5 and a constant error of +1 (the
# first four) or -1 (the last one):
#   F  forward integration, no limits          B  backward integration, no limits
#   T  trapezoidal integration, no limits      U  backward, upper = 1.002 (anti-windup)
#   L  backward, lower = -1.002 (anti-windup)  D  backward, Td = 1 ms (derivative term)
#
# Reference: the block's recurrence with Ts = 1e-3, written out in the test in the same
# operation order as the generated code:
#   delta = Ts*ep | Ts*u | (Ts*(u + ep))/2      i = i + delta
#   d = (u - ep)/Ts                             v = Kp*u + (Kp/Ti)*i + (Kp*Td)*d
#   if v out of range: i = i - delta, recompute v     y = clamp(v, lower, upper)
# so the sequences are bit-exact and compared with `==`.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :dg_model)
    include(joinpath(@__DIR__, "golden_discrete.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: DiscretePID" begin
    Ts = 1.0e-3

    function reference(; method, u = 1.0, Kp = 1.0, Ti = 0.5, Td = 0.0,
        lower = -1.0e30, upper = 1.0e30, n = 8)
        i, ep = 0.0, 0.0
        values, integrals = Float64[0.0], Float64[0.0]
        for _ in 1:n
            if method == 0
                delta = Ts * ep
            elseif method == 1
                delta = Ts * u
            else
                delta = (Ts * (u + ep)) / 2.0
            end
            i = i + delta
            d = (u - ep) / Ts
            v = Kp * u + (Kp / Ti) * i + (Kp * Td) * d
            if v > upper
                i = i - delta
                v = Kp * u + (Kp / Ti) * i + (Kp * Td) * d
            elseif v < lower
                i = i - delta
                v = Kp * u + (Kp / Ti) * i + (Kp * Td) * d
            end
            y = v < lower ? lower : (v > upper ? upper : v)
            push!(values, y)
            push!(integrals, i)
            ep = u
        end
        return values, integrals
    end

    params(; method = 1, Td = "0.0", lower = "-1.0e30", upper = "1.0e30") = Dict{String,Any}(
        "method" => string(method), "Kp" => "1.0", "Ti" => "0.5", "Td" => Td,
        "lower" => lower, "upper" => upper,
    )

    model = dg_model(
        "DiscretePIDMethodsAndLimits",
        [
            dg_node("n1", "CP", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            dg_node("n2", "CN", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "-1.0")),
            dg_node("n3", "F", bg_ref("stdlib:discrete/DiscretePID");
                params = params(method = 0)),
            dg_node("n4", "B", bg_ref("stdlib:discrete/DiscretePID");
                params = params(method = 1)),
            dg_node("n5", "T", bg_ref("stdlib:discrete/DiscretePID");
                params = params(method = 2)),
            dg_node("n6", "U", bg_ref("stdlib:discrete/DiscretePID");
                params = params(method = 1, upper = "1.002")),
            dg_node("n7", "L", bg_ref("stdlib:discrete/DiscretePID");
                params = params(method = 1, lower = "-1.002")),
            dg_node("n8", "D", bg_ref("stdlib:discrete/DiscretePID");
                params = params(method = 1, Td = "0.001")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n3", "u"),
            bg_conn("c2", "signal", "n1", "y", "n4", "u"),
            bg_conn("c3", "signal", "n1", "y", "n5", "u"),
            bg_conn("c4", "signal", "n1", "y", "n6", "u"),
            bg_conn("c5", "signal", "n2", "y", "n7", "u"),
            bg_conn("c6", "signal", "n1", "y", "n8", "u"),
        ];
        t_end = 0.008, points = 9,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0

    grid = dg_grid(0.008; points = 9)
    @test dg_values(columns, "F/y", grid) == reference(method = 0)[1]
    @test dg_values(columns, "B/y", grid) == reference(method = 1)[1]
    @test dg_values(columns, "T/y", grid) == reference(method = 2)[1]
    @test dg_values(columns, "D/y", grid) == reference(method = 1, Td = 0.001)[1]

    # The saturated instances clamp at the limit and the integral does not wind up: the
    # anti-windup step removes the increment again, so `i` stays at the last unsaturating value.
    upper_values, upper_integrals = reference(method = 1, upper = 1.002)
    @test dg_values(columns, "U/y", grid) == upper_values
    @test dg_values(columns, "U/i", grid) == upper_integrals
    @test all(v -> v <= 1.002, upper_values)
    @test bg_value(columns, "U/i", 0.008) == 0.001

    lower_values, _ = reference(method = 1, u = -1.0, lower = -1.002)
    @test dg_values(columns, "L/y", grid) == lower_values
    @test all(v -> v >= -1.002, lower_values)

    # Literal first steps: backward integration adds 0.001 to i and 2*0.001 to the output,
    # the forward one skips the first sample, and the derivative adds the initial kick
    # (Kp*Td)*(u - 0)/Ts = 0.001*1000 = 1.
    @test bg_value(columns, "B/y", 0.001) == 1.002
    @test bg_value(columns, "F/y", 0.001) == 1.0
    @test bg_value(columns, "T/y", 0.001) == 1.001
    @test bg_value(columns, "D/y", 0.001) == 2.002
    @test bg_value(columns, "D/y", 0.002) == 1.004
end
