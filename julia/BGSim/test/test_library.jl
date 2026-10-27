# Work package J1.3: the library loader, the catalog and the standard library.
#
# Three kinds of test:
#   * the stdlib on disk: every plan ref (the M1 set plus the M2 rows that have landed), one
#     file each, the file name equals the block name, every parameter described, every block
#     checking clean and balanced;
#   * the catalog contract: the structural fields of `contracts/schemas/catalog.schema.json`
#     (every object's property set, exactly) and a field-for-field comparison with
#     `contracts/fixtures/catalog/valid/catalog.min.json` — no field is skipped;
#   * the loader itself: the source-hash cache, diagnostics that point at the block ref, the
#     project library (refs, ordering, file-name and duplicate-name errors) and the D12
#     intrinsic table.
using BGSim
using BGSim.Library: BlockDef, load_block, load_source, load_stdlib, load_project_library,
    catalog, intrinsics, stdlib_dir, has_errors, source_hash, clear_cache, cached_blocks,
    group_info, BLOCK_METADATA, GROUPS
using Test
using JSON3

# The contract fixtures live at the repository root; `Pkg.test()` runs from
# `julia/BGSim/test`, so walk up until `contracts/` is found.
function _repo_root()
    dir = normpath(@__DIR__)
    for _ in 1:10
        isdir(joinpath(dir, "contracts", "schemas")) && return dir
        parent = dirname(dir)
        parent == dir && break
        dir = parent
    end
    error("could not find the repository root (a directory with contracts/schemas) above $(@__DIR__)")
end

const REPO_ROOT = _repo_root()
const CATALOG_SCHEMA_PATH = joinpath(REPO_ROOT, "contracts", "schemas", "catalog.schema.json")
const CATALOG_FIXTURE_PATH =
    joinpath(REPO_ROOT, "contracts", "fixtures", "catalog", "valid", "catalog.min.json")

# The M1 library of plan section 8, by group, as sorted refs. This list is the plan's, not
# the fixture's: the fixture test below compares against the fixture, and this list makes
# sure the fixture and the plan agree.
const M1_REFS = [
    "stdlib:bondgraph/C",
    "stdlib:bondgraph/De",
    "stdlib:bondgraph/Df",
    "stdlib:bondgraph/GY",
    "stdlib:bondgraph/I",
    "stdlib:bondgraph/MSe",
    "stdlib:bondgraph/R",
    "stdlib:bondgraph/Se",
    "stdlib:bondgraph/Sf",
    "stdlib:bondgraph/TF",
    "stdlib:continuous/Gain",
    "stdlib:continuous/Integrator",
    "stdlib:continuous/PIController",
    "stdlib:continuous/Sum",
    "stdlib:converters/AngleSensor",
    "stdlib:converters/DCMotor",
    "stdlib:converters/SpeedSensor",
    "stdlib:electrical/Capacitor",
    "stdlib:electrical/Ground",
    "stdlib:electrical/Inductor",
    "stdlib:electrical/Resistor",
    "stdlib:electrical/VoltageSource",
    "stdlib:rotation/FixedShaft",
    "stdlib:rotation/IdealGear",
    "stdlib:rotation/Inertia",
    "stdlib:rotation/RotationalDamper",
    "stdlib:rotation/TorqueSource",
    "stdlib:rotation/TorsionSpring",
    "stdlib:sources/Constant",
    "stdlib:sources/Sine",
    "stdlib:sources/Step",
    "stdlib:translation/Damper",
    "stdlib:translation/Fixed",
    "stdlib:translation/ForceSource",
    "stdlib:translation/Mass",
    "stdlib:translation/Spring",
]

# The M2 blocks of plan section 8, added by the J2.7 work packages. Every M1 ref above stays
# covered; this list is what the catalog must hold in addition, and `ALL_REFS` is the set the
# on-disk and catalog tests below check against.
const M2_REFS = [
    # J2.7a: the rest of the bond-graph catalog.
    "stdlib:bondgraph/MGY",
    "stdlib:bondgraph/MR",
    "stdlib:bondgraph/MSf",
    "stdlib:bondgraph/MTF",
    # J2.7b: sources and sinks.
    "stdlib:sources/Chirp",
    "stdlib:sources/Noise",
    "stdlib:sources/Pulse",
    "stdlib:sources/Ramp",
    "stdlib:sources/Recorder",
    "stdlib:sources/Scope",
    "stdlib:sources/Time",
    "stdlib:sources/TimeTable",
    # J2.7c: continuous blocks.
    "stdlib:continuous/Abs",
    "stdlib:continuous/DeadZone",
    "stdlib:continuous/Divide",
    "stdlib:continuous/FilteredDerivative",
    "stdlib:continuous/FirstOrder",
    "stdlib:continuous/LeadLag",
    "stdlib:continuous/Lookup1D",
    "stdlib:continuous/Lookup2D",
    "stdlib:continuous/MathFunction",
    "stdlib:continuous/Max",
    "stdlib:continuous/Min",
    "stdlib:continuous/PID",
    "stdlib:continuous/Product",
    "stdlib:continuous/RateLimiter",
    "stdlib:continuous/Relay",
    "stdlib:continuous/Saturation",
    "stdlib:continuous/SecondOrder",
    "stdlib:continuous/Sign",
    "stdlib:continuous/StateSpace",
    "stdlib:continuous/Switch",
    # J2.7d: discrete and logic blocks.
    "stdlib:discrete/And",
    "stdlib:discrete/Compare",
    "stdlib:discrete/Counter",
    "stdlib:discrete/DiscreteIntegrator",
    "stdlib:discrete/DiscretePID",
    "stdlib:discrete/DiscreteSS",
    "stdlib:discrete/DiscreteTF",
    "stdlib:discrete/EdgeDetect",
    "stdlib:discrete/FIR",
    "stdlib:discrete/IIR",
    "stdlib:discrete/Not",
    "stdlib:discrete/OnOffDelay",
    "stdlib:discrete/Or",
    "stdlib:discrete/Quantizer",
    "stdlib:discrete/RateTransition",
    "stdlib:discrete/SRFlipFlop",
    "stdlib:discrete/TypeConversion",
    "stdlib:discrete/UnitDelay",
    "stdlib:discrete/Xor",
    "stdlib:discrete/ZOH",
    # J2.7e: electrical blocks.
    "stdlib:electrical/CurrentSource",
    "stdlib:electrical/IdealDiode",
    "stdlib:electrical/IdealSwitch",
    "stdlib:electrical/IdealTransformer",
    # J2.7f: translation blocks.
    "stdlib:translation/SpringDamper",
    "stdlib:translation/VelocitySource",
    "stdlib:translation/Friction",
    "stdlib:translation/HardStop",
    # J2.7g: rotation completion.
    "stdlib:rotation/SpeedSource",
    "stdlib:rotation/RotationalFriction",
    "stdlib:rotation/ElasticShaft",
    "stdlib:rotation/GearBacklash",
    "stdlib:rotation/LossyGear",
    "stdlib:rotation/GearWithBacklash",
    # J2.7g: the hydraulic group.
    "stdlib:hydraulic/PressureSource",
    "stdlib:hydraulic/FlowSource",
    "stdlib:hydraulic/Tank",
    "stdlib:hydraulic/Volume",
    "stdlib:hydraulic/Orifice",
    "stdlib:hydraulic/VariableOrifice",
    # J2.7g: converters and sensors.
    "stdlib:converters/EMConverter",
    "stdlib:converters/RackAndPinion",
    "stdlib:converters/BallScrew",
    "stdlib:converters/Wheel",
    "stdlib:converters/HydraulicCylinder",
    "stdlib:converters/PositionSensor",
    "stdlib:converters/VelocitySensor",
    "stdlib:converters/AccelerationSensor",
    "stdlib:converters/ForceSensor",
    "stdlib:converters/TorqueSensor",
    "stdlib:converters/VoltageSensor",
    "stdlib:converters/CurrentSensor",
    "stdlib:converters/PressureSensor",
    "stdlib:converters/FlowSensor",
    "stdlib:converters/PowerSensor",
    "stdlib:converters/ExportInput",
    "stdlib:converters/ExportOutput",
    "stdlib:converters/ExportParameter",
]

# Every stdlib block the library must hold: the M1 set plus the M2 rows that have landed.
# Sorted, because `load_stdlib` sorts its blocks by ref.
const ALL_REFS = sort(vcat(M1_REFS, M2_REFS))

# ---------------------------------------------------------------------------------------
# Small helpers: JSON3 values and named tuples to plain Dict/Vector trees, so that `==`
# compares data rather than JSON3 wrappers.
# ---------------------------------------------------------------------------------------

_plain(v::JSON3.Object) =
    Dict{String,Any}(String(k) => _plain(v[k]) for k in keys(v))
_plain(v::JSON3.Array) = [_plain(x) for x in v]
_plain(v::NamedTuple) =
    Dict{String,Any}(String(k) => _plain(getfield(v, k)) for k in keys(v))
_plain(v::AbstractVector) = [_plain(x) for x in v]
_plain(v::AbstractDict) = Dict{String,Any}(String(k) => _plain(v[k]) for k in keys(v))
_plain(v::Symbol) = String(v)
_plain(v) = v

# The data properties of a schema object: `$comment` is an annotation the schema itself
# allows, never data the worker emits, so it is not part of the key set we assert.
_schema_keys(props) = Set(String(k) for k in keys(props) if String(k) != raw"$comment")
_schema_required(def) = Set(String.(def.required))

function _check_object_keys(entry, def)
    e = _plain(entry)
    @test Set(keys(e)) == _schema_keys(def.properties)
    @test _schema_required(def) ⊆ Set(keys(e))
    return nothing
end

_field(obj, name) = obj[Symbol(name)]

const INTERFACE_FIELDS = [
    ("constants", "constantDecl"),
    ("parameters", "parameterDecl"),
    ("inputs", "ioDecl"),
    ("outputs", "ioDecl"),
    ("ports", "portDecl"),
    ("variables", "variableDecl"),
    ("causality", "causalityDecl"),
]

@testset "library" begin
    @testset "the stdlib on disk" begin
        @test isdir(stdlib_dir())
        blocks = load_stdlib()
        @test length(blocks) == length(ALL_REFS)
        @test [b.ref for b in blocks] == ALL_REFS
        @test [b.ref for b in blocks] == sort([b.ref for b in blocks])

        for b in blocks
            group, name = split(b.ref[length("stdlib:")+1:end], '/')
            path = joinpath(stdlib_dir(), group, name * ".jl")
            @test b isa BlockDef
            @test isfile(path)
            @test String(b.name) == name           # plan 3.3: file name == block name
            @test read(path, String) == b.source * "\n"  # the catalog's source is verbatim
            @test b.path == "stdlib/$group/$name.jl"
            @test b.release == "0.1"
            @test b.group == group_info(group).name
            @test !isempty(b.description)
            @test !isempty(b.icon)
        end

        # Every stdlib directory is a catalog group, and every block has its metadata.
        dirs = sort([basename(d) for d in readdir(stdlib_dir(); join = true) if isdir(d)])
        @test dirs == sort([g.dir for g in GROUPS])
        @test Set(keys(BLOCK_METADATA)) == Set([b.ref for b in blocks])
    end

    @testset "every stdlib block checks clean and balanced" begin
        for b in load_stdlib()
            errors = [d for d in b.diagnostics if d.severity == "error"]
            @test isempty(errors)
            @test !has_errors(b)
            # No unused declarations, and the block-level balance precheck (E103) is silent.
            @test isempty([d for d in b.diagnostics if d.code == "W204"])
            @test isempty([d for d in b.diagnostics if d.code == "E103"])
            # A textual composite has no equations of its own; its balance is the model-level
            # check after flattening (J2.6). Every flat block balances here.
            if isempty(components(b.ast))
                bal = block_balance(b.ast)
                @test bal.unknowns == bal.equations
            end
            # Plan section 8: every parameter needs a description.
            for p in b.interface.parameters
                @test !isempty(p.description)
            end
            # `block_equations` returns the checked AST for a clean block.
            @test length(block_equations(b.ast)) == length(equations(b.ast))
        end
    end

    @testset "the M2 bond-graph rows (J2.7a)" begin
        # Plan section 8, M2 row "Bond graph": MSf, MR, MTF, MGY. The spec's component
        # catalog gives their ports and key parameters, so those are asserted here: the
        # golden tests then check the equations.
        blocks = Dict(b.ref => b for b in load_stdlib())

        # MSf/Sf-style: one Generic power port plus a signal input and the flow `gain`. The
        # modulated flow is fixed flow causality, exactly like Sf.
        msf = blocks["stdlib:bondgraph/MSf"]
        @test [(p.name, p.domain, p.size) for p in msf.interface.ports] ==
              [("p", "Generic", Int[])]
        @test [(i.name, i.type, i.size) for i in msf.interface.inputs] ==
              [("u", "Real", Int[])]
        @test [p.name for p in msf.interface.parameters] == ["gain"]
        @test msf.interface.parameters[1].unit == "flow"
        @test msf.interface.causality == [(ports = ["p"], kind = "fixed", value = "flow_out")]
        @test isempty(msf.interface.variables)

        # MR: the same single port and input, with the resistance gain (free causality, like
        # R: no `@causality` declaration).
        mr = blocks["stdlib:bondgraph/MR"]
        @test [(p.name, p.domain, p.size) for p in mr.interface.ports] ==
              [("p", "Generic", Int[])]
        @test [(i.name, i.type, i.size) for i in mr.interface.inputs] ==
              [("u", "Real", Int[])]
        @test [p.name for p in mr.interface.parameters] == ["gain"]
        @test mr.interface.parameters[1].unit == "effort/flow"
        @test isempty(mr.interface.causality)

        # MTF/MGY: two Generic power ports, the signal input as the modulus and no
        # parameters (the spec's "none"), with the two-port causal relation of TF/GY.
        for (ref, kind) in (("stdlib:bondgraph/MTF", "transformer"),
            ("stdlib:bondgraph/MGY", "gyrator"))
            b = blocks[ref]
            @test [(p.name, p.domain, p.size) for p in b.interface.ports] ==
                  [("p1", "Generic", Int[]), ("p2", "Generic", Int[])]
            @test [(i.name, i.type, i.size) for i in b.interface.inputs] ==
                  [("u", "Real", Int[])]
            @test isempty(b.interface.parameters)
            @test isempty(b.interface.variables)
            @test b.interface.causality ==
                  [(ports = ["p1", "p2"], kind = kind, value = nothing)]
        end
    end

    @testset "the M2 sources and sinks rows (J2.7b)" begin
        # Plan section 8, M2 row "Sources and sinks": Ramp, Pulse, Chirp, Time, TimeTable,
        # Noise, Scope (editor-only) and Recorder (no-op, decimation ignored). The golden
        # tests check the equations; this pins the interface the editor and the spec see.
        blocks = Dict(b.ref => b for b in load_stdlib())
        refs = [
            "stdlib:sources/Chirp",
            "stdlib:sources/Noise",
            "stdlib:sources/Pulse",
            "stdlib:sources/Ramp",
            "stdlib:sources/Recorder",
            "stdlib:sources/Scope",
            "stdlib:sources/Time",
            "stdlib:sources/TimeTable",
        ]
        for ref in refs
            b = blocks[ref]
            @test !isempty(b.description)
            @test !isempty(b.icon)
            @test isempty(b.interface.ports)         # signal blocks have no power ports
            @test isempty(b.interface.causality)
        end

        # The four scalar sources plus Time and Noise have one real output `y`.
        for name in ("Ramp", "Pulse", "Chirp", "Time", "Noise")
            b = blocks["stdlib:sources/" * name]
            @test [(o.name, o.type, o.size) for o in b.interface.outputs] ==
                  [("y", "Real", Int[])]
        end

        ramp = blocks["stdlib:sources/Ramp"]
        @test [p.name for p in ramp.interface.parameters] ==
              ["t_start", "slope", "initial"]
        @test [p.unit for p in ramp.interface.parameters] == ["s", "1/s", nothing]
        @test isempty(ramp.interface.constants)
        @test isempty(ramp.interface.inputs)

        pulse = blocks["stdlib:sources/Pulse"]
        @test [p.name for p in pulse.interface.parameters] ==
              ["amplitude", "period", "duty", "t_start"]
        @test pulse.interface.parameters[2].unit == "s"
        @test pulse.interface.parameters[3].min == 0
        @test pulse.interface.parameters[3].max == 1
        @test pulse.interface.parameters[4].unit == "s"

        chirp = blocks["stdlib:sources/Chirp"]
        @test [p.name for p in chirp.interface.parameters] ==
              ["f_start", "f_end", "duration"]
        @test [p.unit for p in chirp.interface.parameters] == ["Hz", "Hz", "s"]

        time = blocks["stdlib:sources/Time"]
        @test time.interface.outputs[1].unit == "s"
        @test isempty(time.interface.parameters)
        @test isempty(time.interface.constants)

        noise = blocks["stdlib:sources/Noise"]
        @test [p.name for p in noise.interface.parameters] ==
              ["mean", "std", "seed", "sample_time"]
        @test noise.interface.parameters[3].type == "Int"
        @test noise.interface.parameters[4].unit == "s"
        @test noise.interface.parameters[2].min == 0

        # The time table: N is a structural constant; the method is D11's Int enumeration
        # (0 = hold, 1 = linear), never a string.
        table = blocks["stdlib:sources/TimeTable"]
        @test [(c.name, c.type, c.default, c.structural) for c in table.interface.constants] ==
              [("N", "Int", 8, true)]
        @test [p.name for p in table.interface.parameters] ==
              ["t_start", "sample_time", "values", "method"]
        @test table.interface.parameters[1].unit == "s"
        @test table.interface.parameters[2].unit == "s"
        @test table.interface.parameters[3].type == "Real"   # Vec{N} elements are Real
        @test table.interface.parameters[4].type == "Int"
        @test table.interface.parameters[4].options == ["hold", "linear"]

        # The editor-only scope: a vector input, no output, no effect on the run.
        scope = blocks["stdlib:sources/Scope"]
        @test [(c.name, c.default) for c in scope.interface.constants] == [("N", 1)]
        @test [(i.name, i.type, i.size) for i in scope.interface.inputs] ==
              [("u", "Real", [1])]
        @test isempty(scope.interface.outputs)
        @test isempty(scope.interface.parameters)

        # The recorder: the same vector input, plus a decimation Int that is ignored.
        recorder = blocks["stdlib:sources/Recorder"]
        @test [(c.name, c.default) for c in recorder.interface.constants] == [("N", 1)]
        @test [(i.name, i.type, i.size) for i in recorder.interface.inputs] ==
              [("u", "Real", [1])]
        @test isempty(recorder.interface.outputs)
        @test [p.name for p in recorder.interface.parameters] == ["decimation"]
        @test recorder.interface.parameters[1].type == "Int"
        @test recorder.interface.parameters[1].min == 1
    end

    @testset "the M2 continuous rows (J2.7c)" begin
        # Plan section 8, M2 row "Continuous": every block of the spec's continuous table that
        # this work package adds. The golden tests check the equations; this pins the
        # interface the editor and the spec see.
        blocks = Dict(b.ref => b for b in load_stdlib())
        refs = [
            "stdlib:continuous/Abs",
            "stdlib:continuous/DeadZone",
            "stdlib:continuous/Divide",
            "stdlib:continuous/FilteredDerivative",
            "stdlib:continuous/FirstOrder",
            "stdlib:continuous/LeadLag",
            "stdlib:continuous/Lookup1D",
            "stdlib:continuous/Lookup2D",
            "stdlib:continuous/MathFunction",
            "stdlib:continuous/Max",
            "stdlib:continuous/Min",
            "stdlib:continuous/PID",
            "stdlib:continuous/Product",
            "stdlib:continuous/RateLimiter",
            "stdlib:continuous/Relay",
            "stdlib:continuous/Saturation",
            "stdlib:continuous/SecondOrder",
            "stdlib:continuous/Sign",
            "stdlib:continuous/StateSpace",
            "stdlib:continuous/Switch",
        ]
        for ref in refs
            b = blocks[ref]
            @test !isempty(b.description)
            @test !isempty(b.icon)
            @test isempty(b.interface.ports)         # signal blocks have no power ports
            @test isempty(b.interface.causality)
            @test [(o.name, o.type) for o in b.interface.outputs] == [("y", "Real")]
        end

        # Product / divide and min / max take two scalar inputs; the language has no N-ary
        # product or extremum reducer, so these are chainable two-input blocks.
        for name in ("Product", "Divide", "Min", "Max")
            b = blocks["stdlib:continuous/" * name]
            @test [(i.name, i.type) for i in b.interface.inputs] ==
                  [("u1", "Real"), ("u2", "Real")]
            @test isempty(b.interface.parameters)
            @test isempty(b.interface.constants)
        end

        # The scalar one-input blocks.
        @test [(i.name, i.type) for i in blocks["stdlib:continuous/Abs"].interface.inputs] ==
              [("u", "Real")]
        @test isempty(blocks["stdlib:continuous/Abs"].interface.parameters)
        @test isempty(blocks["stdlib:continuous/Sign"].interface.parameters)

        # Saturation and dead zone: the two limits, never a string.
        for name in ("Saturation", "DeadZone")
            b = blocks["stdlib:continuous/" * name]
            @test [p.name for p in b.interface.parameters] == ["lower", "upper"]
            @test all(p -> p.type == "Real", b.interface.parameters)
        end
        @test [p.name for p in blocks["stdlib:continuous/RateLimiter"].interface.parameters] ==
              ["rising", "falling"]

        # The first-order family: time constants in seconds.
        fd = blocks["stdlib:continuous/FilteredDerivative"]
        @test [p.name for p in fd.interface.parameters] == ["Tf"]
        @test fd.interface.parameters[1].unit == "s"
        @test [(v.name, v.type) for v in fd.interface.variables] == [("x", "Real")]

        fo = blocks["stdlib:continuous/FirstOrder"]
        @test [p.name for p in fo.interface.parameters] == ["k", "tau"]
        @test fo.interface.parameters[2].unit == "s"

        so = blocks["stdlib:continuous/SecondOrder"]
        @test [p.name for p in so.interface.parameters] == ["k", "w0", "zeta"]
        @test so.interface.parameters[2].unit == "rad/s"
        @test [v.name for v in so.interface.variables] == ["x1", "x2"]

        ll = blocks["stdlib:continuous/LeadLag"]
        @test [p.name for p in ll.interface.parameters] == ["k", "T_lead", "T_lag"]
        @test [p.unit for p in ll.interface.parameters] == [nothing, "s", "s"]

        pid = blocks["stdlib:continuous/PID"]
        @test [p.name for p in pid.interface.parameters] ==
              ["Kp", "Ti", "Td", "N", "lower", "upper"]
        @test [p.unit for p in pid.interface.parameters] ==
              [nothing, "s", "s", nothing, nothing, nothing]
        @test pid.interface.parameters[1].tunable
        @test [v.name for v in pid.interface.variables] == ["xi", "xd", "v"]

        # The state-space block: N is structural, the matrices are Vec/Mat. A parameter decl
        # carries its type and default text (the array size lives in the `Vec`/`Mat` type and
        # in the source), while a variable decl also carries the resolved `size` array.
        ss = blocks["stdlib:continuous/StateSpace"]
        @test [(c.name, c.type, c.default) for c in ss.interface.constants] ==
              [("N", "Int", 2)]
        @test [p.name for p in ss.interface.parameters] == ["A", "B", "C", "D"]
        @test all(p -> p.type == "Real", ss.interface.parameters)
        @test ss.interface.parameters[1].default == "[0.0 1.0; -1.0 -2.0]"
        @test ss.interface.parameters[2].default == "[0.0, 1.0]"
        @test ss.interface.variables[1].size == [2]

        # The relay keeps a held state and declares its two thresholds and two values.
        relay = blocks["stdlib:continuous/Relay"]
        @test [p.name for p in relay.interface.parameters] ==
              ["hi", "lo", "on_value", "off_value", "leak"]
        @test [(v.name, v.type) for v in relay.interface.variables] == [("s", "Real")]

        # Lookup 1D/2D: the table sizes are structural (D13) and the intrinsic is the lookup.
        l1 = blocks["stdlib:continuous/Lookup1D"]
        @test [(c.name, c.default) for c in l1.interface.constants] == [("N", 3)]
        @test [p.name for p in l1.interface.parameters] == ["x", "table"]
        @test l1.interface.parameters[1].default == "[0.0, 1.0, 2.0]"
        @test occursin("interp1", l1.source)

        l2 = blocks["stdlib:continuous/Lookup2D"]
        @test [(c.name, c.default) for c in l2.interface.constants] == [("N", 3)]
        @test [(i.name, i.type) for i in l2.interface.inputs] ==
              [("u", "Real"), ("v", "Real")]
        @test l2.interface.parameters[1].default == "[0.0 1.0 2.0; 0.0 1.0 2.0]"
        @test l2.interface.parameters[2].default ==
              "[0.0 1.0 2.0; 1.0 2.0 3.0; 2.0 3.0 4.0]"
        @test occursin("interp2", l2.source)

        # The math function selector is structural (a @constants Int, D11).
        mf = blocks["stdlib:continuous/MathFunction"]
        @test [(c.name, c.type, c.default) for c in mf.interface.constants] ==
              [("fn", "Int", 0)]
        @test isempty(mf.interface.parameters)
        @test occursin("sin(u)", mf.source)

        sw = blocks["stdlib:continuous/Switch"]
        @test [(i.name, i.type) for i in sw.interface.inputs] ==
              [("u1", "Real"), ("u2", "Real"), ("ctrl", "Real")]
        @test [p.name for p in sw.interface.parameters] == ["threshold"]
    end

    @testset "the M2 discrete and logic rows (J2.7d)" begin
        # Plan section 8, M2 row "Discrete and logic": every block of the spec's discrete
        # table that this work package adds. The golden tests check the equations and the
        # scheduler interaction; this pins the interface the editor and the spec see.
        blocks = Dict(b.ref => b for b in load_stdlib())
        refs = [
            "stdlib:discrete/And",
            "stdlib:discrete/Compare",
            "stdlib:discrete/Counter",
            "stdlib:discrete/DiscreteIntegrator",
            "stdlib:discrete/DiscretePID",
            "stdlib:discrete/DiscreteSS",
            "stdlib:discrete/DiscreteTF",
            "stdlib:discrete/EdgeDetect",
            "stdlib:discrete/FIR",
            "stdlib:discrete/IIR",
            "stdlib:discrete/Not",
            "stdlib:discrete/OnOffDelay",
            "stdlib:discrete/Or",
            "stdlib:discrete/Quantizer",
            "stdlib:discrete/RateTransition",
            "stdlib:discrete/SRFlipFlop",
            "stdlib:discrete/TypeConversion",
            "stdlib:discrete/UnitDelay",
            "stdlib:discrete/Xor",
            "stdlib:discrete/ZOH",
        ]
        for ref in refs
            b = blocks[ref]
            @test !isempty(b.description)
            @test !isempty(b.icon)
            @test b.group == "Discrete and logic"
            @test isempty(b.interface.ports)         # signal blocks have no power ports
            @test isempty(b.interface.causality)
            # Every discrete block drives a `@discrete` scope from a structural period
            # constant; rate transition has an input and an output clock (checked below).
            @test occursin("@discrete Ts = sample_period", b.source) || ref ==
                  "stdlib:discrete/RateTransition"
            @test any(c -> c.name == "sample_period", b.interface.constants) || ref ==
                  "stdlib:discrete/RateTransition"
        end

        # The sample period is a structural constant (D13): it fixes the clock, so changing it
        # is a structural change.
        for ref in refs
            ref == "stdlib:discrete/RateTransition" && continue
            period = only(filter(c -> c.name == "sample_period", blocks[ref].interface.constants))
            @test period.type == "Real"
            @test period.structural
            @test period.default == 1.0e-3
        end

        # Rate transition is the one block with an input and an output clock.
        rt = blocks["stdlib:discrete/RateTransition"]
        @test [(c.name, c.default) for c in rt.interface.constants] ==
              [("sample_period_in", 5.0e-3), ("sample_period_out", 1.0e-3)]
        @test occursin("@discrete Ts = sample_period_in", rt.source)
        @test occursin("@discrete Ts = sample_period_out", rt.source)
        @test [(v.name, v.type) for v in rt.interface.variables] == [("x", "Real")]

        # The scalar one-input, one-output blocks with a Real signal path.
        for name in ("UnitDelay", "ZOH", "DiscreteIntegrator", "DiscretePID", "FIR", "IIR",
            "DiscreteTF", "DiscreteSS", "Quantizer")
            b = blocks["stdlib:discrete/" * name]
            @test [(i.name, i.type) for i in b.interface.inputs] == [("u", "Real")]
            @test [(o.name, o.type) for o in b.interface.outputs] == [("y", "Real")]
        end
        # The on/off-delay timer is the one Bool-in, Bool-out timer.
        delay = blocks["stdlib:discrete/OnOffDelay"]
        @test [(i.name, i.type) for i in delay.interface.inputs] == [("u", "Bool")]
        @test [(o.name, o.type) for o in delay.interface.outputs] == [("y", "Bool")]

        # The Bool blocks: comparators and logic gates.
        @test [(i.name, i.type) for i in blocks["stdlib:discrete/Compare"].interface.inputs] ==
              [("u1", "Real"), ("u2", "Real")]
        @test blocks["stdlib:discrete/Compare"].interface.outputs[1].type == "Bool"
        for name in ("And", "Or", "Xor")
            b = blocks["stdlib:discrete/" * name]
            @test [(i.name, i.type) for i in b.interface.inputs] ==
                  [("u1", "Bool"), ("u2", "Bool")]
            @test [(o.name, o.type) for o in b.interface.outputs] == [("y", "Bool")]
        end
        for name in ("Not", "EdgeDetect")
            b = blocks["stdlib:discrete/" * name]
            @test [(i.name, i.type) for i in b.interface.inputs] == [("u", "Bool")]
            @test [(o.name, o.type) for o in b.interface.outputs] == [("y", "Bool")]
        end
        sr = blocks["stdlib:discrete/SRFlipFlop"]
        @test [(i.name, i.type) for i in sr.interface.inputs] ==
              [("set", "Bool"), ("reset", "Bool")]
        @test [(o.name, o.type) for o in sr.interface.outputs] == [("q", "Bool")]

        # The counter: two Bool inputs and an Int output, with the limits as Int parameters.
        counter = blocks["stdlib:discrete/Counter"]
        @test [(i.name, i.type) for i in counter.interface.inputs] ==
              [("trigger", "Bool"), ("reset", "Bool")]
        @test [(o.name, o.type) for o in counter.interface.outputs] == [("y", "Int")]
        @test [p.name for p in counter.interface.parameters] ==
              ["lower", "upper", "step", "wrap"]
        @test all(p -> p.type == "Int", counter.interface.parameters)

        # The D11 enumerations are Int parameters with option labels, never strings.
        enumerations = Dict(
            "DiscreteIntegrator" => ("method", ["forward", "backward", "trapezoidal"]),
            "DiscretePID" => ("method", ["forward", "backward", "trapezoidal"]),
            "Counter" => ("wrap", ["stop", "wrap"]),
            "Compare" => ("op", ["==", "!=", "<", "<=", ">", ">="]),
            "EdgeDetect" => ("mode", ["rising", "falling", "both"]),
            "SRFlipFlop" => ("dominant", ["set", "reset"]),
            "TypeConversion" => ("target", ["Real", "Int", "Bool"]),
        )
        for (name, (parameter, options)) in enumerations
            p = only(filter(p -> p.name == parameter,
                blocks["stdlib:discrete/" * name].interface.parameters))
            @test p.type == "Int"
            @test p.options == options
            @test p.min === nothing && p.max === nothing   # the labels carry the meaning
        end

        # The discrete controller family: the continuous PID parameter names, in seconds.
        pid = blocks["stdlib:discrete/DiscretePID"]
        @test [p.name for p in pid.interface.parameters] ==
              ["method", "Kp", "Ti", "Td", "lower", "upper"]
        @test [p.unit for p in pid.interface.parameters] ==
              [nothing, nothing, "s", "s", nothing, nothing]
        @test [v.name for v in pid.interface.variables] == ["i", "ep"]

        # The state-space and filter sizes are structural (D13), the matrices are Vec/Mat.
        ss = blocks["stdlib:discrete/DiscreteSS"]
        @test [(c.name, c.type, c.default) for c in ss.interface.constants] ==
              [("N", "Int", 2), ("sample_period", "Real", 1.0e-3)]
        @test [p.name for p in ss.interface.parameters] == ["A", "B", "C", "D"]
        @test ss.interface.parameters[1].default == "[0.5 0.25; 0.0 0.5]"
        @test ss.interface.parameters[2].default == "[1.0, 0.0]"
        @test ss.interface.variables[1].size == [2]

        tf = blocks["stdlib:discrete/DiscreteTF"]
        @test [(c.name, c.default) for c in tf.interface.constants] ==
              [("N", 3), ("sample_period", 1.0e-3)]
        @test [p.name for p in tf.interface.parameters] == ["b", "a"]
        @test tf.interface.variables[1].size == [3]

        fir = blocks["stdlib:discrete/FIR"]
        @test [p.name for p in fir.interface.parameters] == ["b"]
        @test [(c.name, c.default) for c in fir.interface.constants] ==
              [("N", 3), ("sample_period", 1.0e-3)]

        iir = blocks["stdlib:discrete/IIR"]
        @test [p.name for p in iir.interface.parameters] == ["b", "a"]
        @test [(c.name, c.default) for c in iir.interface.constants] ==
              [("N", 3), ("M", 2), ("sample_period", 1.0e-3)]
        @test [(v.name, v.size) for v in iir.interface.variables] ==
              [("uh", [3]), ("yh", [2])]

        # The timers take their delays in seconds.
        onoff = blocks["stdlib:discrete/OnOffDelay"]
        @test [p.name for p in onoff.interface.parameters] == ["t_on", "t_off"]
        @test [p.unit for p in onoff.interface.parameters] == ["s", "s"]
        @test [(v.name, v.unit) for v in onoff.interface.variables] ==
              [("ton", "s"), ("toff", "s")]

        # The quantizer resolution and the unit-delay initial value are tunable parameters.
        @test blocks["stdlib:discrete/Quantizer"].interface.parameters[1].name == "resolution"
        @test blocks["stdlib:discrete/UnitDelay"].interface.parameters[1].name == "initial"
        @test blocks["stdlib:discrete/UnitDelay"].interface.parameters[1].tunable
    end

    @testset "the M2 electrical rows (J2.7e)" begin
        # Plan section 8, M2 row "Electrical": CurrentSource, Ideal diode, Ideal switch and
        # Ideal transformer, plus the M1 rows (Resistor, Capacitor, Inductor, Ground,
        # VoltageSource) that stay green. The golden tests check the equations and the
        # switching behaviour; this pins the interface the editor and the spec see.
        blocks = Dict(b.ref => b for b in load_stdlib())
        refs = [
            "stdlib:electrical/CurrentSource",
            "stdlib:electrical/IdealDiode",
            "stdlib:electrical/IdealSwitch",
            "stdlib:electrical/IdealTransformer",
        ]
        for ref in refs
            b = blocks[ref]
            @test !isempty(b.description)
            @test !isempty(b.icon)
            @test b.group == "Electrical"
            @test all(p -> p.domain == "Electrical", b.interface.ports)
            @test isempty(b.interface.variables)
        end

        # The M1 rows are untouched: the five plan M1 electrical blocks are still there.
        for name in ("Capacitor", "Ground", "Inductor", "Resistor", "VoltageSource")
            @test haskey(blocks, "stdlib:electrical/" * name)
        end

        # CurrentSource: the dual of VoltageSource, with the current gain in amperes and the
        # fixed flow causality of a flow source (D6).
        cs = blocks["stdlib:electrical/CurrentSource"]
        @test [(p.name, p.domain, p.size) for p in cs.interface.ports] ==
              [("p", "Electrical", Int[]), ("n", "Electrical", Int[])]
        @test [(i.name, i.type, i.size) for i in cs.interface.inputs] ==
              [("u", "Real", Int[])]
        @test [p.name for p in cs.interface.parameters] == ["I"]
        @test cs.interface.parameters[1].unit == "A"
        @test cs.interface.causality == [(ports = ["p"], kind = "fixed", value = "flow_out")]

        # IdealDiode: R_on in ohms, G_off in inverse ohms, V_knee in volts. The piecewise
        # linear branch is an `ifelse`, the non-smooth form J2.3 collects.
        diode = blocks["stdlib:electrical/IdealDiode"]
        @test [(p.name, p.domain, p.size) for p in diode.interface.ports] ==
              [("p", "Electrical", Int[]), ("n", "Electrical", Int[])]
        @test [p.name for p in diode.interface.parameters] ==
              ["R_on", "G_off", "V_knee"]
        @test [p.unit for p in diode.interface.parameters] == ["Ohm", "1/Ohm", "V"]
        @test isempty(diode.interface.inputs)
        @test isempty(diode.interface.causality)
        @test occursin("ifelse(", diode.source)
        @test occursin("V_knee", diode.source)

        # IdealSwitch: the spec's Bool control, with the same two conductances.
        switch = blocks["stdlib:electrical/IdealSwitch"]
        @test [(p.name, p.domain, p.size) for p in switch.interface.ports] ==
              [("p", "Electrical", Int[]), ("n", "Electrical", Int[])]
        @test [(i.name, i.type, i.size) for i in switch.interface.inputs] ==
              [("ctrl", "Bool", Int[])]
        @test [p.name for p in switch.interface.parameters] == ["R_on", "G_off"]
        @test [p.unit for p in switch.interface.parameters] == ["Ohm", "1/Ohm"]
        @test isempty(switch.interface.causality)

        # IdealTransformer: four electrical terminals (two windings) and the turns ratio,
        # which is dimensionless.
        transformer = blocks["stdlib:electrical/IdealTransformer"]
        @test [(p.name, p.domain, p.size) for p in transformer.interface.ports] ==
              [("p1", "Electrical", Int[]), ("n1", "Electrical", Int[]),
                  ("p2", "Electrical", Int[]), ("n2", "Electrical", Int[])]
        @test [p.name for p in transformer.interface.parameters] == ["n"]
        @test transformer.interface.parameters[1].unit === nothing
        @test transformer.interface.parameters[1].min == 1.0e-12
        @test isempty(transformer.interface.inputs)
        @test occursin("n * (p2.e - n2.e)", transformer.source)
        @test occursin("p2.f ~ -n * p1.f", transformer.source)
    end

    @testset "the M2 translation rows (J2.7f)" begin
        # Plan section 8, M2 row "Translation": Spring-damper, Velocity source, Friction
        # (Coulomb, viscous and Stribeck, tanh-smoothed or switched) and Hard stop, plus the
        # M1 rows (Damper, Fixed, ForceSource, Mass, Spring) that stay green. D8 makes the
        # Translation across variable `f` (velocity) and the through variable `e` (force).
        # The golden tests check the equations; this pins the interface the editor sees.
        blocks = Dict(b.ref => b for b in load_stdlib())
        refs = [
            "stdlib:translation/SpringDamper",
            "stdlib:translation/VelocitySource",
            "stdlib:translation/Friction",
            "stdlib:translation/HardStop",
        ]
        for ref in refs
            b = blocks[ref]
            @test !isempty(b.description)
            @test !isempty(b.icon)
            @test b.group == "Translation"
            @test all(p -> p.domain == "Translation", b.interface.ports)
        end

        # The M1 rows are untouched: the five plan M1 translation blocks are still there.
        for name in ("Damper", "Fixed", "ForceSource", "Mass", "Spring")
            @test haskey(blocks, "stdlib:translation/" * name)
        end

        # SpringDamper: the spring and the viscous damper in parallel, with the relative
        # displacement x [m] as the state and integral causality.
        sd = blocks["stdlib:translation/SpringDamper"]
        @test [(p.name, p.domain, p.size) for p in sd.interface.ports] ==
              [("a", "Translation", Int[]), ("b", "Translation", Int[])]
        @test isempty(sd.interface.inputs)
        @test [p.name for p in sd.interface.parameters] == ["k", "d"]
        @test [p.unit for p in sd.interface.parameters] == ["N/m", "N*s/m"]
        @test [p.min for p in sd.interface.parameters] == [0, 0]
        @test [(v.name, v.type, v.unit, v.state) for v in sd.interface.variables] ==
              [("x", "Real", "m", "prefer")]
        @test isempty(sd.interface.causality)
        @test occursin("ddt(x) ~ a.f - b.f", sd.source)
        @test occursin("a.e ~ k * x + d * (a.f - b.f)", sd.source)
        @test occursin("b.e ~ -a.e", sd.source)

        # VelocitySource: the flow source of D8 (a.f = v*u), with one power port, a Real
        # input and the fixed flow-out causality of Sf/Fixed.
        vs = blocks["stdlib:translation/VelocitySource"]
        @test [(p.name, p.domain, p.size) for p in vs.interface.ports] ==
              [("a", "Translation", Int[])]
        @test [(i.name, i.type, i.size) for i in vs.interface.inputs] ==
              [("u", "Real", Int[])]
        @test [p.name for p in vs.interface.parameters] == ["v"]
        @test vs.interface.parameters[1].unit == "m/s"
        @test isempty(vs.interface.variables)
        @test vs.interface.causality == [(ports = ["a"], kind = "fixed", value = "flow_out")]
        @test occursin("a.f ~ v * u", vs.source)

        # Friction: two power ports; the Stribeck magnitudes Fs and Fc [N], the viscous
        # coefficient Fv [N*s/m], the Stribeck velocity v_s [m/s] and the smoothing v_eps
        # [m/s]. The sliding direction `s` is an algebraic helper, not a state.
        fr = blocks["stdlib:translation/Friction"]
        @test [(p.name, p.domain, p.size) for p in fr.interface.ports] ==
              [("a", "Translation", Int[]), ("b", "Translation", Int[])]
        @test isempty(fr.interface.inputs)
        @test [p.name for p in fr.interface.parameters] ==
              ["Fs", "Fc", "Fv", "v_s", "v_eps"]
        @test [p.unit for p in fr.interface.parameters] ==
              ["N", "N", "N*s/m", "m/s", "m/s"]
        @test [p.min for p in fr.interface.parameters] == [0, 0, 0, 1.0e-12, 0]
        @test [(v.name, v.unit, v.state) for v in fr.interface.variables] ==
              [("s", nothing, nothing)]
        @test isempty(fr.interface.causality)
        @test occursin("tanh((a.f - b.f) / v_eps)", fr.source)
        @test occursin("v_eps > 0.0", fr.source)
        @test occursin("ifelse(a.f - b.f > 0.0", fr.source)
        @test occursin("exp(-abs(a.f - b.f) / v_s)", fr.source)
        @test occursin("b.e ~ -a.e", fr.source)

        # HardStop: two power ports, the free-travel limits lower/upper [m] and the contact
        # spring-damper k [N/m], d [N*s/m]; the relative displacement x [m] is the state.
        hs = blocks["stdlib:translation/HardStop"]
        @test [(p.name, p.domain, p.size) for p in hs.interface.ports] ==
              [("a", "Translation", Int[]), ("b", "Translation", Int[])]
        @test isempty(hs.interface.inputs)
        @test [p.name for p in hs.interface.parameters] == ["lower", "upper", "k", "d"]
        @test [p.unit for p in hs.interface.parameters] == ["m", "m", "N/m", "N*s/m"]
        @test [p.min for p in hs.interface.parameters] == [nothing, nothing, 0, 0]
        @test [(v.name, v.type, v.unit, v.state) for v in hs.interface.variables] ==
              [("x", "Real", "m", "prefer")]
        @test isempty(hs.interface.causality)
        @test occursin("ddt(x) ~ a.f - b.f", hs.source)
        @test occursin("x > upper", hs.source)
        @test occursin("x < lower", hs.source)
        @test occursin("b.e ~ -a.e", hs.source)
    end

    @testset "the M2 rotation completion rows (J2.7g)" begin
        # Plan section 8, M2 row "Rotation": Speed source, Rotational friction, Elastic shaft
        # and the spec's GearBacklash, LossyGear and GearWithBacklash (the last a composite).
        blocks = Dict(b.ref => b for b in load_stdlib())
        refs = [
            "stdlib:rotation/SpeedSource",
            "stdlib:rotation/RotationalFriction",
            "stdlib:rotation/ElasticShaft",
            "stdlib:rotation/GearBacklash",
            "stdlib:rotation/LossyGear",
            "stdlib:rotation/GearWithBacklash",
        ]
        for ref in refs
            b = blocks[ref]
            @test !isempty(b.description)
            @test !isempty(b.icon)
            @test b.group == "Rotation"
            @test all(p -> p.domain == "Rotation", b.interface.ports)
        end
        # The six M1 rotation rows are untouched.
        for name in ("FixedShaft", "IdealGear", "Inertia", "RotationalDamper",
            "TorqueSource", "TorsionSpring")
            @test haskey(blocks, "stdlib:rotation/" * name)
        end

        # SpeedSource: the D6 flow source of the rotation domain.
        speed = blocks["stdlib:rotation/SpeedSource"]
        @test [(p.name, p.domain, p.size) for p in speed.interface.ports] ==
              [("a", "Rotation", Int[])]
        @test [(i.name, i.type, i.size) for i in speed.interface.inputs] ==
              [("u", "Real", Int[])]
        @test [p.name for p in speed.interface.parameters] == ["w"]
        @test speed.interface.parameters[1].unit == "rad/s"
        @test speed.interface.causality ==
              [(ports = ["a"], kind = "fixed", value = "flow_out")]
        @test occursin("a.f ~ w * u", speed.source)

        # RotationalFriction: the translational Friction law in torque and angular speed.
        rf = blocks["stdlib:rotation/RotationalFriction"]
        @test [(p.name, p.domain) for p in rf.interface.ports] ==
              [("a", "Rotation"), ("b", "Rotation")]
        @test [p.name for p in rf.interface.parameters] ==
              ["Fs", "Fc", "Fv", "v_s", "v_eps"]
        @test [p.unit for p in rf.interface.parameters] ==
              ["N*m", "N*m", "N*m*s/rad", "rad/s", "rad/s"]
        @test [(v.name, v.type, v.state) for v in rf.interface.variables] ==
              [("s", "Real", nothing)]
        @test isempty(rf.interface.causality)
        @test occursin("tanh((a.f - b.f) / v_eps)", rf.source)
        @test occursin("exp(-abs(a.f - b.f) / v_s)", rf.source)
        @test occursin("b.e ~ -a.e", rf.source)

        # ElasticShaft: the torsional C element, with phi as the state.
        es = blocks["stdlib:rotation/ElasticShaft"]
        @test [(p.name, p.domain) for p in es.interface.ports] ==
              [("a", "Rotation"), ("b", "Rotation")]
        @test [p.name for p in es.interface.parameters] == ["k", "d"]
        @test [p.unit for p in es.interface.parameters] == ["N*m/rad", "N*m*s/rad"]
        @test [(v.name, v.type, v.unit, v.state) for v in es.interface.variables] ==
              [("phi", "Real", "rad", "prefer")]
        @test isempty(es.interface.causality)
        @test occursin("ddt(phi) ~ a.f - b.f", es.source)
        @test occursin("a.e ~ k * phi + d * (a.f - b.f)", es.source)
        @test occursin("b.e ~ -a.e", es.source)

        # GearBacklash: the spec's dead-zone contact spring.
        gb = blocks["stdlib:rotation/GearBacklash"]
        @test [(p.name, p.domain) for p in gb.interface.ports] ==
              [("a", "Rotation"), ("b", "Rotation")]
        @test [p.name for p in gb.interface.parameters] == ["k", "d", "gap"]
        @test [p.unit for p in gb.interface.parameters] ==
              ["N*m/rad", "N*m*s/rad", "rad"]
        @test [(v.name, v.unit, v.state) for v in gb.interface.variables] ==
              [("phi", "rad", "prefer"), ("w", "rad/s", nothing), ("T", "N*m", nothing)]
        @test isempty(gb.interface.causality)
        @test occursin("T ~ ifelse(phi > gap / 2", gb.source)
        @test occursin("min(k * (phi + gap / 2) + d * w, 0.0)", gb.source)
        @test occursin("a.e ~ T", gb.source)
        @test occursin("b.e ~ -T", gb.source)

        # LossyGear: ratio and direction-dependent efficiency, a transformer.
        lg = blocks["stdlib:rotation/LossyGear"]
        @test [(p.name, p.domain) for p in lg.interface.ports] ==
              [("a", "Rotation"), ("b", "Rotation")]
        @test [p.name for p in lg.interface.parameters] == ["n", "eta"]
        @test [p.unit for p in lg.interface.parameters] == ["1", "1"]
        @test lg.interface.parameters[2].min == 0
        @test lg.interface.parameters[2].max == 1
        @test lg.interface.causality ==
              [(ports = ["a", "b"], kind = "transformer", value = nothing)]
        @test occursin("a.f ~ n * b.f", lg.source)
        @test occursin("ifelse(a.e * a.f > 0.0, eta, 1.0 / eta)", lg.source)

        # GearWithBacklash: a textual composite. It declares only its two ports and the two
        # components; J2.6 flattens it to the same diagram a JSON subsystem would give.
        gwb = blocks["stdlib:rotation/GearWithBacklash"]
        @test [(p.name, p.domain) for p in gwb.interface.ports] ==
              [("a", "Rotation"), ("b", "Rotation")]
        @test isempty(gwb.interface.parameters)
        @test isempty(gwb.interface.variables)
        @test isempty(gwb.interface.causality)
        comps = components(gwb.ast)
        @test [component_name(c) for c in comps] == [:gear, :play]
        @test [component_block(c) for c in comps] == [:LossyGear, :GearBacklash]
        @test length(connections(gwb.ast)) == 3
        @test occursin("@components", gwb.source)
        @test occursin("connect(gear.b, play.a)", gwb.source)
    end

    @testset "the M2 hydraulic rows (J2.7g)" begin
        # Plan section 8, M2 row "Hydraulic": Pressure source, Flow source, Tank, Volume,
        # Orifice and VariableOrifice. D8 makes the Hydraulic across variable `e` (pressure)
        # and the through variable `f` (volume flow); a pressure source fixes effort, a flow
        # source fixes flow.
        blocks = Dict(b.ref => b for b in load_stdlib())
        refs = [
            "stdlib:hydraulic/PressureSource",
            "stdlib:hydraulic/FlowSource",
            "stdlib:hydraulic/Tank",
            "stdlib:hydraulic/Volume",
            "stdlib:hydraulic/Orifice",
            "stdlib:hydraulic/VariableOrifice",
        ]
        for ref in refs
            b = blocks[ref]
            @test !isempty(b.description)
            @test !isempty(b.icon)
            @test b.group == "Hydraulic"
            @test all(p -> p.domain == "Hydraulic", b.interface.ports)
        end

        # PressureSource and Tank fix the effort (pressure); the D6 entry is effort_out.
        for name in ("PressureSource", "Tank")
            b = blocks["stdlib:hydraulic/" * name]
            @test [(p.name, p.domain, p.size) for p in b.interface.ports] ==
                  [("a", "Hydraulic", Int[])]
            @test b.interface.causality ==
                  [(ports = ["a"], kind = "fixed", value = "effort_out")]
        end
        ps = blocks["stdlib:hydraulic/PressureSource"]
        @test [(i.name, i.type) for i in ps.interface.inputs] == [("u", "Real")]
        @test [p.name for p in ps.interface.parameters] == ["p"]
        @test ps.interface.parameters[1].unit == "Pa"
        @test occursin("a.e ~ p * u", ps.source)
        tank = blocks["stdlib:hydraulic/Tank"]
        @test [p.name for p in tank.interface.parameters] == ["p"]
        @test tank.interface.parameters[1].unit == "Pa"
        @test occursin("a.e ~ p", tank.source)

        # FlowSource: two terminals, a signal input and the flow gain. The two-terminal
        # fixed flow has no one-port D6 entry, so it declares no causality.
        fs = blocks["stdlib:hydraulic/FlowSource"]
        @test [(p.name, p.domain) for p in fs.interface.ports] ==
              [("a", "Hydraulic"), ("b", "Hydraulic")]
        @test [(i.name, i.type) for i in fs.interface.inputs] == [("u", "Real")]
        @test [p.name for p in fs.interface.parameters] == ["Q"]
        @test fs.interface.parameters[1].unit == "m^3/s"
        @test isempty(fs.interface.causality)
        @test occursin("a.f ~ Q * u", fs.source)
        @test occursin("b.f ~ -Q * u", fs.source)

        # Volume: the hydraulic C element, V and bulk modulus beta, pressure state p.
        vol = blocks["stdlib:hydraulic/Volume"]
        @test [(p.name, p.domain) for p in vol.interface.ports] ==
              [("a", "Hydraulic")]
        @test [p.name for p in vol.interface.parameters] == ["V", "beta"]
        @test [p.unit for p in vol.interface.parameters] == ["m^3", "Pa"]
        @test [(v.name, v.type, v.unit, v.state) for v in vol.interface.variables] ==
              [("p", "Real", "Pa", "prefer")]
        @test isempty(vol.interface.causality)
        @test occursin("ddt(p) ~ beta * a.f / V", vol.source)
        @test occursin("a.e ~ p", vol.source)

        # Orifice and VariableOrifice: the regularized law, with dp and Q as observed
        # algebraic helpers. Both declare no causality (a two-port R element is free).
        for (name, has_input) in (("Orifice", false), ("VariableOrifice", true))
            b = blocks["stdlib:hydraulic/" * name]
            @test [(p.name, p.domain) for p in b.interface.ports] ==
                  [("a", "Hydraulic"), ("b", "Hydraulic")]
            @test [p.name for p in b.interface.parameters] ==
                  ["Cd", "A", "rho", "p_tr"]
            @test [p.unit for p in b.interface.parameters] ==
                  ["1", "m^2", "kg/m^3", "Pa"]
            @test [(v.name, v.unit) for v in b.interface.variables] ==
                  [("dp", "Pa"), ("Q", "m^3/s")]
            @test isempty(b.interface.causality)
            @test occursin("dp ~ a.e - b.e", b.source)
            @test occursin("p_tr * p_tr", b.source)
            @test occursin("a.f ~ Q", b.source)
            @test occursin("b.f ~ -Q", b.source)
            if has_input
                @test [(i.name, i.type) for i in b.interface.inputs] == [("u", "Real")]
                @test occursin("(A * u) * (A * u)", b.source)
            else
                @test isempty(b.interface.inputs)
                @test occursin("A * A", b.source)
            end
        end
    end

    @testset "the M2 converters and sensors rows (J2.7g)" begin
        # Plan section 8, M2 row "Converters and sensors": the EM converter, the three
        # kinematic converters, the hydraulic cylinder, the ten sensor blocks and the three
        # export interface markers, on top of the M1 DCMotor/SpeedSensor/AngleSensor.
        blocks = Dict(b.ref => b for b in load_stdlib())
        refs = [
            "stdlib:converters/EMConverter",
            "stdlib:converters/RackAndPinion",
            "stdlib:converters/BallScrew",
            "stdlib:converters/Wheel",
            "stdlib:converters/HydraulicCylinder",
            "stdlib:converters/PositionSensor",
            "stdlib:converters/VelocitySensor",
            "stdlib:converters/AccelerationSensor",
            "stdlib:converters/ForceSensor",
            "stdlib:converters/TorqueSensor",
            "stdlib:converters/VoltageSensor",
            "stdlib:converters/CurrentSensor",
            "stdlib:converters/PressureSensor",
            "stdlib:converters/FlowSensor",
            "stdlib:converters/PowerSensor",
            "stdlib:converters/ExportInput",
            "stdlib:converters/ExportOutput",
            "stdlib:converters/ExportParameter",
        ]
        for ref in refs
            b = blocks[ref]
            @test !isempty(b.description)
            @test !isempty(b.icon)
            @test b.group == "Converters and sensors"
        end
        for name in ("DCMotor", "SpeedSensor", "AngleSensor")
            @test haskey(blocks, "stdlib:converters/" * name)
        end

        # EMConverter: electrical p/n plus one rotational shaft, k in N*m/A, a gyrator
        # relation (no D6 entry: the two electrical terminals are one port).
        em = blocks["stdlib:converters/EMConverter"]
        @test [(p.name, p.domain, p.size) for p in em.interface.ports] ==
              [("p", "Electrical", Int[]), ("n", "Electrical", Int[]),
                  ("shaft", "Rotation", Int[])]
        @test [p.name for p in em.interface.parameters] == ["k"]
        @test em.interface.parameters[1].unit == "N*m/A"
        @test isempty(em.interface.inputs)
        @test isempty(em.interface.causality)
        @test occursin("p.e - n.e ~ -k * shaft.f", em.source)
        @test occursin("shaft.e ~ k * p.f", em.source)

        # Rack and pinion and wheel: rotation a -> translation b, radius r, transformer.
        for (name, radius) in (("RackAndPinion", "0.02"), ("Wheel", "0.3"))
            b = blocks["stdlib:converters/" * name]
            @test [(p.name, p.domain) for p in b.interface.ports] ==
                  [("a", "Rotation"), ("b", "Translation")]
            @test [p.name for p in b.interface.parameters] == ["r"]
            @test b.interface.parameters[1].unit == "m"
            @test b.interface.parameters[1].default == radius
            @test b.interface.causality ==
                  [(ports = ["a", "b"], kind = "transformer", value = nothing)]
            @test occursin("b.f ~ r * a.f", b.source)
            @test occursin("b.e ~ -a.e / r", b.source)
        end

        # Ball screw: lead in m/rev and efficiency; one lead is one revolution.
        bs = blocks["stdlib:converters/BallScrew"]
        @test [(p.name, p.domain) for p in bs.interface.ports] ==
              [("a", "Rotation"), ("b", "Translation")]
        @test [p.name for p in bs.interface.parameters] == ["lead", "eta"]
        @test [p.unit for p in bs.interface.parameters] == ["m", "1"]
        @test bs.interface.causality ==
              [(ports = ["a", "b"], kind = "transformer", value = nothing)]
        @test occursin("6.283185307179586", bs.source)     # 2*pi, no pi predefined

        # HydraulicCylinder: chambers A and B plus the translation rod, with dead volumes
        # and the swept volumes as the compressibility states.
        cyl = blocks["stdlib:converters/HydraulicCylinder"]
        @test [(p.name, p.domain, p.size) for p in cyl.interface.ports] ==
              [("A", "Hydraulic", Int[]), ("B", "Hydraulic", Int[]),
                  ("rod", "Translation", Int[])]
        @test [p.name for p in cyl.interface.parameters] ==
              ["Ap", "Ar", "V0A", "V0B", "beta", "stroke"]
        @test [p.unit for p in cyl.interface.parameters] ==
              ["m^2", "m^2", "m^3", "m^3", "Pa", "m"]
        @test [(v.name, v.unit, v.state) for v in cyl.interface.variables] ==
              [("x", "m", "prefer"), ("pA", "Pa", "prefer"), ("pB", "Pa", "prefer")]
        @test isempty(cyl.interface.causality)
        @test occursin("V0A + Ap * x", cyl.source)
        @test occursin("V0B + Ar * (stroke - x)", cyl.source)
        @test occursin("rod.e ~ pB * Ar - pA * Ap", cyl.source)

        # The three translational sensors share the port and the zero-effort tap.
        for (name, unit, has_state) in (("PositionSensor", "m", true),
            ("VelocitySensor", "m/s", false), ("AccelerationSensor", "m/s^2", true))
            b = blocks["stdlib:converters/" * name]
            @test [(p.name, p.domain) for p in b.interface.ports] ==
                  [("a", "Translation")]
            @test [(o.name, o.type, o.unit) for o in b.interface.outputs] ==
                  [("y", "Real", unit)]
            @test isempty(b.interface.parameters)
            @test b.interface.causality ==
                  [(ports = ["a"], kind = "fixed", value = "effort_out")]
            @test occursin("a.e ~ 0.0", b.source)
            @test has_state == !isempty(b.interface.variables)
        end
        @test occursin("ddt(x) ~ a.f", blocks["stdlib:converters/PositionSensor"].source)
        @test occursin("y ~ ddt(v)",
            blocks["stdlib:converters/AccelerationSensor"].source)

        # Force and torque sensors: transparent two-ports, no parameters, no causality.
        for (name, domain, unit) in (("ForceSensor", "Translation", "N"),
            ("TorqueSensor", "Rotation", "N*m"))
            b = blocks["stdlib:converters/" * name]
            @test [(p.name, p.domain) for p in b.interface.ports] ==
                  [("a", domain), ("b", domain)]
            @test [(o.name, o.unit) for o in b.interface.outputs] == [("y", unit)]
            @test isempty(b.interface.parameters)
            @test isempty(b.interface.causality)
            @test occursin("a.f ~ b.f", b.source)
            @test occursin("b.e ~ -y", b.source)
        end

        # Voltage/current sensors and pressure/flow sensors.
        for (name, unit) in (("VoltageSensor", "V"), ("CurrentSensor", "A"))
            b = blocks["stdlib:converters/" * name]
            @test [(p.name, p.domain) for p in b.interface.ports] ==
                  [("p", "Electrical"), ("n", "Electrical")]
            @test [(o.name, o.unit) for o in b.interface.outputs] == [("y", unit)]
            @test isempty(b.interface.parameters)
            @test isempty(b.interface.causality)
        end
        vs = blocks["stdlib:converters/VoltageSensor"]
        @test occursin("p.f ~ 0.0", vs.source)
        @test occursin("y ~ p.e - n.e", vs.source)
        cs = blocks["stdlib:converters/CurrentSensor"]
        @test occursin("p.e - n.e ~ 0.0", cs.source)
        @test occursin("p.f ~ y", cs.source)

        prs = blocks["stdlib:converters/PressureSensor"]
        @test [(p.name, p.domain) for p in prs.interface.ports] ==
              [("a", "Hydraulic")]
        @test [(o.name, o.unit) for o in prs.interface.outputs] == [("y", "Pa")]
        @test prs.interface.causality ==
              [(ports = ["a"], kind = "fixed", value = "flow_out")]
        @test occursin("a.f ~ 0.0", prs.source)
        fls = blocks["stdlib:converters/FlowSensor"]
        @test [(p.name, p.domain) for p in fls.interface.ports] ==
              [("a", "Hydraulic"), ("b", "Hydraulic")]
        @test [(o.name, o.unit) for o in fls.interface.outputs] ==
              [("y", "m^3/s")]
        @test isempty(fls.interface.causality)
        @test occursin("a.e ~ b.e", fls.source)
        @test occursin("a.f ~ y", fls.source)

        # PowerSensor: a Generic two-port bond tap; the output carries the D9 symbolic
        # power unit (it becomes W when a concrete island adopts the block).
        pws = blocks["stdlib:converters/PowerSensor"]
        @test [(p.name, p.domain) for p in pws.interface.ports] ==
              [("a", "Generic"), ("b", "Generic")]
        @test [(o.name, o.unit) for o in pws.interface.outputs] ==
              [("y", "effort*flow")]
        @test isempty(pws.interface.parameters)
        @test occursin("y ~ a.e * a.f", pws.source)

        # Export markers: an input is a constant source in simulation, an output holds its
        # input, and a parameter publishes a tunable value. The spec's name/type/unit are
        # instance metadata, which the language has no parameter type for.
        ei = blocks["stdlib:converters/ExportInput"]
        @test isempty(ei.interface.ports)
        @test isempty(ei.interface.inputs)
        @test [(o.name, o.type) for o in ei.interface.outputs] == [("y", "Real")]
        @test [p.name for p in ei.interface.parameters] == ["value"]
        @test occursin("y ~ value", ei.source)

        eo = blocks["stdlib:converters/ExportOutput"]
        @test isempty(eo.interface.ports)
        @test [(i.name, i.type) for i in eo.interface.inputs] == [("u", "Real")]
        @test isempty(eo.interface.outputs)
        @test isempty(eo.interface.parameters)
        @test occursin("sink ~ u", eo.source)

        ep = blocks["stdlib:converters/ExportParameter"]
        @test isempty(ep.interface.ports)
        @test isempty(ep.interface.inputs)
        @test isempty(ep.interface.outputs)
        @test [p.name for p in ep.interface.parameters] == ["value"]
        @test ep.interface.parameters[1].tunable
        @test occursin("sink ~ value", ep.source)
    end

    @testset "catalog structure against catalog.schema.json" begin
        schema = JSON3.read(read(CATALOG_SCHEMA_PATH, String))
        defs = schema[raw"$defs"]
        cat = catalog()

        # Root object: exactly the schema's data properties, and the required ones present.
        root = _plain(cat)
        @test Set(keys(root)) == _schema_keys(schema.properties)
        @test _schema_required(schema) ⊆ Set(keys(root))
        @test cat.language == "0.1.0"

        for block in cat.blocks
            _check_object_keys(block, defs["catalogBlock"])
            for (field, defname) in INTERFACE_FIELDS
                for entry in _field(block, field)
                    _check_object_keys(entry, defs[defname])
                end
            end
        end

        for junction in cat.junctions
            _check_object_keys(junction, defs["junction"])
        end
        for domain in cat.domains
            _check_object_keys(domain, defs["domain"])
            for field in ("effort", "flow")
                _check_object_keys(_field(domain, field), defs["domainVariable"])
            end
        end

        # The shared `blockInterface` definition exists and covers the same seven arrays the
        # catalog block embeds; that is what keeps `block.check` and `catalog.get` aligned.
        iface = _schema_keys(defs["blockInterface"].properties)
        @test iface == Set([field for (field, _) in INTERFACE_FIELDS])
        first_interface = _plain(block_interface(load_stdlib()[1].ast))
        @test _schema_required(defs["blockInterface"]) ⊆ Set(keys(first_interface))
    end

    @testset "catalog against the contract fixture, field for field" begin
        fixture = JSON3.read(read(CATALOG_FIXTURE_PATH, String))
        cat = catalog()

        @test cat.language == String(fixture.language)
        # The fixture is the contract for the M1 catalog and is not edited by the M2 work
        # packages, so it is compared field for field rather than for coverage: every
        # fixture block must still be in the catalog unchanged, and the catalog holds the
        # M2 rows on top of it (checked against `ALL_REFS` below and by the schema test).
        @test length(cat.blocks) == length(ALL_REFS)

        ours = Dict(b.ref => _plain(b) for b in cat.blocks)
        theirs = Dict(String(b.ref) => _plain(b) for b in fixture.blocks)
        @test sort(collect(keys(theirs))) == sort(M1_REFS)
        @test sort(collect(keys(ours))) == ALL_REFS
        @test all(haskey(ours, ref) for ref in keys(theirs))

        for ref in sort(collect(keys(theirs)))
            a, b = ours[ref], theirs[ref]
            # No skipped fields: the key sets must be equal and every value must match.
            @test Set(keys(a)) == Set(keys(b))
            for field in sort(collect(keys(b)))
                @test a[field] == b[field]
            end
            # The name lists the plan's contract calls out explicitly.
            for field in ("constants", "parameters", "inputs", "outputs", "ports", "variables")
                @test [entry["name"] for entry in a[field]] ==
                      [entry["name"] for entry in b[field]]
            end
        end

        @test _plain(cat.junctions) == _plain(fixture.junctions)
        @test _plain(cat.domains) == _plain(fixture.domains)

        # The two junctions and the five domains, explicitly (plan 3.2 and decision D8).
        @test [j.ref for j in cat.junctions] == ["junction:0", "junction:1"]
        @test [d.name for d in cat.domains] ==
              ["Electrical", "Translation", "Rotation", "Hydraulic", "Generic"]
        domains = Dict(d.name => d for d in cat.domains)
        @test domains["Electrical"].effort == (name = "voltage", unit = "V")
        @test domains["Electrical"].flow == (name = "current", unit = "A")
        @test domains["Electrical"].across == "e"
        @test domains["Translation"].effort == (name = "force", unit = "N")
        @test domains["Translation"].flow == (name = "velocity", unit = "m/s")
        @test domains["Translation"].across == "f"
        @test domains["Rotation"].effort == (name = "torque", unit = "N*m")
        @test domains["Rotation"].flow == (name = "angular_velocity", unit = "rad/s")
        @test domains["Rotation"].across == "f"
        @test domains["Hydraulic"].effort == (name = "pressure", unit = "Pa")
        @test domains["Hydraulic"].flow == (name = "volume_flow", unit = "m^3/s")
        @test domains["Hydraulic"].across == "e"
        @test domains["Generic"].effort == (name = "effort", unit = nothing)
        @test domains["Generic"].flow == (name = "flow", unit = nothing)
        @test domains["Generic"].across === nothing
        @test all(d -> d.size == 1, cat.domains)

        # Deterministic: a second call returns the same catalog (and exercises the cache).
        @test _plain(catalog()) == _plain(cat)
    end

    @testset "the parse cache is keyed on the source text" begin
        clear_cache()
        @test cached_blocks() == 0
        text = read(joinpath(stdlib_dir(), "bondgraph", "C.jl"), String)
        b1 = load_block(text; ref = "stdlib:bondgraph/C")
        b2 = load_block(text; ref = "stdlib:bondgraph/C")
        @test b1 === b2                         # cached: the identical object
        @test cached_blocks() == 1

        # `load_source` returns the same ParsedBlock the cache holds.
        @test load_source(text; ref = "stdlib:bondgraph/C") === b1.ast
        @test cached_blocks() == 1

        # The hash is stable and content sensitive.
        @test source_hash(text) == source_hash(String(codeunits(text)))
        @test source_hash(text) != source_hash(text * " ")

        # The ref is part of the key (it changes the group and the stdlib-only rule).
        other = load_block(text; ref = "project:C")
        @test other !== b1
        @test other.group == "Project"
        @test b1.group == "Bond graph"
        @test cached_blocks() == 2

        # An edited source is a new entry and does not disturb the cached one.
        edited = replace(text, "c::Real = 1.0" => "c::Real = 2.0")
        b3 = load_block(edited; ref = "stdlib:bondgraph/C")
        @test b3 !== b1
        @test b3.interface.parameters[1].default == "2.0"
        @test b1.interface.parameters[1].default == "1.0"

        clear_cache()
        @test cached_blocks() == 0
    end

    @testset "a bad block reports diagnostics against its ref" begin
        bad = """
        @block Bad begin
            @ports p::Power{Generic}
            @parameters k::Real = 1.0, [description = "Gain"]
            @equations p.e ~ k * missing_name
        end
        """
        b = load_block(bad; ref = "project:Bad")
        @test has_errors(b)
        errors = [d for d in b.diagnostics if d.code == "E003"]
        @test length(errors) == 1
        d = only(errors)
        @test d.severity == "error"
        @test d.block == "project:Bad"
        @test d.source !== nothing
        @test d.source.kind == "project"
        @test d.source.ref == "project:Bad"
        @test d.source.range !== nothing
        @test d.source.range.line == 4
        @test d.scope == "@equations"

        # A warning (unused declaration) does not make the block unusable.
        unused = """
        @block Unused begin
            @ports p::Power{Generic}
            @parameters k::Real = 1.0, [description = "Never used"]
            @equations p.e ~ 0.0
        end
        """
        w = load_block(unused; ref = "project:Unused")
        @test !has_errors(w)
        @test any(d -> d.code == "W204" && d.severity == "warning", w.diagnostics)

        # A syntax error is carried through as E000, not thrown.
        broken = load_block(
            "@block Broken begin\n    @ports p::Power{Generic}\n"; ref = "project:Broken"
        )
        @test has_errors(broken)
        @test any(d -> d.code == "E000", broken.diagnostics)
    end

    @testset "project library" begin
        mktempdir() do dir
            lib = joinpath(dir, "library")
            mkpath(lib)
            write(
                joinpath(lib, "Adder.jl"),
                """
                @block Adder begin
                    @inputs u::Real
                    @outputs y::Real
                    @parameters offset::Real = 0.0, [description = "Offset"]
                    @equations y ~ u + offset
                end
                """,
            )
            write(
                joinpath(lib, "Doubler.jl"),
                """
                @block Doubler begin
                    @inputs u::Real
                    @outputs y::Real
                    @parameters k::Real = 2.0, [description = "Gain"]
                    @equations y ~ k * u
                end
                """,
            )

            blocks = load_project_library(lib)
            @test [b.ref for b in blocks] == ["project:Adder", "project:Doubler"]
            @test all(b -> b.group == "Project", blocks)
            @test all(b -> !has_errors(b), blocks)
            @test blocks[1].path == "library/Adder.jl"
            @test blocks[1].release == "0.1"
            @test isempty(blocks[1].description)   # no metadata entry for a project block

            # The catalog merges them at their project refs, sorted, from either the project
            # root or the library directory itself.
            c_lib = catalog(lib)
            c_root = catalog(dir)
            @test length(c_lib.blocks) == length(ALL_REFS) + 2
            @test [b.ref for b in c_lib.blocks] == [b.ref for b in c_root.blocks]
            @test issorted([b.ref for b in c_lib.blocks])
            @test c_lib.blocks[1].ref == "project:Adder"
            @test c_lib.blocks[2].ref == "project:Doubler"
            @test c_lib.blocks[2].path == "library/Doubler.jl"
            @test c_lib.blocks[2].name == "Doubler"
            @test length(c_lib.blocks[2].parameters) == 1
            @test c_lib.blocks[2].parameters[1].default == "2.0"

            # A file name that does not match the block name is an E001 on that block.
            write(
                joinpath(lib, "Wrong.jl"),
                """
                @block NotWrong begin
                    @outputs y::Real
                    @equations y ~ 0.0
                end
                """,
            )
            blocks = load_project_library(lib)
            wrong = only(filter(b -> b.ref == "project:Wrong", blocks))
            name_errors = [d for d in wrong.diagnostics if d.code == "E001"]
            @test length(name_errors) == 1
            d = only(name_errors)
            @test occursin("does not match the block name", d.message)
            @test d.block == "project:Wrong"
            @test d.source.ref == "project:Wrong"
            @test d.source.range !== nothing
            rm(joinpath(lib, "Wrong.jl"))

            # A block name declared by two files is ambiguous; the second gets an E001.
            write(
                joinpath(lib, "Clash1.jl"),
                """
                @block Clash begin
                    @outputs y::Real
                    @equations y ~ 0.0
                end
                """,
            )
            write(
                joinpath(lib, "Clash2.jl"),
                """
                @block Clash begin
                    @outputs y::Real
                    @equations y ~ 1.0
                end
                """,
            )
            blocks = load_project_library(lib)
            first_clash = only(filter(b -> b.ref == "project:Clash1", blocks))
            second_clash = only(filter(b -> b.ref == "project:Clash2", blocks))
            @test !any(d -> occursin("already declared", d.message), first_clash.diagnostics)
            @test any(d -> d.code == "E001" && occursin("already declared", d.message),
                second_clash.diagnostics)

            # A project without a library directory is not an error.
            @test isempty(load_project_library(joinpath(dir, "missing")))
            @test length(catalog(dir).blocks) == length(ALL_REFS) + 4  # re-read; the two clash files are included
        end
    end

    @testset "intrinsics (D12)" begin
        rows = intrinsics()
        @test [r.name for r in rows] == ["delay", "interp1", "interp2", "noise_normal"]
        by = Dict(r.name => r for r in rows)
        @test by["interp1"].arity == 3
        @test by["interp2"].arity == 4
        @test by["noise_normal"].arity == 2
        @test by["delay"].arity == 2
        @test by["interp1"].stdlib_only == false
        @test by["interp2"].stdlib_only == false
        @test by["noise_normal"].stdlib_only == true
        @test by["delay"].stdlib_only == true
        @test by["delay"].lowering == :delay
        @test all(
            r -> r.lowering == :intrinsic,
            [by["interp1"], by["interp2"], by["noise_normal"]],
        )
        @test all(r -> !isempty(r.description), rows)

        # The table is derived from the one whitelist table, so it cannot drift from it.
        for row in rows
            rule = BGSim.function_rule(Symbol(row.name))
            @test rule !== nothing
            @test rule.stdlib_only == row.stdlib_only
            @test rule.min_args == row.arity == rule.max_args
        end
    end

    @testset "blocks serialise to JSON" begin
        blocks = load_stdlib()
        b = only(filter(b -> b.ref == "stdlib:converters/DCMotor", blocks))
        d = BGSim.Library.to_dict(b)
        @test d isa Dict{String,Any}
        @test Set(keys(d)) == Set(keys(_plain(BGSim.Library.to_namedtuple(b))))

        back = JSON3.read(JSON3.write(d))
        @test _plain(back) == _plain(BGSim.Library.to_namedtuple(b))

        # The whole catalog round-trips through JSON unchanged.
        cat = catalog()
        fresh = JSON3.read(JSON3.write(cat))
        @test _plain(fresh) == _plain(cat)
        @test length(fresh["blocks"]) == length(ALL_REFS)
    end
end
