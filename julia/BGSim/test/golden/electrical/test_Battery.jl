# Golden test for `stdlib:electrical/Battery`, through the real pipeline.
#
# Model: a `CurrentSource` (I*u, u = 1) draws a constant current I_d out of the battery's p
# terminal (I_d < 0 charges it). With the charging current i = p.f = -I_d:
#
#   soc(t) = soc0 + i*t/(3600*capacity)                    (capacity in A*h)
#   v1(t)  = i*R1*(1 - exp(-t/(R1*C1)))                    (the RC pair, v1(0) = 0)
#   v(t)   = ocv(soc(t)) + R0*i + v1(t),                   ocv piecewise linear in soc.
#
# The capacity is small (0.01 A*h) so the discharge crosses the 0.9 and 0.5 breakpoints of
# the default OCV table within 20 s. Power: what enters the terminals is the chemical power
# ocv*i, the RC storage rate C1*v1*v1' and the heat R0*i^2 + v1^2/R1 >= 0.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

const BAT_SOC = [0.0, 0.1, 0.5, 0.9, 1.0]
const BAT_OCV = [3.0, 3.45, 3.7, 4.0, 4.2]

function battery_ocv(soc)
    soc <= BAT_SOC[1] && return BAT_OCV[1]
    soc >= BAT_SOC[end] && return BAT_OCV[end]
    j = findlast(x -> x <= soc, BAT_SOC)
    return BAT_OCV[j] + (BAT_OCV[j + 1] - BAT_OCV[j]) * (soc - BAT_SOC[j]) /
                        (BAT_SOC[j + 1] - BAT_SOC[j])
end

function battery_model(I_d, soc0)
    return bg_model(
        "BatteryConstantCurrent",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "I1", bg_ref("stdlib:electrical/CurrentSource");
                params = Dict{String,Any}("I" => string(I_d))),
            bg_node("n3", "B1", bg_ref("stdlib:electrical/Battery");
                params = Dict{String,Any}("capacity" => "0.01", "R0" => "0.05",
                    "R1" => "0.02", "C1" => "1000.0"),
                starts = Dict{String,Any}("soc" => string(soc0))),
            bg_node("n4", "G1", bg_ref("stdlib:electrical/Ground")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "p", "n3", "p"),
            bg_conn("c3", "wire", "n2", "n", "n4", "p"),
            bg_conn("c4", "wire", "n3", "n", "n4", "p"),
        ];
        t_end = 20.0, points = 201,
    )
end

@testset "golden: Battery" begin
    R0 = 0.05
    R1 = 0.02
    C1 = 1000.0
    Q = 0.01 * 3600.0
    for (I_d, soc0) in ((1.0, 1.0), (-0.5, 0.3))
        i = -I_d
        columns, result, flat = bg_run(battery_model(I_d, soc0))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        @test flat.stats.states == 2
        soc(t) = soc0 + i * t / Q
        v1(t) = i * R1 * (1 - exp(-t / (R1 * C1)))
        for t in (0.0, 1.0, 3.6, 5.0, 10.0, 17.9, 20.0)
            v = battery_ocv(soc(t)) + R0 * i + v1(t)
            @test isapprox(bg_value(columns, "B1/soc", t), soc(t); rtol = 1e-9)
            @test isapprox(bg_value(columns, "B1/v1", t), v1(t); rtol = 1e-6, atol = 1e-12)
            @test isapprox(bg_value(columns, "B1/ocv", t), battery_ocv(soc(t)); rtol = 1e-9)
            @test isapprox(bg_value(columns, "B1/p.e", t), v; rtol = 1e-6)
            @test isapprox(bg_value(columns, "B1/p.f", t), i; rtol = 1e-12)
            # Power balance: terminal power = chemical + RC storage + heat (heat >= 0).
            p = bg_value(columns, "B1/p.P", t) + bg_value(columns, "B1/n.P", t)
            dv1 = (i - v1(t) / R1) / C1
            heat = R0 * i^2 + v1(t)^2 / R1
            @test heat >= 0.0
            @test isapprox(p, battery_ocv(soc(t)) * i + C1 * v1(t) * dv1 + heat; rtol = 1e-6)
        end
    end
end
