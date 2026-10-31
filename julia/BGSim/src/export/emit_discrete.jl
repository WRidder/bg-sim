# Discrete partitions -> C (plan/EXPORT_PLAN.md D-EX2).
#
# The input is exactly what the Julia scheduler compiles: `Compile.step_expression`, an
# anonymous-function `Expr` whose leaves are `dstate.values[i]`, `dstate.prev[i]`,
# `inputs.values[j]`, `inputs.prev[j]`, `params[k]`, `t`, `dstate.prev_t`, temporaries and
# literals, and whose helpers are `GlobalRef`s into `DiscreteRuntime`. Translating that
# expression (instead of re-walking the partition) keeps the operation order identical, which
# is what makes the discrete goldens bit-exact in C.
#
# Comparisons yield 1.0/0.0 and conditions test `!= 0.0`, as `__truthy` does in Julia.

ctemp(s::Symbol) = "tmp" * replace(String(s), r"^_+" => "_")

const _DISC_HELPERS = Dict{Symbol,String}(
    :__round => "bg_round", :__sign => "bg_sign", :__clamp => "bg_clamp",
    :__deadzone => "bg_deadzone",
)

"""    dval(ex, param) -> String

The C value of one step-expression node; `param[k]` is the C spelling of `params[k]` (a
parameter field, an input slot or a folded literal)."""
function dval(ex, param::Dict{Int,String})
    ex isa Bool && return clit(ex)
    ex isa Number && return clit(ex)
    if ex isa Symbol
        ex === :t && return "t"
        return ctemp(ex)
    end
    ex isa Expr || throw(ExportError("discrete code: unsupported node `$ex`"))
    h = ex.head
    if h === :ref
        arr, i = ex.args
        arr === :params && return param[i]
        if arr isa Expr && arr.head === :.
            obj, fld = arr.args[1], arr.args[2].value
            obj === :dstate && fld === :values && return "m->d[$(i - 1)]"
            obj === :dstate && fld === :prev && return "m->dprev[$(i - 1)]"
            obj === :inputs && fld === :values && return "m->din[$(i - 1)]"
            obj === :inputs && fld === :prev && return "m->dinprev[$(i - 1)]"
        end
    elseif h === :. && ex.args[1] === :dstate && ex.args[2].value === :prev_t
        return "m->dprev_t"
    elseif h === :&&
        return "((($(dval(ex.args[1], param))) != 0.0 && ($(dval(ex.args[2], param))) != 0.0) ? 1.0 : 0.0)"
    elseif h === :||
        return "((($(dval(ex.args[1], param))) != 0.0 || ($(dval(ex.args[2], param))) != 0.0) ? 1.0 : 0.0)"
    elseif h === :call
        f = ex.args[1]
        if f isa GlobalRef && f.name === :bg_delay_ring!
            # J-EX9: (ring, ring_pos, id, off, k, x); ring `id` (1-based) at slot `off`.
            _, _, id, off, k, x = ex.args[2:end]
            return "bg_delay_ring(m->ring + $(off), &m->ring_pos[$(id - 1)], $(k), $(dval(x, param)))"
        end
        if f isa GlobalRef && f.name === :bg_delay_ring_at!
            # `delay(x, Tmax, tau)`: (ring, ring_pos, id, off, k, x, tau / Ts).
            _, _, id, off, k, x, d = ex.args[2:end]
            return "bg_delay_ring_at(m->ring + $(off), &m->ring_pos[$(id - 1)], $(k), $(dval(x, param)), $(dval(d, param)))"
        end
        a = String[dval(y, param) for y in ex.args[2:end]]
        if f isa GlobalRef
            n = f.name
            n === :__truthy && return "(($(a[1]) != 0.0) ? 1.0 : 0.0)"
            n === :__not && return "(($(a[1]) == 0.0) ? 1.0 : 0.0)"
            n === :__ifelse && return "(($(a[1]) != 0.0) ? $(a[2]) : $(a[3]))"
            n === :__clamp && length(a) == 2 && return "bg_clamp($(a[1]), -($(a[2])), $(a[2]))"
            n === :__deadzone && length(a) == 2 && return "bg_deadzone($(a[1]), -($(a[2])), $(a[2]))"
            haskey(_DISC_HELPERS, n) && return "$(_DISC_HELPERS[n])(" * join(a, ", ") * ")"
            # J-EX9: the counter-based draws, bit-identical twins in bg_intrinsics.c.
            f.mod === BGSim && n in (:bg_noise_normal, :bg_noise_uniform) &&
                return "$(n)(" * join(a, ", ") * ")"
            if f.mod === Base
                n === :abs && return "fabs($(a[1]))"
                n === :min && return "bg_min($(a[1]), $(a[2]))"
                n === :max && return "bg_max($(a[1]), $(a[2]))"
                n === :mod && return "bg_mod($(a[1]), $(a[2]))"
                n === :rem && return "fmod($(a[1]), $(a[2]))"
                n === :atan && length(a) == 2 && return "atan2($(a[1]), $(a[2]))"
                n in (:sin, :cos, :tan, :asin, :acos, :atan, :sinh, :cosh, :tanh, :exp,
                    :log, :log10, :sqrt, :floor, :ceil, :hypot) &&
                    return "$(n)(" * join(a, ", ") * ")"
            end
            throw(ExportError("discrete code: `$(f.name)` has no C implementation yet"))
        elseif f isa Symbol
            # Folded parameters reach this code as literals; with `simplify` the exact
            # peephole drops `1.0` factors and turns `(-1.0)` into a negation (D-EX10).
            f === :* && C_SIMPLIFY[] && return _c_product(a; exact = true)
            f in (:+, :*) && return "(" * join(a, " $f ") * ")"
            f === :- && return length(a) == 1 ? "(-$(a[1]))" : "($(a[1]) - $(a[2]))"
            f === :/ && return "($(a[1]) / $(a[2]))"
            f === :^ && return "pow($(a[1]), $(a[2]))"
            f in (:(==), :(!=), :<, :<=, :>, :>=) && return "(($(a[1]) $f $(a[2])) ? 1.0 : 0.0)"
        end
    end
    throw(ExportError("discrete code: unsupported expression `$ex`"))
end

function dstmt(io, ex, param::Dict{Int,String}, ind::Int)
    pad = " "^ind
    if ex isa LineNumberNode
        return
    elseif ex isa Expr && ex.head === :block
        for s in ex.args
            dstmt(io, s, param, ind)
        end
    elseif ex isa Expr && ex.head in (:local, :return)
        return  # temporaries are declared at the top of the function
    elseif ex isa Expr && ex.head === :(=)
        println(io, pad, dval(ex.args[1], param), " = ", dval(ex.args[2], param), ";")
    elseif ex isa Expr && ex.head === :if
        println(io, pad, "if (", dval(ex.args[1], param), " != 0.0) {")
        dstmt(io, ex.args[2], param, ind + 4)
        if length(ex.args) == 3 && !(ex.args[3] isa Expr && ex.args[3].head === :block && isempty(ex.args[3].args))
            println(io, pad, "} else {")
            dstmt(io, ex.args[3], param, ind + 4)
        end
        println(io, pad, "}")
    else
        throw(ExportError("discrete code: unsupported statement `$ex`"))
    end
end

"""    emit_partition(io, k, partition, sched, param)

One `static void bg_part_<k>(bg_model *m, double t)` from the scheduler's step expression."""
function emit_partition(io, k::Int, p, sched, param::Dict{Int,String})
    ex = Compile.step_expression(p, sched.held_index, sched.input_index, sched.param_index,
        BGSim.DiscreteRuntime)
    println(io, "/* $(ccomment(p.label)): Ts = $(p.period_ns) ns, offset = $(p.offset_ns) ns */")
    println(io, "static void bg_part_$(k)(bg_model *m, double t) {")
    println(io, "    (void)t;")
    # A temporary may be written and never read (a dead component of a vector expression);
    # the (void) keeps -Werror=unused-but-set-variable quiet.
    for s in p.temp_slots
        println(io, "    double $(ctemp(s)) = 0.0; (void)$(ctemp(s));")
    end
    dstmt(io, ex.args[2], param, 4)
    # A temporary the block writes but never reads (one component of a vector local) is
    # legal, but -Werror=unused-but-set-variable would reject it.
    for s in p.temp_slots
        println(io, "    (void)$(ctemp(s));")
    end
    println(io, "}\n")
end
