# Parameters settable before initialization (plan/EXPORT_PLAN.md J-EX8 and the W-EX1
# tunables editor; plan/GLOBAL_PARAMETERS.md "Expose global parameters as FMU parameters").
#
# By default every parameter is folded into a literal (D-EX10) and the start is computed in
# Julia at export (D-EX11 phase 1). The settings can instead keep some values settable before
# initialization (FMI `causality="parameter"`, `variability="fixed"`):
#
#   tunables         flat parameter ids (`Motor/R`) and globals (`global:m`) the user picked
#   expose_globals   every independent global parameter (one whose value is a literal)
#   ranges           a [min, max] per tunable (D-EX16); a parameter falls back to its catalog
#                    `min`/`max`, a global has none unless the user gives one
#
# A picked parameter is not folded: the C code reads it from `m->p[]`. An exposed global is a
# parameter slot of its own that no equation reads; every parameter and start whose instance
# value is an expression over it (`Flat.GlobalInfo`) becomes a *calculated* value: the
# parameter a `calculatedParameter` in `m->p[]`, the start a recomputed initial state. A
# driven global (`c = a + b`) is never set directly; it is recomputed when one of its inputs is
# exposed, so every calculated value is written as an expression over the exposed globals only
# (and the picked parameters, for an `int` start). Nothing is recomputed per step:
# `bg_init_values` (generated) runs once in `fmi2ExitInitializationMode` (through `bg_init` of
# the runtime), followed, for a DAE, by a bounded Newton iteration on the algebraic block
# (`bg_project`'s Newton, D-EX11 phase 2). The hot path is unchanged (section 5.3).
#
# Refusals:
#   * W215: a tunable request is not honoured and the value stays folded: an unknown id, a
#     driven global, a global that sets a structural constant or a non-scalar value (or one of
#     its dependents does), a held discrete value, a parameter whose instance value is an
#     expression over globals (expose the global instead);
#   * E110: a picked value whose change before initialization moves the start in a way the C
#     initialization does not reproduce (MTK's initialization changes a differential state,
#     e.g. through `@initial` equations or index reduction). It is detected by comparing, for a
#     perturbed value, MTK's initialization (`lower_model` + `init`, i.e. a Julia run with that
#     value) with the C one emulated in Julia (recomputed starts, then Newton on the algebraic
#     block). An ODE without `@initial` equations skips the check: MTK starts it at its
#     starts, which the C recomputes. (`@initial` equations are parsed but not flattened yet,
#     so today the check runs for DAEs only.);
#   * E110: a range that does not contain the exported value.
#
# Ranges (D-EX16): a tunable the Jacobian depends on joins the spectrum scan with its range
# (each end, and the corners for up to 6 values); without a complete range it gets W210. The
# FMU refuses `fmi2SetReal` outside the range with a log message naming the variable, the value
# and the range (no clamping: a silently changed value would hide the mistake).

const GLOBAL_PREFIX = IR.GLOBAL_OVERRIDE_PREFIX

"""A global parameter exposed as an FMU parameter."""
struct ExposedGlobal
    name::Symbol
    sym::Any            # its symbolic stand-in in the calculated expressions (unwrapped)
    value::Float64
    lo::Float64
    hi::Float64
end

"""    TunablePlan

What `plan_tunables` decided: `requested` the flat parameter ids kept as fixed parameters,
`globals` the exposed globals, `calc` flat parameter id => expression over the exposed
globals' symbols (a calculated parameter), `starts` flat variable id => expression (a start
recomputed at initialization), `ranges` id => (lo, hi) of every requested value."""
struct TunablePlan
    requested::Vector{String}
    globals::Vector{ExposedGlobal}
    calc::Dict{String,Any}
    starts::Dict{String,Any}
    ranges::Dict{String,Tuple{Float64,Float64}}
end

TunablePlan() = TunablePlan(String[], ExposedGlobal[], Dict{String,Any}(), Dict{String,Any}(),
    Dict{String,Tuple{Float64,Float64}}())

has_init_values(tp::TunablePlan) = !isempty(tp.requested) || !isempty(tp.globals)

_w215(message; hint = nothing, path = nothing) =
    diag("W215", message; hint = hint, path = path, scope = "export")

"""The range of a requested value: the user's, else the catalog's `min`/`max` (`fp`)."""
function _tunable_range(settings, id, fp)
    r = get(settings.ranges, id, nothing)
    clo, chi = _range(fp)
    r === nothing && return (clo, chi)
    lo = isfinite(r[1]) ? r[1] : clo
    hi = isfinite(r[2]) ? r[2] : chi
    return (lo, hi)
end

"""Every global whose value depends on one of `roots` (transitively), the roots included."""
function _global_dependents(gi, roots)
    live = Set{Symbol}(roots)
    for n in gi.order
        n in live && continue
        deps = _global_deps(gi, n)
        any(d -> d in live, deps) && push!(live, n)
    end
    return live
end

_global_deps(gi, n) = haskey(gi.exprs, n) ? BGSim.Compile._expr_names!(Symbol[], gi.exprs[n]) :
    Symbol[]

_names_in(ast) = BGSim.Compile._expr_names!(Symbol[], ast)

"""    plan_tunables(flat, settings, lowered, diags) -> TunablePlan

Resolve the tunables of the settings against the flat model (file header)."""
function plan_tunables(flat, settings, lowered, diags)
    gi = flat.globals
    isempty(settings.tunables) && !settings.expose_globals && return TunablePlan()
    flat_params = Dict(p.id => p for p in flat.parameters)
    req_params = String[]
    req_globals = Symbol[]
    for id in unique(settings.tunables)
        if startswith(id, GLOBAL_PREFIX)
            push!(req_globals, Symbol(id[length(GLOBAL_PREFIX) + 1:end]))
        else
            push!(req_params, id)
        end
    end

    # ---- the exposed globals
    exposed = Symbol[]
    if gi === nothing
        isempty(req_globals) || push!(diags, _w215(
            "the model has no global parameters, so `$(GLOBAL_PREFIX)$(first(req_globals))` cannot be exposed"))
    else
        candidates = Symbol[]
        if settings.expose_globals
            append!(candidates, [n for n in gi.names if haskey(gi.values, n) &&
                                                      isempty(_global_deps(gi, n))])
        end
        for n in req_globals
            if !haskey(gi.values, n)
                push!(diags, _w215("`$(GLOBAL_PREFIX)$n` is not a global parameter of the model (or cannot be evaluated), so it is not exposed"))
            elseif !isempty(_global_deps(gi, n))
                push!(diags, _w215(
                    "global `$n` is defined by an equation over $(join(("`$d`" for d in _global_deps(gi, n)), ", ")); it is recomputed from them, not set directly";
                    hint = "expose the globals it uses instead"))
            else
                push!(candidates, n)
            end
        end
        for n in unique(candidates)
            uses = String[]
            for d in _global_dependents(gi, (n,))
                append!(uses, get(gi.fixed, d, String[]))
            end
            if !isempty(uses)
                push!(diags, _w215(
                    "global `$n` cannot be exposed as an FMU parameter: it sets $(join(first(uses, 3), "; "))$(length(uses) > 3 ? " and $(length(uses) - 3) more" : ""); it stays folded";
                    hint = "a structural or non-scalar value is fixed at export; give it a literal or a global of its own"))
                continue
            end
            push!(exposed, n)
        end
    end

    globals = ExposedGlobal[]
    gsym = Dict{Symbol,Any}()
    for n in exposed
        sym = BGSim.mtk_parameter(GLOBAL_PREFIX * String(n))
        gsym[n] = sym
        id = GLOBAL_PREFIX * String(n)
        r = get(settings.ranges, id, nothing)
        lo = r === nothing || !isfinite(r[1]) ? -Inf : r[1]
        hi = r === nothing || !isfinite(r[2]) ? Inf : r[2]
        push!(globals, ExposedGlobal(n, Symbolics.unwrap(sym), Float64(gi.values[n]), lo, hi))
    end

    # ---- every global as a number or an expression over the exposed ones
    calc = Dict{String,Any}()
    starts = Dict{String,Any}()
    if !isempty(exposed)
        live = _global_dependents(gi, exposed)
        genv = Dict{String,Num}()
        for n in gi.order
            haskey(gi.values, n) || continue
            genv[String(n)] = if haskey(gsym, n)
                gsym[n]
            elseif n in live
                Num(BGSim.lower_expression(gi.exprs[n], BGSim.LowerCtx(Dict{String,Num}(), genv)))
            else
                Num(Float64(gi.values[n]))
            end
        end
        lower_over_globals(ast) = Symbolics.unwrap(Num(BGSim.lower_expression(ast,
            BGSim.LowerCtx(Dict{String,Num}(), genv))))
        for (id, ast) in gi.param_exprs
            any(n -> n in live, _names_in(ast)) || continue
            calc[id] = lower_over_globals(ast)
        end
        for (id, ast) in gi.start_exprs
            any(n -> n in live, _names_in(ast)) || continue
            starts[id] = lower_over_globals(ast)
        end
    end

    # ---- the picked parameters
    requested = String[]
    ranges = Dict{String,Tuple{Float64,Float64}}()
    for id in req_params
        fp = get(flat_params, id, nothing)
        if fp === nothing || !haskey(lowered.model.params, id)
            push!(diags, _w215("`$id` is not a parameter of the exported model, so it cannot be tunable"))
        elseif get(fp.attrs, :kind, nothing) === :discrete
            push!(diags, _w215("`$id` is a held discrete value, not a parameter; it cannot be tunable";
                path = fp.origin.path))
        elseif haskey(calc, id)
            push!(diags, _w215("`$id` is computed from an exposed global parameter at initialization, so it is not set on its own";
                path = fp.origin.path, hint = "change the global instead"))
        elseif gi !== nothing && haskey(gi.param_exprs, id)
            used = unique(_names_in(gi.param_exprs[id]))
            push!(diags, _w215("`$id` is an expression over the global parameter$(length(used) == 1 ? "" : "s") $(join(("`$n`" for n in used), ", ")), so it cannot be set on its own; it stays folded";
                path = fp.origin.path, hint = "expose the global instead"))
        else
            push!(requested, id)
            ranges[id] = _tunable_range(settings, id, fp)
        end
    end
    for g in globals
        ranges[GLOBAL_PREFIX * String(g.name)] = (g.lo, g.hi)
    end
    return TunablePlan(requested, globals, calc, starts, ranges)
end

"""    substitute_number(e, subs) -> Float64

The value of a calculated expression with `subs` (symbol => number) substituted."""
function substitute_number(e, subs)
    r = Symbolics.unwrap(Symbolics.substitute(e, subs))
    c = _try_const(r)
    c === nothing && throw(ExportError("internal: a calculated value `$e` did not evaluate to a number"))
    return Float64(c)
end

"""    start_targets(flat, lowered, tp, xs, names_x, psym) -> Vector{Tuple{Int,Any}}

The compiled differential states whose start is recomputed at initialization, with the
expression: a start written as an expression over an exposed global (followed along the
alias chain to the state MTK kept, as `_u0_pairs` does), or the start of an `int` state that
reads a picked or calculated parameter (`psym`: flat parameter id => its symbol or calculated
expression)."""
function start_targets(flat, lowered, tp::TunablePlan, xs, names_x, psym)
    out = Tuple{Int,Any}[]
    has_init_values(tp) || return out
    sys = lowered.model.system
    by_id = Dict{String,Flat.FlatVar}(v.id => v for v in flat.variables)
    alias = BGSim._alias_map(sys)
    states = BGSim._state_keys(sys)
    int_start = Dict{String,Any}(BGSim._var_name(p.first) => p.second
                                 for p in lowered.model.int_states)
    penv = Dict{String,Num}()
    for p in flat.parameters
        penv[p.id] = haskey(psym, p.id) ? Num(psym[p.id]) : Num(BGSim._number(p.value, p.id))
    end
    for (i, x) in enumerate(xs)
        key = BGSim._var_name(x)
        key in states || continue
        if haskey(int_start, key)
            ast = int_start[key]
            any(n -> haskey(psym, String(n)), _names_in(ast)) || continue
            push!(out, (i, Symbolics.unwrap(Num(BGSim.lower_expression(ast,
                BGSim.LowerCtx(Dict{String,Num}(), penv))))))
            continue
        end
        source = BGSim._start_source(by_id, alias, key)
        source === nothing && continue
        id, sign = source
        haskey(tp.starts, id) && push!(out, (i, sign == 1 ? tp.starts[id] : -tp.starts[id]))
    end
    return out
end

"""A value to try for `v0` inside `[lo, hi]`: half way to an end of the range, else 10 %
more (or 0.1 for a zero)."""
function _probe_value(v0, lo, hi)
    isfinite(hi) && hi > v0 && return v0 + 0.5 * (hi - v0)
    isfinite(lo) && lo < v0 && return v0 - 0.5 * (v0 - lo)
    return v0 == 0 ? 0.1 : 1.1 * v0
end

"""    check_initialization(flat, lowered, settings, tp, ...) -> Vector{Dict}

E110 when the C initialization (recomputed starts, then Newton on the algebraic block) does
not reproduce MTK's initialization for a changed tunable (file header). Each tunable is
probed on its own (at most 8), and all together once when there are several. Returns the
probes for the report."""
function check_initialization(flat, lowered, settings, tp::TunablePlan, xs, x0, names_x, ps,
    names_p, p0, mass_an, starts, calc_index, req_index, pobj_of, diags)
    probes = Dict{String,Any}[]
    has_init_values(tp) || return probes
    algebraic = mass_an !== nothing
    # An ODE without `@initial` equations starts at its starts: MTK changes nothing.
    !algebraic && isempty(flat.initial) && return probes
    ids = vcat(tp.requested, [GLOBAL_PREFIX * String(g.name) for g in tp.globals])
    g0 = Dict{Any,Float64}(g.sym => g.value for g in tp.globals)
    base = Dict{String,Float64}()
    for id in tp.requested
        base[id] = p0[req_index[id]]
    end
    for g in tp.globals
        base[GLOBAL_PREFIX * String(g.name)] = g.value
    end
    psyms = Dict{String,Any}(id => Symbolics.unwrap(ps[req_index[id]]) for id in tp.requested)
    sets = [[id] for id in first(ids, 8)]
    length(ids) > 1 && push!(sets, ids)
    alg = algebraic ? findall(iszero, mass_an) : Int[]
    f = lowered.problem.f
    for set in sets
        vals = copy(base)
        for id in set
            lo, hi = tp.ranges[id]
            vals[id] = _probe_value(base[id], lo, hi)
        end
        gsub = Dict{Any,Any}(g.sym => vals[GLOBAL_PREFIX * String(g.name)] for g in tp.globals)
        sub = merge(gsub, Dict{Any,Any}(psyms[id] => vals[id] for id in tp.requested))
        pupd = Dict{String,Any}(id => vals[id] for id in tp.requested)
        for (id, e) in tp.calc
            pupd[id] = substitute_number(e, gsub)
        end
        supd = Dict{String,Any}(id => substitute_number(e, gsub) for (id, e) in tp.starts)
        p = copy(p0)
        for (id, v) in pupd
            k = get(calc_index, id, get(req_index, id, nothing))
            k === nothing || (p[k] = v)
        end
        # MTK: a Julia run with these values.
        xref = try
            flat2 = BGSim.set_parameter_values(flat, pupd)
            isempty(supd) || (flat2 = BGSim.set_start_values(flat2, supd))
            low2 = BGSim.lower_model(flat2; t_start = 0.0, t_end = max(settings.t_end, settings.step))
            integ2 = MTK.SciMLBase.init(low2.problem, algebraic ? Rodas5P() : Tsit5();
                abstol = 1e-12, reltol = 1e-12)
            Float64[getu(integ2, x)(integ2) for x in xs]
        catch err
            err isa InterruptException && rethrow()
            push!(diags, _w215(
                "the initialization check of $(join(("`$i`" for i in set), ", ")) was skipped: Julia's initialization failed at $(join((string(vals[i]) for i in set), ", "))";
                hint = first(sprint(showerror, err), 300)))
            continue
        end
        # C: the recomputed starts, then Newton on the algebraic block (bg_init).
        xc = copy(x0)
        for (i, e) in starts
            xc[i] = substitute_number(e, sub)
        end
        if algebraic && !isempty(alg)
            pobj = pobj_of(p)
            r = zeros(length(xc))
            for _ in 1:50
                f(r, xc, pobj, 0.0)
                J = _jac_at(f, xc, pobj)
                dz = try
                    J[alg, alg] \ r[alg]
                catch
                    break
                end
                xc[alg] .-= dz
                maximum(abs, dz; init = 0.0) <= 1e-13 * (1 + maximum(abs, xc[alg])) && break
            end
        end
        err, k = findmax(abs.(xc .- xref) ./ max.(1.0, abs.(xref)))
        push!(probes, Dict{String,Any}("ids" => set, "values" => [vals[i] for i in set],
            "maxStartDeviation" => err))
        if err > 1e-6
            push!(diags, diag("E110",
                "changing $(join(("`$i`" for i in set), ", ")) before initialization changes the start of `$(names_x[k])` ($(xref[k]) in Julia, $(xc[k]) in C), which the C initialization does not reproduce";
                scope = "export",
                hint = "MTK's initialization moves a differential state here (@initial equations or index reduction); remove it from the tunables so it is folded"))
        end
    end
    return probes
end

"""A central-difference Jacobian of `f(r, x, p, t)` at t = 0 (the initialization check)."""
function _jac_at(f, x, pobj)
    n = length(x)
    J = zeros(n, n)
    fp = zeros(n)
    fm = zeros(n)
    xp = copy(x)
    for j in 1:n
        h = 6.0e-6 * max(1.0, abs(x[j]))
        xp[j] = x[j] + h
        f(fp, xp, pobj, 0.0)
        xp[j] = x[j] - h
        f(fm, xp, pobj, 0.0)
        xp[j] = x[j]
        J[:, j] .= (fp .- fm) ./ (2h)
    end
    return J
end

"""A C string literal."""
c_string(s) = "\"" * replace(String(s), "\\" => "\\\\", "\"" => "\\\"") * "\""
