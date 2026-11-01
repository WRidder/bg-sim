# Global (model-level) parameters: `src/compile/globals.jl`, the `parameters` array of the model
# contract, and their use in instance expressions (spec "Global parameters").
#
#   * evaluation order, arithmetic chains, Int/Real results, pure functions;
#   * E113 for a cycle (with its path), a non-finite result and a dependent of a failed global;
#   * E003 for an undeclared name, a duplicate, a reserved or built-in name;
#   * use in params and starts, inside a subsystem, in a structural constant;
#   * a changed global changes the simulation; `override_globals` re-folds dependents;
#   * the C/FMU export sees only the folded numbers.

using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import BGSim.Flat
import JSON3

const _GL_REPO = normpath(joinpath(@__DIR__, "..", "..", ".."))
const _GL_FIXTURE = joinpath(_GL_REPO, "contracts", "fixtures", "model", "valid",
    "model.global-parameters.json")
const _GL_CYCLE = joinpath(_GL_REPO, "contracts", "fixtures", "model", "semantic",
    "model.e113-global-cycle.json")

_gl_plain(x) = x isa AbstractDict ? Dict{String,Any}(String(k) => _gl_plain(v) for (k, v) in pairs(x)) :
               x isa AbstractVector ? Any[_gl_plain(v) for v in x] : x
_gl_doc() = _gl_plain(JSON3.read(read(_GL_FIXTURE, String)))

function _gl_model(globals; nodes = Any[], connections = Any[])
    return Dict{String,Any}(
        "format" => "bgsim.model",
        "language" => "0.1.0",
        "name" => "Globals",
        "parameters" => Any[Dict{String,Any}("name" => n, "value" => v) for (n, v) in globals],
        "diagram" => Dict{String,Any}("nodes" => nodes, "connections" => connections),
        "settings" => Dict{String,Any}(
            "t_start" => 0.0, "t_end" => 1.0, "solver" => "auto", "reltol" => 1e-8,
            "abstol" => 1e-10, "max_step" => nothing,
            "output" => Dict{String,Any}("mode" => "points", "points" => 11),
            "event_limit" => 10000),
    )
end

_gl_const(id, name, value) = Dict{String,Any}(
    "id" => id, "name" => name, "block" => Dict{String,Any}("ref" => "stdlib:sources/Constant"),
    "position" => Dict{String,Any}("x" => 0, "y" => 0), "params" => Dict{String,Any}("value" => value))

_gl_eval(globals) = Compile.evaluate_globals(IR.parse_model(_gl_model(globals)))
_gl_codes(diags) = [d.code for d in diags]
_gl_param(fm, id) = only(p.value for p in fm.parameters if p.id == id)
_gl_errors(fm) = [d for d in fm.diagnostics if d.severity == "error"]

function _gl_columns(dir)
    m = JSON3.read(read(joinpath(dir, "manifest.json"), String))
    n = Int(m.time.n)
    nsig = length(m.signals)
    raw = read(joinpath(dir, "columns.f64"))
    columns = reshape(reinterpret(Float64, raw), (n, nsig + 1))
    out = Dict{String,Vector{Float64}}("time" => collect(columns[:, 1]))
    for (j, signal) in enumerate(m.signals)
        out[String(signal.id)] = collect(columns[:, j + 1])
    end
    return out
end

@testset "global parameters" begin
    @testset "parse: the contract's top-level parameters array" begin
        md = IR.parse_model(_GL_FIXTURE)
        @test [g.name for g in md.globals] == ["m", "rate", "x0"]
        @test md.globals[1].unit == "kg"
        @test md.globals[1].description == "Base mass"
        @test md.globals[3].unit === nothing
        # A model without `parameters` has none.
        plain = _gl_model(Pair{String,String}[])
        delete!(plain, "parameters")
        @test isempty(IR.parse_model(plain).globals)
    end

    @testset "evaluation order, chains and functions" begin
        # Declared out of order: `k` uses `m`, which comes later; `w` chains through both.
        env, diags = _gl_eval(["k" => "4*m", "w" => "sqrt(k/m)", "m" => "2", "n" => "3"])
        @test isempty(diags)
        @test env.values[:m] == 2
        @test env.values[:m] isa Int
        @test env.values[:k] == 8
        @test env.values[:w] ≈ 2.0
        @test env.values[:n] isa Int
        @test findfirst(==(:m), env.order) < findfirst(==(:k), env.order) <
              findfirst(==(:w), env.order)
        @test env.deps[:w] == [:k, :m]
        env, diags = _gl_eval(["a" => "1.5e-3", "b" => "-a^2 + max(a, 2) * (1 + 1)",
            "c" => "ifelse(b > 0, 1.0, 2.0)"])
        @test isempty(diags)
        @test env.values[:b] ≈ -(1.5e-3)^2 + 4
        @test env.values[:c] == 1.0
        @test Compile.evaluate_globals_values(IR.parse_model(_gl_model(["m" => "2"]))) ==
              Dict("m" => 2)
    end

    @testset "cycles are E113 with the cycle path" begin
        env, diags = _gl_eval(["a" => "b + 1", "b" => "2*c", "c" => "a", "d" => "a + 1",
            "e" => "1"])
        cyc = [d for d in diags if d.code == "E113" && occursin("cycle", d.message)]
        @test length(cyc) == 1
        @test occursin("a -> b -> c -> a", only(cyc).message)
        @test only(cyc).scope == "global:a"
        @test only(cyc).path === nothing
        @test :a in env.failed && :b in env.failed && :c in env.failed
        # `d` depends on the cycle: it fails as a dependent, `e` is unaffected.
        @test :d in env.failed
        @test any(d -> d.code == "E113" && d.scope == "global:d", diags)
        @test env.values[:e] == 1
        # A self-reference is a one-element cycle.
        _, diags = _gl_eval(["x" => "x + 1"])
        @test any(d -> d.code == "E113" && occursin("x -> x", d.message), diags)
        # Two separate cycles are two diagnostics.
        _, diags = _gl_eval(["p" => "q", "q" => "p", "r" => "s", "s" => "r"])
        @test count(d -> d.code == "E113" && occursin("cycle", d.message), diags) == 2
    end

    @testset "names: undeclared, duplicate, reserved, built-in" begin
        env, diags = _gl_eval(["k" => "4*mass"])
        @test _gl_codes(diags) == ["E003"]
        @test occursin("`mass`", only(diags).message)
        @test :k in env.failed
        _, diags = _gl_eval(["m" => "1", "m" => "2"])
        @test any(d -> d.code == "E003" && occursin("declared twice", d.message), diags)
        _, diags = _gl_eval(["t" => "1"])
        @test any(d -> d.code == "E003" && occursin("reserved", d.message), diags)
        _, diags = _gl_eval(["pi" => "3"])
        @test any(d -> d.code == "E003" && occursin("reserved", d.message), diags)
        _, diags = _gl_eval(["sin" => "1"])
        @test any(d -> d.code == "E003" && occursin("built-in", d.message), diags)
        _, diags = _gl_eval(["bad name" => "1"])
        @test any(d -> d.code == "E003" && occursin("not an identifier", d.message), diags)
    end

    @testset "the built-in constants pi and π" begin
        env, diags = _gl_eval(["f" => "50", "w" => "2*pi*f", "q" => "π/4"])
        @test isempty(diags)
        @test env.values[:w] ≈ 100pi
        @test env.values[:q] ≈ pi / 4
        @test env.deps[:w] == [:f]
        @test isempty(env.deps[:q])

        # the table is the shared contract fixture (the web evaluator checks the same one)
        table = JSON3.read(read(joinpath(_GL_REPO, "contracts", "fixtures", "constants",
            "builtin_constants.json"), String))
        @test Set(Symbol(c.name) for c in table.constants) == Set(keys(BGSim.BUILTIN_CONSTANTS))
        for c in table.constants
            want = c.value == "Inf" ? Inf : Float64(c.value)
            @test BGSim.BUILTIN_CONSTANTS[Symbol(c.name)] == want
            # none can name a global
            _, diags = _gl_eval([String(c.name) => "1"])
            @test any(d -> d.code == "E003", diags)
        end
        env, diags = _gl_eval(["a" => "30*deg", "w" => "3000*rpm", "W" => "m*g_n", "m" => "2",
                               "T" => "T_0C + 20"])
        @test isempty(diags)
        @test env.values[:a] ≈ pi / 6
        @test env.values[:w] ≈ 100pi
        @test env.values[:W] == 2 * 9.80665
        @test env.values[:T] ≈ 293.15
        # a global must be finite; Inf is for limits inside blocks
        _, diags = _gl_eval(["x" => "Inf"])
        @test any(d -> d.code == "E113" && occursin("not finite", d.message), diags)
    end

    @testset "built-in constants in a block: folded, not declarable" begin
        src = """
        @block ConstUse begin
            @parameters begin
                a::Real = 30*deg
                hi::Real = Inf
            end
            @inputs u::Real
            @outputs y::Real
            @equations begin
                y ~ clamp(sin(a) * u * g_n, -hi, hi)
            end
        end
        """
        pb = BGSim.parse_block(src; filename = "x", ref = "inline:x")
        @test isempty([d for d in BGSim.check_block(pb) if d.severity == "error"])
        ps = Dict(d.name => d for d in BGSim.declarations(pb, :parameters))
        @test BGSim.eval_const(ps[:a].default) ≈ pi / 6
        @test BGSim.eval_const(ps[:hi].default) == Inf
        bad = BGSim.parse_block("""
        @block ConstDecl begin
            @parameters g_n::Real = 9.81
            @outputs y::Real
            @equations begin
                y ~ g_n
            end
        end
        """; filename = "x", ref = "inline:x")
        @test any(d -> d.code == "E003" && occursin("built-in constant", d.message),
            BGSim.check_block(bad))

        # In a model, a block that declares one reports its own E003, and its wires are not an
        # E102 each (the node has no ports because its block did not load).
        src = "@block RpmOut begin\n    @inputs w::Real\n    @outputs begin\n        rpm::Real\n" *
              "        regen::Real\n    end\n    @equations begin\n        rpm ~ w\n        regen ~ 2.0*w\n" *
              "    end\nend"
        node = Dict{String,Any}("id" => "n2", "name" => "Motor",
            "block" => Dict{String,Any}("inline" => Dict{String,Any}("source" => src)),
            "position" => Dict{String,Any}("x" => 0, "y" => 0), "params" => Dict{String,Any}())
        wire(id, port) = Dict{String,Any}("id" => id, "kind" => "signal",
            "from" => Dict{String,Any}("node" => "n2", "port" => port),
            "to" => Dict{String,Any}("node" => "n3", "port" => "u"))
        sink(id) = Dict{String,Any}("id" => id, "name" => "Sink$id",
            "block" => Dict{String,Any}("ref" => "stdlib:continuous/Gain"),
            "position" => Dict{String,Any}("x" => 0, "y" => 0), "params" => Dict{String,Any}())
        doc = _gl_model(Pair{String,String}[]; nodes = Any[_gl_const("n1", "W", "1.0"), node, sink("n3")],
            connections = Any[
                Dict{String,Any}("id" => "c1", "kind" => "signal",
                    "from" => Dict{String,Any}("node" => "n1", "port" => "y"),
                    "to" => Dict{String,Any}("node" => "n2", "port" => "w")),
                wire("c2", "regen")])
        errors = _gl_errors(Compile.flatten(IR.parse_model(doc)))
        @test [d.code for d in errors] == ["E003"]
        @test occursin("`rpm` is a built-in constant", only(errors).message)
    end

    @testset "values: syntax, whitelist, finiteness, numbers" begin
        _, diags = _gl_eval(["m" => "2 +"])
        @test _gl_codes(diags) == ["E001"]
        _, diags = _gl_eval(["m" => "rand(1)"])
        @test "E002" in _gl_codes(diags)
        _, diags = _gl_eval(["z" => "0", "m" => "1/z"])
        @test any(d -> d.code == "E113" && d.scope == "global:m", diags)
        _, diags = _gl_eval(["m" => "1e308 * 10"])
        @test any(d -> d.code == "E113" && occursin("not finite", d.message), diags)
        _, diags = _gl_eval(["m" => "sqrt(-1)"])
        @test any(d -> d.code == "E113" && d.scope == "global:m", diags)
        _, diags = _gl_eval(["m" => "1 < 2"])
        @test any(d -> d.code in ("E004",) && d.scope == "global:m", diags)
    end

    @testset "use in params, starts and inside a subsystem" begin
        fm = Compile.flatten(IR.parse_model(_GL_FIXTURE))
        @test isempty(_gl_errors(fm))
        @test _gl_param(fm, "Source/Rate/value") == 8
        x = only(v for v in fm.variables if v.id == "Int1/x")
        @test x.start ≈ sqrt(2) + 0.5

        # A start, a constant and a parameter on one instance; the structural constant `n` of
        # an inline block takes an Int global.
        inline = Dict{String,Any}(
            "id" => "n2", "name" => "Vec", "position" => Dict{String,Any}("x" => 0, "y" => 0),
            "block" => Dict{String,Any}("inline" => Dict{String,Any}("source" => """
                @block Vec begin
                    @constants n::Int = 2
                    @parameters g::Real = 1.0
                    @outputs y::Vec{n}
                    @equations begin
                        for i in 1:n
                            y[i] ~ g * i
                        end
                    end
                end""")),
            "constants" => Dict{String,Any}("n" => "count"),
            "params" => Dict{String,Any}("g" => "gain / 2"))
        doc = _gl_model(["count" => "1 + 2", "gain" => "3"];
            nodes = Any[_gl_const("n1", "C1", "2*gain"), inline])
        fm = Compile.flatten(IR.parse_model(doc))
        @test isempty(_gl_errors(fm))
        @test _gl_param(fm, "C1/value") == 6
        @test _gl_param(fm, "Vec/g") == 1.5
        @test any(v -> v.id == "Vec/y[3]", fm.variables)
    end

    @testset "instance diagnostics: undeclared name and a broken global" begin
        doc = _gl_model(["m" => "2"]; nodes = Any[_gl_const("n1", "C1", "mass * 2")])
        fm = Compile.flatten(IR.parse_model(doc))
        d = only(d for d in fm.diagnostics if d.code == "E003")
        @test d.node == "n1"
        @test occursin("global parameter", d.hint)

        fm = Compile.flatten(IR.parse_model(_GL_CYCLE))
        @test any(d -> d.code == "E113" && d.node === nothing && occursin("cycle", d.message),
            fm.diagnostics)
        @test any(d -> d.code == "E113" && d.node == "n1", fm.diagnostics)

        # A number literal with an exponent is not a reference to a global named `e`.
        doc = _gl_model(["e" => "1/0"]; nodes = Any[_gl_const("n1", "C1", "1e-3")])
        fm = Compile.flatten(IR.parse_model(doc))
        @test !any(d -> d.node == "n1", fm.diagnostics)
        @test _gl_param(fm, "C1/value") == 1e-3
    end

    @testset "a changed global changes the simulation; override_globals re-folds" begin
        settings = BGSim.RunSettings(t_start = 0.0, t_end = 1.0, solver = "Tsit5",
            reltol = 1e-10, abstol = 1e-12,
            output = Dict{String,Any}("mode" => "points", "points" => 11))
        md = IR.parse_model(_GL_FIXTURE)
        dir = mktempdir()
        result = BGSim.simulate(Compile.flatten(md); run_dir = dir, settings = settings)
        @test result.status == "done"
        y = _gl_columns(dir)["Int1/y"]
        @test y[1] ≈ sqrt(2) + 0.5 atol = 1e-9
        @test y[end] ≈ sqrt(2) + 0.5 + 8 atol = 1e-7

        # The dashboard hook: `global:m` = 3 before evaluation, so `rate` = 12, `x0` = sqrt(3)+0.5.
        md3 = IR.override_globals(md, Dict("global:m" => 3, "Int1/x" => "ignored"))
        @test md3.globals[1].value == "3"
        @test md.globals[1].value == "2"           # the original is untouched
        dir3 = mktempdir()
        BGSim.simulate(Compile.flatten(md3); run_dir = dir3, settings = settings)
        y3 = _gl_columns(dir3)["Int1/y"]
        @test y3[1] ≈ sqrt(3) + 0.5 atol = 1e-9
        @test y3[end] ≈ sqrt(3) + 0.5 + 12 atol = 1e-7
        @test IR.override_globals(md, Dict("global:m" => "2*2")).globals[1].value == "2*2"
        @test IR.override_globals(md, Dict{String,Any}()) === md
        @test_throws ArgumentError IR.override_globals(md, Dict("global:nope" => 1))
    end

    @testset "the C/FMU export sees the folded numbers" begin
        doc = _gl_doc()
        # Mark the output for the export interface: Int1/y -> ExportOutput.
        push!(doc["diagram"]["nodes"], Dict{String,Any}(
            "id" => "n3", "name" => "Out", "position" => Dict{String,Any}("x" => 400, "y" => 120),
            "block" => Dict{String,Any}("ref" => "stdlib:converters/ExportOutput")))
        push!(doc["diagram"]["connections"], Dict{String,Any}(
            "id" => "c2", "kind" => "signal", "from" => Dict{String,Any}("node" => "n2", "port" => "y"),
            "to" => Dict{String,Any}("node" => "n3", "port" => "u")))
        fm = Compile.flatten(IR.parse_model(doc))
        @test isempty(_gl_errors(fm))
        out = mktempdir()
        result = BGSim.Export.export_model(fm, out;
            settings = BGSim.Export.ExportSettings(step = 1e-2, t_end = 1.0))
        @test result.ok
        model_c = read(joinpath(out, "sources", "model.c"), String)
        # No global name survives into the generated code; the folded rate (8) does.
        @test !occursin(r"\brate\b", model_c)
        @test occursin("8", model_c)
        xml = read(joinpath(out, "modelDescription.xml"), String)
        @test !occursin("\"rate\"", xml) && !occursin("\"m\"", xml)
    end
end
