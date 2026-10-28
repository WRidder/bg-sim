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

check(md::IR.ModelDoc) = BGSim.Compile.model_check(md)
check(model) = BGSim.Compile.model_check(IR.parse_model(model))
flatten(md::IR.ModelDoc) = BGSim.Compile.flatten(md)
flatten(model) = BGSim.Compile.flatten(IR.parse_model(model))

_has_code(result, code) = any(d -> d.code == code, result.diagnostics)
_diag(result, code) = first(d for d in result.diagnostics if d.code == code)
_codes(result) = [d.code for d in result.diagnostics]

# Inline blocks used by the frame tests. `_source_block` is the system-under-test's generic
# "hold the flow at zero" port; the causality declaration is optional so a junction model can
# avoid a causal conflict that is not the subject of the test.
function _sink_block(domain::AbstractString, frame)
    n = domain == "Planar" ? 3 : 6
    frame_attr = frame === nothing ? "" : ", [frame = \"$frame\"]"
    return """
    @block Sink$(domain) begin
        @ports p::Power{$domain}$frame_attr
        @equations begin
            for k in 1:$n
                p.f[k] ~ 0.0
            end
        end
    end
    """
end

function _ground_block(domain::AbstractString, frame)
    n = domain == "Planar" ? 3 : 6
    frame_attr = frame === nothing ? "" : ", [frame = \"$frame\"]"
    return """
    @block Ground$(domain) begin
        @ports p::Power{$domain}$frame_attr
        @equations p.f ~ [$(join(zeros(Int, n), ", "))]
        @causality p => (:flow_out, :fixed)
    end
    """
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
