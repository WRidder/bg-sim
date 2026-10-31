# Golden test for `stdlib:rotation/PlanetaryGear`, through the real pipeline.
#
# The ideal set obeys the Willis equation w_sun + ratio*w_ring = (1 + ratio)*w_carrier and
# splits the torques 1 : ratio : -(1 + ratio), so the power into the three flanges sums to
# zero.
#
# Case 1, sun drives, ring fixed: a `SpeedSource` holds w_sun, a `RotationalDamper` d from
# the carrier to ground is the load. Then w_carrier = w_sun/(1 + ratio), the damper torque
# is d*w_carrier, carrier.e = -d*w_carrier, sun.e = d*w_carrier/(1 + ratio) and
# ring.e = ratio*sun.e (the reaction the fixed ring takes).
#
# Case 2, carrier drives, sun fixed: w_ring = (1 + ratio)/ratio * w_carrier, damper on the
# ring, ring.e = -d*w_ring, sun.e = ring.e/ratio, carrier.e = -(1 + ratio)*sun.e.
#
# Case 3, dynamics: a constant torque T drives a sun inertia J_s, the ring is fixed and the
# carrier carries an inertia J_c. The inertias are kinematically coupled, so the effective
# inertia at the sun is J_s + J_c/(1 + ratio)^2 and w_sun(t) = T*t/J_eff; the kinetic energy
# equals the work of the source.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

function planetary_model(case; ratio = 2.5, w = 4.0, d = 0.3)
    nodes = Any[
        bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
            params = Dict{String,Any}("value" => "1.0")),
        bg_node("n2", "W1", bg_ref("stdlib:rotation/SpeedSource");
            params = Dict{String,Any}("w" => string(w))),
        bg_node("n3", "PG1", bg_ref("stdlib:rotation/PlanetaryGear");
            params = Dict{String,Any}("ratio" => string(ratio))),
        bg_node("n4", "D1", bg_ref("stdlib:rotation/RotationalDamper");
            params = Dict{String,Any}("d" => string(d))),
        bg_node("n5", "F1", bg_ref("stdlib:rotation/FixedShaft")),
    ]
    driven, held, loaded = case == 1 ? ("sun", "ring", "carrier") : ("carrier", "sun", "ring")
    conns = Any[
        bg_conn("c1", "signal", "n1", "y", "n2", "u"),
        bg_conn("c2", "wire", "n2", "a", "n3", driven),
        bg_conn("c3", "wire", "n3", held, "n5", "a"),
        bg_conn("c4", "wire", "n3", loaded, "n4", "a"),
        bg_conn("c5", "wire", "n4", "b", "n5", "a"),
    ]
    return bg_model("PlanetaryCase$case", nodes, conns; t_end = 0.01, points = 11)
end

function planetary_balance(columns, t)
    return bg_value(columns, "PG1/sun.P", t) + bg_value(columns, "PG1/ring.P", t) +
           bg_value(columns, "PG1/carrier.P", t)
end

@testset "golden: PlanetaryGear" begin
    ratio = 2.5
    w = 4.0
    d = 0.3

    # Case 1: sun drives, ring fixed, damper on the carrier.
    columns, result, flat = bg_run(planetary_model(1))
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 0
    w_c = w / (1 + ratio)
    for t in (0.0, 0.005, 0.01)
        @test isapprox(bg_value(columns, "PG1/sun.f", t), w; rtol = 1e-9)
        @test isapprox(bg_value(columns, "PG1/ring.f", t), 0.0; atol = 1e-12)
        @test isapprox(bg_value(columns, "PG1/carrier.f", t), w_c; rtol = 1e-9)
        @test isapprox(bg_value(columns, "PG1/carrier.e", t), -d * w_c; rtol = 1e-9)
        @test isapprox(bg_value(columns, "PG1/sun.e", t), d * w_c / (1 + ratio); rtol = 1e-9)
        @test isapprox(bg_value(columns, "PG1/ring.e", t), ratio * d * w_c / (1 + ratio);
            rtol = 1e-9)
        # Power: what the sun takes in leaves at the carrier.
        @test abs(planetary_balance(columns, t)) < 1e-12
        @test isapprox(bg_value(columns, "PG1/sun.P", t), d * w_c^2; rtol = 1e-9)
    end

    # Case 2: carrier drives, sun fixed, damper on the ring.
    columns, result, flat = bg_run(planetary_model(2))
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    w_r = (1 + ratio) / ratio * w
    for t in (0.0, 0.005, 0.01)
        @test isapprox(bg_value(columns, "PG1/carrier.f", t), w; rtol = 1e-9)
        @test isapprox(bg_value(columns, "PG1/sun.f", t), 0.0; atol = 1e-12)
        @test isapprox(bg_value(columns, "PG1/ring.f", t), w_r; rtol = 1e-9)
        @test isapprox(bg_value(columns, "PG1/ring.e", t), -d * w_r; rtol = 1e-9)
        @test isapprox(bg_value(columns, "PG1/sun.e", t), -d * w_r / ratio; rtol = 1e-9)
        @test isapprox(bg_value(columns, "PG1/carrier.e", t), (1 + ratio) * d * w_r / ratio;
            rtol = 1e-9)
        @test abs(planetary_balance(columns, t)) < 1e-12
    end

    # Case 3: torque-driven sun inertia, carrier inertia, ring fixed.
    T = 2.0
    J_s = 0.01
    J_c = 0.2
    J_eff = J_s + J_c / (1 + ratio)^2
    model = bg_model(
        "PlanetaryDynamics",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "TS1", bg_ref("stdlib:rotation/TorqueSource");
                params = Dict{String,Any}("T" => string(T))),
            bg_node("n3", "PG1", bg_ref("stdlib:rotation/PlanetaryGear");
                params = Dict{String,Any}("ratio" => string(ratio))),
            bg_node("n4", "Js", bg_ref("stdlib:rotation/Inertia");
                params = Dict{String,Any}("J" => string(J_s))),
            bg_node("n5", "Jc", bg_ref("stdlib:rotation/Inertia");
                params = Dict{String,Any}("J" => string(J_c))),
            bg_node("n6", "F1", bg_ref("stdlib:rotation/FixedShaft")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n6", "a"),
            bg_conn("c3", "wire", "n2", "b", "n4", "a"),
            bg_conn("c4", "wire", "n4", "a", "n3", "sun"),
            bg_conn("c5", "wire", "n4", "b", "n6", "a"),
            bg_conn("c6", "wire", "n3", "ring", "n6", "a"),
            bg_conn("c7", "wire", "n3", "carrier", "n5", "a"),
            bg_conn("c8", "wire", "n5", "b", "n6", "a"),
        ];
        t_end = 0.5, points = 51,
    )
    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    for t in (0.1, 0.25, 0.5)
        w_s = T * t / J_eff
        @test isapprox(bg_value(columns, "PG1/sun.f", t), w_s; rtol = 1e-6)
        @test isapprox(bg_value(columns, "PG1/carrier.f", t), w_s / (1 + ratio); rtol = 1e-6)
        @test abs(planetary_balance(columns, t)) < 1e-9
        # The work of the source, T times the sun angle T*t^2/(2*J_eff), is all kinetic.
        work = T * (T * t^2 / (2 * J_eff))
        @test isapprox(0.5 * J_s * bg_value(columns, "Js/w", t)^2 +
                       0.5 * J_c * bg_value(columns, "Jc/w", t)^2, work; rtol = 1e-6)
    end
end
