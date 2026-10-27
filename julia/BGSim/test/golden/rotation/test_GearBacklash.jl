# Golden test for `stdlib:rotation/GearBacklash` (plan section 8, M2 row: the spec's
# `GearBacklash`), through the real pipeline.
#
# Model: two `Sf` sources hold both shafts at fixed speeds, so the block's relative angle is
# `phi(t) = phi0 + fb*t` with `w = fb = a.f - b.f` (port a is driven at 0 and b at fb). The
# spec's dead-zone law
#
#   T = phi >  gap/2 ? max(k*(phi - gap/2) + d*w, 0) :
#       phi < -gap/2 ? min(k*(phi + gap/2) + d*w, 0) : 0,
#   a.e = T,  b.e = -T
#
# is then exact and algebraic. The static cases pin the gap, both contact sides and the
# contact damping; the ramp case checks the law on every recorded sample.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

const BACKLASH_K = 1.0e4        # N*m/rad
const BACKLASH_D = 5.0          # N*m*s/rad
const BACKLASH_GAP = 0.01       # rad

function backlash_torque(phi, w; k = BACKLASH_K, d = BACKLASH_D, gap = BACKLASH_GAP)
    if phi > gap / 2
        return max(k * (phi - gap / 2) + d * w, 0.0)
    elseif phi < -gap / 2
        return min(k * (phi + gap / 2) + d * w, 0.0)
    end
    return 0.0
end

function backlash_static_model(phi0, fb)
    return bg_model(
        "GearBacklashStatic",
        [
            bg_node("n1", "SfA", bg_ref("stdlib:bondgraph/Sf");
                params = Dict{String,Any}("f" => "0.0")),
            bg_node("n2", "P1", bg_ref("stdlib:rotation/GearBacklash");
                params = Dict{String,Any}(
                    "k" => string(BACKLASH_K), "d" => string(BACKLASH_D),
                    "gap" => string(BACKLASH_GAP)),
                starts = Dict{String,Any}("phi" => string(phi0))),
            bg_node("n3", "SfB", bg_ref("stdlib:bondgraph/Sf");
                params = Dict{String,Any}("f" => string(fb))),
        ],
        [
            bg_conn("c1", "bond", "n1", "p", "n2", "a"),
            bg_conn("c2", "bond", "n3", "p", "n2", "b"),
        ];
        t_end = 0.01, points = 11,
    )
end

@testset "golden: GearBacklash" begin
    for (phi0, fb, expected) in (
        (0.0, 0.0, 0.0),         # dead centre
        (0.004, 0.0, 0.0),       # inside the positive gap half: no torque
        (-0.004, 0.0, 0.0),      # inside the negative gap half
        (0.02, 0.0, 150.0),      # contact: k*(phi - gap/2)
        (-0.02, 0.0, -150.0),    # the mirrored contact
        (0.02, 0.1, 150.5),      # contact plus damping d*w
    )
        columns, result, flat = bg_run(backlash_static_model(phi0, fb))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        @test flat.stats.states == 1             # the relative angle phi
        @test bg_value(columns, "P1/T", 0.0) == expected
        @test bg_value(columns, "P1/a.e", 0.0) == expected
        @test bg_value(columns, "P1/b.e", 0.0) == -expected
        @test bg_value(columns, "P1/w", 0.0) == fb
        @test isapprox(bg_value(columns, "P1/phi", 0.01), phi0 + fb * 0.01;
            atol = 1e-12)
        # The recorded torque obeys the spec's law on every sample.
        @test all(
            columns["P1/T"][i] == backlash_torque(columns["P1/phi"][i], columns["P1/w"][i])
            for i in eachindex(columns["time"])
        )
        if fb == 0.0
            @test all(columns["P1/T"] .== expected)
        end
    end
end
