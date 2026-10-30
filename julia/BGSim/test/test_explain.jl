# Work package J4.3: `model.explain` (plan 5.13).
#
# For one signal id: its kind after `mtkcompile` (differential state, algebraic unknown,
# observed, alias, parameter, discrete held output), the defining expression of an observed
# signal rendered with our signal ids, `aliasOf`, the source equations that mention it with
# their origins, and the W201/W202 findings that involve it. It needs no run and uses the
# compile cache: a warm call must take less than 300 ms.

using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import JSON3

const _XT_REPO = normpath(joinpath(@__DIR__, "..", "..", ".."))
const _XT_DC_PROJECT = joinpath(_XT_REPO, "examples", "dc-motor")
const _XT_DC = joinpath(_XT_DC_PROJECT, "models", "iconic.bgmodel.json")
const _XT_KALMAN_PROJECT = joinpath(_XT_REPO, "examples", "drivetrain-kalman")
const _XT_KALMAN = joinpath(_XT_KALMAN_PROJECT, "models", "drivetrain-kalman.bgmodel.json")
const _XT_CAUSALITY = joinpath(@__DIR__, "fixtures", "causality")

_xt_explain(signal; model = _XT_DC, project = _XT_DC_PROJECT) =
    model_explain(model, project, signal)

@testset "model.explain (J4.3)" begin
    @testset "state, observed and alias with their origins (dc-motor iconic)" begin
        # A differential state: the winding current is the integrated variable.
        r = _xt_explain("Motor1/gyrator/n.f")
        @test r.signal == "Motor1/gyrator/n.f"
        @test r.kind == "state"
        @test r.unit == "A"
        @test r.expression === nothing && r.aliasOf === nothing
        @test isempty(r.diagnostics)
        @test !isempty(r.equations)
        paths = Set(e.origin.path for e in r.equations)
        @test "Motor1/gyrator" in paths && "Motor1/inductor" in paths
        gyrator = first(e for e in r.equations if e.origin.path == "Motor1/gyrator")
        @test gyrator.origin.ref == "stdlib:converters/EMConverter"
        @test gyrator.origin.range.line > 0 && gyrator.origin.range.endCol >= gyrator.origin.range.col
        @test occursin("s\"Motor1/gyrator/n.f\"", gyrator.text) && occursin(" ~ ", gyrator.text)

        # An observed signal: the defining expression is rendered with our ids.
        r = _xt_explain("Motor1/p.e")
        @test r.kind == "observed"
        @test r.unit == "V"
        @test r.aliasOf === nothing
        @test r.expression isa String
        @test occursin("s\"V1/V\"", r.expression) && occursin("s\"Step1/y\"", r.expression)
        @test !occursin("var\"", r.expression) && !occursin("(t)", r.expression)
        # An observed signal with a conditional.
        r = _xt_explain("Step1/y")
        @test r.kind == "observed"
        @test startswith(r.expression, "ifelse(")
        @test occursin("s\"Step1/t_step\"", r.expression) && occursin("s\"Step1/final\"", r.expression)
        # A power (derived) signal is a product of a flow and an effort.
        r = _xt_explain("Motor1/p.P")
        @test r.kind == "observed" && r.unit == "W"
        @test occursin("s\"Motor1/gyrator/n.f\"", r.expression) &&
              occursin("s\"Motor1/p.e\"", r.expression) && occursin(" * ", r.expression)

        # An alias: the observed equation's right-hand side is a single variable.
        r = _xt_explain("Motor1/i")
        @test r.kind == "alias"
        @test r.aliasOf == "Motor1/gyrator/n.f"
        @test r.expression === nothing
        @test r.unit == "A"
        r = _xt_explain("Motor1/shaft.f")
        @test r.kind == "alias"
        @test r.aliasOf in ("Damp1/a.f", "Motor1/rotor/w")
        @test r.unit == "1/s"
        # The state the alias points at is a state, not an alias.
        @test _xt_explain(r.aliasOf).kind in ("state", "alias")

        # Another differential state (the rotor speed) and the angle.
        @test _xt_explain("Motor1/rotor/w").kind == "state"
        @test _xt_explain("Motor1/rotor/phi").kind == "state"
    end

    @testset "parameters and unknown signals" begin
        r = _xt_explain("Motor1/R")
        @test r.kind == "parameter"
        @test r.unit == "Ohm"
        @test r.expression === nothing && r.aliasOf === nothing
        @test any(e -> e.origin.ref == "stdlib:electrical/Resistor" && e.origin.path == "Motor1/resistor",
            r.equations)
        @test isempty(r.diagnostics)

        # An unknown signal is an E003 diagnostic in the result, not an exception.
        r = _xt_explain("Motor1/nope")
        @test r.signal == "Motor1/nope"
        @test length(r.diagnostics) == 1
        @test r.diagnostics[1].code == "E003" && r.diagnostics[1].severity == "error"
        @test isempty(r.equations) && r.expression === nothing && r.aliasOf === nothing
        @test r.diagnostics[1] isa NamedTuple
    end

    @testset "a held discrete output (drivetrain-kalman)" begin
        md = IR.parse_model(_XT_KALMAN)
        flat = Compile.flatten(md; project_dir = _XT_KALMAN_PROJECT)
        held = [String(s.id) for s in flat.signals if String(s.kind) == "discrete"]
        @test !isempty(held)
        for id in held
            r = _xt_explain(id; model = _XT_KALMAN, project = _XT_KALMAN_PROJECT)
            @test r.kind == "discrete"
            @test r.expression === nothing && r.aliasOf === nothing
            @test isempty(r.diagnostics) || all(d -> d.code in ("W201", "W202"), r.diagnostics)
        end
        # A parameter of the same model.
        p = first(p.id for p in flat.parameters if !(p.id in held))
        @test _xt_explain(p; model = _XT_KALMAN, project = _XT_KALMAN_PROJECT).kind == "parameter"
    end

    @testset "W201 and W202 findings that involve the signal" begin
        # Two compliances in series: W201 on C2.
        model = joinpath(_XT_CAUSALITY, "two_c_series.json")
        flat = Compile.flatten(IR.parse_model(model))
        c2 = [String(s.id) for s in flat.signals if s.path == "C2"]
        @test !isempty(c2)
        r = _xt_explain(first(c2); model = model, project = nothing)
        @test any(d -> d.code == "W201" && d.path == "C2", r.diagnostics)
        @test all(d -> d.code in ("W201", "W202"), r.diagnostics)
        # An R-R loop: W202 names both resistors, so a signal of either one is involved.
        model = joinpath(_XT_CAUSALITY, "r_r_loop.json")
        flat = Compile.flatten(IR.parse_model(model))
        for name in ("R1", "R2")
            ids = [String(s.id) for s in flat.signals if s.path == name]
            @test !isempty(ids)
            r = _xt_explain(first(ids); model = model, project = nothing)
            @test any(d -> d.code == "W202" && occursin("R1, R2", d.message), r.diagnostics)
        end
    end

    @testset "a warm call takes less than 300 ms and needs no recompile" begin
        _xt_explain("Motor1/i")                      # fills the compile cache
        builds = compile_build_count()
        times = Float64[]
        for signal in ("Motor1/i", "Motor1/p.e", "Motor1/gyrator/n.f", "Motor1/R", "Motor1/nope")
            t0 = time_ns()
            _xt_explain(signal)
            push!(times, (time_ns() - t0) / 1.0e9)
        end
        @test compile_build_count() == builds         # a cache hit: no mtkcompile
        println("  model.explain warm: ", join((round(1000 * t; digits = 1) for t in times), ", "), " ms")
        @test maximum(times) < 0.3
    end
end
