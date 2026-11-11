# Golden test for `stdlib:converters/LoadSensingPump`, through the real pipeline.
#
# Static law: a `SpeedSource` turns the shaft at w, three `Tank`s hold the suction a, the
# delivery b and the LS port. With dp = p_b - p_a and the margin m = p_b - p_ls:
#
#   x_ls = clamp((dp_ls + dp_reg - m)/dp_reg, 0, 1),  x_pc = clamp((p_cut + dp_reg - dp)/dp_reg, 0, 1),
#   x_tq = T_max/(D*sqrt(dp^2 + p_tr^2)),            x = min(x_ls, x_pc, x_tq),
#   Q = D*x*w - K_leak*dp,  T = D*x*dp + K_fr*dp*tanh(dp/p_tr)*tanh(w/w_tr).
#
# Checks: full stroke below the margin, the linear regulation range, zero stroke above it,
# the pressure cut-off, the torque limiter, no flow through the LS port, and a closed LS
# loop (pump -> volume -> orifice -> tank with the LS port on the load side) that settles
# with the margin inside [dp_ls, dp_ls + dp_reg].
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

function _lsp_law(w, p_a, p_b, p_ls; D = 3.5e-5, eta_v = 0.95, eta_m = 0.9, p_nom = 3.0e7,
    w_nom = 188.5, dp_ls = 2.5e6, dp_reg = 2.0e5, p_cut = 3.2e7, T_max = 1.0e9, p_tr = 1.0e5,
    w_tr = 1.0)
    sclamp(s) = 0.5 * (sqrt(s^2 + 1e-6) - sqrt((s - 1)^2 + 1e-6) + 1)
    smin(a, b) = 0.5 * (a + b - sqrt((a - b)^2 + 1e-6))
    dp = p_b - p_a
    m = p_b - p_ls
    x = smin(smin(sclamp((dp_ls + dp_reg - m) / dp_reg), sclamp((p_cut + dp_reg - dp) / dp_reg)),
        T_max / (D * sqrt(dp^2 + p_tr^2)))
    Q = D * x * w - D * w_nom * (1 - eta_v) / p_nom * dp
    T = D * x * dp + D * (1 - eta_m) / eta_m * dp * tanh(dp / p_tr) * tanh(w / w_tr)
    return x, Q, T
end

function _lsp_static(w, p_a, p_b, p_ls, params)
    return bg_model(
        "LSPumpBetweenTanks",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "W1", bg_ref("stdlib:rotation/SpeedSource");
                params = Dict{String,Any}("w" => string(w))),
            bg_node("n3", "P1", bg_ref("stdlib:converters/LoadSensingPump");
                params = Dict{String,Any}(params)),
            bg_node("n4", "TA", bg_ref("stdlib:hydraulic/Tank");
                params = Dict{String,Any}("p" => string(p_a))),
            bg_node("n5", "TB", bg_ref("stdlib:hydraulic/Tank");
                params = Dict{String,Any}("p" => string(p_b))),
            bg_node("n6", "TL", bg_ref("stdlib:hydraulic/Tank");
                params = Dict{String,Any}("p" => string(p_ls))),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "shaft"),
            bg_conn("c3", "wire", "n4", "a", "n3", "a"),
            bg_conn("c4", "wire", "n3", "b", "n5", "a"),
            bg_conn("c5", "wire", "n6", "a", "n3", "ls"),
        ];
        t_end = 0.01, points = 3,
    )
end

@testset "golden: LoadSensingPump" begin
    w, p_a = 188.5, 1.0e5
    @testset "static law: $label" for (label, p_b, p_ls, params, x_expect) in (
        ("full stroke below the margin", 1.5e7, 1.4e7, Dict{String,Any}(), 1.0),
        ("inside the regulation range", 1.5e7, 1.5e7 - 2.6e6, Dict{String,Any}(), 0.5),
        ("zero stroke above the margin", 1.5e7, 1.0e7, Dict{String,Any}(), 0.0),
        ("pressure cut-off", 3.22e7, 3.0e7, Dict{String,Any}(), 0.5),
        ("torque limiter", 2.0e7, 1.9e7, Dict{String,Any}("T_max" => "350.0"), nothing),
    )
        kw = Dict(Symbol(k) => parse(Float64, v) for (k, v) in params)
        x, Q, T = _lsp_law(w, p_a, p_b, p_ls; kw...)
        x_expect === nothing || @test isapprox(x, x_expect; atol = 2e-3)
        columns, result, flat = bg_run(_lsp_static(w, p_a, p_b, p_ls, params))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        @test isapprox(bg_value(columns, "P1/x", 0.01), x; rtol = 1e-9, atol = 1e-9)
        @test isapprox(bg_value(columns, "P1/Q", 0.01), Q; rtol = 1e-9, atol = 1e-12)
        @test isapprox(bg_value(columns, "P1/T", 0.01), T; rtol = 1e-9, atol = 1e-9)
        @test bg_value(columns, "P1/ls.f", 0.01) == 0.0
        # the readout outputs: displacement, shaft power T*w, hydraulic power dp*Q
        @test isapprox(bg_value(columns, "P1/xd", 0.01), x; rtol = 1e-9, atol = 1e-9)
        @test isapprox(bg_value(columns, "P1/P_in", 0.01), T * w; rtol = 1e-9, atol = 1e-6)
        @test isapprox(bg_value(columns, "P1/P_out", 0.01), (p_b - p_a) * Q; rtol = 1e-9, atol = 1e-3)
        if label == "torque limiter"
            # x_tq = T_max/(D*dp) caps the ideal torque D*x*dp at T_max.
            @test isapprox(x, 350.0 / (3.5e-5 * sqrt(1.99e7^2 + 1e10)); rtol = 1e-3)
            @test isapprox(3.5e-5 * x * 1.99e7, 350.0; rtol = 1e-3)
        end
    end

    @testset "closed LS loop settles at the margin" begin
        # Pump -> 1 L line volume VP -> laminar restrictor R1 -> 1 L load volume VL (the LS
        # port taps it) -> laminar restrictor R2 -> tank (each R on a 1-junction). In steady
        # state R1 carries the margin, Q = margin/R1 (about 1e-3 m^3/s), the load pressure is
        # Q*R2 (about 100 bar), and the pump delivers Q at a part stroke.
        nodes = [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "W1", bg_ref("stdlib:rotation/SpeedSource");
                params = Dict{String,Any}("w" => "188.5")),
            bg_node("n3", "P1", bg_ref("stdlib:converters/LoadSensingPump")),
            bg_node("n4", "TA", bg_ref("stdlib:hydraulic/Tank")),
            bg_node("n5", "VP", bg_ref("stdlib:hydraulic/Volume");
                params = Dict{String,Any}("V" => "1.0e-3"), starts = Dict{String,Any}("p" => "1.0e5")),
            bg_node("n6", "R1", bg_ref("stdlib:bondgraph/R");
                params = Dict{String,Any}("r" => "2.6e9")),
            bg_node("n7", "VL", bg_ref("stdlib:hydraulic/Volume");
                params = Dict{String,Any}("V" => "1.0e-3"), starts = Dict{String,Any}("p" => "1.0e5")),
            bg_node("n8", "R2", bg_ref("stdlib:bondgraph/R");
                params = Dict{String,Any}("r" => "1.0e10")),
            bg_node("n9", "TB", bg_ref("stdlib:hydraulic/Tank")),
            bg_node("n10", "JP", bg_junction("0")),
            bg_node("n11", "JL", bg_junction("0")),
            bg_node("n12", "J1", bg_junction("1")),
            bg_node("n13", "J2", bg_junction("1")),
        ]
        conns = [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "shaft"),
            bg_conn("c3", "wire", "n4", "a", "n3", "a"),
            bg_conn("c4", "bond", "n10", nothing, "n3", "b"),
            bg_conn("c5", "bond", "n10", nothing, "n5", "a"),
            bg_conn("c6", "bond", "n10", nothing, "n12", nothing),
            bg_conn("c7", "bond", "n12", nothing, "n6", "p"),
            bg_conn("c8", "bond", "n12", nothing, "n11", nothing),
            bg_conn("c9", "bond", "n11", nothing, "n7", "a"),
            bg_conn("c10", "bond", "n11", nothing, "n13", nothing),
            bg_conn("c11", "bond", "n13", nothing, "n8", "p"),
            bg_conn("c12", "bond", "n13", nothing, "n9", "a"),
            bg_conn("c13", "bond", "n11", nothing, "n3", "ls"),
        ]
        columns, result, flat = bg_run(bg_model("LSPumpLoop", nodes, conns; t_end = 0.5, points = 51))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        m = bg_value(columns, "P1/margin", 0.5)
        @test 2.5e6 - 1e3 <= m <= 2.7e6 + 1e3
        pP, pL = bg_value(columns, "VP/p", 0.5), bg_value(columns, "VL/p", 0.5)
        @test isapprox(m, pP - pL; rtol = 1e-9)
        # Steady state: the pump delivers what the restrictors pass.
        @test isapprox(bg_value(columns, "P1/Q", 0.5), (pP - pL) / 2.6e9; rtol = 1e-3)
        @test isapprox(bg_value(columns, "P1/Q", 0.5), (pL - 1e5) / 1.0e10; rtol = 1e-3)
        @test 0.0 < bg_value(columns, "P1/x", 0.5) < 1.0
    end
end
