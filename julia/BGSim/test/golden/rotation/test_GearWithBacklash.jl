# Golden test for `stdlib:rotation/GearWithBacklash` (plan section 8, M2 row: the spec's
# `GearWithBacklash`, a composite through `@components`), through the real pipeline.
#
# Model (the J2.6 acceptance structure, now on the stdlib composite): an `Sf` flow source
# drives the input at -0.3 rad/s, the composite's `b` drives an `Inertia` (J = 0.01), whose
# other side is a `FixedShaft`. The gear is 10:1 with eta = 0.9, so the output side starts at
# 0.03 rad/s, crosses the 0.01 rad backlash and makes contact.
#
# The dead-zone law is exact on every recorded sample; the contact peak (0.216385 N*m at
# phi_max ~ 0.005021 rad) is the hand-checked reference value from the J2.6 acceptance run.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

const GWB_K = 1.0e4
const GWB_D = 5.0
const GWB_GAP = 0.01

function gwb_torque(phi, w; k = GWB_K, d = GWB_D, gap = GWB_GAP)
    if phi > gap / 2
        return max(k * (phi - gap / 2) + d * w, 0.0)
    elseif phi < -gap / 2
        return min(k * (phi + gap / 2) + d * w, 0.0)
    end
    return 0.0
end

@testset "golden: GearWithBacklash" begin
    f = -0.3
    model = bg_model(
        "GearWithBacklashDrive",
        [
            bg_node("n1", "Sf1", bg_ref("stdlib:bondgraph/Sf");
                params = Dict{String,Any}("f" => string(f))),
            bg_node("n2", "G1", bg_ref("stdlib:rotation/GearWithBacklash")),
            bg_node("n3", "J1", bg_ref("stdlib:rotation/Inertia");
                params = Dict{String,Any}("J" => "0.01")),
            bg_node("n4", "F1", bg_ref("stdlib:rotation/FixedShaft")),
        ],
        [
            bg_conn("c1", "bond", "n1", "p", "n2", "a"),
            bg_conn("c2", "wire", "n2", "b", "n3", "a"),
            bg_conn("c3", "wire", "n3", "b", "n4", "a"),
        ];
        t_end = 0.5, points = 501, reltol = 1.0e-10, abstol = 1.0e-12,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    # The composite expands to gear + play: play/phi is the only added state over the
    # inertia's phi and w.
    @test flat.stats.states == 3
    @test length(columns["time"]) >= 501        # contact instants are recorded twice

    phi = columns["G1/play/phi"]
    w = columns["G1/play/w"]
    torque = columns["G1/play/T"]
    @test 0.005 < maximum(abs.(phi)) < 0.0055
    @test maximum(torque) > 0.2
    @test minimum(torque) >= 0.0
    # The spec's dead-zone law holds on every sample.
    @test all(torque[i] == gwb_torque(phi[i], w[i]) for i in eachindex(phi))
    # No torque is transmitted inside the gap.
    @test all(torque[abs.(phi) .<= GWB_GAP / 2] .== 0.0)
    # Contact peak: k*(phi - gap/2) + d*w at the maximum, from the J2.6 acceptance run.
    i = argmax(torque)
    @test isapprox(torque[i], 0.21638545146325042; rtol = 1.0e-3)
    @test isapprox(phi[i], 0.0050213; rtol = 1.0e-3)
    # The gear efficiency survives the composite: a.e = T/(n*eta) at the peak.
    @test isapprox(columns["G1/gear/a.e"][i], torque[i] / (10.0 * 0.9);
        rtol = 1.0e-6, atol = 1.0e-9)
    # The input speed is held; the output speed is the ratio times it while in contact.
    @test isapprox(columns["G1/gear/a.f"][1], -f; rtol = 1e-12)
    @test isapprox(columns["G1/gear/b.f"][1], -f / 10.0; rtol = 1e-12)
end
