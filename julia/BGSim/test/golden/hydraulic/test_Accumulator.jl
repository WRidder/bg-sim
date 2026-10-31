# Golden test for `stdlib:hydraulic/Accumulator`, through the real pipeline.
#
# Model: a `FlowSource` (return to a tank) pushes a constant flow Q into the accumulator,
# so the fluid volume is exactly V_f(t) = V_f0 + Q*t. With the precharge p0 = 50 bar in
# V0 = 1 l, polytropic index n and the smooth split eps = p_tr*V_dead/beta:
#
#   V_gas = V0 - (V_f + sqrt(V_f^2 + eps^2))/2,   p_gas = p0*(V0/V_gas)^n,
#   p     = p_gas + beta/V_dead*(V_f - sqrt(V_f^2 + eps^2))/2.
#
# Checks: the charging run (n = 1.4 and n = 1) follows this law at rtol 1e-9, keeps
# p_gas*V_gas^n = p0*V0^n, and its hydraulic work int p dV equals the polytropic gas
# energy p0*V0^n/(n - 1)*(V_gas^(1-n) - V0^(1-n)) (n = 1.4; the trapezoid of the recorded
# a.P to 1e-6). A discharge below the precharge empties the accumulator: the pressure
# then drops with the stiff dead-volume law p = p0 + beta*V_f/V_dead.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

function _acc_law(V_f; p0 = 5.0e6, V0 = 1.0e-3, n = 1.4, V_dead = 1.0e-5, beta = 1.4e9,
    p_tr = 1.0e4)
    eps = p_tr * V_dead / beta
    r = sqrt(V_f^2 + eps^2)
    V_gas = V0 - (V_f + r) / 2
    p_gas = p0 * (V0 / V_gas)^n
    return (V_gas = V_gas, p_gas = p_gas, p = p_gas + beta / V_dead * (V_f - r) / 2)
end

function _acc_model(Q, V_f0, params; t_end = 1.0, points = 101)
    return bg_model(
        "AccumulatorChargedByFlowSource",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "F1", bg_ref("stdlib:hydraulic/FlowSource");
                params = Dict{String,Any}("Q" => string(-Q))),
            bg_node("n3", "AC", bg_ref("stdlib:hydraulic/Accumulator");
                params = Dict{String,Any}(params),
                starts = Dict{String,Any}("V_f" => string(V_f0))),
            bg_node("n4", "TK", bg_ref("stdlib:hydraulic/Tank")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n2", "b", "n4", "a"),
        ];
        t_end = t_end, points = points,
    )
end

@testset "golden: Accumulator" begin
    @testset "charging, n = $n" for n in (1.4, 1.0)
        Q, V_f0 = 5.0e-4, 1.0e-4                # 0.5 l/s from 0.1 l to 0.6 l in 1 s
        columns, result, flat = bg_run(_acc_model(Q, V_f0, Dict("n" => string(n))))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        @test flat.stats.states == 1             # the fluid volume
        for t in (0.0, 0.25, 0.5, 1.0)
            V_f = V_f0 + Q * t
            ref = _acc_law(V_f; n = n)
            @test isapprox(bg_value(columns, "AC/V_f", t), V_f; rtol = 1e-9)
            @test isapprox(bg_value(columns, "AC/V_gas", t), ref.V_gas; rtol = 1e-9)
            @test isapprox(bg_value(columns, "AC/p_gas", t), ref.p_gas; rtol = 1e-9)
            @test isapprox(bg_value(columns, "AC/p", t), ref.p; rtol = 1e-9)
            @test isapprox(bg_value(columns, "AC/a.e", t), ref.p; rtol = 1e-9)
            # The polytropic invariant p*V^n of the gas.
            pVn = bg_value(columns, "AC/p_gas", t) * bg_value(columns, "AC/V_gas", t)^n
            @test isapprox(pVn, 5.0e6 * (1.0e-3)^n; rtol = 1e-9)
        end
        if n == 1.4
            # Hydraulic work into the accumulator equals the gas energy stored.
            ts, P = columns["time"], columns["AC/a.P"]
            work = sum((ts[k+1] - ts[k]) * (P[k] + P[k+1]) / 2 for k in 1:length(ts)-1)
            Vg(t) = _acc_law(V_f0 + Q * t).V_gas
            energy = 5.0e6 * (1.0e-3)^1.4 / 0.4 * (Vg(1.0)^(-0.4) - Vg(0.0)^(-0.4))
            @test isapprox(work, energy; rtol = 1e-4)
        end
    end

    @testset "discharging below the precharge" begin
        # Draw 1e-4 m^3/s from 0.05 l of fluid: empty after 0.5 s, then the dead volume.
        Q, V_f0 = -1.0e-4, 5.0e-5
        t_end = 0.5001
        columns, result, _ = bg_run(_acc_model(Q, V_f0, Dict{String,Any}();
            t_end = t_end, points = 11))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        # At t = 0.5 + 1e-4 s the fluid volume is -1e-8 m^3: deep in the empty branch,
        # p = p0 + beta*V_f/V_dead = 50 bar - 14 bar.
        V_f = V_f0 + Q * t_end
        @test isapprox(bg_value(columns, "AC/V_f", t_end), V_f; rtol = 1e-7)
        @test isapprox(bg_value(columns, "AC/p", t_end), _acc_law(V_f).p; rtol = 1e-7)
        @test isapprox(_acc_law(V_f).p, 5.0e6 + 1.4e9 * V_f / 1.0e-5; rtol = 1e-5)   # 18 Pa of rounding
        @test isapprox(bg_value(columns, "AC/V_gas", t_end), 1.0e-3; rtol = 1e-9)
        # While fluid remains the gas law holds; the pressure is continuous through p0.
        @test isapprox(bg_value(columns, "AC/p", 0.0), _acc_law(V_f0).p; rtol = 1e-9)
        @test issorted(reverse(columns["AC/p"]))
    end
end
