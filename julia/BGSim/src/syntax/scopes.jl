# Block-level checks (plan 4.4): E000 to E006, W204 and the E103 balance precheck.
#
# `check_block(pb)` is the fast pass that runs as the user types. It is total: it never
# throws on bad input, it returns a (possibly empty) `Vector{Diagnostic}`. Parse-stage
# diagnostics already collected in `pb` are included first, so a caller needs only
# `check_block(parse_block(text))`.
#
# Checks, in order:
#   1. declaration names (duplicates, `t`, shadowing a whitelisted function) — E003
#   2. declaration types (Bool state, Int outside discrete, array sizes) — E004/E005
#   3. defaults (constant expressions, type) — E004
#   4. equations (names, types, indices, `for` bounds, `if` branch counts) — E001..E005
#   5. `@causality` port names — E003
#   6. units, via `BGSim.Units.check_units` when J1.2 has landed — E006
#   7. unused declarations — W204
#   8. balance: #equations == #variables + #outputs + #powerports — E103 (a warning here)

# ---------------------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------------------

"""    assignable(target, value) -> Bool

Whether a value of type `value` may be used where `target` is declared. `Int` widens to
`Real`; nothing else converts implicitly (spec: "Real to Int never happens implicitly")."""
function assignable(target::TypeSpec, value::TypeSpec)
    target.kind == value.kind && target.args == value.args && return true
    target.kind == :Real && value.kind == :Int && return true
    return false
end

_numeric(t::TypeSpec) = t.kind == :Real || t.kind == :Int
_scalar_numeric(t::TypeSpec) = t.kind == :Real || t.kind == :Int

# ---------------------------------------------------------------------------------------
# The checker
# ---------------------------------------------------------------------------------------

mutable struct Checker
    pb::ParsedBlock
    decls::Dict{Symbol,Decl}
    consts::Dict{Symbol,Any}
    diags::Vector{Diagnostic}
    scope::Symbol          # source scope of the construct being checked
    context::Symbol        # :equation | :default | :discrete | :events
    allow_cond::Bool
    used::Set{Symbol}
    loopvars::Dict{Symbol,TypeSpec}
    loop_ranges::Dict{Symbol,Tuple{Int,Int}}
    locals::Dict{Symbol,TypeSpec}   # D18 temporaries of the current discrete/event body
    stdlib::Bool
    failed::Bool           # an error was reported; suppress cascading E103
end

function Checker(pb::ParsedBlock)
    decls = Dict{Symbol,Decl}()
    for scope in DECLARATION_SCOPES
        for d in get(pb.declaration_map, scope, Decl[])
            haskey(decls, d.name) || (decls[d.name] = d)
        end
    end
    return Checker(
        pb,
        decls,
        constant_env(pb),
        copy(pb.diagnostics),
        :equations,
        :equation,
        false,
        Set{Symbol}(),
        Dict{Symbol,TypeSpec}(),
        Dict{Symbol,Tuple{Int,Int}}(),
        Dict{Symbol,TypeSpec}(),
        startswith(pb.ref, "stdlib:"),
        any(d -> d.severity == "error", pb.diagnostics),
    )
end

function _report!(ck::Checker, code, message, node; hint = nothing, severity = nothing, scope = nothing)
    code[1] == 'E' && (ck.failed = true)
    push!(
        ck.diags,
        diag(
            code,
            message,
            ck.pb,
            node;
            hint = hint,
            severity = severity,
            scope = scope === nothing ? scope_string(ck.scope) : scope,
        ),
    )
    return nothing
end

"""    check_block(pb::ParsedBlock) -> Vector{Diagnostic}

Run the block-level checks (plan 4.4). Includes the parse-stage diagnostics carried by `pb`.
"""
function check_block(pb::ParsedBlock)
    ck = Checker(pb)
    _check_declaration_names!(ck)
    _check_declaration_types!(ck)
    _check_port_dimension!(ck)
    _check_defaults!(ck)
    _check_components!(ck)
    _check_observations!(ck)
    for item in pb.equation_items
        _check_eq_item!(ck, item)
    end
    _check_initial_items!(ck)
    _check_discrete_scopes!(ck)
    _check_events!(ck)
    _check_causality!(ck)
    _check_units!(ck)
    _check_unused!(ck)
    _check_balance!(ck)
    return ck.diags
end

# ---------------------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------------------

function _check_declaration_names!(ck::Checker)
    seen = Dict{Symbol,SourceRange}()
    for scope in DECLARATION_SCOPES
        for d in get(ck.pb.declaration_map, scope, Decl[])
            ck.scope = scope
            n = d.name
            if n === :t || n === :Ts
                _report!(
                    ck,
                    "E003",
                    "`$n` is predefined and cannot be declared",
                    d;
                    hint = "`t` is the simulation time; choose another name",
                )
            elseif function_rule(n) !== nothing || n === :ifelse
                _report!(
                    ck,
                    "E003",
                    "`$n` shadows built-in function `$n`",
                    d;
                    hint = "rename the declaration; built-in functions cannot be shadowed",
                )
            end
            if haskey(seen, n)
                _report!(
                    ck,
                    "E003",
                    "`$n` is already declared on line $(seen[n].line)",
                    d;
                    hint = "a name may be declared once per block",
                )
            else
                seen[n] = d.range
            end
        end
    end
    ck.scope = :equations
    return nothing
end

function _check_declaration_types!(ck::Checker)
    discrete_names = _discrete_assigned_names(ck.pb)
    for scope in DECLARATION_SCOPES
        for d in get(ck.pb.declaration_map, scope, Decl[])
            ck.scope = scope
            t = d.type
            if scope == :ports
                if t.kind != :Power
                    _report!(
                        ck,
                        "E004",
                        "a port must be `Power{Domain}`, found `$(type_name(t))`",
                        d;
                        hint = "write `p::Power{Generic}` or `p::Power{Electrical}`",
                    )
                end
                continue
            end
            if t.kind == :Power
                _report!(
                    ck,
                    "E004",
                    "`$(type_name(t))` is only allowed in @ports",
                    d;
                    hint = "power ports are declared in @ports",
                )
                continue
            end
            if t.kind == :Bool && scope == :variables && !(d.name in discrete_names)
                _report!(
                    ck,
                    "E004",
                    "`Bool` is not allowed as a continuous state",
                    d;
                    hint = "Bool values belong in discrete code or in an output",
                )
            end
            if t.kind == :Int && scope in (:variables, :inputs, :outputs)
                if scope in (:variables, :outputs) && d.name in discrete_names
                    # A held discrete counter: Int is allowed because it lives in discrete
                    # code only (plan 4.3: "Int only in discrete code, indices and constants").
                else
                    _report!(
                        ck,
                        "E004",
                        "`Int` is only allowed in discrete code, indices and constants",
                        d;
                        hint = "use `Real` here, or assign the counter in a `@discrete` scope",
                    )
                end
            end
            if scope == :constants && d.default === nothing
                _report!(
                    ck,
                    "E004",
                    "`$(d.name)` is a constant and needs a value",
                    d;
                    hint = "write `$(d.name)::$(type_name(t)) = ...`",
                )
            end
            if t.kind == :Vec || t.kind == :Mat
                for a in t.args
                    a isa Symbol && haskey(ck.decls, a) && push!(ck.used, a)
                    if a isa Expr
                        size_names = Set{Symbol}()
                        _collect_expr_refs!(size_names, a)
                        for n in size_names
                            haskey(ck.decls, n) && push!(ck.used, n)
                        end
                    end
                end
                if type_size(t, ck.consts) === nothing
                    _report!(
                        ck,
                        "E005",
                        "array size of `$(d.name)` is not static: `$(type_name(t))`",
                        d;
                        hint = "declare the size in `@constants`, e.g. `@constants N::Int = 3`",
                    )
                end
            end
        end
    end
    ck.scope = :equations
    return nothing
end

"""
    _check_port_dimension!(ck)

D-MB12: a block has at most one model dimension, derived from its ports (Planar -> 2,
Spatial -> 3). Mixing Planar and Spatial ports in one block is a clear E102 instead of
silently picking one; the interface then omits `dimension`.
"""
function _check_port_dimension!(ck::Checker)
    planar = nothing
    spatial = nothing
    for d in ports(ck.pb)
        dom = type_domain(d.type)
        dom === :Planar && planar === nothing && (planar = d)
        dom === :Spatial && spatial === nothing && (spatial = d)
    end
    (planar === nothing || spatial === nothing) && return nothing
    ck.scope = :ports
    _report!(
        ck,
        "E102",
        "`$(ck.pb.name)` mixes Planar and Spatial ports (`$(planar.name)` is Planar, `$(spatial.name)` is Spatial)",
        spatial;
        hint = "a block has one model dimension; split it into a planar and a spatial block, or use ports of the same domain",
    )
    ck.scope = :equations
    return nothing
end

function _check_defaults!(ck::Checker)
    for scope in DECLARATION_SCOPES
        for d in get(ck.pb.declaration_map, scope, Decl[])
            d.default === nothing && continue
            ck.scope = scope
            ck.context = :default
            t = _check_expr!(ck, d.default)
            ck.context = :equation
            if t !== nothing && !assignable(resolve_type(d.type, ck.consts), t)
                _report!(
                    ck,
                    "E004",
                    "default of `$(d.name)` is `$(type_name(t))` but the declaration is `$(type_name(d.type))`",
                    d.default;
                )
            end
            if scope == :constants
                ok, value = try_eval_const(d.default, ck.consts)
                if !ok
                    _report!(
                        ck,
                        "E004",
                        "`$(d.name)` is not a constant expression: $value",
                        d.default;
                        hint = "constants may use literals, other constants and pure functions",
                    )
                end
            end
        end
    end
    ck.scope = :equations
    ck.context = :equation
    return nothing
end

# ---------------------------------------------------------------------------------------
# Textual subsystems (J2.6, decision D5)
# ---------------------------------------------------------------------------------------

# What a composite may declare besides its interface, its parameters and its components.
# Everything else is a flat block construct that has no meaning without `@equations` of its
# own. `@parameters` (J2.6b) are exposed at the composite's path and aliased symbolically
# into the internal components' parameters, so they stay runtime-tunable.
const _COMPOSITE_FORBIDDEN = (
    (scope = :variables, hint = "declare it in the component that owns it"),
    (scope = :equations, hint = "a composite is a wiring diagram; its physics lives in the components"),
    (scope = :initial, hint = "initial equations belong to a component"),
    (scope = :discrete, hint = "discrete code belongs to a component"),
    (scope = :events, hint = "events belong to a component"),
    (scope = :causality, hint = "declare causality on the component"),
)

"""Whether the parsed block declares anything in `scope` (a declaration scope or an item
scope)."""
function _has_scope(pb::ParsedBlock, scope::Symbol)
    scope == :equations && return !isempty(pb.equation_items)
    scope == :initial && return !isempty(pb.initial_items)
    scope == :discrete && return !isempty(pb.discrete_items)
    scope == :events && return !isempty(pb.event_items)
    scope == :causality && return !isempty(pb.causality_items)
    return !isempty(get(pb.declaration_map, scope, Decl[]))
end

"""
    _check_components!(ck)

The block-level checks of `@components` / `@connections` (J2.6). A block that declares
components is the *textual form of a subsystem* (D5): its interface is `@ports`, `@inputs`
and `@outputs`, its body is the component list and the wiring between the component ports and
the interface ports.

Checked here:
- a composite has no `@variables`, `@equations`, `@initial`, `@discrete`, `@events` or
  `@causality` of its own; `@parameters` are allowed and become the composite's tunable
  parameters (J2.6b), while `@observables` alias internal signals to the composite path;
- component names are unique and do not collide with a declaration;
- every `connect` side names an interface port or a declared component;
- the parameter overrides of a component are constant expressions or a name of one of the
  composite's `@parameters` (the J2.6b symbolic alias);
- every interface port is exposed by exactly one `connect` to a component port. The exposed
  internal port itself is checked at instantiation, when the component's block is known.

A referenced component *port* that does not exist is E102 at instantiation (the component's
block is not loaded during the fast block check), with the component's path.
"""
function _check_components!(ck::Checker)
    comps = ck.pb.component_items
    conns = ck.pb.connection_items
    isempty(comps) && isempty(conns) && return nothing
    if isempty(comps)
        _report!(
            ck,
            "E003",
            "`@connections` has nothing to connect: the block declares no `@components`",
            isempty(conns) ? ck.pb.range : conns[1];
            scope = :connections,
            hint = "declare the internal instances in a `@components` scope first",
        )
        ck.scope = :equations
        return nothing
    end
    blockname = block_name(ck.pb)
    for entry in _COMPOSITE_FORBIDDEN
        _has_scope(ck.pb, entry.scope) || continue
        node = _first_scope_node(ck.pb, entry.scope)
        _report!(
            ck,
            "E001",
            "a textual composite cannot declare `$(scope_string(entry.scope))`",
            node;
            scope = entry.scope,
            hint = entry.hint,
            severity = "error",
        )
    end
    if ck.failed
        ck.scope = :equations
        return nothing
    end

    # Component names: unique, and disjoint from the declarations of the block.
    seen = Dict{Symbol,SourceRange}()
    for comp in comps
        n = comp.name
        d = get(ck.decls, n, nothing)
        if d !== nothing
            _report!(
                ck,
                "E003",
                "component `$n` collides with the `$(scope_string(d.scope))` declaration of `$n`",
                comp;
                scope = :components,
                hint = "a component name is a name inside the composite; choose another one",
            )
        end
        if haskey(seen, n)
            _report!(
                ck,
                "E003",
                "component `$n` is declared twice",
                comp;
                scope = :components,
                hint = "a component name is unique inside a composite",
            )
        else
            seen[n] = comp.range
        end
        push!(ck.used, n)
        for (key, value) in comp.kwargs
            ck.scope = :components
            ck.context = :default
            t = _check_expr!(ck, value)
            if t !== nothing && !is_scalar_type(t) && !is_array_type(t)
                _report!(
                    ck,
                    "E004",
                    "parameter `$key` of component `$n` must be a value, got `$(type_name(t))`",
                    value;
                    scope = :components,
                )
            end
            if value isa Name && haskey(ck.decls, value.name) &&
               ck.decls[value.name].scope == :parameters
                # J2.6b: a component parameter may be bound to one of the composite's own
                # parameters. It is not a constant; instantiation creates the alias.
                push!(ck.used, value.name)
                continue
            end
            ok, folded = try_eval_const(value, ck.consts)
            ok && continue
            message = String(folded)
            code = occursin("is not a constant", message) ? "E003" : "E001"
            _report!(
                ck,
                code,
                "parameter `$key` of component `$n` is not a constant expression: $message",
                value;
                scope = :components,
                hint = "a component parameter is bound at compile time; use literals and `@constants`",
            )
        end
    end
    ck.context = :equation

    # Interface ports: each must be exposed by exactly one `connect`.
    face_uses = Dict{Symbol,Int}()
    for c in conns
        ck.scope = :connections
        for (ref, other) in ((c.from, c.to), (c.to, c.from))
            if ref.instance === nothing
                d = get(ck.decls, ref.port, nothing)
                if d === nothing || !(d.scope in (:ports, :inputs, :outputs))
                    _report!(
                        ck,
                        "E003",
                        "`$(ref.port)` is not a port of `$blockname`",
                        ref;
                        scope = :connections,
                        hint = "declare it in `@ports`, `@inputs` or `@outputs`",
                    )
                    continue
                end
                push!(ck.used, ref.port)
                face_uses[ref.port] = get(face_uses, ref.port, 0) + 1
                if other.instance === nothing
                    _report!(
                        ck,
                        "E001",
                        "`connect` joins two ports of `$blockname`",
                        c;
                        scope = :connections,
                        hint = "connect each interface port to a component port",
                    )
                end
            elseif !haskey(seen, ref.instance)
                _report!(
                    ck,
                    "E003",
                    "`connect` refers to unknown component `$(ref.instance)`",
                    ref;
                    scope = :connections,
                    hint = "declare it in `@components`, or fix the spelling",
                )
            end
        end
        if c.from.instance !== nothing && c.from.instance === c.to.instance &&
           c.from.port === c.to.port
            _report!(
                ck,
                "E003",
                "port `$(c.from.port)` of component `$(c.from.instance)` is connected to itself",
                c;
                scope = :connections,
            )
        elseif c.from.instance === nothing && c.to.instance === nothing &&
               c.from.port === c.to.port
            _report!(
                ck,
                "E003",
                "port `$(c.from.port)` of `$blockname` is connected to itself",
                c;
                scope = :connections,
            )
        end
    end
    for scope in (:ports, :inputs, :outputs)
        for d in get(ck.pb.declaration_map, scope, Decl[])
            uses = get(face_uses, d.name, 0)
            uses == 1 && continue
            what = scope === :ports ? "power port" : (scope === :inputs ? "input" : "output")
            _report!(
                ck,
                "E003",
                uses == 0 ?
                "$what `$(d.name)` of `$blockname` is not connected to a component" :
                "$what `$(d.name)` of `$blockname` is exposed by more than one `connect`",
                d;
                scope = :connections,
                hint = uses == 0 ?
                       "connect it to one component port, as in `connect($(d.name), gear.$(d.name))`" :
                       "an interface port exposes exactly one internal port",
            )
        end
    end
    ck.scope = :equations
    ck.context = :equation
    return nothing
end

"""    _check_observations!(ck)

Validate the `@observables` scope of a textual composite (J2.6b). An observed entry aliases
an internal component signal to the composite's own path. The target must be a component
variable (`instance.var`) or a port field (`instance.port.e`/`.f`); whether that variable or
port exists is checked at instantiation, when the component's block is loaded. Names are
unique, and an unqualified observed name must not shadow a declaration of the composite.
"""
function _check_observations!(ck::Checker)
    obs = ck.pb.observation_items
    isempty(obs) && return nothing
    if isempty(ck.pb.component_items)
        _report!(
            ck,
            "E003",
            "`@observables` has nothing to observe: the block declares no `@components`",
            first(obs);
            scope = :observables,
            hint = "declare the internal instances in a `@components` scope first",
        )
        return nothing
    end
    comps = Set(component_name(c) for c in ck.pb.component_items)
    seen = Dict{Tuple{Symbol,Union{Symbol,Nothing}},SourceRange}()
    for o in obs
        ck.scope = :observables
        name = observation_name(o)
        key = (name, observation_field(o))
        if haskey(seen, key)
            _report!(
                ck,
                "E003",
                "observed signal `$name` is declared twice",
                o;
                scope = :observables,
                hint = "each observed signal name is unique inside a composite",
            )
        else
            seen[key] = source_range(o)
        end
        if observation_field(o) === nothing
            d = get(ck.decls, name, nothing)
            if d !== nothing
                _report!(
                    ck,
                    "E003",
                    "observed signal `$name` collides with the `$(scope_string(d.scope))` declaration of `$name`",
                    o;
                    scope = :observables,
                    hint = "choose another name for the observed signal",
                )
            end
        else
            d = get(ck.decls, name, nothing)
            if d === nothing || !(d.scope in (:ports, :inputs, :outputs))
                _report!(
                    ck,
                    "E003",
                    "`$name` is not a port of `$(block_name(ck.pb))`",
                    o;
                    scope = :observables,
                    hint = "an observed port field names an interface port",
                )
            else
                push!(ck.used, name)
            end
        end
        target = observation_target(o)
        instance = _observation_instance(target)
        field = _observation_field(target)
        if instance === nothing || field === nothing
            _report!(
                ck,
                "E003",
                "an observed target is `instance.signal` or `instance.port.e`/`.f`",
                o;
                scope = :observables,
                hint = "write `i = inductor.i` or `p.e = resistor.p.e`",
            )
        elseif !(instance in comps)
            _report!(
                ck,
                "E003",
                "`@observables` refers to unknown component `$instance`",
                o;
                scope = :observables,
                hint = "declare it in `@components`, or fix the spelling",
            )
        end
    end
    ck.scope = :equations
    return nothing
end

# The component name of an observation target, or `nothing` when the shape is wrong.
_observation_instance(e::Name) = nothing
_observation_instance(e::Field) = e.base isa Name ? e.base.name :
    (e.base isa Field && e.base.base isa Name ? e.base.base.name : nothing)
_observation_instance(::Any) = nothing

# The final signal name of an observation target (the variable or the port field).
_observation_field(e::Name) = e.name
_observation_field(e::Field) = e.field
_observation_field(::Any) = nothing

"""The node a forbidden-scope diagnostic points at: the first declaration or item of that
scope, or the block itself."""
function _first_scope_node(pb::ParsedBlock, scope::Symbol)
    if _has_scope(pb, scope)
        if scope in (:equations, :initial, :discrete, :events)
            items = getfield(pb, scope == :equations ? :equation_items :
                scope == :initial ? :initial_items :
                scope == :discrete ? :discrete_items : :event_items)
            return first(items)
        elseif scope == :causality
            return first(pb.causality_items)
        end
        return first(get(pb.declaration_map, scope, Decl[]))
    end
    return pb.range
end

# ---------------------------------------------------------------------------------------
# Equations
# ---------------------------------------------------------------------------------------

function _check_eq_item!(ck::Checker, item)
    if item isa Equation
        _check_equation!(ck, item)
    elseif item isa IfEquation
        _check_if_equation!(ck, item)
    elseif item isa ForEquation
        _check_for_equation!(ck, item)
    end
    return nothing
end

function _check_equation!(ck::Checker, eq::Equation)
    ck.scope = eq.scope
    ck.context = :equation
    lhs = _check_expr!(ck, eq.lhs)
    rhs = _check_expr!(ck, eq.rhs)
    if eq.lhs isa Name && haskey(ck.decls, eq.lhs.name)
        d = ck.decls[eq.lhs.name]
        if d.scope in (:parameters, :constants, :inputs)
            what = d.scope == :inputs ? "an input" :
                   d.scope == :parameters ? "a parameter" : "a constant"
            _report!(
                ck,
                "E004",
                "`$(eq.lhs.name)` is $what and cannot be the left side of an equation",
                eq.lhs;
                hint = "put the unknown on the left: `unknown ~ expression`",
            )
        end
    end
    if lhs !== nothing && rhs !== nothing && !assignable(lhs, rhs) && !assignable(rhs, lhs)
        _report!(
            ck,
            "E004",
            "type mismatch: `$(type_name(lhs))` ~ `$(type_name(rhs))`",
            eq;
        )
    end
    return nothing
end

function _check_if_equation!(ck::Checker, ifeq::IfEquation)
    has_else = any(b -> b.cond === nothing, ifeq.branches)
    if !has_else
        _report!(
            ck,
            "E001",
            "an `if` in $(scope_string(ck.scope)) needs an `else` branch",
            ifeq;
            hint = "every branch must leave the same number of equations",
        )
    end
    for b in ifeq.branches
        if b.cond !== nothing
            t = _check_cond!(ck, b.cond)
            if t !== nothing && t.kind != :Bool
                _report!(
                    ck,
                    "E004",
                    "`if` condition must be Bool, got `$(type_name(t))`",
                    b.cond,
                )
            end
        end
        for item in b.body
            _check_eq_item!(ck, item)
        end
    end
    # Plan 4.4: an `if` counts one branch, with `for` loops unrolled and Vec/Mat expanded, so
    # the branch count is the scalar equation count.
    counts = [_count_items(b.body, ck.decls, ck.consts) for b in ifeq.branches]
    if length(unique(counts)) > 1
        _report!(
            ck,
            "E001",
            "the branches of an `if` must have the same number of equations, got $(join(counts, ", "))",
            ifeq;
            hint = "move the branch-varying part into an `ifelse` expression",
        )
    end
    return nothing
end

function _check_for_equation!(ck::Checker, fe::ForEquation)
    range = _check_for_bounds!(ck, fe.lo, fe.hi, fe.step)
    _check_local_name!(ck, fe.var, fe)
    ck.loopvars[fe.var] = INT
    range === nothing || (ck.loop_ranges[fe.var] = range)
    for item in fe.body
        _check_eq_item!(ck, item)
    end
    delete!(ck.loopvars, fe.var)
    delete!(ck.loop_ranges, fe.var)
    return nothing
end

"""Fold and check a `for` range, return the inclusive `(first, last)` iteration values when
they are static, else `nothing`. Reports E005 for a bound that is not an integer constant."""
function _check_for_bounds!(ck::Checker, lo, hi, step)
    values = Any[nothing, nothing, 1]
    ok = true
    for (i, e) in enumerate((lo, hi, step))
        e === nothing && continue
        _check_expr!(ck, e)   # marks constants used and reports bad names
        good, value = try_eval_const(e, ck.consts)
        if !good
            ok = false
            _report!(
                ck,
                "E005",
                (i == 3 ? "the `for` step must be constant: " : "the `for` range must be constant: ") *
                value,
                e;
                hint = "N in `for i in 1:N` must be a `@constants` value",
            )
        elseif !(value isa Integer)
            ok = false
            _report!(ck, "E005", "the `for` range must be integral, got `$value`", e)
        else
            values[i] = Int(value)
        end
    end
    ok || return nothing
    from, to = values[1], values[2]
    (from === nothing || to === nothing) && return nothing
    s = values[3]
    s == 0 && return nothing
    n = s > 0 ? fld(to - from, s) + 1 : fld(from - to, -s) + 1
    n <= 0 && return (from, from - 1)   # an empty loop: no index is ever in range
    last = from + (n - 1) * s
    return minmax(from, last)
end

# ---------------------------------------------------------------------------------------
# @initial (J2.1)
# ---------------------------------------------------------------------------------------

"""`@initial` is checked like `@equations`; only the semantics differ (no `ddt`, and the
equations are solved once and are not part of the balance count)."""
function _check_initial_items!(ck::Checker)
    for item in ck.pb.initial_items
        old_scope, old_context = ck.scope, ck.context
        ck.scope = :initial
        ck.context = :equation
        _check_eq_item!(ck, item)
        ck.scope, ck.context = old_scope, old_context
    end
    return nothing
end

# ---------------------------------------------------------------------------------------
# @discrete and @events (J2.1, D18 and D19)
# ---------------------------------------------------------------------------------------

function _check_discrete_scopes!(ck::Checker)
    for ds in ck.pb.discrete_items
        ck.scope = :discrete
        ck.context = :discrete
        empty!(ck.locals)
        empty!(ck.loopvars)
        empty!(ck.loop_ranges)
        # Walk the period and offset so constants used only there are marked used (W204).
        _check_expr!(ck, ds.period)
        ds.offset === nothing || _check_expr!(ck, ds.offset)
        for stmt in ds.body
            _check_stmt!(ck, stmt)
        end
    end
    empty!(ck.locals)
    ck.scope = :equations
    ck.context = :equation
    return nothing
end

function _check_events!(ck::Checker)
    for ev in ck.pb.event_items
        old_scope, old_context = ck.scope, ck.context
        ck.scope = :events
        ck.context = :events
        empty!(ck.locals)
        empty!(ck.loopvars)
        empty!(ck.loop_ranges)
        _check_event_condition!(ck, ev)
        for stmt in ev.body
            _check_stmt!(ck, stmt)
        end
        empty!(ck.locals)
        ck.scope, ck.context = old_scope, old_context
    end
    return nothing
end

"""D19: an event trigger is a real expression (an upward zero crossing) or a `<` / `>`
comparison. Any other comparison is rejected, because "becomes true" has no upward zero
crossing for `<=`, `>=`, `==` or `!=`."""
function _check_event_condition!(ck::Checker, ev::EventDecl)
    cond = ev.cond
    if cond isa Comparison
        if !(cond.op === :< || cond.op === :>)
            _report!(
                ck,
                "E001",
                "an `@events` condition is `a < b`, `a > b` or a real expression, not `$(cond.op)`",
                cond;
                hint = "write `a < b` or `a > b`; the body fires when the comparison becomes true",
            )
        end
        for node in (cond.lhs, cond.rhs)
            t = _check_expr!(ck, node)
            if t !== nothing && !_numeric(t)
                _report!(
                    ck,
                    "E004",
                    "an `@events` condition compares numbers, got `$(type_name(t))`",
                    node;
                    hint = "use a real expression or a comparison of two numbers",
                )
            end
        end
        return nothing
    end
    t = _check_expr!(ck, cond)
    if t !== nothing && t.kind !== :Real
        _report!(
            ck,
            "E004",
            "an `@events` condition must be a real expression or a comparison, got `$(type_name(t))`",
            cond;
            hint = "write `x - x0` for an upward zero crossing, or `x < x0`",
        )
    end
    return nothing
end

function _check_stmt!(ck::Checker, stmt)
    if stmt isa Assign
        _check_assign!(ck, stmt)
    elseif stmt isa IfStatement
        _check_if_statement!(ck, stmt)
    elseif stmt isa ForStatement
        _check_for_statement!(ck, stmt)
    elseif stmt isa CallStatement
        _check_call_statement!(ck, stmt)
    end
    return nothing
end

function _check_if_statement!(ck::Checker, stmt::IfStatement)
    old_scope = ck.scope
    ck.scope = stmt.scope
    for b in stmt.branches
        if b.cond !== nothing
            t = _check_cond!(ck, b.cond)
            if t !== nothing && t.kind !== :Bool
                _report!(
                    ck,
                    "E004",
                    "`if` condition must be Bool, got `$(type_name(t))`",
                    b.cond,
                )
            end
        end
        for item in b.body
            _check_stmt!(ck, item)
        end
    end
    ck.scope = old_scope
    return nothing
end

function _check_for_statement!(ck::Checker, stmt::ForStatement)
    old_scope = ck.scope
    ck.scope = stmt.scope
    range = _check_for_bounds!(ck, stmt.lo, stmt.hi, stmt.step)
    _check_local_name!(ck, stmt.var, stmt)
    ck.loopvars[stmt.var] = INT
    range === nothing || (ck.loop_ranges[stmt.var] = range)
    for item in stmt.body
        _check_stmt!(ck, item)
    end
    delete!(ck.loopvars, stmt.var)
    delete!(ck.loop_ranges, stmt.var)
    ck.scope = old_scope
    return nothing
end

function _check_call_statement!(ck::Checker, stmt::CallStatement)
    old_scope = ck.scope
    ck.scope = stmt.scope
    name = stmt.call.fn.name
    if name !== :reinit
        _report!(
            ck,
            "E001",
            "`$name` is not a statement",
            stmt.call.fn;
            hint = "only `reinit(x, value)` is a call statement, and only in `@events`",
        )
        ck.scope = old_scope
        return nothing
    end
    _check_expr!(ck, stmt.call)
    ck.scope = old_scope
    return nothing
end

"""
    _check_local_name!(ck, name, node) -> Bool

A D18 temporary or a loop variable may not shadow a predefined name or a built-in
function (spec: "Shadowing a whitelisted function name is an error"). Reports E003 and
returns `false` when `name` is not usable as a local.
"""
function _check_local_name!(ck::Checker, n::Symbol, node)
    if n === :t || n === :Ts
        _report!(
            ck,
            "E003",
            "`$n` is predefined and cannot be assigned",
            node;
            hint = "choose another name; `t` is the simulation time and `Ts` the clock period",
        )
        return false
    elseif function_rule(n) !== nothing || n === :ifelse
        _report!(
            ck,
            "E003",
            "`$n` shadows built-in function `$n`",
            node;
            hint = "rename the temporary; built-in functions cannot be shadowed",
        )
        return false
    end
    return true
end

"""
Check one assignment (D18). A declared `@variables`/`@outputs` name is a held value; an
undeclared name in `@discrete`/`@events` becomes a block-local temporary whose type and size
come from the assigned value. Assigning to an input, parameter, constant or port is E004.
"""
function _check_assign!(ck::Checker, a::Assign)
    old_scope = ck.scope
    ck.scope = a.scope
    target = a.target
    if target isa Name
        n = target.name
        if haskey(ck.locals, n) && !haskey(ck.decls, n)
            tt = ck.locals[n]
            _check_assign_value!(ck, a, tt)
        elseif haskey(ck.decls, n)
            d = ck.decls[n]
            push!(ck.used, n)
            if !(d.scope in (:variables, :outputs))
                what = d.scope == :inputs ? "an input" :
                       d.scope == :parameters ? "a parameter" :
                       d.scope == :constants ? "a constant" :
                       d.scope == :ports ? "a port" : "declared in " * scope_string(d.scope)
                _report!(
                    ck,
                    "E004",
                    "`$n` is $what and cannot be assigned",
                    target;
                    hint = "assign a `@variables` or `@outputs` value, or a new temporary (D18)",
                )
                _check_expr!(ck, a.value)
            else
                _check_assign_value!(ck, a, resolve_type(d.type, ck.consts))
            end
        else
            name_ok = _check_local_name!(ck, n, target)
            if a.op !== :assign
                name_ok && _report!(
                    ck,
                    "E003",
                    "`$n` is used but not declared",
                    target;
                    hint = "write `$n = ...` first to create a temporary (D18)",
                )
                _check_expr!(ck, a.value)
            else
                vt = _check_expr!(ck, a.value)
                name_ok && vt !== nothing && (ck.locals[n] = vt)
            end
        end
    elseif target isa Index
        _check_assign_index!(ck, target)
        tt = _check_index!(ck, target)
        if tt === nothing
            _check_expr!(ck, a.value)
        else
            _check_assign_value!(ck, a, tt)
        end
    else
        _report!(
            ck,
            "E001",
            "the left side of an assignment must be a name or an index",
            target;
            hint = "write `x = value`, `x[i] = value`, `x += value` or `x[i] += value`",
        )
        _check_expr!(ck, a.value)
    end
    ck.scope = old_scope
    return nothing
end

function _check_assign_value!(ck::Checker, a::Assign, target_type::TypeSpec)
    vt = _check_expr!(ck, a.value)
    vt === nothing && return nothing
    result = vt
    if a.op !== :assign
        result = _arith_result!(ck, a.op, target_type, vt, a)
        result === nothing && return nothing
    end
    if !assignable(target_type, result)
        _report!(
            ck,
            "E004",
            "cannot assign `$(type_name(result))` to `$(type_name(target_type))`",
            a.value;
            hint = "types never convert implicitly; `Real` to `Int` in particular",
        )
    end
    return nothing
end

function _check_assign_index!(ck::Checker, target::Index)
    base = target.base
    if !(base isa Name)
        _report!(
            ck,
            "E001",
            "an indexed assignment needs a declared name as its base",
            target;
            hint = "write `x[i] = value`, where `x` is a `Vec`/`Mat` or a D18 temporary",
        )
        return nothing
    end
    n = base.name
    if haskey(ck.decls, n)
        d = ck.decls[n]
        push!(ck.used, n)
        if !(d.scope in (:variables, :outputs))
            _report!(
                ck,
                "E004",
                "`$n` is not a held value and cannot be assigned",
                base;
                hint = "assign a `@variables` or `@outputs` array, or a new temporary (D18)",
            )
        end
    end
    return nothing
end

# ---------------------------------------------------------------------------------------
# Causality
# ---------------------------------------------------------------------------------------

function _check_causality!(ck::Checker)
    ck.scope = :causality
    for c in ck.pb.causality_items
        for p in c.ports
            if !haskey(ck.decls, p) || ck.decls[p].scope != :ports
                _report!(
                    ck,
                    "E003",
                    "`$p` is not a port of this block",
                    c;
                    hint = "declare it in @ports first",
                )
            else
                push!(ck.used, p)
            end
        end
    end
    ck.scope = :equations
    return nothing
end

# ---------------------------------------------------------------------------------------
# Units (J1.2 hook)
# ---------------------------------------------------------------------------------------

# J1.2 owns `src/units/` and adds `Units.check_units(pb)::Vector{Diagnostic}`. Until that
# module exists this is a no-op. This `isdefined` guard is the only one in the front end and
# J1.2 may remove it once `Units` is always loaded.
function _check_units!(ck::Checker)
    isdefined(@__MODULE__, :Units) || return nothing
    units = getfield(@__MODULE__, :Units)
    isdefined(units, :check_units) || return nothing
    extra = getfield(units, :check_units)(ck.pb)
    for d in extra
        push!(ck.diags, d isa Diagnostic ? d : from_dict(Dict(d)))
    end
    return nothing
end

# ---------------------------------------------------------------------------------------
# Unused declarations (W204)
# ---------------------------------------------------------------------------------------

function _check_unused!(ck::Checker)
    for scope in DECLARATION_SCOPES
        for d in get(ck.pb.declaration_map, scope, Decl[])
            d.name in ck.used && continue
            ck.scope = scope
            _report!(
                ck,
                "W204",
                "`$(d.name)` is declared but never used",
                d;
                hint = "remove the declaration, or use it in an equation",
            )
        end
    end
    ck.scope = :equations
    return nothing
end

# ---------------------------------------------------------------------------------------
# Balance (plan 4.4)
# ---------------------------------------------------------------------------------------

"""    block_balance(pb) -> (unknowns, equations)

The scalar counts behind the block-level balance precheck: unknowns are
`#variables + #outputs + #powerports` (scalars, with `Vec`/`Mat` expanded), equations are the
scalar equations after unrolling `for` and taking one branch of an `if`.

Names assigned in `@discrete` or `@events` are *held discrete values*, not continuous
unknowns (plan 4.4: "discrete-scope variables are excluded"), so they are left out of the
unknown count. `@initial` equations are not counted either: they are solved once.
"""
function block_balance(pb::ParsedBlock)
    decls = Dict{Symbol,Decl}()
    for scope in DECLARATION_SCOPES
        for d in get(pb.declaration_map, scope, Decl[])
            haskey(decls, d.name) || (decls[d.name] = d)
        end
    end
    consts = constant_env(pb)
    discrete_names = _discrete_assigned_names(pb)
    unknowns = 0
    for scope in (:variables, :outputs, :ports)
        for d in get(pb.declaration_map, scope, Decl[])
            d.name in discrete_names && continue
            unknowns += type_scalar_count(resolve_type(d.type, consts), consts)
        end
    end
    eqs = _count_items(pb.equation_items, decls, consts)
    return (unknowns = unknowns, equations = eqs)
end

"""The names assigned anywhere in `@discrete` or `@events` (an indexed assignment counts its
base name). They are held discrete values, excluded from the balance count."""
function _discrete_assigned_names(pb::ParsedBlock)
    out = Set{Symbol}()
    for ds in pb.discrete_items, stmt in ds.body
        _collect_assigned!(out, stmt)
    end
    for ev in pb.event_items, stmt in ev.body
        _collect_assigned!(out, stmt)
    end
    return out
end

function _collect_assigned!(out::Set{Symbol}, stmt)
    if stmt isa Assign
        n = _assign_base_name(stmt.target)
        n === nothing || push!(out, n)
    elseif stmt isa IfStatement
        for b in stmt.branches, s in b.body
            _collect_assigned!(out, s)
        end
    elseif stmt isa ForStatement
        for s in stmt.body
            _collect_assigned!(out, s)
        end
    end
    return nothing
end

_assign_base_name(e::Name) = e.name
_assign_base_name(e::Index) = _assign_base_name(e.base)
_assign_base_name(::Any) = nothing

function _scalar_size(e, decls::Dict{Symbol,Decl}, consts::AbstractDict)::Int
    if e isa Name && haskey(decls, e.name)
        d = decls[e.name]
        return type_scalar_count(resolve_type(d.type, consts), consts)
    elseif e isa Field && e.base isa Name && haskey(decls, e.base.name)
        # `p.e`/`p.f` on a multibond port is one scalar per component: the balance count of
        # a whole-port equation is the port size (D-MB10).
        d = decls[e.base.name]
        d.scope == :ports && return type_scalar_count(resolve_type(d.type, consts), consts)
        return 1
    elseif e isa Call && e.fn.name === :ddt && length(e.args) == 1
        return _scalar_size(e.args[1], decls, consts)
    end
    return 1
end

function _count_items(items, decls::Dict{Symbol,Decl}, consts::AbstractDict)::Int
    total = 0
    for item in items
        if item isa Equation
            total += _scalar_size(item.lhs, decls, consts)
        elseif item isa IfEquation
            isempty(item.branches) && continue
            total += _count_items(item.branches[1].body, decls, consts)
        elseif item isa ForEquation
            total += _for_iterations(item, consts) * _count_items(item.body, decls, consts)
        end
    end
    return total
end

function _for_iterations(fe::ForEquation, consts::AbstractDict)::Int
    ok1, lo = try_eval_const(fe.lo, consts)
    ok2, hi = try_eval_const(fe.hi, consts)
    step = 1
    if fe.step !== nothing
        ok3, s = try_eval_const(fe.step, consts)
        ok3 || return 1
        s isa Integer || return 1
        step = Int(s)
    end
    (ok1 && ok2 && lo isa Integer && hi isa Integer && step != 0) || return 1
    return step > 0 ? max(0, fld(Int(hi) - Int(lo), step) + 1) :
           max(0, fld(Int(lo) - Int(hi), -step) + 1)
end

_plural(n::Int, one::String, many::String) = n == 1 ? one : many

function _check_balance!(ck::Checker)
    ck.failed && return nothing
    # A textual composite (J2.6) has no equations of its own: its unknowns are the internal
    # instances, which the model-level balance check sees after flattening.
    isempty(ck.pb.component_items) || return nothing
    discrete_names = _discrete_assigned_names(ck.pb)
    continuous(scope) = count(
        d -> !(d.name in discrete_names), get(ck.pb.declaration_map, scope, Decl[])
    )
    n_vars = continuous(:variables)
    n_outs = continuous(:outputs)
    n_ports = continuous(:ports)
    bal = block_balance(ck.pb)
    bal.unknowns == bal.equations && return nothing
    # Plan 4.4: E103 at block level is reported as a *warning* (the plan section 5
    # model-level check keeps it an error). This is the one explicit severity override.
    push!(
        ck.diags,
        diag(
            "E103",
            "unbalanced block: $(bal.unknowns) $(_plural(bal.unknowns, "unknown", "unknowns")), " *
            "$(bal.equations) $(_plural(bal.equations, "equation", "equations"))",
            ck.pb,
            ck.pb.range;
            hint = "`$(block_name(ck.pb))` declares $n_vars $(_plural(n_vars, "variable", "variables")), " *
                   "$n_outs $(_plural(n_outs, "output", "outputs")) and " *
                   "$n_ports $(_plural(n_ports, "power port", "power ports")), so it needs $(bal.unknowns) equations",
            severity = "warning",
            scope = nothing,
        ),
    )
    return nothing
end

# ---------------------------------------------------------------------------------------
# Expression checking
# ---------------------------------------------------------------------------------------

function _check_cond!(ck::Checker, e)
    old = ck.allow_cond
    old_scope = ck.scope
    ck.allow_cond = true
    t = _check_expr!(ck, e)
    ck.allow_cond = old
    ck.scope = old_scope
    return t
end

function _check_expr!(ck::Checker, e)::Union{TypeSpec,Nothing}
    if e isa Lit
        v = e.value
        v isa Bool && return BOOL
        v isa Integer && return INT
        v isa AbstractFloat && return REAL
        if v isa AbstractString
            _report!(
                ck,
                "E001",
                "string literals are only allowed in `description`, `unit` and `frame` attributes",
                e;
            )
        end
        return nothing
    elseif e isa Name
        return _check_name!(ck, e)
    elseif e isa Field
        return _check_field!(ck, e)
    elseif e isa Call
        return _check_call!(ck, e)
    elseif e isa BinOp
        return _check_binop!(ck, e)
    elseif e isa UnOp
        return _check_unop!(ck, e)
    elseif e isa Index
        return _check_index!(ck, e)
    elseif e isa VectorLit
        return _check_vector!(ck, e)
    elseif e isa MatrixLit
        return _check_matrix!(ck, e)
    elseif e isa IfElse
        return _check_ifelse!(ck, e)
    elseif e isa Comparison
        return _check_comparison!(ck, e)
    elseif e isa BoolOp
        return _check_boolop!(ck, e)
    end
    return nothing
end

function _check_name!(ck::Checker, e::Name)::Union{TypeSpec,Nothing}
    n = e.name
    if haskey(ck.loopvars, n)
        return ck.loopvars[n]
    end
    if haskey(ck.locals, n)
        return ck.locals[n]
    end
    if n === :t
        if ck.context == :default
            _report!(
                ck,
                "E004",
                "`t` is not a constant expression",
                e;
                hint = "a default may use `@constants` and `@parameters`, not `t`",
            )
            return nothing
        end
        return REAL
    elseif n === :Ts
        if ck.context === :discrete
            return REAL
        end
        _report!(
            ck,
            "E001",
            "`Ts` is only available in @discrete",
            e;
            hint = "`Ts` is the clock period of a `@discrete` scope; `@events` fires on a condition, not on a clock",
        )
        return nothing
    end
    if haskey(ck.decls, n)
        d = ck.decls[n]
        push!(ck.used, n)
        if d.scope == :ports
            _report!(
                ck,
                "E003",
                "`$n` is a port; use `$n.e` or `$n.f`",
                e;
                hint = "a power port carries two variables, effort and flow",
            )
            return nothing
        end
        if ck.context == :default && d.scope in (:variables, :inputs, :outputs)
            _report!(
                ck,
                "E004",
                "`$n` is not a constant expression",
                e;
                hint = "defaults may use literals, `@constants`, `@parameters` and pure functions",
            )
            return nothing
        end
        return resolve_type(d.type, ck.consts)
    end
    if ck.context in (:discrete, :events)
        _report!(
            ck,
            "E003",
            "`$n` is used but not declared",
            e;
            hint = "assign a value to it first to create a temporary (D18), or declare it in the block",
        )
    else
        _report!(
            ck,
            "E003",
            "`$n` is used but not declared",
            e;
            hint = "declare it in @parameters, or fix the spelling",
        )
    end
    return nothing
end

function _check_field!(ck::Checker, e::Field)::Union{TypeSpec,Nothing}
    if e.base isa Name
        n = e.base.name
        if haskey(ck.decls, n)
            d = ck.decls[n]
            push!(ck.used, n)
            if d.scope == :ports
                if e.field === :e || e.field === :f
                    sz = domain_size(type_domain(d.type))
                    return sz == 1 ? REAL : TypeSpec(:Vec, (sz,))
                end
                _report!(
                    ck,
                    "E003",
                    "port `$n` has fields `e` and `f`, not `$(e.field)`",
                    e;
                    hint = "write `$n.e` for the effort or `$n.f` for the flow",
                )
                return nothing
            end
            _report!(
                ck,
                "E003",
                "`$n` is not a port, so it has no `$(e.field)` field",
                e;
                hint = "only a power port has `e` and `f`",
            )
            return nothing
        end
    end
    _check_expr!(ck, e.base)
    return nothing
end

function _arity_message(name::Symbol, rule)::String
    if rule.max_args < 0
        return "`$name` takes at least $(rule.min_args) arguments, got this many"
    elseif rule.min_args == rule.max_args
        n = rule.min_args
        return "`$name` takes $n $(_plural(n, "argument", "arguments"))"
    end
    return "`$name` takes $(rule.min_args) to $(rule.max_args) arguments"
end

function _call_scope_name(rule)
    isempty(rule.contexts) && return "no scope"
    names = String[]
    for c in rule.contexts
        push!(
            names,
            c == :equation ? "@equations" :
            c == :discrete ? "@discrete" : c == :events ? "@events" : "defaults",
        )
    end
    return join(names, " or ")
end

function _context_name(context::Symbol)::String
    context === :equation && return "@equations"
    context === :default && return "a default"
    context === :discrete && return "@discrete"
    context === :events && return "@events"
    return "@" * String(context)
end

"""Whether a function rule accepts a context. `@events` shares the `@discrete` column of the
spec tables (plan D19 bodies are discrete code); `reinit` is the one events-only row."""
function _rule_allows(rule, context::Symbol)
    context in rule.contexts && return true
    return context === :events && (:discrete in rule.contexts)
end

function _check_call!(ck::Checker, e::Call)::Union{TypeSpec,Nothing}
    name = e.fn.name
    rule = function_rule(name)
    if rule === nothing
        hint = if name === :rand || name === :randn
            "use the `noise_normal(seed, k)` intrinsic for seeded noise"
        else
            "see the built-in function whitelist in the language spec"
        end
        _report!(ck, "E002", "`$name` is not a built-in function", e.fn; hint = hint)
        return nothing
    end
    if !_rule_allows(rule, ck.context)
        _report!(
            ck,
            "E001",
            "`$name` is not allowed in $(_context_name(ck.context))",
            e.fn;
            hint = "it is available in $(_call_scope_name(rule))",
        )
        return nothing
    end
    if rule.stdlib_only && !ck.stdlib
        _report!(
            ck,
            "E002",
            "`$name` is only available in stdlib blocks",
            e.fn;
            hint = "`$name` is an intrinsic; user blocks cannot call it",
        )
        return nothing
    end
    nargs = length(e.args)
    max_args = rule.max_args < 0 ? typemax(Int) : rule.max_args
    if !(rule.min_args <= nargs <= max_args)
        _report!(
            ck,
            "E001",
            "$(_arity_message(name, rule)), got $nargs",
            e;
            hint = "see the built-in function whitelist in the language spec",
        )
        return nothing
    end
    if name === :ddt
        return _check_ddt!(ck, e)
    elseif name === :reinit
        return _check_reinit!(ck, e)
    end
    tys = Union{TypeSpec,Nothing}[_check_expr!(ck, a) for a in e.args]
    any(t -> t === nothing, tys) && return nothing
    st = TypeSpec[t for t in tys if t !== nothing]

    if name === :int
        for (i, t) in enumerate(st)
            if !_numeric(t)
                _report!(ck, "E004", "`int` needs numeric arguments, got `$(type_name(t))`", e.args[i])
                return nothing
            end
        end
        return REAL
    elseif name === :delay
        ok, _ = try_eval_const(e.args[2], ck.consts)
        if !ok
            _report!(
                ck,
                "E004",
                "`delay` needs a constant delay time",
                e.args[2];
                hint = "the delay (in seconds) must be a `@constants` value",
            )
        end
        return st[1]
    elseif name === :dot
        if length(st) == 2 && st[1].kind == :Vec && st[2].kind == :Vec
            if st[1].args != st[2].args
                _report!(
                    ck,
                    "E005",
                    "`dot` needs vectors of the same size, got `$(type_name(st[1]))` and `$(type_name(st[2]))`",
                    e;
                )
                return nothing
            end
            return REAL
        elseif length(st) == 2 && st[1].kind == :Mat && st[2].kind == :Mat
            return REAL
        end
        _report!(ck, "E004", "`dot` needs two arrays, got `$(type_name(st[1]))` and `$(type_name(st[2]))`", e)
        return nothing
    elseif name === :norm
        _numeric(st[1]) && (_report!(ck, "E004", "`norm` needs an array, got `$(type_name(st[1]))`", e); return nothing)
        return REAL
    elseif name === :cross
        if length(st) == 2 && st[1].kind == :Vec && st[2].kind == :Vec &&
           st[1].args == (3,) && st[2].args == (3,)
            return TypeSpec(:Vec, (3,))
        end
        _report!(ck, "E004", "`cross` needs two `Vec{3}` values", e)
        return nothing
    elseif name === :transpose
        if st[1].kind == :Mat
            return TypeSpec(:Mat, (st[1].args[2], st[1].args[1]))
        end
        return st[1]
    elseif name === :deadzone || name === :saturate
        for (i, t) in enumerate(st)
            if !_numeric(t)
                _report!(ck, "E004", "`$name` needs numeric arguments, got `$(type_name(t))`", e.args[i])
                return nothing
            end
        end
        return REAL
    elseif name === :interp1 || name === :interp2
        return REAL
    elseif name === :noise_normal
        for (i, t) in enumerate(st)
            if t.kind !== :Int
                _report!(
                    ck,
                    "E004",
                    "`noise_normal` needs integer `seed, k` arguments, got `$(type_name(t))`",
                    e.args[i];
                )
                return nothing
            end
        end
        return REAL
    elseif name === :previous || name === :hold
        return st[1]
    end

    for (i, t) in enumerate(st)
        if !_numeric(t)
            _report!(
                ck,
                "E004",
                "`Bool` value passed to `$name`",
                e.args[i];
                hint = "convert it first, or use it in `ifelse`",
            )
            return nothing
        end
    end
    # Preserve Int when every argument is Int and the function stays integral.
    integral = name in (:abs, :sign, :min, :max, :clamp, :floor, :ceil, :round, :mod, :rem, :hypot)
    if integral && all(t -> t.kind == :Int, st)
        return INT
    end
    return REAL
end

function _check_ddt!(ck::Checker, e::Call)::Union{TypeSpec,Nothing}
    if ck.scope === :initial
        _report!(
            ck,
            "E001",
            "`ddt` is not allowed in @initial",
            e.fn;
            hint = "initial equations are algebraic; write the derivative in @equations",
        )
    end
    arg = e.args[1]
    if arg isa Name
        n = arg.name
        if haskey(ck.decls, n)
            d = ck.decls[n]
            push!(ck.used, n)
            if d.scope == :variables
                return resolve_type(d.type, ck.consts)
            end
            what = d.scope == :parameters ? "a parameter" :
                   d.scope == :constants ? "a constant" :
                   "declared in " * scope_string(d.scope)
            _report!(
                ck,
                "E004",
                "`ddt` needs a variable, but `$n` is $what",
                arg;
                hint = "declare the integrated quantity in @variables",
            )
            return nothing
        end
    elseif arg isa Index && arg.base isa Name && haskey(ck.decls, arg.base.name) &&
           ck.decls[arg.base.name].scope == :variables
        # `ddt(P[k])` on a declared Vec/Mat variable: one scalar state per element
        # (D-MB10 writes multibond equations component-wise).
        push!(ck.used, arg.base.name)
        return _check_index!(ck, arg)
    elseif arg isa Field
        _report!(
            ck,
            "E004",
            "`ddt` needs a variable, not a port field",
            arg;
            hint = "declare the state in @variables and integrate that",
        )
        return nothing
    end
    t = _check_expr!(ck, arg)
    t === nothing && return nothing
    _report!(
        ck,
        "E004",
        "`ddt` needs a declared variable",
        arg;
        hint = "declare it in @variables",
    )
    return nothing
end

"""`reinit(x, value)` in `@events` (plan D19): `x` must be a continuous state declared in
`@variables`, and `value` must have its type and size. The lowering turns it into the
affect equation `x ~ value` evaluated with pre-event values."""
function _check_reinit!(ck::Checker, e::Call)::Union{TypeSpec,Nothing}
    arg = e.args[1]
    vt = _check_expr!(ck, e.args[2])
    if arg isa Name
        n = arg.name
        if haskey(ck.locals, n) && !haskey(ck.decls, n)
            _report!(
                ck,
                "E004",
                "`reinit` needs a state declared in @variables, but `$n` is a temporary",
                arg;
                hint = "reinit resets a continuous state; a D18 temporary is not stored between ticks",
            )
            return nothing
        elseif haskey(ck.decls, n)
            d = ck.decls[n]
            push!(ck.used, n)
            if d.scope !== :variables
                what = d.scope == :outputs ? "an output" :
                       d.scope == :inputs ? "an input" :
                       d.scope == :parameters ? "a parameter" :
                       d.scope == :constants ? "a constant" : "not a variable"
                _report!(
                    ck,
                    "E004",
                    "`reinit` needs a state declared in @variables, but `$n` is $what",
                    arg;
                    hint = "declare the reset state in @variables",
                )
                return nothing
            end
            tt = resolve_type(d.type, ck.consts)
            if vt !== nothing && !assignable(tt, vt) && !assignable(vt, tt)
                _report!(
                    ck,
                    "E004",
                    "`reinit` assigns `$(type_name(vt))` to `$n`, which is `$(type_name(tt))`",
                    e.args[2];
                )
            end
            return nothing
        end
    end
    _check_expr!(ck, arg)
    _report!(
        ck,
        "E004",
        "`reinit` needs a state declared in @variables",
        arg;
        hint = "write `reinit(x, value)` with `x` from @variables",
    )
    return nothing
end

function _check_binop!(ck::Checker, e::BinOp)::Union{TypeSpec,Nothing}
    op = e.op
    is_integer_power = op === :^ && e.rhs isa Lit && e.rhs.value isa Integer
    key = op === :^ ? (is_integer_power ? :pow_int : :pow_real) : operator_rule_key(op)
    if key === nothing
        hint = op === Symbol("%") ? "use `mod(a, b)` or `rem(a, b)`" :
               op === Symbol("÷") ? "use `floor(a / b)` or `div(a, b)`" : nothing
        _report!(ck, "E002", "operator `$op` is not on the whitelist", e; hint = hint)
        return nothing
    end
    if !syntax_allowed(key, ck.context)
        _report!(
            ck,
            "E001",
            "operator `$op` is not allowed in $(_context_name(ck.context))",
            e;
            hint = "see the operator table in the language spec",
        )
        return nothing
    end
    a = _check_expr!(ck, e.lhs)
    b = _check_expr!(ck, e.rhs)
    (a === nothing || b === nothing) && return nothing
    for (t, node) in ((a, e.lhs), (b, e.rhs))
        if t.kind == :Bool
            _report!(
                ck,
                "E004",
                "Bool value used in arithmetic",
                node;
                hint = "convert it first with a Type conversion block (Real)",
            )
            return nothing
        elseif t.kind == :Power
            _report!(ck, "E004", "a power port cannot be used in arithmetic", node)
            return nothing
        end
    end
    if op === :^
        # An integer literal exponent expands to multiplication (a negative one to division);
        # a real exponent maps to `pow`. Both are whitelisted in every expression scope.
    end
    return _arith_result!(ck, op, a, b, e)
end

function _arith_result!(ck::Checker, op::Symbol, a::TypeSpec, b::TypeSpec, e)
    if _scalar_numeric(a) && _scalar_numeric(b)
        op === :/ && return REAL
        return a.kind == :Int && b.kind == :Int ? INT : REAL
    end
    if op === :+ || op === :-
        if a.kind == b.kind && a.args == b.args
            return a
        end
        _report!(
            ck,
            "E004",
            "cannot `$op` `$(type_name(a))` and `$(type_name(b))`",
            e;
            hint = "both sides must have the same type and size",
        )
        return nothing
    end
    if op === :*
        a.kind == :Mat && b.kind == :Vec && a.args[2] == b.args[1] &&
            return TypeSpec(:Vec, (a.args[1],))
        a.kind == :Mat && b.kind == :Mat && a.args[2] == b.args[1] &&
            return TypeSpec(:Mat, (a.args[1], b.args[2]))
        if a.kind == :Vec && b.kind == :Vec
            _report!(
                ck,
                "E004",
                "`*` on two vectors is not the dot product",
                e;
                hint = "use `dot(a, b)`",
            )
            return nothing
        end
        _scalar_numeric(a) && is_array_type(b) && return b
        is_array_type(a) && _scalar_numeric(b) && return a
        _report!(ck, "E004", "cannot multiply `$(type_name(a))` and `$(type_name(b))`", e)
        return nothing
    end
    if op === :/
        is_array_type(a) && _scalar_numeric(b) && return a
        _report!(ck, "E004", "cannot divide `$(type_name(a))` by `$(type_name(b))`", e; hint = "divide by a scalar, or use `\\` for a linear solve")
        return nothing
    end
    if op === Symbol("\\")
        a.kind == :Mat && b.kind == :Vec && return TypeSpec(:Vec, (a.args[2],))
        a.kind == :Mat && b.kind == :Mat && return TypeSpec(:Mat, (a.args[2], b.args[2]))
        _scalar_numeric(a) && _scalar_numeric(b) && return REAL
        _report!(ck, "E004", "cannot solve `$(type_name(a))` \\ `$(type_name(b))`", e)
        return nothing
    end
    _report!(ck, "E004", "operator `$op` is not defined for `$(type_name(a))` and `$(type_name(b))`", e)
    return nothing
end

function _check_unop!(ck::Checker, e::UnOp)::Union{TypeSpec,Nothing}
    t = _check_expr!(ck, e.operand)
    if e.op === Symbol("!")
        if !_cond_ok(ck)
            _report!(
                ck,
                "E001",
                "`!` is only allowed inside `ifelse`, in `@discrete` and in `@events`",
                e;
                hint = "write `ifelse(!flag, a, b)`, or use `!` in discrete code",
            )
            return nothing
        end
        if t !== nothing && t.kind != :Bool
            _report!(ck, "E004", "`!` needs a Bool, got `$(type_name(t))`", e)
            return nothing
        end
        return BOOL
    end
    t === nothing && return nothing
    if t.kind == :Bool
        _report!(ck, "E004", "Bool value used in arithmetic"; e.operand)
        return nothing
    end
    _scalar_numeric(t) || is_array_type(t) || return nothing
    return t
end

"""Comparisons and `&& || !` are legal in `ifelse` conditions in equations and defaults, and
everywhere in discrete code (the spec's "@discrete / @events" column)."""
_cond_ok(ck::Checker) = ck.allow_cond || ck.context in (:discrete, :events)

function _check_index!(ck::Checker, e::Index)::Union{TypeSpec,Nothing}
    base = _check_expr!(ck, e.base)
    for i in e.indices
        it = _check_expr!(ck, i)
        if it !== nothing && it.kind != :Int && !(i isa Lit && i.value isa Integer)
            _report!(ck, "E004", "an index must be `Int`, got `$(type_name(it))`", i)
        end
    end
    base === nothing && return nothing
    if base.kind == :Vec
        if length(e.indices) != 1
            _report!(
                ck,
                "E005",
                "a vector takes one index, got $(length(e.indices))",
                e;
            )
            return nothing
        end
        n = base.args[1]
        n isa Integer && _check_one_index!(ck, e, e.indices[1], Int(n), 1, base)
        return REAL
    elseif base.kind == :Mat
        if length(e.indices) != 2
            _report!(ck, "E005", "a matrix takes two indices, got $(length(e.indices))", e)
            return nothing
        end
        if length(base.args) == 2 && base.args[1] isa Integer && base.args[2] isa Integer
            for k in 1:2
                _check_one_index!(ck, e, e.indices[k], Int(base.args[k]), k, base)
            end
        end
        return REAL
    end
    _report!(
        ck,
        "E005",
        "`$(_show(e.base))` is not an array, so it cannot be indexed",
        e;
        hint = "only `Vec` and `Mat` values have indices",
    )
    return nothing
end

"""
Range-check one index of `e` against `n` (E005). The index is checked when it is static:
a literal, a `@constants` value, or a `for` loop variable whose range is known. A loop
variable that runs outside the array is exactly the J2.1 "unrolled index check" case.
"""
function _check_one_index!(ck::Checker, e::Index, node, n::Int, k::Int, base::TypeSpec)
    where = length(e.indices) == 1 ? "" : " (index $k)"
    if node isa Name && haskey(ck.loopvars, node.name)
        r = get(ck.loop_ranges, node.name, nothing)
        r === nothing && return nothing
        if r[1] < 1 || r[2] > n
            _report!(
                ck,
                "E005",
                "loop index `$(node.name)` runs $(r[1]):$(r[2])$where but `$(_show(e.base))` is `$(type_name(base))`",
                e;
                hint = "make the loop range fit the array: 1:$(n)",
            )
        end
        return nothing
    end
    ok, value = try_eval_const(node, ck.consts)
    if !ok
        # Equations need static indices (spec table: "Yes, static indices"); discrete code
        # may use a runtime index and J2.3 emits the bounds check.
        if ck.context === :equation
            _report!(
                ck,
                "E005",
                "the index of `$(_show(e))` is not static",
                node;
                hint = "use an integer literal, a `@constants` value or a `for` loop variable",
            )
        end
        return nothing
    end
    value isa Integer || return nothing
    idx = Int(value)
    if !(1 <= idx <= n)
        _report!(
            ck,
            "E005",
            "index out of range: `$(_show(e))` but `$(_show(e.base))` is `$(type_name(base))`$where",
            e;
            hint = "use an index between 1 and $n, or raise the structural constant",
        )
    end
    return nothing
end

_show(e::Expr) = sprint(show, e)

function _check_vector!(ck::Checker, e::VectorLit)::Union{TypeSpec,Nothing}
    for el in e.elements
        t = _check_expr!(ck, el)
        t === nothing && return nothing
        if is_array_type(t)
            _report!(ck, "E004", "a vector element cannot be an array", el)
            return nothing
        elseif t.kind == :Bool
            _report!(ck, "E004", "a `Vec` holds Real values; Bool is not allowed", el)
            return nothing
        end
    end
    return TypeSpec(:Vec, (length(e.elements),))
end

function _check_matrix!(ck::Checker, e::MatrixLit)::Union{TypeSpec,Nothing}
    for row in e.rows, el in row
        t = _check_expr!(ck, el)
        t === nothing && return nothing
        if is_array_type(t)
            _report!(ck, "E004", "a matrix element cannot be an array", el)
            return nothing
        elseif t.kind == :Bool
            _report!(ck, "E004", "a `Mat` holds Real values; Bool is not allowed", el)
            return nothing
        end
    end
    return TypeSpec(:Mat, (length(e.rows), length(e.rows[1])))
end

function _check_ifelse!(ck::Checker, e::IfElse)::Union{TypeSpec,Nothing}
    c = _check_cond!(ck, e.cond)
    if c !== nothing && c.kind != :Bool
        _report!(
            ck,
            "E004",
            "`ifelse` condition must be Bool, got `$(type_name(c))`",
            e.cond;
            hint = "write a comparison, e.g. `ifelse(x > 0, a, b)`",
        )
    end
    a = _check_expr!(ck, e.then)
    b = _check_expr!(ck, e.otherwise)
    (a === nothing || b === nothing) && return nothing
    if assignable(a, b)
        return a
    elseif assignable(b, a)
        return b
    end
    _report!(
        ck,
        "E004",
        "`ifelse` branches have different types: `$(type_name(a))` and `$(type_name(b))`",
        e;
    )
    return nothing
end

function _check_comparison!(ck::Checker, e::Comparison)::Union{TypeSpec,Nothing}
    a = _check_expr!(ck, e.lhs)
    b = _check_expr!(ck, e.rhs)
    if !_cond_ok(ck)
        _report!(
            ck,
            "E001",
            "comparisons are only allowed inside `ifelse` in @equations",
            e;
            hint = "write `ifelse(a < b, x, y)`, or use the comparison in `@discrete`",
        )
    end
    if a !== nothing && b !== nothing
        if a.kind == :Bool && b.kind == :Bool
            if e.op === Symbol("==") || e.op === Symbol("!=")
                return BOOL
            end
            _report!(ck, "E004", "order comparisons need numbers, not Bool"; e)
            return BOOL
        end
        if !_numeric(a) || !_numeric(b)
            _report!(
                ck,
                "E004",
                "cannot compare `$(type_name(a))` and `$(type_name(b))`",
                e;
            )
            return nothing
        end
        if !(a.kind == b.kind || (a.kind == :Int && b.kind == :Real) ||
             (a.kind == :Real && b.kind == :Int))
            _report!(
                ck,
                "E004",
                "cannot compare `$(type_name(a))` and `$(type_name(b))`",
                e;
            )
        end
    end
    return BOOL
end

function _check_boolop!(ck::Checker, e::BoolOp)::Union{TypeSpec,Nothing}
    if !_cond_ok(ck)
        _report!(
            ck,
            "E001",
            "`$(e.op)` is only allowed inside `ifelse` in @equations",
            e;
            hint = "write `ifelse(cond1 && cond2, a, b)`, or use logic in `@discrete`",
        )
    end
    for operand in e.operands
        t = _check_expr!(ck, operand)
        if t !== nothing && t.kind != :Bool
            _report!(
                ck,
                "E004",
                "`$(e.op)` needs Bool operands, got `$(type_name(t))`",
                operand,
            )
        end
    end
    return BOOL
end

# ---------------------------------------------------------------------------------------
# block_interface (plan 3.2)
# ---------------------------------------------------------------------------------------

"""
    block_dimension(pb::ParsedBlock) -> Union{Int,Nothing}

The model dimension encoded by the block's ports (D-MB12): `2` when it has a Planar port,
`3` when it has a Spatial port, and `nothing` for a scalar block or a block that mixes the
two (which `check_block` reports as E102). This is the catalog's and block interface's
`dimension`.
"""
function block_dimension(pb::ParsedBlock)
    planar = false
    spatial = false
    for d in ports(pb)
        dom = type_domain(d.type)
        dom === :Planar && (planar = true)
        dom === :Spatial && (spatial = true)
    end
    planar && spatial && return nothing
    spatial && return 3
    planar && return 2
    return nothing
end

function _const_value(d::Decl, consts::AbstractDict)
    if d.default !== nothing
        ok, value = try_eval_const(d.default, consts)
        ok && (value isa Number || value isa Bool || value isa AbstractArray) && return value
    end
    return something(d.default_text, "")
end

_type_string(t::TypeSpec) = String(type_element(t))

function _size_of(t::TypeSpec, consts::AbstractDict)
    sz = type_size(t, consts)
    return sz === nothing ? Int[] : sz
end

"""
    block_interface(pb::ParsedBlock) -> NamedTuple

The catalog interface of plan 3.2 and `contracts/schemas/catalog.schema.json`:
`constants, parameters, inputs, outputs, ports, variables, causality`. Each entry is a
`Vector` of `NamedTuple`s with exactly the schema fields, so J1.3 can put it straight into
`catalog.get`.

Sizes are the default expansion of the block's structural constants (`Vec{N}` with `N = 2`
gives `[2]`); an unresolvable size gives `[]` here and E005 from `check_block`.
`type` is the scalar element type (`Real` for `Vec`/`Mat`, per the schema).
"""
function block_interface(pb::ParsedBlock)
    consts = constant_env(pb)

    constants = [
        (
            name = String(d.name),
            type = _type_string(d.type),
            default = _const_value(d, consts),
            structural = get(d.attrs, :structural, false) === true,
        ) for d in get(pb.declaration_map, :constants, Decl[])
    ]

    parameters = [
        (
            name = String(d.name),
            type = _type_string(d.type),
            default = something(d.default_text, ""),
            unit = get(d.attrs, :unit, nothing),
            min = get(d.attrs, :min, nothing),
            max = get(d.attrs, :max, nothing),
            tunable = get(d.attrs, :tunable, false) === true,
            description = something(get(d.attrs, :description, nothing), ""),
            options = get(d.attrs, :options, nothing),
        ) for d in get(pb.declaration_map, :parameters, Decl[])
    ]

    io_entries(scope) = [
        (
            name = String(d.name),
            type = _type_string(d.type),
            size = _size_of(d.type, consts),
            unit = get(d.attrs, :unit, nothing),
        ) for d in get(pb.declaration_map, scope, Decl[])
    ]

    port_entries = [
        (
            name = String(d.name),
            domain = String(something(type_domain(d.type), :Generic)),
            size = domain_size(type_domain(d.type)) == 1 ? Int[] :
                   Int[domain_size(type_domain(d.type))],
            frame = get(d.attrs, :frame, nothing),
        ) for d in get(pb.declaration_map, :ports, Decl[])
    ]

    variables = [
        let st = get(d.attrs, :state, nothing)
            (
                name = String(d.name),
                type = _type_string(d.type),
                size = _size_of(d.type, consts),
                unit = get(d.attrs, :unit, nothing),
                start = something(d.default_text, ""),
                state = st === nothing ? nothing : String(st),
            )
        end for d in get(pb.declaration_map, :variables, Decl[])
    ]

    causality_entries = [
        (
            ports = String[String(p) for p in c.ports],
            kind = String(c.kind),
            value = c.value === nothing ? nothing : String(c.value),
        ) for c in pb.causality_items
    ]

    iface = (
        constants = constants,
        parameters = parameters,
        inputs = io_entries(:inputs),
        outputs = io_entries(:outputs),
        ports = port_entries,
        variables = variables,
        causality = causality_entries,
    )
    # `dimension` is optional and the schema's enum is `2 | 3` (no null), so a scalar block
    # omits it; a multibond block reports the model dimension (D-MB12).
    dimension = block_dimension(pb)
    return dimension === nothing ? iface : merge(iface, (dimension = dimension,))
end

"""
    block_equations(pb::ParsedBlock) -> Vector{Any}

The checked equation AST: the `@equations` items (`Equation`, `IfEquation`, `ForEquation`)
when `check_block` reports no error, and an empty vector otherwise. Warnings (W204, and the
block-level E103) do not suppress the equations.
"""
function block_equations(pb::ParsedBlock)
    for d in check_block(pb)
        d.severity == "error" && return Any[]
    end
    return Any[pb.equation_items...]
end

"""
    block_initial_equations(pb::ParsedBlock) -> Vector{Any}

The checked `@initial` AST: the `@initial` items when `check_block` reports no error, and an
empty vector otherwise. Warnings do not suppress them. Kept separate from
[`block_equations`](@ref) because initial equations are solved once before `t = 0` and do not
take part in the balance count.
"""
function block_initial_equations(pb::ParsedBlock)
    for d in check_block(pb)
        d.severity == "error" && return Any[]
    end
    return Any[pb.initial_items...]
end
