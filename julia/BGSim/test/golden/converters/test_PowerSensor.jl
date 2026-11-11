# Golden test for `stdlib:converters/PowerSensor` (plan section 8, M2 row: Power sensor),
# through the real pipeline.
#
# The sensor is a transparent two-port: `a.e = b.e`, `a.f + b.f = 0` (port flows count into
# the block, so the flow that enters at `a` leaves at `b`), and `y = a.e*a.f`, the power that
# enters at `a`. With the bonds drawn through the sensor (half-arrows into `a`, out of `b`)
# that is the power in the half-arrow direction, in every placement: element -> sensor ->
# element, junction -> sensor -> element and element -> sensor -> junction. Inserting it
# changes nothing else in the model: every other port carries what it carries without it.
#
# Model 1: Sf(-2) -> PowerSensor -> R(3), against Sf(-2) -> R(3). A flow source delivers its
# flow at the tail of its bond (O15), so the bond carries f_b = -2 and the resistor sees
# e = r*f = -6: power 12 W from the source to the resistor.
#   R.p.f = -2, R.p.e = -6, R.p.P = +12 (absorbed), Sf.p.P = -12 (delivered), P1.y = +12.
#
# Model 2: Se(6) -> 1-junction -> PowerSensor -> R(3): the reading follows the half-arrows,
# +12 W into R. The same with the bonds of the sensor reversed (R -> sensor -> junction) read
# -12 W before port orientation; R's port is `in`, so that bond is now refused (E114).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden
import BGSim

@testset "golden: PowerSensor" begin
    f = 2.0
    r = 3.0
    power = r * f * f

    @testset "element -> sensor -> element is transparent" begin
        with_sensor = bg_model(
            "PowerSensorOnGenericBond",
            [
                bg_node("n1", "Sf1", bg_ref("stdlib:bondgraph/Sf");
                    params = Dict{String,Any}("f" => string(-f))),
                bg_node("n2", "P1", bg_ref("stdlib:converters/PowerSensor")),
                bg_node("n3", "R1", bg_ref("stdlib:bondgraph/R");
                    params = Dict{String,Any}("r" => string(r))),
            ],
            [
                bg_conn("c1", "bond", "n1", "p", "n2", "a"),
                bg_conn("c2", "bond", "n2", "b", "n3", "p"),
            ];
            t_end = 0.01, points = 11,
        )
        without = bg_model(
            "SfIntoR",
            [
                bg_node("n1", "Sf1", bg_ref("stdlib:bondgraph/Sf");
                    params = Dict{String,Any}("f" => string(-f))),
                bg_node("n3", "R1", bg_ref("stdlib:bondgraph/R");
                    params = Dict{String,Any}("r" => string(r))),
            ],
            [bg_conn("c1", "bond", "n1", "p", "n3", "p")];
            t_end = 0.01, points = 11,
        )

        columns, result, flat = bg_run(with_sensor)
        ref, ref_result, _ = bg_run(without)
        @test result.status == "done"
        @test ref_result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        @test flat.stats.states == 0
        for t in (0.0, 0.005, 0.01)
            # The rest of the model does not notice the sensor.
            for id in ("R1/p.f", "R1/p.e", "R1/p.P", "Sf1/p.e", "Sf1/p.P")
                @test isapprox(bg_value(columns, id, t), bg_value(ref, id, t); rtol = 1e-9)
            end
            @test isapprox(bg_value(columns, "R1/p.f", t), -f; rtol = 1e-9)
            @test isapprox(bg_value(columns, "R1/p.P", t), power; rtol = 1e-9)
            @test isapprox(bg_value(columns, "Sf1/p.P", t), -power; rtol = 1e-9)
            # Flow in at a, out at b; the effort passes through.
            @test isapprox(bg_value(columns, "P1/a.f", t), -f; rtol = 1e-9)
            @test isapprox(bg_value(columns, "P1/b.f", t), f; rtol = 1e-9)
            @test isapprox(bg_value(columns, "P1/a.e", t), -r * f; rtol = 1e-9)
            @test isapprox(bg_value(columns, "P1/b.e", t), -r * f; rtol = 1e-9)
            # The reading is the power from the source to the resistor, and the sensor
            # neither stores nor dissipates: what enters at a leaves at b.
            @test isapprox(bg_value(columns, "P1/y", t), power; rtol = 1e-9)
            @test isapprox(bg_value(columns, "P1/a.P", t), power; rtol = 1e-9)
            @test isapprox(bg_value(columns, "P1/b.P", t), -power; rtol = 1e-9)
        end
    end

    @testset "junction placements follow the half-arrows" begin
        e = r * f
        function junction_model(bonds)
            return bg_model(
                "PowerSensorAtJunction",
                [
                    bg_node("se", "Se1", bg_ref("stdlib:bondgraph/Se");
                        params = Dict{String,Any}("e" => string(e))),
                    bg_node("j", "J1", bg_junction(1)),
                    bg_node("s", "P1", bg_ref("stdlib:converters/PowerSensor")),
                    bg_node("r", "R1", bg_ref("stdlib:bondgraph/R");
                        params = Dict{String,Any}("r" => string(r))),
                ],
                vcat([bg_conn("c1", "bond", "se", "p", "j", nothing)],
                    [bg_conn(b[1], "bond", b[2], b[3], b[4], b[5]) for b in bonds]);
                t_end = 0.01, points = 11,
            )
        end

        # junction -> a, b -> R: the half-arrows point to R, the reading is +12 W.
        columns, result, _ = bg_run(junction_model(
            [("c2", "j", nothing, "s", "a"), ("c3", "s", "b", "r", "p")]))
        @test result.status == "done"
        @test isempty([d for d in result.diagnostics if d.severity == "error"])
        for t in (0.0, 0.01)
            # Se drives e into the 1-junction, so the resistor absorbs e^2/r.
            @test isapprox(bg_value(columns, "R1/p.P", t), power; rtol = 1e-9)
            @test isapprox(abs(bg_value(columns, "R1/p.f", t)), f; rtol = 1e-9)
            @test isapprox(bg_value(columns, "P1/y", t), power; rtol = 1e-9)
            @test isapprox(bg_value(columns, "P1/a.P", t) + bg_value(columns, "P1/b.P", t),
                0.0; atol = 1e-9)
        end

        # R -> a, b -> junction (half-arrows pointing away from R) used to read -12 W. R's port
        # is `in` (port orientation), so the bond out of R is refused with E114 instead.
        flat = BGSim.Compile.flatten(BGSim.IR.parse_model(junction_model(
            [("c2", "r", "p", "s", "a"), ("c3", "s", "b", "j", nothing)])))
        @test [d.code for d in flat.diagnostics if d.severity == "error"] == ["E114"]
    end
end
