# Work package J-MB1: `Power{Planar}`/`Power{Spatial}`, frame metadata and E007.
#
# The acceptance tests:
#   * planars port size 3 and spatial size 6 through instantiation: flat ids per component,
#     stats/unknowns, and per-component junction equations on a 0- and a 1-junction;
#   * `@ports ...[frame = "name"]`, `portDecl.frame`, `catalogBlock.dimension` and
#     `blockInterface.dimension`;
#   * the D-MB5 frame union-find: a direct bond, a junction with three ports, a wire group, a
#     frame-neutral port that adopts its neighbour's frame, a subsystem face that is
#     authoritative outside, one legal internal transform and one illegal direct internal
#     bond;
#   * `model.check.frames` (instance-qualified, keyed by connection id) and
#     `model.check.multibond` (2 for Planar, 3 for Spatial).
#
# The C-MB1 contract fixtures are consumed directly where J-MB1 owns the semantics (the E007
# case and the frame/domain metadata of the valid multibond models). The transform blocks in
# `model.planar.multibond.json`, `model.spatial.multibond.json` and `model.frame-bridge.json`
# additionally use per-component units and a six-argument `Ad`; those two features are
# J-MB2 and J-MB3, so their *end-to-end* clean check belongs to those work packages. J-MB1
# asserts the frame and multibond facts of the same fixtures here, and exercises the same
# topology end-to-end with inline blocks whose equations are legal at J-MB1's uniform-unit
# stage (see the "subsystem frames" testset).

using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import BGSim.Library
import JSON3

const _REPO = normpath(joinpath(@__DIR__, "..", "..", ".."))
const _MODEL_VALID = joinpath(_REPO, "contracts", "fixtures", "model", "valid")
const _MODEL_SEMANTIC = joinpath(_REPO, "contracts", "fixtures", "model", "semantic")
const _RPC_VALID = joinpath(_REPO, "contracts", "fixtures", "worker-rpc", "valid")

# ---------------------------------------------------------------------------------------
# Model document builders (plain Dicts are accepted by IR.parse_model)
# ---------------------------------------------------------------------------------------

function _settings()
    return Dict{String,Any}(
        "t_start" => 0.0,
        "t_end" => 1.0,
        "solver" => "auto",
        "reltol" => 1.0e-6,
        "abstol" => 1.0e-8,
        "max_step" => nothing,
        "output" => Dict{String,Any}("mode" => "points", "points" => 10),
        "event_limit" => 10000,
    )
end

function _node(id, name, block)
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

_inline(source) = Dict{String,Any}("inline" => Dict{String,Any}("source" => source))
_junction(kind) = Dict{String,Any}("junction" => string(kind))

function _endpoint(node, port)
    ep = Dict{String,Any}("node" => node)
    port === nothing || (ep["port"] = port)
    return ep
end

function _conn(id, kind, from_node, from_port, to_node, to_port = nothing)
    return Dict{String,Any}(
        "id" => id,
        "kind" => kind,
        "from" => _endpoint(from_node, from_port),
        "to" => _endpoint(to_node, to_port),
    )
end

function _diagram(nodes, connections, ports = Any[])
    return Dict{String,Any}(
        "nodes" => nodes,
        "connections" => connections,
        "subsystemPorts" => ports,
        "annotations" => Any[],
    )
end

function _model(name; nodes = Any[], connections = Any[], diagram = nothing, ports = Any[])
    return Dict{String,Any}(
        "format" => "bgsim.model",
        "language" => "0.1.0",
        "name" => name,
        "diagram" => something(diagram, _diagram(nodes, connections, ports)),
        "settings" => _settings(),
        "plots" => Any[],
        "scene" => nothing,
        "bindings" => Any[],
    )
end

check(md::IR.ModelDoc; project_dir = nothing) =
    BGSim.Compile.model_check(md; project_dir = project_dir)
check(model; project_dir = nothing) =
    BGSim.Compile.model_check(IR.parse_model(model); project_dir = project_dir)
flatten(md::IR.ModelDoc) = BGSim.Compile.flatten(md)
flatten(model) = BGSim.Compile.flatten(IR.parse_model(model))

_has_code(result, code) = any(d -> d.code == code, result.diagnostics)
_diag(result, code) = first(d for d in result.diagnostics if d.code == code)
_codes(result) = [d.code for d in result.diagnostics]

# Inline blocks used by the frame tests. `_source_block` is the system-under-test's generic
# "hold the flow at zero" port; the causality declaration is optional so a junction model can
# avoid a causal conflict that is not the subject of the test.
function _sink_block(domain::AbstractString, frame)
    n = domain == "Planar" ? 3 : domain == "Spatial" ? 6 : 1
    frame_attr = frame === nothing ? "" : ", [frame = \"$frame\"]"
    equations = n == 1 ? "p.f ~ 0.0" : """
            for k in 1:$n
                p.f[k] ~ 0.0
            end
    """
    return """
    @block Sink$(domain) begin
        @ports p::Power{$domain}$frame_attr
        @equations begin
            $equations
        end
    end
    """
end

function _ground_block(domain::AbstractString, frame)
    n = domain == "Planar" ? 3 : domain == "Spatial" ? 6 : 1
    frame_attr = frame === nothing ? "" : ", [frame = \"$frame\"]"
    equation = n == 1 ? "p.f ~ 0.0" : "p.f ~ [$(join(zeros(Int, n), ", "))]"
    return """
    @block Ground$(domain) begin
        @ports p::Power{$domain}$frame_attr
        @equations $equation
        @causality p => (:flow_out, :fixed)
    end
    """
end

function _generic_sink_block(frame = nothing)
    frame_attr = frame === nothing ? "" : ", [frame = \"$frame\"]"
    return """
    @block GenericSink begin
        @ports p::Power{Generic}$frame_attr
        @equations p.f ~ 0.0
    end
    """
end

function _pass_block(domain::AbstractString, from_frame, to_frame)
    n = domain == "Planar" ? 3 : 6
    fa = from_frame === nothing ? "" : ", [frame = \"$from_frame\"]"
    fb = to_frame === nothing ? "" : ", [frame = \"$to_frame\"]"
    return """
    @block Pass$(domain) begin
        @ports begin
            a::Power{$domain}$fa
            b::Power{$domain}$fb
        end
        @equations begin
            for k in 1:$n
                a.f[k] ~ b.f[k]
                b.e[k] ~ a.e[k]
            end
        end
    end
    """
end

"""Flatten a sum expression into `(sign, term)` pairs, left to right."""
function _sum_terms(e, sign::Symbol = :+)
    if e isa BGSim.BinOp && e.op === :+
        return vcat(_sum_terms(e.lhs, sign), _sum_terms(e.rhs, sign))
    elseif e isa BGSim.UnOp && e.op === :-
        return _sum_terms(e.operand, sign === :+ ? :- : :+)
    end
    return [(sign, e)]
end

function _junction_model(domain::AbstractString, junction::Int; second_frame = "world",
    first_frame = "world")
    return _model(
        "J$(junction)$(domain)";
        nodes = Any[
            _node("n1", "World", _inline(_ground_block(domain, first_frame))),
            _node("n2", "J1", _junction(junction)),
            _node("n3", "Load", _inline(_sink_block(domain, second_frame))),
        ],
        connections = Any[
            _conn("c1", "bond", "n1", "p", "n2", nothing),
            _conn("c2", "bond", "n2", nothing, "n3", "p"),
        ],
    )
end

# ---------------------------------------------------------------------------------------
# Port size, flattening and vector junction equations
# ---------------------------------------------------------------------------------------

@testset "J-MB1 multibond ports, frames and E007" begin
    @testset "Power{Planar}/Power{Spatial} port size through instantiation" begin
        for (domain, n, strokes) in (("Planar", 3, 2), ("Spatial", 6, 3))
            result = check(_junction_model(domain, 1))
            @test isempty(result.diagnostics)
            @test result.stats == (states = 0, equations = 4 * n)
            domains = Dict(d => d for d in values(result.domains))
            @test domains == Dict(domain => domain)
            @test result.multibond == Dict("c1" => strokes, "c2" => strokes)
            @test result.frames["c1"] == "World/world"
            @test result.frames["c2"] == "Load/world"

            fm = flatten(_junction_model(domain, 1))
            @test fm.stats.unknowns == 4 * n          # two ports, effort + flow per component
            @test length(fm.variables) == 4 * n
            e = [v.id for v in fm.variables if v.kind === :port && endswith(v.id, ".e[1]")]
            f = [v.id for v in fm.variables if v.kind === :port && endswith(v.id, ".f[$n]")]
            @test e == ["World/p.e[1]", "Load/p.e[1]"]
            @test f == ["World/p.f[$n]", "Load/p.f[$n]"]
            @test !any(occursin("p.e[$(n + 1)]", v.id) for v in fm.variables)

            # The junction loops over the port size: a 1-junction with two bonds has
            # D*(n-1) equality equations plus D through-sum equations, i.e. D*n.
            junction_eqs = [eq for eq in fm.equations if eq.origin.kind === :junction]
            @test length(junction_eqs) == n * 2
        end
    end

    @testset "vector junction equations on a 0-junction" begin
        for domain in ("Planar", "Spatial")
            fm = flatten(_junction_model(domain, 0))
            n = domain == "Planar" ? 3 : 6
            junction_eqs = [eq for eq in fm.equations if eq.origin.kind === :junction]
            @test length(junction_eqs) == n * 2
            @test !_has_code(check(_junction_model(domain, 0)), "E007")
        end
    end

    @testset "junction width, Generic-on-multibond and per-component signs" begin
        function junction_sign_model(name, kind)
            return _model(
                name;
                nodes = Any[
                    _node("n1", "World", _inline(_ground_block("Planar", "world"))),
                    _node("n2", "J", _junction(kind)),
                    _node("n3", "LoadA", _inline(_sink_block("Planar", "world"))),
                    _node("n4", "LoadB", _inline(_sink_block("Planar", "world"))),
                ],
                connections = Any[
                    _conn("c1", "bond", "n1", "p", "n2", nothing),
                    _conn("c2", "bond", "n2", nothing, "n3", "p"),
                    _conn("c3", "bond", "n2", nothing, "n4", "p"),
                ],
            )
        end
        for (kind, field) in ((0, :f), (1, :e))
            fm = flatten(junction_sign_model("JSign$kind", kind))
            sums = [
                eq for eq in fm.equations if
                eq.origin.kind === :junction && eq.rhs isa BGSim.Lit && eq.rhs.value == 0.0
            ]
            @test length(sums) == 3
            expected_signs = kind == 0 ? [:-, :-, :-] : [:+, :-, :-]
            for (c, eq) in enumerate(sums)
                terms = _sum_terms(eq.lhs)
                @test [sign for (sign, _) in terms] == expected_signs
                names = String[]
                for (_, term) in terms
                    @test term isa BGSim.Name
                    push!(names, String(term.name))
                end
                @test names == [
                    "World/p.$field[$c]", "LoadA/p.$field[$c]", "LoadB/p.$field[$c]",
                ]
            end
        end

        # A Generic scalar port (one flat e/f pair) cannot join an adopted multibond
        # junction: E102 names the port, the junction and the width, not a downstream E103.
        generic = _model(
            "GenericOnPlanarJunction";
            nodes = Any[
                _node("n1", "World", _inline(_ground_block("Planar", "world"))),
                _node("n2", "J", _junction(1)),
                _node("n3", "Load", _inline(_generic_sink_block())),
            ],
            connections = Any[
                _conn("c1", "bond", "n1", "p", "n2", nothing),
                _conn("c2", "bond", "n2", nothing, "n3", "p"),
            ],
        )
        result = check(generic)
        d = _diag(result, "E102")
        @test d.path == "J"
        @test d.connection == "c2"
        @test occursin("Generic scalar port", d.message)
        @test occursin("Planar", d.message)
        @test occursin("3 components", d.message)
        @test !_has_code(result, "E103")

        # Two Planar junctions are connected per component by a virtual (e, f) pair of the
        # adopted width: each 1-junction emits D*(n-1)+D = D*n equations.
        jj = _model(
            "PlanarJunctionToJunction";
            nodes = Any[
                _node("n1", "World", _inline(_ground_block("Planar", "world"))),
                _node("n2", "J1", _junction(1)),
                _node("n3", "J2", _junction(1)),
                _node("n4", "Load", _inline(_sink_block("Planar", "world"))),
            ],
            connections = Any[
                _conn("c1", "bond", "n1", "p", "n2", nothing),
                _conn("c2", "bond", "n2", nothing, "n3", nothing),
                _conn("c3", "bond", "n3", nothing, "n4", "p"),
            ],
        )
        jresult = check(jj)
        @test isempty([d for d in jresult.diagnostics if d.severity == "error"])
        @test jresult.stats == (states = 0, equations = 18)
        @test jresult.multibond["c2"] == 2
        jfm = flatten(jj)
        junction_eqs = [eq for eq in jfm.equations if eq.origin.kind === :junction]
        @test length(junction_eqs) == 3 * 2 * 2          # D*n per junction, two junctions
        @test count(v -> v.id == "c2.e[1]", jfm.variables) == 1
        @test count(v -> v.id == "c2.f[3]", jfm.variables) == 1
        @test !any(v -> v.id == "c2.e", jfm.variables)
    end

    @testset "@ports frame attribute, interface dimension and block metadata" begin
        source = """
        @block BodyPlanar begin
            @ports p::Power{Planar}, [frame = "body"]
            @equations begin
                for k in 1:3
                    p.f[k] ~ 0.0
                end
            end
        end
        """
        pb = parse_block(source)
        @test isempty(check_block(pb))
        iface = BGSim.block_interface(pb)
        @test iface.dimension == 2
        @test iface.ports ==
              [(name = "p", domain = "Planar", size = [3], frame = "body")]
        @test BGSim.block_dimension(pb) == 2

        spatial = replace(source, "BodyPlanar" => "BodySpatial", "Planar" => "Spatial",
            "1:3" => "1:6")
        siface = BGSim.block_interface(parse_block(spatial))
        @test siface.dimension == 3
        @test siface.ports[1].size == [6]
        @test siface.ports[1].frame == "body"

        scalar = parse_block("@block ScalarBlock begin\n @ports p::Power{Generic}\n end")
        @test !haskey(BGSim.block_interface(scalar), :dimension)
        @test BGSim.block_dimension(scalar) === nothing
        @test BGSim.block_interface(scalar).ports[1].frame === nothing

        # `frame` is a ports-only string attribute (metadata, so D11 does not apply).
        bad_value = parse_block("""
        @block BadFrame begin
            @ports p::Power{Planar}, [frame = 3]
            @equations p.f ~ [0.0, 0.0, 0.0]
        end
        """)
        @test any(d -> d.code == "E001" && occursin("frame", d.message),
            check_block(bad_value))
        wrong_scope = parse_block("""
        @block FrameOnParam begin
            @ports p::Power{Planar}
            @parameters m::Real = 1.0, [frame = "body"]
            @equations p.f ~ [0.0, 0.0, 0.0]
        end
        """)
        @test any(d -> d.code == "E001" && occursin("frame", d.message),
            check_block(wrong_scope))

        # A block with both multibond domains has no single model dimension: E102, not a
        # silent choice.
        mixed = parse_block("""
        @block MixedDimensions begin
            @ports begin
                a::Power{Planar}
                b::Power{Spatial}
            end
        end
        """)
        @test BGSim.block_dimension(mixed) === nothing
        @test any(d -> d.code == "E102" && occursin("mixes Planar and Spatial",
            d.message), check_block(mixed))
    end

    @testset "the catalog reports the seven domains and the new optional fields" begin
        cat = BGSim.Library.catalog()
        @test [d.name for d in cat.domains] ==
              ["Electrical", "Translation", "Rotation", "Hydraulic", "Generic", "Planar", "Spatial"]
        @test [d.size for d in cat.domains] == [1, 1, 1, 1, 1, 3, 6]
        @test cat.domains[6].components ==
              (effort = ["N*m", "N", "N"], flow = ["rad/s", "m/s", "m/s"])
        @test cat.domains[7].components ==
              (effort = ["N*m", "N*m", "N*m", "N", "N", "N"],
                  flow = ["rad/s", "rad/s", "rad/s", "m/s", "m/s", "m/s"])
        # Every port entry carries the new nullable `frame` property (null for the scalar
        # stdlib blocks); `dimension` is non-nullable, so scalar blocks omit it.
        for block in cat.blocks
            @test !haskey(block, :dimension)
            for port in block.ports
                @test haskey(port, :frame)
                @test port.frame === nothing
            end
        end

        # The catalog owns its unit arrays: mutating a returned catalog (or the helper's
        # result) must not corrupt the next call.
        cat.domains[6].components.effort[1] = "corrupted"
        BGSim.Library.domain_components(:Planar).flow[1] = "corrupted"
        fresh = BGSim.Library.catalog()
        @test fresh.domains[6].components.effort[1] == "N*m"
        @test fresh.domains[6].components.flow[1] == "rad/s"
        @test cat.domains[6].components.effort[1] == "corrupted"   # the returned copy
    end

    # -----------------------------------------------------------------------------------
    # Frame union-find (D-MB5)
    # -----------------------------------------------------------------------------------

    @testset "a direct bond between different named frames is E007" begin
        result = check(IR.parse_model(
            joinpath(_MODEL_SEMANTIC, "model.e007-frame-mismatch.json")))
        @test _has_code(result, "E007")
        d = _diag(result, "E007")
        @test d.path == "Body"
        @test d.connection == "c1"
        @test length(d.related) == 1
        @test d.related[1].path == "World"
        @test occursin("frame `body`", d.message)
        @test occursin("frame `world`", d.message)
        @test occursin("FixedTransform", d.hint)
        @test occursin("null frame unifies", d.hint)
        # The frame is recorded even for the connection that fails the check.
        @test result.frames["c1"] == "Body/body"
        @test result.multibond["c1"] == 2
    end

    @testset "a junction with three ports reports E007 on the closing connection" begin
        model = _model(
            "JunctionFrameMismatch";
            nodes = Any[
                _node("n1", "A", _inline(_sink_block("Planar", "world"))),
                _node("n2", "J", _junction(1)),
                _node("n3", "B", _inline(_sink_block("Planar", "world"))),
                _node("n4", "C", _inline(_sink_block("Planar", "body"))),
            ],
            connections = Any[
                _conn("c1", "bond", "n1", "p", "n2", nothing),
                _conn("c2", "bond", "n2", nothing, "n3", "p"),
                _conn("c3", "bond", "n2", nothing, "n4", "p"),
            ],
        )
        result = check(model)
        d = _diag(result, "E007")
        @test d.path == "C"
        @test d.connection == "c3"
        @test d.related[1].path == "A"
        @test occursin("frame `body`", d.message)
        @test occursin("frame `world`", d.message)
        @test result.frames == Dict("c1" => "A/world", "c2" => "B/world", "c3" => "C/body")
    end

    @testset "a wire group is transitive: two legal ports plus an illegal third" begin
        model = _model(
            "WireFrameMismatch";
            nodes = Any[
                _node("n1", "A", _inline(_sink_block("Planar", "world"))),
                _node("n2", "B", _inline(_sink_block("Planar", "world"))),
                _node("n3", "C", _inline(_sink_block("Planar", "body"))),
            ],
            connections = Any[
                _conn("c1", "wire", "n1", "p", "n2", "p"),
                _conn("c2", "wire", "n2", "p", "n3", "p"),
            ],
        )
        result = check(model)
        d = _diag(result, "E007")
        @test d.path == "C"
        @test d.connection == "c2"
        @test d.related[1].path == "A"
    end

    @testset "a null frame is neutral and adopts its neighbour's frame" begin
        model = _model(
            "NullFrame";
            nodes = Any[
                _node("n1", "World", _inline(_ground_block("Planar", "world"))),
                _node("n2", "J1", _junction(1)),
                _node("n3", "Load", _inline(_sink_block("Planar", nothing))),
            ],
            connections = Any[
                _conn("c1", "bond", "n1", "p", "n2", nothing),
                _conn("c2", "bond", "n2", nothing, "n3", "p"),
            ],
        )
        result = check(model)
        @test !_has_code(result, "E007")
        @test result.frames["c1"] == "World/world"
        @test result.frames["c2"] == "World/world"   # adopted from the junction group
        # A frame-neutral port never causes E007, including on a direct bond.
        direct = _model(
            "NullDirect";
            nodes = Any[
                _node("n1", "World", _inline(_sink_block("Planar", "world"))),
                _node("n2", "Load", _inline(_sink_block("Planar", nothing))),
            ],
            connections = Any[_conn("c1", "bond", "n1", "p", "n2", "p")],
        )
        @test !_has_code(check(direct), "E007")
        @test check(direct).frames["c1"] == "World/world"

        # A null-null chain inside one wire group still ends at two different named frames:
        # the nulls adopt `world`, so the final `body` port closes the conflict.
        chain = _model(
            "NullNullChain";
            nodes = Any[
                _node("n1", "World", _inline(_sink_block("Planar", "world"))),
                _node("n2", "N1", _inline(_sink_block("Planar", nothing))),
                _node("n3", "N2", _inline(_sink_block("Planar", nothing))),
                _node("n4", "Body", _inline(_sink_block("Planar", "body"))),
            ],
            connections = Any[
                _conn("c1", "wire", "n1", "p", "n2", "p"),
                _conn("c2", "wire", "n2", "p", "n3", "p"),
                _conn("c3", "wire", "n3", "p", "n4", "p"),
            ],
        )
        chain_result = check(chain)
        cd = _diag(chain_result, "E007")
        @test cd.path == "Body"
        @test cd.connection == "c3"
        @test occursin("frame `body`", cd.message)
        @test occursin("frame `world`", cd.message)
    end

    # -----------------------------------------------------------------------------------
    # Subsystem ports keep their frame (D-MB4/D-MB5)
    # -----------------------------------------------------------------------------------

    @testset "a transform block is the legal bridge between two named frames" begin
        bridge = """
        @block Bridge begin
            @ports begin
                a::Power{Planar}, [frame = "world"]
                b::Power{Planar}, [frame = "arm"]
            end
            @equations begin
                for k in 1:3
                    a.f[k] ~ b.f[k]
                    b.e[k] ~ a.e[k]
                end
            end
        end
        """
        model = _model(
            "DirectTransformBridge";
            nodes = Any[
                _node("n1", "World", _inline(_ground_block("Planar", "world"))),
                _node("n2", "Mount", _inline(bridge)),
                _node("n3", "Load", _inline(_sink_block("Planar", "arm"))),
            ],
            connections = Any[
                _conn("c1", "bond", "n1", "p", "n2", "a"),
                _conn("c2", "bond", "n2", "b", "n3", "p"),
            ],
        )
        result = check(model)
        @test !_has_code(result, "E007")
        @test isempty([d for d in result.diagnostics if d.severity == "error"])
        @test result.frames == Dict("c1" => "Mount/world", "c2" => "Load/arm")
    end

    @testset "a subsystem face is authoritative and a transform bridges the internal frame" begin
        transform = """
        @block FixedTransformPlanar begin
            @ports begin
                a::Power{Planar}, [frame = "body"]
                b::Power{Planar}, [frame = "arm"]
            end
            @equations begin
                for k in 1:3
                    a.f[k] ~ b.f[k]
                    b.e[k] ~ a.e[k]
                end
            end
        end
        """
        face = Dict{String,Any}(
            "name" => "p", "kind" => "power", "domain" => "Planar",
            "size" => Any[3], "frame" => "arm", "node" => "s2", "port" => "a",
        )
        sub = Dict{String,Any}(
            "ports" => Any[face],
            "diagram" => _diagram(
                Any[
                    _node("s2", "Transform", _inline(transform)),
                    _node("s3", "Sink", _inline(_sink_block("Planar", "arm"))),
                ],
                Any[_conn("cB", "bond", "s2", "b", "s3", "p")],
            ),
        )
        model = _model(
            "SubsystemBridge";
            nodes = Any[
                _node("n1", "World", _inline(_ground_block("Planar", "arm"))),
                _node("n2", "Arm", Dict{String,Any}("subsystem" => sub)),
            ],
            connections = Any[_conn("c1", "bond", "n1", "p", "n2", "p")],
        )
        result = check(model)
        @test !_has_code(result, "E007")
        @test isempty([d for d in result.diagnostics if d.severity == "error"])
        # The exposed face's frame is used outside (`Arm/arm`), not the internal body frame.
        @test result.frames["c1"] == "Arm/arm"
        @test result.frames["cB"] == "Arm/Sink/arm"
        @test result.multibond == Dict("c1" => 2, "cB" => 2)

        # The subsystem port's declared frame differs from the exposed port's catalog frame
        # (`body`); the internal transform is the only reason that is legal.
        md = IR.parse_model(model)
        @test md.diagram.nodes[2].subsystem_ports[1].frame == "arm"
    end

    @testset "an unconnected transform does not justify a subsystem face" begin
        # The verifier's counterexample: the face exposes a body port and the subsystem
        # contains a transform that declares body/arm, but it is not wired to the exposed
        # port (nor is the second one). Set membership is not connectivity.
        face = Dict{String,Any}(
            "name" => "p", "kind" => "power", "domain" => "Planar",
            "size" => Any[3], "frame" => "arm", "node" => "s1", "port" => "p",
        )
        sub = Dict{String,Any}(
            "ports" => Any[face],
            "diagram" => _diagram(
                Any[
                    _node("s1", "Face", _inline(_sink_block("Planar", "body"))),
                    _node("s2", "T1", _inline(_pass_block("Planar", "body", "arm"))),
                    _node("s3", "T2", _inline(_pass_block("Planar", "body", "arm"))),
                ],
                Any[],
            ),
        )
        model = _model(
            "UnconnectedTransform";
            nodes = Any[
                _node("n1", "World", _inline(_ground_block("Planar", "arm"))),
                _node("n2", "Arm", Dict{String,Any}("subsystem" => sub)),
            ],
            connections = Any[_conn("c1", "bond", "n1", "p", "n2", "p")],
        )
        result = check(model)
        d = _diag(result, "E007")
        @test d.path == "Arm"
        @test occursin("subsystem port `p`", d.message)
        @test occursin("frame `arm`", d.message)
        @test occursin("frame `body`", d.message)
    end

    @testset "a connected internal transform is accepted" begin
        # The face exposes the transform itself; its other side is genuinely wired onward to
        # a sink. The transform's two declared frames are what make the face frame legal.
        face = Dict{String,Any}(
            "name" => "p", "kind" => "power", "domain" => "Planar",
            "size" => Any[3], "frame" => "arm", "node" => "s2", "port" => "a",
        )
        sub = Dict{String,Any}(
            "ports" => Any[face],
            "diagram" => _diagram(
                Any[
                    _node("s2", "Transform", _inline(_pass_block("Planar", "body", "arm"))),
                    _node("s3", "Sink", _inline(_sink_block("Planar", "arm"))),
                ],
                Any[_conn("cC", "bond", "s2", "b", "s3", "p")],
            ),
        )
        model = _model(
            "ConnectedTransform";
            nodes = Any[
                _node("n1", "World", _inline(_ground_block("Planar", "arm"))),
                _node("n2", "Arm", Dict{String,Any}("subsystem" => sub)),
            ],
            connections = Any[_conn("c1", "bond", "n1", "p", "n2", "p")],
        )
        result = check(model)
        @test !_has_code(result, "E007")
        @test isempty([d for d in result.diagnostics if d.severity == "error"])
    end

    @testset "an illegal direct internal bond is E007" begin
        # No transform: the subsystem's internal body port is bonded straight to an arm
        # port. The face itself is consistent, so the error is the internal bond.
        face = Dict{String,Any}(
            "name" => "p", "kind" => "power", "domain" => "Planar",
            "size" => Any[3], "frame" => "arm", "node" => "s4", "port" => "p",
        )
        sub = Dict{String,Any}(
            "ports" => Any[face],
            "diagram" => _diagram(
                Any[
                    _node("s1", "Body", _inline(_sink_block("Planar", "body"))),
                    _node("s2", "ArmLoad", _inline(_sink_block("Planar", "arm"))),
                    _node("s4", "Face", _inline(_sink_block("Planar", "arm"))),
                ],
                Any[_conn("cX", "bond", "s1", "p", "s2", "p")],
            ),
        )
        model = _model(
            "SubsystemDirectBond";
            nodes = Any[
                _node("n1", "World", _inline(_ground_block("Planar", "arm"))),
                _node("n2", "Arm", Dict{String,Any}("subsystem" => sub)),
            ],
            connections = Any[_conn("c1", "bond", "n1", "p", "n2", "p")],
        )
        result = check(model)
        d = _diag(result, "E007")
        @test d.path == "Arm/ArmLoad"
        @test d.connection == "cX"
        @test d.related[1].path == "Arm/Body"
        @test occursin("frame `arm`", d.message)
        @test occursin("frame `body`", d.message)

        # A face that differs from its internal port with no internal transform is E007 too.
        face2 = Dict{String,Any}(
            "name" => "p", "kind" => "power", "domain" => "Planar",
            "size" => Any[3], "frame" => "arm", "node" => "s1", "port" => "p",
        )
        sub2 = Dict{String,Any}(
            "ports" => Any[face2],
            "diagram" => _diagram(
                Any[_node("s1", "Body", _inline(_sink_block("Planar", "body")))],
                Any[],
            ),
        )
        model2 = _model(
            "SubsystemUnbridgedFace";
            nodes = Any[
                _node("n1", "World", _inline(_ground_block("Planar", "arm"))),
                _node("n2", "Arm", Dict{String,Any}("subsystem" => sub2)),
            ],
            connections = Any[_conn("c1", "bond", "n1", "p", "n2", "p")],
        )
        result2 = check(model2)
        d2 = _diag(result2, "E007")
        @test d2.path == "Arm"
        @test occursin("subsystem port `p`", d2.message)
        @test occursin("FixedTransform", d2.hint)
    end

    @testset "a null subsystem face is frame-neutral" begin
        # The face has no frame and the internal port says `body`; the face must adopt the
        # outside `world`, not inherit the internal catalog frame.
        face = Dict{String,Any}(
            "name" => "p", "kind" => "power", "domain" => "Planar",
            "size" => Any[3], "node" => "s1", "port" => "p",
        )
        sub = Dict{String,Any}(
            "ports" => Any[face],
            "diagram" => _diagram(
                Any[_node("s1", "Body", _inline(_sink_block("Planar", "body")))],
                Any[],
            ),
        )
        model = _model(
            "NullFace";
            nodes = Any[
                _node("n1", "World", _inline(_ground_block("Planar", "world"))),
                _node("n2", "Arm", Dict{String,Any}("subsystem" => sub)),
            ],
            connections = Any[_conn("c1", "bond", "n1", "p", "n2", "p")],
        )
        result = check(model)
        @test !_has_code(result, "E007")
        @test result.frames["c1"] == "World/world"
    end

    @testset "a concrete override of a Generic internal port is a clear E102" begin
        # The Generic internal port was flattened as one scalar e/f pair, so a 3-component
        # override is not representable in v1: say that instead of a raw size mismatch.
        face = Dict{String,Any}(
            "name" => "p", "kind" => "power", "domain" => "Planar",
            "size" => Any[3], "frame" => "world", "node" => "s1", "port" => "p",
        )
        sub = Dict{String,Any}(
            "ports" => Any[face],
            "diagram" => _diagram(
                Any[_node("s1", "Load", _inline(_generic_sink_block()))],
                Any[],
            ),
        )
        model = _model(
            "GenericOverride";
            nodes = Any[
                _node("n1", "World", _inline(_ground_block("Planar", "world"))),
                _node("n2", "Arm", Dict{String,Any}("subsystem" => sub)),
            ],
            connections = Any[_conn("c1", "bond", "n1", "p", "n2", "p")],
        )
        result = check(model)
        d = _diag(result, "E102")
        @test occursin("overrides a Generic internal port", d.message)
        @test occursin("must stay scalar", d.message)
        @test occursin("Power{Planar}", d.hint)
        @test !occursin("declares size", d.message)

        # The scalar override still works: a Rotation face over a Generic internal port.
        sface = Dict{String,Any}(
            "name" => "p", "kind" => "power", "domain" => "Rotation",
            "size" => Any[1], "frame" => "world", "node" => "s1", "port" => "p",
        )
        ssub = Dict{String,Any}(
            "ports" => Any[sface],
            "diagram" => _diagram(
                Any[_node("s1", "Load", _inline(_generic_sink_block()))],
                Any[],
            ),
        )
        smodel = _model(
            "GenericScalarOverride";
            nodes = Any[
                _node("n1", "World", _inline(_ground_block("Rotation", "world"))),
                _node("n2", "Arm", Dict{String,Any}("subsystem" => ssub)),
            ],
            connections = Any[_conn("c1", "bond", "n1", "p", "n2", "p")],
        )
        sresult = check(smodel)
        @test !_has_code(sresult, "E102")
        @test !_has_code(sresult, "E007")
        @test sresult.frames["c1"] == "Arm/world"
    end

    @testset "a textual composite carries its interface frame" begin
        mktempdir() do dir
            library = joinpath(dir, "library")
            mkpath(library)
            write(
                joinpath(library, "CompSinkPlanar.jl"),
                """
                @block CompSinkPlanar begin
                    @ports p::Power{Planar}
                    @equations begin
                        for k in 1:3
                            p.f[k] ~ 0.0
                        end
                    end
                end
                """,
            )
            write(
                joinpath(library, "CompSinkBody.jl"),
                """
                @block CompSinkBody begin
                    @ports p::Power{Planar}, [frame = "body"]
                    @equations begin
                        for k in 1:3
                            p.f[k] ~ 0.0
                        end
                    end
                end
                """,
            )
            composite(component) = """
            @block ArmComposite begin
                @ports p::Power{Planar}, [frame = "arm"]
                @components begin
                    sink = $component()
                end
                @connections begin
                    connect(p, sink.p)
                end
            end
            """
            build(component) = _model(
                "TextualFrame";
                nodes = Any[
                    _node("n1", "World", _inline(_ground_block("Planar", "arm"))),
                    _node("n2", "Arm", _inline(composite(component))),
                ],
                connections = Any[_conn("c1", "bond", "n1", "p", "n2", "p")],
            )
            # A null internal port lets the composite face's `arm` be authoritative.
            result = check(build("CompSinkPlanar"); project_dir = dir)
            @test !_has_code(result, "E007")
            @test result.frames["c1"] == "Arm/arm"

            # If the internal port declares `body`, the composite face is still `arm`; with no
            # internal transform that is E007 (not silently ignored).
            bad = check(build("CompSinkBody"); project_dir = dir)
            d = _diag(bad, "E007")
            @test d.path == "Arm"
            @test occursin("frame `arm`", d.message)
            @test occursin("frame `body`", d.message)
        end
    end

    @testset "two instances with the same frame name are the same frame (v1)" begin
        # D-MB5 v1 limitation: frames are compared by unqualified name, so two different
        # bodies that both name their local frame `body` are accepted. Distinct names per
        # body are the discipline until typed frame objects land.
        model = _model(
            "SameFrameName";
            nodes = Any[
                _node("n1", "Body1", _inline(_sink_block("Planar", "body"))),
                _node("n2", "Body2", _inline(_sink_block("Planar", "body"))),
            ],
            connections = Any[_conn("c1", "bond", "n1", "p", "n2", "p")],
        )
        result = check(model)
        @test !_has_code(result, "E007")
        @test result.frames["c1"] == "Body2/body"
    end

    # -----------------------------------------------------------------------------------
    # model.check shape and the C-MB1 fixtures
    # -----------------------------------------------------------------------------------

    @testset "model.check carries frames and multibond" begin
        result = check(_junction_model("Planar", 1))
        @test Set(keys(result)) == Set((
            :diagnostics, :domains, :causality, :frames, :multibond, :unitFactors,
            :signals, :stats,
        ))
        @test result.frames isa Dict{String,String}
        @test result.multibond isa Dict{String,Int}
        # A scalar model still reports the required empty frame object.
        dc = check(IR.parse_model(joinpath(_MODEL_VALID, "model.dcmotor.json")))
        @test result.frames["c1"] == "World/world"
        @test dc.frames == Dict{String,String}()
        @test dc.multibond == Dict{String,Int}()
        # The worker's result has the same contract fields.
        worker = BGSim.Worker._model_check_result(IR.parse_model(_junction_model("Planar", 1)))
        @test haskey(worker, :frames)
        @test haskey(worker, :multibond)
        @test worker.frames == result.frames
    end

    @testset "the response.model-check.multibond fixture lines up with our signals" begin
        expected = JSON3.read(read(
            joinpath(_RPC_VALID, "response.model-check.multibond.json"), String)).result
        # The fixture's frame and stroke contract.
        @test Set(String.(keys(expected.frames))) == Set(["c1", "c2"])
        @test all(occursin("/", String(v)) for v in values(expected.frames))
        @test Dict(String(k) => Int(v) for (k, v) in pairs(expected.multibond)) ==
              Dict("c1" => 2, "c2" => 3)
        # Every component signal is `<path>/<port>.e[k]` or `.f[k]` with kind "port", plus the
        # scalar power `<path>/<port>.P` with kind "power" (units are J-MB2).
        for signal in expected.signals
            id = String(signal.id)
            if endswith(id, ".P")
                @test String(signal.kind) == "power"
            else
                @test String(signal.kind) == "port"
                @test occursin(r"\.(e|f)\[\d+\]$", id)
            end
        end
        # Our planar model emits exactly that shape for each port.
        result = check(_junction_model("Planar", 1))
        for port in ("World/p", "Load/p")
            for field in ("e", "f"), k in 1:3
                signal = only(filter(s -> s.id == "$port.$field[$k]", result.signals))
                @test signal.kind == "port"
            end
            @test only(filter(s -> s.id == "$port.P", result.signals)).kind == "power"
        end
    end

    @testset "the valid C-MB1 fixtures: frames and multibond" begin
        # `model.frame-bridge.json`: the subsystem port frames and the per-component unit
        # arrays are parsed and forwarded; the model has no frame error.
        mdf = IR.parse_model(joinpath(_MODEL_VALID, "model.frame-bridge.json"))
        mount = mdf.diagram.nodes[3]
        arm = mdf.diagram.nodes[4]
        @test [sp.frame for sp in mount.subsystem_ports] == ["world", "arm"]
        @test [sp.frame for sp in arm.subsystem_ports] == ["arm"]
        @test mount.subsystem_ports[1].effort_units == ["N*m", "N", "N"]
        @test mount.subsystem_ports[1].flow_units == ["rad/s", "m/s", "m/s"]
        @test !_has_code(check(mdf), "E007")

        # `model.planar.multibond.json` / `model.spatial.multibond.json`: the ground-to-
        # junction bond is a multibond in the declared domain, in frame `world`.
        for (file, domain, strokes, n) in (
            ("model.planar.multibond.json", "Planar", 2, 3),
            ("model.spatial.multibond.json", "Spatial", 3, 6),
        )
            md = IR.parse_model(joinpath(_MODEL_VALID, file))
            result = check(md)
            @test !_has_code(result, "E007")
            @test result.domains["c1"] == domain
            @test result.multibond["c1"] == strokes
            @test result.frames["c1"] == "World/world"
            # The inline ground port is the declared multibond domain with the right size.
            ground = parse_block(md.diagram.nodes[1].inline_source)
            iface = BGSim.block_interface(ground)
            @test iface.dimension == (domain == "Planar" ? 2 : 3)
            @test iface.ports[1].domain == domain
            @test iface.ports[1].size == [n]
            @test iface.ports[1].frame == "world"
        end
    end
end
