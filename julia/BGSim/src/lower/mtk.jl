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

This is the J2.3 seam. The continuous M1 lowering does not add nonsmooth events yet, so the
collector returns an empty vector; filling it is the only change J2.3 needs at this level.
"""
nonsmooth_conditions(::Flat.FlatModel) = Expr[]

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

# The compile cache of plan 5.8. The key is structural; parameter values and start values are
# deliberately absent, which is what makes a parameter-only re-run hit the cache. The limit
# keeps a long-lived worker bounded; J2.8 owns the full cache policy.
const COMPILE_CACHE = Dict{String,CompiledModel}()
const COMPILE_ORDER = String[]
const COMPILE_CACHE_LIMIT = 8
const COMPILE_LOCK = ReentrantLock()

"""    cache_size() -> Int

The number of compiled models currently in the structural cache."""
cache_size() = length(COMPILE_CACHE)

"""    clear_compile_cache!()

Empty the structural cache. The worker calls this for `cache.clear`."""
function clear_compile_cache!()
    lock(COMPILE_LOCK) do
        empty!(COMPILE_CACHE)
        empty!(COMPILE_ORDER)
    end
    return nothing
end

function _cache_store!(key::String, model::CompiledModel)
    COMPILE_CACHE[key] = model
    push!(COMPILE_ORDER, key)
    while length(COMPILE_ORDER) > COMPILE_CACHE_LIMIT
        old = popfirst!(COMPILE_ORDER)
        delete!(COMPILE_CACHE, old)
    end
    return nothing
end

function _cache_touch!(key::String)
    index = findfirst(==(key), COMPILE_ORDER)
    index === nothing && return nothing
    deleteat!(COMPILE_ORDER, index)
    push!(COMPILE_ORDER, key)
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
    compile_key(flat) -> String

The structural hash of plan 5.8, as 64 lowercase hex characters (the `modelHash` shape of
the run manifest). It hashes the variables, parameters, equations, initial equations, events,
discrete items, derived signals and the recording order — but **not** parameter values and
**not** start values, so a parameter-only re-run hits the cache (decision D4).

Source ranges and block paths are not part of the key: editing a comment must not force a
recompile, and the equations already contain the fully qualified signal ids.
"""
function compile_key(flat::Flat.FlatModel)
    io = IOBuffer()
    print(io, "bg-sim-structure-v1\n")
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
    return bytes2hex(sha256(take!(io)))
end

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
        params[p.id] = mtk_parameter(p.id)
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

    # The J2.3 seam: condition-only continuous events. `nonsmooth_conditions` is empty for
    # the continuous M1 models, so this loop is quiet until J2.3 fills the collector.
    events = Any[]
    for c in nonsmooth_conditions(flat)
        ctx.origin = nothing
        push!(events, SymbolicContinuousCallback(lower_expression(c, ctx) ~ 0))
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

# The operating point must contain exactly the compiled unknowns (states plus, for a DAE,
# algebraic unknowns). Passing every flat variable would make MTK treat the algebraic and
# observed start guesses as initialization equations, which is both wrong and very slow
# (observed: 7 s and an "overdetermined initialization" warning on the DC motor).
function _u0_pairs(flat::Flat.FlatModel, system, int_states::Vector{Pair{Num,Any}})
    by_id = Dict{String,Flat.FlatVar}(v.id => v for v in flat.variables)
    int_start = Dict{String,Any}(_var_name(p.first) => p.second for p in int_states)
    out = Pair{Num,Any}[]
    for x in ModelingToolkit.unknowns(system)
        key = _var_name(x)
        if haskey(int_start, key)
            push!(out, x => _int_start(int_start[key], flat))
        elseif haskey(by_id, key)
            v = by_id[key]
            start = v.start === nothing ? 0.0 : _number(v.start, "the start of `$(v.id)`")
            push!(out, x => start)
        else
            # A generated algebraic unknown (tearing): 0.0 is the initial guess.
            push!(out, x => 0.0)
        end
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
    prob = ODEProblem(csys, op, tspan)
    return CompiledModel(key, csys, prob, lowered.vars, lowered.params,
        lowered.int_states, _has_algebraic(prob))
end

"""
    lower_model(flat; t_start = 0.0, t_end = 1.0) -> NamedTuple

Lower and compile `flat` (plan 5.8), or reuse the cached compiled system when the structural
hash matches. A cache hit rebuilds only the `ODEProblem`, through `remake(prob; u0, p,
tspan)` — the parameter-only path of decision D4. The result carries `model` (the
`CompiledModel`), `problem`, and `cache_hit`.
"""
function lower_model(flat::Flat.FlatModel; t_start::Real = 0.0, t_end::Real = 1.0)
    key = compile_key(flat)
    tspan = (Float64(t_start), Float64(t_end))
    lock(COMPILE_LOCK)
    try
        cached = get(COMPILE_CACHE, key, nothing)
        if cached !== nothing
            _cache_touch!(key)
            prob = remake(
                cached.problem;
                u0 = _u0_pairs(flat, cached.system, cached.int_states),
                p = _p_pairs(flat, cached.params),
                tspan = tspan,
            )
            return (; model = cached, problem = prob, cache_hit = true)
        end
        model = _build_compiled(flat, key, tspan)
        _cache_store!(key, model)
        return (; model = model, problem = model.problem, cache_hit = false)
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

