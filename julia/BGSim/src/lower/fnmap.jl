# Lowering of the front-end AST to Symbolics (plan section 5.8).
#
# `fnmap.jl` is the one place where a language function becomes a Symbolics expression. The
# whitelist in `src/syntax/whitelist.jl` decides *whether* a function is allowed; this file
# decides *what it means*. The flat model (`src/ir/flat.jl`) already contains only scalar
# expressions with fully qualified names, arrays unrolled, `for` loops expanded, `if`
# equations split, and `dot`/`norm`/`cross`/`transpose` turned into scalar arithmetic by the
# flattener. That is why every expression here is scalar.
#
# Rules that matter:
#
# * `ddt` becomes `D` (`ModelingToolkit.D_nounits`), never a string nor `eval`.
# * `int(x, x0)` is sugar for a new state with `D(s) ~ x` and the start value `x0` (the spec
#   calls it "sugar for a new state with ddt"). The state is named deterministically from the
#   instance path and a counter, and its start expression is kept in the AST so a
#   parameter-only re-run can evaluate it with the current parameter values.
# * Nonsmooth functions are rewritten into `ifelse` forms. Symbolics could evaluate `abs`,
#   `min`, `max` and `clamp` itself, but rewriting makes every switching condition explicit,
#   which is what the J2.3 event collector needs, and avoids relying on derivatives of
#   non-differentiable heads.
# * `&&`, `||` and `!` are lowered to Symbolics' boolean operators `&`, `|` and `!`; they only
#   occur inside an `ifelse` condition in `@equations` (checked by the front end).
# * Intrinsics and discrete samplers (`interp1`, `interp2`, `delay`, `noise_normal`,
#   `previous`, `hold`, `reinit`) are not part of the continuous M1 lowering. They raise a
#   `LowerError` that `simulate` reports as E900 with the block path; the work packages that
#   add them (J2.2, J2.3, J2.7b) extend this table. Nothing here silently returns zero.
# * `interp1`/`interp2` are **opaque registered functions** (plan D12): the numeric
#   implementations live below, `Symbolics.@register_symbolic` makes the lowering emit one
#   `bg_interp1(...)` term instead of an unrolled table search, and the generated RHS calls
#   the numeric method at run time. `delay` and `noise_normal` still raise a `LowerError`
#   (see `lower_call`).
# * J-MB3 adds the screw algebra (`bg_exp2`, `bg_Ad`…): the component functions below are
#   the scalar interface to `src/mech/`, and `lower_mech` builds them from the pose
#   functions of the spec. They are generic over `Real` because the solver's Jacobian calls
#   them with `ForwardDiff.Dual` numbers.

using StaticArrays: SVector, SMatrix

"""
    bg_interp1(u, xs, ys)

The D12 piecewise-linear 1-D table lookup, as an opaque Symbolics function. `xs` are the
strictly increasing breakpoints and `ys` the value at each breakpoint; outside the table the
first/last value is held. `interp1` calls it through
[`lower_call`](@ref); the plain-Julia method below is what the compiled right-hand side runs.
"""
function bg_interp1(u::Real, xs::AbstractVector, ys::AbstractVector)
    n = length(xs)
    length(ys) == n ||
        throw(ArgumentError("interp1: the abscissa and ordinate need the same length"))
    n == 0 && throw(ArgumentError("interp1: the table is empty"))
    u <= xs[1] && return ys[1]
    u >= xs[n] && return ys[n]
    k = 1
    while k < n - 1 && u > xs[k + 1]
        k += 1
    end
    x0, x1 = xs[k], xs[k + 1]
    x1 == x0 && return ys[k]
    w = (u - x0) / (x1 - x0)
    # Arithmetic stays generic: the adaptive solver calls this with `ForwardDiff.Dual`
    # numbers for its time gradient, so nothing may convert to `Float64`.
    return (one(w) - w) * ys[k] + w * ys[k + 1]
end

"""
    bg_interp2(u, v, breaks, table)

The D12 bilinear 2-D table lookup, as an opaque Symbolics function. Row 1 of `breaks` holds
the x breakpoints and row 2 the y breakpoints; `table[i,j]` is the value at
`(x = breaks[1,j], y = breaks[2,i])`, so `table` is `length(x-axis) × length(y-axis)` and the
two axes have the same number of points (a square grid, `Lookup2D` declares it with one
structural constant `N`). Outside the grid the edge value is held. `interp2` calls it through
[`lower_call`](@ref); the method below is what the compiled right-hand side runs.
"""
function bg_interp2(u::Real, v::Real, breaks::AbstractMatrix, table::AbstractMatrix)
    size(breaks, 1) == 2 ||
        throw(ArgumentError("interp2: `breaks` needs two rows (x, then y)"))
    nx = size(breaks, 2)
    size(table, 1) == nx && size(table, 2) == nx || throw(ArgumentError(
        "interp2: a $(nx)x$(nx) grid needs a $(nx)x$(nx) table, got $(size(table))"
    ))
    nx == 0 && throw(ArgumentError("interp2: the table is empty"))
    ux = u
    vx = v
    ux <= breaks[1, 1] && (ux = breaks[1, 1])
    ux >= breaks[1, nx] && (ux = breaks[1, nx])
    vx <= breaks[2, 1] && (vx = breaks[2, 1])
    vx >= breaks[2, nx] && (vx = breaks[2, nx])
    j = 1
    while j < nx - 1 && ux > breaks[1, j + 1]
        j += 1
    end
    i = 1
    while i < nx - 1 && vx > breaks[2, i + 1]
        i += 1
    end
    x0, x1 = breaks[1, j], breaks[1, j + 1]
    y0, y1 = breaks[2, i], breaks[2, i + 1]
    fx = x1 == x0 ? zero(ux) : (ux - x0) / (x1 - x0)
    fy = y1 == y0 ? zero(vx) : (vx - y0) / (y1 - y0)
    # Generic arithmetic again: no `Float64` conversion, so ForwardDiff duals pass through.
    low = (one(fx) - fx) * table[i, j] + fx * table[i, j + 1]
    high = (one(fx) - fx) * table[i + 1, j] + fx * table[i + 1, j + 1]
    return (one(fy) - fy) * low + fy * high
end

Symbolics.@register_symbolic bg_interp1(
    u::Real, xs::AbstractVector, ys::AbstractVector
)
Symbolics.@register_symbolic bg_interp2(
    u::Real, v::Real, breaks::AbstractMatrix, table::AbstractMatrix
)

# ---------------------------------------------------------------------------------------
# J-MB3: the screw algebra for equations
# ---------------------------------------------------------------------------------------
# The flat IR is scalar (see the file header), so every screw function that an equation can
# call has a **component form** here: the pose/twist/quaternion components as separate
# scalar arguments plus a 1-based selector (`k`, or a row/column pair). A block writes its
# component-wise loop (plan 5.3, D-MB10) and calls exactly these functions, and the
# lowering of the spec's `Ad(g)`/`exp(T)`/... builds the same calls (see `lower_mech`).
#
# Only the functions whose closed form has a branch that cannot be taken symbolically are
# opaque registered functions: `exp`, `log`, the quaternion exponential/logarithm and the
# quaternion-of-a-matrix branch. Everything else (`hat`, `vee`, `Ad`, `ad`, `compose`,
# `inv`, `spatial_inertia`, the quaternion products and rotations) expands into scalar
# arithmetic, which Symbolics can differentiate itself.
#
# The solver's Jacobian calls these methods with `ForwardDiff.Dual` numbers (probe in
# NOTES.md), so nothing here may convert to `Float64`: the numeric core is generic over
# `Real` and every branch compares primal values.
#
# `@register_symbolic` gives each of them an *opaque* symbolic term: `mtkcompile` keeps one
# call instead of unrolling it, and `Symbolics.derivative` of such a term returns an
# unevaluated `Differential` (verified). No explicit derivative rule is registered because
# no path in this milestone differentiates a pose *symbolically*: poses are algebraic
# functions of the states (D-MB6) and the solver differentiates the generated right-hand
# side numerically. NOTES.md records the probe and the one unsupported form
# (`ddt(pose_function(...))`, which MTK reports rather than silently accepting).

function _component(k::Integer, r, name::String)
    k in r || throw(ArgumentError("$name: component $k is not in $r"))
    return Int(k)
end

"""    bg_exp2(ω, vx, vy, k)

Component `k` of the planar pose chart `(θ, p_x, p_y)` of `exp([ω, vx, vy])` (the `Vec{3}`
form of [`exp`](@ref) in `src/mech/se2.jl`)."""
function bg_exp2(ω::Real, vx::Real, vy::Real, k::Integer)
    c = Mech.chart(exp(Mech.Twist{3}(ω, vx, vy)))
    return c[_component(k, 1:3, "bg_exp2")]
end

"""    bg_log2(θ, px, py, k)

Component `k` of the planar twist `[ω, vx, vy]` of `log(SE2(θ, p))`."""
function bg_log2(θ::Real, px::Real, py::Real, k::Integer)
    V = Mech.log(Mech.pose(Mech.SE2, SVector(θ, px, py)))
    return V[_component(k, 1:3, "bg_log2")]
end

"""    bg_exp3(wx, wy, wz, vx, vy, vz, k)

Component `k` of the spatial pose chart `(q_w, q_x, q_y, q_z, p_x, p_y, p_z)` of
`exp([ω; v])` (D-MB6: a quaternion plus a position)."""
function bg_exp3(wx::Real, wy::Real, wz::Real, vx::Real, vy::Real, vz::Real, k::Integer)
    c = Mech.chart(exp(Mech.Twist{6}(wx, wy, wz, vx, vy, vz)))
    return c[_component(k, 1:7, "bg_exp3")]
end

"""    bg_log3(qw, qx, qy, qz, px, py, pz, k)

Component `k` of the spatial twist `log(pose)` of a quaternion-plus-position chart."""
function bg_log3(qw::Real, qx::Real, qy::Real, qz::Real, px::Real, py::Real, pz::Real,
    k::Integer)
    V = Mech.log(Mech.pose(Mech.SE3, SVector(qw, qx, qy, qz, px, py, pz)))
    return V[_component(k, 1:6, "bg_log3")]
end

"""    bg_quat_mul(a0, a1, a2, a3, b0, b1, b2, b3, k)

Component `k` of the Hamilton product `a ⊗ b`."""
function bg_quat_mul(a0::Real, a1::Real, a2::Real, a3::Real,
    b0::Real, b1::Real, b2::Real, b3::Real, k::Integer)
    q = Mech.compose(Mech.Quat(a0, a1, a2, a3), Mech.Quat(b0, b1, b2, b3))
    return SVector{4}(q.w, q.x, q.y, q.z)[_component(k, 1:4, "bg_quat_mul")]
end

"""    bg_quat_normalise(q0, q1, q2, q3, k)

Component `k` of `q / |q|` (the D-MB6 normalisation of a quaternion state)."""
function bg_quat_normalise(q0::Real, q1::Real, q2::Real, q3::Real, k::Integer)
    q = normalise(Mech.Quat(q0, q1, q2, q3))
    return SVector{4}(q.w, q.x, q.y, q.z)[_component(k, 1:4, "bg_quat_normalise")]
end

"""    bg_quat_exp(wx, wy, wz, k)

Component `k` of the quaternion of the rotation vector `[wx, wy, wz]`."""
function bg_quat_exp(wx::Real, wy::Real, wz::Real, k::Integer)
    q = Mech.quat_exp(SVector(wx, wy, wz))
    return SVector{4}(q.w, q.x, q.y, q.z)[_component(k, 1:4, "bg_quat_exp")]
end

"""    bg_quat_log(q0, q1, q2, q3, k)

Component `k` of the principal rotation vector of a unit quaternion."""
function bg_quat_log(q0::Real, q1::Real, q2::Real, q3::Real, k::Integer)
    v = Mech.quat_log(Mech.Quat(q0, q1, q2, q3))
    return v[_component(k, 1:3, "bg_quat_log")]
end

"""    bg_quat_to_matrix(q0, q1, q2, q3, i, j)

Entry `(i, j)` of the rotation matrix of `normalise(q)`."""
function bg_quat_to_matrix(q0::Real, q1::Real, q2::Real, q3::Real, i::Integer, j::Integer)
    _component(i, 1:3, "bg_quat_to_matrix")
    _component(j, 1:3, "bg_quat_to_matrix")
    return Mech.quat_to_matrix(Mech.Quat(q0, q1, q2, q3))[i, j]
end

"""    bg_quat_from_rotation(r11, …, r33, k)

Component `k` of the quaternion of a 3x3 rotation matrix (row-major arguments, so
`r12` is `R[1, 2]`)."""
function bg_quat_from_rotation(r11::Real, r12::Real, r13::Real,
    r21::Real, r22::Real, r23::Real, r31::Real, r32::Real, r33::Real, k::Integer)
    R = SMatrix{3,3}(r11, r21, r31, r12, r22, r32, r13, r23, r33)
    q = Mech.quat_from_rotation(R)
    return SVector{4}(q.w, q.x, q.y, q.z)[_component(k, 1:4, "bg_quat_from_rotation")]
end

"""    bg_quat_rotate(q0, q1, q2, q3, vx, vy, vz, k)

Component `k` of `q v q*` (the rotation of a vector by a quaternion)."""
function bg_quat_rotate(q0::Real, q1::Real, q2::Real, q3::Real,
    vx::Real, vy::Real, vz::Real, k::Integer)
    v = Mech.quat_rotate(Mech.Quat(q0, q1, q2, q3), SVector(vx, vy, vz))
    return v[_component(k, 1:3, "bg_quat_rotate")]
end

"""    bg_inertia2(m, J, cx, cy, i, j)

Entry `(i, j)` of the planar inertia `planar_inertia(m, J, [cx, cy])` of
`src/mech/lie.jl`, without validation, so the solver's duals pass through."""
function bg_inertia2(m::Real, J::Real, cx::Real, cy::Real, i::Integer, j::Integer)
    _component(i, 1:3, "bg_inertia2")
    _component(j, 1:3, "bg_inertia2")
    z = zero(m)
    (i == 1 && j == 1) && return J + m * (cx^2 + cy^2)
    ((i == 1 && j == 2) || (i == 2 && j == 1)) && return -m * cy
    ((i == 1 && j == 3) || (i == 3 && j == 1)) && return m * cx
    (i == 2 && j == 2) && return m
    (i == 3 && j == 3) && return m
    return z
end

"""    bg_inertia3(m, J1, J2, J3, c1, c2, c3, i, j)

Entry `(i, j)` of `spatial_inertia(m, J, c)` for the diagonal principal inertia of D-MB3,
without validation."""
function bg_inertia3(m::Real, J1::Real, J2::Real, J3::Real,
    c1::Real, c2::Real, c3::Real, i::Integer, j::Integer)
    _component(i, 1:6, "bg_inertia3")
    _component(j, 1:6, "bg_inertia3")
    return Mech.inertia_entry(m, SVector(J1, J2, J3), SVector(c1, c2, c3), i, j)
end

for _f in (
    :(bg_exp2(ω::Real, vx::Real, vy::Real, k::Integer)),
    :(bg_log2(θ::Real, px::Real, py::Real, k::Integer)),
    :(bg_exp3(wx::Real, wy::Real, wz::Real, vx::Real, vy::Real, vz::Real, k::Integer)),
    :(bg_log3(qw::Real, qx::Real, qy::Real, qz::Real, px::Real, py::Real, pz::Real,
        k::Integer)),
    :(bg_quat_mul(a0::Real, a1::Real, a2::Real, a3::Real, b0::Real, b1::Real, b2::Real,
        b3::Real, k::Integer)),
    :(bg_quat_normalise(q0::Real, q1::Real, q2::Real, q3::Real, k::Integer)),
    :(bg_quat_exp(wx::Real, wy::Real, wz::Real, k::Integer)),
    :(bg_quat_log(q0::Real, q1::Real, q2::Real, q3::Real, k::Integer)),
    :(bg_quat_to_matrix(q0::Real, q1::Real, q2::Real, q3::Real, i::Integer, j::Integer)),
    :(bg_quat_from_rotation(r11::Real, r12::Real, r13::Real, r21::Real, r22::Real,
        r23::Real, r31::Real, r32::Real, r33::Real, k::Integer)),
    :(bg_quat_rotate(q0::Real, q1::Real, q2::Real, q3::Real, vx::Real, vy::Real,
        vz::Real, k::Integer)),
    :(bg_inertia2(m::Real, J::Real, cx::Real, cy::Real, i::Integer, j::Integer)),
    :(bg_inertia3(m::Real, J1::Real, J2::Real, J3::Real, c1::Real, c2::Real, c3::Real,
        i::Integer, j::Integer)),
)
    @eval Symbolics.@register_symbolic $_f
end

"""
    LowerError(message, path, block, range)

A construct the continuous lowering of this milestone cannot express, with the provenance
of the offending equation. `simulate` turns it into the E900 diagnostic of plan section 5.11;
the message ends up in the diagnostic's `hint` so the user sees which construct failed.
"""
struct LowerError <: Exception
    message::String
    path::Union{String,Nothing}
    block::Union{String,Nothing}
    range::Union{SourceRange,Nothing}
end

LowerError(message::AbstractString, origin::Union{Flat.Origin,Nothing}) = LowerError(
    String(message),
    origin === nothing ? nothing : origin.path,
    origin === nothing ? nothing : origin.block,
    origin === nothing ? nothing : origin.range,
)

function Base.showerror(io::IO, e::LowerError)
    print(io, e.message)
    e.path === nothing || print(io, " (in ", e.path, ")")
    return nothing
end

"""
    LowerCtx

The state shared by the expression walker: the signal-id → symbolic-variable maps, the extra
states created by `int`, the equations those states need, and the provenance of the equation
currently being lowered.
"""
mutable struct LowerCtx
    vars::Dict{String,Num}
    params::Dict{String,Num}
    int_states::Vector{Pair{Num,Any}}
    int_equations::Vector{Any}
    counter::Base.RefValue{Int}
    origin::Union{Flat.Origin,Nothing}
    event_values::Union{Dict{String,Any},Nothing}
end

LowerCtx(vars::Dict{String,Num}, params::Dict{String,Num}) =
    LowerCtx(vars, params, Pair{Num,Any}[], Any[], Ref(0), nothing, nothing)

_lower_error(message::AbstractString, ctx::LowerCtx) =
    throw(LowerError(message, ctx.origin))

"""    lower_expression(e, ctx) -> Any

Lower one scalar AST node to a Symbolics value. The result is a `Num` for symbolic nodes and
a Julia number for literals; arrays are returned as Julia arrays for the few contexts that
still need them (intrinsic arguments in later milestones).
"""
function lower_expression(e::Lit, ::LowerCtx)
    v = e.value
    if v isa Bool || v isa Integer || v isa AbstractFloat
        return v
    end
    throw(LowerError("literal $(repr(v)) cannot appear in an expression", nothing))
end

function lower_expression(e::Name, ctx::LowerCtx)
    e.name === :t && return t
    key = String(e.name)
    if ctx.event_values !== nothing && haskey(ctx.event_values, key)
        return ctx.event_values[key]
    end
    haskey(ctx.vars, key) && return ctx.event_values === nothing ? ctx.vars[key] :
                                ModelingToolkit.Pre(ctx.vars[key])
    haskey(ctx.params, key) && return ctx.params[key]
    return _lower_error("unknown name `$key` in a lowered expression", ctx)
end

function lower_expression(e::Field, ctx::LowerCtx)
    key = Flat.flat_id(e)
    if ctx.event_values !== nothing && haskey(ctx.event_values, key)
        return ctx.event_values[key]
    end
    haskey(ctx.vars, key) && return ctx.event_values === nothing ? ctx.vars[key] :
                                ModelingToolkit.Pre(ctx.vars[key])
    haskey(ctx.params, key) && return ctx.params[key]
    return _lower_error("unknown port field `$key` in a lowered expression", ctx)
end

function lower_expression(e::BinOp, ctx::LowerCtx)
    lhs = lower_expression(e.lhs, ctx)
    rhs = lower_expression(e.rhs, ctx)
    op = e.op
    op === :+ && return lhs + rhs
    op === :- && return lhs - rhs
    op === :* && return lhs * rhs
    op === :/ && return lhs / rhs
    op === Symbol("\\") && return rhs / lhs
    op === :^ && return lhs^rhs
    return _lower_error("operator `$op` cannot be lowered", ctx)
end

function lower_expression(e::UnOp, ctx::LowerCtx)
    x = lower_expression(e.operand, ctx)
    e.op === :- && return -x
    e.op === :+ && return x
    e.op === Symbol("!") && return !x
    return _lower_error("unary operator `$(e.op)` cannot be lowered", ctx)
end

function lower_expression(e::IfElse, ctx::LowerCtx)
    cond = lower_expression(e.cond, ctx)
    then = lower_expression(e.then, ctx)
    otherwise = lower_expression(e.otherwise, ctx)
    return ifelse(cond, then, otherwise)
end

function lower_expression(e::Comparison, ctx::LowerCtx)
    lhs = lower_expression(e.lhs, ctx)
    rhs = lower_expression(e.rhs, ctx)
    op = e.op
    op === :< && return lhs < rhs
    op === :<= && return lhs <= rhs
    op === :> && return lhs > rhs
    op === :>= && return lhs >= rhs
    op === Symbol("==") && return lhs == rhs
    op === Symbol("!=") && return lhs != rhs
    return _lower_error("comparison `$op` cannot be lowered", ctx)
end

function lower_expression(e::BoolOp, ctx::LowerCtx)
    values = [lower_expression(a, ctx) for a in e.operands]
    isempty(values) && return _lower_error("empty boolean expression", ctx)
    if e.op === Symbol("&&")
        out = values[1]
        for v in values[2:end]
            out = out & v
        end
        return out
    elseif e.op === Symbol("||")
        out = values[1]
        for v in values[2:end]
            out = out | v
        end
        return out
    elseif e.op === Symbol("!")
        length(values) == 1 || return _lower_error("`!` takes one operand", ctx)
        return !values[1]
    end
    return _lower_error("boolean operator `$(e.op)` cannot be lowered", ctx)
end

# ---------------------------------------------------------------------------------------
# Indexing and array literals
# ---------------------------------------------------------------------------------------

# The flattener expands arrays into `x[1]`-style scalar ids, so an `Index` normally does not
# survive. Keep the literal-index case for the later scopes (@initial, @events) that reuse
# this walker with a non-expanded AST.
function _literal_index_id(e::Index)
    indices = Int[]
    for i in e.indices
        i isa Lit && i.value isa Integer || return nothing
        push!(indices, Int(i.value))
    end
    if e.base isa Name
        return String(e.base.name) * "[" * join(indices, ",") * "]"
    elseif e.base isa Field
        return Flat.flat_id(e.base) * "[" * join(indices, ",") * "]"
    end
    return nothing
end

function lower_expression(e::Index, ctx::LowerCtx)
    key = _literal_index_id(e)
    key !== nothing && haskey(ctx.vars, key) && return ctx.vars[key]
    return _lower_error("array index `$(sprint(show, e))` cannot be lowered", ctx)
end

function lower_expression(e::VectorLit, ctx::LowerCtx)
    return [lower_expression(x, ctx) for x in e.elements]
end

function lower_expression(e::MatrixLit, ctx::LowerCtx)
    isempty(e.rows) && return Any[]
    ncols = length(e.rows[1])
    all(row -> length(row) == ncols, e.rows) ||
        return _lower_error("matrix literal rows have different lengths", ctx)
    return [lower_expression(e.rows[r][c], ctx) for r in eachindex(e.rows), c in 1:ncols]
end

# ---------------------------------------------------------------------------------------
# Calls
# ---------------------------------------------------------------------------------------

_one_arg(args, fn, ctx) = length(args) == 1 ? args[1] :
                          _lower_error("`$fn` takes one argument", ctx)

# ---------------------------------------------------------------------------------------
# J-MB3: the screw algebra
# ---------------------------------------------------------------------------------------
# The pose functions are overloaded on the *shape* of their argument, exactly as the spec
# overloads `exp`/`log`/`inv`/`*`: a `Vec{3}` is a planar pose or twist, a `Vec{6}` a
# spatial twist, a `Vec{7}` a spatial pose `(quaternion, position)`, and a `Mat` a matrix
# argument. The result is a Julia vector/matrix of scalar `Num`s, so the ordinary `*` and
# `+` of the surrounding equation keep working; only the branchy pieces become opaque
# `bg_*` calls (see the registration block above).

const MECH_CALLS = (
    :hat, :vee, :Ad, :ad, :compose, :inv, :spatial_inertia, :SE3, :rotation,
    :translation, :quat_compose, :quat_inv, :quat_normalise, :quat_exp, :quat_log,
    :quat_to_matrix, :quat_from_rotation, :quat_rotate,
)

_mech_error(fn, ctx) = _lower_error(
    "`$fn` needs a pose or twist vector (`Vec{3}` planar, `Vec{6}` spatial twist, " *
    "`Vec{7}` quaternion + position) or a matrix argument", ctx,
)

function _mech_vec(fn::Symbol, values, ctx::LowerCtx)
    length(values) == 1 || return _lower_error("`$fn` takes one argument", ctx)
    x = values[1]
    x isa AbstractVector || return _mech_error(fn, ctx)
    return x
end

# The 3x3 cross-product matrix as a symbolic matrix (the matrix analogue of `skew`).
function _hat3(a, b, c)
    z = zero(a)
    return [z -c b; c z -a; -b a z]
end

# The 3x3 rotation matrix of a quaternion chart, one opaque call per entry.
_quat_matrix(q) = [bg_quat_to_matrix(q[1], q[2], q[3], q[4], i, j) for i in 1:3, j in 1:3]

function lower_mech(fn::Symbol, values::AbstractVector, ctx::LowerCtx)
    if fn === :hat
        v = _mech_vec(fn, values, ctx)
        if length(v) == 3
            ω, vx, vy = v[1], v[2], v[3]
            z = zero(ω)
            return [z -ω vx; ω z vy; z z z]
        elseif length(v) == 6
            z = zero(v[1])
            return [z -v[3] v[2] v[4];
                v[3] z -v[1] v[5];
                -v[2] v[1] z v[6];
                z z z z]
        end
        return _mech_error(fn, ctx)
    elseif fn === :vee
        length(values) == 1 || return _lower_error("`vee` takes one argument", ctx)
        M = values[1]
        M isa AbstractMatrix || return _mech_error(fn, ctx)
        size(M) == (3, 3) && return [M[2, 1], M[1, 3], M[2, 3]]
        size(M) == (4, 4) &&
            return [M[3, 2], M[1, 3], M[2, 1], M[1, 4], M[2, 4], M[3, 4]]
        return _mech_error(fn, ctx)
    elseif fn === :Ad
        g = _mech_vec(fn, values, ctx)
        if length(g) == 3
            c, s = cos(g[1]), sin(g[1])
            z = zero(g[1])
            return [one(g[1]) z z; g[3] c -s; -g[2] s c]
        elseif length(g) == 7
            R = _quat_matrix(g[1:4])
            PR = _hat3(g[5], g[6], g[7]) * R
            return [R zero(R); PR R]
        end
        return _mech_error(fn, ctx)
    elseif fn === :ad
        v = _mech_vec(fn, values, ctx)
        if length(v) == 3
            z = zero(v[1])
            return [z z z; v[3] z -v[1]; -v[2] v[1] z]
        elseif length(v) == 6
            W = _hat3(v[1], v[2], v[3])
            Vc = _hat3(v[4], v[5], v[6])
            return [W zero(W); Vc W]
        end
        return _mech_error(fn, ctx)
    elseif fn === :compose
        length(values) == 2 || return _lower_error("`compose` takes two arguments", ctx)
        a, b = values[1], values[2]
        (a isa AbstractVector && b isa AbstractVector) || return _mech_error(fn, ctx)
        if length(a) == 3 && length(b) == 3
            c, s = cos(a[1]), sin(a[1])
            return [a[1] + b[1], a[2] + c * b[2] - s * b[3], a[3] + s * b[2] + c * b[3]]
        elseif length(a) == 7 && length(b) == 7
            q = [bg_quat_mul(a[1], a[2], a[3], a[4], b[1], b[2], b[3], b[4], k)
                 for k in 1:4]
            p = [a[4 + k] + bg_quat_rotate(a[1], a[2], a[3], a[4],
                b[5], b[6], b[7], k) for k in 1:3]
            return vcat(q, p)
        end
        return _mech_error(fn, ctx)
    elseif fn === :inv
        g = _mech_vec(fn, values, ctx)
        if length(g) == 3
            c, s = cos(g[1]), sin(g[1])
            return [-g[1], -(c * g[2] + s * g[3]), -(-s * g[2] + c * g[3])]
        elseif length(g) == 7
            # A unit quaternion's inverse is its conjugate.
            qi = [g[1], -g[2], -g[3], -g[4]]
            p = [-bg_quat_rotate(qi[1], qi[2], qi[3], qi[4], g[5], g[6], g[7], k)
                 for k in 1:3]
            return vcat(qi, p)
        end
        return _mech_error(fn, ctx)
    elseif fn === :exp
        isempty(values) && return _lower_error("`exp` takes one argument", ctx)
        x = values[1]
        x isa AbstractVector || return nothing  # the ordinary scalar exponential
        length(x) == 3 && return [bg_exp2(x[1], x[2], x[3], k) for k in 1:3]
        length(x) == 6 &&
            return [bg_exp3(x[1], x[2], x[3], x[4], x[5], x[6], k) for k in 1:7]
        return _mech_error(fn, ctx)
    elseif fn === :log
        isempty(values) && return _lower_error("`log` takes one argument", ctx)
        x = values[1]
        x isa AbstractVector || return nothing  # the ordinary scalar logarithm
        length(x) == 3 && return [bg_log2(x[1], x[2], x[3], k) for k in 1:3]
        length(x) == 7 && return [
            bg_log3(x[1], x[2], x[3], x[4], x[5], x[6], x[7], k) for k in 1:6
        ]
        return _mech_error(fn, ctx)
    elseif fn === :spatial_inertia
        2 <= length(values) <= 3 ||
            return _lower_error("`spatial_inertia` takes two or three arguments", ctx)
        m, Ic = values[1], values[2]
        c = length(values) == 3 ? values[3] : nothing
        if Ic isa AbstractMatrix
            size(Ic) == (3, 3) || return _lower_error(
                "`spatial_inertia` needs a `Mat{3,3}` rotational inertia", ctx
            )
            cv = if c === nothing
                (zero(m), zero(m), zero(m))
            elseif c isa AbstractVector && length(c) == 3
                (c[1], c[2], c[3])
            else
                return _lower_error(
                    "`spatial_inertia` needs a `Vec{3}` centre of mass for a spatial " *
                    "body", ctx
                )
            end
            z = zero(m)
            return [begin
                if i <= 3 && j <= 3
                    Ic[i, j] + m * ((i == j ? cv[1]^2 + cv[2]^2 + cv[3]^2 : z) -
                                    cv[i] * cv[j])
                elseif i <= 3
                    m * _skew_entry(cv, i, j - 3)
                elseif j <= 3
                    m * _skew_entry(cv, j, i - 3)
                elseif i == j
                    m
                else
                    z
                end
            end for i in 1:6, j in 1:6]
        else
            cv = if c === nothing
                (zero(m), zero(m))
            elseif c isa AbstractVector && length(c) == 2
                (c[1], c[2])
            else
                return _lower_error(
                    "`spatial_inertia` needs a `Vec{2}` centre of mass for a planar body",
                    ctx,
                )
            end
            z = zero(m)
            return [Ic + m * (cv[1]^2 + cv[2]^2) -m * cv[2] m * cv[1];
                -m * cv[2] m z;
                m * cv[1] z m]
        end
    elseif fn === :SE3
        if isempty(values)
            return [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        elseif length(values) == 2
            R, p = values[1], values[2]
            R isa AbstractMatrix && size(R) == (3, 3) || return _lower_error(
                "`SE3` needs a `Mat{3,3}` rotation and a `Vec{3}` position", ctx
            )
            p isa AbstractVector && length(p) == 3 || return _lower_error(
                "`SE3` needs a `Mat{3,3}` rotation and a `Vec{3}` position", ctx
            )
            q = [bg_quat_from_rotation(R[1, 1], R[1, 2], R[1, 3], R[2, 1], R[2, 2],
                R[2, 3], R[3, 1], R[3, 2], R[3, 3], k) for k in 1:4]
            return vcat(q, [p[1], p[2], p[3]])
        end
        return _lower_error("`SE3` takes no arguments or `SE3(R, p)`", ctx)
    elseif fn === :rotation
        g = _mech_vec(fn, values, ctx)
        if length(g) == 3
            c, s = cos(g[1]), sin(g[1])
            return [c -s; s c]
        elseif length(g) == 7
            return _quat_matrix(g[1:4])
        end
        return _mech_error(fn, ctx)
    elseif fn === :translation
        g = _mech_vec(fn, values, ctx)
        length(g) == 3 && return [g[2], g[3]]
        length(g) == 7 && return [g[5], g[6], g[7]]
        return _mech_error(fn, ctx)
    elseif fn === :quat_compose || fn === :quat_rotate
        nargs = fn === :quat_compose ? 2 : 2
        length(values) == nargs ||
            return _lower_error("`$fn` takes two arguments", ctx)
        a, b = values[1], values[2]
        if fn === :quat_compose
            (a isa AbstractVector && length(a) == 4 && b isa AbstractVector &&
             length(b) == 4) || return _lower_error(
                "`quat_compose` needs two `Vec{4}` quaternions", ctx
            )
            return [bg_quat_mul(a[1], a[2], a[3], a[4], b[1], b[2], b[3], b[4], k)
                    for k in 1:4]
        end
        (a isa AbstractVector && length(a) == 4 && b isa AbstractVector &&
         length(b) == 3) || return _lower_error(
            "`quat_rotate` needs a `Vec{4}` quaternion and a `Vec{3}` vector", ctx
        )
        return [bg_quat_rotate(a[1], a[2], a[3], a[4], b[1], b[2], b[3], k)
                for k in 1:3]
    elseif fn === :quat_inv
        q = _mech_vec(fn, values, ctx)
        length(q) == 4 || return _lower_error("`quat_inv` needs a `Vec{4}` quaternion", ctx)
        return [q[1], -q[2], -q[3], -q[4]]
    elseif fn === :quat_normalise
        q = _mech_vec(fn, values, ctx)
        length(q) == 4 ||
            return _lower_error("`quat_normalise` needs a `Vec{4}` quaternion", ctx)
        return [bg_quat_normalise(q[1], q[2], q[3], q[4], k) for k in 1:4]
    elseif fn === :quat_exp
        v = _mech_vec(fn, values, ctx)
        length(v) == 3 || return _lower_error(
            "`quat_exp` needs a `Vec{3}` rotation vector", ctx
        )
        return [bg_quat_exp(v[1], v[2], v[3], k) for k in 1:4]
    elseif fn === :quat_log
        q = _mech_vec(fn, values, ctx)
        length(q) == 4 ||
            return _lower_error("`quat_log` needs a `Vec{4}` quaternion", ctx)
        return [bg_quat_log(q[1], q[2], q[3], q[4], k) for k in 1:3]
    elseif fn === :quat_to_matrix
        q = _mech_vec(fn, values, ctx)
        length(q) == 4 ||
            return _lower_error("`quat_to_matrix` needs a `Vec{4}` quaternion", ctx)
        return _quat_matrix(q)
    elseif fn === :quat_from_rotation
        R = values[1]
        R isa AbstractMatrix && size(R) == (3, 3) || return _lower_error(
            "`quat_from_rotation` needs a `Mat{3,3}` rotation", ctx
        )
        return [bg_quat_from_rotation(R[1, 1], R[1, 2], R[1, 3], R[2, 1], R[2, 2],
            R[2, 3], R[3, 1], R[3, 2], R[3, 3], k) for k in 1:4]
    end
    return _mech_error(fn, ctx)
end

# The `(a, b)` entry of `skew(c)` as a plain expression (used by `spatial_inertia`).
function _skew_entry(c, a::Int, b::Int)
    (a == 1 && b == 2) && return -c[3]
    (a == 2 && b == 1) && return c[3]
    (a == 1 && b == 3) && return c[2]
    (a == 3 && b == 1) && return -c[2]
    (a == 2 && b == 3) && return -c[1]
    (a == 3 && b == 2) && return c[1]
    return zero(c[1])
end

function lower_expression(e::Call, ctx::LowerCtx)
    return lower_call(e.fn.name, e.args, ctx, e)
end

"""
    lower_call(fn::Symbol, args, ctx, node) -> Any

Lower one whitelisted call. `node` is the source node (used only for its range).
"""
function lower_call(fn::Symbol, args, ctx::LowerCtx, node)
    # Special forms that are not plain function calls.
    if fn === :ddt
        length(args) == 1 || return _lower_error("`ddt` takes one argument", ctx)
        return D(lower_expression(args[1], ctx))
    elseif fn === :int
        length(args) == 2 || return _lower_error("`int` takes two arguments", ctx)
        return _lower_int(args[1], args[2], ctx)
    elseif fn === :ifelse
        length(args) == 3 || return _lower_error("`ifelse` takes three arguments", ctx)
        return ifelse(
            lower_expression(args[1], ctx),
            lower_expression(args[2], ctx),
            lower_expression(args[3], ctx),
        )
    end

    # J-MB3: the screw algebra, dispatched on the shape of its arguments. `exp` and `log`
    # return `nothing` here for a scalar argument, so the ordinary scalar branch below
    # still handles them (`exp(x)` of a signal is the scalar exponential).
    if fn in MECH_CALLS || fn === :exp || fn === :log
        mech = lower_mech(fn, lower_args(args, ctx), ctx)
        mech === nothing || return mech
    end

    # Nonsmooth functions become explicit `ifelse` forms (see the file header).
    if fn === :abs
        x = _one_arg(lower_args(args, ctx), fn, ctx)
        return ifelse(x < 0, -x, x)
    elseif fn === :sign
        x = _one_arg(lower_args(args, ctx), fn, ctx)
        return ifelse(x > 0, 1.0, ifelse(x < 0, -1.0, 0.0))
    elseif fn === :min || fn === :max || fn === :clamp || fn === :saturate ||
           fn === :deadzone
        return lower_nonsmooth(fn, lower_args(args, ctx), ctx)
    elseif fn === :round
        length(args) == 1 || return _lower_error("`round` takes one argument", ctx)
        x = lower_expression(args[1], ctx)
        # `round` is round-half-away-from-zero; floor/ceil are native Symbolics heads.
        return ifelse(x >= 0, floor(x + 0.5), ceil(x - 0.5))
    elseif fn === :hypot
        length(args) == 2 || return _lower_error("`hypot` takes two arguments", ctx)
        a = lower_expression(args[1], ctx)
        b = lower_expression(args[2], ctx)
        return hypot(a, b)
    end

    # Pure scalar functions that Symbolics implements directly.
    if fn in (:sin, :cos, :tan, :asin, :acos, :sinh, :cosh, :tanh, :exp, :log, :log10,
        :sqrt, :floor, :ceil)
        length(args) == 1 || return _lower_error("`$fn` takes one argument", ctx)
        x = lower_expression(args[1], ctx)
        fn === :sin && return sin(x)
        fn === :cos && return cos(x)
        fn === :tan && return tan(x)
        fn === :asin && return asin(x)
        fn === :acos && return acos(x)
        fn === :sinh && return sinh(x)
        fn === :cosh && return cosh(x)
        fn === :tanh && return tanh(x)
        fn === :exp && return exp(x)
        fn === :log && return log(x)
        fn === :log10 && return log10(x)
        fn === :sqrt && return sqrt(x)
        fn === :floor && return floor(x)
        fn === :ceil && return ceil(x)
    elseif fn === :mod || fn === :rem
        length(args) == 2 || return _lower_error("`$fn` takes two arguments", ctx)
        a = lower_expression(args[1], ctx)
        b = lower_expression(args[2], ctx)
        return fn === :mod ? mod(a, b) : rem(a, b)
    elseif fn === :atan
        values = lower_args(args, ctx)
        length(values) == 1 && return atan(values[1])
        length(values) == 2 && return atan(values[1], values[2])
        return _lower_error("`atan` takes one or two arguments", ctx)
    elseif fn === :dot
        values = lower_args(args, ctx)
        length(values) == 2 || return _lower_error("`dot` takes two arguments", ctx)
        a, b = values
        if a isa AbstractArray && b isa AbstractArray
            length(a) == length(b) || return _lower_error("`dot` sizes differ", ctx)
            return sum(a[k] * b[k] for k in eachindex(a))
        end
        return a * b
    elseif fn === :norm
        values = lower_args(args, ctx)
        x = _one_arg(values, fn, ctx)
        return x isa AbstractArray ? sqrt(sum(abs2, x)) : abs(x)
    elseif fn === :cross
        values = lower_args(args, ctx)
        length(values) == 2 || return _lower_error("`cross` takes two arguments", ctx)
        a, b = values
        (a isa AbstractVector && b isa AbstractVector && length(a) == 3 &&
         length(b) == 3) || return _lower_error("`cross` needs two 3-vectors", ctx)
        return [
            a[2] * b[3] - a[3] * b[2],
            a[3] * b[1] - a[1] * b[3],
            a[1] * b[2] - a[2] * b[1],
        ]
    elseif fn === :transpose
        values = lower_args(args, ctx)
        x = _one_arg(values, fn, ctx)
        x isa AbstractMatrix && return permutedims(x)
        x isa AbstractVector && return x
        return _lower_error("`transpose` needs a vector or matrix", ctx)
    end

    # Discrete, event or M2 constructs. J2.2/J2.3/J2.7b extend this table; a clear error is
    # better than silently inventing a value.
    fn in (:previous, :hold, :reinit) && return _lower_error(
        "`$fn` is only lowered for discrete/event code (J2.2/J2.3)", ctx
    )
    if fn === :interp1 || fn === :interp2
        values = lower_args(args, ctx)
        (fn === :interp1 ? 3 : 4) == length(values) || return _lower_error(
            "`$fn` takes $(fn === :interp1 ? 3 : 4) arguments", ctx
        )
        return fn === :interp1 ? bg_interp1(values...) : bg_interp2(values...)
    end
    fn in (:delay, :noise_normal) && return _lower_error(
        "`$fn` is an intrinsic that this build does not lower yet", ctx
    )
    return _lower_error("function `$fn` cannot be lowered", ctx)
end

function lower_args(args, ctx::LowerCtx)
    return [lower_expression(a, ctx) for a in args]
end

function lower_nonsmooth(fn::Symbol, values, ctx::LowerCtx)
    if fn === :min
        2 <= length(values) <= 3 || return _lower_error("`min` takes two or three arguments", ctx)
        out = values[1]
        for v in values[2:end]
            out = ifelse(out <= v, out, v)
        end
        return out
    elseif fn === :max
        2 <= length(values) <= 3 || return _lower_error("`max` takes two or three arguments", ctx)
        out = values[1]
        for v in values[2:end]
            out = ifelse(out >= v, out, v)
        end
        return out
    elseif fn === :clamp || fn === :saturate
        length(values) in (2, 3) || return _lower_error(
            "`$fn` takes two or three arguments", ctx
        )
        if length(values) == 2
            x, hi = values
            lo = -hi
        else
            x, lo, hi = values
        end
        return ifelse(x < lo, lo, ifelse(x > hi, hi, x))
    elseif fn === :deadzone
        length(values) in (2, 3) || return _lower_error(
            "`deadzone` takes two or three arguments", ctx
        )
        if length(values) == 2
            x, hi = values
            lo = -hi
        else
            x, lo, hi = values
        end
        return ifelse(x > hi, x - hi, ifelse(x < lo, x - lo, 0.0))
    end
    return _lower_error("`$fn` cannot be lowered", ctx)
end

# ---------------------------------------------------------------------------------------
# `int(x, x0)`
# ---------------------------------------------------------------------------------------

"""
    _lower_int(x, x0, ctx) -> Num

Create the hidden state of `int(x, x0)`: a fresh scalar named from the origin path and a
per-model counter, with `D(state) ~ x` appended to the system and `x0` remembered as an AST
so the run can evaluate it with the parameter values of that run (D4).
"""
function _lower_int(x, x0, ctx::LowerCtx)
    ctx.counter[] += 1
    path = ctx.origin === nothing ? "model" : something(ctx.origin.path, "model")
    name = "__bgint/" * path * "/" * string(ctx.counter[])
    state = mtk_variable(name)
    rhs = lower_expression(x, ctx)
    push!(ctx.int_equations, D(state) ~ rhs)
    push!(ctx.int_states, state => x0)
    return state
end
