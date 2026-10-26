# The catalog (plan section 3.2): the block metadata tables, the power-domain table and the
# two junctions. `catalog()` puts them together with the loaded blocks.
#
# Everything here is data that the language has no syntax for. The groups mirror the
# directories under `stdlib/`; the per-block table holds only what cannot be derived (a
# description and the icon id used by the editor). `test/test_library.jl` asserts that the
# table covers exactly the stdlib blocks and that every value matches the contract fixture
# `contracts/fixtures/catalog/valid/catalog.min.json`.

"""    LANGUAGE_VERSION

The language version stamp written into every saved model and block (plan section 1.3)."""
const LANGUAGE_VERSION = "0.1.0"

"""    RELEASE

The library release the M1 blocks ship in (plan section 8)."""
const RELEASE = "0.1"

"""
    GROUPS

The stdlib directory -> human group name and icon prefix. The order of this tuple is the
order the editor shows the groups in; it also fixes which directories are read at all (a
directory that is not listed is ignored by `load_stdlib`, and the test suite asserts that
every directory under `stdlib/` is listed).
"""
const GROUPS = (
    (dir = "bondgraph", name = "Bond graph", icon_prefix = "bg"),
    (dir = "sources", name = "Sources and sinks", icon_prefix = "src"),
    (dir = "continuous", name = "Continuous", icon_prefix = "cont"),
    (dir = "electrical", name = "Electrical", icon_prefix = "elec"),
    (dir = "translation", name = "Translation", icon_prefix = "mech"),
    (dir = "rotation", name = "Rotation", icon_prefix = "rot"),
    (dir = "converters", name = "Converters and sensors", icon_prefix = "conv"),
)

"""    GROUP_BY_DIR

`GROUPS` indexed by directory name, for `load_stdlib`."""
const GROUP_BY_DIR = Dict(g.dir => g for g in GROUPS)

"""    PROJECT_GROUP

The catalog group of a block that comes from a project's `library/` directory."""
const PROJECT_GROUP = "Project"

"""
    BLOCK_METADATA

Catalog presentation data per stdlib block ref: the description shown in the library palette
and the icon id. The `group` comes from the directory (see [`GROUPS`](@ref)) and the
`release` from [`RELEASE`](@ref); both are not repeated here.
"""
const BLOCK_METADATA = Dict{String,NamedTuple{(:description, :icon),Tuple{String,String}}}(
    "stdlib:bondgraph/C" => (
        description = "Capacitive storage; integral causality by preference.", icon = "bg-c",
    ),
    "stdlib:bondgraph/De" => (
        description = "Effort detector; reads the effort, imposes zero flow.",
        icon = "bg-de",
    ),
    "stdlib:bondgraph/Df" => (
        description = "Flow detector; reads the flow, imposes zero effort.", icon = "bg-df",
    ),
    "stdlib:bondgraph/GY" => (
        description = "Gyrator; power conserving, with the modulus r.", icon = "bg-gy",
    ),
    "stdlib:bondgraph/I" => (
        description = "Inertial storage; integral causality by preference.", icon = "bg-i",
    ),
    "stdlib:bondgraph/MGY" => (
        description = "Modulated gyrator; the modulus comes from a signal input.",
        icon = "bg-mgy",
    ),
    "stdlib:bondgraph/MR" => (
        description = "Modulated resistor; the resistance is gain*u from a signal input.",
        icon = "bg-mr",
    ),
    "stdlib:bondgraph/MSe" => (
        description = "Modulated effort source; the effort comes from a signal input.",
        icon = "bg-mse",
    ),
    "stdlib:bondgraph/MSf" => (
        description = "Modulated flow source; the flow comes from a signal input.",
        icon = "bg-msf",
    ),
    "stdlib:bondgraph/MTF" => (
        description = "Modulated transformer; the modulus comes from a signal input.",
        icon = "bg-mtf",
    ),
    "stdlib:bondgraph/R" => (
        description = "Resistive element; free causality.", icon = "bg-r",
    ),
    "stdlib:bondgraph/Se" => (
        description = "Effort source; imposes the effort on its bond.", icon = "bg-se",
    ),
    "stdlib:bondgraph/Sf" => (
        description = "Flow source; imposes the flow on its bond.", icon = "bg-sf",
    ),
    "stdlib:bondgraph/TF" => (
        description = "Transformer; power conserving, with the modulus n.", icon = "bg-tf",
    ),
    "stdlib:continuous/Gain" => (
        description = "Multiplies the input by a constant gain.", icon = "cont-gain",
    ),
    "stdlib:continuous/Integrator" => (
        description = "Integrates the input; the start value comes from the variable's start override.",
        icon = "cont-integrator",
    ),
    "stdlib:continuous/PIController" => (
        description = "Parallel-form PI controller with a tunable gain and integral time.",
        icon = "cont-pi",
    ),
    "stdlib:continuous/Sum" => (
        description = "Signed sum of a vector of inputs; N is a structural constant (D10).",
        icon = "cont-sum",
    ),
    "stdlib:converters/AngleSensor" => (
        description = "Rotational angle sensor; integrates the angular velocity of its port.",
        icon = "conv-angle-sensor",
    ),
    "stdlib:converters/DCMotor" => (
        description = "Permanent-magnet DC motor, written flat for M1 (plan section 8): electrical p and n, rotational shaft and housing.",
        icon = "conv-dc-motor",
    ),
    "stdlib:converters/SpeedSensor" => (
        description = "Rotational speed sensor; reads the angular velocity of its port.",
        icon = "conv-speed-sensor",
    ),
    "stdlib:electrical/Capacitor" => (
        description = "Electrical capacitor; the initial voltage is the start value of v.",
        icon = "elec-capacitor",
    ),
    "stdlib:electrical/Ground" => (
        description = "Electrical reference node; holds its port at zero voltage.",
        icon = "elec-ground",
    ),
    "stdlib:electrical/Inductor" => (
        description = "Electrical inductor; the initial current is the start value of i.",
        icon = "elec-inductor",
    ),
    "stdlib:electrical/Resistor" => (
        description = "Electrical resistor between p and n.", icon = "elec-resistor",
    ),
    "stdlib:electrical/VoltageSource" => (
        description = "Signal-controlled voltage source; feed it a Constant for a constant source.",
        icon = "elec-voltage-source",
    ),
    "stdlib:rotation/FixedShaft" => (
        description = "Fixed shaft; holds its port at zero angular velocity.",
        icon = "rot-fixed-shaft",
    ),
    "stdlib:rotation/IdealGear" => (
        description = "Lossless gear with ratio n; a is the fast shaft, a.f = n * b.f.",
        icon = "rot-gear",
    ),
    "stdlib:rotation/Inertia" => (
        description = "Rotational inertia between two rotation ports; initial angle and speed come from the start values of phi and w.",
        icon = "rot-inertia",
    ),
    "stdlib:rotation/RotationalDamper" => (
        description = "Linear viscous damper between two rotation ports.", icon = "rot-damper",
    ),
    "stdlib:rotation/TorqueSource" => (
        description = "Signal-controlled torque source between two rotation ports.",
        icon = "rot-torque-source",
    ),
    "stdlib:rotation/TorsionSpring" => (
        description = "Linear torsional spring between two rotation ports.",
        icon = "rot-torsion-spring",
    ),
    "stdlib:sources/Chirp" => (
        description = "Linear frequency sweep from f_start to f_end over duration; frequency in Hz.",
        icon = "src-chirp",
    ),
    "stdlib:sources/Constant" => (
        description = "Constant signal source.", icon = "src-constant",
    ),
    "stdlib:sources/Noise" => (
        description = "Seeded normal noise on a fixed sample clock; the same seed repeats the run.",
        icon = "src-noise",
    ),
    "stdlib:sources/Pulse" => (
        description = "Pulse / square signal source with amplitude, period, duty and t_start.",
        icon = "src-pulse",
    ),
    "stdlib:sources/Ramp" => (
        description = "Ramp signal source; starts at t_start with slope and initial value.",
        icon = "src-ramp",
    ),
    "stdlib:sources/Recorder" => (
        description = "Recorder sink; every signal is always recorded, so decimation is ignored (D15).",
        icon = "src-recorder",
    ),
    "stdlib:sources/Scope" => (
        description = "Editor-only scope; opens a plot panel for its inputs and has no effect on the simulation.",
        icon = "src-scope",
    ),
    "stdlib:sources/Sine" => (
        description = "Sine signal source; frequency in rad/s.", icon = "src-sine",
    ),
    "stdlib:sources/Step" => (description = "Step signal source.", icon = "src-step"),
    "stdlib:sources/Time" => (
        description = "Simulation time as an output signal.", icon = "src-time",
    ),
    "stdlib:sources/TimeTable" => (
        description = "Uniformly sampled time table with hold or linear interpolation (method 0 or 1).",
        icon = "src-time-table",
    ),
    "stdlib:translation/Damper" => (
        description = "Linear viscous damper between two translation ports.",
        icon = "mech-damper",
    ),
    "stdlib:translation/Fixed" => (
        description = "Fixed point; holds its port at zero velocity.", icon = "mech-fixed",
    ),
    "stdlib:translation/ForceSource" => (
        description = "Signal-controlled force source between two translation ports.",
        icon = "mech-force-source",
    ),
    "stdlib:translation/Mass" => (
        description = "Point mass between two translation ports; initial position and velocity come from the start values of x and v.",
        icon = "mech-mass",
    ),
    "stdlib:translation/Spring" => (
        description = "Linear translational spring between two ports.", icon = "mech-spring",
    ),
)

"""
    block_metadata(ref) -> Union{NamedTuple,Nothing}

The [`BLOCK_METADATA`](@ref) entry for a stdlib ref, or `nothing` (a project block, or a
stdlib block whose metadata has not been written yet).
"""
block_metadata(ref::AbstractString) = get(BLOCK_METADATA, String(ref), nothing)

"""    group_info(dir) -> Union{NamedTuple,Nothing}

The [`GROUPS`](@ref) entry for a stdlib directory name, or `nothing`."""
group_info(dir::AbstractString) = get(GROUP_BY_DIR, String(dir), nothing)

"""
    DOMAINS

The five power domains of plan 3.2 and decision D8: effort and flow names and units, which
port field is the across variable (`e` for Electrical and Hydraulic, `f` for Translation and
Rotation, `nothing` for Generic until a domain is adopted) and the port size.
"""
const DOMAINS = [
    (
        name = "Electrical",
        effort = (name = "voltage", unit = "V"),
        flow = (name = "current", unit = "A"),
        across = "e",
        size = 1,
    ),
    (
        name = "Translation",
        effort = (name = "force", unit = "N"),
        flow = (name = "velocity", unit = "m/s"),
        across = "f",
        size = 1,
    ),
    (
        name = "Rotation",
        effort = (name = "torque", unit = "N*m"),
        flow = (name = "angular_velocity", unit = "rad/s"),
        across = "f",
        size = 1,
    ),
    (
        name = "Hydraulic",
        effort = (name = "pressure", unit = "Pa"),
        flow = (name = "volume_flow", unit = "m^3/s"),
        across = "e",
        size = 1,
    ),
    (
        name = "Generic",
        effort = (name = "effort", unit = nothing),
        flow = (name = "flow", unit = nothing),
        across = nothing,
        size = 1,
    ),
]

"""    JUNCTIONS

The two junction types. Junctions are generated by the compiler, not written as files
(plan section 8), so the catalog only carries their refs.
"""
const JUNCTIONS = [(ref = "junction:0",), (ref = "junction:1",)]

"""
    project_library_dir(dir) -> String

The directory that holds a project's `library/<Name>.jl` files. `dir` may be the library
directory itself (that is what the worker protocol's `projectLibraryDir` is) or a project
root that contains a `library` subdirectory (that is what the plan's `project_dir` argument
suggests); both are accepted so that no caller has to guess.
"""
function project_library_dir(dir::AbstractString)
    nested = joinpath(dir, "library")
    return isdir(nested) ? nested : String(dir)
end

"""
    catalog(project_dir = nothing) -> NamedTuple

The plan 3.2 catalog, ready for `JSON3.write`:

    (language = "0.1.0", blocks = [...], junctions = [...], domains = [...])

Every `blocks` entry is a `NamedTuple` with exactly the schema fields (`ref`, `name`,
`group`, `release`, `description`, `icon`, the seven interface arrays, `source`, `path`), so
`b.ref` and `b.parameters` work directly. Blocks are sorted by `ref`; with `project_dir` the
project's blocks are merged in at their `project:<Name>` refs. `project_dir` is either the
project root or its `library` directory (see [`project_library_dir`](@ref)).

The catalog is a pure function of the files on disk: it re-reads and re-checks them on every
call. The per-source parse cache makes the second call cheap; the catalog itself is not
cached, so an edited library file is picked up immediately.
"""
function catalog(project_dir::Union{Nothing,AbstractString} = nothing)
    blocks = load_stdlib()
    if project_dir !== nothing
        append!(blocks, load_project_library(project_library_dir(project_dir)))
    end
    sort!(blocks; by = b -> b.ref)
    return (
        language = LANGUAGE_VERSION,
        blocks = [to_namedtuple(b) for b in blocks],
        junctions = copy(JUNCTIONS),
        domains = copy(DOMAINS),
    )
end
