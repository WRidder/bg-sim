# Golden test for `stdlib:rotation/RotationalFriction` (plan section 8, M2 row: Rotational
# friction), through the real pipeline.
#
# Model: a `SpeedSource` (gain w, driven by a Constant 1) prescribes the relative speed
# `a.f - b.f`; `b` is a `FixedShaft`. With `dw = a.f - b.f` the block's law is the
# rotational twin of the translational `Friction`:
#
#   s   = v_eps > 0 ? tanh(dw/v_eps) : (dw > 0 ? 1 : dw < 0 ? -1 : 0)
#   a.e = (Fc + (Fs - Fc)*exp(-|dw|/v_s)) * s + Fv*dw,   b.e = -a.e.
#
# Both branches are swept: the smooth tanh branch at positive, negative, near-zero and zero
# speed, and the exact ifelse switch. Tolerance: rtol 1e-6 against the analytic law.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

const ROT_FRICTION_Fs = 8.0               # N*m
const ROT_FRICTION_Fc = 5.0               # N*m
const ROT_FRICTION_Fv = 40.0              # N*m*s/rad
const ROT_FRICTION_vs = 0.01              # rad/s

"""The exact block law, written from the plan spec (not from recorded output)."""
function rotational_stribeck(dw, v_eps;
    Fs = ROT_FRICTION_Fs, Fc = ROT_FRICTION_Fc, Fv = ROT_FRICTION_Fv, v_s = ROT_FRICTION_vs)
    s = v_eps > 0.0 ? tanh(dw / v_eps) :
        (dw > 0.0 ? 1.0 : (dw < 0.0 ? -1.0 : 0.0))
    return (Fc + (Fs - Fc) * exp(-abs(dw) / v_s)) * s + Fv * dw
end

function rotational_friction_model(w, v_eps)
    return bg_model(
        "RotationalFrictionConstantSpeed",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "W1", bg_ref("stdlib:rotation/SpeedSource");
                params = Dict{String,Any}("w" => string(w))),
            bg_node("n3", "FR1", bg_ref("stdlib:rotation/RotationalFriction");
                params = Dict{String,Any}(
                    "Fs" => "8.0", "Fc" => "5.0", "Fv" => "40.0", "v_s" => "0.01",
                    "v_eps" => string(v_eps))),
            bg_node("n4", "F1", bg_ref("stdlib:rotation/FixedShaft")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n3", "b", "n4", "a"),
        ];
        t_end = 0.01, points = 11,
    )
end

@testset "golden: RotationalFriction" begin
    for w in (0.2, -0.2, 0.05, -0.05, 1.0e-4, -1.0e-4, 0.0)
        columns, result, flat = bg_run(rotational_friction_model(w, 1.0e-3))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        @test flat.stats.states == 0
        expected = rotational_stribeck(w, 1.0e-3)
        for t in (0.0, 0.005, 0.01)
            @test isapprox(bg_value(columns, "FR1/a.f", t), w; rtol = 1e-9, atol = 1e-15)
            @test isapprox(bg_value(columns, "FR1/b.f", t), 0.0; atol = 1e-12)
            @test isapprox(bg_value(columns, "FR1/a.e", t), expected;
                rtol = 1e-6, atol = 1e-12)
            @test isapprox(bg_value(columns, "FR1/b.e", t), -expected;
                rtol = 1e-6, atol = 1e-12)
            @test isapprox(bg_value(columns, "W1/a.e", t), -expected;
                rtol = 1e-6, atol = 1e-12)
            @test isapprox(bg_value(columns, "FR1/s", t), tanh(w / 1.0e-3);
                rtol = 1e-9, atol = 1e-15)
        end
        @test isapprox(bg_value(columns, "FR1/a.P", 0.0), expected * w; rtol = 1e-6,
            atol = 1e-12)
        @test isapprox(bg_value(columns, "FR1/b.P", 0.0), 0.0; atol = 1e-12)
    end

    for w in (0.2, -0.2, 0.05, -0.05, 1.0e-4, -1.0e-4)
        columns, result, flat = bg_run(rotational_friction_model(w, 0.0))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        @test flat.stats.states == 0
        expected = rotational_stribeck(w, 0.0)
        @test isapprox(bg_value(columns, "FR1/s", 0.0), w > 0.0 ? 1.0 : -1.0;
            rtol = 1e-12)
        @test isapprox(bg_value(columns, "FR1/a.e", 0.0), expected; rtol = 1e-6)
        @test isapprox(bg_value(columns, "FR1/b.e", 0.0), -expected; rtol = 1e-6)
    end
end
