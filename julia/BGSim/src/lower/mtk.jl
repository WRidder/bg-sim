"""
    mtk_variable(name::AbstractString) -> Num

Create a ModelingToolkit unknown `name(t)` from a string, for example
`mtk_variable("motor.omega")`.

This is the documented equivalent of `only(@variables \$(Symbol(name))(t))`. It is how the
lowering stage (plan section 5.8) turns a bg-sim signal ID into a symbolic variable; the
caller keeps the `Dict{String, Num}` from signal ID to variable and never parses MTK's
generated names.

The name is used verbatim, so a bg-sim signal ID such as `"motor.omega"` survives the
round trip (verified: it prints as `var"motor.omega"(t)` and `signal_name` gives it back).
Two calls with the same string produce the same symbolic variable (`isequal` is `true`).

Note: symbolic variables must never be compared with `==`; in Symbolics `==` builds an
`Equation`. Use `isequal`.
"""
function mtk_variable(name::AbstractString)::Num
    isempty(name) &&
        throw(ArgumentError("a signal name must not be empty"))
    sym = Symbol(name)
    return only(@variables $(sym)(t))
end

"""
    mtk_parameter(name::AbstractString) -> Num

Create a ModelingToolkit parameter from a string, for example `mtk_parameter("motor.R")`.

Parameters are time independent (`@parameters`), so they are not called with `t`. Every
bg-sim parameter stays a runtime MTK parameter (plan decision D4), which is what makes a
parameter-only re-run possible through `remake` (see `julia/BGSim/NOTES.md`).
"""
function mtk_parameter(name::AbstractString)::Num
    isempty(name) &&
        throw(ArgumentError("a parameter name must not be empty"))
    sym = Symbol(name)
    return only(@parameters $(sym))
end

"""
    mtk_discrete(name::AbstractString) -> Num

Create a ModelingToolkit discrete variable from a string, for example
`mtk_discrete("motor.mode")`.

This is the documented equivalent of `only(@discretes \$(Symbol(name))(t))`. A discrete is a
*time-dependent parameter* (`isparameter` is `true`), which is what events are allowed to
write to: it must be passed in the parameter list of the `System`, not in the unknown list,
and an affect that writes it must list it in the callback's `discrete_parameters`.
"""
function mtk_discrete(name::AbstractString)::Num
    isempty(name) &&
        throw(ArgumentError("a discrete name must not be empty"))
    sym = Symbol(name)
    return only(@discretes $(sym)(t))
end

"""
    signal_name(x) -> String

Return the plain name of a symbolic variable, parameter or observed quantity as a
`String`, for example `signal_name(mtk_variable("motor.omega")) == "motor.omega"`.

This is the inverse of [`mtk_variable`](@ref)/[`mtk_parameter`](@ref) and is what the
recorder uses to map an MTK quantity back to a bg-sim signal ID. It never parses a
generated name: it reads the `VariableSource` metadata through
`SymbolicIndexingInterface.getname`.
"""
signal_name(x) = String(getname(x))

# ---------------------------------------------------------------------------------------
# Lowering a flat model to a compiled MTK system (plan section 5.8)
# ---------------------------------------------------------------------------------------

using SHA: sha256

"""
    nonsmooth_conditions(flat) -> Vector{BGSim.Expr}

The switching conditions that must become condition-only continuous events (plan 5.8): every
`ifelse`, `abs`, `sign`, `min`, `max`, `clamp`, `saturate`, `deadzone`, `floor`, `ceil` and
`round` in the continuous equations. Each returned expression is a real expression whose
upward zero crossing is the switching instant; `lower_flat` turns each into a
`SymbolicContinuousCallback(c ~ 0)` with no affect.

This is the J2.3 seam: the structural walk lives in `src/compile/events.jl`, and this method
is the BGSim-level name the J1.5 seam and the export use.
"""
nonsmooth_conditions(flat::Flat.FlatModel) = Compile.nonsmooth_conditions(flat)

"""    CompiledModel

One compiled model in the structural cache: the `mtkcompile`d `System`, the `ODEProblem` it
was built into (with the parameter values of that build), the signal-id → variable maps and
the extra `int` states. A cache hit reuses all of this and only remakes the problem (D4).
"""
struct CompiledModel
    key::String
    system::Any
    problem::Any
    vars::Dict{String,Num}
    params::Dict{String,Num}
    int_states::Vector{Pair{Num,Any}}
    algebraic::Bool
end

# The compile cache of plan 5.8, bounded by J2.8. The key is structural (see `compile_key`);
# parameter values and start values are deliberately absent, which is what makes a
# parameter-only re-run hit the cache. The policy is a bounded LRU: `COMPILE_ORDER` holds the
# keys least recently used first, a hit moves its key to the end, and an insertion past
# `COMPILE_CACHE_LIMIT` evicts the oldest entry. The limit keeps a long-lived worker bounded;
# `clear_compile_cache!` (`cache.clear` in the worker protocol) empties it completely.
const COMPILE_CACHE = Dict{String,CompiledModel}()
const COMPILE_ORDER = String[]
const COMPILE_CACHE_LIMIT = 8
const COMPILE_LOCK = ReentrantLock()
# A cumulative count of *real* compiles (`mtkcompile` + `ODEProblem`), never cache hits. The
# tests use it to prove that a repeated or parameter-only run did not recompile.
const COMPILE_BUILDS = Ref(0)

"""    cache_size() -> Int

The number of compiled models currently in the structural cache."""
cache_size() = lock(COMPILE_LOCK) do
    length(COMPILE_CACHE)
end

"""    compile_cache_limit() -> Int

The maximum number of compiled models the structural cache keeps (J2.8)."""
compile_cache_limit() = COMPILE_CACHE_LIMIT

"""    compile_build_count() -> Int

How many models this process has actually compiled (`mtkcompile` + `ODEProblem`) since it
started. A cache hit does not increment it, so a test can assert "this re-run did not
recompile" without timing. It is cumulative: capture it before an operation and compare.
`clear_compile_cache!` does not reset it."""
compile_build_count() = COMPILE_BUILDS[]

"""    compile_cache_keys() -> Vector{String}

The structural keys in the cache, least recently used first. A read-only snapshot for tests
and diagnostics; do not mutate it."""
compile_cache_keys() = lock(COMPILE_LOCK) do
    copy(COMPILE_ORDER)
end

"""    clear_compile_cache!()

Empty the structural cache. The worker calls this for `cache.clear`."""
function clear_compile_cache!()
    lock(COMPILE_LOCK) do
        empty!(COMPILE_CACHE)
        empty!(COMPILE_ORDER)
    end
    return nothing
end

# Drop one entry from both the map and the LRU order. The lock is assumed held, but the
# function takes it again (a `ReentrantLock`), so the tests may call it directly too.
function _cache_remove!(key::String)
    lock(COMPILE_LOCK) do
        delete!(COMPILE_CACHE, key)
        index = findfirst(==(key), COMPILE_ORDER)
        index === nothing || deleteat!(COMPILE_ORDER, index)
    end
    return nothing
end

function _cache_store!(key::String, model::CompiledModel)
    lock(COMPILE_LOCK) do
        # A duplicate key can only come from a caller that stored it by hand (the builds go
        # through `lower_model`, which looks the key up first); keep the order canonical.
        haskey(COMPILE_CACHE, key) && _cache_remove!(key)
        COMPILE_CACHE[key] = model
        push!(COMPILE_ORDER, key)
        while length(COMPILE_ORDER) > COMPILE_CACHE_LIMIT
            old = popfirst!(COMPILE_ORDER)
            delete!(COMPILE_CACHE, old)
        end
    end
    return nothing
end

function _cache_touch!(key::String)
    lock(COMPILE_LOCK) do
        index = findfirst(==(key), COMPILE_ORDER)
        index === nothing && return nothing
        deleteat!(COMPILE_ORDER, index)
        push!(COMPILE_ORDER, key)
    end
    return nothing
end

# ---------------------------------------------------------------------------------------
# The structural hash
# ---------------------------------------------------------------------------------------

_key_unit(u) = u === nothing ? "" : Units.unit_string(u)

function _key_attrs(attrs::AbstractDict)
    io = IOBuffer()
    for k in sort!(collect(keys(attrs)); by = string)
        print(io, string(k), '=', repr(attrs[k]), ';')
    end
    return String(take!(io))
end

"""
    compile_key(flat::Flat.FlatModel) -> String

The structural hash of plan 5.8 and the compile-cache key of J2.8, as 64 lowercase hex
characters (the `modelHash` shape of the run manifest). It hashes every input of the lowering
— plus the topology that produced them — so two flat models with the same compiled MTK system
always share a key, and a structural edit always changes it (conservatively: an edit that
cannot change the system may still miss):

| section | hashed | why |
| --- | --- | --- |
| variables | id, kind, type, unit, attrs | declarations and the MTK unknown list/order |
| parameters | id, name, type, unit, attrs | the MTK parameter list; `attrs[:kind]` selects a discrete |
| equations, initial | lowered ASTs, in order | the system's equation list and initialization |
| events, discrete | each item's canonical `show` | `SymbolicContinuousCallback`s and the discrete partitions |
| derived, signals | id, kind, type, unit, expr / recording order | the power observables and the recorder |
| instances | path, block ref | a different block is a different model, even with equal equations |
| connections | kind, both resolved paths/ports, domain, unit factor | topology |
| junctions | path, kind, bond ports/direction/`eids`/`fids` | bond-graph topology |

Deliberately **not** hashed:

* **parameter values** (D4: every parameter stays a runtime MTK parameter, so `remake` applies
  the new value) and **start values** (initial guesses, not structure);
* editor metadata that cannot change the compiled system: node/connection ids, positions,
  source ranges, origin block paths and comments. Editing a comment or moving a node must not
  force a recompile.

A structural edit (topology, a block reference, an array size from a `@constants` value, an
equation, an `@events`/`@discrete` body) changes one of the sections above and misses the
cache. A constant that only feeds a *parameter default* folds into that parameter's value at
flattening time, so it keeps the key and is applied by `remake` like any other parameter.
"""
function compile_key(flat::Flat.FlatModel)
    io = IOBuffer()
    print(io, "bg-sim-structure-v2\n")
    for v in flat.variables
        print(io, "v\t", v.id, '\t', v.kind, '\t', v.type, '\t', _key_unit(v.unit), '\t',
            _key_attrs(v.attrs), '\n')
    end
    for p in flat.parameters
        print(io, "p\t", p.id, '\t', p.name, '\t', p.type, '\t', _key_unit(p.unit), '\t',
            _key_attrs(p.attrs), '\n')
    end
    for e in flat.equations
        print(io, "e\t", sprint(show, e.lhs), '\t', sprint(show, e.rhs), '\n')
    end
    for e in flat.initial
        print(io, "i\t", sprint(show, e.lhs), '\t', sprint(show, e.rhs), '\n')
    end
    for e in flat.events
        print(io, "ev\t", sprint(show, e), '\n')
    end
    for e in flat.discrete
        print(io, "d\t", sprint(show, e), '\n')
    end
    for d in flat.derived
        print(io, "dv\t", d.id, '\t', d.kind, '\t', d.type, '\t', _key_unit(d.unit), '\t',
            sprint(show, d.expr), '\n')
    end
    for s in flat.signals
        print(io, "s\t", s.id, '\t', s.kind, '\t', s.type, '\t',
            s.unit === nothing ? "" : String(s.unit), '\t',
            s.path === nothing ? "" : String(s.path), '\n')
    end
    # Topology (J2.8). The equations already encode this, but the extra sections make the
    # invalidation rule explicit and cover edits that leave the equations unchanged, such as
    # swapping a block reference for one with identical behavior. Editor ids are excluded.
    for i in flat.instances
        print(io, "n\t", i.path, '\t', i.ref, '\n')
    end
    for c in flat.connections
        print(io, "c\t", c.kind, '\t', c.from_path, '\t', _key_port(c.from_port), '\t',
            c.to_path, '\t', _key_port(c.to_port), '\t',
            c.domain === nothing ? "" : String(c.domain), '\t',
            c.factor === nothing ? "" : repr(c.factor), '\n')
    end
    for j in flat.junctions
        print(io, "j\t", j.path, '\t', j.kind, '\n')
        for b in j.bonds
            print(io, "b\t", _key_port(b.port), '\t', b.into ? "1" : "0", '\t',
                b.flip ? "1" : "0", '\t', join(b.eids, ','), '\t', join(b.fids, ','), '\n')
        end
    end
    return bytes2hex(sha256(take!(io)))
end

_key_port(port::Nothing) = ""
_key_port(port) = string(port)

# ---------------------------------------------------------------------------------------
# Expression lowering for a whole flat model
# ---------------------------------------------------------------------------------------

"""
    lower_flat(flat) -> NamedTuple

Lower every continuous equation of `flat` (including the derived power signals and the
`int` sugar) to Symbolics. Returns the maps and the extra state/equation lists; it does not
build an MTK system yet, which keeps the expression walker testable on its own.
"""
function lower_flat(flat::Flat.FlatModel)
    vars = Dict{String,Num}()
    for v in flat.variables
        vars[v.id] = mtk_variable(v.id)
    end
    for d in flat.derived
        vars[d.id] = mtk_variable(d.id)
    end
    params = Dict{String,Num}()
    for p in flat.parameters
        # A held discrete output is an MTK *discrete* (a time-dependent parameter, D4); every
        # other parameter stays a plain runtime parameter.
        params[p.id] = get(p.attrs, :kind, nothing) === :discrete ?
                       mtk_discrete(p.id) : mtk_parameter(p.id)
    end

    ctx = LowerCtx(vars, params)
    eqs = Symbolics.Equation[]
    for e in flat.equations
        ctx.origin = e.origin
        lhs = lower_expression(e.lhs, ctx)
        rhs = lower_expression(e.rhs, ctx)
        push!(eqs, lhs ~ rhs)
    end
    for d in flat.derived
        ctx.origin = nothing
        push!(eqs, vars[d.id] ~ lower_expression(d.expr, ctx))
    end
    append!(eqs, ctx.int_equations)

    initial = Symbolics.Equation[]
    for e in flat.initial
        ctx.origin = e.origin
        lhs = lower_expression(e.lhs, ctx)
        rhs = lower_expression(e.rhs, ctx)
        push!(initial, lhs ~ rhs)
    end

    # `@events` (plan D19, section 5.8): rising-edge zero crossings with the final
    # assignment map as the affect; then one condition-only callback per nonsmooth kink.
    events = Any[]
    append!(events, Compile.event_callbacks(flat, ctx))
    # A model with no continuous state has nothing to integrate: every signal is an exact
    # algebraic function of `t` and the parameters, so landing the integrator on a kink of an
    # `ifelse`/`abs`/... cannot improve any value. MTK's compiled scalar condition also
    # writes its result into `tmp[1]` of an empty state cache and reads it back, which throws
    # a BoundsError inside the first `step!` (plan/STATUS.md NOTE-4 gap 3: a `t`-dependent
    # source with no states used to fail E901 with "no states were available"). Condition-only
    # callbacks are therefore skipped for a stateless model; the model runs, with exact
    # values and without the extra left/right event rows. `@events` affects are unaffected:
    # they change values, so `simulate` refuses a stateless model that has one with E901
    # up front (the solver's event root finder needs a state) instead of failing inside
    # `step!` with a confusing BoundsError.
    if flat.stats.states > 0 || !isempty(ctx.int_states)
        for c in nonsmooth_conditions(flat)
            ctx.origin = nothing
            ctx.event_values = nothing
            push!(events, SymbolicContinuousCallback(lower_expression(c, ctx) ~ 0))
        end
    end

    return (; vars, params, eqs, initial, events, int_states = ctx.int_states, ctx)
end

# ---------------------------------------------------------------------------------------
# Operating point and parameters
# ---------------------------------------------------------------------------------------

function _number(value, what::AbstractString)
    value isa Bool && return value ? 1.0 : 0.0
    value isa Real && return Float64(value)
    throw(LowerError("$what is not a real number", nothing))
end

_var_name(x) = try
    signal_name(x)
catch
    sprint(show, x)
end

function _int_start(expr, flat::Flat.FlatModel)
    env = Dict{Symbol,Any}(Symbol(p.id) => p.value for p in flat.parameters)
    ok, value = try_eval_const(expr, env)
    ok || throw(LowerError(
        "the start value of `int` is not a constant expression: " * String(value), nothing
    ))
    return _number(value, "the start value of `int`")
end

# The operating point must contain exactly the compiled **differential** unknowns. An
# algebraic unknown is not a state: MTK solves it from the equations at t0, and passing a
# value for it turns that value into an initialization equation (one equation, no unknowns),
# which is overdetermined and fails whenever the true algebraic value is not that start
# (NOTE-2 in plan/STATUS.md). Algebraic starts are passed as `guesses` instead below.
function _state_keys(system)
    return Set(_var_name(x) for x in ModelingToolkit.collect_differential_variables(system))
end

function _u0_pairs(flat::Flat.FlatModel, system, int_states::Vector{Pair{Num,Any}})
    by_id = Dict{String,Flat.FlatVar}(v.id => v for v in flat.variables)
    int_start = Dict{String,Any}(_var_name(p.first) => p.second for p in int_states)
    alias = _alias_map(system)
    states = _state_keys(system)
    out = Pair{Num,Any}[]
    for x in ModelingToolkit.unknowns(system)
        key = _var_name(x)
        if haskey(int_start, key)
            push!(out, x => _int_start(int_start[key], flat))
        elseif key in states
            start = _start_value(by_id, alias, key)
            # A generated tearing state with no start anywhere is 0.0.
            push!(out, x => start === nothing ? 0.0 : start)
        end
    end
    return out
end

"""    _alias_map(system) -> Dict{String,Vector{String}}

The pure alias relations among the compiled unknowns (`u ~ v` in the observed equations, both
directions), used to follow a start value to the variable MTK kept.

A composite body wires `IPlanar/Pm` into `CoriolisPlanar/P`; MTK then eliminates the momentum
in favour of one of the aliases (and, for a rigid joint, in favour of the twist), so the state
a start value was written on is no longer an unknown. Without this the initial momentum of a
composite body would be silently lost (J-MB6, `Free2D`)."""
function _alias_map(system)
    out = Dict{String,Vector{String}}()
    for equation in ModelingToolkit.observed(system)
        lhs = equation.lhs
        lhs isa Num && (lhs = Symbolics.unwrap(lhs))
        rhs = equation.rhs
        rhs isa Num && (rhs = Symbolics.unwrap(rhs))
        ModelingToolkit.isvariable(lhs) || continue
        ModelingToolkit.isvariable(rhs) || continue
        a = _var_name(lhs)
        b = _var_name(rhs)
        push!(get!(out, a, String[]), b)
        push!(get!(out, b, String[]), a)
    end
    return out
end

"""    _start_value(by_id, alias, key) -> Union{Nothing,Float64}

The start value of a compiled state: its own flat variable's start, or the nearest one found
along the alias chain (breadth first, so the closest definition wins)."""
function _start_value(by_id, alias, key::String)
    queue = String[key]
    seen = Set{String}([key])
    while !isempty(queue)
        current = popfirst!(queue)
        v = get(by_id, current, nothing)
        if v !== nothing && v.start !== nothing
            return _number(v.start, "the start of `$(v.id)`")
        end
        for next in get(alias, current, String[])
            next in seen && continue
            push!(seen, next)
            push!(queue, next)
        end
    end
    return nothing
end

# A start value of an algebraic variable is an initialisation *guess*, not a constraint.
function _guess_pairs(flat::Flat.FlatModel, system)
    by_id = Dict{String,Flat.FlatVar}(v.id => v for v in flat.variables)
    states = _state_keys(system)
    out = Pair{Num,Any}[]
    for x in ModelingToolkit.unknowns(system)
        key = _var_name(x)
        key in states && continue
        v = get(by_id, key, nothing)
        v === nothing && continue
        v.start === nothing && continue
        start = try
            _number(v.start, "the start of `$(v.id)`")
        catch
            continue
        end
        push!(out, x => start)
    end
    return out
end

function _p_pairs(flat::Flat.FlatModel, params::Dict{String,Num})
    out = Pair{Num,Any}[]
    for p in flat.parameters
        x = get(params, p.id, nothing)
        x === nothing && continue
        push!(out, x => _number(p.value, "parameter `$(p.id)`"))
    end
    return out
end

# ---------------------------------------------------------------------------------------
# Building and caching the compiled system
# ---------------------------------------------------------------------------------------

function _identity_mass(mm)
    mm === nothing && return true
    if mm isa AbstractMatrix
        size(mm, 1) == size(mm, 2) || return false
        for i in axes(mm, 1), j in axes(mm, 2)
            mm[i, j] == (i == j ? 1.0 : 0.0) || return false
        end
        return true
    end
    # LinearAlgebra.UniformScaling and other lazy identities.
    return try
        mm[1, 1] == 1 && mm[1, 2] == 0 && mm[2, 1] == 0 && mm[2, 2] == 1
    catch
        false
    end
end

_has_algebraic(prob) = !_identity_mass(prob.f.mass_matrix)

function _build_compiled(flat::Flat.FlatModel, key::String, tspan::Tuple{Float64,Float64})
    lowered = lower_flat(flat)
    vars = Num[lowered.vars[v.id] for v in flat.variables]
    for d in flat.derived
        push!(vars, lowered.vars[d.id])
    end
    for p in lowered.int_states
        push!(vars, p.first)
    end
    pars = Num[lowered.params[p.id] for p in flat.parameters]

    sysname = Symbol("bg_" * first(key, 12))
    kwargs = (; name = sysname)
    if !isempty(lowered.initial)
        kwargs = merge(kwargs, (; initialization_eqs = lowered.initial))
    end
    if !isempty(lowered.events)
        kwargs = merge(kwargs, (; continuous_events = lowered.events))
    end

    sys = System(lowered.eqs, t, vars, pars; kwargs...)
    csys = mtkcompile(sys)
    op = Pair{Num,Any}[]
    append!(op, _u0_pairs(flat, csys, lowered.int_states))
    append!(op, _p_pairs(flat, lowered.params))
    guesses = _guess_pairs(flat, csys)
    prob = ODEProblem(csys, op, tspan; guesses = guesses)
    return CompiledModel(key, csys, prob, lowered.vars, lowered.params,
        lowered.int_states, _has_algebraic(prob))
end

"""
    lower_model(flat; t_start = 0.0, t_end = 1.0) -> NamedTuple

Lower and compile `flat` (plan 5.8), or reuse the cached compiled system when the structural
hash [`compile_key`](@ref) matches. A cache hit rebuilds only the `ODEProblem`, through
`remake(prob; u0, p, tspan)` — the parameter-only path of decision D4 — so the new parameter
and start values are applied without touching the cached `System` or `ODEProblem` (which makes
the cached entry immune to a later run mutating its own problem). The result carries `key`
(the structural key), `model` (the `CompiledModel`), `problem`, and `cache_hit`.

A structural edit yields a different key and therefore a fresh `System` + `ODEProblem`: a
cache entry is never reused for a different structure. The cache is a bounded LRU
(`compile_cache_limit()`) and is emptied by [`clear_compile_cache!`](@ref).
"""
function lower_model(flat::Flat.FlatModel; t_start::Real = 0.0, t_end::Real = 1.0)
    key = compile_key(flat)
    tspan = (Float64(t_start), Float64(t_end))
    lock(COMPILE_LOCK)
    try
        cached = get(COMPILE_CACHE, key, nothing)
        if cached !== nothing && cached.key != key
            # Defensive: an entry filed under the wrong key must never be reused.
            _cache_remove!(key)
            cached = nothing
        end
        if cached !== nothing
            _cache_touch!(key)
            prob = remake(
                cached.problem;
                u0 = _u0_pairs(flat, cached.system, cached.int_states),
                p = _p_pairs(flat, cached.params),
                tspan = tspan,
            )
            return (; key = key, model = cached, problem = prob, cache_hit = true)
        end
        model = _build_compiled(flat, key, tspan)
        _cache_store!(key, model)
        COMPILE_BUILDS[] += 1
        return (; key = key, model = model, problem = model.problem, cache_hit = false)
    finally
        unlock(COMPILE_LOCK)
    end
end

# ---------------------------------------------------------------------------------------
# Parameter-only and start-only changes (structural key unchanged)
# ---------------------------------------------------------------------------------------

function _update_map(updates)
    out = Dict{String,Any}()
    for (k, v) in pairs(updates)
        out[String(k)] = v
    end
    return out
end

"""
    set_parameter_values(flat, updates) -> FlatModel

Return a copy of `flat` with parameter values replaced by `updates` (a map from signal id
such as `"Motor1/R"` to a number). The structure — and therefore [`compile_key`](@ref) — is
unchanged, so the next run hits the compile cache and only remakes the problem (D4).
"""
function set_parameter_values(flat::Flat.FlatModel, updates)
    wanted = _update_map(updates)
    known = Set(p.id for p in flat.parameters)
    for k in keys(wanted)
        k in known || throw(ArgumentError("`$k` is not a parameter of `$(flat.name)`"))
    end
    params = Flat.FlatParam[]
    for p in flat.parameters
        if haskey(wanted, p.id)
            push!(params, Flat.FlatParam(
                p.id, p.name, wanted[p.id], p.type, p.unit, p.attrs, p.origin
            ))
        else
            push!(params, p)
        end
    end
    return Flat.FlatModel(
        flat.name, flat.variables, params, flat.equations, flat.initial, flat.events,
        flat.discrete, flat.junctions, flat.connections, flat.instances, flat.domains,
        flat.unit_factors, flat.derived, flat.signals, flat.diagnostics, flat.stats,
    )
end

"""
    set_start_values(flat, updates) -> FlatModel

Return a copy of `flat` with state start values replaced by `updates` (signal id → number).
Like [`set_parameter_values`](@ref), this leaves the structural key unchanged: start values
are initial guesses, not structure (plan 5.8).
"""
function set_start_values(flat::Flat.FlatModel, updates)
    wanted = _update_map(updates)
    known = Set(v.id for v in flat.variables)
    for k in keys(wanted)
        k in known || throw(ArgumentError("`$k` is not a variable of `$(flat.name)`"))
    end
    variables = Flat.FlatVar[]
    for v in flat.variables
        if haskey(wanted, v.id)
            push!(variables, Flat.FlatVar(
                v.id, v.kind, v.type, v.unit, wanted[v.id], v.attrs, v.origin
            ))
        else
            push!(variables, v)
        end
    end
    return Flat.FlatModel(
        flat.name, variables, flat.parameters, flat.equations, flat.initial, flat.events,
        flat.discrete, flat.junctions, flat.connections, flat.instances, flat.domains,
        flat.unit_factors, flat.derived, flat.signals, flat.diagnostics, flat.stats,
    )
end

