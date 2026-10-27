# The flattening pipeline (plan 5.2): the entry point of work package J1.4.
#
# `BGSim.jl` includes exactly this file. It loads the two IR modules (`BGSim.IR` for the
# parsed model document, `BGSim.Flat` for the flattened model), then defines the `Compile`
# module with the passes in the order the plan prescribes:
#
#   1. instantiate   resolve blocks, bind constants, expand subsystems, create variables,
#                    bind parameters/starts, flatten the block equations (5.2.1 - 5.2.4);
#   2. connect       check the connection kinds, build wire nodes and junction bonds (5.5);
#   3. domains       adopt one domain per bond island and wire node, report W205 (5.6);
#   4. units         substitute the adopted domain's units and compute `unitFactors` (5.3);
#   5. connections   emit the wire, bond and signal equations (5.5);
#   6. junctions     emit the 0/1-junction constraints (5.4);
#   7. unconnected   E101 for a port, input or junction with no connection (5.2.6);
#   8. balance       E103, ranking the instances by local imbalance (5.2.7);
#   9. causality     SCAP, the causal strokes and W201/W202/E106 (5.7).
#
# The discrete pass (`collect_discrete!`, plan 5.9) runs right after `collect_events!`: it
# qualifies the `@discrete` scopes, moves the held outputs to the parameter list (D4), reports
# E104/E105 and fixes the topological tick order.
#
# `model_check` returns exactly the plan 3.6 `model.check` result, including the causal
# strokes the causality pass returns. `stats` carries all counts on the `FlatModel`, while
# the contract result keeps only the two fields `contracts/schemas/worker-rpc.schema.json`
# allows (`states`, `equations`).

include(joinpath(@__DIR__, "..", "ir", "blockdef.jl"))
include(joinpath(@__DIR__, "..", "ir", "flat.jl"))

"""
    Compile

Flattening and the model-level checks (plan sections 5.2, 5.4, 5.5, 5.6).

| function | result |
| --- | --- |
| [`flatten`](@ref)`(md; project_dir)` | the [`BGSim.Flat.FlatModel`](@ref) |
| [`model_check`](@ref)`(md; project_dir)` | the plan 3.6 `model.check` result |
| [`check_block_source`](@ref)`(text; ref)` | the plan 3.6 `block.check` result |
"""
module Compile

using ..BGSim
import ..BGSim: Name, Field, Lit, Call, BinOp, UnOp, Index, VectorLit, MatrixLit, IfElse,
    Comparison, BoolOp, Equation, IfEquation, ForEquation, EqBranch, try_eval_const,
    eval_const, ConstFoldError, constant_env, type_scalar_count, parse_block, check_block,
    block_interface, block_equations, block_diagnostics, declarations, equations, ports,
    decl_name, decl_type, decl_default, decl_attrs, decl_scope, decl_range,
    decl_default_text, expr_range, source_range, type_element, type_domain, type_size,
    domain_size, resolve_type, diag, sort_diagnostics, source_kind, SourceRange, SourceRef,
    Diagnostic, Related, ParsedBlock, Decl, TypeSpec, type_kind, type_name, severity_of
import ..BGSim.Units
import ..BGSim.Units: Dims
import ..BGSim.Library
import ..BGSim.IR
import ..BGSim.Flat

include("instantiate.jl")
include("connect.jl")
include("domains.jl")
include("junctions.jl")
include("balance.jl")
include("causality.jl")
include("events.jl")
include("discrete.jl")

# ---------------------------------------------------------------------------------------
# The recording list (plan 3.5, D15)
# ---------------------------------------------------------------------------------------

function _push_var_signal!(out::Vector{NamedTuple}, b::Builder, id::String)
    v = var_by_id(b, id)
    if v !== nothing
        push!(out, Flat.signal_namedtuple(v))
        return nothing
    end
    # A held discrete output is an MTK parameter (D4), not an unknown; it is still recorded,
    # with the plan 3.5 kind `"discrete"`.
    if haskey(b.param_index, id)
        push!(out, discrete_signal_namedtuple(b.params[b.param_index[id]]))
    end
    return nothing
end

"""    model_signals(b) -> (signals, derived)

Every recorded signal in recording order (D15): the variables, inputs and outputs of each
instance in declaration order, then for every power port its `e`, its `f` and the derived
power `e*f`. Port fields are kept together so the signal browser shows a port as one group.
Junction-to-junction virtual bond variables are not instance ports and are not recorded."""
function model_signals(b::Builder)
    out = NamedTuple[]
    derived = Flat.DerivedSignal[]
    for st in b.states
        for scope in (:variables, :inputs, :outputs)
            for d in BGSim.declarations(st.pb, scope)
                for id in get(st.ids, BGSim.decl_name(d), String[])
                    _push_var_signal!(out, b, id)
                end
            end
        end
        for d in BGSim.ports(st.pb)
            port = get(st.ports, BGSim.decl_name(d), nothing)
            port === nothing && continue
            for id in port.eids
                _push_var_signal!(out, b, id)
            end
            for id in port.fids
                _push_var_signal!(out, b, id)
            end
            power = get(b.power_signals, port.qname * ".P", nothing)
            if power !== nothing
                push!(out, Flat.signal_namedtuple(power))
                push!(derived, power)
            end
        end
    end
    # Composite observables (J2.6b): recording aliases at the composite's own path. They are
    # derived signals (one equation each), so they add no state and no reported equation.
    for d in b.observed
        push!(out, Flat.signal_namedtuple(d))
        push!(derived, d)
    end
    return out, derived
end

# ---------------------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------------------

"""    flatten(md::IR.ModelDoc; project_dir = nothing) -> FlatModel

Flatten a model document into the plan 5.1 flat model. The function is total for user
errors: every problem the model can have becomes a `Diagnostic` on the result (and the
partial model is still returned, so the editor can colour what it can). A bug in this code
throws; `model_check` turns that into E900 with the exception message in the hint.
"""
function flatten(md::IR.ModelDoc; project_dir = nothing)
    return first(_flatten(md; project_dir = project_dir))
end

"""    _flatten(md; project_dir) -> (FlatModel, CausalityMap)

The one flattening run. It returns the flat model *and* the causal strokes, because the
strokes are editor metadata that `model_check` returns and `FlatModel` deliberately does not
carry (J2.4 keeps the plan 5.1 shape)."""
function _flatten(md::IR.ModelDoc; project_dir = nothing)
    b = Builder(md, project_dir === nothing ? nothing : String(project_dir))
    instantiate!(b)
    events = collect_events!(b)
    discrete = collect_discrete!(b)
    plan = classify_connections!(b)
    domains = resolve_domains!(b, plan)
    unit_factors = apply_domains!(b, plan)
    emit_connections!(b, plan)
    emit_junction_equations!(b)
    check_unconnected!(b, plan)
    instances = build_instances!(b, plan)
    check_balance!(b, instances)
    causality = analyze_causality!(b, plan)
    signals, derived = model_signals(b)
    diagnostics = sort_diagnostics(b.diagnostics)
    states = count(v -> v.kind === :state, b.vars)
    stats = (
        states = states,
        equations = length(b.equations),
        unknowns = length(b.vars),
        nodes = b.nodes_total,
        connections = b.conns_total,
        instances = length(b.states),
        junctions = length(b.junctions),
        parameters = length(b.params),
        signals = length(signals),
    )
    model = Flat.FlatModel(
        md.name,
        b.vars,
        b.params,
        b.equations,
        Flat.FlatEq[],
        events,
        discrete,
        b.junctions,
        connection_infos(plan),
        instances,
        domains,
        unit_factors,
        derived,
        signals,
        diagnostics,
        stats,
    )
    return model, causality
end

flatten(source::AbstractString; project_dir = nothing) =
    flatten(IR.parse_model(source); project_dir = project_dir)
flatten(doc::AbstractDict; project_dir = nothing) =
    flatten(IR.parse_model(doc); project_dir = project_dir)

"""    model_check(md::IR.ModelDoc; project_dir = nothing) -> NamedTuple

The plan 3.6 `model.check` result:

    (diagnostics, domains, causality, unitFactors, signals, stats)

`domains` maps a power connection id to the adopted domain name (plan 5.6), `unitFactors`
maps a connection id to the factor the compiler inserts (plan 5.3), and `signals` is the plan
3.5 recording list. `causality` maps a bond connection id to `(strokeAt = "from" | "to",)`,
the end where effort is the input to the element there (plan 5.7); it is empty for a model
with no bonds.

`stats` contains exactly the two fields the worker contract allows (`states`, `equations`);
the full counts are on `flatmodel.stats`.
"""
function model_check(md::IR.ModelDoc; project_dir = nothing)
    fm, causality = try
        _flatten(md; project_dir = project_dir)
    catch err
        message = "internal compiler error while flattening `$(md.name)`"
        d = diag("E900", message; hint = sprint(showerror, err))
        (
            Flat.empty_model(md.name; diagnostics = [d], stats = (states = 0, equations = 0)),
            CausalityMap(),
        )
    end
    return (
        diagnostics = fm.diagnostics,
        domains = fm.domains,
        causality = causality,
        unitFactors = fm.unit_factors,
        signals = fm.signals,
        stats = (states = fm.stats.states, equations = fm.stats.equations),
    )
end

model_check(source::AbstractString; project_dir = nothing) =
    model_check(IR.parse_model(source); project_dir = project_dir)
model_check(doc::AbstractDict; project_dir = nothing) =
    model_check(IR.parse_model(doc); project_dir = project_dir)

"""    check_block_source(text; ref = "inline:x") -> NamedTuple

The plan 3.6 `block.check` result: the block's diagnostics, plus its catalog interface when
the source has no error (`nothing` when it has one, as the worker contract requires). The
heavy lifting is the J1.1 front end and the J1.3 block cache; this entry point exists so the
worker has one function per RPC method.
"""
function check_block_source(text::AbstractString; ref::AbstractString = "inline:x")
    block = Library.load_block(text; ref = ref)
    bad = any(d -> d.severity == "error", block.diagnostics)
    return (diagnostics = block.diagnostics, interface = bad ? nothing : block.interface)
end

export flatten, model_check, check_block_source

end # module Compile
