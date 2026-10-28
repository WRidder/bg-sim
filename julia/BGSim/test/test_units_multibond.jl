# Work package J-MB2: per-component units for multibond ports (finding F9, D-MB2/D-MB3/
# D-MB8/D-MB10; plan 5.3, 5.6, 9.1 and Gate B).
#
# The acceptance tests:
#   * the component unit vectors of `Planar`/`Spatial` and the refusal of a whole-port
#     single unit (`effort_dims(:Planar)` throws instead of claiming `N`);
#   * the catalog's `domain.components` and the block checker take their units from the same
#     table: a torque/force mix is E006 naming both units and the component, for a literal
#     index **and** inside the unrolled `for k in 1:D`;
#   * `p.P` is the scalar dot product `Σ_k e[k]*f[k]` with unit W, and is legal in a block;
#   * every component of a multibond port gets its own `FlatVar.unit` (including the virtual
#     pair of a junction-to-junction bond) and the power signal is W;
#   * a real planar run records `p.e[1] = "N*m"`, `p.e[2..3] = "N"`,
#     `p.f[1] = "rad/s"`, `p.f[2..3] = "m/s"` and `p.P = "W"` in the run manifest, and a
#     spatial run records the six-component equivalent and its live dot product;
#   * `contracts/fixtures/model/semantic/model.e006-unit-mismatch.json` yields E006;
#   * the C-MB1 valid `model.planar.multibond.json` and `model.frame-bridge.json` check
#     clean once their Ground block writes `p.f[k]` component-wise; the contract-owned
#     fixtures still write `p.f ~ [0, 0, 0]`, so the tests below pin exactly that pending
#     E006 (C-MB1 updates them) and `model.spatial.multibond.json` also still needs J-MB4's
#     `Ad(pose)` (see the last testset: the remaining errors are asserted, not weakened).
#
# `unit_string` is dimension-based (plan 5.3), so a computed unit prints `J` for `N*m` and
# `1/s` for `rad/s`; a **multibond port component** carries the catalog spelling in its
# signal label instead (`attrs[:unit_label]`, J-MB2), because a torque shown as energy is
# misleading. The diagnostic labels likewise use `N*m`/`rad/s`.
using Test
using JSON3
import BGSim
import BGSim.IR
import BGSim.Compile
import BGSim.Flat
import BGSim.Units
import BGSim.Library
import BGSim: simulate, RunSettings, check_block, parse_block

const MB = BGSim.Units

const MB_ROOT = normpath(joinpath(@__DIR__, "..", "..", ".."))
const MB_MODEL_VALID = joinpath(MB_ROOT, "contracts", "fixtures", "model", "valid")
const MB_MODEL_SEMANTIC = joinpath(MB_ROOT, "contracts", "fixtures", "model", "semantic")

# ---------------------------------------------------------------------------------------
# Model-document builders
# ---------------------------------------------------------------------------------------

function _mb2_settings(t_end = 0.1, points = 2)
    return Dict{String,Any}(
        "t_start" => 0.0,
        "t_end" => t_end,
        "solver" => "auto",
        "reltol" => 1.0e-9,
        "abstol" => 1.0e-11,
        "max_step" => nothing,
        "output" => Dict{String,Any}("mode" => "points", "points" => points),
        "event_limit" => 10000,
    )
end

function _mb2_node(id, name, block)
    return Dict{String,Any}(
        "id" => id,
        "name" => name,
        "block" => block,
        "position" => Dict{String,Any}("x" => 0.0, "y" => 0.0),
        "params" => Dict{String,Any}(),
        "constants" => Dict{String,Any}(),
        "starts" => Dict{String,Any}(),
    )
end

_mb2_inline(source) = Dict{String,Any}("inline" => Dict{String,Any}("source" => source))

function _mb2_endpoint(node, port)
    ep = Dict{String,Any}("node" => node)
    port === nothing || (ep["port"] = port)
    return ep
end

function _mb2_conn(id, from_node, from_port, to_node, to_port = nothing)
    return Dict{String,Any}(
        "id" => id,
        "kind" => "bond",
        "from" => _mb2_endpoint(from_node, from_port),
        "to" => _mb2_endpoint(to_node, to_port),
    )
end

function _mb2_model(name; nodes = Any[], connections = Any[], t_end = 0.1, points = 2)
    return Dict{String,Any}(
        "format" => "bgsim.model",
        "language" => "0.1.0",
        "name" => name,
        "diagram" => _mb2_diagram(nodes, connections),
        "settings" => _mb2_settings(t_end, points),
        "plots" => Any[],
        "scene" => nothing,
        "bindings" => Any[],
    )
end

function _mb2_diagram(nodes, connections)
    return Dict{String,Any}(
        "nodes" => Any[nodes...],
        "connections" => Any[connections...],
        "subsystemPorts" => Any[],
        "annotations" => Any[],
    )
end

_mb2_check(md::IR.ModelDoc) = BGSim.Compile.model_check(md)
_mb2_check(model::AbstractDict) = BGSim.Compile.model_check(IR.parse_model(model))
_mb2_flatten(model::AbstractDict) = BGSim.Compile.flatten(IR.parse_model(model))

_mb2_errors(result) = [d for d in result.diagnostics if d.severity == "error"]
_mb2_has(result, code) = any(d -> d.code == code, result.diagnostics)
function _mb2_diag(result, code)
    hits = [d for d in result.diagnostics if d.code == code]
    return isempty(hits) ? nothing : hits[1]
end
_mb2_unit_diags(pb) = [d for d in check_block(pb) if d.code == "E006"]

_mb2_var(fm, id) = fm.variables[findfirst(v -> v.id == id, fm.variables)]
function _mb2_signal(fm, id)
    return only(filter(s -> s.id == id, fm.signals))
end

# ---------------------------------------------------------------------------------------
# Inline blocks
# ---------------------------------------------------------------------------------------

function _mb2_ground(domain::AbstractString)
    n = domain == "Planar" ? 3 : 6
    return """
    @block Ground$(domain)Units begin
        @ports p::Power{$domain}, [frame = "world"]
        @equations begin
            for k in 1:$n
                p.f[k] ~ 0.0
            end
        end
        @causality p => (:flow_out, :fixed)
    end
    """
end

function _mb2_sink(domain::AbstractString)
    n = domain == "Planar" ? 3 : 6
    return """
    @block Sink$(domain)Units begin
        @ports p::Power{$domain}, [frame = "world"]
        @equations begin
            for k in 1:$n
                p.f[k] ~ 0.0
            end
        end
    end
    """
end

# Ground -> 1-junction -> sink: one bond is a multibond of `domain`.
function _mb2_junction_model(domain::AbstractString)
    n = domain == "Planar" ? 3 : 6
    return _mb2_model(
        "Junction$(domain)Units";
        nodes = Any[
            _mb2_node("n1", "World", _mb2_inline(_mb2_ground(domain))),
            _mb2_node("n2", "J1", Dict{String,Any}("junction" => "1")),
            _mb2_node("n3", "Load", _mb2_inline(_mb2_sink(domain))),
        ],
        connections = Any[
            _mb2_conn("c1", "n1", "p", "n2"),
            _mb2_conn("c2", "n2", nothing, "n3", "p"),
        ],
    )
end

# Two junctions, so the bond between them is a virtual per-component (e, f) pair.
function _mb2_junction_pair_model()
    return _mb2_model(
        "JunctionPairPlanarUnits";
        nodes = Any[
            _mb2_node("n1", "World", _mb2_inline(_mb2_ground("Planar"))),
            _mb2_node("n2", "J1", Dict{String,Any}("junction" => "1")),
            _mb2_node("n3", "J2", Dict{String,Any}("junction" => "1")),
            _mb2_node("n4", "Load", _mb2_inline(_mb2_sink("Planar"))),
        ],
        connections = Any[
            _mb2_conn("c1", "n1", "p", "n2"),
            _mb2_conn("c2", "n2", nothing, "n3"),
            _mb2_conn("c3", "n3", nothing, "n4", "p"),
        ],
    )
end

# A runnable multibond model: a wrench source drives an inertia through one bond. Its only
# job is to exercise the real `simulate` path with a planar (or spatial) port.
function _mb2_source_block(domain::AbstractString)
    n = domain == "Planar" ? 3 : 6
    effort = domain == "Planar" ? ["tau", "F", "F3"] : ["tau", "tau2", "tau3", "F", "F2", "F3"]
    units = domain == "Planar" ? ["N*m", "N", "N"] :
            ["N*m", "N*m", "N*m", "N", "N", "N"]
    params = ["$(effort[k])::Real = $(Float64(k)), [unit = \"$(units[k])\"]" for k in 1:n]
    eqs = ["p.e[$(k)] ~ $(effort[k])" for k in 1:n]
    return """
    @block Drive$(domain)Units begin
        @ports p::Power{$domain}, [frame = "world"]
        @parameters begin
            $(join(params, "\n        "))
        end
        @equations begin
            $(join(eqs, "\n            "))
        end
    end
    """
end

function _mb2_inertia_block(domain::AbstractString)
    n = domain == "Planar" ? 3 : 6
    angular = domain == "Planar" ? 1 : 3
    eqs = String[]
    for k in 1:n
        push!(eqs, "ddt(P[$(k)]) ~ p.e[$(k)]")
    end
    for k in 1:n
        inertia = k <= angular ? "J" : "m"
        push!(eqs, "p.f[$(k)] ~ P[$(k)] / $inertia")
    end
    return """
    @block Inertia$(domain)Units begin
        @ports p::Power{$domain}, [frame = "world"]
        @parameters begin
            m::Real = 1.0, [unit = "kg"]
            J::Real = 1.0, [unit = "kg*m^2"]
        end
        @variables P::Vec{$n} = [$(join(zeros(Int, n), ", "))], [state = :prefer]
        @equations begin
            $(join(eqs, "\n            "))
        end
        @causality p => :flow_out
    end
    """
end

function _mb2_drive_model(domain::AbstractString)
    return _mb2_model(
        "Run$(domain)Units";
        nodes = Any[
            _mb2_node("n1", "Drive", _mb2_inline(_mb2_source_block(domain))),
            _mb2_node("n2", "Body", _mb2_inline(_mb2_inertia_block(domain))),
        ],
        connections = Any[_mb2_conn("c1", "n1", "p", "n2", "p")],
        t_end = 0.2,
        points = 3,
    )
end

# ---------------------------------------------------------------------------------------
# The suite
# ---------------------------------------------------------------------------------------

@testset "J-MB2 per-component multibond units" begin
    @testset "component unit vectors and the catalog agree" begin
        # Exact units, angular first (D-MB2). `N*m` and `J` are one dimension, and so are
        # `rad/s` and `1/s`; the catalog strings are the user-facing spelling.
        @test MB.effort_component_dims(:Planar) ==
              [MB.parse_unit("N*m"), MB.parse_unit("N"), MB.parse_unit("N")]
        @test MB.flow_component_dims(:Planar) ==
              [MB.parse_unit("rad/s"), MB.parse_unit("m/s"), MB.parse_unit("m/s")]
        @test MB.effort_component_dims(:Spatial) ==
              vcat([MB.parse_unit("N*m") for _ in 1:3], [MB.parse_unit("N") for _ in 1:3])
        @test MB.flow_component_dims(:Spatial) ==
              vcat([MB.parse_unit("rad/s") for _ in 1:3], [MB.parse_unit("m/s") for _ in 1:3])
        @test MB.component_count(:Planar) == 3
        @test MB.component_count(:Spatial) == 6
        @test MB.component_count(:Rotation) == 1

        # A whole multibond port has no single unit: the one-argument form refuses, and the
        # indexed form is bounds-checked.
        @test_throws ArgumentError MB.effort_dims(:Planar)
        @test_throws ArgumentError MB.flow_dims(:Spatial)
        @test_throws ArgumentError MB.effort_dims(:Planar, 4)
        @test_throws ArgumentError MB.effort_dims(:Rotation, 2)

        # The catalog's `domain.components` is the checker's table (F9/D-MB10): one string
        # list, parsed back to the same per-component `Dims`.
        for domain in (:Planar, :Spatial)
            components = Library.domain_components(domain)
            @test components.effort == MB.domain_effort_unit_strings(domain)
            @test components.flow == MB.domain_flow_unit_strings(domain)
            @test [MB.parse_unit(u) for u in components.effort] ==
                  MB.effort_component_dims(domain)
            @test [MB.parse_unit(u) for u in components.flow] ==
                  MB.flow_component_dims(domain)
            @test MB.power_dims(domain) == MB.parse_unit("W")
        end
        @test Library.domain_components(:Rotation) === nothing
        @test MB.domain_effort_unit_strings(:Rotation) == ["N*m"]

        # The power of every component pair is W; a table that disagreed would throw.
        @test MB.power_dims(:Planar) == MB.effort_dims(:Planar, 1) * MB.flow_dims(:Planar, 1)
        @test MB.power_dims(:Planar) == MB.effort_dims(:Planar, 2) * MB.flow_dims(:Planar, 2)
        @test MB.power_dims(:Spatial) == MB.effort_dims(:Spatial, 4) * MB.flow_dims(:Spatial, 4)
    end

    @testset "the checker sees p.e[k]/p.f[k] with their own units" begin
        # A torque component is not a force component (finding F9).
        torque_force = parse_block("""
        @block TorqueForceMix begin
            @ports p::Power{Planar}
            @equations p.e[1] ~ p.e[2]
        end
        """)
        diags = _mb2_unit_diags(torque_force)
        @test length(diags) == 1
        @test occursin("[N]", diags[1].message)
        @test occursin("[N*m]", diags[1].message)
        @test occursin("p.e[1]", diags[1].hint) && occursin("p.e[2]", diags[1].hint)
        @test occursin("[N*m]", diags[1].hint) && occursin("[N]", diags[1].hint)

        # The same for flow: an angular rate is not a linear velocity.
        rate_velocity = parse_block("""
        @block RateVelocityMix begin
            @ports p::Power{Planar}
            @equations p.f[1] ~ p.f[2]
        end
        """)
        diags = _mb2_unit_diags(rate_velocity)
        @test length(diags) == 1
        @test occursin("[m/s]", diags[1].message)
        @test occursin("[rad/s]", diags[1].message)

        # A user variable declared in N*m cannot be assigned to the force component.
        user_unit = parse_block("""
        @block TorqueIntoForceComponent begin
            @ports p::Power{Planar}
            @variables tau::Real, [unit = "N*m"]
            @equations p.e[3] ~ tau
        end
        """)
        diags = _mb2_unit_diags(user_unit)
        @test length(diags) == 1
        @test occursin("[N*m]", diags[1].message)
        @test occursin("[N]", diags[1].message)

        # Spatial: an angular component 2 is not the linear component 4.
        spatial = parse_block("""
        @block SpatialComponentMix begin
            @ports p::Power{Spatial}
            @equations p.e[2] ~ p.e[4]
        end
        """)
        diags = _mb2_unit_diags(spatial)
        @test length(diags) == 1
        @test occursin("[N*m]", diags[1].message)
        @test occursin("[N]", diags[1].message)

        # The unrolled `for k in 1:D` form: the loop index is substituted before the unit
        # lookup, so components 2 and 3 are N against the declared N*m (component 1 is
        # correct).
        loop_planar = parse_block("""
        @block PlanarLoopUnits begin
            @ports p::Power{Planar}
            @variables P::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m"]
            @equations begin
                for k in 1:3
                    p.e[k] ~ P[k]
                end
            end
        end
        """)
        diags = _mb2_unit_diags(loop_planar)
        @test length(diags) == 2
        @test all(d -> occursin("[N]", d.message) && occursin("[N*m]", d.message), diags)

        loop_spatial = parse_block("""
        @block SpatialLoopUnits begin
            @ports p::Power{Spatial}
            @variables w::Vec{6} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [unit = "rad/s"]
            @equations begin
                for k in 1:6
                    p.f[k] ~ w[k]
                end
            end
        end
        """)
        diags = _mb2_unit_diags(loop_spatial)
        @test length(diags) == 3          # components 4:6 are m/s, not rad/s
        @test all(d -> occursin("[m/s]", d.message) && occursin("[rad/s]", d.message), diags)

        # A correct per-component block is clean: the fixture's body equations.
        clean = parse_block("""
        @block PlanarBodyUnits begin
            @ports p::Power{Planar}
            @parameters begin
                m::Real = 1.2, [unit = "kg"]
                J::Real = 0.04, [unit = "kg*m^2"]
            end
            @variables P::Vec{3} = [0.0, 0.0, 0.0], [state = :prefer]
            @equations begin
                p.f[1] ~ P[1] / J
                p.f[2] ~ P[2] / m
                p.f[3] ~ P[3] / m
                for k in 1:3
                    ddt(P[k]) ~ p.e[k]
                end
            end
        end
        """)
        @test isempty(_mb2_unit_diags(clean))
    end

    @testset "p.P is the scalar power sum in W" begin
        # `p.P` is the derived power signal (D15), not a port field a block may write: the
        # scope check rejects `p.P` in an equation (E003). The unit environment still
        # carries it, so a model-level consumer that resolves it sees W.
        port = parse_block("""
        @block PlanarPowerPort begin
            @ports p::Power{Planar}
            @equations p.f[1] ~ 0.0
        end
        """)
        env = MB.unit_env(port)
        @test env.names[Symbol("p.P")] == MB.parse_unit("W")
        @test env.labels[Symbol("p.P")] == "W"
        @test MB.unit_env(parse_block("""
        @block RotationPowerPort begin
            @ports p::Power{Rotation}
            @equations p.f ~ 0.0
        end
        """)).names[Symbol("p.P")] == MB.parse_unit("W")

        # The explicit dot product is W: a balanced block checks clean.
        explicit = parse_block("""
        @block PlanarExplicitPower begin
            @ports p::Power{Planar}
            @variables power::Real = 0.0, [unit = "W"]
            @equations begin
                power ~ p.e[1] * p.f[1] + p.e[2] * p.f[2] + p.e[3] * p.f[3]
                p.f[1] ~ 0.0
                p.f[2] ~ 0.0
                p.f[3] ~ 0.0
            end
        end
        """)
        @test isempty(check_block(explicit))
        @test isempty(_mb2_unit_diags(explicit))

        # A single component is an effort, not a power: E006.
        wrong = parse_block("""
        @block PlanarWrongPower begin
            @ports p::Power{Planar}
            @variables y::Real = 0.0, [unit = "N"]
            @equations y ~ p.e[1] * p.f[1]
        end
        """)
        diags = _mb2_unit_diags(wrong)
        @test length(diags) == 1
        @test occursin("[W]", diags[1].message)
        @test occursin("[N]", diags[1].message)
    end

    @testset "a whole multibond field is E006, not a wildcard" begin
        # `p.e ~ [F, F, F]` with F in N must not pass: component 1 is a torque. Plan 5.3
        # writes multibond equations component-wise (D-MB10), so a bare field is an error.
        whole_literal = parse_block("""
        @block WholeFieldLiteral begin
            @ports p::Power{Planar}
            @parameters F::Real = 1.0, [unit = "N"]
            @equations p.e ~ [F, F, F]
        end
        """)
        diags = _mb2_unit_diags(whole_literal)
        @test length(diags) == 1
        @test occursin("whole multibond port field", diags[1].message)
        @test occursin("p.e", diags[1].message)
        @test occursin("component-wise (D-MB10)", diags[1].hint)
        @test occursin("p.e[k]", diags[1].hint)
        @test diags[1].source !== nothing
        @test diags[1].source.range !== nothing

        whole_flow = parse_block("""
        @block WholeFieldFlow begin
            @ports p::Power{Planar}
            @variables v::Real, [unit = "m/s"]
            @equations p.f ~ v
        end
        """)
        diags = _mb2_unit_diags(whole_flow)
        @test length(diags) == 1
        @test occursin("p.f", diags[1].message)
        @test occursin("component-wise (D-MB10)", diags[1].hint)

        # Two whole fields are two mistakes, each named with its own component-wise hint.
        whole_pair = parse_block("""
        @block WholeFieldPair begin
            @ports p::Power{Planar}
            @equations p.e ~ p.f
        end
        """)
        diags = _mb2_unit_diags(whole_pair)
        @test length(diags) == 2
        @test any(d -> occursin("`p.e`", d.message), diags)
        @test any(d -> occursin("`p.f`", d.message), diags)
        @test all(d -> occursin("component-wise (D-MB10)", d.hint), diags)

        # Spatial is the same rule (six components).
        whole_spatial = parse_block("""
        @block WholeFieldSpatial begin
            @ports a::Power{Spatial}
            @parameters w::Real = 1.0, [unit = "rad/s"]
            @equations a.f ~ w
        end
        """)
        diags = _mb2_unit_diags(whole_spatial)
        @test length(diags) == 1
        @test occursin("6 components", diags[1].message)

        # Scalar domains keep their whole-field meaning (`p.e` is the one effort).
        scalar = parse_block("""
        @block ScalarWholeField begin
            @ports p::Power{Rotation}
            @variables y::Real = 0.0, [unit = "N*m"]
            @equations y ~ p.e
        end
        """)
        @test isempty(_mb2_unit_diags(scalar))
    end

    @testset "component indices are folded and bounds-checked" begin
        # `p.e[1+1]` is component 2 (a force), so a torque variable cannot equal it.
        folded = parse_block("""
        @block FoldedIndex begin
            @ports p::Power{Planar}
            @variables y::Real = 0.0, [unit = "N*m"]
            @equations y ~ p.e[1 + 1]
        end
        """)
        diags = _mb2_unit_diags(folded)
        @test length(diags) == 1
        @test occursin("[N]", diags[1].message)
        @test occursin("[N*m]", diags[1].message)
        @test occursin("p.e[1 + 1]", diags[1].hint)

        # `k+1` inside the loop: k = 1, 2 gives components 2 and 3, both forces.
        looped = parse_block("""
        @block FoldedLoopIndex begin
            @ports p::Power{Planar}
            @variables y::Vec{2} = [0.0, 0.0], [unit = "N*m"]
            @equations begin
                for k in 1:2
                    y[k] ~ p.e[k + 1]
                end
            end
        end
        """)
        diags = _mb2_unit_diags(looped)
        @test length(diags) == 2
        @test all(d -> occursin("[N]", d.message) && occursin("[N*m]", d.message), diags)

        # A constant index folds too, and stays in range.
        const_index = parse_block("""
        @block ConstIndex begin
            @ports p::Power{Planar}
            @constants D = 2
            @variables y::Real = 0.0, [unit = "N"]
            @equations y ~ p.e[D]
        end
        """)
        @test isempty(_mb2_unit_diags(const_index))

        # An out-of-range component is E005 (owned by the size check), not a silent
        # wildcard and not a bogus whole-field E006. The literal, a folded expression and a
        # loop range wider than the port are all covered; the unit pass does not duplicate.
        function range_codes(source)
            pb = parse_block(source)
            return pb, [d.code for d in check_block(pb)]
        end
        _, codes = range_codes("""
        @block OutOfRangeIndex begin
            @ports p::Power{Planar}
            @variables y::Real = 0.0, [unit = "N"]
            @equations y ~ p.e[4]
        end
        """)
        @test count(==("E005"), codes) == 1
        @test !("E006" in codes)

        _, codes = range_codes("""
        @block FoldedOutOfRange begin
            @ports p::Power{Planar}
            @variables y::Real = 0.0, [unit = "N"]
            @equations y ~ p.e[2 + 2]
        end
        """)
        @test count(==("E005"), codes) == 1
        @test !("E006" in codes)

        # A loop range wider than the port is E005 too, and the unit pass adds no E006.
        looped_range, codes = range_codes("""
        @block LoopedOutOfRange begin
            @ports p::Power{Planar}
            @variables y::Real = 0.0
            @equations begin
                for k in 1:5
                    y ~ p.e[k]
                end
            end
        end
        """)
        @test count(==("E005"), codes) == 1
        @test !("E006" in codes)
        d = first(d for d in check_block(looped_range) if d.code == "E005")
        @test occursin("loop index", d.message)
        @test d.source !== nothing && d.source.range !== nothing

        # A non-static index cannot be resolved: E006 naming the component index rule.
        dynamic = parse_block("""
        @block DynamicIndex begin
            @ports p::Power{Spatial}
            @parameters i::Real = 1.0
            @variables y::Real = 0.0, [unit = "N"]
            @equations y ~ p.e[i]
        end
        """)
        diags = _mb2_unit_diags(dynamic)
        @test length(diags) == 1
        @test occursin("static integer", diags[1].message)
        @test occursin("p.e[i]", diags[1].message)
    end

    @testset "per-component FlatVar.unit and the power signal" begin
        planar = _mb2_flatten(_mb2_junction_model("Planar"))
        @test isempty(planar.diagnostics)
        e = [MB.parse_unit("N*m"), MB.parse_unit("N"), MB.parse_unit("N")]
        f = [MB.parse_unit("rad/s"), MB.parse_unit("m/s"), MB.parse_unit("m/s")]
        for port in ("World/p", "Load/p")
            for k in 1:3
                @test _mb2_var(planar, "$port.e[$k]").unit == e[k]
                @test _mb2_var(planar, "$port.f[$k]").unit == f[k]
            end
            # The signal label is the catalog spelling, not the dimension printer: a
            # torque component must not read `J` and an angular rate must not read `1/s`.
            @test _mb2_signal(planar, "$port.e[1]").unit == "N*m"
            @test _mb2_signal(planar, "$port.e[2]").unit == "N"
            @test _mb2_signal(planar, "$port.e[3]").unit == "N"
            @test _mb2_signal(planar, "$port.f[1]").unit == "rad/s"
            @test _mb2_signal(planar, "$port.f[2]").unit == "m/s"
            @test _mb2_signal(planar, "$port.f[3]").unit == "m/s"
            @test _mb2_signal(planar, "$port.P").unit == "W"
            @test _mb2_signal(planar, "$port.P").kind == "power"
            # The label lives on the port component; the `Dims` stays authoritative.
            @test _mb2_var(planar, "$port.e[1]").attrs[:unit_label] == "N*m"
            @test _mb2_var(planar, "$port.f[1]").attrs[:unit_label] == "rad/s"
            power = only(s for s in planar.derived if s.id == "$port.P")
            @test power.unit == MB.parse_unit("W")
        end
        # The power expression is the three-term dot product, not one `e*f`.
        p = only(s for s in planar.derived if s.id == "World/p.P")
        @test occursin("World/p.e[1]", sprint(show, p.expr))
        @test occursin("World/p.f[3]", sprint(show, p.expr))

        spatial = _mb2_flatten(_mb2_junction_model("Spatial"))
        @test isempty(spatial.diagnostics)
        for k in 1:3
            @test _mb2_var(spatial, "World/p.e[$k]").unit == MB.parse_unit("N*m")
            @test _mb2_var(spatial, "World/p.f[$k]").unit == MB.parse_unit("rad/s")
        end
        for k in 4:6
            @test _mb2_var(spatial, "World/p.e[$k]").unit == MB.parse_unit("N")
            @test _mb2_var(spatial, "World/p.f[$k]").unit == MB.parse_unit("m/s")
        end
        @test _mb2_signal(spatial, "Load/p.P").unit == "W"
        @test _mb2_signal(spatial, "World/p.e[1]").unit == "N*m"
        @test _mb2_signal(spatial, "World/p.e[4]").unit == "N"
        @test _mb2_signal(spatial, "World/p.f[1]").unit == "rad/s"
        @test _mb2_signal(spatial, "World/p.f[6]").unit == "m/s"

        # The virtual pair of a junction-to-junction planar bond is per component too.
        pair = _mb2_flatten(_mb2_junction_pair_model())
        @test _mb2_var(pair, "c2.e[1]").unit == MB.parse_unit("N*m")
        @test _mb2_var(pair, "c2.e[2]").unit == MB.parse_unit("N")
        @test _mb2_var(pair, "c2.e[3]").unit == MB.parse_unit("N")
        @test _mb2_var(pair, "c2.f[1]").unit == MB.parse_unit("rad/s")
        @test _mb2_var(pair, "c2.f[2]").unit == MB.parse_unit("m/s")
    end

    @testset "a real planar run records the per-component units" begin
        flat = _mb2_flatten(_mb2_drive_model("Planar"))
        @test isempty(flat.diagnostics)
        dir = mktempdir()
        result = simulate(
            flat;
            run_dir = dir,
            settings = RunSettings(
                t_end = 0.2,
                output = Dict{String,Any}("mode" => "points", "points" => 3),
            ),
        )
        @test result.status == "done"
        @test !_mb2_has(result, "W201")
        @test !_mb2_has(result, "E006")
        @test isempty(_mb2_errors(result))

        manifest = JSON3.read(read(joinpath(dir, "manifest.json"), String))
        units = Dict{String,Any}(String(s.id) => s.unit for s in manifest.signals)
        @test units["Drive/p.e[1]"] == "N*m"
        @test units["Drive/p.e[2]"] == "N"
        @test units["Drive/p.e[3]"] == "N"
        @test units["Drive/p.f[1]"] == "rad/s"
        @test units["Drive/p.f[2]"] == "m/s"
        @test units["Drive/p.f[3]"] == "m/s"
        @test units["Drive/p.P"] == "W"
        @test units["Body/p.e[1]"] == "N*m"
        @test units["Body/p.e[3]"] == "N"
        @test units["Body/p.f[1]"] == "rad/s"
        @test units["Body/p.f[3]"] == "m/s"
        @test units["Body/p.P"] == "W"

        # P = Σ_k e[k]*f[k]: e = (1, 2, 3), J = m = 1, so P_body(t) = 14 t.
        n = Int(manifest.time.n)
        nsig = length(manifest.signals)
        raw = read(joinpath(dir, "columns.f64"))
        columns = reshape(reinterpret(Float64, raw), (n, nsig + 1))
        ids = String[String(s.id) for s in manifest.signals]
        times = columns[:, 1]
        power = columns[:, findfirst(==("Body/p.P"), ids) + 1]
        for i in 1:n
            @test isapprox(power[i], 14.0 * times[i]; atol = 1e-9)
        end
        # The source carries the same power with the opposite sign (it delivers it).
        source_power = columns[:, findfirst(==("Drive/p.P"), ids) + 1]
        @test all(isapprox.(source_power, -power; atol = 1e-9))
    end

    @testset "a real spatial run records the six-component units" begin
        flat = _mb2_flatten(_mb2_drive_model("Spatial"))
        @test isempty(flat.diagnostics)
        dir = mktempdir()
        result = simulate(
            flat;
            run_dir = dir,
            settings = RunSettings(
                t_end = 0.1,
                output = Dict{String,Any}("mode" => "points", "points" => 2),
            ),
        )
        @test result.status == "done"
        @test !_mb2_has(result, "W201")
        manifest = JSON3.read(read(joinpath(dir, "manifest.json"), String))
        units = Dict{String,Any}(String(s.id) => s.unit for s in manifest.signals)
        for k in 1:3
            @test units["Body/p.e[$k]"] == "N*m"
            @test units["Body/p.f[$k]"] == "rad/s"
        end
        for k in 4:6
            @test units["Body/p.e[$k]"] == "N"
            @test units["Body/p.f[$k]"] == "m/s"
        end
        @test units["Body/p.P"] == "W"
        @test units["Drive/p.e[1]"] == "N*m"
        @test units["Drive/p.f[6]"] == "m/s"

        # The scalar power really is the six-component dot product: e = (1, …, 6) and
        # J = m = 1, so P_body(t) = (Σ k²) t = 91 t. A three-component sum would not
        # reproduce this.
        n = Int(manifest.time.n)
        nsig = length(manifest.signals)
        raw = read(joinpath(dir, "columns.f64"))
        columns = reshape(reinterpret(Float64, raw), (n, nsig + 1))
        ids = String[String(s.id) for s in manifest.signals]
        times = columns[:, 1]
        power = columns[:, findfirst(==("Body/p.P"), ids) + 1]
        for i in 1:n
            direct = sum(
                columns[i, findfirst(==("Body/p.e[$k]"), ids) + 1] *
                columns[i, findfirst(==("Body/p.f[$k]"), ids) + 1] for k in 1:6
            )
            @test isapprox(power[i], direct; atol = 1e-12)
            @test isapprox(power[i], 91.0 * times[i]; atol = 1e-9)
        end
        # The source delivers it: the same dot product with the opposite sign.
        source_power = columns[:, findfirst(==("Drive/p.P"), ids) + 1]
        @test all(isapprox.(source_power, -power; atol = 1e-9))
    end

    @testset "labels and component dims cannot drift" begin
        # `units.jl` asserts this at load time; repeating it here documents the rule and
        # covers every scalar domain, whose label is its whole unit.
        for domain in keys(MB.DOMAIN_UNIT_LABELS)
            labels = MB.DOMAIN_UNIT_LABELS[domain]
            @test MB.parse_unit(labels[1]) == MB.effort_dims(domain, 1)
            @test MB.parse_unit(labels[2]) == MB.flow_dims(domain, 1)
        end
        for domain in (:Planar, :Spatial)
            labels = MB.DOMAIN_COMPONENT_LABELS[domain]
            for k in 1:MB.component_count(domain)
                @test MB.parse_unit(labels.effort[k]) == MB.effort_dims(domain, k)
                @test MB.parse_unit(labels.flow[k]) == MB.flow_dims(domain, k)
            end
            @test Library.domain_components(domain).effort == labels.effort
            @test Library.domain_components(domain).flow == labels.flow
        end
        # The canonical printer is unchanged for computed/declaration units.
        @test MB.unit_string(MB.parse_unit("N*m")) == "J"
        @test MB.unit_string(MB.parse_unit("rad/s")) == "1/s"
    end

    @testset "subsystem unit arrays are compared by parsed Dims" begin
        function subsystem_model(; domain, size, effort_units, flow_units)
            face = Dict{String,Any}(
                "name" => "p", "kind" => "power", "domain" => domain,
                "size" => Any[size], "node" => "s1", "port" => "p",
            )
            effort_units === nothing || (face["effortUnits"] = Any[effort_units...])
            flow_units === nothing || (face["flowUnits"] = Any[flow_units...])
            internal = domain in ("Planar", "Spatial") ? _mb2_sink(domain) :
                       """
                       @block RotSinkUnits begin
                           @ports p::Power{Rotation}
                           @equations p.f ~ 0.0
                       end
                       """
            sub = Dict{String,Any}(
                "ports" => Any[face],
                "diagram" => _mb2_diagram(
                    Any[_mb2_node("s1", "Internal", _mb2_inline(internal))], Any[]),
            )
            ground = domain in ("Planar", "Spatial") ? _mb2_ground(domain) :
                     """
                     @block RotGroundUnits begin
                         @ports p::Power{Rotation}
                         @equations p.e ~ 0.0
                     end
                     """
            return _mb2_model(
                "SubsystemUnits";
                nodes = Any[
                    _mb2_node("n1", "World", _mb2_inline(ground)),
                    _mb2_node("n2", "Arm", Dict{String,Any}("subsystem" => sub)),
                ],
                connections = Any[_mb2_conn("c1", "n1", "p", "n2", "p")],
            )
        end

        # `J` is `N*m` and `1/s` is `rad/s`: a different spelling of the same dimension is
        # accepted, so the contract is about units, not strings.
        spelled = _mb2_check(subsystem_model(domain = "Planar", size = 3,
            effort_units = ["J", "N", "N"], flow_units = ["1/s", "m/s", "m/s"]))
        @test isempty(_mb2_errors(spelled))

        wrong = _mb2_check(subsystem_model(domain = "Planar", size = 3,
            effort_units = ["N", "N", "N"], flow_units = nothing))
        d = _mb2_diag(wrong, "E102")
        @test d !== nothing
        @test occursin("effortUnits", d.message)
        @test occursin("N*m", d.message) && occursin("N", d.message)

        bad = _mb2_check(subsystem_model(domain = "Planar", size = 3,
            effort_units = ["N*m", "N", "furlong"], flow_units = nothing))
        d = _mb2_diag(bad, "E102")
        @test d !== nothing
        @test occursin("furlong", d.message)

        short = _mb2_check(subsystem_model(domain = "Spatial", size = 6,
            effort_units = ["N*m", "N", "N"], flow_units = nothing))
        d = _mb2_diag(short, "E102")
        @test d !== nothing
        @test occursin("3 effortUnits", d.message)

        # A component array on a scalar domain is meaningless.
        scalar = _mb2_check(subsystem_model(domain = "Rotation", size = 1,
            effort_units = ["N*m"], flow_units = nothing))
        d = _mb2_diag(scalar, "E102")
        @test d !== nothing
        @test occursin("scalar", d.message)
        @test occursin("effortUnits", d.message)
    end

    @testset "the semantic E006 fixture yields E006" begin
        result = _mb2_check(IR.parse_model(
            joinpath(MB_MODEL_SEMANTIC, "model.e006-unit-mismatch.json")))
        e006 = [d for d in result.diagnostics if d.code == "E006"]
        # The fixture's subject: a torque added to a force, and nothing else.
        torque_force = [d for d in e006 if occursin("cannot add", d.message)]
        @test length(torque_force) == 1
        @test length(e006) == 1
        @test torque_force[1].path == "BadUnits"
        @test torque_force[1].severity == "error"
        @test occursin("[N]", torque_force[1].message)
        @test occursin("[N*m]", torque_force[1].message)
    end

    @testset "the valid C-MB1 multibond models" begin
        # The contract fixtures are component-wise by contract (D-MB10) since the C-MB1
        # fixture follow-up, so a valid multibond model must check clean — no unit rule
        # exception, no `Ad` arity gap.
        planar = _mb2_check(IR.parse_model(
            joinpath(MB_MODEL_VALID, "model.planar.multibond.json")))
        @test isempty(planar.diagnostics)
        @test !_mb2_has(planar, "E007")

        # The planar transform (the component-wise `y*b.f[1]` equations) is clean.
        planar_md = IR.parse_model(joinpath(MB_MODEL_VALID, "model.planar.multibond.json"))
        mount = parse_block(planar_md.diagram.nodes[3].inline_source)
        @test isempty([d for d in check_block(mount) if d.code == "E006"])

        bridge = _mb2_check(IR.parse_model(
            joinpath(MB_MODEL_VALID, "model.frame-bridge.json")))
        @test isempty(bridge.diagnostics)
        @test !_mb2_has(bridge, "E007")

        # The spatial slice is fully clean now that its Mount is a component-wise,
        # power-continuous pure-translation adjoint (no six-argument `Ad` call).
        spatial = _mb2_check(IR.parse_model(
            joinpath(MB_MODEL_VALID, "model.spatial.multibond.json")))
        @test isempty(spatial.diagnostics)
        @test !_mb2_has(spatial, "E007")
    end
end
