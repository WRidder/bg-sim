# Golden test for `stdlib:translation/Friction` (plan section 8, M2 row: Friction — Coulomb,
# viscous and Stribeck), through the real pipeline (`parse` -> `flatten` -> `lower` ->
# `simulate`).
#
# Model: a `VelocitySource` (gain v, driven by a Constant 1) prescribes the relative velocity
# `a.f - b.f`; `b` is `Fixed`. In D8's Translation convention the across variable is the
# velocity `f` and the through variable the force `e`. With `dv = a.f - b.f` the block's law
#
#   s   = v_eps > 0 ? tanh(dv/v_eps) : (dv > 0 ? 1 : dv < 0 ? -1 : 0)
#   a.e = (Fc + (Fs - Fc)*exp(-|dv|/v_s)) * s + Fv*dv,   b.e = -a.e
#
# is algebraic, so the recorded force is exact up to the signal round trip. The test sweeps
# positive, negative and near-zero velocities for both branches: the smooth branch
# (`v_eps = 1e-3`, tanh, also at exactly zero velocity where s = 0) and the exact switch
# (`v_eps = 0`, the non-smooth ifelse the event collector sees). Tolerance: rtol 1e-6
# against the analytic law (the run itself is at reltol 1e-10).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

const FRICTION_Fs = 8.0                    # N, static (zero-velocity) Stribeck magnitude
const FRICTION_Fc = 5.0                    # N, Coulomb (high-velocity) magnitude
const FRICTION_Fv = 40.0                   # N*s/m, viscous coefficient
const FRICTION_vs = 0.01                   # m/s, Stribeck velocity

"""The exact block law, written from the plan spec (not from recorded output)."""
function stribeck_force(dv, v_eps;
    Fs = FRICTION_Fs, Fc = FRICTION_Fc, Fv = FRICTION_Fv, v_s = FRICTION_vs)
    s = v_eps > 0.0 ? tanh(dv / v_eps) :
        (dv > 0.0 ? 1.0 : (dv < 0.0 ? -1.0 : 0.0))
    return (Fc + (Fs - Fc) * exp(-abs(dv) / v_s)) * s + Fv * dv
end

function friction_model(v, v_eps)
    return bg_model(
        "FrictionConstantVelocity",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "V1", bg_ref("stdlib:translation/VelocitySource");
                params = Dict{String,Any}("v" => string(v))),
            bg_node("n3", "FR1", bg_ref("stdlib:translation/Friction");
                params = Dict{String,Any}(
                    "Fs" => "8.0", "Fc" => "5.0", "Fv" => "40.0", "v_s" => "0.01",
                    "v_eps" => string(v_eps))),
            bg_node("n4", "F1", bg_ref("stdlib:translation/Fixed")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n3", "b", "n4", "a"),
        ];
        t_end = 0.01, points = 11,
    )
end

@testset "golden: Friction" begin
    # The smooth (tanh) branch, including exact zero velocity where s = tanh(0) = 0.
    for v in (0.2, -0.2, 0.05, -0.05, 1.0e-4, -1.0e-4, 0.0)
        columns, result, flat = bg_run(friction_model(v, 1.0e-3))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        @test flat.stats.states == 0             # Friction is algebraic
        expected = stribeck_force(v, 1.0e-3)
        for t in (0.0, 0.005, 0.01)
            @test isapprox(bg_value(columns, "FR1/a.f", t), v; rtol = 1e-9, atol = 1e-15)
            @test isapprox(bg_value(columns, "FR1/b.f", t), 0.0; atol = 1e-12)
            @test isapprox(bg_value(columns, "FR1/a.e", t), expected;
                rtol = 1e-6, atol = 1e-12)
            @test isapprox(bg_value(columns, "FR1/b.e", t), -expected;
                rtol = 1e-6, atol = 1e-12)
            # The reaction travels through the wire into the flow source.
            @test isapprox(bg_value(columns, "V1/a.e", t), -expected;
                rtol = 1e-6, atol = 1e-12)
            # The smoothed direction factor is the tanh of the relative velocity.
            @test isapprox(bg_value(columns, "FR1/s", t), tanh(v / 1.0e-3);
                rtol = 1e-9, atol = 1e-15)
        end
        # The friction element is resistive: the entering power force*v is dissipated and
        # the fixed side (b.f = 0) carries none of it.
        @test isapprox(bg_value(columns, "FR1/a.P", 0.0), expected * v; rtol = 1e-6,
            atol = 1e-12)
        @test isapprox(bg_value(columns, "FR1/b.P", 0.0), 0.0; atol = 1e-12)
    end

    # The exact switch (`v_eps = 0`): away from zero the sign is +-1, so the force is the
    # same Stribeck magnitude with the viscous term; the tanh factor is not used.
    for v in (0.2, -0.2, 0.05, -0.05, 1.0e-4, -1.0e-4)
        columns, result, flat = bg_run(friction_model(v, 0.0))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        @test flat.stats.states == 0
        expected = stribeck_force(v, 0.0)
        sign = v > 0.0 ? 1.0 : -1.0
        @test isapprox(bg_value(columns, "FR1/s", 0.0), sign; rtol = 1e-12)
        @test isapprox(bg_value(columns, "FR1/a.e", 0.0), expected; rtol = 1e-6)
        @test isapprox(bg_value(columns, "FR1/b.e", 0.0), -expected; rtol = 1e-6)
    end
end
