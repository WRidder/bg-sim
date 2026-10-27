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
    (dir = "discrete", name = "Discrete and logic", icon_prefix = "disc"),
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
    "stdlib:continuous/Abs" => (
        description = "Absolute value of the input; the kink at zero is a switching event.",
        icon = "cont-abs",
    ),
    "stdlib:continuous/DeadZone" => (
        description = "Dead zone: zero output inside the zone and u - edge outside it.",
        icon = "cont-dead-zone",
    ),
    "stdlib:continuous/Divide" => (
        description = "Divides u1 by u2.",
        icon = "cont-divide",
    ),
    "stdlib:continuous/FilteredDerivative" => (
        description = "Derivative with a first-order filter; Tf is the filter time constant.",
        icon = "cont-filtered-derivative",
    ),
    "stdlib:continuous/FirstOrder" => (
        description = "First-order lag k/(tau*s + 1).",
        icon = "cont-first-order",
    ),
    "stdlib:continuous/Gain" => (
        description = "Multiplies the input by a constant gain.", icon = "cont-gain",
    ),
    "stdlib:continuous/Integrator" => (
        description = "Integrates the input; the start value comes from the variable's start override.",
        icon = "cont-integrator",
    ),
    "stdlib:continuous/LeadLag" => (
        description = "Lead-lag filter k*(1 + T_lead*s)/(1 + T_lag*s).",
        icon = "cont-lead-lag",
    ),
    "stdlib:continuous/Lookup1D" => (
        description = "Piecewise-linear 1-D lookup table over N breakpoints (interp1, D12).",
        icon = "cont-lookup-1d",
    ),
    "stdlib:continuous/Lookup2D" => (
        description = "Bilinear 2-D lookup table on an N-by-N grid (interp2, D12); row 1 of breaks is the x axis, row 2 the y axis.",
        icon = "cont-lookup-2d",
    ),
    "stdlib:continuous/MathFunction" => (
        description = "One whitelisted scalar function, selected structurally by the constant fn (0 sin, 1 cos, 2 tan, 3 asin, 4 acos, 5 atan, 6 sinh, 7 cosh, 8 tanh, 9 exp, 10 log, 11 log10, 12 sqrt, 13 abs, 14 sign, 15 floor, 16 ceil).",
        icon = "cont-math-function",
    ),
    "stdlib:continuous/Max" => (
        description = "Larger of two inputs.", icon = "cont-max",
    ),
    "stdlib:continuous/Min" => (
        description = "Smaller of two inputs.", icon = "cont-min",
    ),
    "stdlib:continuous/PIController" => (
        description = "Parallel-form PI controller with a tunable gain and integral time.",
        icon = "cont-pi",
    ),
    "stdlib:continuous/PID" => (
        description = "PID controller with a filtered derivative, output limits and back-calculation anti-windup.",
        icon = "cont-pid",
    ),
    "stdlib:continuous/Product" => (
        description = "Product of two inputs; chain instances for more factors.",
        icon = "cont-product",
    ),
    "stdlib:continuous/RateLimiter" => (
        description = "Limits the rate of change of the output to the rising and falling rates.",
        icon = "cont-rate-limiter",
    ),
    "stdlib:continuous/Relay" => (
        description = "Relay with hysteresis: on (rising) and off (falling) thresholds and the two output values; the held state starts at the start value of s.",
        icon = "cont-relay",
    ),
    "stdlib:continuous/Saturation" => (
        description = "Clamps the input between lower and upper.",
        icon = "cont-saturation",
    ),
    "stdlib:continuous/SecondOrder" => (
        description = "Second-order lag k*w0^2/(s^2 + 2*zeta*w0*s + w0^2).",
        icon = "cont-second-order",
    ),
    "stdlib:continuous/Sign" => (
        description = "Sign of the input: -1, 0 or 1.",
        icon = "cont-sign",
    ),
    "stdlib:continuous/StateSpace" => (
        description = "SISO state-space model x' = A*x + B*u, y = C*x + D*u with N states.",
        icon = "cont-state-space",
    ),
    "stdlib:continuous/Sum" => (
        description = "Signed sum of a vector of inputs; N is a structural constant (D10).",
        icon = "cont-sum",
    ),
    "stdlib:continuous/Switch" => (
        description = "Selects u1 while ctrl is above threshold, u2 otherwise.",
        icon = "cont-switch",
    ),
    "stdlib:discrete/And" => (
        description = "Logical AND of two Bool inputs; chain instances for more inputs, because a Bool vector port is not available.",
        icon = "disc-and",
    ),
    "stdlib:discrete/Compare" => (
        description = "Compares two inputs; op selects ==, !=, <, <=, > or >=, and the output is Bool.",
        icon = "disc-compare",
    ),
    "stdlib:discrete/Counter" => (
        description = "Counts rising edges of trigger between lower and upper, resets to lower while reset is high; wrap selects wrap or stop.",
        icon = "disc-counter",
    ),
    "stdlib:discrete/DiscreteIntegrator" => (
        description = "Discrete-time integrator; method selects forward, backward or trapezoidal, and the output is clamped to the limits.",
        icon = "disc-integrator",
    ),
    "stdlib:discrete/DiscretePID" => (
        description = "Discrete PID with a backward-difference derivative and clamping anti-windup; method discretizes the integral term.",
        icon = "disc-pid",
    ),
    "stdlib:discrete/DiscreteSS" => (
        description = "Discrete state-space model x[k+1] = A*x[k] + B*u[k], y[k] = C*x[k] + D*u[k] with N states.",
        icon = "disc-state-space",
    ),
    "stdlib:discrete/DiscreteTF" => (
        description = "Discrete transfer function b(z)/a(z) in powers of z^-1 with N coefficients each, evaluated directly.",
        icon = "disc-transfer-function",
    ),
    "stdlib:discrete/EdgeDetect" => (
        description = "Reports a rising, falling or both edges of a Bool input on the tick where it happens.",
        icon = "disc-edge-detect",
    ),
    "stdlib:discrete/FIR" => (
        description = "FIR filter: the weighted sum of the last N input samples, with b[1] the newest.",
        icon = "disc-fir",
    ),
    "stdlib:discrete/IIR" => (
        description = "IIR filter: N feedforward and M feedback coefficients, a[1] is the output gain.",
        icon = "disc-iir",
    ),
    "stdlib:discrete/Not" => (
        description = "Logical NOT of a Bool input.",
        icon = "disc-not",
    ),
    "stdlib:discrete/OnOffDelay" => (
        description = "On-delay and off-delay timer: the output follows the Bool input after t_on high and t_off low.",
        icon = "disc-on-off-delay",
    ),
    "stdlib:discrete/Or" => (
        description = "Logical OR of two Bool inputs; chain instances for more inputs, because a Bool vector port is not available.",
        icon = "disc-or",
    ),
    "stdlib:discrete/Quantizer" => (
        description = "Rounds the input to a multiple of the resolution; half steps round away from zero.",
        icon = "disc-quantizer",
    ),
    "stdlib:discrete/RateTransition" => (
        description = "Samples the input on the input clock and publishes the most recent sample on the output clock.",
        icon = "disc-rate-transition",
    ),
    "stdlib:discrete/SRFlipFlop" => (
        description = "Set/reset latch; dominant selects which input wins when both are high.",
        icon = "disc-sr-flip-flop",
    ),
    "stdlib:discrete/TypeConversion" => (
        description = "Converts the input to Real, Int (truncation toward zero) or Bool (0/1), selected by target.",
        icon = "disc-type-conversion",
    ),
    "stdlib:discrete/UnitDelay" => (
        description = "Delays the input by one sample; initial is the output at the first tick.",
        icon = "disc-unit-delay",
    ),
    "stdlib:discrete/Xor" => (
        description = "Exclusive OR of two Bool inputs.",
        icon = "disc-xor",
    ),
    "stdlib:discrete/ZOH" => (
        description = "Zero-order hold: samples the input on the clock and holds it until the next tick.",
        icon = "disc-zoh",
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
    "stdlib:electrical/CurrentSource" => (
        description = "Signal-controlled current source; p.f = I*u, so feed it a Constant for a constant source.",
        icon = "elec-current-source",
    ),
    "stdlib:electrical/Ground" => (
        description = "Electrical reference node; holds its port at zero voltage.",
        icon = "elec-ground",
    ),
    "stdlib:electrical/IdealDiode" => (
        description = "Piecewise-linear diode: conducts above V_knee through R_on, leaks G_off below it.",
        icon = "elec-diode",
    ),
    "stdlib:electrical/IdealSwitch" => (
        description = "Ideal switch: closed (R_on) while the Bool control is true, open (G_off) otherwise.",
        icon = "elec-switch",
    ),
    "stdlib:electrical/IdealTransformer" => (
        description = "Lossless two-winding transformer with turns ratio n (v1 = n*v2, p1.f = -p2.f/n).",
        icon = "elec-transformer",
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
