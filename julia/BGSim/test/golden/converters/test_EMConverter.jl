# Golden test for `stdlib:converters/EMConverter` (plan section 8, M2 row: EM converter
# (gyrator)), through the real pipeline.
#
# Model: a `VoltageSource` at 12 V feeds `p`/`n`; the shaft drives a `RotationalDamper`
# (d = 1e-3) against a `FixedShaft`. The ideal gyrator has
#
#   p.e - n.e = -k*shaft.f,   shaft.e = k*p.f,   p.f + n.f = 0,
#
# so with V = 12 V and k = 0.05 N*m/A: shaft.f = -V/k = -240 rad/s, the damper torque is
# d*shaft.f = -0.24 N*m, shaft.e = +0.24, p.f = shaft.e/k = 4.8 A, and the electrical power
# 12*4.8 = 57.6 W leaves through the shaft at -0.24*(-240) = 57.6 W. Power is conserved.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: EMConverter" begin
    V = 12.0
    k = 0.05
    d = 1.0e-3
    w = -V / k
    torque_shaft = -d * w                  # +0.24 N*m into the converter
    current = -d * w / k                   # +4.8 A into the converter at p

    model = bg_model(
        "EMConverterDrivesDamper",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "V1", bg_ref("stdlib:electrical/VoltageSource");
                params = Dict{String,Any}("V" => string(V))),
            bg_node("n3", "E1", bg_ref("stdlib:converters/EMConverter");
                params = Dict{String,Any}("k" => string(k))),
            bg_node("n4", "D1", bg_ref("stdlib:rotation/RotationalDamper");
                params = Dict{String,Any}("d" => string(d))),
            bg_node("n5", "F1", bg_ref("stdlib:rotation/FixedShaft")),
            bg_node("n6", "G1", bg_ref("stdlib:electrical/Ground")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "p", "n3", "p"),
            bg_conn("c3", "wire", "n2", "n", "n3", "n"),
            bg_conn("c4", "wire", "n3", "shaft", "n4", "a"),
            bg_conn("c5", "wire", "n4", "b", "n5", "a"),
            bg_conn("c6", "wire", "n2", "n", "n6", "p"),
        ];
        t_end = 0.01, points = 11,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 0
    for t in (0.0, 0.005, 0.01)
        @test isapprox(bg_value(columns, "E1/p.e", t) - bg_value(columns, "E1/n.e", t),
            V; rtol = 1e-9)
        @test isapprox(bg_value(columns, "E1/shaft.f", t), w; rtol = 1e-9)
        @test isapprox(bg_value(columns, "D1/a.f", t), w; rtol = 1e-9)
        @test isapprox(bg_value(columns, "D1/a.e", t), d * w; rtol = 1e-9)
        @test isapprox(bg_value(columns, "E1/shaft.e", t), torque_shaft; rtol = 1e-9)
        @test isapprox(bg_value(columns, "E1/p.f", t), current; rtol = 1e-9)
        @test isapprox(bg_value(columns, "E1/n.f", t), -current; rtol = 1e-9)
        # Power: electrical in, mechanical out, and the sum over all ports is zero.
        @test isapprox(bg_value(columns, "V1/p.P", t) + bg_value(columns, "V1/n.P", t),
            -V * current; rtol = 1e-9)
        @test isapprox(bg_value(columns, "E1/p.P", t) + bg_value(columns, "E1/n.P", t),
            V * current; rtol = 1e-9)
        @test isapprox(bg_value(columns, "E1/shaft.P", t), -V * current; rtol = 1e-9)
        @test isapprox(bg_value(columns, "D1/a.P", t), V * current; rtol = 1e-9)
        @test abs(bg_value(columns, "V1/p.P", t) + bg_value(columns, "V1/n.P", t) +
                  bg_value(columns, "E1/p.P", t) + bg_value(columns, "E1/n.P", t) +
                  bg_value(columns, "E1/shaft.P", t) +
                  bg_value(columns, "D1/a.P", t) + bg_value(columns, "D1/b.P", t)) <= 1e-9
    end
end
