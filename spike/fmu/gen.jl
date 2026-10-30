# FMU export spike: generate C99 for one bg-sim model.
#
#   julia --project=julia/BGSim spike/fmu/gen.jl <project_dir> <model> <out_dir> \
#         [dt] [t_end] [method] [out_interval]
#
# Writes into <out_dir>:
#   sources/model.h, sources/model.c   generated model code (derivatives, Jacobian, outputs,
#                                      discrete partitions); the hand-written solver and
#                                      FMI wrapper in spike/fmu/ include model.h
#   modelDescription.xml               FMI 2.0 co-simulation description
#   meta.json                          value references and settings for check.py
#   reference/                         a tight-tolerance Julia run of the same model
#
# Spike scope (see README.md): ODE systems only (no algebraic unknowns after mtkcompile),
# continuous events are not emitted (nonsmooth conditions are evaluated per stage, which is
# the W203 behaviour), start values are baked at generation time.

using BGSim
using ModelingToolkit
using SymbolicIndexingInterface: getname, getu, getp
using OrdinaryDiffEqTsit5: Tsit5
import Symbolics
const SymbolicUtils = Symbolics.SymbolicUtils
import JSON3

const MTK = ModelingToolkit
const Compile = BGSim.Compile

# ---------------------------------------------------------------------------------------
# Symbolic expression -> C expression
# ---------------------------------------------------------------------------------------

clit(v::Bool) = v ? "1.0" : "0.0"
function clit(v::Real)
    f = Float64(v)
    isnan(f) && return "NAN"
    isinf(f) && return f > 0 ? "INFINITY" : "(-INFINITY)"
    s = repr(f)
    return f < 0 ? "($s)" : s
end

_const_value(x) = x isa Number ? x : nothing
function _try_const(x)
    x isa Number && return x
    if isdefined(SymbolicUtils, :isconst) && SymbolicUtils.isconst(x)
        return SymbolicUtils.unwrap_const(x)
    end
    return nothing
end

const C_MATH1 = Dict{Any,String}(
    sin => "sin", cos => "cos", tan => "tan", asin => "asin", acos => "acos",
    sinh => "sinh", cosh => "cosh", tanh => "tanh", exp => "exp", log => "log",
    log10 => "log10", sqrt => "sqrt", abs => "fabs", floor => "floor", ceil => "ceil",
    sign => "bg_sign", round => "bg_round",
)
const C_CMP = Dict{Any,String}(
    (>=) => ">=", (>) => ">", (<=) => "<=", (<) => "<", (==) => "==", (!=) => "!=",
)

# `modes`: when given, every `ifelse` condition is replaced by a frozen mode value `m->c[k]`
# (collected into `modes`), which `bg_modes` evaluates once at the start of each step.
function cexpr(x, env::Dict{Any,String}, modes = nothing)
    x = Symbolics.unwrap(x)
    s = get(env, x, nothing)
    s === nothing || return s
    c = _try_const(x)
    c === nothing || return clit(c)
    SymbolicUtils.iscall(x) || error("unsupported symbolic leaf `$x` ($(typeof(x)))")
    op = SymbolicUtils.operation(x)
    args = SymbolicUtils.arguments(x)
    if op === ifelse && modes !== nothing
        cond = Symbolics.unwrap(args[1])
        k = findfirst(c -> isequal(c, cond), modes)
        k === nothing && (push!(modes, cond); k = length(modes))
        return "((m->c[$(k - 1)] != 0.0) ? $(cexpr(args[2], env, modes)) : $(cexpr(args[3], env, modes)))"
    end
    a = String[cexpr(y, env, modes) for y in args]
    if op === (+)
        return "(" * join(a, " + ") * ")"
    elseif op === (*)
        return "(" * join(a, " * ") * ")"
    elseif op === (-)
        return length(a) == 1 ? "(-$(a[1]))" : "($(a[1]) - $(a[2]))"
    elseif op === (/)
        return "($(a[1]) / $(a[2]))"
    elseif op === (^)
        e = _try_const(Symbolics.unwrap(args[2]))
        e == 2 && return "($(a[1]) * $(a[1]))"
        e == -1 && return "(1.0 / $(a[1]))"
        return "pow($(a[1]), $(a[2]))"
    elseif op === ifelse
        return "(($(a[1])) ? $(a[2]) : $(a[3]))"
    elseif haskey(C_CMP, op)
        return "($(a[1]) $(C_CMP[op]) $(a[2]))"
    elseif op === (&)
        return "(" * join(a, " && ") * ")"
    elseif op === (|)
        return "(" * join(a, " || ") * ")"
    elseif op === (!)
        return "(!$(a[1]))"
    elseif op === atan
        return length(a) == 2 ? "atan2($(a[1]), $(a[2]))" : "atan($(a[1]))"
    elseif op === min
        return "bg_min($(a[1]), $(a[2]))"
    elseif op === max
        return "bg_max($(a[1]), $(a[2]))"
    elseif op === hypot
        return "hypot($(a[1]), $(a[2]))"
    elseif op === mod
        return "bg_mod($(a[1]), $(a[2]))"
    elseif op === rem
        return "fmod($(a[1]), $(a[2]))"
    elseif haskey(C_MATH1, op)
        return "$(C_MATH1[op])($(a[1]))"
    end
    error("no C lowering for operation `$op` in `$x` (spike: registered intrinsics such as " *
          "interp1 and the mechanics functions are not emitted yet)")
end

# The observed variables an expression needs, transitively, in observed order.
function needed_observed(exprs, obs_index::Dict{Any,Int}, obs_rhs::Vector{Any})
    need = falses(length(obs_rhs))
    stack = Any[]
    for e in exprs
        append!(stack, Symbolics.get_variables(e))
        u = Symbolics.unwrap(e)
        haskey(obs_index, u) && push!(stack, u)
    end
    while !isempty(stack)
        v = Symbolics.unwrap(pop!(stack))
        k = get(obs_index, v, 0)
        (k == 0 || need[k]) && continue
        need[k] = true
        append!(stack, Symbolics.get_variables(obs_rhs[k]))
    end
    return need
end

"""Emit one C function: the observed locals it needs, then `target = expr;` lines."""
function emit_function(io, signature, targets, env, obs; modes = nothing)
    exprs = Any[t[2] for t in targets]
    need = needed_observed(exprs, obs.index, obs.rhs)
    println(io, signature, " {")
    println(io, "    (void)m; (void)t; (void)x;")
    local_env = copy(env)
    for k in eachindex(obs.rhs)
        need[k] || continue
        cname = "o$(k - 1)"
        println(io, "    const double $cname = $(cexpr(obs.rhs[k], local_env, modes)); /* $(obs.names[k]) */")
        local_env[obs.lhs[k]] = cname
    end
    for (target, e, comment) in targets
        println(io, "    $target = $(cexpr(e, local_env, modes));", comment === nothing ? "" : " /* $comment */")
    end
    println(io, "}\n")
end

# ---------------------------------------------------------------------------------------
# Discrete partition (step_expression Expr) -> C statements
# ---------------------------------------------------------------------------------------

const DISC_CALLS = Dict{Symbol,String}(
    :__ifelse => "", :__truthy => "", :__not => "", :__round => "bg_round",
    :__sign => "bg_sign", :__clamp => "bg_clamp", :__deadzone => "bg_deadzone",
)

ctemp(s::Symbol) = "tmp" * replace(String(s), r"^_+" => "_")

function dval(ex, maps)
    if ex isa Bool
        return clit(ex)
    elseif ex isa Number
        return clit(ex)
    elseif ex isa Symbol
        ex === :t && return "t"
        return ctemp(ex)
    elseif ex isa Expr
        h = ex.head
        if h === :ref
            arr, i = ex.args
            if arr === :params
                return "m->p[$(maps.param[i])]"
            end
            obj, fld = arr.args[1], arr.args[2].value
            obj === :dstate && fld === :values && return "m->d[$(i - 1)]"
            obj === :dstate && fld === :prev && return "m->dprev[$(i - 1)]"
            obj === :inputs && fld === :values && return "m->din[$(i - 1)]"
            obj === :inputs && fld === :prev && return "m->dinprev[$(i - 1)]"
        elseif h === :. && ex.args[1] === :dstate && ex.args[2].value === :prev_t
            return "m->dprev_t"
        elseif h === :&&
            return "($(dval(ex.args[1], maps)) && $(dval(ex.args[2], maps)))"
        elseif h === :||
            return "($(dval(ex.args[1], maps)) || $(dval(ex.args[2], maps)))"
        elseif h === :call
            f = ex.args[1]
            a = String[dval(y, maps) for y in ex.args[2:end]]
            if f isa GlobalRef
                n = f.name
                n === :__truthy && return "($(a[1]) != 0.0)"
                n === :__not && return "($(a[1]) == 0.0)"
                n === :__ifelse && return "(($(a[1]) != 0.0) ? $(a[2]) : $(a[3]))"
                n === :__clamp && length(a) == 2 && return "bg_clamp($(a[1]), -($(a[2])), $(a[2]))"
                n === :__deadzone && length(a) == 2 && return "bg_deadzone($(a[1]), -($(a[2])), $(a[2]))"
                haskey(DISC_CALLS, n) && return "$(DISC_CALLS[n])(" * join(a, ", ") * ")"
                if f.mod === Base
                    n === :abs && return "fabs($(a[1]))"
                    n === :min && return "bg_min($(a[1]), $(a[2]))"
                    n === :max && return "bg_max($(a[1]), $(a[2]))"
                    n === :mod && return "bg_mod($(a[1]), $(a[2]))"
                    n === :rem && return "fmod($(a[1]), $(a[2]))"
                    n === :atan && length(a) == 2 && return "atan2($(a[1]), $(a[2]))"
                    return "$(n)(" * join(a, ", ") * ")"
                end
            elseif f isa Symbol
                f in (:+, :*) && return "(" * join(a, " $f ") * ")"
                f === :- && return length(a) == 1 ? "(-$(a[1]))" : "($(a[1]) - $(a[2]))"
                f === :/ && return "($(a[1]) / $(a[2]))"
                f === :^ && return "pow($(a[1]), $(a[2]))"
                f in (:(==), :(!=), :<, :<=, :>, :>=) && return "(($(a[1]) $f $(a[2])) ? 1.0 : 0.0)"
            end
        end
    end
    error("no C lowering for discrete expression `$ex`")
end

function dstmt(io, ex, maps, ind)
    pad = " "^ind
    if ex isa Expr && ex.head === :block
        for s in ex.args
            s isa LineNumberNode && continue
            dstmt(io, s, maps, ind)
        end
    elseif ex isa Expr && ex.head === :local
        return  # declared at the top of the function
    elseif ex isa Expr && ex.head === :return
        return
    elseif ex isa Expr && ex.head === :(=)
        println(io, pad, dval(ex.args[1], maps), " = ", dval(ex.args[2], maps), ";")
    elseif ex isa Expr && ex.head === :if
        println(io, pad, "if (", dval(ex.args[2 - 1], maps), ") {")
        dstmt(io, ex.args[2], maps, ind + 4)
        if length(ex.args) == 3 && !(ex.args[3] isa Expr && ex.args[3].head === :block && isempty(ex.args[3].args))
            println(io, pad, "} else {")
            dstmt(io, ex.args[3], maps, ind + 4)
        end
        println(io, pad, "}")
    else
        error("no C lowering for discrete statement `$ex`")
    end
end

# ---------------------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------------------

# ---------------------------------------------------------------------------------------
# Stiffness: the largest stable fixed step along the reference trajectory
# ---------------------------------------------------------------------------------------

using LinearAlgebra: eigvals

rk4_amp(z) = abs(1 + z + z^2 / 2 + z^3 / 6 + z^4 / 24)

# The largest h with |R(h λ)| <= 1 for every eigenvalue (bisection per eigenvalue; λ with
# Re λ >= 0 are physical growth or neutral modes and do not limit h here).
function rk4_hmax(lams)
    h = Inf
    for λ in lams
        real(λ) < -1e-12 || continue
        lo, hi = 0.0, 10.0 / abs(λ)
        for _ in 1:80
            mid = (lo + hi) / 2
            rk4_amp(mid * λ) <= 1 ? (lo = mid) : (hi = mid)
        end
        h = min(h, lo)
    end
    return h
end

function _read_reference(ref_dir)
    manifest = JSON3.read(read(joinpath(ref_dir, "manifest.json"), String))
    ids = String[String(s.id) for s in manifest.signals]
    raw = reinterpret(Float64, read(joinpath(ref_dir, "stream.f64")))
    ncol = 1 + length(ids)
    rows = [raw[(r - 1) * ncol + 1:r * ncol] for r in 1:(length(raw) ÷ ncol)]
    return ids, rows
end

function stiffness_report(jac, xs, ps, pnames, pvals, held_ids, dvals, x0, iv, ref_dir, dt)
    ids, rows = _read_reference(ref_dir)
    col = Dict(id => i + 1 for (i, id) in enumerate(ids))
    pdict = Dict(zip(pnames, pvals))
    ddict = Dict(zip(held_ids, dvals))
    picks = unique(round.(Int, range(1, length(rows); length = min(25, length(rows)))))
    worst = (hmax = Inf, t = 0.0, lam = ComplexF64[])
    for r in picks
        row = rows[r]
        sub = Dict{Any,Any}(iv => row[1])
        for (i, x) in enumerate(xs)
            n = String(getname(x))
            sub[x] = haskey(col, n) ? row[col[n]] : x0[i]
        end
        for p in ps
            n = String(getname(p))
            sub[p] = haskey(pdict, n) ? pdict[n] :
                     haskey(col, n) ? row[col[n]] : get(ddict, n, 0.0)
        end
        J = Float64[Float64(Symbolics.value(Symbolics.substitute(jac[i, j], sub)))
                    for i in axes(jac, 1), j in axes(jac, 2)]
        lam = eigvals(J)
        h = rk4_hmax(lam)
        h < worst.hmax && (worst = (hmax = h, t = row[1], lam = ComplexF64.(lam)))
    end
    margin = 0.5
    n1ms = ceil(Int, 1e-3 / (margin * worst.hmax))
    println("stiffness: max |λ| = $(maximum(abs, worst.lam)) 1/s at t = $(worst.t); ",
        "RK4 stable for h <= $(worst.hmax) s; with margin $(margin): $(n1ms) substeps per 1 ms; ",
        "chosen dt = $dt (", dt <= worst.hmax ? "stable for RK4" : "UNSTABLE for RK4", ")")
    return (max_abs_lambda = maximum(abs, worst.lam), at_t = worst.t,
        eigenvalues = [[real(l), imag(l)] for l in worst.lam],
        rk4_hmax = worst.hmax, margin = margin, rk4_substeps_per_ms = n1ms)
end

xml(s) = replace(String(s), "&" => "&amp;", "<" => "&lt;", ">" => "&gt;", "\"" => "&quot;")

function main(args)
    project_dir, model_name, out_dir = args[1], args[2], args[3]
    dt = length(args) >= 4 ? parse(Float64, args[4]) : 1.0e-4
    t_end = length(args) >= 5 ? parse(Float64, args[5]) : 1.0
    method = length(args) >= 6 ? uppercase(args[6]) : "ROS2"
    out_interval = length(args) >= 7 ? parse(Float64, args[7]) : 1.0e-3
    method in ("RK4", "ROS2") || error("method must be RK4 or ROS2")
    dt_ns = round(Int64, dt * 1e9)
    abs(dt_ns / 1e9 - dt) < 1e-15 || error("dt must be a whole number of nanoseconds")

    ident = replace(model_name, r"[^A-Za-z0-9_]" => "_")
    src = read(joinpath(project_dir, "models", model_name * ".bgmodel.json"), String)
    flat = Compile.flatten(BGSim.IR.parse_model(src); project_dir = project_dir)
    errs = [d for d in flat.diagnostics if d.severity == "error"]
    isempty(errs) || error("model has errors: $(errs)")

    lowered = BGSim.lower_model(flat; t_start = 0.0, t_end = t_end)
    sys = lowered.model.system
    lowered.model.algebraic &&
        error("spike: the compiled system keeps algebraic unknowns (mass-matrix DAE); not supported yet")

    # Run MTK's initialization once, so baked start values are consistent.
    integ = MTK.SciMLBase.init(lowered.problem, Tsit5())

    iv = Symbolics.unwrap(MTK.get_iv(sys))
    xs = [Symbolics.unwrap(x) for x in MTK.unknowns(sys)]
    nx = length(xs)
    x0 = Float64[getu(integ, x)(integ) for x in xs]

    # Discrete schedule: the same maps the Julia scheduler uses.
    has_disc = !isempty(flat.discrete)
    sched = has_disc ? BGSim.discrete_schedule(flat; t_start = 0.0, t_end = t_end) : nothing
    held_ids = has_disc ? sched.held_ids : String[]

    ps = [Symbolics.unwrap(p) for p in MTK.parameters(sys)]
    env = Dict{Any,String}(iv => "t")
    for (i, x) in enumerate(xs)
        env[x] = "x[$(i - 1)]"
    end
    pnames = String[]; pvals = Float64[]; ptunable = Bool[]
    dvals = zeros(length(held_ids))
    flat_params = Dict(p.id => p for p in flat.parameters)
    for p in ps
        name = String(getname(p))
        val = Float64(getp(integ, p)(integ))
        k = findfirst(==(name), held_ids)
        if k !== nothing
            env[p] = "m->d[$(k - 1)]"
            dvals[k] = val
        else
            get(get(flat_params, name, nothing) === nothing ? Dict() : flat_params[name].attrs, :kind, nothing) === :discrete &&
                error("discrete `$name` is not written by any partition")
            push!(pnames, name); push!(pvals, val)
            fp = get(flat_params, name, nothing)
            push!(ptunable, fp !== nothing && get(fp.attrs, :tunable, false) === true)
            env[p] = "m->p[$(length(pnames) - 1)]"
        end
    end
    np = length(pnames)

    obs_eqs = MTK.observed(sys)
    obs = (
        lhs = Any[Symbolics.unwrap(e.lhs) for e in obs_eqs],
        rhs = Any[Symbolics.unwrap(e.rhs) for e in obs_eqs],
        names = String[String(getname(e.lhs)) for e in obs_eqs],
        index = Dict{Any,Int}(),
    )
    for (k, l) in enumerate(obs.lhs)
        obs.index[l] = k
    end

    # Derivatives: `equations(sys)` keeps the observed variables, so the observed locals act
    # as common subexpressions.
    eqs = MTK.equations(sys)
    rhs = Vector{Any}(undef, nx)
    for e in eqs
        lhs = Symbolics.unwrap(e.lhs)
        SymbolicUtils.iscall(lhs) && SymbolicUtils.operation(lhs) isa Symbolics.Differential ||
            error("spike: non-differential equation `$e`")
        x = Symbolics.unwrap(SymbolicUtils.arguments(lhs)[1])
        rhs[findfirst(y -> isequal(y, x), xs)] = Symbolics.unwrap(e.rhs)
    end
    jac = MTK.calculate_jacobian(sys)

    # Outputs: every recorded signal that the compiled system can evaluate.
    known = Dict{String,Any}()
    for x in xs; known[String(getname(x))] = x; end
    for l in obs.lhs; known[String(getname(l))] = l; end
    for p in ps; known[String(getname(p))] = p; end
    outputs = Tuple{String,Any,Bool}[]
    skipped = String[]
    for s in flat.signals
        id = String(s.id)
        v = get(known, id, nothing)
        if v === nothing || id in pnames
            push!(skipped, id)
            continue
        end
        push!(outputs, (id, v, id in held_ids))
    end
    ny = length(outputs)

    parts = has_disc ? sched.partitions : []
    nd = length(held_ids)
    ni = has_disc ? length(sched.input_ids) : 0

    mkpath(joinpath(out_dir, "sources"))
    guid = "{" * bytes2hex(BGSim.sha256(string(lowered.key, dt, method)))[1:32] * "}"
    guid = string(guid[1:9], "-", guid[10:13], "-", guid[14:17], "-", guid[18:21], "-", guid[22:end])

    # ---------------- model.c (into a buffer: the header needs the mode count)
    modes = Any[]
    cbuf = IOBuffer()
    let io = cbuf
        println(io, "/* Generated by the bg-sim FMU export spike from model `$(model_name)`. Do not edit. */")
        println(io, "#include <math.h>\n#include \"model.h\"\n#include \"bg_runtime.h\"\n")
        arr(name, vals) = println(io, "const double $name[BG_SZ($(length(vals)))] = {",
            isempty(vals) ? "0.0" : join(clit.(vals), ", "), "};")
        arr("bg_x0", x0)
        arr("bg_p0", pvals)
        arr("bg_d0", dvals)
        println(io, "const unsigned char bg_p_tunable[BG_SZ($np)] = {",
            np == 0 ? "0" : join(Int.(ptunable), ", "), "};")
        println(io, "\n/* states: ", join(["x[$(i-1)] = $(getname(x))" for (i, x) in enumerate(xs)], ", "), " */")
        println(io, "/* parameters: ", join(["p[$(i-1)] = $n" for (i, n) in enumerate(pnames)], ", "), " */")
        println(io, "/* held: ", join(["d[$(i-1)] = $n" for (i, n) in enumerate(held_ids)], ", "), " */\n")

        emit_function(io,
            "void bg_derivatives(const bg_model *m, double t, const double *x, double *dx)",
            [("dx[$(i - 1)]", rhs[i], "d/dt " * String(getname(xs[i]))) for i in 1:nx], env, obs; modes = modes)
        jt = Tuple{String,Any,Any}[]
        for i in 1:nx, j in 1:nx
            push!(jt, ("J[$((i - 1) * nx + (j - 1))]", Symbolics.unwrap(jac[i, j]), nothing))
        end
        emit_function(io,
            "void bg_jacobian(const bg_model *m, double t, const double *x, double *J)",
            jt, env, obs; modes = modes)
        # The frozen switching conditions: evaluated live, once per step, at its start.
        emit_function(io,
            "void bg_modes(const bg_model *m, double t, const double *x, double *c)",
            [("c[$(k - 1)]", modes[k], string(modes[k])) for k in eachindex(modes)], env, obs)
        emit_function(io,
            "void bg_outputs(const bg_model *m, double t, const double *x, double *y)",
            [("y[$(k - 1)]", o[2], o[1]) for (k, o) in enumerate(outputs)], env, obs)
        sample_targets = Tuple{String,Any,Any}[]
        if has_disc
            for (j, id) in enumerate(sched.input_ids)
                v = get(known, id, nothing)
                v === nothing && error("discrete input `$id` is not in the compiled system")
                push!(sample_targets, ("din[$(j - 1)]", v, id))
            end
        end
        emit_function(io,
            "void bg_sample(const bg_model *m, double t, const double *x, double *din)",
            sample_targets, env, obs)

        # Discrete partitions.
        pmap = Dict{Int,Int}()
        if has_disc
            for (k, id) in enumerate(sched.param_ids)
                i = findfirst(==(id), pnames)
                i === nothing && error("discrete parameter `$id` is not a runtime parameter")
                pmap[k] = i - 1
            end
        end
        maps = (param = pmap,)
        for (k, sp) in enumerate(parts)
            p = sp.partition
            ex = Compile.step_expression(p, sched.held_index, sched.input_index,
                sched.param_index, BGSim.DiscreteRuntime)
            println(io, "/* $(p.label): Ts = $(p.period_ns) ns, offset = $(p.offset_ns) ns */")
            println(io, "static void bg_part_$(k - 1)(bg_model *m, double t) {")
            println(io, "    (void)t;")
            for s in p.temp_slots
                println(io, "    double $(ctemp(s)) = 0.0;")
            end
            dstmt(io, ex.args[2], maps, 4)
            println(io, "}\n")
            p.period_ns % dt_ns == 0 && p.offset_ns % dt_ns == 0 ||
                error("E104: partition $(p.label) period/offset is not a multiple of dt")
        end
        if isempty(parts)
            println(io, "const bg_partition bg_partitions[1] = {{0, 0, 0}};")
        else
            println(io, "const bg_partition bg_partitions[$(length(parts))] = {")
            for (k, sp) in enumerate(parts)
                println(io, "    {INT64_C($(sp.partition.period_ns)), INT64_C($(sp.partition.offset_ns)), bg_part_$(k - 1)},")
            end
            println(io, "};")
        end
    end

    # ---------------- model.h
    open(joinpath(out_dir, "sources", "model.h"), "w") do io
        print(io, """
        /* Generated by the bg-sim FMU export spike from model `$(model_name)`. Do not edit. */
        #ifndef BG_MODEL_H
        #define BG_MODEL_H

        #include <stdint.h>

        #define BG_MODEL_IDENTIFIER "$(ident)"
        #define BG_GUID "$(guid)"
        #define BG_NX $(nx)
        #define BG_NP $(np)
        #define BG_ND $(nd)
        #define BG_NI $(ni)
        #define BG_NY $(ny)
        #define BG_NPART $(length(parts))
        #define BG_NC $(length(modes))      /* frozen switching conditions */
        #define BG_DT $(repr(dt))
        #define BG_DT_NS INT64_C($(dt_ns))
        #define BG_METHOD_RK4 1
        #define BG_METHOD_ROS2 2
        #define BG_METHOD BG_METHOD_$(method)

        /* Value references: outputs [0, BG_NY), then parameters [BG_VR_P0, BG_VR_P0 + BG_NP). */
        #define BG_VR_P0 $(ny)

        /* Arrays are never zero-length (C99), so every size is at least 1. */
        #define BG_SZ(n) ((n) > 0 ? (n) : 1)

        /* One model instance. Everything the hot path touches lives here; its size is fixed at
           generation time, so a step never allocates. */
        typedef struct {
            double t;                      /* current time */
            double t_start;
            int64_t n;                     /* steps taken since t_start */
            int64_t t_start_ns;
            double x[BG_SZ(BG_NX)];        /* continuous states */
            double p[BG_SZ(BG_NP)];        /* parameters */
            double d[BG_SZ(BG_ND)];        /* held discrete values */
            double dprev[BG_SZ(BG_ND)];    /* held values before this tick (previous(x)) */
            double din[BG_SZ(BG_NI)];      /* continuous values sampled by discrete code */
            double dinprev[BG_SZ(BG_NI)];
            double dprev_t;
            double c[BG_SZ(BG_NC)];        /* switching conditions, frozen during a step */
            double y[BG_SZ(BG_NY)];        /* outputs, valid when y_valid */
            int y_valid;
            /* solver workspace */
            double k1[BG_SZ(BG_NX)], k2[BG_SZ(BG_NX)], k3[BG_SZ(BG_NX)], k4[BG_SZ(BG_NX)];
            double xs[BG_SZ(BG_NX)];
            double w[BG_SZ(BG_NX * BG_NX)];
            int piv[BG_SZ(BG_NX)];
        } bg_model;

        typedef struct {
            int64_t period_ns;
            int64_t offset_ns;
            void (*run)(bg_model *m, double t);
        } bg_partition;

        extern const double bg_x0[BG_SZ(BG_NX)];
        extern const double bg_p0[BG_SZ(BG_NP)];
        extern const double bg_d0[BG_SZ(BG_ND)];
        extern const unsigned char bg_p_tunable[BG_SZ(BG_NP)];
        extern const bg_partition bg_partitions[BG_SZ(BG_NPART)];

        void bg_derivatives(const bg_model *m, double t, const double *x, double *dx);
        void bg_jacobian(const bg_model *m, double t, const double *x, double *J); /* row-major */
        void bg_outputs(const bg_model *m, double t, const double *x, double *y);
        void bg_sample(const bg_model *m, double t, const double *x, double *din);
        void bg_modes(const bg_model *m, double t, const double *x, double *c);

        /* bg_solver.c */
        void bg_reset(bg_model *m, double t_start);
        int bg_step(bg_model *m); /* advance one BG_DT; 0 ok, nonzero error */
        void bg_update_outputs(bg_model *m);

        #endif
        """)
    end

    write(joinpath(out_dir, "sources", "model.c"), take!(cbuf))

    # ---------------- modelDescription.xml
    open(joinpath(out_dir, "modelDescription.xml"), "w") do io
        println(io, """<?xml version="1.0" encoding="UTF-8"?>
        <fmiModelDescription fmiVersion="2.0" modelName="$(xml(model_name))" guid="$(guid)"
          generationTool="bg-sim FMU export spike" variableNamingConvention="flat"
          numberOfEventIndicators="0">
          <CoSimulation modelIdentifier="$(ident)" canHandleVariableCommunicationStepSize="true"
            canInterpolateInputs="false" canBeInstantiatedOnlyOncePerProcess="false"
            canNotUseMemoryManagementFunctions="false" canGetAndSetFMUstate="false"
            canSerializeFMUstate="false" providesDirectionalDerivative="false">
            <SourceFiles>
              <File name="model.c"/><File name="bg_solver.c"/><File name="fmi2_cs.c"/>
            </SourceFiles>
          </CoSimulation>
          <DefaultExperiment startTime="0" stopTime="$(t_end)" stepSize="$(out_interval)"/>
          <ModelVariables>""")
        for (k, (id, _, isheld)) in enumerate(outputs)
            var = isheld ? "discrete" : "continuous"
            println(io, """    <ScalarVariable name="$(xml(id))" valueReference="$(k - 1)" causality="output" variability="$var"><Real/></ScalarVariable>""")
        end
        for (i, n) in enumerate(pnames)
            var = ptunable[i] ? "tunable" : "fixed"
            println(io, """    <ScalarVariable name="$(xml(n))" valueReference="$(ny + i - 1)" causality="parameter" variability="$var" initial="exact"><Real start="$(repr(pvals[i]))"/></ScalarVariable>""")
        end
        println(io, "  </ModelVariables>\n  <ModelStructure>\n    <Outputs>")
        for k in 1:ny
            println(io, """      <Unknown index="$k"/>""")
        end
        println(io, "    </Outputs>\n    <InitialUnknowns>")
        for k in 1:ny
            println(io, """      <Unknown index="$k"/>""")
        end
        println(io, "    </InitialUnknowns>\n  </ModelStructure>\n</fmiModelDescription>")
    end

    # ---------------- reference run
    ref_dir = joinpath(out_dir, "reference")
    isdir(ref_dir) && rm(ref_dir; recursive = true)
    BGSim.simulate(flat; run_dir = ref_dir, settings = Dict(
        "t_end" => t_end, "solver" => "Tsit5", "reltol" => 1e-10, "abstol" => 1e-12,
        "output" => Dict("mode" => "interval", "interval" => out_interval)))

    stiff = stiffness_report(jac, xs, ps, pnames, pvals, held_ids, dvals, x0, iv, ref_dir, dt)

    open(joinpath(out_dir, "meta.json"), "w") do io
        JSON3.write(io, (
            model = model_name, identifier = ident, guid = guid, dt = dt, t_end = t_end,
            method = method, out_interval = out_interval, nx = nx, np = np, nd = nd,
            outputs = [o[1] for o in outputs], parameters = pnames, tunable = ptunable,
            skipped = skipped, stiffness = stiff,
        ))
    end
    println("generated $(ident): nx=$nx np=$np nd=$nd ni=$ni ny=$ny partitions=$(length(parts)) ",
        "observed=$(length(obs.lhs)) modes=$(length(modes)) method=$method dt=$dt; skipped $(length(skipped)) signals")
end

main(ARGS)
