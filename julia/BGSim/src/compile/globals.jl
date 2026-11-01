# Global (model-level) parameters (spec "Global parameters", plan/GLOBAL_PARAMETERS.md).
#
# A model may declare named parameters at the top level (`model.parameters[]`). Each one has a
# constant expression over literals, other globals and the whitelisted pure functions. They are
# *statically* evaluated here, once per compile, before any instance is created:
#
#   1. names: an identifier, unique, not a reserved word or built-in function (E003);
#   2. syntax: every value is parsed by the block front end, wrapped in a throwaway `@block`
#      exactly like an instance value (`_parse_value`), so the tokenizer and whitelist match;
#   3. references: a name that is not a global is E003; the dependency graph is sorted
#      topologically and every cycle is E113 with the cycle path (`a -> b -> a`);
#   4. folding: in topological order, with the constant folder (never `eval`); the result must
#      be a finite number (E004 for a non-number, E113 for Inf/NaN or a domain error).
#
# A global that fails makes every global that uses it fail too (E113 "uses `x`, which has an
# error"), and an instance expression that uses a failed global is E113 on that instance.
#
# The folded numbers are what every instance-level expression (params, starts, string
# constants, at every diagram level, including inside subsystems) sees, so the flat model,
# the simulation and the C/FMU export only ever contain numbers: globals are not runtime
# tunables. A start-time change (dashboard input) goes through `IR.override_globals` *before*
# this pass, so dependents are re-folded.

"""    GlobalEnv

The result of [`evaluate_globals`](@ref): `values` maps every global that folded to its number
(`Int` or `Float64`), `failed` holds the declared globals that could not be evaluated, `order`
is the evaluation (topological) order, `deps` the globals each global's expression uses and
`exprs` the parsed expression (front-end AST over global names) of every global that folded,
which the C/FMU export needs to recompute a global exposed as an FMU parameter
(plan/GLOBAL_PARAMETERS.md)."""
struct GlobalEnv
    values::Dict{Symbol,Any}
    failed::Set{Symbol}
    order::Vector{Symbol}
    deps::Dict{Symbol,Vector{Symbol}}
    exprs::Dict{Symbol,Any}
end

GlobalEnv() = GlobalEnv(Dict{Symbol,Any}(), Set{Symbol}(), Symbol[], Dict{Symbol,Vector{Symbol}}(),
    Dict{Symbol,Any}())

"""Names a global parameter may not take: the predefined `t`/`Ts`, `ifelse`, the literals,
the built-in constants (`BGSim.BUILTIN_CONSTANTS`: an expression may use them), and the Julia keywords the front end would parse
as syntax. Whitelisted function names are refused separately (`function_rule`)."""
const RESERVED_GLOBAL_NAMES = Set{Symbol}([
    keys(BGSim.BUILTIN_CONSTANTS)...,
    :t, :Ts, :ifelse, Symbol("true"), Symbol("false"), :begin, :end, :if, :else,
    :elseif, :for, :while,
    :function, :return, :let, :local, :global, :const, :struct, :module, :using, :import,
    :do, :try, :catch, :finally, :quote, :macro, :abstract, :primitive, :mutable,
    :baremodule, :export, :in, :isa, :where, :break, :continue, :type,
])

const GLOBAL_NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"

# An identifier that is not part of a number (`1e-3`), a field (`a.b`) or another word.
const _IDENT_IN_TEXT = r"(?<![A-Za-z0-9_.])[A-Za-z_][A-Za-z0-9_]*"

_global_scope(name) = "global:" * String(name)

function _global_diag(code, name, message; hint = nothing)
    return diag(code, message; hint = hint, scope = _global_scope(name))
end

# Every `Name` an expression reads, excluding called function names.
function _expr_names!(out::Vector{Symbol}, e)
    if e isa Name
        e.name in out || push!(out, e.name)
    elseif e isa BinOp || e isa Comparison
        _expr_names!(out, e.lhs)
        _expr_names!(out, e.rhs)
    elseif e isa UnOp
        _expr_names!(out, e.operand)
    elseif e isa Call
        foreach(a -> _expr_names!(out, a), e.args)
    elseif e isa Index
        _expr_names!(out, e.base)
        foreach(a -> _expr_names!(out, a), e.indices)
    elseif e isa VectorLit
        foreach(a -> _expr_names!(out, a), e.elements)
    elseif e isa MatrixLit
        foreach(row -> foreach(a -> _expr_names!(out, a), row), e.rows)
    elseif e isa IfElse
        _expr_names!(out, e.cond)
        _expr_names!(out, e.then)
        _expr_names!(out, e.otherwise)
    elseif e isa BoolOp
        foreach(a -> _expr_names!(out, a), e.operands)
    elseif e isa Field
        _expr_names!(out, e.base)
    end
    return out
end

"""    global_names_in(text) -> Vector{Symbol}

The identifiers an expression string mentions, in order of first appearance; a cheap superset
of the names it reads (it also lists called function names), used to decide which globals an
instance expression needs."""
function global_names_in(text::AbstractString)
    out = Symbol[]
    for m in eachmatch(_IDENT_IN_TEXT, text)
        s = Symbol(m.match)
        s in out || push!(out, s)
    end
    return out
end

# The `@constants` lines that declare the given globals inside a value-wrapper block.
function _global_decl_lines(names, values::AbstractDict{Symbol,Any})
    io = IOBuffer()
    for name in names
        v = values[name]
        tname = v isa Integer ? "Int" : "Real"
        print(io, "    @constants ", name, "::", tname, " = ", repr(v), "\n")
    end
    return String(take!(io))
end

# Parse one global's expression; returns the default `Expr` or a diagnostic.
function _parse_global(g::IR.GlobalParam)
    src = "@block __GlobalValue begin\n    @parameters __value::Real = " * g.value * "\nend\n"
    pb = try
        parse_block(src; filename = "__global_value", ref = "inline:__global_value")
    catch err
        return _global_diag("E001", g.name,
            "invalid value of global parameter `$(g.name)`: " * sprint(showerror, err);
            hint = "write a constant expression such as `2.0`, `4*m` or `sqrt(k/m)`")
    end
    ds = declarations(pb, :parameters)
    if isempty(ds) || ds[1].default === nothing || isempty(strip(g.value))
        message = "invalid value of global parameter `$(g.name)`: the expression cannot be parsed"
        for d in block_diagnostics(pb)
            d.severity == "error" || continue
            message = "invalid value of global parameter `$(g.name)`: " * d.message
            break
        end
        return _global_diag("E001", g.name, message;
            hint = "write a constant expression such as `2.0`, `4*m` or `sqrt(k/m)`")
    end
    return ds[1].default
end

# Find one cycle through `start` in the dependency graph restricted to `nodes`.
function _find_cycle(deps::Dict{Symbol,Vector{Symbol}}, start::Symbol, nodes::Set{Symbol})
    path = Symbol[start]
    onpath = Set{Symbol}([start])
    visited = Set{Symbol}()
    function walk(n)
        for m in get(deps, n, Symbol[])
            m in nodes || continue
            m == start && return true
            (m in onpath || m in visited) && continue
            push!(path, m)
            push!(onpath, m)
            walk(m) && return true
            pop!(path)
            delete!(onpath, m)
            push!(visited, m)
        end
        return false
    end
    walk(start) || return nothing
    return path
end

"""    evaluate_globals(md::IR.ModelDoc) -> (GlobalEnv, Vector{Diagnostic})

Statically evaluate the model's global parameters (see the file header for the rules). Total
for user errors: every problem is a diagnostic with `scope = "global:<name>"` and no path
(a global is model-wide), and the globals that did fold are still returned."""
function evaluate_globals(md::IR.ModelDoc)
    diags = Diagnostic[]
    env = GlobalEnv()
    isempty(md.globals) && return env, diags

    declared = Dict{Symbol,IR.GlobalParam}()
    exprs = Dict{Symbol,Any}()
    for g in md.globals
        if !occursin(GLOBAL_NAME_PATTERN, g.name)
            push!(diags, _global_diag("E003", g.name,
                "global parameter name `$(g.name)` is not an identifier";
                hint = "start with a letter or underscore and use letters, digits and underscores"))
            continue
        end
        name = Symbol(g.name)
        if haskey(declared, name)
            push!(diags, _global_diag("E003", g.name,
                "global parameter `$(g.name)` is declared twice";
                hint = "a global parameter name must be unique in the model"))
            continue
        end
        declared[name] = g
        if name in RESERVED_GLOBAL_NAMES
            push!(diags, _global_diag("E003", g.name,
                "`$(g.name)` is reserved and cannot name a global parameter";
                hint = "choose another name"))
            push!(env.failed, name)
            continue
        elseif BGSim.function_rule(name) !== nothing
            push!(diags, _global_diag("E003", g.name,
                "global parameter `$(g.name)` shadows built-in function `$(g.name)`";
                hint = "rename the global parameter; built-in functions cannot be shadowed"))
            push!(env.failed, name)
            continue
        end
        parsed = _parse_global(g)
        if parsed isa Diagnostic
            push!(diags, parsed)
            push!(env.failed, name)
            continue
        end
        exprs[name] = parsed
    end

    # References: every name an expression reads must be a declared global.
    for g in md.globals
        name = Symbol(g.name)
        haskey(exprs, name) || continue
        names = _expr_names!(Symbol[], exprs[name])
        unknown = [n for n in names if !haskey(declared, n)]
        env.deps[name] = [n for n in names if haskey(declared, n)]
        if !isempty(unknown)
            list = join(("`$n`" for n in unknown), ", ")
            push!(diags, _global_diag("E003", g.name,
                "global parameter `$(g.name)` uses $(list), which " *
                (length(unknown) == 1 ? "is" : "are") * " not a global parameter";
                hint = "declare it in the model's global parameters, or fix the spelling"))
            push!(env.failed, name)
        end
    end

    # Cycles: Kahn's algorithm over the parsed globals; whatever is left sits on or behind a
    # cycle. Each cycle is reported once, with its path, on its first member in document order.
    pending = Set(k for k in keys(exprs))
    order = Symbol[]
    indeg = Dict(k => count(d -> d in pending, unique(env.deps[k])) for k in pending)
    users = Dict{Symbol,Vector{Symbol}}()
    for k in pending, d in unique(env.deps[k])
        d in pending && push!(get!(users, d, Symbol[]), k)
    end
    queue = [Symbol(g.name) for g in md.globals if Symbol(g.name) in pending &&
                                                    indeg[Symbol(g.name)] == 0]
    while !isempty(queue)
        n = popfirst!(queue)
        push!(order, n)
        delete!(pending, n)
        for u in get(users, n, Symbol[])
            indeg[u] -= 1
            indeg[u] == 0 && push!(queue, u)
        end
    end
    reported = Set{Symbol}()
    for g in md.globals
        name = Symbol(g.name)
        (name in pending && !(name in reported)) || continue
        cycle = _find_cycle(env.deps, name, pending)
        cycle === nothing && continue          # only behind a cycle: handled below
        any(c -> c in reported, cycle) && continue
        foreach(c -> push!(reported, c), cycle)
        foreach(c -> push!(env.failed, c), cycle)
        chain = join(vcat(String.(cycle), String(name)), " -> ")
        push!(diags, _global_diag("E113", g.name,
            "global parameters form a cycle: $chain";
            hint = "a global parameter may only use globals that do not depend on it"))
    end
    # Globals behind a cycle come after it in the order; they fail as dependents below.
    for g in md.globals
        name = Symbol(g.name)
        name in pending && !(name in order) && push!(order, name)
    end
    append!(env.order, order)

    # Fold in order.
    for name in order
        name in env.failed && continue
        g = declared[name]
        broken = [d for d in env.deps[name] if !haskey(env.values, d)]
        if !isempty(broken)
            push!(env.failed, name)
            push!(diags, _global_diag("E113", g.name,
                "global parameter `$(g.name)` uses `$(first(broken))`, which cannot be evaluated";
                hint = "fix `$(first(broken))` first"))
            continue
        end
        deps = unique(env.deps[name])
        src = "@block __GlobalValue begin\n" * _global_decl_lines(deps, env.values) *
              "    @parameters __value::Real = " * g.value * "\nend\n"
        pb = parse_block(src; filename = "__global_value", ref = "inline:__global_value")
        bad = false
        for d in check_block(pb)
            d.code == "W204" && continue
            d.severity == "error" || continue
            bad = true
            push!(diags, _global_diag(d.code == "E000" ? "E001" : d.code, g.name,
                "invalid value of global parameter `$(g.name)`: " * d.message; hint = d.hint))
        end
        if bad
            push!(env.failed, name)
            continue
        end
        local_env = Dict{Symbol,Any}(d => env.values[d] for d in deps)
        value = nothing
        message = nothing
        ast = declarations(pb, :parameters)[end].default
        try
            value = eval_const(ast, local_env)
        catch err
            message = err isa ConstFoldError ? err.message : sprint(showerror, err)
        end
        if message !== nothing
            push!(env.failed, name)
            push!(diags, _global_diag("E113", g.name,
                "global parameter `$(g.name)` cannot be evaluated: $message"))
        elseif !(value isa Real) || value isa Bool
            push!(env.failed, name)
            push!(diags, _global_diag("E004", g.name,
                "global parameter `$(g.name)` must be a number, got `$(repr(value))`";
                hint = "a global parameter is a scalar number"))
        elseif !isfinite(value)
            push!(env.failed, name)
            push!(diags, _global_diag("E113", g.name,
                "global parameter `$(g.name)` evaluates to $(value), which is not finite";
                hint = "check for a division by zero or an overflow"))
        else
            env.values[name] = value isa Integer ? Int(value) : Float64(value)
            env.exprs[name] = ast
        end
    end
    return env, diags
end

"""    evaluate_globals_values(md) -> Dict{String,Any}

The folded value of every global that evaluates, keyed by name: the numbers the editor shows
and a dashboard can display next to an override."""
evaluate_globals_values(md::IR.ModelDoc) =
    Dict{String,Any}(String(k) => v for (k, v) in first(evaluate_globals(md)).values)
