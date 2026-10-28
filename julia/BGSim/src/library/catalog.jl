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
    (dir = "hydraulic", name = "Hydraulic", icon_prefix = "hyd"),
    (dir = "converters", name = "Converters and sensors", icon_prefix = "conv"),
    (dir = "multibond", name = "Multibond", icon_prefix = "mb"),
    (dir = "planar", name = "Planar mechanics", icon_prefix = "pl"),
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
    "stdlib:converters/AccelerationSensor" => (
        description = "Translational acceleration sensor; differentiates the velocity of its port without drawing force.",
        icon = "conv-acceleration-sensor",
    ),
    "stdlib:converters/AngleSensor" => (
        description = "Rotational angle sensor; integrates the angular velocity of its port.",
        icon = "conv-angle-sensor",
    ),
    "stdlib:converters/BallScrew" => (
        description = "Ball screw from rotation a to translation b; lead per revolution and direction-dependent efficiency.",
        icon = "conv-ball-screw",
    ),
    "stdlib:converters/CurrentSensor" => (
        description = "Series electrical current sensor: zero voltage drop, output y in amperes.",
        icon = "conv-current-sensor",
    ),
    "stdlib:converters/DCMotor" => (
        description = "Permanent-magnet DC motor as a composite (winding, gyrator, rotor): electrical p and n, rotational shaft and housing.",
        icon = "conv-dc-motor",
    ),
    "stdlib:converters/EMConverter" => (
        description = "Ideal electromagnetic gyrator: back-EMF -k*shaft.f and shaft torque k*p.f, power conserving.",
        icon = "conv-em-converter",
    ),
    "stdlib:converters/ExportInput" => (
        description = "Export interface input marker; in simulation it supplies the constant parameter value.",
        icon = "conv-export-input",
    ),
    "stdlib:converters/ExportOutput" => (
        description = "Export interface output marker; in simulation it holds the input value for recording.",
        icon = "conv-export-output",
    ),
    "stdlib:converters/ExportParameter" => (
        description = "Export interface parameter marker; publishes a tunable parameter value.",
        icon = "conv-export-parameter",
    ),
    "stdlib:converters/FlowSensor" => (
        description = "Series hydraulic flow sensor: zero pressure drop, output y in m^3/s.",
        icon = "conv-flow-sensor",
    ),
    "stdlib:converters/ForceSensor" => (
        description = "Series translational force sensor: passes the velocity through and reads the force.",
        icon = "conv-force-sensor",
    ),
    "stdlib:converters/HydraulicCylinder" => (
        description = "Double-acting hydraulic cylinder with chamber compressibility: dead volumes plus the swept volumes, drive from A and B to the translation rod.",
        icon = "conv-hydraulic-cylinder",
    ),
    "stdlib:converters/PositionSensor" => (
        description = "Translational position sensor; integrates the velocity of its port without drawing force.",
        icon = "conv-position-sensor",
    ),
    "stdlib:converters/PowerSensor" => (
        description = "Transparent bond sensor; output y is the power e*f of the bond it sits on.",
        icon = "conv-power-sensor",
    ),
    "stdlib:converters/PressureSensor" => (
        description = "Hydraulic pressure sensor; reads the port pressure and draws no flow.",
        icon = "conv-pressure-sensor",
    ),
    "stdlib:converters/RackAndPinion" => (
        description = "Rack and pinion from rotation a to translation b; b.f = r*a.f and b.e = -a.e/r.",
        icon = "conv-rack-pinion",
    ),
    "stdlib:converters/SpeedSensor" => (
        description = "Rotational speed sensor; reads the angular velocity of its port.",
        icon = "conv-speed-sensor",
    ),
    "stdlib:converters/TorqueSensor" => (
        description = "Series rotational torque sensor: passes the angular velocity through and reads the torque.",
        icon = "conv-torque-sensor",
    ),
    "stdlib:converters/VelocitySensor" => (
        description = "Translational velocity sensor; reads the velocity of its port without drawing force.",
        icon = "conv-velocity-sensor",
    ),
    "stdlib:converters/VoltageSensor" => (
        description = "Open-circuit electrical voltage sensor; draws no current and reads the terminal voltage.",
        icon = "conv-voltage-sensor",
    ),
    "stdlib:converters/Wheel" => (
        description = "Rolling wheel from rotation a to translation b; radius r, b.f = r*a.f and b.e = -a.e/r.",
        icon = "conv-wheel",
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
    "stdlib:rotation/ElasticShaft" => (
        description = "Elastic shaft with torsional stiffness and damping; the twist angle is the state.",
        icon = "rot-elastic-shaft",
    ),
    "stdlib:rotation/FixedShaft" => (
        description = "Fixed shaft; holds its port at zero angular velocity.",
        icon = "rot-fixed-shaft",
    ),
    "stdlib:rotation/GearBacklash" => (
        description = "Dead-zone contact spring across a gear mesh: no torque inside gap, stiff contact outside it.",
        icon = "rot-gear-backlash",
    ),
    "stdlib:rotation/GearWithBacklash" => (
        description = "Composite gear with efficiency and backlash: LossyGear followed by GearBacklash on the output side.",
        icon = "rot-gear-with-backlash",
    ),
    "stdlib:rotation/IdealGear" => (
        description = "Lossless gear with ratio n; a is the fast shaft, a.f = n * b.f.",
        icon = "rot-gear",
    ),
    "stdlib:rotation/Inertia" => (
        description = "Rotational inertia between two rotation ports; initial angle and speed come from the start values of phi and w.",
        icon = "rot-inertia",
    ),
    "stdlib:rotation/LossyGear" => (
        description = "Gear with ratio n and direction-dependent efficiency eta (the reciprocal when back-driven).",
        icon = "rot-lossy-gear",
    ),
    "stdlib:rotation/RotationalDamper" => (
        description = "Linear viscous damper between two rotation ports.", icon = "rot-damper",
    ),
    "stdlib:rotation/RotationalFriction" => (
        description = "Rotational friction with Coulomb, viscous and Stribeck terms; tanh-smoothed or switched.",
        icon = "rot-friction",
    ),
    "stdlib:rotation/SpeedSource" => (
        description = "Signal-controlled angular speed source; a.f = w*u with fixed flow causality (D6).",
        icon = "rot-speed-source",
    ),
    "stdlib:rotation/TorqueSource" => (
        description = "Signal-controlled torque source between two rotation ports.",
        icon = "rot-torque-source",
    ),
    "stdlib:rotation/TorsionSpring" => (
        description = "Linear torsional spring between two rotation ports.",
        icon = "rot-torsion-spring",
    ),
    "stdlib:hydraulic/FlowSource" => (
        description = "Signal-controlled volume-flow source; Q*u enters a and returns through b.",
        icon = "hyd-flow-source",
    ),
    "stdlib:hydraulic/Orifice" => (
        description = "Regularized orifice: Q = Cd*A*sqrt(2/rho)*dp/(dp^2 + p_tr^2)^(1/4), smooth through dp = 0.",
        icon = "hyd-orifice",
    ),
    "stdlib:hydraulic/PressureSource" => (
        description = "Signal-controlled pressure source; a.e = p*u with fixed effort causality (D6).",
        icon = "hyd-pressure-source",
    ),
    "stdlib:hydraulic/Tank" => (
        description = "Tank at a constant pressure; holds its port at p.",
        icon = "hyd-tank",
    ),
    "stdlib:hydraulic/VariableOrifice" => (
        description = "Orifice whose area A*u comes from a signal input; the same regularized flow law.",
        icon = "hyd-variable-orifice",
    ),
    "stdlib:hydraulic/Volume" => (
        description = "Hydraulic volume with fluid compressibility; the pressure integrates the net flow with the bulk modulus.",
        icon = "hyd-volume",
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
    "stdlib:translation/Friction" => (
        description = "Stribeck friction (Coulomb, static and viscous terms) between two translation ports, smoothed by tanh(v/v_eps) when v_eps > 0 and by the exact ifelse switch otherwise.",
        icon = "mech-friction",
    ),
    "stdlib:translation/HardStop" => (
        description = "Hard stop with free travel between lower and upper; a contact spring-damper acts outside them.",
        icon = "mech-hard-stop",
    ),
    "stdlib:translation/Mass" => (
        description = "Point mass between two translation ports; initial position and velocity come from the start values of x and v.",
        icon = "mech-mass",
    ),
    "stdlib:translation/Spring" => (
        description = "Linear translational spring between two ports.", icon = "mech-spring",
    ),
    "stdlib:translation/SpringDamper" => (
        description = "Linear spring and viscous damper in parallel between two translation ports; initial displacement comes from the start value of x.",
        icon = "mech-spring-damper",
    ),
    "stdlib:translation/VelocitySource" => (
        description = "Signal-controlled velocity source; a.f = v*u with fixed flow causality (D6).",
        icon = "mech-velocity-source",
    ),
    "stdlib:multibond/ComposePose2D" => (
        description = "Planar pose composition g = gp composed with gl on the SE(2) chart (theta, x, y); the fixed-base link pose is algebraic (D-MB6).",
        icon = "mb-compose-pose-2d",
    ),
    "stdlib:multibond/CoriolisPlanar" => (
        description = "Eulerian junction structure (Coriolis/gyroscopic) for a planar body: p.e = ad(p.f)^T P from the momentum signal, no inertia copy (D-MB3).",
        icon = "mb-coriolis-planar",
    ),
    "stdlib:multibond/CPlanar" => (
        description = "Planar capacitive storage (the planar C): three scalar displacement states, one per component, with their own units and a zero rest deflection.",
        icon = "mb-c-planar",
    ),
    "stdlib:multibond/DePlanar" => (
        description = "Planar effort detector; reads the wrench, imposes zero twist, outputs the three wrench components.",
        icon = "mb-de-planar",
    ),
    "stdlib:multibond/DfPlanar" => (
        description = "Planar flow detector; reads the twist, imposes zero wrench, outputs the three twist components.",
        icon = "mb-df-planar",
    ),
    "stdlib:multibond/ExternalWrenchPlanar" => (
        description = "Planar external wrench source in the port frame: three scalar inputs (N*m, N, N) are the physical external wrench W_ext; the port effort is -W_ext, so a body on a 1-junction feels +W_ext.",
        icon = "mb-external-wrench-planar",
    ),
    "stdlib:multibond/FixedTransform2D" => (
        description = "Constant planar frame transform (x, y, theta) from a parent frame to a child frame; the legal two-frame bridge (D-MB5).",
        icon = "mb-fixed-transform-2d",
    ),
    "stdlib:multibond/GravityPlanar" => (
        description = "Planar gravity wrench at the body centre of mass, from the composed body pose in the world; the port effort is the negative of that wrench for a 1-junction.",
        icon = "mb-gravity-planar",
    ),
    "stdlib:multibond/GroundPlanar" => (
        description = "Planar reference node; holds its port at zero twist in the world frame.",
        icon = "mb-ground-planar",
    ),
    "stdlib:multibond/GYPlanar" => (
        description = "Planar matrix gyrator (the planar GY): a.e = G*b.f and b.e = -G^T*a.f, power-continuous for every G, no inverse needed.",
        icon = "mb-gy-planar",
    ),
    "stdlib:multibond/IPlanar" => (
        description = "Planar rigid-body inertia at the centre of mass (J, m): momentum P is the state, the twist is its output, and P is exposed as a signal for Coriolis (D-MB3).",
        icon = "mb-i-planar",
    ),
    "stdlib:multibond/JointTransform2D" => (
        description = "Joint-role planar adjoint transform (the plan JointTransform): component-wise Ad(g) between the joint parent and child frames, power-continuous.",
        icon = "mb-joint-transform-2d",
    ),
    "stdlib:multibond/MGYPlanar" => (
        description = "Modulated planar matrix gyrator: the 3x3 gyrator matrix is a signal input; a.e = G*b.f and b.e = -G^T*a.f.",
        icon = "mb-mgy-planar",
    ),
    "stdlib:multibond/MSePlanar" => (
        description = "Modulated planar effort source: three scalar input components (N*m, N, N) impose the wrench component-wise with fixed effort causality.",
        icon = "mb-mse-planar",
    ),
    "stdlib:multibond/MSfPlanar" => (
        description = "Modulated planar flow source: three scalar input components (rad/s, m/s, m/s) impose the twist component-wise with fixed flow causality.",
        icon = "mb-msf-planar",
    ),
    "stdlib:multibond/MTFPlanar" => (
        description = "Modulated planar transformer: a diagonal Vec{3} modulus signal scales each component, power-continuous per component with a dimensionless modulus.",
        icon = "mb-mtf-planar",
    ),
    "stdlib:multibond/MTFPlanarMat" => (
        description = "Modulated planar matrix transformer: a 3x3 matrix signal input with a.f = M*b.f and b.e = -M^T*a.e, power-continuous for every M without an inverse.",
        icon = "mb-mtf-planar-mat",
    ),
    "stdlib:multibond/Revolute2D" => (
        description = "Minimal planar revolute joint: parent and child planar bonds plus a rotational drive, with the joint pose composed from q (not integrated).",
        icon = "mb-revolute-2d",
    ),
    "stdlib:multibond/RPlanar" => (
        description = "Planar resistive element (the planar R): a torsional and two translational damping coefficients, free causality.",
        icon = "mb-r-planar",
    ),
    "stdlib:multibond/ScrewTF" => (
        description = "Planar revolute screw transformer S = [1, ry, -rx] between a planar bond and one rotational drive axis (D-MB8).",
        icon = "mb-screw-tf",
    ),
    "stdlib:multibond/SePlanar" => (
        description = "Planar effort source; imposes a Vec{3} wrench on its bond (fixed effort causality).",
        icon = "mb-se-planar",
    ),
    "stdlib:multibond/SfPlanar" => (
        description = "Planar flow source; imposes a Vec{3} twist on its bond (fixed flow causality).",
        icon = "mb-sf-planar",
    ),
    "stdlib:multibond/TFAd" => (
        description = "Planar adjoint transformer driven by a pose signal (theta, x, y); power-continuous, the general transform primitive, frame-named world -> body.",
        icon = "mb-tf-ad",
    ),
    "stdlib:multibond/TFAdNeutral" => (
        description = "Frame-neutral planar adjoint transformer: the TFAd equations with both ports left frame-neutral, so a joint composite's parent role adopts GroundPlanar's world or a body 1-junction frame (FIX-MB-4).",
        icon = "mb-tf-ad-neutral",
    ),
    "stdlib:multibond/TFPlanar" => (
        description = "Planar diagonal transformer (the planar TF): a dimensionless Vec{3} modulus per component, a.f[k] = n[k]*b.f[k] and b.e[k] = -n[k]*a.e[k].",
        icon = "mb-tf-planar",
    ),
    "stdlib:multibond/TFPlanarMat" => (
        description = "Planar matrix transformer (the general planar TF): a 3x3 matrix M with a.f = M*b.f and b.e = -M^T*a.e, component-wise and power-continuous for every M without an inverse.",
        icon = "mb-tf-planar-mat",
    ),
    "stdlib:planar/FixedJoint2D" => (
        description = "Rigid fixed planar joint between the parent and child body frames: a constant adjoint bridge with the joint role frames, written in the parent->child causal direction (FIX-MB-2).",
        icon = "pl-fixed-joint-2d",
    ),
    "stdlib:planar/Free2D" => (
        description = "Floating planar base: a planar rigid body whose world pose is integrated from its own twist by PoseIntegrator2D (D-MB6); one port, pose output.",
        icon = "pl-free-2d",
    ),
    "stdlib:planar/JointPose2D" => (
        description = "Joint-pose chart g(q) = (q + theta0, rx, ry) for a joint coordinate, consumed by a joint transform and a fixed-base pose chain.",
        icon = "pl-joint-pose-2d",
    ),
    "stdlib:planar/LocalPose2D" => (
        description = "Constant local SE(2) pose (theta, x, y): the link mounting pose composed by ComposePose2D in a fixed-base chain.",
        icon = "pl-local-pose-2d",
    ),
    "stdlib:planar/PoseIntegrator2D" => (
        description = "Floating-base pose integrator: ddt(theta) = omega and ddt(p) = R(theta) v from a Vec{3} twist input; no exp integrator (D-MB6).",
        icon = "pl-pose-integrator-2d",
    ),
    "stdlib:planar/Prismatic2D" => (
        description = "Planar prismatic joint: exact translation along an axis (phi) with a Translation drive (D-MB8) and compliant rotation/perpendicular directions; q/qdot outputs.",
        icon = "pl-prismatic-2d",
    ),
    "stdlib:planar/Revolute2DCompliant" => (
        description = "Compliant planar revolute joint with a torsional spring-damper on the link angle (k, b, qrest) on top of the compliant pivot; k and kt -> Inf converge to the rigid joint.",
        icon = "pl-revolute-2d-compliant",
    ),
    "stdlib:planar/Revolute2DFriction" => (
        description = "Planar revolute joint with viscous plus regularised-Coulomb friction on the joint rate (stick/slip); dissipative by construction.",
        icon = "pl-revolute-2d-friction",
    ),
    "stdlib:planar/Revolute2DLimit" => (
        description = "Planar revolute joint with one-sided spring-damper limits on the joint angle (lower, upper, kL, bL).",
        icon = "pl-revolute-2d-limit",
    ),
    "stdlib:planar/Revolute2DRigid" => (
        description = "Rigid planar revolute joint as a bond-graph composite: 0-junction, adjoint and screw transforms, 1-junction with the drive, Df and integrator; frame-neutral parent (a legal elbow), index-3 DAE whose two joint-frame translations are derivative-causal (DEC-MB-2).",
        icon = "pl-revolute-2d-rigid",
    ),
    "stdlib:planar/RigidBody2D" => (
        description = "Planar rigid body (m, J) with one planar port: the flat graph is the 1-junction with IPlanar, CoriolisPlanar fed by IPlanar/Pm and GravityPlanar fed by the world pose (plan 5.2).",
        icon = "pl-rigid-body-2d",
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
    DOMAIN_COMPONENTS

The authoritative per-component effort/flow units of a multibond domain, angular first
(D-MB2, C-MB1). A scalar domain has no components; its scalar `effort`/`flow` descriptors
are the whole unit story. The arrays come from the unit table
(`BGSim.Units.domain_effort_unit_strings` / `domain_flow_unit_strings`), so the catalog and
the checker cannot disagree (J-MB2, finding F9).
"""
const DOMAIN_COMPONENTS = Dict{Symbol,NamedTuple{(:effort, :flow),Tuple{Vector{String},Vector{String}}}}(
    :Planar => (
        effort = BGSim.Units.domain_effort_unit_strings(:Planar),
        flow = BGSim.Units.domain_flow_unit_strings(:Planar),
    ),
    :Spatial => (
        effort = BGSim.Units.domain_effort_unit_strings(:Spatial),
        flow = BGSim.Units.domain_flow_unit_strings(:Spatial),
    ),
)

"""
    domain_components(domain) -> Union{NamedTuple,Nothing}

The per-component unit arrays of a multibond domain (Planar or Spatial), or `nothing` for a
scalar domain. Used by the subsystem-boundary check and by the catalog. The arrays are
copies, so a caller can never mutate the catalog's data.
"""
function domain_components(domain::Symbol)
    components = get(DOMAIN_COMPONENTS, domain, nothing)
    components === nothing && return nothing
    return (effort = copy(components.effort), flow = copy(components.flow))
end

"""    _catalog_domain(entry) -> NamedTuple

A copy of one [`DOMAINS`](@ref) entry whose mutable unit arrays are freshly allocated, so a
consumer mutating a returned catalog cannot corrupt the module's tables."""
function _catalog_domain(entry)
    haskey(entry, :components) || return entry
    return merge(entry, (components = domain_components(Symbol(entry.name)),))
end

"""
    DOMAINS

The seven power domains of plan 3.2 and decisions D8/D-MB1: effort and flow names and units,
which port field is the across variable (`e` for Electrical and Hydraulic, `f` for
Translation, Rotation, Planar and Spatial, `nothing` for Generic until a domain is adopted),
the port size, and for the multibond domains the authoritative `components` arrays. The order
is the contract fixture's order.
"""
const DOMAINS = Any[
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
    (
        name = "Planar",
        effort = (name = "wrench", unit = "N*m"),
        flow = (name = "twist", unit = "rad/s"),
        across = "f",
        size = 3,
        components = DOMAIN_COMPONENTS[:Planar],
    ),
    (
        name = "Spatial",
        effort = (name = "wrench", unit = "N*m"),
        flow = (name = "twist", unit = "rad/s"),
        across = "f",
        size = 6,
        components = DOMAIN_COMPONENTS[:Spatial],
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
        domains = [_catalog_domain(d) for d in DOMAINS],
    )
end
