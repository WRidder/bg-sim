# Modeling Language Spec v0.1

Oct 21, 2026 · @Wilbert

## Purpose and design principles

One small language, written in a restricted subset of Julia syntax, describes every model element: bond graph elements, block diagram blocks and plain equation models. It plays the role SIDOPS+ plays in [20-sim](https://www.20sim.com/webhelp/language_reference_language_reference.php): library elements are written in it, and users can open, copy and edit them.

1. **One language, one intermediate representation.** Bond graphs, blocks and equations all compile to the same hybrid DAE. Nothing downstream knows which editor view a model came from.
2. **Julia syntax, not Julia semantics.** User code is parsed with Julia's parser and translated by our compiler. It is never evaluated.
3. **Whitelist, not blacklist.** Every syntax node, type and function must be explicitly allowed for the scope it appears in. Anything else is a compile error.
4. **The whitelist is the target build's vocabulary.** A construct is admitted only once it compiles into a trimmed, allocation-free Julia step library and has a golden test.
5. **Static and deterministic.** Types and array sizes are known at compile time. No heap allocation, no unbounded loops, no recursion, no I/O.
6. **Errors point at the user's code.** Every diagnostic carries the block path, scope, line and column.

Non-goals: general-purpose programming, strings, user-defined types, file or network access, and calling arbitrary Julia packages.

**Target platform.** Targets are (real-time) Linux controllers, such as ctrlX CORE, which run Julia directly. A model is deployed as a fixed-step step function, compiled ahead of time with `juliac` into a trimmed shared library and called by the controller app through a C ABI. Throughout this spec, "export" and "exported code" mean this target build.

**Future option: C++ export.** Generating C++ for targets without a Julia runtime (bare-metal microcontrollers, vendor RTOS) is a possible later feature. The whitelist rules (static sizes, no allocation, a small function set) keep that option open.

## Block structure and scopes

A block is one `@block` expression containing named scopes; each scope has its own rules for what may appear in it. The syntax follows ModelingToolkit conventions so the Julia parser accepts it unchanged.

```julia
@block PIController begin
    @parameters begin
        Kp::Real = 1.0, [tunable = true]
        Ti::Real = 0.1, [unit = "s", min = 0]
    end
    @inputs  e::Real
    @outputs u::Real
    @variables x::Real = 0.0
    @equations begin
        ddt(x) ~ e / Ti
        u ~ Kp * (e + x)
    end
end

@block SpeedMonitor begin
    @parameters wmax::Real = 300.0, [unit = "rad/s"]
    @inputs  w::Real
    @outputs fault::Bool = false
    @discrete Ts = 1e-3 begin
        if abs(w) > wmax
            fault = true
        end
    end
end
```

| Scope | Purpose | Order matters | Evaluated |
| --- | --- | --- | --- |
| `@constants` | Fixed values, folded at compile time; may set array sizes | No | Compile time |
| `@parameters` | Named values; `tunable = true` keeps them adjustable at runtime | No | Compile time, or at init if tunable |
| `@inputs` / `@outputs` | Directed signal ports | No | Every step |
| `@ports` | Power ports (effort and flow pairs) for bond graph and physical connections | No | Every step |
| `@variables` | Internal continuous or discrete quantities, with optional start values | No | Every step |
| `@initial` | Initial equations, solved once before t = 0 | No | Once |
| `@equations` | Acausal equations using `~`; the compiler sorts and solves them | No | Continuously |
| `@discrete Ts = …` | Imperative statements run in order at each tick of a clock | Yes | At each tick |
| `@events` | Zero-crossing conditions with state resets | Yes, within one event | When triggered |

Operator rules: `~` states an equation, `=` assigns (only in `@discrete` and `@events`), and `==` is a boolean comparison. This keeps `ddt(x) = …` from ever reading as a Julia function definition.

## Types and declarations

Five types cover v0.1, and every size is fixed at compile time.

| Type | Julia representation | Notes |
| --- | --- | --- |
| `Real` | `Float64` | Default for all variables; `Float32` target option later |
| `Int` | `Int32` | Discrete scopes, counters, array indices |
| `Bool` | `Bool` | Not allowed as a continuous state |
| `Vec{N}` | `SVector{N,Float64}` | N is a literal or a `@constants` value |
| `Mat{N,M}` | `SMatrix{N,M,Float64}` | Same size rule as `Vec` |

Declaration form: `name::Type = default, [attributes]`. The type defaults to `Real` when omitted.

| Attribute | Applies to | Meaning |
| --- | --- | --- |
| `unit = "N*m"` | All numeric | Checked for dimensional consistency at compile time; no runtime conversion |
| `min`, `max` | All numeric | Validated on parameters at init; optional runtime assertion on variables in debug builds |
| `tunable = true` | Parameters | Stays a field in the generated parameter struct instead of being folded |
| `description = "…"` | All | Shown in the editor and copied into generated code comments |
| `nominal = 1e-3` | Variables | Scaling hint for solvers |
| `state = :prefer` / `:avoid` | Variables | Hint for state selection during index reduction |

Scoping rules: names are local to the block. Ports and their fields are reached with dot syntax (`p.e`, `p.f`). Shadowing a whitelisted function name is an error.

## Operators and statements per scope

Equations are declarative and order-free; discrete code is imperative and bounded. Anything not listed is rejected.

| Construct | `@equations` / `@initial` | `@discrete` / `@events` | Defaults and sizes |
| --- | --- | --- | --- |
| `+ - * /`, unary `-` | Yes | Yes | Yes |
| `^` with integer literal exponent | Yes, expanded to multiplication | Yes | Yes |
| `^` with real exponent | Yes, maps to `pow` | Yes | Yes |
| `== != < <= > >=` | Inside `ifelse` only | Yes | No |
| `&& \|\| !` | Inside `ifelse` only | Yes | No |
| `a ~ b` (equation) | Yes | No | No |
| `x = expr` (assignment) | No | Yes | Default values only |
| `x += expr` and similar | No | Yes | No |
| `ifelse(c, a, b)` | Yes, may create an event (see semantics) | Yes | Yes |
| `if / elseif / else` | Only around whole equations, with equal equation counts per branch | Yes | No |
| `for i in 1:N` | Yes, N static; unrolled | Yes, N static | No |
| `while`, `break`, `continue` | No | No | No |
| Array literals and indexing `v[i]` | Yes, static indices | Yes, index checked against size | Yes |
| `ddt(x)`, `int(x)` | Yes | No | No |
| `previous(x)`, `hold(x)` | No | Yes | No |
| `reinit(x, value)` | No | `@events` only | No |
| Function definitions, closures, `do` blocks | No | No | No |
| Macros other than the scope macros | No | No | No |
| String literals | `description` and `unit` attributes only | No | No |

Every equation scope must be balanced: the compiler counts unknowns and equations after flattening and reports the block that causes a mismatch.

## Built-in function whitelist

This table is the contract between the language, the simulator and the target build; adding a row requires an allocation-free, trim-compatible implementation and a golden test.

| Function | Julia | Scopes | Notes |
| --- | --- | --- | --- |
| `sin cos tan` | `Base` | All |  |
| `asin acos atan`, `atan(y, x)` | `Base` | All |  |
| `sinh cosh tanh` | `Base` | All |  |
| `exp log log10 sqrt` | `Base` | All | Domain errors are compile-time warnings when provable |
| `abs sign` | `Base` | All | Nonsmooth: may create events |
| `min max clamp` | `Base` | All | Nonsmooth |
| `floor ceil round` | `Base` | All | Discontinuous: events in equations |
| `mod rem` | `Base` | All | Julia sign conventions |
| `hypot` | `Base` | All |  |
| `dot norm cross` | `LinearAlgebra` | All | Static sizes only |
| `transpose`, `A * x`, `A \ b` | `StaticArrays` | All | `\` via fixed-size LU; `inv` is not offered |
| `ddt(x)` | Derivative operator | Equations | Bond graph integral causality uses it |
| `int(x, x0)` | Integral with start value | Equations | Sugar for a new state with `ddt` |
| `deadzone(x, a, b)`, `saturate(x, lo, hi)` | Library | All | Nonsmooth |
| `delay(x, T)` | Transport delay | Equations | T constant; ring buffer sized `ceil(T / dt)`; fixed-step only |
| `previous(x)` | Value at last tick | Discrete | Breaks loops between discrete blocks |
| `hold(x)` | Sampled value at tick | Discrete | Explicit zero-order sample of a continuous signal |
| `t`, `Ts` | Time, clock period | `t` all, `Ts` discrete | Read only |

Determinism note: simulation and the target build run the same Julia function implementations. With the same Julia version, package manifest and CPU target, fixed-step results repeat bit for bit. They can differ across CPU architectures (for example in FMA use), so reference results are generated on the target itself.

## Ports, connections and bond graph elements

Two port kinds exist: directed signal ports and undirected power ports. A bond is a connection between two power ports; bond graph elements are ordinary blocks written in the language.

| Port kind | Declared in | Carries | Connection rule |
| --- | --- | --- | --- |
| Signal | `@inputs` / `@outputs` | One typed value | One output to many inputs; types and units must match |
| Power | `@ports` | Effort `e` and flow `f`, product = power | Exactly two ports per bond; domains must match |

Power ports carry a domain tag so connections are checked and units come for free:

| Domain | Effort | Flow |
| --- | --- | --- |
| `Electrical` | voltage \[V\] | current \[A\] |
| `Translation` | force \[N\] | velocity \[m/s\] |
| `Rotation` | torque \[N\*m\] | angular velocity \[rad/s\] |
| `Hydraulic` | pressure \[Pa\] | volume flow \[m^3/s\] |
| `Generic` | e | f |

A capacitor-type element, as it would appear in the standard library:

```julia
@block C begin
    @ports p::Power{Generic}
    @parameters c::Real = 1.0, [min = 0]
    @variables q::Real = 0.0, [state = :prefer]
    @equations begin
        ddt(q) ~ p.f
        p.e ~ q / c
    end
    @causality p => :effort_out   # preferred: integral causality
end
```

Rules for bond graph semantics:

- **Bond direction.** The half arrow sets positive power direction; the editor stores it, and the compiler uses it for signs in junction equations.
- **Causality.** `@causality` declares fixed (`Se`, `Sf`), preferred (`C`, `I`) or free (`R`) causality. Causality assignment (SCAP) runs on the flattened graph before symbolic reduction. Elements that end up in derivative causality are reported as warnings, because they raise the DAE index.
- **Junctions.** `0` and `1` junctions are n-port, so they are generated by the compiler rather than written per arity: a 0-junction gives equal efforts and signed flows summing to zero; a 1-junction the reverse.
- **TF and GY.** Two-port elements with a modulus parameter; modulated versions (`MTF`, `MGY`, `MSe`, `MSf`) take the modulus from a signal input, which is how block diagrams and bond graphs connect.
- **Iconic components.** Physical components (motors, springs, resistors) are blocks with power ports and the same equations, so they connect directly to bonds.

**Editor connection rules.** The editor only lets a connection be drawn between matching ports, and the compiler enforces the same rules (`E102`) for models edited as text.

- **Port kind:** signal to signal, power to power. Crossing between them needs an explicit element (`MSe`, `MSf`, a sensor).
- **Domain:** both power ports carry the same domain. Crossing domains goes through a `TF`, `GY` or converter component. `Generic` ports, as on bond graph elements, adopt the domain of their first concrete connection, and their parameter units follow (a `C` on an electrical bond takes farads).
- **Size:** scalar to scalar; `Vec{N}` only to `Vec{N}` with the same N.
- **Type:** `Real`, `Int` and `Bool` never mix implicitly; a conversion block makes it explicit.
- **Units:** equal units connect directly. Units of the same dimension (mm and m, rpm and rad/s) connect, and the compiler inserts a constant factor that the editor shows on the wire. Different dimensions are refused.
- **Direction:** a signal output may feed many inputs; an input has exactly one source.

While the user drags a connection, the editor highlights only compatible ports and shows the reason when a drop is refused.

## Component catalog

The standard library ships eight groups of components, each written in the language itself so users can open, copy and extend them. Release marks what ships in v0.1 and what follows; ports use the names from the ports section.

### Bond graph elements

All bond graph elements use `Generic` power ports and take their domain from the bonds they connect to.

| Element | Ports | Key parameters | Release |
| --- | --- | --- | --- |
| `Se` effort source | `p` | `e` | v0.1 |
| `Sf` flow source | `p` | `f` | v0.1 |
| `MSe` modulated effort source | `p`, input `u` | `gain` | v0.1 |
| `MSf` modulated flow source | `p`, input `u` | `gain` | v0.1 |
| `C` capacitive storage | `p` | `c`, initial `q` | v0.1 |
| `I` inertial storage | `p` | `i`, initial momentum | v0.1 |
| `R` resistor | `p` | `r` | v0.1 |
| `MR` modulated resistor | `p`, input `u` | `gain` | v0.1 |
| `TF` transformer | `p1`, `p2` | `n` | v0.1 |
| `MTF` modulated transformer | `p1`, `p2`, input `u` | none | v0.1 |
| `GY` gyrator | `p1`, `p2` | `r` | v0.1 |
| `MGY` modulated gyrator | `p1`, `p2`, input `u` | none | v0.1 |
| `0` junction (common effort) | n power ports | none, generated | v0.1 |
| `1` junction (common flow) | n power ports | none, generated | v0.1 |
| `De` effort detector | `p`, output `y` | none | v0.1 |
| `Df` flow detector | `p`, output `y` | none | v0.1 |
| `CC`, `II` multiport storage | n power ports | matrix | v0.2 |
| `RS` resistive source (thermal coupling) | `p`, thermal port | `r` | v0.2 |

Nonlinear variants (for example a C with a user-defined constitutive law) are made by copying the element and editing its equations.

### Signal sources and sinks

| Block | Ports | Key parameters | Release |
| --- | --- | --- | --- |
| Constant | output `y` | `value` | v0.1 |
| Step | output `y` | `t_step`, `initial`, `final` | v0.1 |
| Ramp | output `y` | `t_start`, `slope`, `initial` | v0.1 |
| Sine | output `y` | `amplitude`, `frequency`, `phase`, `offset` | v0.1 |
| Pulse / square | output `y` | `amplitude`, `period`, `duty`, `t_start` | v0.1 |
| Chirp | output `y` | `f_start`, `f_end`, `duration` | v0.1 |
| Time | output `y` | none | v0.1 |
| Time table | output `y` | data table, interpolation (`hold`, `linear`) | v0.1 |
| Noise | output `y` | `mean`, `std`, `seed`, sample `Ts` | v0.1 |
| Plot / scope sink | inputs `u[]` | none; marks signals for recording | v0.1 |
| Recorder | inputs `u[]` | decimation | v0.1 |

Noise is seeded and sampled on a fixed clock, so runs repeat bit for bit, in simulation and on the target.

### Continuous blocks

| Block | Ports | Key parameters | Release |
| --- | --- | --- | --- |
| Gain | `u`, `y` | `k` (scalar or matrix) | v0.1 |
| Sum | `u[]`, `y` | signs, e.g. `"+-+"` | v0.1 |
| Product / divide | `u[]`, `y` | operations | v0.1 |
| Integrator | `u`, `y`, optional `reset` | initial value, `lower`, `upper` limits | v0.1 |
| Filtered derivative | `u`, `y` | time constant | v0.1 |
| Transfer function | `u`, `y` | numerator, denominator | v0.1 |
| State space | `u`, `y` | `A`, `B`, `C`, `D`, initial state | v0.1 |
| First order / second order | `u`, `y` | `k`, `tau` / `k`, `w0`, `zeta` | v0.1 |
| Lead-lag | `u`, `y` | zero, pole, gain | v0.1 |
| PID | `u` (error), `y`, optional `track` | `Kp`, `Ti`, `Td`, `N`, limits, anti-windup | v0.1 |
| Saturation | `u`, `y` | `lower`, `upper` | v0.1 |
| Dead zone | `u`, `y` | `lower`, `upper` | v0.1 |
| Rate limiter | `u`, `y` | rising, falling rate | v0.1 |
| Backlash | `u`, `y` | width, initial output | v0.2 |
| Relay with hysteresis | `u`, `y` | on/off thresholds, on/off values | v0.1 |
| Lookup table 1D / 2D | `u` (or `u1`, `u2`), `y` | breakpoints, table, interpolation | v0.1 |
| Transport delay | `u`, `y` | delay `T` (constant) | v0.1 |
| Switch | `u1`, `u2`, `ctrl`, `y` | threshold | v0.1 |
| Min / max, abs, sign | `u[]`, `y` | none | v0.1 |
| Math function | `u`, `y` | one whitelisted function | v0.1 |
| Equation block | user-declared | user-declared | v0.1 |
| Subsystem | user-declared | user-declared | v0.1 |

The equation block and subsystem are the extension points: everything else in the library could be rebuilt from them.

### Discrete and logic blocks

Every discrete block takes a sample period `Ts`, and optionally an `offset`; the clock rules from the semantics section apply.

| Block | Ports | Key parameters | Release |
| --- | --- | --- | --- |
| Unit delay (z⁻¹) | `u`, `y` | initial value | v0.1 |
| Zero-order hold | `u`, `y` | `Ts` | v0.1 |
| Rate transition | `u`, `y` | input and output periods | v0.1 |
| Discrete integrator | `u`, `y`, optional `reset` | method (forward, backward, trapezoidal), limits | v0.1 |
| Discrete transfer function | `u`, `y` | numerator, denominator in z | v0.1 |
| Discrete state space | `u`, `y` | `A`, `B`, `C`, `D` | v0.1 |
| Discrete PID | `u`, `y`, optional `track` | as continuous PID, plus discretization method | v0.1 |
| FIR / IIR filter | `u`, `y` | coefficients | v0.1 |
| Quantizer | `u`, `y` | resolution | v0.1 |
| Counter | `trigger`, `reset`, `y` | limits, wrap | v0.1 |
| Compare | `u1`, `u2`, `y` (Bool) | operator | v0.1 |
| AND / OR / NOT / XOR | `u[]` (Bool), `y` (Bool) | none | v0.1 |
| Edge detect | `u` (Bool), `y` (Bool) | rising, falling, both | v0.1 |
| SR flip-flop | `set`, `reset`, `q` | dominant input | v0.1 |
| On-delay / off-delay timer | `u` (Bool), `y` (Bool) | delay | v0.1 |
| Type conversion | `u`, `y` | target type (`Real`, `Int`, `Bool`) | v0.1 |
| Discrete code block | user-declared | user-declared | v0.1 |
| State machine | user-declared | states, transitions | v0.2 |

### Electrical components

All ports are `Electrical`: voltage \[V\] and current \[A\].

| Component | Ports | Key parameters | Release |
| --- | --- | --- | --- |
| Resistor | `p`, `n` | `R` \[Ohm\] | v0.1 |
| Capacitor | `p`, `n` | `C` \[F\], initial voltage | v0.1 |
| Inductor | `p`, `n` | `L` \[H\], initial current | v0.1 |
| Ground | `p` | none | v0.1 |
| Voltage source (constant / signal-controlled) | `p`, `n`, optional input `u` | `V` | v0.1 |
| Current source (constant / signal-controlled) | `p`, `n`, optional input `u` | `I` | v0.1 |
| Ideal diode | `p`, `n` | `R_on`, `G_off`, `V_knee` | v0.1 |
| Ideal switch | `p`, `n`, input `ctrl` (Bool) | `R_on`, `G_off` | v0.1 |
| Ideal transformer | `p1`, `n1`, `p2`, `n2` | turns ratio | v0.1 |
| Ideal op-amp | `in_p`, `in_n`, `out` | none | v0.2 |
| Averaged H-bridge | `dc_p`, `dc_n`, `out_p`, `out_n`, input `duty` | none | v0.2 |
| Battery (equivalent circuit) | `p`, `n` | capacity, `R_internal`, OCV table | v0.2 |

### Mechanical translation and rotation

Translation ports carry force \[N\] and velocity \[m/s\]; rotation ports carry torque \[N\*m\] and angular velocity \[rad/s\].

| Component | Domain | Ports | Key parameters | Release |
| --- | --- | --- | --- | --- |
| Mass | Translation | `a`, `b` | `m` \[kg\], initial position and velocity | v0.1 |
| Spring | Translation | `a`, `b` | `k` \[N/m\], free length | v0.1 |
| Damper | Translation | `a`, `b` | `d` \[N\*s/m\] | v0.1 |
| Spring-damper | Translation | `a`, `b` | `k`, `d` | v0.1 |
| Fixed point | Translation | `a` | position | v0.1 |
| Force source | Translation | `a`, `b`, optional input `u` | `F` | v0.1 |
| Velocity source | Translation | `a`, optional input `u` | `v` | v0.1 |
| Friction (Coulomb, viscous, Stribeck) | Translation | `a`, `b` | static, Coulomb, viscous coefficients, Stribeck velocity | v0.1 |
| Hard stop | Translation | `a`, `b` | limits, contact stiffness, damping | v0.1 |
| Inertia | Rotation | `a`, `b` | `J` \[kg\*m^2\], initial angle and speed | v0.1 |
| Torsion spring | Rotation | `a`, `b` | `k` \[N\*m/rad\] | v0.1 |
| Rotational damper | Rotation | `a`, `b` | `d` \[N*m*s/rad\] | v0.1 |
| Fixed shaft | Rotation | `a` | angle | v0.1 |
| Torque source | Rotation | `a`, `b`, optional input `u` | `T` | v0.1 |
| Speed source | Rotation | `a`, optional input `u` | `w` | v0.1 |
| Rotational friction | Rotation | `a`, `b` | as translational friction | v0.1 |
| Ideal gear | Rotation | `a`, `b` | ratio | v0.1 |
| Gear with efficiency and backlash | Rotation | `a`, `b` | ratio, efficiency, backlash | v0.2 |
| Elastic shaft | Rotation | `a`, `b` | stiffness, damping | v0.1 |
| 3D rigid body and joints | Multibody (`Vec{3}` ports) | frames | mass, inertia tensor | v0.3, see Spatial mechanics |

Multibody components are specified in the Spatial mechanics section.

### Worked example: gear with backlash and efficiency

Backlash is modeled as a dead-zone spring on the relative angle across the gear: no torque inside the gap, stiff contact outside it. It stays an ordinary bond graph C element, conserves energy, and needs no switching between model structures.

| Approach | Energetic | Fixed-step export | Use for |
| --- | --- | --- | --- |
| Dead-zone spring (this example) | Yes | Yes, with small enough `dt` | Torque transmission in drivetrains |
| Hybrid impact model (free and contact modes, restitution law) | Yes | Hard: state count changes between modes | Rigid gears where impact dynamics matter |
| Play operator on a signal (catalog Backlash block) | No | Yes | Sensor and kinematic effects only |

Sign convention: power is positive into each port, so a torque T carried from `a` to `b` appears as `a.e = T` and `b.e = -T`.

```julia
@block GearBacklash begin
    @ports begin
        a::Power{Rotation}
        b::Power{Rotation}
    end
    @parameters begin
        k::Real   = 1e4,  [unit = "N*m/rad", min = 0]    # tooth contact stiffness
        d::Real   = 5.0,  [unit = "N*m*s/rad", min = 0]  # contact damping
        gap::Real = 0.01, [unit = "rad", min = 0]        # total backlash
    end
    @variables begin
        phi::Real = 0.0, [unit = "rad"]     # relative angle a minus b
        w::Real,         [unit = "rad/s"]
        T::Real,         [unit = "N*m"]
    end
    @equations begin
        w ~ a.f - b.f
        ddt(phi) ~ w
        # damping acts only in contact and never pulls the teeth together
        T ~ ifelse(phi >  gap/2, max(k*(phi - gap/2) + d*w, 0.0),
            ifelse(phi < -gap/2, min(k*(phi + gap/2) + d*w, 0.0), 0.0))
        a.e ~ T
        b.e ~ -T
    end
end

@block LossyGear begin
    @ports begin
        a::Power{Rotation}    # input shaft (fast)
        b::Power{Rotation}    # output shaft (slow)
    end
    @parameters begin
        n::Real   = 10.0                    # a.f = n * b.f
        eta::Real = 0.9, [min = 0, max = 1] # efficiency
    end
    @equations begin
        a.f ~ n * b.f
        # efficiency depends on power direction: driven from a, or back-driven from b
        b.e ~ -n * a.e * ifelse(a.e * a.f > 0, eta, 1/eta)
    end
end

@block GearWithBacklash begin
    @ports begin
        a::Power{Rotation}
        b::Power{Rotation}
    end
    @components begin
        gear = LossyGear(n = 10.0, eta = 0.9)
        play = GearBacklash(k = 1e4, d = 5.0, gap = 0.01)
    end
    @connections begin
        connect(a, gear.a)
        connect(gear.b, play.a)
        connect(play.b, b)
    end
end
```

Notes:

- **Placement:** the backlash sits on the output side, so `gap` and `k` are in output-shaft units, matching how datasheets state them.
- **Events:** in Julia simulation each `ifelse` condition becomes a zero-crossing event, so contact instants are located exactly. In fixed-step export the compiler reports `W203`, and contact is detected only at step boundaries.
- **Step size:** contact stiffness sets the fastest dynamics. Choose `dt` so one contact oscillation, about 2π·√(J/k), spans at least 10 to 20 steps, or use an implicit fixed-step integrator.
- **Efficiency switching:** near zero power the efficiency factor can chatter. If it shows up, replace the switch with a smooth blend over a small power band.
- **Parameters:** `k` comes from tooth mesh stiffness, `gap` from the datasheet backlash, and `d` is tuned to a realistic restitution.
- **Same pattern:** hard stops, couplings with play and compliant contact reuse this dead-zone structure.
- **Open item:** the textual subsystem scopes `@components` and `@connections` used here mirror what the editor saves, but they are not yet in the scopes table.

### Hydraulic and thermal

Hydraulic ports carry pressure \[Pa\] and volume flow \[m^3/s\]. Thermal is a v0.2 domain that uses the pseudo bond graph convention: temperature \[K\] and heat flow \[W\], whose product is not a power, so it never connects to the other domains except through `RS`-type couplings.

| Component | Domain | Ports | Key parameters | Release |
| --- | --- | --- | --- | --- |
| Pressure source | Hydraulic | `a`, optional input `u` | `p` | v0.1 |
| Flow source | Hydraulic | `a`, `b`, optional input `u` | `Q` | v0.1 |
| Tank (constant pressure) | Hydraulic | `a` | pressure | v0.1 |
| Volume (fluid compressibility) | Hydraulic | `a` | volume, bulk modulus | v0.1 |
| Orifice | Hydraulic | `a`, `b` | discharge coefficient, area, density | v0.1 |
| Pipe (lumped) | Hydraulic | `a`, `b` | length, diameter, friction model | v0.2 |
| Check valve | Hydraulic | `a`, `b` | cracking pressure, area | v0.2 |
| Proportional valve (4/3) | Hydraulic | `P`, `T`, `A`, `B`, input `spool` | flow gain, leakage | v0.2 |
| Heat capacity | Thermal | `a` | `C` \[J/K\], initial temperature | v0.2 |
| Thermal conductor | Thermal | `a`, `b` | `G` \[W/K\] | v0.2 |
| Convection | Thermal | `a`, `b` | `h`, area | v0.2 |
| Fixed temperature | Thermal | `a` | `T` | v0.2 |
| Heat flow source | Thermal | `a`, optional input `u` | `Q` | v0.2 |

### Domain converters, sensors and export interfaces

Converters are the only components with ports in two domains, which is what lets the editor rule out every other cross-domain connection.

| Component | Ports | Key parameters | Release |
| --- | --- | --- | --- |
| DC motor | Electrical `p`, `n`; Rotation `shaft`, `housing` | `R`, `L`, `k_t`, `J`, `d` | v0.1 |
| Ideal EM converter (gyrator) | Electrical `p`, `n`; Rotation `shaft` | `k` \[N\*m/A\] | v0.1 |
| Rack and pinion | Rotation `a`; Translation `b` | pinion radius | v0.1 |
| Ball screw | Rotation `a`; Translation `b` | lead \[m/rev\], efficiency | v0.1 |
| Wheel | Rotation `a`; Translation `b` | radius | v0.1 |
| Hydraulic cylinder | Hydraulic `A`, `B`; Translation `rod` | piston and rod areas, stroke, leakage | v0.1 |
| Hydraulic pump / motor | Hydraulic `a`, `b`; Rotation `shaft` | displacement, efficiency | v0.2 |
| Position, velocity, acceleration sensor | Translation `a`; output `y` | none | v0.1 |
| Angle, speed sensor | Rotation `a`; output `y` | none | v0.1 |
| Force / torque sensor | power `a`, `b`; output `y` | none | v0.1 |
| Voltage / current sensor | Electrical; output `y` | none | v0.1 |
| Pressure / flow sensor | Hydraulic; output `y` | none | v0.1 |
| Power sensor | any power domain `a`, `b`; output `y` | none | v0.1 |
| Temperature / heat flow sensor | Thermal; output `y` | none | v0.2 |
| Export input | output `y` | name, type, unit | v0.1 |
| Export output | input `u` | name, type, unit | v0.1 |
| Export parameter | none | name, links to a tunable parameter | v0.1 |

Export inputs and outputs define the interface of the generated step function, the FMU and the ctrlX Data Layer nodes, so their names are what the controller, SIL harness and 3D bindings refer to.

## Continuous, discrete and event semantics

A model is a hybrid system: one continuous DAE, plus clocked discrete partitions, plus events. The same semantics hold in Julia simulation and in exported code, except where noted.

**Continuous.** All `@equations` across the flattened model form one DAE in time `t`. The compiler sorts, reduces and solves it; equation order in the source has no meaning.

**Discrete clocks.**

- Each `@discrete` scope runs on a periodic clock with period `Ts` and optional `offset`.
- All periods in one model must be integer multiples of a base tick (their greatest common divisor). This makes the schedule fixed and repeatable.
- Reading a continuous variable in discrete code samples it at the tick. Discrete outputs are held constant between ticks (zero-order hold).

**Order at a tick.** When several discrete blocks fire at the same tick:

1. Sample all continuous values the discrete blocks read.
2. Run discrete blocks in dependency order (topologically sorted on their signal connections).
3. Reject cycles between discrete blocks unless one link goes through `previous(x)`.
4. Publish the new held outputs, then continue continuous integration.

**Events.**

- `@events` declares `condition => begin … end` pairs. A condition crossing zero from negative to positive fires the body once; `reinit(x, v)` resets a state.
- Nonsmooth functions in equations (`abs`, `sign`, `min`, `max`, `ifelse`, `floor`) create zero-crossing events in Julia variable-step simulation, so switching instants are located accurately.
- Exported fixed-step code does not locate events: it evaluates conditions once per step. The compiler reports every such site, so differences between simulation and target are visible, not silent.

**Fixed-step export.** Every discrete period must be an integer multiple of the solver step `dt`. The exported step function advances exactly one `dt`, and runs any discrete blocks due at the end of that step.

## Compilation pipeline

&#91;embedded content: compilation pipeline · 6 stages, 3 outputs\]

Every editor view passes through the same validation and reduction, so simulation and the target build always model the same system. The dashed link is the CI check that the fixed-step target build matches variable-step simulation within tolerance. C++ export is shown as a possible future output.

## Validation rules and error reporting

Validation runs in two passes: per block right after parsing (fast, runs as the user types), and on the flattened model before symbolic reduction.

| Code | Pass | Rule | Example message |
| --- | --- | --- | --- |
| `E001` | Block | Syntax node not allowed in this scope | `while` loops are not allowed in `@discrete` |
| `E002` | Block | Function not on the whitelist | `rand` is not a built-in function |
| `E003` | Block | Undeclared or shadowed name | `Kp` is used but not declared |
| `E004` | Block | Type mismatch | `Bool` value used in arithmetic |
| `E005` | Block | Size not static, or index out of range | `v[4]` but `v` is `Vec{3}` |
| `E006` | Block | Unit inconsistency | Adding \[N\] to \[m/s\] |
| `E101` | Model | Unconnected port or input | Input `e` of `PI1` is not connected |
| `E102` | Model | Domain or type mismatch on a connection | `Electrical` port bonded to `Rotation` port |
| `E103` | Model | Unbalanced system | 14 unknowns, 13 equations; check `Motor1` |
| `E104` | Model | Discrete clock not a multiple of base tick or `dt` | `Ts = 0.0015` with `dt = 0.001` |
| `E105` | Model | Cycle between discrete blocks | Add `previous()` on one link |
| `W201` | Model | Derivative causality | `I2` is in derivative causality; DAE index raised |
| `W202` | Model | Algebraic loop torn | Loop through `R1`, `R3` solved iteratively |
| `W203` | Model | Event not located in fixed-step export | `abs` in `Friction1` switches between steps |
| `W204` | Block | Unused declaration | `x` is declared but never used |

Every diagnostic carries the block path (for example `Plant/Motor1`), scope, line and column in the user's source, the code, the message, and a fix hint where one exists. The editor highlights the element on the canvas and the line in the code view.

## Visualization and bindings

The 3D viewer (Babylon.js) shows an SDFormat-style scene, and simulation values reach it only through declarative bindings. The viewer does no physics: any derived quantity it needs is a model output, validated and exported with everything else.

**Scene format.** A subset of SDFormat, parsed in the browser:

| SDF element | Supported in v0.1 | Babylon.js mapping |
| --- | --- | --- |
| `model`, nested `model` | Yes | Root `TransformNode` per model |
| `link` with `pose` | Yes | `TransformNode` |
| `visual` with `mesh`, `box`, `cylinder`, `sphere` | Yes | Mesh under its link |
| `joint`: `revolute`, `continuous`, `prismatic`, `fixed` | Yes | Parent-child transform along the joint axis |
| `joint`: `ball`, `universal`, `screw` | Later |  |
| `frame` | Yes | Named `TransformNode`, usable as a binding target |
| `collision`, `inertial`, `sensor`, `plugin` | Ignored | The viewer does not simulate |

- Meshes are converted to glTF on upload; the viewer loads only glTF.
- SDF is right-handed and Z-up, while Babylon.js defaults to left-handed and Y-up. The viewer sets `scene.useRightHandedSystem = true` and rotates one root node to Z-up.
- Units are SI throughout: metres and radians.

**Binding schema.** Bindings are stored with the model and reference names only, never solver internals:

```json
{ "bindings": [
  { "target": "joint:shoulder", "property": "position",
    "signal": "Plant/Arm/phi1", "gain": 1.0, "offset": 0.0 },
  { "target": "link:cart", "property": "pose",
    "signal": ["Plant/Cart/x", "Plant/Cart/y", "Plant/Cart/z",
               "Plant/Cart/qw", "Plant/Cart/qx", "Plant/Cart/qy", "Plant/Cart/qz"] },
  { "target": "visual:force_arrow", "property": "scale.z",
    "signal": "Plant/Gripper/F", "gain": 0.01 },
  { "target": "visual:motor_body", "property": "color",
    "signal": "Plant/Motor1/T_winding", "colormap": "heat", "range": [20, 120] }
]}
```

| Property | Targets | Signals | Unit check |
| --- | --- | --- | --- |
| `position` | Revolute or continuous joint | 1 | rad |
| `position` | Prismatic joint | 1 | m |
| `pose` | Link or frame | 7: position + unit quaternion | m, dimensionless |
| `scale.x`, `scale.y`, `scale.z` | Visual | 1 | Any, after `gain` |
| `color` | Visual | 1, with `colormap` and `range` | Any |
| `visible` | Visual or link | 1 Bool | None |

- Only `gain` and `offset` are allowed; any other math belongs in the model as an output.
- Validation: every target must exist in the scene, every signal in the model's outputs or variables, and units must match the property. Errors use the same diagnostic format as model validation.
- A binding to a signal removed by symbolic reduction keeps working, because the compiler retains every bound signal as an observable.

&#91;embedded content: visualization data path · 3 sources, 1 stream\]

Switching between Julia simulation, SIL and the real controller changes only the source; the bindings and the scene stay the same.

**Stream format.** One format serves every source:

1. **Handshake** (JSON, once per session): ordered list of signal IDs, their units, and the source sample rate.
2. **Frames** (binary, little-endian): `[t, v1 … vn]` as `Float64`, in handshake order. Pose quaternions arrive as four separate signals.
3. **Rate:** the server decimates to the display rate, 60 Hz by default. The simulation never waits for the viewer.
4. **Playback files** use the same layout in columnar form: one time vector plus one array per signal, so recorded and live runs share a code path.

**Viewer loop.** Each render frame, the viewer advances its own playback clock, finds the bracketing samples by binary search, interpolates (linear for scalars, slerp for quaternions), and applies every binding. Scrubbing, pause and slow motion only change the playback clock.

## Spatial mechanics (screw theory)

Robots are modeled with multibond graphs: bonds that carry a twist as flow and a wrench as effort, so every element from this spec carries over in matrix-valued form. Planar mechanics ships in v0.2 and full spatial mechanics in v0.3; both follow the coordinate-free, screw-based bond graph approach that 20-sim's 3D mechanics is rooted in.

### Types and domains

Two new power domains carry screws instead of scalars. Screws are ordered angular part first, then linear part, throughout.

| Domain | Effort (wrench) | Flow (twist) | Port size | Release |
| --- | --- | --- | --- | --- |
| `Planar` | (τ \[N\*m\], fx \[N\], fy \[N\]) | (ω \[rad/s\], vx \[m/s\], vy \[m/s\]) | `Vec{3}` | v0.2 |
| `Spatial` | (τ \[N\*m\], f \[N\]) | (ω \[rad/s\], v \[m/s\]) | `Vec{6}` | v0.3 |

Units are checked per component, so a wrench is not a vector of one unit.

| Type | Meaning | Julia representation |
| --- | --- | --- |
| `SE2` | Planar pose | angle + `SVector{2}` position |
| `SE3` | Spatial pose | `SMatrix{3,3}` rotation + `SVector{3}` position |
| `Twist{F}` | Twist expressed in frame F | `SVector{3}` or `SVector{6}` |
| `Wrench{F}` | Wrench expressed in frame F | `SVector{3}` or `SVector{6}` |
| `Inertia` | Spatial inertia, symmetric positive definite | `SMatrix{6,6}` |

The stored representation of `SE3` in exported code is an open decision (see below); the language type is the same either way.

### Frame typing

Every pose, twist and wrench carries frame tags, and the validator checks them the way it checks units. Mixing frames without an explicit transformation is a compile error (`E007`), which removes a whole class of robotics bugs.

| Declaration | Meaning |
| --- | --- |
| `SE3{:a, :b}` | Pose of frame b expressed in frame a |
| `Twist{:i, :j, :k}` | Twist of body i relative to j, expressed in k |
| `Wrench{:k}` | Wrench expressed in frame k |
| `Power{Spatial, :k}` | Power port whose twist and wrench are expressed in k |

Rules:

- **Sum and equation:** both sides must be expressed in the same frame.
- **Composition:** twists chain only through a shared frame: `Twist{:i,:j,:k} + Twist{:j,:l,:k}` gives `Twist{:i,:l,:k}`.
- **Change of frame:** `Ad(H)` with `H::SE3{:a,:b}` maps a twist expressed in b to one expressed in a. Wrenches use the dual, `transpose(Ad(H))`, in the opposite direction.
- **Power:** `dot(W, T)` requires W and T expressed in the same frame.
- **Bonds:** two spatial ports connect only if their frames match; otherwise an `Ad` element sits between them.

A rigid body as it would appear in the library:

```julia
@block RigidBody begin
    @ports p::Power{Spatial, :body}      # twist and wrench in body frame
    @parameters begin
        m::Real = 1.0, [unit = "kg"]
        Ic::Mat{3,3} = [0.01 0 0; 0 0.01 0; 0 0 0.01], [unit = "kg*m^2"]
    end
    @variables begin
        H::SE3{:world, :body} = SE3(), [state = :prefer]   # pose of body in world
        P::Wrench{:body}                                    # momentum co-screw
    end
    @equations begin
        ddt(H) ~ H * hat(p.f)                    # kinematics on SE(3)
        P ~ spatial_inertia(m, Ic) * p.f
        ddt(P) ~ p.e + transpose(ad(p.f)) * P    # Newton-Euler, body frame
    end
end
```

### Screw element catalog

Each element is the matrix-valued counterpart of a bond graph element. Planar versions ship first and share the same names.

| Element | Bond graph role | Ports | Key parameters | Release |
| --- | --- | --- | --- | --- |
| World frame | Fixed reference | `p` | none | v0.2 |
| Rigid body | `I` | `p` | mass, center of mass, inertia | Planar v0.2, Spatial v0.3 |
| Frame offset | `MTF` with constant `Ad` | `a`, `b` | fixed pose | v0.2 |
| Frame transform | `MTF` with `Ad(H)` | `a`, `b`, input `H` | none | v0.2 |
| Spatial spring | `C` | `a`, `b` | stiffness matrix or geometric potential, rest pose | v0.2 |
| Spatial damper | `R` | `a`, `b` | damping matrix | v0.2 |
| Gravity | `Se` per body | `p` | gravity vector | v0.2 |
| Revolute joint | `MTF` from scalar to screw | `parent`, `child`, Rotation `drive` | axis, offset, limits | v0.2 |
| Prismatic joint | `MTF` from scalar to screw | `parent`, `child`, Translation `drive` | axis, offset, limits | v0.2 |
| Fixed joint | Rigid connection | `parent`, `child` | offset pose | v0.2 |
| Spherical, universal, planar joints | Multi-DOF `MTF` | `parent`, `child`, drives | axes | v0.3 |
| Compliant joint | Joint plus stiff spatial spring | `parent`, `child` | stiffness, damping | v0.3 |
| Point contact (compliant) | Nonlinear `C` and `R` | `a`, `b` | stiffness, damping, friction | Later |
| Pose, twist, wrench sensors | Detectors | `p`; output `SE3` / `Vec{6}` | frame to report in | v0.2 |

Actuation needs no special component: a DC motor's Rotation port connects to a revolute joint's `drive` port, through a gear if needed.

### Function additions

These join the whitelist under the same rule: each needs an allocation-free, trim-compatible implementation and a golden test. All are registered with Symbolics as opaque functions, so symbolic reduction treats them as single operations instead of expanding them into thousands of scalar terms.

| Function | Meaning | Scopes | Implementation |
| --- | --- | --- | --- |
| `hat(T)`, `vee(M)` | Twist to matrix form and back | All | Inline, fixed size |
| `Ad(H)` | Adjoint: changes the frame of a twist | All | Inline 6×6 (3×3 planar) |
| `ad(T)` | Small adjoint (Lie bracket) of a twist | All | Inline |
| `exp(T)`, `log(H)` | Exponential and logarithm on SE(2) / SE(3) | All | Closed form, small-angle branch |
| `H1 * H2`, `inv(H)` | Pose composition and inverse | All | Inline |
| `spatial_inertia(m, Ic, c)` | Builds a 6×6 inertia from mass, inertia and center of mass | All | Inline |
| `SE3(R, p)`, `rotation(H)`, `translation(H)` | Construct and take apart poses | All | Inline |
| `pose_of(:frame)` | Forward kinematics of a named frame | Discrete | Generated from the kinematic tree |
| `jacobian(:frame)` | Geometric Jacobian of a named frame | Discrete | Generated from the kinematic tree |

`pose_of` and `jacobian` are available in discrete scopes so controller code can use kinematics computed from the same model it is tested against. The compiler generates them per model; they are not general-purpose functions.

### Compilation strategy

The same model compiles two ways: as a flattened DAE for simulation, and as a recursive algorithm for the fixed-step target build. CI compares the two, as it compares every target build with simulation.

- **Pose states.** A pose evolves on SE(3), not on a vector space: Ḣ = H · hat(T). The integrator must keep it a valid pose. Options are a Lie-group integrator (Runge-Kutta-Munthe-Kaas or Crouch-Grossman) or a quaternion plus position with renormalization each step. One choice applies to simulation and the target build.
- **Dependent inertias.** Bodies joined by rigid joints put inertias in derivative causality, the classic multibond graph problem. In Julia simulation, index reduction handles it. The compiler reports it as `W201`, as for scalar bond graphs.
- **Open chains in export.** For serial and tree-structured robots, the exporter generates a recursive Newton-Euler or articulated-body step from the kinematic tree instead of a flattened DAE. Cost grows linearly with the number of bodies, and there are no algebraic loops.
- **Closed chains.** Loops create index-3 constraints. They are supported through index reduction in simulation; for export the user either accepts constraint stabilization or replaces one joint with a compliant joint.
- **Planar first.** Planar mechanics exercises all of the above (frame typing, Lie-group states, recursive export) at a fraction of the cost, so it ships and is validated one release before spatial.

### SDF import, visualization and open decisions

The SDF file that drives the 3D viewer also generates the mechanical model, so the visual and physical robot cannot drift apart.

- **Import:** SDF `link` elements become rigid bodies, using their `inertial` data (ignored by the viewer, used here). `joint` elements become joints with their axes and limits, and `pose` elements become frame offsets. `collision` stays ignored until contact ships.
- **Round trip:** the generated model is ordinary language code. Users add motors, gears, friction and controllers around it in the editor.
- **Visualization:** an `SE3` signal binds directly to a link's `pose` property, replacing the seven-signal form. Joint angle bindings are unchanged.

Open decisions for this extension:

- Pose state and integrator in exported code: Lie-group integrator, or quaternion plus position with renormalization?
- Screw ordering: angular first, as written here, or linear first, which some libraries use? Fixing it once avoids silent errors at every import and export.
- Frame-tag syntax: type parameters as written here, or attributes such as `[frame = :body]`, which are lighter for users?
- Recursive export algorithms: generated directly from the kinematic tree, or derived through ModelingToolkit?
- Closed-chain support in exported code: required for v0.3, or deferred?

## Versioning, open questions and next steps

Every saved model and library block records the language version it was written for, using semantic versioning. A minor version only adds constructs; a major version may change meaning and ships with an automatic migration, written as a syntax-tree rewrite and tested on the standard library.

**Open questions**

- Is `~` acceptable to users coming from 20-sim, who write `=` for equations? Alternative: accept `=` in `@equations` and translate it.
- Units: adopt Unitful.jl for checking, or keep a small dimension checker of our own that stays trim-compatible in the target build?
- Discrete scheduling: use ModelingToolkit clocks, or run our own scheduler around the continuous part? Needs a multi-rate prototype.
- Bit-exact results across CPU architectures (x86 and ARM64 targets): required, or is repeatability per target enough?
- Matrix size limits in equations: is a cap needed to keep symbolic reduction fast?
- Should `delay` be offered in variable-step simulation, or stay export-only?

**Next steps**

- [ ] Write the formal grammar as a whitelist over Julia syntax nodes, per scope
- [ ] Define the JSON model schema the web editor saves
- [ ] Prototype parser and validator on five library elements: `C`, `I`, `R`, `Se`, PI controller
- [ ] Implement the whitelist as allocation-free, trim-compatible Julia, with golden tests per function
- [ ] Prototype multi-rate discrete scheduling and decide the clock question
- [ ] Run an end-to-end DC motor model through simulation and the target build on real-time Linux, and compare outputs
