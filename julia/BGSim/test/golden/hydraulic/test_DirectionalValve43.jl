# Golden test for `stdlib:hydraulic/DirectionalValve43`, through the real pipeline.
#
# Model: four fixed pressures, a 100 bar `PressureSource` at P, `Tank`s at T (1 bar),
# A (40 bar) and B (20 bar), and a `Constant` spool position u. Each metering edge follows
# the Orifice's regularized law with the area A_leak + A_max*clamp((+-u - lap)/(1 - lap));
# the reference below uses the same smooth clamp (corners over 1e-6 of the stroke).
#
# Checks (rtol 1e-9): the four edge flows and the port flows for u > 0 (P->A, B->T open),
# u < 0 (P->B, A->T open), the closed centre (u = 0, leakage only), an overlap (a command
# inside the dead band stays closed) and an underlap (open centre at u = 0). The body
# conserves flow (P.f + T.f + A.f + B.f = 0) and only dissipates.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

_dv_clamp(s) = 0.5 * (sqrt(s^2 + 1e-12) - sqrt((s - 1)^2 + 1e-12) + 1)
_dv_orifice(A, dp; Cd = 0.62, rho = 850.0, p_tr = 1.0e5) =
    Cd * A * sqrt(2 / rho) * dp / (dp^2 + p_tr^2)^(1 / 4)

function _dv_flows(u, pP, pT, pA, pB; A_max = 1.0e-5, A_leak = 1.0e-9, lap = 0.0)
    Ap = A_leak + A_max * _dv_clamp((u - lap) / (1 - lap))
    An = A_leak + A_max * _dv_clamp((-u - lap) / (1 - lap))
    return (PA = _dv_orifice(Ap, pP - pA), BT = _dv_orifice(Ap, pB - pT),
        PB = _dv_orifice(An, pP - pB), AT = _dv_orifice(An, pA - pT))
end

function _dv_model(u, pP, pT, pA, pB, params)
    tank(id, name, p) = bg_node(id, name, bg_ref("stdlib:hydraulic/Tank");
        params = Dict{String,Any}("p" => string(p)))
    return bg_model(
        "DirectionalValveBetweenFixedPressures",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "PS", bg_ref("stdlib:hydraulic/PressureSource");
                params = Dict{String,Any}("p" => string(pP))),
            bg_node("n3", "DV", bg_ref("stdlib:hydraulic/DirectionalValve43");
                params = Dict{String,Any}(params)),
            tank("n4", "TT", pT),
            tank("n5", "TA", pA),
            tank("n6", "TB", pB),
            bg_node("n7", "U1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => string(u))),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "P"),
            bg_conn("c3", "wire", "n3", "T", "n4", "a"),
            bg_conn("c4", "wire", "n3", "A", "n5", "a"),
            bg_conn("c5", "wire", "n3", "B", "n6", "a"),
            bg_conn("c6", "signal", "n7", "y", "n3", "u"),
        ];
        t_end = 0.01, points = 3,
    )
end

@testset "golden: DirectionalValve43" begin
    pP, pT, pA, pB = 1.0e7, 1.0e5, 4.0e6, 2.0e6
    results = Dict{String,Any}()
    @testset "$label" for (label, u, lap) in (
        ("u = 0.5", 0.5, 0.0),
        ("u = 1.0", 1.0, 0.0),
        ("u = 1.5 (beyond the stroke)", 1.5, 0.0),
        ("u = -0.5", -0.5, 0.0),
        ("closed centre", 0.0, 0.0),
        ("overlap, u inside the dead band", 0.05, 0.1),
        ("overlap, u = 0.55", 0.55, 0.1),
        ("underlap, u = 0", 0.0, -0.1),
    )
        ref = _dv_flows(u, pP, pT, pA, pB; lap = lap)
        columns, result, flat = bg_run(_dv_model(u, pP, pT, pA, pB,
            Dict{String,Any}("lap" => string(lap))))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        @test flat.stats.states == 0
        t = 0.01
        for (name, q) in pairs(ref)
            @test isapprox(bg_value(columns, "DV/Q_$name", t), q; rtol = 1e-9, atol = 1e-20)
        end
        @test isapprox(bg_value(columns, "DV/P.f", t), ref.PA + ref.PB; rtol = 1e-9)
        @test isapprox(bg_value(columns, "DV/T.f", t), -(ref.BT + ref.AT); rtol = 1e-9)
        @test isapprox(bg_value(columns, "DV/A.f", t), ref.AT - ref.PA; rtol = 1e-9)
        @test isapprox(bg_value(columns, "DV/B.f", t), ref.BT - ref.PB; rtol = 1e-9)
        flows = [bg_value(columns, "DV/$p.f", t) for p in ("P", "T", "A", "B")]
        @test abs(sum(flows)) <= 1e-12 * maximum(abs.(flows))
        P = sum(bg_value(columns, "DV/$p.P", t) for p in ("P", "T", "A", "B"))
        @test P >= 0
        results[label] = ref
    end
    # Metering: the open edges at u = 0.5 carry half the full-stroke area plus leakage,
    # the closed ones only the leakage; the stroke end limits the area.
    open = _dv_orifice(1.0e-9 + 0.5e-5, pP - pA)
    @test isapprox(results["u = 0.5"].PA, open; rtol = 1e-6)
    @test results["u = 0.5"].PB < 1e-3 * open
    @test isapprox(results["u = 1.5 (beyond the stroke)"].PA, results["u = 1.0"].PA; rtol = 1e-6)
    # Closed centre and dead band: every edge passes only about the leakage area.
    for label in ("closed centre", "overlap, u inside the dead band")
        @test all(abs(q) < 1.01 * _dv_orifice(1.0e-9, 1.0e7) for q in results[label])
    end
    # Overlap: 0.55 with lap 0.1 opens (0.55 - 0.1)/0.9 = 0.5 of the stroke.
    @test isapprox(results["overlap, u = 0.55"].PA, open; rtol = 1e-6)
    # Underlap: at u = 0 every edge is open by 0.1/1.1 of the stroke.
    @test isapprox(results["underlap, u = 0"].PA,
        _dv_orifice(1.0e-9 + 1.0e-5 * 0.1 / 1.1, pP - pA); rtol = 1e-6)
end
