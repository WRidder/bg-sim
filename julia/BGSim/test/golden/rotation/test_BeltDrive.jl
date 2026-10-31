# Golden test for `stdlib:rotation/BeltDrive`, through the real pipeline.
#
# Model: a `SpeedSource` holds pulley a at w_a, pulley b drives a `RotationalDamper` d_b to
# ground. With the belt stretch x, the tension difference F = k*x + d*(r_a*w_a - r_b*w_b),
# and the torque balance at b, d_b*w_b = r_b*F, the stretch obeys the linear ODE
#
#   x' = alpha - beta*x,  alpha = r_a*w_a*d_b/(d_b + d*r_b^2),  beta = k*r_b^2/(d_b + d*r_b^2),
#
# so x(t) = (alpha/beta)*(1 - exp(-beta*t)), w_b = r_b*(k*x + d*r_a*w_a)/(d_b + d*r_b^2), and
# in the steady state the belt speeds match, r_b*w_b = r_a*w_a. The belt stores k*x^2/2 and
# dissipates d*(r_a*w_a - r_b*w_b)^2: the power into the two pulleys is exactly that.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: BeltDrive" begin
    w_a = 10.0
    r_a = 0.04
    r_b = 0.12
    k = 2.0e4
    d = 20.0
    d_b = 0.5
    den = d_b + d * r_b^2
    alpha = r_a * w_a * d_b / den
    beta = k * r_b^2 / den
    x(t) = alpha / beta * (1 - exp(-beta * t))
    w_b(t) = r_b * (k * x(t) + d * r_a * w_a) / den
    F(t) = k * x(t) + d * (r_a * w_a - r_b * w_b(t))

    model = bg_model(
        "BeltDriveDamperLoad",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "W1", bg_ref("stdlib:rotation/SpeedSource");
                params = Dict{String,Any}("w" => string(w_a))),
            bg_node("n3", "B1", bg_ref("stdlib:rotation/BeltDrive");
                params = Dict{String,Any}("r_a" => string(r_a), "r_b" => string(r_b),
                    "k" => string(k), "d" => string(d))),
            bg_node("n4", "D1", bg_ref("stdlib:rotation/RotationalDamper");
                params = Dict{String,Any}("d" => string(d_b))),
            bg_node("n5", "F1", bg_ref("stdlib:rotation/FixedShaft")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n3", "b", "n4", "a"),
            bg_conn("c4", "wire", "n4", "b", "n5", "a"),
        ];
        t_end = 0.1, points = 101,
    )
    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 1                 # the belt stretch
    @test 1 / beta < 0.02                        # settled well before t_end

    for t in (0.0, 0.002, 0.005, 0.01, 0.03, 0.1)
        @test isapprox(bg_value(columns, "B1/x", t), x(t); rtol = 1e-6, atol = 1e-12)
        @test isapprox(bg_value(columns, "B1/b.f", t), w_b(t); rtol = 1e-6)
        @test isapprox(bg_value(columns, "B1/F", t), F(t); rtol = 1e-6)
        @test isapprox(bg_value(columns, "B1/a.e", t), r_a * F(t); rtol = 1e-6)
        @test isapprox(bg_value(columns, "B1/b.e", t), -r_b * F(t); rtol = 1e-6)
        # Power: storage rate plus damping loss.
        slip = r_a * w_a - r_b * w_b(t)
        stored_rate = k * x(t) * slip
        p = bg_value(columns, "B1/a.P", t) + bg_value(columns, "B1/b.P", t)
        @test isapprox(p, stored_rate + d * slip^2; rtol = 1e-6, atol = 1e-9)
        @test d * slip^2 >= 0.0
    end
    # Steady state: equal belt speeds, so w_b = w_a*r_a/r_b.
    @test isapprox(bg_value(columns, "B1/b.f", 0.1), w_a * r_a / r_b; rtol = 1e-6)
end
