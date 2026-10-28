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
#   * a real planar run records `p.e[1] = "J"` (N*m), `p.e[2..3] = "N"`,
#     `p.f[1] = "1/s"` (rad/s), `p.f[2..3] = "m/s"` and `p.P = "W"` in the run manifest, and
#     a spatial run records the six-component equivalent;
#   * `contracts/fixtures/model/semantic/model.e006-unit-mismatch.json` yields E006;
#   * the C-MB1 valid `model.planar.multibond.json` and `model.frame-bridge.json` check
#     clean; `model.spatial.multibond.json` is unit-clean but still fails on the J-MB4
#     primitive `Ad(pose)` (see the last testset: the error is asserted, not weakened).
#
# `unit_string` is dimension-based (plan 5.3), so a torque prints `J` and an angular rate
# `1/s`: those are the strings the run manifest records for `N*m` and `rad/s`. The
# diagnostic labels use the catalog's spellings (`N*m`, `rad/s`) because a user wrote them.
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
        "diagram" => Dict{String,Any}(
            "nodes" => Any[nodes...],
            "connections" => Any[connections...],
            "subsystemPorts" => Any[],
            "annotations" => Any[],
        ),
        "settings" => _mb2_settings(t_end, points),
        "plots" => Any[],
        "scene" => nothing,
        "bindings" => Any[],
    )
end

_mb2_check(md::IR.ModelDoc) = BGSim.Compile.model_check(md)
_mb2_check(model::AbstractDict) = BGSim.Compile.model_check(IR.parse_model(model))
_mb2_flatten(model::AbstractDict) = BGSim.Compile.flatten(IR.parse_model(model))

_mb2_errors(result) = [d for d in result.diagnostics if d.severity == "error"]
_mb2_has(result, code) = any(d -> d.code == code, result.diagnostics)
_mb2_diag(result, code) = first((d for d in result.diagnostics if d.code == code), nothing)
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
    zeros_text = join(zeros(Int, n), ", ")
    return """
    @block Ground$(domain)Units begin
        @ports p::Power{$domain}, [frame = "world"]
        @equations p.f ~ [$zeros_text]
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
            @test _mb2_signal(planar, "$port.e[1]").unit == "J"        # N*m prints J
            @test _mb2_signal(planar, "$port.e[2]").unit == "N"
            @test _mb2_signal(planar, "$port.e[3]").unit == "N"
            @test _mb2_signal(planar, "$port.f[1]").unit == "1/s"      # rad/s is 1/s
            @test _mb2_signal(planar, "$port.f[2]").unit == "m/s"
            @test _mb2_signal(planar, "$port.f[3]").unit == "m/s"
            @test _mb2_signal(planar, "$port.P").unit == "W"
            @test _mb2_signal(planar, "$port.P").kind == "power"
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
        @test units["Drive/p.e[1]"] == "J"        # N*m
        @test units["Drive/p.e[2]"] == "N"
        @test units["Drive/p.e[3]"] == "N"
        @test units["Drive/p.f[1]"] == "1/s"      # rad/s
        @test units["Drive/p.f[2]"] == "m/s"
        @test units["Drive/p.f[3]"] == "m/s"
        @test units["Drive/p.P"] == "W"
        @test units["Body/p.e[1]"] == "J"
        @test units["Body/p.e[3]"] == "N"
        @test units["Body/p.f[1]"] == "1/s"
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
        @test units["Body/p.e[1]"] == "J"
        @test units["Body/p.e[2]"] == "J"
        @test units["Body/p.e[3]"] == "J"
        @test units["Body/p.e[4]"] == "N"
        @test units["Body/p.e[6]"] == "N"
        @test units["Body/p.f[1]"] == "1/s"
        @test units["Body/p.f[3]"] == "1/s"
        @test units["Body/p.f[4]"] == "m/s"
        @test units["Body/p.P"] == "W"
    end

    @testset "the semantic E006 fixture yields E006" begin
        result = _mb2_check(IR.parse_model(
            joinpath(MB_MODEL_SEMANTIC, "model.e006-unit-mismatch.json")))
        e006 = [d for d in result.diagnostics if d.code == "E006"]
        @test length(e006) == 1
        @test e006[1].path == "BadUnits"
        @test e006[1].severity == "error"
        @test occursin("[N]", e006[1].message)
        @test occursin("[N*m]", e006[1].message)
    end

    @testset "the valid C-MB1 multibond models" begin
        # The planar slice is now unit-clean: component-wise torque/force units make the
        # transform's `Ad`-style equations check (`y*b.f[1]` is a velocity, not m^2/s).
        planar = _mb2_check(IR.parse_model(
            joinpath(MB_MODEL_VALID, "model.planar.multibond.json")))
        @test isempty(_mb2_errors(planar))
        @test !_mb2_has(planar, "E006")

        bridge = _mb2_check(IR.parse_model(
            joinpath(MB_MODEL_VALID, "model.frame-bridge.json")))
        @test isempty(_mb2_errors(bridge))
        @test !_mb2_has(bridge, "E006")

        # The spatial slice is unit-clean but cannot assemble yet: its transform uses the
        # six-argument `Ad(x, y, z, roll, pitch, yaw)`, which is J-MB4's pose-valued
        # primitive (`_check_call!` still rejects a Vec argument and the whitelist row has
        # arity 1). The block is dropped, so the port E102s are the cascade of that E001.
        # J-MB4 owns making this fixture check clean; the units are already correct here.
        spatial = _mb2_check(IR.parse_model(
            joinpath(MB_MODEL_VALID, "model.spatial.multibond.json")))
        @test !_mb2_has(spatial, "E006")
        @test any(
            d -> d.code == "E001" && occursin("`Ad` takes 1 argument", d.message),
            spatial.diagnostics,
        )
    end
end
