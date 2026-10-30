# Statement hooks and line breakpoints (plan sections 3.8 and 5.13, decisions D20 and D21;
# work package J4.2).
#
# A debug run compiles its discrete partitions in a *debug variant* (`step_expression(...;
# debug = DebugEmit)`, `src/compile/discrete.jl`): the function takes the hook state as a fifth
# argument and every source statement is preceded by
#
#     if dbg.armed[k] | stepping(dbg); hook(dbg, k, (assigned temporaries...)) end
#
# where `k` indexes the static hook table `HookState.emit.sites`. A normal run never sees any of
# this: its generated function is the unchanged four-argument expression (DEC-M4-8). The debug
# variant is wrapped in a [`DebugStep`](@ref), so `run_tick!` keeps calling
# `step(dstate, inputs, params, t)`.
#
#   * The `"line"` breakpoint kind resolves `(ref, line, path)` to the hooks of every instance
#     of the block (or of the one `path`). No instance of the block: W401. A line without a
#     statement: E401. Conditions are parsed once with the language front end and evaluated by
#     the constant-folding interpreter (`eval_const`, D27) in the frame's names; user text never
#     reaches `eval`. Hit counts are kept per breakpoint id.
#   * Step granularity `"statement"` pauses at the next hook of any partition.
#   * A statement pause carries the plan 3.8 `Frame`; the same frame with raw values and the
#     name environment for expressions is `paused_frame(ctx)` (`ctx.ext[:frame]`).

"""
    HookState(ctx)

The runtime half of the statement hooks of one debug run, referenced from the generated step
functions as `dbg`. `emit` is the hook table the generator fills while
[`discrete_schedule`](@ref) compiles the partitions; `armed[k]` is true for the hooks that an
enabled line breakpoint resolved to; `lines` are those breakpoints (with their compiled
conditions) and `by_hook[k]` the indices into `lines` that watch hook `k`. Stepping is read
from `ctx.step_mode`, so `debug_step!(ctx, "statement")` needs no extra state."""
mutable struct HookState
    ctx::DebugCtx
    emit::Compile.DebugEmit
    armed::BitVector
    lines::Vector{Any}
    by_hook::Vector{Vector{Int}}
    hits::Dict{String,Tuple{Any,Int}}
    scopes::Vector{Any}
    types::Union{Nothing,Dict{String,String}}
end

# What the generated code calls. `GlobalRef`s into this module, never a user name.
function _hook_entry end
_hook_stepping(h::HookState) = h.ctx.step_mode === :statement

function HookState(ctx::DebugCtx)
    emit = Compile.DebugEmit(
        GlobalRef(@__MODULE__, :_hook_entry), GlobalRef(@__MODULE__, :_hook_stepping)
    )
    return HookState(ctx, emit, falses(0), Any[], Vector{Int}[], Dict{String,Tuple{Any,Int}}(),
        Any[], nothing)
end

"""
    DebugStep(fn, hooks)

A debug-variant partition function bound to its hook state. Calling it with the normal
`(dstate, inputs, params, t)` passes `hooks` as the fifth argument of the generated function."""
struct DebugStep{F}
    fn::F
    hooks::HookState
end

(d::DebugStep)(dstate, inputs, params, t) = d.fn(dstate, inputs, params, t, d.hooks)

# The `# M4 debug:` insertion points of `discrete_schedule` and `simulate` (the `Nothing`
# methods are the normal run).
_dbg_hooks(::Nothing) = nothing

function _dbg_hooks(ctx::DebugCtx)
    h = HookState(ctx)
    ctx.ext[:hooks] = h
    return h
end

_dbg_emitter(::Nothing) = nothing
_dbg_emitter(h::HookState) = h.emit

_dbg_step(::Nothing, fn) = fn

function _dbg_step(h::HookState, fn)
    n = length(h.emit.sites)
    h.armed = falses(n)
    h.by_hook = [Int[] for _ in 1:n]
    h.scopes = Any[nothing for _ in 1:n]
    return DebugStep(fn, h)
end

# `s.event_cursor` mirrors the loop's local cursor, so a pause in the middle of a tick (or at
# its end) never records the event rows of the last step twice.
_dbg_sync_cursor!(::Nothing, ::Nothing, cursor) = nothing

function _dbg_sync_cursor!(::DebugCtx, s::DebugSession, cursor)
    s.event_cursor = cursor
    return nothing
end

# ---------------------------------------------------------------------------------------
# Frames (plan 3.8 `Frame`)
# ---------------------------------------------------------------------------------------

# One named group of scalar slots: a scalar, a vector or a matrix of a declared name.
# `idx` holds, in column-major order of `shape`, the position of each element in the vector of
# its `kind` (`:temp`: in the temporaries tuple; `:held`/`:input`/`:param`: in the shared
# runtime vectors), 0 for an element the partition never touches.
struct Binding
    name::Symbol
    kind::Symbol
    idx::Vector{Int}
    shape::Tuple{Vararg{Int}}
    type::String
end

# The names that are in scope at one hook: `locals` are the temporaries assigned so far,
# `held` every held value of the block instance, `previous` what the partition reads through
# `previous(x)`, `reads` the parameters and inputs the partition reads.
struct SiteScope
    locals::Vector{Binding}
    held::Vector{Binding}
    previous::Vector{Binding}
    reads::Vector{Binding}
    Ts::Float64
end

"""
    PausedFrame

The frame of a statement pause, kept in `ctx.ext[:frame]` ([`paused_frame`](@ref)) while the
run is paused there. `view` is the plan 3.8 `Frame` of the `PausedInfo`; `env` maps every name
in scope (the temporaries assigned so far, the held values, the parameters and inputs the
partition reads, `t` and `Ts`) to its raw value (`Float64`/`Int`/`Bool`, `Vector`, `Matrix`),
exactly what `BGSim.eval_const(expr, env)` needs for `debug.evaluate` (D27). `hook` and `site`
identify the statement."""
struct PausedFrame
    hook::Int
    site::Compile.HookSite
    view::NamedTuple
    env::Dict{Symbol,Any}
end

"""    paused_frame(ctx) -> Union{Nothing,PausedFrame}

The frame of the statement the run is paused at, `nothing` at any other pause or while the run
is running."""
paused_frame(ctx::DebugCtx) = get(ctx.ext, :frame, nothing)

function _flat_types(s::DebugSession)
    types = Dict{String,String}()
    for p in s.flat.parameters
        types[String(p.id)] = String(p.type)
    end
    return types
end

# Group scalar ids `path/name`, `path/name[i]`, `path/name[i,j]` into bindings.
function _group_bindings(ids::Vector{String}, positions::Vector{Int}, kind::Symbol, path::String,
    shapes, types)
    prefix = path * "/"
    order = String[]
    groups = Dict{String,Vector{Tuple{Vector{Int},Int,String}}}()
    for (id, pos) in zip(ids, positions)
        startswith(id, prefix) || continue
        rest = chop(id; head = ncodeunits(prefix), tail = 0)
        occursin('/', rest) && continue
        m = match(r"^([^\[]+)(?:\[([0-9,]+)\])?$", rest)
        m === nothing && continue
        name = String(m[1])
        subs = m[2] === nothing ? Int[] : Base.parse.(Int, split(m[2], ","))
        haskey(groups, name) || (groups[name] = Tuple{Vector{Int},Int,String}[]; push!(order, name))
        push!(groups[name], (subs, pos, get(types, id, "Real")))
    end
    out = Binding[]
    for name in order
        elems = groups[name]
        nd = length(elems[1][1])
        shape = if nd == 0
            ()
        else
            declared = get(shapes, prefix * name, nothing)
            if declared !== nothing && length(declared) == nd
                Tuple(declared)
            else
                Tuple(maximum(e[1][d] for e in elems) for d in 1:nd)
            end
        end
        idx = zeros(Int, isempty(shape) ? (1,) : shape)
        for (subs, pos, _) in elems
            isempty(subs) ? (idx[1] = pos) :
            (all(d -> 1 <= subs[d] <= shape[d], 1:nd) && (idx[CartesianIndex(subs...)] = pos))
        end
        push!(out, Binding(Symbol(name), kind, vec(idx), shape, elems[1][3]))
    end
    return out
end

function _partition_of(sched, label::String)
    for sp in sched.partitions
        sp.partition.label == label && return sp.partition
    end
    error("no scheduled partition `$label`")
end

function _site_scope(h::HookState, s::DebugSession, k::Int)
    cached = h.scopes[k]
    cached === nothing || return cached
    site = h.emit.sites[k]
    sched = s.schedule
    part = _partition_of(sched, site.label)
    info = Compile.block_info(s.flat)
    shapes = info === nothing ? Dict{String,Tuple{Vararg{Int}}}() : info.shapes
    h.types === nothing && (h.types = _flat_types(s))
    types = h.types
    # Temporaries: the generated code passes the slot values in this order.
    locals = Binding[]
    pos = 0
    for (name, slots) in site.temps
        n = length(slots)
        push!(locals, Binding(Symbol(name), :temp, collect(pos + 1:pos + n),
            n == 1 ? () : (n,), ""))
        pos += n
    end
    held = _group_bindings(
        sched.held_ids, collect(1:length(sched.held_ids)), :held, site.path, shapes, types
    )
    prev_ids = String[id for id in part.previous_reads]
    previous = Binding[]
    for (kind, index) in ((:held, sched.held_index), (:input, sched.input_index),
        (:param, sched.param_index))
        ids = String[id for id in prev_ids if haskey(index, id)]
        append!(previous, _group_bindings(
            ids, Int[index[id] for id in ids], kind, site.path, shapes, types
        ))
    end
    reads = Binding[]
    for (kind, index) in ((:input, sched.input_index), (:param, sched.param_index))
        ids = String[id for id in part.reads if haskey(index, id)]
        append!(reads, _group_bindings(
            ids, Int[index[id] for id in ids], kind, site.path, shapes, types
        ))
    end
    scope = SiteScope(locals, held, previous, reads, part.period)
    h.scopes[k] = scope
    return scope
end

_elem_type(type::String) = type == "Bool" ? Bool : type == "Int" ? Int : Float64
_conv(::Type{Bool}, x) = x isa Bool ? x : x != 0
_conv(::Type{Int}, x) = x isa Integer ? Int(x) : (isfinite(x) ? Int(round(x)) : 0)
_conv(::Type{Float64}, x) = Float64(x)

function _temp_type(vals)
    all(v -> v isa Bool, vals) && return Bool
    all(v -> v isa Integer, vals) && return Int
    return Float64
end

# The raw value of a binding: a scalar, a Vector or an Array of `shape`.
function _binding_value(b::Binding, fetch)
    raw = Any[i == 0 ? NaN : fetch(i) for i in b.idx]
    T = b.kind === :temp ? _temp_type(raw) : _elem_type(b.type)
    vals = T[_conv(T, x) for x in raw]
    isempty(b.shape) && return vals[1]
    length(b.shape) == 1 && return vals
    return reshape(vals, b.shape)
end

_binding_type(v) = v isa Bool || (v isa AbstractArray && eltype(v) === Bool) ? "Bool" :
                   v isa Integer || (v isa AbstractArray && eltype(v) <: Integer) ? "Int" : "Real"

_nested(v) = v
_nested(v::AbstractVector) = collect(v)
_nested(v::AbstractArray) = Any[_nested(selectdim(v, 1, i)) for i in axes(v, 1)]

function _frame_entry(b::Binding, value)
    return (
        name = String(b.name), type = _binding_type(value),
        size = collect(Int, b.shape), value = _nested(value),
    )
end

function _fetcher(run, temps, b::Binding, prev::Bool)
    if b.kind === :temp
        return i -> temps[i]
    elseif b.kind === :held
        v = prev ? run.state.prev : run.state.values
        return i -> v[i]
    elseif b.kind === :input
        v = prev ? run.inputs.prev : run.inputs.values
        return i -> v[i]
    end
    return i -> run.params[i]
end

# The names a condition or `debug.evaluate` may use, with their raw values. `names === nothing`
# collects all of them.
function _frame_env(scope::SiteScope, run, temps, names = nothing)
    env = Dict{Symbol,Any}(:t => run.state.prev_t, :Ts => scope.Ts)
    for list in (scope.held, scope.reads, scope.locals), b in list
        (names === nothing || b.name in names) || continue
        env[b.name] = _binding_value(b, _fetcher(run, temps, b, false))
    end
    return env
end

function _capture_frame(h::HookState, s::DebugSession, k::Int, temps)
    scope = _site_scope(h, s, k)
    run = s.run
    env = _frame_env(scope, run, temps)
    locals = [
        _frame_entry(b, _binding_value(b, _fetcher(run, temps, b, false))) for b in scope.locals
    ]
    held = [
        _frame_entry(b, _binding_value(b, _fetcher(run, temps, b, false))) for b in scope.held
    ]
    previous = [
        _frame_entry(b, _binding_value(b, _fetcher(run, temps, b, true))) for b in scope.previous
    ]
    return PausedFrame(k, h.emit.sites[k], (locals = locals, held = held, previous = previous), env)
end

function _site_location(site::Compile.HookSite)
    r = site.range
    return (
        path = site.path, ref = site.ref, scope = site.scope,
        range = (line = r.line, col = r.col, endLine = r.endLine, endCol = r.endCol),
    )
end

# ---------------------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------------------

struct CompiledCondition
    text::String
    expr::BGSim.Expr
    names::Vector{Symbol}
end

const _CONDITION_FUNCS = Set{Symbol}([
    :abs, :sign, :min, :max, :clamp, :floor, :ceil, :round, :sqrt, :exp, :log, :log10, :sin,
    :cos, :tan, :asin, :acos, :atan, :sinh, :cosh, :tanh, :mod, :rem, :hypot, :dot, :norm,
    :cross, :transpose,
])

_cond_diag(code, message, bp_ref, path; hint = nothing) = to_namedtuple(diag(
    code, message; hint = hint, path = path, block = bp_ref, scope = "breakpoint condition",
))

# Collect the free names of a condition; reports unsupported syntax through `report(code, msg)`.
function _condition_names!(names::Vector{Symbol}, e, report)
    if e isa BGSim.Name
        e.name in names || push!(names, e.name)
    elseif e isa BGSim.Lit
    elseif e isa BGSim.Field
        report("E003", "`$(sprint(show, e))` is not available in a breakpoint condition",
            "use the plain name of a local, held value or parameter")
    elseif e isa BGSim.Call
        if !(e.fn.name in _CONDITION_FUNCS)
            report("E004", "function `$(e.fn.name)` cannot be used in a breakpoint condition",
                e.fn.name === :previous ?
                "the `previous` list of the paused frame shows those values" : nothing)
        end
        for a in e.args
            _condition_names!(names, a, report)
        end
    elseif e isa BGSim.BinOp || e isa BGSim.Comparison
        _condition_names!(names, e.lhs, report)
        _condition_names!(names, e.rhs, report)
    elseif e isa BGSim.UnOp
        _condition_names!(names, e.operand, report)
    elseif e isa BGSim.BoolOp
        for a in e.operands
            _condition_names!(names, a, report)
        end
    elseif e isa BGSim.IfElse
        _condition_names!(names, e.cond, report)
        _condition_names!(names, e.then, report)
        _condition_names!(names, e.otherwise, report)
    elseif e isa BGSim.Index
        _condition_names!(names, e.base, report)
        for i in e.indices
            _condition_names!(names, i, report)
        end
    elseif e isa BGSim.VectorLit
        for a in e.elements
            _condition_names!(names, a, report)
        end
    elseif e isa BGSim.MatrixLit
        for row in e.rows, a in row
            _condition_names!(names, a, report)
        end
    end
    return nothing
end

# Parse `text` once with the language front end (as the default expression of a throwaway
# block, the way the model values are parsed). Returns `(condition, diagnostics)`.
function _compile_condition(text::String, ref::String, path)
    diags = Any[]
    report(code, message, hint = nothing) =
        push!(diags, _cond_diag(code, message, ref, path; hint = hint))
    if occursin('\n', text) || occursin(';', text)
        report("E001", "a breakpoint condition is one expression",
            "write it on one line without `;`")
        return nothing, diags
    end
    src = "@block __Condition begin\n    @parameters __c::Real = " * text * "\nend\n"
    pb = try
        BGSim.parse_block(src; filename = "breakpoint condition", ref = "inline:__condition")
    catch err
        report("E001", "invalid breakpoint condition: " * sprint(showerror, err),
            "write an expression such as `k == 5` or `abs(v) > umax`")
        return nothing, diags
    end
    ds = BGSim.declarations(pb, :parameters)
    errors = [d for d in BGSim.block_diagnostics(pb) if d.severity == "error"]
    if !isempty(errors) || length(ds) != 1 || ds[1].default === nothing
        message = "invalid breakpoint condition `$text`"
        isempty(errors) || (message *= ": " * errors[1].message)
        report("E001", message, "write an expression such as `k == 5` or `abs(v) > umax`")
        return nothing, diags
    end
    expr = ds[1].default
    names = Symbol[]
    _condition_names!(names, expr, report)
    isempty(diags) || return nothing, diags
    return CompiledCondition(text, expr, names), diags
end

function _in_scope(scope::SiteScope, name::Symbol)
    name === :t && return true
    name === :Ts && return true
    for list in (scope.locals, scope.held, scope.reads), b in list
        b.name === name && return true
    end
    return false
end

# ---------------------------------------------------------------------------------------
# Resolving line breakpoints (D21)
# ---------------------------------------------------------------------------------------

mutable struct LineBp
    bp::Breakpoint
    condition::Union{Nothing,CompiledCondition}
end

function _validate_line(data, raw)
    ref = get(data, "ref", nothing)
    ref isa AbstractString && !isempty(ref) ||
        throw(ArgumentError("a line breakpoint needs a block reference `line.ref`"))
    line = get(data, "line", nothing)
    line isa Integer && line >= 1 ||
        throw(ArgumentError("a line breakpoint needs a positive integer `line.line`"))
    path = get(data, "path", nothing)
    path === nothing || path isa AbstractString ||
        throw(ArgumentError("`line.path` must be a string or null"))
    return nothing
end

# The smallest source item that contains `line`: its scope and range.
function _classify_line(items, line::Int)
    best = nothing
    if items !== nothing
        for item in items
            r = item.range
            (r.line <= line <= r.endLine) || continue
            if best === nothing || (r.endLine - r.line) < (best.range.endLine - best.range.line)
                best = item
            end
        end
    end
    return best
end

const _EQUATION_HINT =
    "equations do not execute in order; add a watch breakpoint on a signal instead"

function _e401(bp::Breakpoint, info, ref::String, line::Int, path)
    item = _classify_line(info === nothing ? nothing : get(info.items, ref, nothing), line)
    scope = item === nothing ? nothing : item.scope
    hint = if scope == "@events"
        "an @events body lowers to an event, not to statements; add an event breakpoint instead"
    elseif scope == "@discrete"
        "this line holds no statement; put the breakpoint on an assignment or `if` inside the " *
        "@discrete body"
    elseif scope === nothing
        "this line holds no statement; put the breakpoint on an assignment or `if` inside a " *
        "@discrete body"
    else
        _EQUATION_HINT
    end
    range = item === nothing ? SourceRange("", line, 1, line, 1) : item.range
    return to_namedtuple(diag(
        "E401", "no statement on line $line of $ref";
        hint = hint, path = path, block = ref, scope = scope,
        source = SourceRef(source_kind(ref), ref, range),
    ))
end

function _w401(bp::Breakpoint, ref::String, path, paths)
    if path === nothing || isempty(paths)
        return to_namedtuple(diag(
            "W401", "the breakpoint's block is not used in this model, so it stays unverified";
            hint = "instantiate $ref in the model or remove the breakpoint", block = ref,
        ))
    end
    return to_namedtuple(diag(
        "W401", "instance `$path` is not an instance of $ref, so the breakpoint stays unverified";
        hint = "use one of: " * join(paths, ", ") * ", or leave the path empty",
        path = path, block = ref,
    ))
end

function _matching_hooks(sites, ref::String, line::Int, path)
    hooks = Int[]
    for (k, site) in enumerate(sites)
        site.ref == ref || continue
        path === nothing || site.path == path || continue
        r = site.range
        hit = site.kind === :if ? r.line == line : r.line <= line <= r.endLine
        hit && push!(hooks, k)
    end
    return hooks
end

function _resolve_line_bp!(ctx::DebugCtx, s::DebugSession, h, bp::Breakpoint)
    ref = String(bp.data["ref"])
    line = Int(bp.data["line"])
    path = get(bp.data, "path", nothing)
    path = path === nothing ? nothing : String(path)
    flat = s.flat
    instance_paths = String[i.path for i in flat.instances if i.ref == ref]
    if isempty(instance_paths) || (path !== nothing && !(path in instance_paths))
        return breakpoint_status(
            bp; verified = false, diagnostics = Any[_w401(bp, ref, path, instance_paths)]
        )
    end
    sites = h === nothing ? Compile.HookSite[] : h.emit.sites
    hooks = _matching_hooks(sites, ref, line, path)
    if isempty(hooks)
        return breakpoint_status(bp; verified = false, diagnostics = Any[
            _e401(bp, Compile.block_info(flat), ref, line, path)
        ])
    end
    paths = unique(String[sites[k].path for k in hooks])
    condition = nothing
    if bp.condition !== nothing && !isempty(strip(bp.condition))
        condition, diags = _compile_condition(String(strip(bp.condition)), ref, path)
        if condition !== nothing
            for k in hooks
                scope = _site_scope(h, s, k)
                for name in condition.names
                    _in_scope(scope, name) && continue
                    site = sites[k]
                    push!(diags, _cond_diag(
                        "E003",
                        "`$name` is not in scope at line $(site.range.line) of $(site.path)",
                        ref, site.path;
                        hint = "a condition may use the temporaries assigned before the line, " *
                               "the held values, the parameters and inputs the partition " *
                               "reads, `t` and `Ts`",
                    ))
                    break
                end
            end
        end
        if !isempty(diags)
            return breakpoint_status(
                bp; verified = false, hooks = length(hooks), paths = paths, diagnostics = diags
            )
        end
    end
    if bp.enabled
        previous = get(h.hits, bp.id, nothing)
        previous !== nothing && previous[1] == bp.raw || (h.hits[bp.id] = (bp.raw, 0))
        push!(h.lines, LineBp(bp, condition))
        for k in hooks
            h.armed[k] = true
            push!(h.by_hook[k], length(h.lines))
        end
    end
    return breakpoint_status(bp; verified = true, hooks = length(hooks), paths = paths)
end

function _resolve_lines!(ctx::DebugCtx, s::Union{Nothing,DebugSession}, bps::Vector{Breakpoint})
    h = get(ctx.ext, :hooks, nothing)
    if h !== nothing
        fill!(h.armed, false)
        empty!(h.lines)
        foreach(empty!, h.by_hook)
    end
    # Before the run exists there is no hook table: the breakpoints bind when it starts.
    s === nothing && return NamedTuple[breakpoint_status(bp; verified = false) for bp in bps]
    return NamedTuple[_resolve_line_bp!(ctx, s, h, bp) for bp in bps]
end

register_breakpoint_kind!("line", _resolve_lines!; validate = _validate_line)
register_step_granularity!("statement")

# ---------------------------------------------------------------------------------------
# The hook itself
# ---------------------------------------------------------------------------------------

# Evaluate one breakpoint at one hook; true when it fires. A condition that fails to
# evaluate fires (the pause carries the diagnostic), like a debugger would.
function _line_hit!(h::HookState, lb::LineBp, s::DebugSession, k::Int, temps, diags)
    bp = lb.bp
    if lb.condition !== nothing
        scope = _site_scope(h, s, k)
        env = _frame_env(scope, s.run, temps, lb.condition.names)
        ok = try
            v = BGSim.eval_const(lb.condition.expr, env)
            v isa Bool ? v : (v isa Real ? v != 0 : error("the condition is not a Bool"))
        catch err
            message = err isa BGSim.ConstFoldError ? err.message : sprint(showerror, err)
            push!(diags, to_namedtuple(diag(
                "E004", "the breakpoint condition `$(lb.condition.text)` failed: $message";
                hint = "fix the condition or remove it", path = h.emit.sites[k].path,
                block = h.emit.sites[k].ref, scope = "breakpoint condition",
            )))
            return true
        end
        ok || return false
    end
    raw, hits = h.hits[bp.id]
    hits += 1
    h.hits[bp.id] = (raw, hits)
    return bp.hit_count === nothing || hits == bp.hit_count
end

function _hook_entry(h::HookState, k::Int, temps)
    ctx = h.ctx
    ctx.cancel_flag[] && return nothing
    s = ctx.session
    s isa DebugSession || return nothing
    reason = nothing
    bp_id = nothing
    diags = Any[]
    if h.armed[k]
        for i in h.by_hook[k]
            lb = h.lines[i]
            if _line_hit!(h, lb, s, k, temps, diags) && bp_id === nothing
                bp_id = lb.bp.id
            end
        end
        bp_id === nothing || (reason = "breakpoint")
    end
    if reason === nothing && ctx.step_mode === :statement
        reason = "step"
    end
    reason === nothing && return nothing
    frame = _capture_frame(h, s, k, temps)
    ctx.ext[:frame] = frame
    try
        dbg_pause!(
            s, reason; breakpoint_id = bp_id, location = _site_location(frame.site),
            frame = frame.view, diagnostics = diags,
        )
    finally
        delete!(ctx.ext, :frame)
    end
    return nothing
end

export HookState, DebugStep, PausedFrame, paused_frame
