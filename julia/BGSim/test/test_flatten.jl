# Work package J1.4: flattening, connections, junctions and domains.
#
# The acceptance tests of the work package:
#   * the four contract fixtures flatten to exact equation/unknown counts;
#   * the `domains` map of every fixture is asserted (including the Generic islands of the
#     two bond-graph models, which plan 5.6 accepts with W205);
#   * ten negative models in `test/fixtures/negative/` report the expected code on the
#     expected node and connection id;
#   * the rest pins the semantics the plan spells out: D7/D8 wire signs, plan 5.4 junction
#     equations, plan 5.5 bond signs, D9 unit adoption, D15 signals, subsystems, arrays and
#     the model.check result shape.

using Test
using BGSim
import BGSim.IR
import BGSim.Flat
import BGSim.Compile
import BGSim.Units
import JSON3

# ---------------------------------------------------------------------------------------
# Paths and small helpers
# ---------------------------------------------------------------------------------------

const _REPO = normpath(joinpath(@__DIR__, "..", "..", ".."))
const _MODEL_FIXTURES = joinpath(_REPO, "contracts", "fixtures", "model", "valid")
const _NEGATIVES = joinpath(@__DIR__, "fixtures", "negative")

_fixture(name) = joinpath(_MODEL_FIXTURES, name)
_negative(name) = joinpath(_NEGATIVES, name)

_errors(fm) = [d for d in fm.diagnostics if d.severity == "error"]
_warnings(fm) = [d for d in fm.diagnostics if d.severity == "warning"]

function _has_code(fm, code; node = nothing, connection = nothing, severity = nothing)
    for d in fm.diagnostics
        d.code == code || continue
        node === nothing || d.node == node || continue
        connection === nothing || d.connection == connection || continue
        severity === nothing || d.severity == severity || continue
        return true
    end
    return false
end

function _diag(fm, code; node = nothing, connection = nothing, severity = nothing)
    for d in fm.diagnostics
        d.code == code || continue
        node === nothing || d.node == node || continue
        connection === nothing || d.connection == connection || continue
        severity === nothing || d.severity == severity || continue
        return d
    end
    return nothing
end

_signal(fm, id) = findfirst(s -> s.id == id, fm.signals)
_has_signal(fm, id) = _signal(fm, id) !== nothing

# ---------------------------------------------------------------------------------------
# Model document builders (a plain Dict is accepted by IR.parse_model)
# ---------------------------------------------------------------------------------------

function _settings()
    return Dict{String,Any}(
        "t_start" => 0.0,
        "t_end" => 1.0,
        "solver" => "auto",
        "reltol" => 1.0e-6,
        "abstol" => 1.0e-8,
        "max_step" => nothing,
        "output" => Dict{String,Any}("mode" => "points", "points" => 100),
        "event_limit" => 10000,
    )
end

function _node(
    id,
    name,
    block;
    params = Dict{String,Any}(),
    constants = Dict{String,Any}(),
    starts = Dict{String,Any}(),
)
    return Dict{String,Any}(
        "id" => id,
        "name" => name,
        "block" => block,
        "position" => Dict{String,Any}("x" => 0.0, "y" => 0.0),
        "params" => params,
        "constants" => constants,
        "starts" => starts,
    )
end

_ref(ref) = Dict{String,Any}("ref" => ref)
_junction(kind) = Dict{String,Any}("junction" => string(kind))
_inline(source) = Dict{String,Any}("inline" => Dict{String,Any}("source" => source))

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

function _model(name, nodes, connections; language = "0.1.0")
    return Dict{String,Any}(
        "format" => "bgsim.model",
        "language" => language,
        "name" => name,
        "diagram" => Dict{String,Any}(
            "nodes" => nodes,
            "connections" => connections,
            "subsystemPorts" => Any[],
            "annotations" => Any[],
        ),
        "settings" => _settings(),
        "plots" => Any[],
        "scene" => nothing,
        "bindings" => Any[],
    )
end

flat(model) = Compile.flatten(IR.parse_model(model))
flat_file(path) = Compile.flatten(IR.parse_model(path))
check(model) = Compile.model_check(IR.parse_model(model))

function _counts(fm)
    return (length(fm.variables), length(fm.equations))
end

# The iconic DC motor and RLC models reused by several builders below.
function _step_node(id, name; t_step = "0.01", initial = "0.0", final = "12.0")
    return _node(
        id, name, _ref("stdlib:sources/Step");
        params = Dict("t_step" => t_step, "initial" => initial, "final" => final),
    )
end

# ---------------------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------------------

@testset "J1.4 flatten, connect, junctions and domains" begin
    @testset "IR: the model document" begin
        md = IR.parse_model(_fixture("model.dcmotor.json"))
        @test md.format == "bgsim.model"
        @test md.language == "0.1.0"
        @test md.name == "DCMotorSpeed"
        @test length(md.diagram.nodes) == 7
        @test length(md.diagram.connections) == 7
        @test md.diagram.nodes[3].id == "n3"
        @test md.diagram.nodes[3].name == "Motor1"
        @test md.diagram.nodes[3].block_kind === :ref
        @test md.diagram.nodes[3].ref == "stdlib:converters/DCMotor"
        @test md.diagram.nodes[3].params["R"] == "2.0"
        @test md.diagram.connections[1].kind === :signal
        @test md.diagram.connections[1].from.node == "n1"
        @test md.diagram.connections[1].from.port === :y
        @test md.settings["t_end"] == 1.0

        bond = IR.parse_model(_fixture("model.dcmotor.bondgraph.json"))
        @test bond.diagram.nodes[2].block_kind === :junction
        @test bond.diagram.nodes[2].junction == 1
        @test bond.diagram.connections[1].to.port === nothing

        # A JSON string, a JSON3 object and a plain Dict all parse to the same document.
        text = read(_fixture("model.rlc.iconic.json"), String)
        from_text = IR.parse_model(text)
        from_json = IR.parse_model(JSON3.read(text))
        @test from_text.name == from_json.name == "RLCSeriesIconic"
        dict = Dict{String,Any}(
            "format" => "bgsim.model",
            "name" => "Tiny",
            "language" => "0.1.0",
            "diagram" => Dict{String,Any}("nodes" => Any[], "connections" => Any[]),
            "settings" => Dict{String,Any}(),
        )
        tiny = IR.parse_model(dict)
        @test tiny.name == "Tiny"
        @test isempty(tiny.diagram.nodes)

        @test_throws ArgumentError IR.parse_model(
            Dict{String,Any}("format" => "something.else", "name" => "X",
                "diagram" => Dict{String,Any}("nodes" => Any[], "connections" => Any[])),
        )
        @test_throws ArgumentError IR.parse_model(
            Dict{String,Any}(
                "format" => "bgsim.model",
                "name" => "Duplicate",
                "diagram" => Dict{String,Any}(
                    "nodes" => Any[
                        _node("n1", "A", _ref("stdlib:sources/Step")),
                        _node("n1", "B", _ref("stdlib:sources/Step")),
                    ],
                    "connections" => Any[],
                ),
            ),
        )

        # Inline blocks keep their source; subsystems keep their ports and diagram.
        inline_doc = IR.parse_model(_model(
            "Inline",
            Any[_node("n1", "B1", _inline("@block B begin\n @outputs y::Real\n @equations y ~ 0.0\nend\n"))],
            Any[],
        ))
        @test inline_doc.diagram.nodes[1].block_kind === :inline
        @test occursin("@block B", inline_doc.diagram.nodes[1].inline_source)

        sub_doc = IR.parse_model(_model(
            "Sub",
            Any[_node(
                "n1", "S1",
                Dict{String,Any}("subsystem" => Dict{String,Any}(
                    "ports" => Any[Dict{String,Any}(
                        "name" => "p", "kind" => "power", "domain" => "Electrical",
                        "size" => Any[], "node" => "n1", "port" => "p",
                    )],
                    "diagram" => Dict{String,Any}(
                        "nodes" => Any[_node(
                            "n1", "R1", _ref("stdlib:electrical/Resistor"),
                        )],
                        "connections" => Any[],
                    ),
                )),
            )],
            Any[],
        ))
        sub_node = sub_doc.diagram.nodes[1]
        @test sub_node.block_kind === :subsystem
        @test length(sub_node.subsystem_ports) == 1
        @test sub_node.subsystem_ports[1].name === :p
        @test sub_node.subsystem_ports[1].domain === :Electrical
        @test sub_node.subsystem.nodes[1].name == "R1"
    end

    @testset "fixtures: exact counts" begin
        expected = Dict(
            "model.dcmotor.json" => (41, 41, 3, 11, 12, 11),
            "model.dcmotor.bondgraph.json" => (16, 16, 2, 8, 7, 6),
            "model.rlc.iconic.json" => (22, 22, 2, 6, 6, 6),
            "model.rlc.bondgraph.json" => (10, 10, 2, 5, 4, 4),
        )
        for (file, (vars, eqs, states, nodes, conns, instances)) in expected
            fm = flat_file(_fixture(file))
            @test _counts(fm) == (vars, eqs)
            @test fm.stats.unknowns == vars
            @test fm.stats.equations == eqs
            @test fm.stats.states == states
            @test fm.stats.nodes == nodes
            @test fm.stats.connections == conns
            @test length(fm.instances) == instances
            @test isempty(_errors(fm))
            @test fm.stats.parameters == length(fm.parameters)
            @test fm.stats.signals == length(fm.signals)
        end
    end

    @testset "fixtures: domains, unit factors and the bond graph" begin
        dcmotor = flat_file(_fixture("model.dcmotor.json"))
        # The six external connections keep their domains; the composite's internal wiring
        # adds five more power connections (`Motor1/DCMotor/c2...`), all of one domain each.
        @test all(
            dcmotor.domains[string("c", i)] == d for (i, d) in
            ((2, "Electrical"), (3, "Electrical"), (7, "Electrical"),
                (4, "Rotation"), (5, "Rotation"), (6, "Rotation"))
        )
        @test length(dcmotor.domains) == 11
        @test all(d -> d == "Electrical" || d == "Rotation", values(dcmotor.domains))
        @test length(dcmotor.unit_factors) == 11
        @test all(f -> f == 1.0, values(dcmotor.unit_factors))
        @test isempty(_warnings(dcmotor))

        rlc = flat_file(_fixture("model.rlc.iconic.json"))
        @test rlc.domains == Dict(
            "c2" => "Electrical", "c3" => "Electrical", "c4" => "Electrical",
            "c5" => "Electrical", "c6" => "Electrical",
        )
        @test isempty(_warnings(rlc))

        # Every port of the two bond-graph fixtures is Generic and no port touches a
        # concrete domain, so plan 5.6 makes the islands dimensionless `Generic` and warns
        # W205. (The contract comments call these "electrical" models, but the *ports* are
        # Power{Generic}: nothing in the document can be adopted. See the WP report.)
        dcmotor_bg = flat_file(_fixture("model.dcmotor.bondgraph.json"))
        @test dcmotor_bg.domains == Dict(string("c", i) => "Generic" for i in 1:7)
        @test length([d for d in dcmotor_bg.diagnostics if d.code == "W205"]) == 2
        @test length(dcmotor_bg.junctions) == 2
        @test [j.kind for j in dcmotor_bg.junctions] == [1, 1]
        @test [length(j.bonds) for j in dcmotor_bg.junctions] == [4, 3]
        @test [b.connection for b in dcmotor_bg.junctions[1].bonds] == ["c1", "c2", "c3", "c4"]
        @test [b.into for b in dcmotor_bg.junctions[1].bonds] == [true, false, false, false]
        @test [b.flip for b in dcmotor_bg.junctions[1].bonds] == [true, false, false, false]

        rlc_bg = flat_file(_fixture("model.rlc.bondgraph.json"))
        @test rlc_bg.domains == Dict(string("c", i) => "Generic" for i in 1:4)
        @test length([d for d in rlc_bg.diagnostics if d.code == "W205"]) == 1
        @test length(rlc_bg.junctions) == 1
        @test length(rlc_bg.junctions[1].bonds) == 4
        # The two storage elements keep their preferred (integral) causality; SCAP itself
        # is J2.4, but the bonds and their signs must be there for it.
        storage = [v for v in rlc_bg.variables if v.origin.path in ("IL", "C1") &&
                                                    v.kind === :state]
        @test length(storage) == 2
    end

    @testset "fixtures: generated equations" begin
        dcmotor = flat_file(_fixture("model.dcmotor.json"))
        # A wire node equates the across variables and sums the through variables. The
        # composite exposes `p` through its resistor and `n` through the gyrator, so the
        # external wires land on those internal port ids (J2.6 boundary binding).
        @test any(e -> Flat.flat_id(e.lhs) == "Motor1/resistor/p.e" &&
                       Flat.flat_id(e.rhs) == "V1/p.e", dcmotor.equations)
        @test any(e -> occursin("Motor1/gyrator/p.f", sprint(show, e)) &&
                       occursin("Ground1/p.f", sprint(show, e)) &&
                       occursin("V1/n.f", sprint(show, e)), dcmotor.equations)
        # A signal connection is input = output.
        @test any(e -> Flat.flat_id(e.lhs) == "V1/u" && Flat.flat_id(e.rhs) == "Step1/y",
            dcmotor.equations)

        bg = flat_file(_fixture("model.rlc.bondgraph.json"))
        # A 1-junction equates the flows and sums the signed efforts. The Se bond points
        # into the junction, so its bond flow is -Se1/p.f (plan 5.5: X.f = -f_b).
        @test any(e -> Flat.flat_id(e.lhs) == "R1/p.f" &&
                       occursin("Se1/p.f", sprint(show, e)) &&
                       occursin("(-Se1/p.f)", sprint(show, e)), bg.equations)
        @test any(e -> Flat.flat_id(e.lhs) == "IL/p.f" &&
                       occursin("(-Se1/p.f)", sprint(show, e)), bg.equations)
        @test any(e -> occursin("Se1/p.e", sprint(show, e)) &&
                       occursin("R1/p.e", sprint(show, e)) &&
                       occursin("IL/p.e", sprint(show, e)) &&
                       occursin("C1/p.e", sprint(show, e)), bg.equations)
    end

    @testset "negative models: 10 codes on the expected ids" begin
        cases = [
            ("e101_unconnected_input.json", "E101", "n1", nothing, 1),
            ("e101_unconnected_port.json", "E101", "n3", nothing, 1),
            ("e102_two_domains_island.json", "E102", "n4", "c3", 1),
            ("e102_two_sources.json", "E102", "n3", "c2", 1),
            ("e103_unbalanced.json", "E103", "n1", nothing, 1),
            ("e102_wrong_port_kind.json", "E102", "n1", "c1", 1),
            ("e101_unknown_block.json", "E101", "n1", nothing, 1),
            ("e102_bond_cross_domain.json", "E102", "n2", "c1", 1),
            ("w205_generic_island.json", "W205", "n1", "c1", 0),
            ("e003_bad_parameter.json", "E003", "n2", nothing, 1),
        ]
        for (file, code, node, connection, n_errors) in cases
            fm = flat_file(_negative(file))
            @test _has_code(fm, code; node = node, connection = connection)
            @test length(_errors(fm)) == n_errors
            # Exactly one diagnostic with the expected code on that node (the E103
            # fixture also has the block-level warning, which is a different severity).
            matches = [
                d for d in fm.diagnostics if d.code == code && d.node == node &&
                                             (connection === nothing ||
                                              d.connection == connection) &&
                                             (code == "E103" ? d.severity == "error" : true)
            ]
            @test length(matches) == 1
        end

        # The messages carry the useful detail the plan asks for.
        unconnected = flat_file(_negative("e101_unconnected_port.json"))
        d = _diag(unconnected, "E101"; node = "n3")
        @test occursin("shaft", d.message)
        @test occursin("connect it or add a source", d.hint)

        two_sources = flat_file(_negative("e102_two_sources.json"))
        d = _diag(two_sources, "E102"; node = "n3", connection = "c2")
        @test occursin("two sources", d.message)
        @test occursin("c1", d.message) && occursin("c2", d.message)

        conflict = flat_file(_negative("e102_two_domains_island.json"))
        d = _diag(conflict, "E102"; node = "n4", connection = "c3")
        @test occursin("Electrical", d.message) && occursin("Rotation", d.message)
        @test occursin("converter", d.hint)

        unbalanced = flat_file(_negative("e103_unbalanced.json"))
        d = _diag(unbalanced, "E103"; node = "n1", severity = "error")
        @test occursin("3 unknowns", d.message)
        @test occursin("Unbalanced1", d.hint)
        @test any(r -> r.path == "Unbalanced1", d.related)

        unknown = flat_file(_negative("e101_unknown_block.json"))
        d = _diag(unknown, "E101"; node = "n1")
        @test occursin("NoSuchBlock", d.message)

        generic = flat_file(_negative("w205_generic_island.json"))
        d = _diag(generic, "W205"; node = "n1")
        @test occursin("dimensionless", d.message)
        @test generic.domains == Dict("c1" => "Generic", "c2" => "Generic")

        bad_param = flat_file(_negative("e003_bad_parameter.json"))
        d = _diag(bad_param, "E003"; node = "n2")
        @test occursin("V0", d.message)
        @test occursin("parameter `V`", d.message)
    end

    @testset "E101: unconnected outputs are fine, outputs and inputs" begin
        # A Step with an unused output is legal (plan 5.2.6).
        step_only = flat(_model("StepOnly", Any[
            _step_node("n1", "Step1"),
        ], Any[]))
        @test isempty(step_only.diagnostics)
        @test _counts(step_only) == (1, 1)
        @test step_only.stats.states == 0
        @test step_only.signals[1].kind == "output"
    end

    @testset "parameters, starts and constants" begin
        # A capacitor between two grounds: p and n each form a 2-port wire node.
        cap_model = _model("Cap", Any[
            _node("n1", "C1", _ref("stdlib:electrical/Capacitor");
                params = Dict("C" => "2.0e-6"), starts = Dict("v" => "0.5")),
            _node("n2", "G1", _ref("stdlib:electrical/Ground")),
            _node("n3", "G2", _ref("stdlib:electrical/Ground")),
        ], Any[
            _conn("c1", "wire", "n1", "p", "n2", "p"),
            _conn("c2", "wire", "n1", "n", "n3", "p"),
        ])
        fm = flat(cap_model)
        @test _counts(fm) == (9, 9)
        @test isempty(fm.diagnostics)
        v = fm.variables[findfirst(x -> x.id == "C1/v", fm.variables)]
        @test v.start == 0.5
        c = fm.parameters[findfirst(x -> x.id == "C1/C", fm.parameters)]
        @test c.value == 2.0e-6
        @test c.unit == BGSim.Units.parse_unit("F")

        # A parameter override that is not a constant expression is E003 at the node.
        bad = _model("BadParam", Any[
            _node("n1", "V1", _ref("stdlib:electrical/VoltageSource");
                params = Dict("V" => "not_declared + 1")),
        ], Any[])
        fmb = flat(bad)
        @test _has_code(fmb, "E003"; node = "n1")
        @test occursin("parameter `V`", _diag(fmb, "E003"; node = "n1").message)

        # A bad start name is E003; a bad start expression is E001.
        bad_start = _model("BadStart", Any[
            _node("n1", "C1", _ref("stdlib:electrical/Capacitor");
                starts = Dict("nope" => "1.0")),
        ], Any[_conn("c1", "wire", "n1", "p", "n1", "n")])
        @test _has_code(flat(bad_start), "E003"; node = "n1")

        # Parameter defaults stay expression strings until flattening and are folded there.
        step = flat(_model("StepParams", Any[
            _step_node("n1", "Step1"; t_step = "0.0", initial = "1.0", final = "3.0"),
        ], Any[]))
        @test isempty(step.diagnostics)
        values = Dict(p.id => p.value for p in step.parameters)
        @test values["Step1/t_step"] == 0.0
        @test values["Step1/initial"] == 1.0
        @test values["Step1/final"] == 3.0
        @test occursin("ifelse", sprint(show, step.equations[1]))
    end

    @testset "arrays and structural constants (D10/D13)" begin
        # Sum with the default N = 2: dot(signs, u) expands to two scalar products.
        sum_model = _model("Sum2", Any[
            _node("n1", "Sum1", _ref("stdlib:continuous/Sum")),
        ], Any[])
        fm = flat(sum_model)
        @test [v.id for v in fm.variables] ==
              ["Sum1/u[1]", "Sum1/u[2]", "Sum1/y"]
        @test [p.id for p in fm.parameters] ==
              ["Sum1/signs[1]", "Sum1/signs[2]"]
        @test _counts(fm) == (3, 1)
        @test occursin("Sum1/u[1]", sprint(show, fm.equations[1]))
        @test occursin("Sum1/u[2]", sprint(show, fm.equations[1]))
        # One E101 for the vector input (not one per element).
        @test length([d for d in fm.diagnostics if d.code == "E101"]) == 1

        # Overriding N to 3 re-fixes every size; signs must be supplied for three elements.
        sum3 = _model("Sum3", Any[
            _node("n1", "Sum1", _ref("stdlib:continuous/Sum");
                params = Dict("signs" => "[1.0, -1.0, 1.0]"),
                constants = Dict("N" => 3)),
        ], Any[])
        fm3 = flat(sum3)
        @test [v.id for v in fm3.variables] ==
              ["Sum1/u[1]", "Sum1/u[2]", "Sum1/u[3]", "Sum1/y"]
        @test [p.value for p in fm3.parameters] == [1.0, -1.0, 1.0]

        # The wrong length for the overridden N is E004 on the instance.
        sum_bad = _model("SumBad", Any[
            _node("n1", "Sum1", _ref("stdlib:continuous/Sum");
                params = Dict("signs" => "[1.0, -1.0]"),
                constants = Dict("N" => 3)),
        ], Any[])
        @test _has_code(flat(sum_bad), "E004"; node = "n1")

        # An array state start is scalarized element-wise.
        vec_block = """
        @block VecBlock begin
            @variables v::Vec{2} = [0.0, 0.0]
            @outputs y::Real = 0.0
            @equations begin
                v[1] ~ 0.0
                v[2] ~ 0.0
                y ~ v[1] + v[2]
            end
        end
        """
        vec_model = _model("VecModel", Any[
            _node("n1", "V1", _inline(vec_block); starts = Dict("v" => "[1.0, 2.0]")),
        ], Any[])
        fmv = flat(vec_model)
        @test _counts(fmv) == (3, 3)
        @test isempty(fmv.diagnostics)
        @test fmv.variables[findfirst(v -> v.id == "V1/v[1]", fmv.variables)].start == 1.0
        @test fmv.variables[findfirst(v -> v.id == "V1/v[2]", fmv.variables)].start == 2.0
    end

    @testset "subsystems (plan 5.2.3)" begin
        # A resistor inside Load, with p and n exposed as power ports.
        resistor = _node("n1", "R1", _ref("stdlib:electrical/Resistor");
            params = Dict("R" => "5.0"))
        subsystem = Dict{String,Any}(
            "ports" => Any[
                Dict{String,Any}("name" => "p", "kind" => "power",
                    "domain" => "Electrical", "size" => Any[], "node" => "n1", "port" => "p"),
                Dict{String,Any}("name" => "n", "kind" => "power",
                    "domain" => "Electrical", "size" => Any[], "node" => "n1", "port" => "n"),
            ],
            "diagram" => Dict{String,Any}("nodes" => Any[resistor], "connections" => Any[]),
        )
        sub_model = _model("SubModel", Any[
            _step_node("n3", "Step1"),
            _node("n1", "V1", _ref("stdlib:electrical/VoltageSource"); params = Dict("V" => "2.0")),
            _node("n2", "Load", Dict{String,Any}("subsystem" => subsystem)),
        ], Any[
            _conn("c1", "signal", "n3", "y", "n1", "u"),
            _conn("c2", "wire", "n1", "p", "n2", "p"),
            _conn("c3", "wire", "n1", "n", "n2", "n"),
        ])
        fm = flat(sub_model)
        @test _counts(fm) == (10, 10)
        @test isempty(fm.diagnostics)
        @test any(v -> v.id == "Load/R1/p.e", fm.variables)
        @test any(c -> c.id == "c2" && c.to_path == "Load/R1" && c.to_port === :p,
            fm.connections)
        @test fm.stats.instances == 3

        # Signal faces: Gain's u and y exposed, Step -> u and y -> V1.u. A resistor closes
        # the electrical side so the model is complete.
        gain = _node("n1", "G1", _ref("stdlib:continuous/Gain"); params = Dict("k" => "3.0"))
        sig_sub = Dict{String,Any}(
            "ports" => Any[
                Dict{String,Any}("name" => "u", "kind" => "signal", "direction" => "input",
                    "type" => "Real", "size" => Any[], "unit" => nothing,
                    "node" => "n1", "port" => "u"),
                Dict{String,Any}("name" => "y", "kind" => "signal", "direction" => "output",
                    "type" => "Real", "size" => Any[], "unit" => nothing,
                    "node" => "n1", "port" => "y"),
            ],
            "diagram" => Dict{String,Any}("nodes" => Any[gain], "connections" => Any[]),
        )
        sig_model = _model("SigSub", Any[
            _step_node("n4", "Step1"; t_step = "0.0", initial = "0.0", final = "1.0"),
            _node("n1", "V1", _ref("stdlib:electrical/VoltageSource"); params = Dict("V" => "2.0")),
            _node("n2", "Load", Dict{String,Any}("subsystem" => sig_sub)),
            _node("n3", "R1", _ref("stdlib:electrical/Resistor"); params = Dict("R" => "5.0")),
        ], Any[
            _conn("c1", "signal", "n4", "y", "n2", "u"),
            _conn("c2", "signal", "n2", "y", "n1", "u"),
            _conn("c3", "wire", "n1", "p", "n3", "p"),
            _conn("c4", "wire", "n1", "n", "n3", "n"),
        ])
        fms = flat(sig_model)
        @test _counts(fms) == (12, 12)
        @test isempty(fms.diagnostics)
        @test any(e -> Flat.flat_id(e.lhs) == "Load/G1/u" && Flat.flat_id(e.rhs) == "Step1/y",
            fms.equations)
        @test any(e -> Flat.flat_id(e.lhs) == "V1/u" && Flat.flat_id(e.rhs) == "Load/G1/y",
            fms.equations)
    end

    @testset "junctions: 0, 1, junction-to-junction and dangling" begin
        # A 0-junction of two effort sources: equal efforts, flows summing to zero.
        zero_model = _model("ZeroJ", Any[
            _node("n1", "Se1", _ref("stdlib:bondgraph/Se"); params = Dict("e" => "1.0")),
            _node("n2", "J0", _junction(0)),
            _node("n3", "Se2", _ref("stdlib:bondgraph/Se"); params = Dict("e" => "2.0")),
        ], Any[
            _conn("c1", "bond", "n1", "p", "n2"),
            _conn("c2", "bond", "n3", "p", "n2"),
        ])
        fm0 = flat(zero_model)
        @test _counts(fm0) == (4, 4)
        # J2.4: two ideal effort sources on one 0-junction is exactly the causal conflict of
        # plan 5.7 (E106 on the second source). The junction equations are still emitted.
        @test length(_errors(fm0)) == 1
        @test _has_code(fm0, "E106"; node = "n3", connection = "c2")
        @test length([d for d in fm0.diagnostics if d.code == "W205"]) == 1
        @test any(e -> Flat.flat_id(e.lhs) == "Se2/p.e" && Flat.flat_id(e.rhs) == "Se1/p.e",
            fm0.equations)
        # The flow sum: -Se1/p.f - Se2/p.f = 0 (both bonds point into the junction).
        @test any(e -> occursin("Se1/p.f", sprint(show, e)) &&
                       occursin("Se2/p.f", sprint(show, e)) &&
                       occursin("~ 0.0", sprint(show, e)), fm0.equations)

        # Junction-to-junction: virtual bond variables are created and the counts balance.
        jj_model = _model("JJ", Any[
            _node("n1", "Se1", _ref("stdlib:bondgraph/Se"); params = Dict("e" => "1.0")),
            _node("n2", "J1", _junction(1)),
            _node("n3", "J2", _junction(1)),
            _node("n4", "R1", _ref("stdlib:bondgraph/R"); params = Dict("r" => "2.0")),
        ], Any[
            _conn("c1", "bond", "n1", "p", "n2"),
            _conn("c2", "bond", "n2", nothing, "n3", nothing),
            _conn("c3", "bond", "n3", nothing, "n4", "p"),
        ])
        fmj = flat(jj_model)
        @test _counts(fmj) == (6, 6)
        @test isempty(_errors(fmj))
        @test any(v -> v.id == "c2.e", fmj.variables)
        @test any(v -> v.id == "c2.f", fmj.variables)
        @test any(e -> Flat.flat_id(e.lhs) == "c2.f", fmj.equations)
        @test any(v -> v == "c2.e", fmj.junctions[1].bonds[2].eids)

        # A junction with no bonds is E101 on the junction node (it can never be solved).
        lonely = _model("Lonely", Any[
            _node("n1", "J9", _junction(1)),
        ], Any[])
        fml = flat(lonely)
        @test _counts(fml) == (0, 0)
        @test _has_code(fml, "E101"; node = "n1")
        @test occursin("junction", _diag(fml, "E101"; node = "n1").message)
    end

    @testset "bond signs and wire signs (plan 5.5, D8)" begin
        # A direct element-to-element bond: Y.e = e_b, Y.f = f_b, X.e = e_b, X.f = -f_b.
        bond_model = _model("Bond", Any[
            _node("n1", "Se1", _ref("stdlib:bondgraph/Se"); params = Dict("e" => "1.0")),
            _node("n2", "R1", _ref("stdlib:bondgraph/R"); params = Dict("r" => "2.0")),
        ], Any[
            _conn("c1", "bond", "n1", "p", "n2", "p"),
        ])
        fmb = flat(bond_model)
        @test _counts(fmb) == (4, 4)
        @test any(e -> Flat.flat_id(e.lhs) == "R1/p.e" && Flat.flat_id(e.rhs) == "Se1/p.e",
            fmb.equations)
        @test any(e -> Flat.flat_id(e.lhs) == "R1/p.f" &&
                       occursin("Se1/p.f", sprint(show, e)), fmb.equations)

        # Rotation wires equate angular velocity (f) and sum torque (e); Electrical wires
        # equate voltage (e) and sum current (f). The fixture test above proves Electrical;
        # here is a Translation wire: across = f, through = e.
        trans_model = _model("Trans", Any[
            _node("n1", "M1", _ref("stdlib:translation/Mass")),
            _node("n2", "F1", _ref("stdlib:translation/Fixed")),
        ], Any[
            _conn("c1", "wire", "n1", "a", "n2", "a"),
            _conn("c2", "wire", "n1", "b", "n2", "a"),
        ])
        fmt = flat(trans_model)
        @test isempty(_errors(fmt))
        @test any(e -> Flat.flat_id(e.lhs) == "F1/a.f" && Flat.flat_id(e.rhs) == "M1/a.f",
            fmt.equations)
        @test any(e -> occursin("M1/a.e", sprint(show, e)) &&
                       occursin("F1/a.e", sprint(show, e)) &&
                       occursin("~ 0.0", sprint(show, e)), fmt.equations)
    end

    @testset "domain adoption and unit factors (D8/D9, plan 5.3)" begin
        # A Generic R bonded to an Electrical island adopts Electrical: r becomes Ohm and
        # the port fields V/A instead of effort/flow.
        adopt_model = _model("Adopt", Any[
            _node("n1", "G1", _ref("stdlib:electrical/Ground")),
            _node("n2", "J1", _junction(1)),
            _node("n3", "R1", _ref("stdlib:bondgraph/R"); params = Dict("r" => "10.0")),
        ], Any[
            _conn("c1", "bond", "n1", "p", "n2"),
            _conn("c2", "bond", "n2", nothing, "n3", "p"),
        ])
        fm = flat(adopt_model)
        @test _counts(fm) == (4, 4)
        @test isempty(fm.diagnostics)
        @test fm.domains == Dict("c1" => "Electrical", "c2" => "Electrical")
        @test fm.variables[findfirst(v -> v.id == "R1/p.e", fm.variables)].unit ==
              BGSim.Units.parse_unit("V")
        @test fm.variables[findfirst(v -> v.id == "R1/p.f", fm.variables)].unit ==
              BGSim.Units.parse_unit("A")
        @test fm.parameters[findfirst(p -> p.id == "R1/r", fm.parameters)].unit ==
              BGSim.Units.parse_unit("Ohm")
        @test _has_signal(fm, "R1/p.P")
        @test fm.signals[_signal(fm, "R1/p.P")].unit == "W"

        # A signal output in rad feeding an input in deg inserts a factor (plan 5.3).
        deg_sink = """
        @block DegSink begin
            @inputs u::Real, [unit = "deg"]
            @outputs y::Real = 0.0, [unit = "deg"]
            @equations y ~ u
        end
        """
        factor_model = _model("Factor", Any[
            _node("n1", "A1", _ref("stdlib:converters/AngleSensor")),
            _node("n2", "F1", _ref("stdlib:rotation/FixedShaft")),
            _node("n3", "S1", _inline(deg_sink)),
        ], Any[
            _conn("c1", "wire", "n1", "a", "n2", "a"),
            _conn("c2", "signal", "n1", "y", "n3", "u"),
        ])
        fmf = flat(factor_model)
        @test _counts(fmf) == (8, 8)
        @test isempty(fmf.diagnostics)
        @test fmf.unit_factors["c2"] ≈ 180 / pi
        @test any(e -> Flat.flat_id(e.lhs) == "S1/u" &&
                       occursin("57.295", sprint(show, e)), fmf.equations)

        # A signal whose dimensions do not match is E102 at the input.
        length_sink = """
        @block LengthSink begin
            @inputs u::Real, [unit = "m"]
            @outputs y::Real = 0.0, [unit = "m"]
            @equations y ~ u
        end
        """
        mismatch_model = _model("Mismatch", Any[
            _node("n1", "A1", _ref("stdlib:converters/AngleSensor")),
            _node("n2", "F1", _ref("stdlib:rotation/FixedShaft")),
            _node("n3", "S1", _inline(length_sink)),
        ], Any[
            _conn("c1", "wire", "n1", "a", "n2", "a"),
            _conn("c2", "signal", "n1", "y", "n3", "u"),
        ])
        fmm = flat(mismatch_model)
        @test _has_code(fmm, "E102"; node = "n3", connection = "c2")
        @test occursin("unit mismatch", _diag(fmm, "E102"; node = "n3").message)
    end

    @testset "signals (D15) and the model.check result" begin
        fm = flat_file(_fixture("model.dcmotor.json"))
        ids = [s.id for s in fm.signals]
        @test length(ids) == length(unique(ids))
        # Every recorded signal is either an unknown or a derived signal (a port power or a
        # composite observable, J2.6b).
        @test length(ids) == length(fm.variables) + length(fm.derived)
        for port in ("Motor1/p", "Motor1/n", "Motor1/shaft", "Motor1/housing",
                     "V1/p", "V1/n", "Ground1/p", "FixHousing/a", "Damp1/a", "Damp1/b",
                     "FixShaft/a")
            @test _has_signal(fm, port * ".e")
            @test _has_signal(fm, port * ".f")
            @test _has_signal(fm, port * ".P")
            @test fm.signals[_signal(fm, port * ".P")].kind == "power"
        end
        # The flat block's signal names survive the composite rewrite as observables.
        @test fm.signals[_signal(fm, "Motor1/i")].kind == "observed"
        @test fm.signals[_signal(fm, "Motor1/w_rel")].kind == "observed"
        @test fm.signals[_signal(fm, "Motor1/i")].unit == "A"
        @test fm.signals[_signal(fm, "Motor1/w_rel")].unit == "1/s"
        @test fm.signals[_signal(fm, "Step1/y")].kind == "output"
        @test fm.signals[_signal(fm, "V1/u")].kind == "input"
        @test fm.signals[_signal(fm, "Motor1/shaft.e")].kind == "port"
        # `unit_string` is dimension-based (plan 5.3): torque is dimensionally energy, so
        # the canonical spelling is "J", and rad/s is "1/s" (the radian is dimensionless).
        @test fm.signals[_signal(fm, "Motor1/shaft.e")].unit == "J"
        @test fm.signals[_signal(fm, "Motor1/shaft.f")].unit == "1/s"
        @test fm.signals[_signal(fm, "Motor1/shaft.P")].unit == "W"
        @test fm.signals[_signal(fm, "Motor1/p.e")].unit == "V"
        @test fm.signals[_signal(fm, "Motor1/p.f")].unit == "A"
        @test fm.signals[_signal(fm, "Motor1/p.P")].unit == "W"
        @test count(s -> s.kind == "state", fm.signals) == fm.stats.states

        result = Compile.model_check(IR.parse_model(_fixture("model.dcmotor.json")))
        @test Set(keys(result)) ==
              Set([:diagnostics, :domains, :causality, :frames, :multibond,
                    :unitFactors, :signals, :stats])
        @test isempty(result.causality)          # an iconic model has no bonds to stroke
        @test result.frames == Dict{String,String}()   # required, empty when no frame
        @test result.multibond == Dict{String,Int}()
        @test result.stats == (states = 3, equations = 41)
        @test result.signals == fm.signals
        @test result.domains == fm.domains
        @test result.unitFactors == fm.unit_factors
        @test isempty(result.diagnostics)

        # The negative model's result carries the diagnostic too.
        bad = Compile.model_check(IR.parse_model(_negative("e103_unbalanced.json")))
        @test any(d -> d.code == "E103" && d.severity == "error", bad.diagnostics)
    end

    @testset "block.check result" begin
        good = Compile.check_block_source(
            """
            @block MyResistor begin
                @ports begin
                    p::Power{Electrical}
                    n::Power{Electrical}
                end
                @parameters R::Real = 1.0, [unit = "Ohm"]
                @equations begin
                    p.f + n.f ~ 0.0
                    p.e - n.e ~ R * p.f
                end
            end
            """;
            ref = "project:MyResistor",
        )
        @test good.interface !== nothing
        @test isempty([d for d in good.diagnostics if d.severity == "error"])
        @test length(good.interface.ports) == 2
        @test good.interface.parameters[1].name == "R"

        bad = Compile.check_block_source(
            "@block Broken begin\n @outputs y::Real\n @equations y ~ rand()\nend\n";
            ref = "inline:x",
        )
        @test bad.interface === nothing
        @test any(d -> d.code == "E002", bad.diagnostics)
    end

    @testset "project library" begin
        dir = mktempdir()
        mkpath(joinpath(dir, "library"))
        write(
            joinpath(dir, "library", "MyResistor.jl"),
            """
            @block MyResistor begin
                @ports p::Power{Electrical}
                @parameters R::Real = 2.0, [unit = "Ohm"]
                @equations p.e ~ R * p.f
            end
            """,
        )
        model = _model("ProjectRef", Any[
            _node("n1", "R1", _ref("project:MyResistor")),
            _node("n2", "G1", _ref("stdlib:electrical/Ground")),
        ], Any[
            _conn("c1", "wire", "n1", "p", "n2", "p"),
        ])
        fm = Compile.flatten(IR.parse_model(model); project_dir = dir)
        @test _counts(fm) == (4, 4)
        @test isempty(fm.diagnostics)
        @test any(v -> v.id == "R1/p.e", fm.variables)
        @test fm.parameters[findfirst(p -> p.id == "R1/R", fm.parameters)].value == 2.0

        # Without the project library the reference is unknown: E101 on the node.
        missing = Compile.flatten(IR.parse_model(model); project_dir = mktempdir())
        @test _has_code(missing, "E101"; node = "n1")
        @test occursin("MyResistor", _diag(missing, "E101"; node = "n1").message)
    end

    @testset "parameter syntax error is E001" begin
        model = _model("BadSyntax", Any[
            _node("n1", "V1", _ref("stdlib:electrical/VoltageSource");
                params = Dict("V" => "2 * (")),
        ], Any[])
        fm = flat(model)
        @test _has_code(fm, "E001"; node = "n1")
        @test occursin("parameter `V`", _diag(fm, "E001"; node = "n1").message)
    end

    @testset "connection kinds: a wire across concrete domains is E102" begin
        model = _model("WireCross", Any[
            _node("n1", "G1", _ref("stdlib:electrical/Ground")),
            _node("n2", "F1", _ref("stdlib:rotation/FixedShaft")),
        ], Any[
            _conn("c1", "wire", "n1", "p", "n2", "a"),
        ])
        fm = flat(model)
        @test _has_code(fm, "E102"; node = "n2", connection = "c1")
        @test length(_errors(fm)) == 1
        @test occursin("Electrical", _diag(fm, "E102"; node = "n2").message)
        @test occursin("Rotation", _diag(fm, "E102"; node = "n2").message)
    end

    @testset "empty model and internal error containment" begin
        empty = flat(_model("Empty", Any[], Any[]))
        @test _counts(empty) == (0, 0)
        @test isempty(empty.diagnostics)
        @test empty.stats.states == 0

        result = check(_model("Empty", Any[], Any[]))
        @test result.stats == (states = 0, equations = 0)
        @test isempty(result.diagnostics)
    end
end
