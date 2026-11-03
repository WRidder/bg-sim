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
    "stdlib:converters/ExportInputPass",
    "stdlib:converters/ExportOutput",
    "stdlib:converters/ExportParameter",
]

# The M3 planar multibond primitives of J-MB4 (plan 6, row J-MB4). They live in the
# `multibond` group; the catalog must carry them alongside the M1/M2 blocks.
const M3_REFS = [
    "stdlib:multibond/ComposePose2D",
    "stdlib:multibond/CoriolisPlanar",
    "stdlib:multibond/CPlanar",
    "stdlib:multibond/DePlanar",
    "stdlib:multibond/DfPlanar",
    "stdlib:multibond/ExternalWrenchPlanar",
    "stdlib:multibond/FixedTransform2D",
    "stdlib:multibond/GravityPlanar",
    "stdlib:multibond/GroundPlanar",
    "stdlib:multibond/GYPlanar",
    "stdlib:multibond/IPlanar",
    "stdlib:multibond/JointTransform2D",
    "stdlib:multibond/MGYPlanar",
    "stdlib:multibond/MSePlanar",
    "stdlib:multibond/MSfPlanar",
    "stdlib:multibond/MTFPlanar",
    "stdlib:multibond/MTFPlanarMat",
    "stdlib:multibond/Revolute2D",
    "stdlib:multibond/RPlanar",
    "stdlib:multibond/ScrewTF",
    "stdlib:multibond/SePlanar",
    "stdlib:multibond/SfPlanar",
    "stdlib:multibond/TFAd",
    "stdlib:multibond/TFAdNeutral",
    "stdlib:multibond/TFPlanar",
    "stdlib:multibond/TFPlanarMat",
    # J-MB8: the spatial primitives with Power{Spatial} (D = 6).
    "stdlib:multibond/ComposePose3D",
    "stdlib:multibond/CoriolisSpatial",
    "stdlib:multibond/CSpatial",
    "stdlib:multibond/DeSpatial",
    "stdlib:multibond/DfSpatial",
    "stdlib:multibond/ExternalWrenchSpatial",
    "stdlib:multibond/FixedTransform3D",
    "stdlib:multibond/FixedTransform3DNeutral",
    "stdlib:multibond/GYSpatial",
    "stdlib:multibond/GravitySpatial",
    "stdlib:multibond/GroundSpatial",
    "stdlib:multibond/ISpatial",
    "stdlib:multibond/JointTransform3D",
    "stdlib:multibond/MGYSpatial",
    "stdlib:multibond/MTFSpatial",
    "stdlib:multibond/PoseIntegrator3D",
    "stdlib:multibond/RSpatial",
    "stdlib:multibond/SeSpatial",
    "stdlib:multibond/SfSpatial",
    "stdlib:multibond/TFSpatial",
    "stdlib:multibond/TFSpatialMat",
]

# Every stdlib block the library must hold: the M1 set plus the M2 rows that have landed.
# Sorted, because `load_stdlib` sorts its blocks by ref.
const M3_PLANAR_REFS = [
    "stdlib:planar/FixedJoint2D",
    "stdlib:planar/Free2D",
    "stdlib:planar/JointPose2D",
    "stdlib:planar/LocalPose2D",
    "stdlib:planar/PoseIntegrator2D",
    "stdlib:planar/Prismatic2D",
    "stdlib:planar/Revolute2DCompliant",
    "stdlib:planar/Revolute2DFriction",
    "stdlib:planar/Revolute2DLimit",
    "stdlib:planar/Revolute2DRigid",
    "stdlib:planar/RigidBody2D",
]

# The M3 spatial composites of J-MB9 (plan 6, row J-MB9): bodies, joints and pose helpers in
# the new `spatial` group.
const M3_SPATIAL_REFS = [
    "stdlib:spatial/Cylindrical3D",
    "stdlib:spatial/Free3D",
    "stdlib:spatial/Helical3D",
    "stdlib:spatial/LocalPose3D",
    "stdlib:spatial/Planar3D",
    "stdlib:spatial/Prismatic3D",
    "stdlib:spatial/Prismatic3DCompliant",
    "stdlib:spatial/Prismatic3DFriction",
    "stdlib:spatial/Prismatic3DLimit",
    "stdlib:spatial/Revolute3D",
    "stdlib:spatial/Revolute3DCompliant",
    "stdlib:spatial/Revolute3DFriction",
    "stdlib:spatial/Revolute3DRigid",
    "stdlib:spatial/Revolute3DLimit",
    "stdlib:spatial/RigidBody3D",
    "stdlib:spatial/Rotor3D",
    "stdlib:spatial/Spherical3D",
    "stdlib:spatial/Universal3D",
]

# The M3 contact elements of J-MB13 (plane surface and compliant contact point).
const M3_CONTACT_REFS = [
    "stdlib:contact/ContactPoint",
    "stdlib:contact/ContactSurface",
    "stdlib:contact/ImpactBody3D",
    "stdlib:contact/ImpactInertia3D",
    "stdlib:contact/MovingPlaneContact",
    "stdlib:contact/RollingDisk",
    "stdlib:contact/RollingSphere",
    "stdlib:contact/SwitchedPivot3D",
    "stdlib:contact/TerrainSurface",
    "stdlib:contact/Tyre",
    "stdlib:contact/SuctionCup",
    "stdlib:contact/VacuumGenerator",
]

# The M3 drives of J-MB11 (plan 6, row J-MB11): composites in the new `drives` group.
const M3_DRIVES_REFS = [
    "stdlib:drives/CurrentControlledDrive",
    "stdlib:drives/ElectricDrive",
    "stdlib:drives/Gearbox",
    "stdlib:drives/ReactionWheel",
]

# F5.1: the CSV input sources and the vector element selector that splits their columns.
const F5_CSV_REFS = [
    "stdlib:continuous/Select",
    "stdlib:sources/CsvSource",
    "stdlib:sources/CsvSourceSampled",
]

# J-EX9: the delay blocks on the discrete `delay` intrinsic.
const JEX9_REFS = ["stdlib:continuous/TransportDelay", "stdlib:discrete/IntegerDelay"]

# The common signal sources added on top of the M2 rows (Modelica.Blocks.Sources set).
const SIGNAL_SOURCE_REFS = [
    "stdlib:sources/BandLimitedWhiteNoise",
    "stdlib:sources/ExpSine",
    "stdlib:sources/Exponentials",
    "stdlib:sources/MultiSine",
    "stdlib:sources/PRBS",
    "stdlib:sources/RandomWalk",
    "stdlib:sources/RepeatingTable",
    "stdlib:sources/Sawtooth",
    "stdlib:sources/Trapezoid",
    "stdlib:sources/Triangle",
    "stdlib:sources/UniformNoise",
]

# Motion profiles (setpoint generators) and drive electronics: the `motion` group.
const MOTION_REFS = [
    "stdlib:motion/ADC",
    "stdlib:motion/CycloidalProfile",
    "stdlib:motion/DAC",
    "stdlib:motion/Encoder",
    "stdlib:motion/HarmonicProfile",
    "stdlib:motion/HBridge",
    "stdlib:motion/PolynomialProfile",
    "stdlib:motion/PowerAmplifier",
    "stdlib:motion/PWM",
    "stdlib:motion/PWMAverage",
    "stdlib:motion/SCurveProfile",
    "stdlib:motion/TrapezoidalProfile",
]

# The Thermal domain (pseudo bond graph: temperature and heat flow) and its couplings.
const THERMAL_REFS = [
    "stdlib:bondgraph/RS",
    "stdlib:thermal/BodyRadiation",
    "stdlib:thermal/Convection",
    "stdlib:thermal/DCMotorThermal",
    "stdlib:thermal/FixedHeatFlow",
    "stdlib:thermal/FixedTemperature",
    "stdlib:thermal/HeatCapacitor",
    "stdlib:thermal/HeatFlowSensor",
    "stdlib:thermal/PrescribedHeatFlow",
    "stdlib:thermal/PrescribedTemperature",
    "stdlib:thermal/ResistorHeated",
    "stdlib:thermal/TemperatureSensor",
    "stdlib:thermal/ThermalConductor",
    "stdlib:thermal/ThermalResistor",
    "stdlib:thermal/VariableConvection",
]

# The common 1D mechanical (rotation) and electrical components (20-sim / Simscape
# Foundation level).
const MECH_ELEC_REFS = [
    "stdlib:electrical/Battery",
    "stdlib:electrical/CCCS",
    "stdlib:electrical/CCVS",
    "stdlib:electrical/IGBT",
    "stdlib:electrical/MOSFET",
    "stdlib:electrical/MutualInductance",
    "stdlib:electrical/OpAmp",
    "stdlib:electrical/VCCS",
    "stdlib:electrical/VCVS",
    "stdlib:rotation/BeltDrive",
    "stdlib:rotation/Brake",
    "stdlib:rotation/Clutch",
    "stdlib:rotation/PlanetaryGear",
    "stdlib:rotation/RotationalHardStop",
    "stdlib:rotation/WormGear",
]

# The common hydraulic components (20-sim / Simscape level): valves, accumulator, pipe in
# the hydraulic group, pumps and motor with the converters.
const HYDRAULIC_REFS = [
    "stdlib:converters/FixedDisplacementPump",
    "stdlib:converters/HydraulicMotor",
    "stdlib:converters/VariableDisplacementPump",
    "stdlib:hydraulic/Accumulator",
    "stdlib:hydraulic/CheckValve",
    "stdlib:hydraulic/DirectionalValve43",
    "stdlib:hydraulic/Pipe",
    "stdlib:hydraulic/PressureCompensatedFlowControl",
    "stdlib:hydraulic/PressureReliefValve",
]

# The signal and control blocks (Simulink / 20-sim set): linear systems, filters, routing,
# nonlinearities, simulation control and observers.
const SIGNAL_CONTROL_REFS = [
    "stdlib:continuous/Backlash",
    "stdlib:continuous/BandPass",
    "stdlib:continuous/Demux2",
    "stdlib:continuous/Demux3",
    "stdlib:continuous/Demux4",
    "stdlib:continuous/HitCrossing",
    "stdlib:continuous/LowPassBessel",
    "stdlib:continuous/LowPassButterworth",
    "stdlib:continuous/Luenberger",
    "stdlib:continuous/MultiportSwitch",
    "stdlib:continuous/Mux2",
    "stdlib:continuous/Mux3",
    "stdlib:continuous/Mux4",
    "stdlib:continuous/Notch",
    "stdlib:continuous/Polynomial",
    "stdlib:continuous/Rounding",
    "stdlib:continuous/TransferFunction",
    "stdlib:continuous/VariableTransportDelay",
    "stdlib:continuous/WrapToPi",
    "stdlib:continuous/ZeroPole",
    "stdlib:discrete/DiscreteDerivative",
    "stdlib:discrete/KalmanFilter",
    "stdlib:discrete/Memory",
    "stdlib:sources/Assertion",
    "stdlib:sources/StopSimulation",
]

# Electromechanical field converters (the maglev example): the variable-reluctance
# electromagnet, a two-port IC-field between the coil and the gap.
const EM_FIELD_REFS = [
    "stdlib:converters/Electromagnet",
]

# Flexible bodies: the assumed-modes beams (planar and spatial composites and their atomic
# modal cores; mode shapes in `src/mech/modes.jl`).
const FLEX_REFS = [
    "stdlib:planar/FlexibleBeam2D",
    "stdlib:planar/ModalBeam2D",
    "stdlib:spatial/FlexibleBeam3D",
    "stdlib:spatial/ModalBeam3D",
    "stdlib:spatial/ModalBody3D",
    "stdlib:spatial/ModalBodyCore3D",
    "stdlib:spatial/ModalStress3D",
]

# Trusses: pin nodes, bars with member failure, the one-block truss and its deck loads (the
# bridge example).
const TRUSS_REFS = [
    "stdlib:planar/AxialBar2D",
    "stdlib:planar/Bar2D",
    "stdlib:planar/DeckContact2D",
    "stdlib:planar/MovingLoad2D",
    "stdlib:planar/PinNode2D",
    "stdlib:planar/PointMass2D",
    "stdlib:planar/Truss2D",
]

# Load sensing (the excavator example): the LS pump with its pressure cut-off and torque
# limiter.
const LS_REFS = ["stdlib:converters/LoadSensingPump"]

const ALL_REFS = sort(vcat(M1_REFS, M2_REFS, M3_REFS, M3_PLANAR_REFS, M3_SPATIAL_REFS, M3_CONTACT_REFS, M3_DRIVES_REFS, F5_CSV_REFS, JEX9_REFS, SIGNAL_SOURCE_REFS, MOTION_REFS, THERMAL_REFS, MECH_ELEC_REFS, HYDRAULIC_REFS, SIGNAL_CONTROL_REFS, EM_FIELD_REFS, FLEX_REFS, TRUSS_REFS, LS_REFS))

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

function _check_object_keys(entry, def; optional = String[])
    e = _plain(entry)
    properties = _schema_keys(def.properties)
    # No unknown keys; every property except the explicitly optional ones is present.
    @test Set(keys(e)) ⊆ properties
    @test setdiff(properties, Set(optional)) ⊆ Set(keys(e))
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
              ["t_start", "slope", "initial", "duration"]
        @test [p.unit for p in ramp.interface.parameters] == ["s", "1/s", nothing, "s"]
        @test ramp.interface.parameters[4].default == "1.0e12"
        @test isempty(ramp.interface.constants)
        @test isempty(ramp.interface.inputs)

        pulse = blocks["stdlib:sources/Pulse"]
        @test [p.name for p in pulse.interface.parameters] ==
              ["amplitude", "period", "duty", "t_start", "offset"]
        @test pulse.interface.parameters[2].unit == "s"
        @test pulse.interface.parameters[3].min == 0
        @test pulse.interface.parameters[3].max == 1
        @test pulse.interface.parameters[4].unit == "s"

        chirp = blocks["stdlib:sources/Chirp"]
        @test [p.name for p in chirp.interface.parameters] ==
              ["f_start", "f_end", "duration", "amplitude", "offset", "start_phase", "method"]
        @test [p.unit for p in chirp.interface.parameters] ==
              ["Hz", "Hz", "s", nothing, nothing, "rad", nothing]
        @test chirp.interface.parameters[7].options == ["linear", "log"]

        time = blocks["stdlib:sources/Time"]
        @test time.interface.outputs[1].unit == "s"
        @test isempty(time.interface.parameters)
        @test isempty(time.interface.constants)

        noise = blocks["stdlib:sources/Noise"]
        # J-EX9: the sample time is a constant (it fixes the discrete clock, like every
        # discrete block's sample_period);
        # the seed stays an Int parameter.
        @test [p.name for p in noise.interface.parameters] == ["mean", "std", "seed"]
        @test noise.interface.parameters[3].type == "Int"
        @test [(c.name, c.type, c.default) for c in noise.interface.constants] ==
              [("sample_time", "Real", 1.0e-3)]
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

    @testset "motion profiles and drive electronics" begin
        # The interfaces the editor, the spec table and the manual show; the golden tests
        # (test/golden/motion) check the behaviour.
        blocks = Dict(b.ref => b for b in load_stdlib())
        b(name) = blocks["stdlib:motion/" * name]
        params(name) = [p.name for p in b(name).interface.parameters]
        outs(name) = [(o.name, o.type) for o in b(name).interface.outputs]
        ins(name) = [i.name for i in b(name).interface.inputs]
        for ref in MOTION_REFS
            @test isempty(blocks[ref].diagnostics)
            @test group_info("motion").name == blocks[ref].group
        end
        @test group_info("motion").name == "Motion and drive electronics"
        for name in ("TrapezoidalProfile", "SCurveProfile", "CycloidalProfile",
                     "PolynomialProfile", "HarmonicProfile")
            @test isempty(ins(name))
            @test isempty(b(name).interface.ports)
            @test params(name)[1:3] == ["q_start", "q_end", "t_start"]
            @test only(p for p in b(name).interface.parameters if p.name == "t_start").unit == "s"
        end
        @test params("TrapezoidalProfile") == ["q_start", "q_end", "t_start", "v_max", "a_max"]
        @test params("SCurveProfile") == ["q_start", "q_end", "t_start", "v_max", "a_max", "j_max"]
        for name in ("CycloidalProfile", "PolynomialProfile", "HarmonicProfile")
            @test params(name) == ["q_start", "q_end", "t_start", "duration"]
        end
        @test outs("TrapezoidalProfile") == [("q", "Real"), ("v", "Real"), ("a", "Real")]
        @test outs("HarmonicProfile") == [("q", "Real"), ("v", "Real"), ("a", "Real")]
        for name in ("SCurveProfile", "CycloidalProfile", "PolynomialProfile")
            @test outs(name) == [("q", "Real"), ("v", "Real"), ("a", "Real"), ("jerk", "Real")]
        end
        @test params("PWM") == ["frequency", "high", "low", "t_start"]
        @test b("PWM").interface.parameters[1].unit == "Hz"
        @test params("PWMAverage") == ["high", "low"]
        @test ins("PWM") == ins("PWMAverage") == ["u"]
        # The sampled converters: a structural clock, integer resolution parameters.
        for name in ("Encoder", "ADC", "DAC")
            @test [(c.name, c.structural) for c in b(name).interface.constants] ==
                  [("sample_period", true)]
        end
        @test params("Encoder") == ["cpr"]
        @test b("Encoder").interface.parameters[1].type == "Int"
        @test outs("Encoder") == [("counts", "Real"), ("y", "Real"), ("index", "Bool")]
        @test params("ADC") == ["bits", "u_min", "u_max"]
        @test outs("ADC") == [("y", "Real"), ("code", "Real")]
        @test params("DAC") == ["bits", "y_min", "y_max", "input"]
        @test b("DAC").interface.parameters[4].options == ["value", "code"]
        # The power electronics: electrical ports, a command input, current taps.
        @test [(p.name, p.domain) for p in b("PowerAmplifier").interface.ports] ==
              [("p", "Electrical"), ("n", "Electrical")]
        @test params("PowerAmplifier") == ["gain", "V_max", "R_out", "I_max", "R_limit"]
        @test [(p.name, p.domain) for p in b("HBridge").interface.ports] ==
              [("dc_p", "Electrical"), ("dc_n", "Electrical"), ("out_p", "Electrical"),
               ("out_n", "Electrical")]
        @test ins("HBridge") == ["duty"]
        @test params("HBridge") == ["R_on", "I_max", "R_limit"]
    end

    @testset "the common signal sources" begin
        # Sawtooth, Triangle, Trapezoid, MultiSine, ExpSine, Exponentials, RepeatingTable:
        # one real output `y`, no inputs or ports, and the parameter lists the editor shows.
        # The golden tests (test/golden/sources) check the waveforms.
        blocks = Dict(b.ref => b for b in load_stdlib())
        for ref in SIGNAL_SOURCE_REFS
            b = blocks[ref]
            @test isempty(b.diagnostics)
            @test !isempty(b.description)
            @test !isempty(b.icon)
            @test isempty(b.interface.ports)
            @test isempty(b.interface.inputs)
            @test [(o.name, o.type, o.size) for o in b.interface.outputs] ==
                  [("y", "Real", Int[])]
        end
        params(name) = [p.name for p in blocks["stdlib:sources/" * name].interface.parameters]
        @test params("Sawtooth") == ["amplitude", "period", "offset", "t_start"]
        @test params("Triangle") == ["amplitude", "period", "offset", "t_start"]
        @test params("Trapezoid") == ["amplitude", "rising", "width", "falling", "period",
            "n_periods", "offset", "t_start"]
        @test params("MultiSine") == ["amplitudes", "frequencies", "phases", "offset", "t_start"]
        @test params("ExpSine") == ["amplitude", "frequency", "phase", "damping", "offset", "t_start"]
        @test params("Sine") == ["amplitude", "frequency", "phase", "offset", "t_start"]
        @test only(p for p in blocks["stdlib:sources/Sine"].interface.parameters
                   if p.name == "t_start").unit == "s"
        @test params("Exponentials") == ["amplitude", "rise_time", "tau_rise", "tau_fall",
            "offset", "t_start"]
        @test params("RepeatingTable") == ["t_start", "sample_time", "values", "method"]
        # The random sources: an explicit integer seed and a structural sample_time clock.
        @test params("UniformNoise") == ["y_min", "y_max", "seed"]
        @test params("BandLimitedWhiteNoise") == ["noise_power", "seed"]
        @test params("PRBS") == ["amplitude", "offset", "bit_ticks", "seed"]
        @test params("RandomWalk") == ["step_std", "initial", "seed"]
        for name in ("Noise", "UniformNoise", "BandLimitedWhiteNoise", "PRBS", "RandomWalk")
            b = blocks["stdlib:sources/" * name]
            seed = only(p for p in b.interface.parameters if p.name == "seed")
            @test seed.type == "Int"
            @test [(c.name, c.structural) for c in b.interface.constants] == [("sample_time", true)]
        end

        trapezoid = blocks["stdlib:sources/Trapezoid"]
        @test trapezoid.interface.parameters[6].type == "Int"
        @test trapezoid.interface.parameters[6].default == "-1"
        @test all(trapezoid.interface.parameters[i].min == 0 for i in 2:4)
        @test trapezoid.interface.parameters[5].min == 1.0e-12
        # Angular frequencies in rad/s, as in Sine (Chirp alone uses Hz).
        @test blocks["stdlib:sources/ExpSine"].interface.parameters[2].unit == "rad/s"
        @test blocks["stdlib:sources/MultiSine"].interface.parameters[2].unit == "rad/s"
        @test blocks["stdlib:sources/Sine"].interface.parameters[2].unit == "rad/s"
        @test [(c.name, c.default) for c in blocks["stdlib:sources/MultiSine"].interface.constants] ==
              [("N", 3)]
        table = blocks["stdlib:sources/RepeatingTable"]
        @test [(c.name, c.default) for c in table.interface.constants] == [("N", 8)]
        @test table.interface.parameters[4].options == ["hold", "linear"]
    end

    @testset "the signal and control blocks" begin
        # Clean blocks with a description, an icon and a described parameter each; the
        # golden tests (test/golden/{continuous,discrete,sources}) check the responses.
        blocks = Dict(b.ref => b for b in load_stdlib())
        for ref in SIGNAL_CONTROL_REFS
            b = blocks[ref]
            @test isempty(b.diagnostics)
            @test !isempty(b.description)
            @test !isempty(b.icon)
            @test all(p -> !isempty(something(p.description, "")), b.interface.parameters)
        end
        params(ref) = [p.name for p in blocks["stdlib:" * ref].interface.parameters]
        consts(ref) = [(c.name, c.default) for c in blocks["stdlib:" * ref].interface.constants]
        @test params("continuous/TransferFunction") == ["num", "den"]
        @test consts("continuous/TransferFunction") == [("n", 2), ("m", 2)]
        @test params("continuous/ZeroPole") == ["gain", "zero_re", "zero_im", "pole_re", "pole_im"]
        @test consts("continuous/ZeroPole") == [("n", 2), ("m", 1)]
        for f in ("LowPassButterworth", "LowPassBessel")
            b = blocks["stdlib:continuous/" * f]
            @test params("continuous/" * f) == ["k", "wc"]
            @test b.interface.parameters[2].unit == "rad/s"
            @test consts("continuous/" * f) == [("n", 2)]
        end
        @test params("continuous/Notch") == ["k", "w0", "bandwidth", "depth"]
        @test params("continuous/BandPass") == ["k", "w0", "bandwidth"]
        @test blocks["stdlib:continuous/Rounding"].interface.parameters[1].options ==
              ["floor", "ceil", "round", "fix"]
        @test blocks["stdlib:continuous/HitCrossing"].interface.parameters[2].options ==
              ["either", "rising", "falling"]
        for n in 2:4
            mux = blocks["stdlib:continuous/Mux$n"]
            @test [i.name for i in mux.interface.inputs] == ["u$i" for i in 1:n]
            @test only(mux.interface.outputs).size == [n]
            demux = blocks["stdlib:continuous/Demux$n"]
            @test only(demux.interface.inputs).size == [n]
            @test [o.name for o in demux.interface.outputs] == ["y$i" for i in 1:n]
        end
        @test [i.name for i in blocks["stdlib:continuous/VariableTransportDelay"].interface.inputs] == ["u", "d"]
        @test params("sources/StopSimulation") == ["threshold"]
        @test params("sources/Assertion") == ["threshold"]
        @test params("discrete/KalmanFilter") == ["A", "B", "C", "D", "Q", "R"]
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
        # in the source), while a variable decl also carries the resolved `size` array. The
        # feedthrough D is a structural constant: D = 0 folds away (no algebraic loop).
        ss = blocks["stdlib:continuous/StateSpace"]
        @test [(c.name, c.type, c.default) for c in ss.interface.constants] ==
              [("N", "Int", 2), ("D", "Real", 0.0)]
        @test [c.structural for c in ss.interface.constants] == [true, true]
        @test [p.name for p in ss.interface.parameters] == ["A", "B", "C"]
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

    @testset "the Thermal domain blocks" begin
        # Pseudo bond graph (spec, "Thermal convention"): e = temperature [K] is the across
        # variable, f = heat flow [W] into the element. Only RS and the heated components
        # touch another domain, and each sends its whole dissipated power to the heat port.
        blocks = Dict(b.ref => b for b in load_stdlib())
        for ref in THERMAL_REFS
            b = blocks[ref]
            @test !has_errors(b)
            @test !isempty(b.description)
            @test !isempty(b.icon)
            @test any(p -> p.domain == "Thermal", b.interface.ports)
            startswith(ref, "stdlib:thermal/") && @test b.group == "Thermal"
        end
        pure = ["BodyRadiation", "Convection", "FixedHeatFlow", "FixedTemperature",
            "HeatCapacitor", "HeatFlowSensor", "PrescribedHeatFlow", "PrescribedTemperature",
            "TemperatureSensor", "ThermalConductor", "ThermalResistor", "VariableConvection"]
        for name in pure
            @test all(p -> p.domain == "Thermal", blocks["stdlib:thermal/" * name].interface.ports)
        end

        hc = blocks["stdlib:thermal/HeatCapacitor"]
        @test [p.name for p in hc.interface.parameters] == ["C"]
        @test hc.interface.parameters[1].unit == "J/K"
        @test [(v.name, v.unit, v.state) for v in hc.interface.variables] ==
              [("T", "K", "prefer")]
        @test occursin("ddt(T) ~ a.f / C", hc.source)

        # Sources fix their variable (D6): temperature is effort, heat flow is flow.
        for name in ("FixedTemperature", "PrescribedTemperature")
            @test blocks["stdlib:thermal/" * name].interface.causality ==
                  [(ports = ["a"], kind = "fixed", value = "effort_out")]
        end
        for name in ("FixedHeatFlow", "PrescribedHeatFlow", "TemperatureSensor")
            @test blocks["stdlib:thermal/" * name].interface.causality ==
                  [(ports = ["a"], kind = "fixed", value = "flow_out")]
        end
        @test [(i.name, i.unit) for i in blocks["stdlib:thermal/PrescribedTemperature"].interface.inputs] ==
              [("T", "K")]
        @test [(i.name, i.unit) for i in blocks["stdlib:thermal/PrescribedHeatFlow"].interface.inputs] ==
              [("Q", "W")]
        @test [(o.name, o.unit) for o in blocks["stdlib:thermal/TemperatureSensor"].interface.outputs] ==
              [("y", "K")]
        @test [(o.name, o.unit) for o in blocks["stdlib:thermal/HeatFlowSensor"].interface.outputs] ==
              [("y", "W")]

        rad = blocks["stdlib:thermal/BodyRadiation"]
        @test [c.name for c in rad.interface.constants] == ["sigma"]
        @test occursin("(a.e^4 - b.e^4)", rad.source)

        # RS: a Generic resistive port plus a Thermal heat port; the block is Generic for
        # adoption (r in effort/flow) and sends p.e*p.f to the heat port.
        rs = blocks["stdlib:bondgraph/RS"]
        @test [(p.name, p.domain) for p in rs.interface.ports] ==
              [("p", "Generic"), ("heat", "Thermal")]
        @test rs.interface.parameters[1].unit == "effort/flow"
        @test BGSim.Units.block_domain(rs.ast) === :Generic
        @test occursin("heat.f ~ -P", rs.source)

        rh = blocks["stdlib:thermal/ResistorHeated"]
        @test [(p.name, p.domain) for p in rh.interface.ports] ==
              [("p", "Electrical"), ("n", "Electrical"), ("heat", "Thermal")]
        @test [p.name for p in rh.interface.parameters] == ["R0", "T0", "alpha"]
        @test occursin("R ~ R0 * (1.0 + alpha * (heat.e - T0))", rh.source)

        motor = blocks["stdlib:thermal/DCMotorThermal"]
        @test [(p.name, p.domain) for p in motor.interface.ports] ==
              [("p", "Electrical"), ("n", "Electrical"), ("shaft", "Rotation"),
                  ("housing", "Rotation"), ("winding", "Thermal")]
        @test component_block.(components(motor.ast)) ==
              [:ResistorHeated, :Inductor, :EMConverter, :Inertia, :RotationalDamper]
    end

    @testset "the common rotation and electrical components" begin
        # The golden tests (test/golden/rotation, test/golden/electrical) check the
        # equations, power balance and dissipation; this pins the interfaces.
        blocks = Dict(b.ref => b for b in load_stdlib())
        for ref in MECH_ELEC_REFS
            b = blocks[ref]
            group, domain = startswith(ref, "stdlib:rotation/") ?
                            ("Rotation", "Rotation") : ("Electrical", "Electrical")
            @test !isempty(b.description)
            @test !isempty(b.icon)
            @test b.group == group
            @test all(p -> p.domain == domain, b.interface.ports)
            @test all(p -> p.description !== nothing && !isempty(p.description),
                b.interface.parameters)
        end
        ports(ref) = [p.name for p in blocks[ref].interface.ports]
        params(ref) = [(p.name, p.unit) for p in blocks[ref].interface.parameters]
        inputs(ref) = [(i.name, i.type) for i in blocks[ref].interface.inputs]

        @test ports("stdlib:rotation/RotationalHardStop") == ["a", "b"]
        @test params("stdlib:rotation/RotationalHardStop") ==
              [("lower", "rad"), ("upper", "rad"), ("k", "N*m/rad"), ("d", "N*m*s/rad")]
        @test ports("stdlib:rotation/Clutch") == ["a", "b"]
        @test inputs("stdlib:rotation/Clutch") == [("f_n", "Real")]
        @test blocks["stdlib:rotation/Clutch"].interface.inputs[1].unit == "N"
        @test ports("stdlib:rotation/Brake") == ["a"]
        @test inputs("stdlib:rotation/Brake") == [("f_n", "Real")]
        @test [p.name for p in blocks["stdlib:rotation/Brake"].interface.parameters] ==
              [p.name for p in blocks["stdlib:rotation/Clutch"].interface.parameters]
        @test ports("stdlib:rotation/PlanetaryGear") == ["sun", "ring", "carrier"]
        @test params("stdlib:rotation/PlanetaryGear") == [("ratio", "1")]
        @test ports("stdlib:rotation/BeltDrive") == ["a", "b"]
        @test params("stdlib:rotation/BeltDrive") ==
              [("r_a", "m"), ("r_b", "m"), ("k", "N/m"), ("d", "N*s/m")]
        @test [(v.name, v.state) for v in blocks["stdlib:rotation/BeltDrive"].interface.variables] ==
              [("x", "prefer"), ("F", nothing)]
        @test params("stdlib:rotation/WormGear") ==
              [("n", "1"), ("eta", "1"), ("eta_back", "1"), ("w_eps", "rad/s")]
        @test blocks["stdlib:rotation/WormGear"].interface.causality ==
              [(ports = ["a", "b"], kind = "transformer", value = nothing)]

        @test ports("stdlib:electrical/OpAmp") == ["in_p", "in_n", "out"]
        @test [c.name for c in blocks["stdlib:electrical/OpAmp"].interface.constants] == ["ideal"]
        @test params("stdlib:electrical/OpAmp") ==
              [("A", "1"), ("T_o", "s"), ("V_pos", "V"), ("V_neg", "V")]
        for (name, param, unit) in (("VCVS", "gain", "1"), ("VCCS", "transconductance", "1/Ohm"),
            ("CCVS", "transresistance", "Ohm"), ("CCCS", "gain", "1"))
            ref = "stdlib:electrical/" * name
            @test ports(ref) == ["p1", "n1", "p2", "n2"]
            @test params(ref) == [(param, unit)]
            @test isempty(blocks[ref].interface.variables)
        end
        @test ports("stdlib:electrical/MutualInductance") == ["p1", "n1", "p2", "n2"]
        @test params("stdlib:electrical/MutualInductance") == [("L1", "H"), ("L2", "H"), ("k", "1")]
        @test [(v.name, v.state) for v in blocks["stdlib:electrical/MutualInductance"].interface.variables] ==
              [("i1", "prefer"), ("i2", "prefer")]
        @test ports("stdlib:electrical/Battery") == ["p", "n"]
        @test [p.name for p in blocks["stdlib:electrical/Battery"].interface.parameters] ==
              ["capacity", "soc_table", "ocv_table", "R0", "R1", "C1"]
        @test blocks["stdlib:electrical/Battery"].interface.parameters[1].unit == "A*h"
        @test [(v.name, v.state) for v in blocks["stdlib:electrical/Battery"].interface.variables] ==
              [("soc", "prefer"), ("v1", "prefer"), ("ocv", nothing)]
        @test ports("stdlib:electrical/MOSFET") == ["d", "s"]
        @test inputs("stdlib:electrical/MOSFET") == [("gate", "Bool")]
        @test ports("stdlib:electrical/IGBT") == ["c", "e"]
        @test inputs("stdlib:electrical/IGBT") == [("gate", "Bool")]
        @test [p.name for p in blocks["stdlib:electrical/IGBT"].interface.parameters] ==
              ["R_on", "V_ce0", "G_off", "V_f", "R_d"]
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

    @testset "the hydraulic components (valves, accumulator, pipe, pumps, motor)" begin
        blocks = Dict(b.ref => b for b in load_stdlib())
        ports(b) = [(p.name, p.domain, p.size) for p in b.interface.ports]
        params(b) = [(p.name, p.unit) for p in b.interface.parameters]
        for ref in HYDRAULIC_REFS
            b = blocks[ref]
            @test !isempty(b.description)
            @test startswith(b.icon, startswith(ref, "stdlib:hydraulic/") ? "hyd-" : "conv-")
            # No switching event anywhere: the laws are smooth (no ifelse, abs or sign),
            # so the blocks also run in fixed-step export without W203.
            @test !occursin("ifelse", b.source)
            @test !occursin("abs(", b.source)
            @test !occursin("sign(", b.source)
            # Isothermal, R/C/I elements without a declared causality.
            @test isempty(b.interface.causality)
        end
        two = [("a", "Hydraulic", Int[]), ("b", "Hydraulic", Int[])]
        for name in ("CheckValve", "PressureReliefValve", "Pipe",
            "PressureCompensatedFlowControl")
            @test ports(blocks["stdlib:hydraulic/" * name]) == two
        end
        @test params(blocks["stdlib:hydraulic/CheckValve"]) ==
              [("p_crack", "Pa"), ("dp_open", "Pa"), ("A_max", "m^2"), ("A_leak", "m^2"),
                  ("Cd", "1"), ("rho", "kg/m^3"), ("p_tr", "Pa")]
        @test params(blocks["stdlib:hydraulic/PressureReliefValve"]) ==
              [("p_set", "Pa"), ("dp_reg", "Pa"), ("A_max", "m^2"), ("A_leak", "m^2"),
                  ("Cd", "1"), ("rho", "kg/m^3"), ("p_tr", "Pa")]
        dv = blocks["stdlib:hydraulic/DirectionalValve43"]
        @test ports(dv) == [(n, "Hydraulic", Int[]) for n in ("P", "T", "A", "B")]
        @test [(i.name, i.type) for i in dv.interface.inputs] == [("u", "Real")]
        @test [p.name for p in dv.interface.parameters] ==
              ["A_max", "A_leak", "lap", "Cd", "rho", "p_tr"]
        lap = dv.interface.parameters[3]
        @test (lap.min, lap.max) == (-0.9, 0.9)
        acc = blocks["stdlib:hydraulic/Accumulator"]
        @test ports(acc) == [("a", "Hydraulic", Int[])]
        @test params(acc) == [("p0", "Pa"), ("V0", "m^3"), ("n", "1"), ("V_dead", "m^3"),
            ("beta", "Pa"), ("p_tr", "Pa")]
        @test [(v.name, v.state) for v in acc.interface.variables if v.state !== nothing] ==
              [("V_f", "prefer")]
        pipe = blocks["stdlib:hydraulic/Pipe"]
        @test [(c.name, c.default) for c in pipe.interface.constants] == [("N", 1)]
        @test params(pipe) == [("L", "m"), ("d", "m"), ("rho", "kg/m^3"), ("nu", "m^2/s"),
            ("beta", "Pa"), ("f_t", "1")]
        for name in ("FixedDisplacementPump", "VariableDisplacementPump", "HydraulicMotor")
            b = blocks["stdlib:converters/" * name]
            @test ports(b) == [("a", "Hydraulic", Int[]), ("b", "Hydraulic", Int[]),
                ("shaft", "Rotation", Int[])]
            @test params(b) == [("D", "m^3/rad"), ("eta_v", "1"), ("eta_m", "1"),
                ("p_nom", "Pa"), ("w_nom", "rad/s"), ("p_tr", "Pa"), ("w_tr", "rad/s")]
            @test [v.name for v in b.interface.variables] == ["w", "dp", "Q", "T", "P_loss"]
            @test isempty(b.interface.inputs) == (name != "VariableDisplacementPump")
        end
    end

    @testset "the load-sensing pump" begin
        b = Dict(b.ref => b for b in load_stdlib())["stdlib:converters/LoadSensingPump"]
        @test b.icon == "conv-ls-pump"
        @test [(p.name, p.domain) for p in b.interface.ports] ==
              [("a", "Hydraulic"), ("b", "Hydraulic"), ("shaft", "Rotation"), ("ls", "Hydraulic")]
        @test isempty(b.interface.inputs)
        @test [o.name for o in b.interface.outputs] == ["xd", "P_in", "P_out"]
        @test [p.name for p in b.interface.parameters] ==
              ["D", "eta_v", "eta_m", "p_nom", "w_nom", "dp_ls", "dp_reg", "p_cut", "T_max", "p_tr", "w_tr"]
        # Smooth laws only: no switching event, so the block also runs in fixed-step export.
        @test !occursin("ifelse", b.source)
        @test !occursin("abs(", b.source)
        @test !occursin("sign(", b.source)
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
            "stdlib:converters/ExportInputPass",
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

        # J2.6b: the DCMotor is a composite with the flat block's interface, and no own
        # variables (its recorded `i`/`w_rel` are observables, not interface entries).
        dc = blocks["stdlib:converters/DCMotor"]
        @test [(p.name, p.domain, p.size) for p in dc.interface.ports] ==
              [("p", "Electrical", Int[]), ("n", "Electrical", Int[]),
                  ("shaft", "Rotation", Int[]), ("housing", "Rotation", Int[])]
        @test [p.name for p in dc.interface.parameters] == ["R", "L", "k_t", "J", "d"]
        @test [p.unit for p in dc.interface.parameters] ==
              ["Ohm", "H", "N*m/A", "kg*m^2", "N*m*s/rad"]
        @test isempty(dc.interface.variables)
        @test isempty(dc.interface.inputs)
        @test isempty(dc.interface.outputs)
        @test isempty(dc.interface.causality)
        @test occursin("@components", dc.source)
        @test dc.description ==
              "Permanent-magnet DC motor as a composite (winding, gyrator, rotor): electrical p and n, rotational shaft and housing."

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

        # Electromagnet: electrical p/n plus the translation stator a and armature b, a
        # two-port IC-field (states i and h) with preferred integral causality: the coil takes a
        # voltage and gives the current (flow out), the gap takes a velocity and gives the force.
        for ref in EM_FIELD_REFS
            b = blocks[ref]
            @test !isempty(b.description)
            @test b.icon == "conv-electromagnet"
            @test b.group == "Converters and sensors"
        end
        mag = blocks["stdlib:converters/Electromagnet"]
        @test [(p.name, p.domain) for p in mag.interface.ports] ==
              [("p", "Electrical"), ("n", "Electrical"), ("a", "Translation"), ("b", "Translation")]
        @test [(p.name, p.unit) for p in mag.interface.parameters] ==
              [("alpha", "H*m"), ("L_inf", "H"), ("h0", "m")]
        @test [(v.name, v.state) for v in mag.interface.variables if v.state !== nothing] ==
              [("i", "prefer"), ("h", "prefer")]
        @test isempty(mag.interface.inputs)
        @test mag.interface.causality == [
            (ports = ["p"], kind = "preferred", value = "flow_out"),
            (ports = ["n"], kind = "preferred", value = "flow_out"),
            (ports = ["a"], kind = "preferred", value = "effort_out"),
            (ports = ["b"], kind = "preferred", value = "effort_out"),
        ]
        @test occursin("F ~ alpha * i * i / ((h + h0) * (h + h0))", mag.source)

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
        # Transparent: the flow that enters at a leaves at b (port flows count inward).
        @test occursin("a.f + b.f ~ 0.0", pws.source)

        # An output that a `@discrete` body holds carries its start (the value before the
        # first tick, which a node may override); a computed output does not.
        let all_blocks = Dict(b.ref => b for b in load_stdlib())
            starts_of(ref) = [(o.name, get(o, :start, nothing))
                              for o in all_blocks[ref].interface.outputs]
            @test starts_of("stdlib:motion/ADC") == [("y", "0.0"), ("code", "0.0")]
            @test starts_of("stdlib:discrete/ZOH") == [("y", "0.0")]
            @test starts_of("stdlib:sources/Noise") == [("y", nothing)]
            @test starts_of("stdlib:continuous/Gain") == [("y", nothing)]
        end

        # Export markers: an input is a constant source in simulation, an output holds its
        # input, and a parameter publishes a tunable value. The spec's name/type/unit are
        # instance metadata, which the language has no parameter type for.
        ei = blocks["stdlib:converters/ExportInput"]
        @test isempty(ei.interface.ports)
        @test isempty(ei.interface.inputs)
        @test [(o.name, o.type) for o in ei.interface.outputs] == [("y", "Real")]
        @test [p.name for p in ei.interface.parameters] == ["value"]
        @test occursin("y ~ value", ei.source)

        # The pass-through input passes its wired signal in simulation; the export cuts the
        # wire and the host supplies `y` (its `value` is the start value).
        eip = blocks["stdlib:converters/ExportInputPass"]
        @test isempty(eip.interface.ports)
        @test [(i.name, i.type) for i in eip.interface.inputs] == [("u", "Real")]
        @test [(o.name, o.type) for o in eip.interface.outputs] == [("y", "Real")]
        @test [p.name for p in eip.interface.parameters] == ["value"]
        @test occursin("y ~ u", eip.source)

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

    @testset "the M3 multibond group (J-MB4)" begin
        # The first planar vector primitives (plan 6, J-MB4). The constitutive and power
        # tests live in `test_multibond_slice.jl`; here the catalog contract is pinned.
        blocks = Dict(b.ref => b for b in load_stdlib())
        for ref in M3_REFS
            b = blocks[ref]
            @test b.group == "Multibond"
            @test !isempty(b.description)
            @test !isempty(b.icon)
            @test isempty([d for d in b.diagnostics if d.severity == "error"])
            @test isempty([d for d in b.diagnostics if d.code in ("W204", "E103")])
        end
        # Every multibond block with a Planar port declares dimension 2 and one with a
        # Spatial port declares dimension 3; the signal-only pose blocks have no dimension.
        # Every multibond port carries a frame field (null means frame-neutral) and the
        # catalog emits it.
        for ref in M3_REFS
            b = blocks[ref]
            planar = any(p -> p.domain == "Planar", b.interface.ports)
            spatial = any(p -> p.domain == "Spatial", b.interface.ports)
            if planar
                @test b.interface.dimension == 2
            elseif spatial
                @test b.interface.dimension == 3
            else
                @test get(b.interface, :dimension, nothing) === nothing
            end
            for p in b.interface.ports
                @test haskey(p, :frame)
            end
        end
        @test [p.frame for p in blocks["stdlib:multibond/GroundPlanar"].interface.ports] ==
              ["world"]
        @test [p.frame for p in blocks["stdlib:multibond/IPlanar"].interface.ports] ==
              ["body"]
        @test [p.frame for p in blocks["stdlib:multibond/GravityPlanar"].interface.ports] ==
              ["body"]
        @test [p.frame for p in blocks["stdlib:multibond/FixedTransform2D"].interface.ports] ==
              ["world", "body"]
        # The joint's two body ports are frame-neutral so one instance joins any body frame
        # (D-MB5: null unifies); the drive is the scalar Rotation port.
        revolute = blocks["stdlib:multibond/Revolute2D"]
        @test [(p.name, p.domain, p.size, p.frame) for p in revolute.interface.ports] ==
              [("parent", "Planar", [3], nothing), ("child", "Planar", [3], nothing),
                  ("drive", "Rotation", Int[], nothing)]
        @test [(o.name, o.size) for o in revolute.interface.outputs] ==
              [("qout", Int[]), ("qdout", Int[]), ("pose", [3]), ("dout", [2]),
                  ("Vrelout", [3]), ("tau_stop", Int[])]
        @test [p.name for p in revolute.interface.parameters] ==
              ["rx", "ry", "kt", "bt", "q0", "k_stop", "d_stop", "w_stop"]

        # The J-MB5 full planar set: the one-port C/R sources and the two-port transformers
        # and gyrators. The physics tests live in `test_planar_primitives.jl`; here the
        # interface fields (the plan 3.2 contract) are pinned.
        c = blocks["stdlib:multibond/CPlanar"]
        @test [(p.name, p.domain, p.size, p.frame) for p in c.interface.ports] ==
              [("p", "Planar", [3], nothing)]
        @test [(v.name, v.size, v.unit) for v in c.interface.variables] ==
              [("qr", Int[], "rad"), ("qx", Int[], "m"), ("qy", Int[], "m")]
        @test [(p.name, p.unit) for p in c.interface.parameters] ==
              [("kr", "N*m/rad"), ("kx", "N/m"), ("ky", "N/m"), ("qr0", "rad"),
                  ("qx0", "m"), ("qy0", "m")]
        @test c.interface.causality ==
              [(ports = ["p"], kind = "preferred", value = "effort_out")]
        r = blocks["stdlib:multibond/RPlanar"]
        @test [(p.name, p.unit) for p in r.interface.parameters] ==
              [("br", "N*m*s/rad"), ("bx", "N*s/m"), ("by", "N*s/m")]
        @test isempty(r.interface.causality)              # free, like the scalar R
        mse = blocks["stdlib:multibond/MSePlanar"]
        @test [(i.name, i.type, i.unit) for i in mse.interface.inputs] ==
              [("ur", "Real", "N*m"), ("ux", "Real", "N"), ("uy", "Real", "N")]
        @test mse.interface.causality ==
              [(ports = ["p"], kind = "fixed", value = "effort_out")]
        msf = blocks["stdlib:multibond/MSfPlanar"]
        @test [(i.name, i.unit) for i in msf.interface.inputs] ==
              [("vr", "rad/s"), ("vx", "m/s"), ("vy", "m/s")]
        @test msf.interface.causality ==
              [(ports = ["p"], kind = "fixed", value = "flow_out")]
        ew = blocks["stdlib:multibond/ExternalWrenchPlanar"]
        @test [(i.name, i.unit) for i in ew.interface.inputs] ==
              [("wr", "N*m"), ("wx", "N"), ("wy", "N")]
        tf = blocks["stdlib:multibond/TFPlanar"]
        @test [(p.name, p.domain, p.size, p.frame) for p in tf.interface.ports] ==
              [("a", "Planar", [3], nothing), ("b", "Planar", [3], nothing)]
        @test [(p.name, p.unit, p.default) for p in tf.interface.parameters] ==
              [("n", "1", "[1.0, 1.0, 1.0]")]
        @test tf.interface.causality ==
              [(ports = ["a", "b"], kind = "transformer", value = nothing)]
        mtf = blocks["stdlib:multibond/MTFPlanar"]
        @test [(i.name, i.size, i.unit) for i in mtf.interface.inputs] ==
              [("u", [3], "1")]
        @test mtf.interface.causality ==
              [(ports = ["a", "b"], kind = "transformer", value = nothing)]
        # The matrix transformer is the general 3x3 form of the same element (FIX-MB-4): the
        # matrix carries no single unit (a Mat has one unit slot) and needs no inverse.
        tfm = blocks["stdlib:multibond/TFPlanarMat"]
        @test [(p.name, p.domain, p.size, p.frame) for p in tfm.interface.ports] ==
              [("a", "Planar", [3], nothing), ("b", "Planar", [3], nothing)]
        @test [(p.name, p.unit) for p in tfm.interface.parameters] == [("M", nothing)]
        @test count(==(';'), tfm.interface.parameters[1].default) == 2    # three rows
        @test tfm.interface.causality ==
              [(ports = ["a", "b"], kind = "transformer", value = nothing)]
        mtfm = blocks["stdlib:multibond/MTFPlanarMat"]
        @test [(i.name, i.size, i.unit) for i in mtfm.interface.inputs] == [("M", [3, 3], nothing)]
        @test mtfm.interface.causality ==
              [(ports = ["a", "b"], kind = "transformer", value = nothing)]
        # The frame-neutral adjoint used by the rigid joint composite: both ports null, so a
        # joint's parent role adopts either world or a body frame.
        tfn = blocks["stdlib:multibond/TFAdNeutral"]
        @test [p.frame for p in tfn.interface.ports] == [nothing, nothing]
        @test [(i.name, i.size) for i in tfn.interface.inputs] == [("g", [3])]
        @test tfn.interface.causality ==
              [(ports = ["a", "b"], kind = "transformer", value = nothing)]
        gy = blocks["stdlib:multibond/GYPlanar"]
        @test [(p.name, p.unit) for p in gy.interface.parameters] == [("G", nothing)]
        @test gy.interface.causality ==
              [(ports = ["a", "b"], kind = "gyrator", value = nothing)]
        mgy = blocks["stdlib:multibond/MGYPlanar"]
        @test [(i.name, i.size, i.unit) for i in mgy.interface.inputs] ==
              [("G", [3, 3], nothing)]
        @test mgy.interface.causality ==
              [(ports = ["a", "b"], kind = "gyrator", value = nothing)]
        # The joint-role transform declares the two joint frames, so it is the legal bridge.
        jt = blocks["stdlib:multibond/JointTransform2D"]
        @test [(p.name, p.domain, p.size, p.frame) for p in jt.interface.ports] ==
              [("a", "Planar", [3], "parent"), ("b", "Planar", [3], "child")]
        @test [(i.name, i.size) for i in jt.interface.inputs] == [("g", [3])]
    end

    @testset "the planar mechanics group (J-MB6)" begin
        blocks = Dict(b.ref => b for b in load_stdlib())
        for ref in M3_PLANAR_REFS
            b = blocks[ref]
            @test b.group == "Planar mechanics"
            @test !isempty(b.description)
            @test !isempty(b.icon)
            @test isempty(b.diagnostics)
            planar = any(p -> p.domain == "Planar", b.interface.ports)
            if planar
                @test b.interface.dimension == 2
            else
                @test get(b.interface, :dimension, nothing) === nothing
            end
            for p in b.interface.ports
                @test haskey(p, :frame)
            end
        end

        # The body's single port is its 1-junction, in the body frame (one port, D-MB4).
        body = blocks["stdlib:planar/RigidBody2D"]
        @test [(p.name, p.domain, p.size, p.frame) for p in body.interface.ports] ==
              [("p", "Planar", [3], "body")]
        @test [(i.name, i.size) for i in body.interface.inputs] == [("g", [3])]
        @test [o.name for o in body.interface.outputs] == ["V", "P"]
        @test [p.name for p in body.interface.parameters] == ["m", "J", "g0"]
        @test [BGSim.component_block(c) for c in BGSim.components(body.ast)] ==
              [:Junction, :IPlanar, :CoriolisPlanar, :GravityPlanar, :DfPlanar]

        # The fixed joint is the frame bridge into a body frame; its pose output feeds a
        # fixed-base chain.
        fixed = blocks["stdlib:planar/FixedJoint2D"]
        @test [(p.name, p.frame) for p in fixed.interface.ports] ==
              [("parent", nothing), ("child", "body")]
        @test [o.name for o in fixed.interface.outputs] == ["pose"]
        @test [p.name for p in fixed.interface.parameters] == ["x", "y", "theta"]
        @test fixed.interface.causality ==
              [(ports = ["parent", "child"], kind = "transformer", value = nothing)]

        # D-MB8: the drive domain follows the screw. A prismatic drive is a Translation port.
        @test [(p.name, p.domain, p.size) for p in
               blocks["stdlib:planar/Prismatic2D"].interface.ports] ==
              [("parent", "Planar", [3]), ("child", "Planar", [3]),
                  ("drive", "Translation", Int[])]
        @test [o.name for o in blocks["stdlib:planar/Prismatic2D"].interface.outputs] ==
              ["qout", "qdout", "pose", "drout", "dout", "Vrelout", "f_stop"]
        for ref in ("stdlib:planar/Revolute2DCompliant", "stdlib:planar/Revolute2DFriction",
            "stdlib:planar/Revolute2DLimit", "stdlib:planar/Revolute2DRigid")
            drive = only([p for p in blocks[ref].interface.ports if p.name == "drive"])
            @test drive.domain == "Rotation"
        end

        # The two signal-only pose blocks and the floating-base integrator.
        @test isempty(blocks["stdlib:planar/LocalPose2D"].interface.ports)
        @test [o.name for o in blocks["stdlib:planar/LocalPose2D"].interface.outputs] ==
              ["g"]
        @test [(i.name, i.unit) for i in
               blocks["stdlib:planar/JointPose2D"].interface.inputs] == [("q", "rad")]
        @test [(p.name, p.unit) for p in
               blocks["stdlib:planar/JointPose2D"].interface.parameters] ==
              [("rx", "m"), ("ry", "m"), ("theta0", "rad")]
        @test [(i.name, i.size) for i in
               blocks["stdlib:planar/PoseIntegrator2D"].interface.inputs] == [("tw", [3])]
        @test [(v.name, v.unit) for v in
               blocks["stdlib:planar/PoseIntegrator2D"].interface.variables] ==
              [("th", "rad"), ("xi", "m"), ("yi", "m")]
        @test [(p.name, p.unit) for p in
               blocks["stdlib:planar/PoseIntegrator2D"].interface.parameters] ==
              [("theta0", "rad"), ("x0", "m"), ("y0", "m")]

        # The friction and limit variants add only their own coefficients, and their effort
        # chain keeps the pivot compliance of the base joint (D-MB9: variants, not a switch).
        @test [p.name for p in blocks["stdlib:planar/Revolute2DFriction"].interface.parameters] ==
              ["rx", "ry", "kt", "bt", "Fc", "Fv", "v_eps", "q0"]
        @test [p.name for p in blocks["stdlib:planar/Revolute2DLimit"].interface.parameters] ==
              ["rx", "ry", "kt", "bt", "lower", "upper", "kL", "bL", "delta", "q0"]
        @test [p.name for p in
               blocks["stdlib:planar/Revolute2DCompliant"].interface.parameters] ==
              ["rx", "ry", "kt", "bt", "k", "b", "q0", "qrest"]
        @test [o.name for o in
               blocks["stdlib:planar/Revolute2DCompliant"].interface.outputs] ==
              ["qout", "qdout", "pose", "dout", "Vrelout", "tauout"]
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
            # `dimension` is optional and non-nullable (`2 | 3`): allowed when present, and
            # its value must match the block's multibond ports.
            _check_object_keys(block, defs["catalogBlock"]; optional = ["dimension"])
            if haskey(block, :dimension)
                @test block.dimension in (2, 3)
                expected = any(p -> p.domain == "Planar", block.ports) ? 2 :
                           any(p -> p.domain == "Spatial", block.ports) ? 3 : nothing
                @test expected !== nothing
                @test block.dimension == expected
            else
                @test !any(p -> p.domain in ("Planar", "Spatial"), block.ports)
            end
            for (field, defname) in INTERFACE_FIELDS
                for entry in _field(block, field)
                    # `start` is only on an output a `@discrete`/`@events` body holds.
                    _check_object_keys(entry, defs[defname];
                        optional = defname == "ioDecl" ? ["start"] : String[])
                    if defname == "ioDecl" && field == "inputs"
                        @test !haskey(_plain(entry), "start")
                    end
                end
            end
        end

        for junction in cat.junctions
            _check_object_keys(junction, defs["junction"])
        end
        for domain in cat.domains
            name = String(domain.name)
            defname = name == "Planar" ? "planarDomain" :
                      name == "Spatial" ? "spatialDomain" : "scalarDomain"
            _check_object_keys(domain, defs[defname])
            if haskey(_plain(domain), "components")
                cdef = name == "Planar" ? "planarComponents" : "spatialComponents"
                _check_object_keys(_field(domain, "components"), defs[cdef])
            end
            for field in ("effort", "flow")
                _check_object_keys(_field(domain, field), defs["domainVariable"])
            end
        end

        # The shared `blockInterface` definition exists and covers the same seven arrays the
        # catalog block embeds; that is what keeps `block.check` and `catalog.get` aligned.
        iface = _schema_keys(defs["blockInterface"].properties)
        @test iface == Set([field for (field, _) in INTERFACE_FIELDS]) ∪ Set(["dimension"])
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
        # C-MB1 added two optional contract fields (`catalogBlock.dimension` and
        # `portDecl.frame`). The M1 fixture predates them and is not edited by the M2/M3
        # work packages, while `catalog.get` always emits `portDecl.frame` (the schema allows
        # null). `catalogBlock.dimension` is non-nullable (`2 | 3`), so the scalar M1 blocks
        # omit it in both the fixture and the catalog. Inject the null `frame` into the
        # fixture copy, then compare key-for-key and value-for-value exactly as before (the
        # same assertion, not a weaker one).
        for block in values(theirs)
            for port in block["ports"]
                port["frame"] = nothing
            end
        end
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

        # The two junctions and the eight domains, explicitly (plan 3.2, D8 and D-MB1).
        @test [j.ref for j in cat.junctions] == ["junction:0", "junction:1"]
        @test [d.name for d in cat.domains] ==
              ["Electrical", "Translation", "Rotation", "Hydraulic", "Generic", "Planar", "Spatial",
                  "Thermal"]
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
        @test all(d -> d.size == 1, cat.domains[1:5])
        # Thermal: a pseudo bond domain, temperature across (D8) and heat flow through.
        @test domains["Thermal"].effort == (name = "temperature", unit = "K")
        @test domains["Thermal"].flow == (name = "heat_flow", unit = "W")
        @test domains["Thermal"].across == "e"
        @test domains["Thermal"].size == 1
        # D-MB1/D-MB2: multibond sizes and the authoritative, angular-first components.
        @test domains["Planar"].size == 3
        @test domains["Planar"].across == "f"
        @test domains["Planar"].components ==
              (effort = ["N*m", "N", "N"], flow = ["rad/s", "m/s", "m/s"])
        @test domains["Spatial"].size == 6
        @test domains["Spatial"].across == "f"
        @test domains["Spatial"].components ==
              (effort = ["N*m", "N*m", "N*m", "N", "N", "N"],
                  flow = ["rad/s", "rad/s", "rad/s", "m/s", "m/s", "m/s"])

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
        @test [r.name for r in rows] ==
              ["csv_value", "delay", "interp1", "interp2", "noise_normal", "noise_uniform"]
        by = Dict(r.name => r for r in rows)
        @test by["csv_value"].arity == 3
        @test by["csv_value"].stdlib_only == true
        @test by["csv_value"].lowering == :intrinsic
        @test by["interp1"].arity == 3
        @test by["interp2"].arity == 4
        @test by["noise_normal"].arity == 2
        @test by["delay"].arity == 2
        @test by["interp1"].stdlib_only == false
        @test by["interp2"].stdlib_only == false
        @test by["noise_normal"].stdlib_only == true
        @test by["noise_uniform"].arity == 2
        @test by["noise_uniform"].stdlib_only == true
        @test by["delay"].stdlib_only == true
        @test by["delay"].lowering == :delay
        @test all(
            r -> r.lowering == :intrinsic,
            [by["interp1"], by["interp2"], by["noise_normal"], by["noise_uniform"], by["csv_value"]],
        )
        @test all(r -> !isempty(r.description), rows)

        # The table is derived from the one whitelist table, so it cannot drift from it.
        for row in rows
            rule = BGSim.function_rule(Symbol(row.name))
            @test rule !== nothing
            @test rule.stdlib_only == row.stdlib_only
            # `arity` is the smallest form; only `delay` has a longer one, the variable read
            # `delay(x, Tmax, tau)`.
            @test rule.min_args == row.arity
            @test rule.max_args == (row.name == "delay" ? 3 : row.arity)
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
