# Optional hard stops on the joint coordinate of `stdlib:spatial/Revolute3D`, `Prismatic3D`,
# `stdlib:multibond/Revolute2D` and `stdlib:planar/Prismatic2D` (structural constants `q_min`,
# `q_max`; parameters `k_stop`, `d_stop`, `w_stop`).
#
#   * a pendulum released toward a stop bounces back and stays within the limit plus a small
#     penetration (both sides, 3D and 2D), with no switching event added;
#   * a prismatic joint pushed by a constant force rests on its stop at `F / k_stop`;
#   * without stops (the default `-Inf`/`Inf`) the joints give **bit-identical** results to the
#     blocks before the stops existed (`fixtures/joint_stops/*Before.jl`).

using Test
using BGSim
import BGSim.IR
import BGSim.Compile
using LinearAlgebra

if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using .BondGraphGolden

if !isdefined(@__MODULE__, :_msp_pendulum)
    let src = read(joinpath(@__DIR__, "test_mech_spatial.jl"), String)
        cut = findfirst("@testset \"J-MB9 spatial body", src)
        include_string(@__MODULE__, src[1:(first(cut) - 1)], "test_mech_spatial.jl (helpers)")
    end
end
if !isdefined(@__MODULE__, :_pm_pendulum)
    let src = read(joinpath(@__DIR__, "test_planar_mechanics.jl"), String)
        cut = findfirst("@testset \"J-MB6 planar mechanics", src)
        include_string(@__MODULE__, src[1:(first(cut) - 1)], "test_planar_mechanics.jl (helpers)")
    end
end

const _JS_FIXTURES = joinpath(@__DIR__, "fixtures", "joint_stops")

function _js_node(doc, name)
    return only(n for n in doc["diagram"]["nodes"] if n["name"] == name)
end

function _js_stops!(doc, name; q_min = nothing, q_max = nothing, params = Dict{String,Any}())
    node = _js_node(doc, name)
    consts = get!(node, "constants", Dict{String,Any}())
    q_min === nothing || (consts["q_min"] = string(q_min))
    q_max === nothing || (consts["q_max"] = string(q_max))
    merge!(node["params"], params)
    return doc
end

function _js_inline!(doc, name, file)
    node = _js_node(doc, name)
    node["block"] = Dict{String,Any}("inline" => Dict{String,Any}(
        "source" => read(joinpath(_JS_FIXTURES, file), String)))
    return doc
end

_js_kinks(doc) = length(BGSim.nonsmooth_conditions(Compile.flatten(IR.parse_model(doc))))

"""Every signal both runs recorded, compared with `===` per sample."""
function _js_bitwise(a, b)
    common = [k for k in keys(a) if haskey(b, k)]
    @test length(common) > 20
    bad = String[]
    for k in common
        length(a[k]) == length(b[k]) && all(a[k] .=== b[k]) || push!(bad, k)
    end
    isempty(bad) || @info "signals that differ" bad
    return isempty(bad)
end

@testset "joint hard stops (q_min / q_max)" begin
    @testset "the four joints load clean with stops on and off" begin
        blocks = Dict(b.ref => b for b in BGSim.Library.load_stdlib())
        for ref in ("stdlib:spatial/Revolute3D", "stdlib:spatial/Prismatic3D",
            "stdlib:multibond/Revolute2D", "stdlib:planar/Prismatic2D")
            @test !BGSim.Library.has_errors(blocks[ref])
            consts = blocks[ref].interface.constants
            # JSON has no infinity: the catalog keeps the default as its text
            @test any(c -> c.name == "q_min" && c.default == "-Inf", consts)
            @test any(c -> c.name == "q_max" && c.default == "Inf", consts)
        end
    end

    @testset "Revolute3D pendulum bounces off the upper stop" begin
        q_max = 0.3
        base = _msp_pendulum(q0 = -0.6, t_end = 3.0, points = 3001)
        kinks_off = _js_kinks(base)
        doc = _js_stops!(_msp_pendulum(q0 = -0.6, t_end = 3.0, points = 3001), "Joint"; q_max = q_max)
        @test _js_kinks(doc) == kinks_off          # the stop adds no switching event
        columns, result, flat = bg_run(doc)
        @test result.status == "done"
        q = columns["Joint/qout"]
        qd = columns["Joint/qdout"]
        ts = columns["Joint/tau_stop"]
        @test maximum(q) > q_max                     # it reached the stop
        @test maximum(q) < q_max + 0.01              # small penetration (k_stop = 1e5)
        hit = findfirst(>(q_max), q)
        @test hit !== nothing
        @test any(<(-0.1), qd[hit:end])              # it bounces back
        @test any(<(q_max - 0.2), q[hit:end])
        @test maximum(abs, ts[1:(findfirst(>(q_max - 0.01), q) - 1)]) < 1.0e-3   # off the stop
        @test maximum(ts) > 1.0                      # a real contact torque
    end

    @testset "Revolute3D pendulum bounces off the lower stop" begin
        q_min = -0.25
        doc = _js_stops!(_msp_pendulum(q0 = 0.6, t_end = 3.0, points = 3001), "Joint";
            q_min = q_min, q_max = 2.0)
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        q = columns["Joint/qout"]
        @test minimum(q) < q_min
        @test minimum(q) > q_min - 0.01
        @test maximum(q) < 0.6 + 1.0e-6              # the upper stop at 2 rad never acts
    end

    @testset "Revolute3D without stops is bit-identical to the joint before the stops" begin
        new = _msp_pendulum(q0 = 0.6, t_end = 1.0, points = 201)
        old = _js_inline!(_msp_pendulum(q0 = 0.6, t_end = 1.0, points = 201), "Joint",
            "Revolute3DBefore.jl")
        a, ra, _ = bg_run(new)
        b, rb, _ = bg_run(old)
        @test ra.status == "done" && rb.status == "done"
        @test all(iszero, a["Joint/tau_stop"])
        @test _js_bitwise(a, b)
        # the double pendulum (a rotating parent)
        new2 = _msp_double(1.0e7; t_end = 0.5, points = 101)
        old2 = deepcopy(new2)
        _js_inline!(old2, "J1", "Revolute3DBefore.jl")
        _js_inline!(old2, "J2", "Revolute3DBefore.jl")
        a2, _, _ = bg_run(new2)
        b2, _, _ = bg_run(old2)
        @test _js_bitwise(a2, b2)
    end

    @testset "Prismatic3D rests on its stop under a constant force" begin
        F = 20.0
        k = 1.0e6
        for side in (+1.0, -1.0)
            doc = _msp_rig(; joint = "stdlib:spatial/Prismatic3D",
                params = Dict{String,Any}("kt" => "1.0e8", "kr" => "1.0e8"),
                g0 = 0.0, t_end = 2.0, points = 201, efforts = Dict("drive" => side * F))
            _js_stops!(doc, "Joint"; q_min = -0.05, q_max = 0.05,
                params = Dict{String,Any}("k_stop" => string(k), "d_stop" => "200.0"))
            columns, result, _ = bg_run(doc)
            @test result.status == "done"
            q = columns["Joint/qout"]
            @test abs(q[end]) > 0.05                       # pushed onto one of the stops
            @test abs(q[end]) < 0.05 + 2 * F / k           # resting at about F / k_stop past it
            @test isapprox(abs(columns["Joint/f_stop"][end]), F; rtol = 1.0e-3)
        end
    end

    @testset "Revolute2D pendulum bounces off its stop; bit-identical without" begin
        q_max = 0.2
        doc = _pm_pendulum(q0 = -0.5)
        doc["settings"]["t_end"] = 3.0
        # At the planar helper's 1e-9 tolerance Rodas5P runs out of steps on the stiff contact
        # (it fails near t = 2.6 s); at 1e-6 the run completes with the same peak to 1e-9 rad.
        doc["settings"]["reltol"] = 1.0e-6
        doc["settings"]["abstol"] = 1.0e-8
        _js_stops!(doc, "Joint"; q_max = q_max)
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        q = columns["Joint/qout"]
        @test maximum(q) > q_max
        @test maximum(q) < q_max + 0.01
        hit = findfirst(>(q_max), q)
        @test any(<(q_max - 0.2), q[hit:end])
        a, _, _ = bg_run(_pm_pendulum(q0 = 0.5))
        b, _, _ = bg_run(_js_inline!(_pm_pendulum(q0 = 0.5), "Joint", "Revolute2DBefore.jl"))
        @test _js_bitwise(a, b)
    end

    @testset "Prismatic2D: the mass-spring oscillator stays above its lower stop" begin
        doc = _pm_prismatic(q0 = 0.1)
        _js_stops!(doc, "Joint"; q_min = -0.05)
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        q = columns["Joint/qout"]
        @test minimum(q) < -0.05
        @test minimum(q) > -0.05 - 0.005
        @test maximum(q) <= 0.1 + 1.0e-6
    end
end
