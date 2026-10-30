# The registered intrinsics -> calls into the C runtime (plan/EXPORT_PLAN.md, J-EX5).
#
# `cexpr` hands every call to `cexpr_intrinsic` first. It maps the opaque functions of
# src/lower/fnmap.jl to their C twins in `bg_intrinsics.c` and `bg_mech.c`, and returns
# `nothing` for every other operation. `csv_value` (`bg_csv`) is refused: a CSV source is
# simulation data, and the host supplies such a signal through an ExportInput.
#
# Tables. `interp1`/`interp2` receive their tables as `SymbolicUtils.array_literal(shape,
# elems...)` terms (elements column-major). When every element is a literal (the parameters
# are folded, D-EX10), the table becomes one file-scope `static const double bg_tab<k>[]` in
# model.c, shared by every call site with the same content. A table with a runtime element
# (a tunable parameter) becomes a local array in each function that reads it.
#
# Calling convention for the functions with several results. The Julia functions return one
# component per call (`bg_exp3(w..., v..., k)`); the C twins write all components into an
# array. Within one generated function, each distinct argument tuple is called once into a
# local array `bg_mv<k>`, declared just before the first statement that needs it, and every
# component is a read `bg_mv<k>[k - 1]`. That keeps the common-subexpression property of the
# observed locals: seven components of one `exp` cost one call. `emit_function` flushes the
# pending declarations (`flush_intrinsic_statements`) before each statement it prints.
#
# The state lives in an `IntrinsicContext` in task-local storage for the duration of one
# `with_intrinsics` block (one model.c), so `cexpr` keeps its signature.

"""Per-model emission state for the intrinsic calls (see the file header)."""
mutable struct IntrinsicContext
    # file scope: name => C definition text, in first-use order, and the size report
    tables::Dict{String,String}          # content key => name
    definitions::Vector{String}
    report::Vector{Dict{String,Any}}
    # function scope
    open::Bool
    calls::Dict{String,String}           # call key => local array name
    pending::Vector{String}
    nlocal::Int
end

IntrinsicContext() = IntrinsicContext(Dict{String,String}(), String[], Dict{String,Any}[],
    false, Dict{String,String}(), String[], 0)

const _INTRINSIC_KEY = :bg_export_intrinsics

"""    with_intrinsics(f) -> IntrinsicContext

Run `f()` (the emission of one model.c) with a fresh context and return it; pass it to
`splice_intrinsics` and `intrinsics_report`."""
function with_intrinsics(f)
    ctx = IntrinsicContext()
    task_local_storage(f, _INTRINSIC_KEY, ctx)
    return ctx
end

_intrinsic_context() = get(task_local_storage(), _INTRINSIC_KEY, nothing)

"""    begin_intrinsic_scope(), end_intrinsic_scope()

The local arrays of one generated C function: `emit_function` opens the scope before its
first statement and closes it after the last."""
function begin_intrinsic_scope()
    ctx = _intrinsic_context()
    ctx === nothing && return nothing
    ctx.open = true
    empty!(ctx.calls)
    empty!(ctx.pending)
    return nothing
end

function end_intrinsic_scope()
    ctx = _intrinsic_context()
    ctx === nothing && return nothing
    isempty(ctx.pending) || error("intrinsic statements left unflushed")
    ctx.open = false
    empty!(ctx.calls)
    return nothing
end

"""    flush_intrinsic_statements(io, pad = "    ")

Print the local array declarations and calls the last `cexpr` needs, before its statement."""
function flush_intrinsic_statements(io, pad::AbstractString = "    ")
    ctx = _intrinsic_context()
    (ctx === nothing || isempty(ctx.pending)) && return nothing
    for s in ctx.pending
        println(io, pad, s)
    end
    empty!(ctx.pending)
    return nothing
end

"""    splice_intrinsics(src, ctx) -> String

Insert the runtime includes and the table definitions into the generated model.c, right
after its `bg_runtime.h` include (tables must precede the functions that read them)."""
function splice_intrinsics(src::AbstractString, ctx::IntrinsicContext)
    marker = "#include \"bg_runtime.h\"\n"
    buf = IOBuffer()
    println(buf, "#include \"bg_intrinsics.h\"\n#include \"bg_mech.h\"")
    if !isempty(ctx.definitions)
        println(buf)
        foreach(d -> print(buf, d), ctx.definitions)
    end
    block = String(take!(buf))
    occursin(marker, src) || return block * src
    return replace(src, marker => marker * block; count = 1)
end

"""    intrinsics_report(ctx) -> Dict

The size report of the constant tables for export.json: every table with its kind, its
number of values and bytes, and the total."""
function intrinsics_report(ctx::IntrinsicContext)
    return Dict{String,Any}(
        "count" => length(ctx.report),
        "bytes" => sum((r["bytes"] for r in ctx.report); init = 0),
        "tables" => ctx.report,
    )
end

# ---------------------------------------------------------------------------------------

function _need_context(what)
    ctx = _intrinsic_context()
    ctx === nothing &&
        throw(ExportError("$what can only be emitted inside `with_intrinsics` (model.c emission)"))
    return ctx
end

function _need_scope(what)
    ctx = _need_context(what)
    ctx.open || throw(ExportError("$what can only be emitted inside a generated function body"))
    return ctx
end

function _is_array_literal(x)
    y = Symbolics.unwrap(x)
    return isdefined(SymbolicUtils, :array_literal) && SymbolicUtils.iscall(y) &&
           SymbolicUtils.operation(y) === SymbolicUtils.array_literal
end

_is_c_literal(s::AbstractString) =
    occursin(r"^\(?-?(\d[\d.]*(e[+-]?\d+)?|INFINITY)\)?$|^NAN$", s)

function _const_int(x, what)
    c = _try_const(Symbolics.unwrap(x))
    (c isa Real && isinteger(c)) ||
        throw(ExportError("$what must be a literal integer, got `$x`"))
    return Int(c)
end

function _c_values(io, vals::AbstractVector{<:AbstractString})
    for (k, v) in enumerate(vals)
        print(io, k == 1 ? "    " : (k - 1) % 8 == 0 ? ",\n    " : ", ", v)
    end
    println(io)
end

"""    _table(arg, env, modes, what) -> (C name, shape)

The C array of one `array_literal` table argument; a matrix is written row-major."""
function _table(arg, env, modes, what)
    a = Symbolics.unwrap(arg)
    _is_array_literal(a) ||
        throw(ExportError("$what needs a literal table (an array parameter), got `$a`"))
    targs = SymbolicUtils.arguments(a)
    s = _try_const(targs[1])
    shape = Tuple(Int.(s === nothing ? targs[1] : s))
    elems = String[cexpr(e, env, modes) for e in targs[2:end]]
    length(elems) == prod(shape) ||
        throw(ExportError("$what: the table has $(length(elems)) values for the shape $shape"))
    isempty(elems) && throw(ExportError("$what: the table is empty"))
    # Column-major (Julia order) -> row-major (C order) for a matrix.
    if length(shape) == 2
        r, c = shape
        elems = [elems[(j - 1) * r + i] for i in 1:r for j in 1:c]
    end
    ctx = _need_context(what)
    n = length(elems)
    if all(_is_c_literal, elems)
        key = join(elems, ",")
        name = get(ctx.tables, key, nothing)
        if name === nothing
            name = "bg_tab$(length(ctx.tables))"
            ctx.tables[key] = name
            io = IOBuffer()
            println(io, "/* table $(ccomment(what)), shape $(join(shape, "x")) */")
            println(io, "static const double $(name)[$n] = {")
            _c_values(io, elems)
            println(io, "};")
            push!(ctx.definitions, String(take!(io)))
            push!(ctx.report, Dict{String,Any}("name" => name, "kind" => what,
                "shape" => collect(shape), "values" => n, "bytes" => 8n))
        end
        return name, shape
    end
    # A runtime element: a local array in this function.
    ctx = _need_scope(what)
    key = "tab|" * join(elems, ",")
    name = get(ctx.calls, key, nothing)
    if name === nothing
        name = "bg_lt$(ctx.nlocal)"
        ctx.nlocal += 1
        ctx.calls[key] = name
        push!(ctx.pending, "const double $(name)[$n] = {" * join(elems, ", ") * "};")
    end
    return name, shape
end

"""The E110 hint for `csv_value`, shared with the block-level refusal in `export_model`."""
const CSV_EXPORT_HINT = "a CSV source is simulation data; in an export variant replace it with an ExportInput (or remove it)"

# name => number of components of the C twin's `out` array
const MECH_MULTI = Dict{Symbol,Int}(
    :bg_exp2 => 3, :bg_log2 => 3, :bg_exp3 => 7, :bg_log3 => 6,
    :bg_quat_exp => 4, :bg_quat_log => 3, :bg_quat_from_rotation => 4,
)

const _INTRINSIC_FNS = IdDict{Any,Symbol}(f => nameof(f) for f in (
    BGSim.bg_interp1, BGSim.bg_interp2, BGSim.bg_csv, BGSim.bg_exp2, BGSim.bg_log2,
    BGSim.bg_exp3, BGSim.bg_log3, BGSim.bg_quat_exp, BGSim.bg_quat_log,
    BGSim.bg_quat_from_rotation, BGSim.bg_inertia2, BGSim.bg_inertia3))

_bgsim_fn(op) = get(_INTRINSIC_FNS, op, nothing)

"""    cexpr_intrinsic(op, args, env, modes) -> String or nothing

The C expression of an intrinsic call, or `nothing` when `op` is not an intrinsic."""
function cexpr_intrinsic(op, args, env, modes)
    name = _bgsim_fn(op)
    if name === :bg_interp1
        u = cexpr(args[1], env, modes)
        xs, sx = _table(args[2], env, modes, "interp1")
        ys, sy = _table(args[3], env, modes, "interp1")
        prod(sx) == prod(sy) ||
            throw(ExportError("interp1: the breakpoints and values differ in length"))
        return "bg_interp1($u, $xs, $ys, $(prod(sx)))"
    elseif name === :bg_interp2
        u = cexpr(args[1], env, modes)
        v = cexpr(args[2], env, modes)
        br, sb = _table(args[3], env, modes, "interp2")
        tb, st = _table(args[4], env, modes, "interp2")
        n = length(sb) == 2 ? sb[2] : 0
        (sb == (2, n) && st == (n, n)) || throw(ExportError(
            "interp2: a 2x$n breakpoint matrix needs a $(n)x$n table, got $(join(st, "x"))"))
        return "bg_interp2($u, $v, $br, $tb, $n)"
    elseif name === :bg_csv
        throw(ExportError("`csv_value` is not exported: $CSV_EXPORT_HINT"))
    elseif name === :bg_inertia2 || name === :bg_inertia3
        a = String[cexpr(y, env, modes) for y in args[1:end - 2]]
        i = _const_int(args[end - 1], "$name: the row")
        j = _const_int(args[end], "$name: the column")
        return "$name(" * join(a, ", ") * ", $i, $j)"
    elseif name !== nothing && haskey(MECH_MULTI, name)
        ncomp = MECH_MULTI[name]
        k = _const_int(args[end], "$name: the component")
        1 <= k <= ncomp || throw(ExportError("$name: component $k is not in 1:$ncomp"))
        a = String[cexpr(y, env, modes) for y in args[1:end - 1]]
        ctx = _need_scope("`$name`")
        key = "$name(" * join(a, ", ") * ")"
        local_name = get(ctx.calls, key, nothing)
        if local_name === nothing
            local_name = "bg_mv$(ctx.nlocal)"
            ctx.nlocal += 1
            ctx.calls[key] = local_name
            push!(ctx.pending, "double $(local_name)[$ncomp];")
            push!(ctx.pending, "$name(" * join(a, ", ") * ", $(local_name));")
        end
        return "$(local_name)[$(k - 1)]"
    end
    any(_is_array_literal ∘ Symbolics.unwrap, args) && throw(ExportError(
        "`$(nameof_op(op))` with table arguments has no C implementation yet (plan J-EX5)"))
    return nothing
end
