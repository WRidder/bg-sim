# Model-level balance (plan 5.2.7, E103).
#
# The global count is `#unknowns` (every scalar variable, input, output and port field) versus
# `#equations` (every flattened block equation, wire node equation, element bond equation,
# signal equation and junction constraint). A complete model balances exactly; the four
# fixtures in `contracts/fixtures/model/valid/` do (see the WP report for the measured
# counts).
#
# When it does not balance the plan asks for the *worst block* to be named. The heuristic
# here is the per-instance share of the global count: an instance contributes
# `2*ports + variables + inputs + outputs - block_equations` to the unknown minus equation
# total, and each of its attached connections contributes one equation to it (a wire node of
# `k` ports has `k` equations shared by `k` ports; an element bond has two shared by two; a
# junction has one per bond; a signal has one per input). So
#
#     local = unknowns - block_equations - connected_ports - connected_inputs
#
# is zero for every instance of a balanced model and names the block that carries the
# surplus. That is a ranking, not a proof: the message always reports the true global
# counts, and the hint names the worst instance.
#
# E103 is suppressed when another model error (E00x, E101, E102, E900) was reported: those
# errors remove or add equations, so the counts would only be a cascade.

function _connected_sets(plan::ConnPlan)
    ports = Set{Tuple{String,Symbol}}()
    inputs = Set{Tuple{String,Symbol}}()
    for state in plan.states
        state.valid || continue
        if state.conn.kind == :bond || state.conn.kind == :wire
            state.from.kind == :power && push!(ports, _portkey(state.from))
            state.to.kind == :power && push!(ports, _portkey(state.to))
        elseif state.conn.kind == :signal
            push!(inputs, _portkey(state.to))
        end
    end
    return ports, inputs
end

"""    build_instances!(b, plan) -> Vector{InstanceInfo}

The per-instance counts, in instantiation order. `connected_ports`/`connected_inputs` count
the ports and inputs that ended up attached to a *valid* connection, which is what the
balance ranking shares the connection equations over."""
function build_instances!(b::Builder, plan::ConnPlan)
    connected_ports, connected_inputs = _connected_sets(plan)
    out = Flat.InstanceInfo[]
    for st in b.states
        nvars = 0
        for d in BGSim.declarations(st.pb, :variables)
            nvars += length(get(st.ids, BGSim.decl_name(d), String[]))
        end
        ninputs = 0
        for d in BGSim.declarations(st.pb, :inputs)
            ninputs += length(get(st.ids, BGSim.decl_name(d), String[]))
        end
        noutputs = 0
        for d in BGSim.declarations(st.pb, :outputs)
            noutputs += length(get(st.ids, BGSim.decl_name(d), String[]))
        end
        nports = length(st.ports)
        cports = 0
        for (name, _) in st.ports
            _portkey(st.path, name) in connected_ports && (cports += 1)
        end
        cinputs = count(
            d -> _portkey(st.path, BGSim.decl_name(d)) in connected_inputs,
            BGSim.declarations(st.pb, :inputs),
        )
        push!(
            out,
            Flat.InstanceInfo(
                st.path,
                st.node,
                st.ref,
                nvars,
                ninputs,
                noutputs,
                nports,
                st.eq_count,
                st.var_count,
                cports,
                cinputs,
            ),
        )
    end
    return out
end

function _local_imbalance(info::Flat.InstanceInfo)
    return info.unknowns - info.equations - info.connected_ports - info.connected_inputs
end

function _blocking_error(diagnostics::Vector{Diagnostic})
    for d in diagnostics
        d.severity == "error" || continue
        (startswith(d.code, "E00") || d.code in ("E101", "E102", "E900")) && return true
    end
    return false
end

function _plural(n::Int, one::String, many::String)
    return n == 1 ? one : many
end

"""    check_balance!(b, instances)

Add the model-level E103 when the flat counts differ. The message is always the plan 5.2.7
form `unbalanced system: N unknowns, M equations`; the hint and `path`/`node` name the
instance with the largest `|local|` and the `related` list carries the three largest."""
function check_balance!(b::Builder, instances::Vector{Flat.InstanceInfo})
    unknowns = length(b.vars)
    equations = length(b.equations)
    unknowns == equations && return nothing
    _blocking_error(b.diagnostics) && return nothing
    if isempty(instances)
        push!(
            b.diagnostics,
            diag(
                "E103",
                "unbalanced system: $unknowns unknowns, $equations equations";
                hint = "the model has no instances to rank",
            ),
        )
        return nothing
    end
    ranked = sort(instances; by = i -> (-abs(_local_imbalance(i)), i.path))
    worst = ranked[1]
    worst_local = _local_imbalance(worst)
    hint = if worst_local > 0
        "`$(worst.path)` has $(worst_local) extra $(_plural(worst_local, "unknown", "unknowns"))"
    elseif worst_local < 0
        "`$(worst.path)` has $(-worst_local) extra $(_plural(-worst_local, "equation", "equations"))"
    else
        "the imbalance is spread over the model"
    end
    related = Related[]
    for info in ranked
        local_i = _local_imbalance(info)
        local_i == 0 && continue
        push!(
            related,
            Related(
                info.path,
                string(abs(local_i), " extra ", _plural(abs(local_i), "unknown", "unknowns")),
            ),
        )
        length(related) >= 3 && break
    end
    push!(
        b.diagnostics,
        diag(
            "E103",
            "unbalanced system: $unknowns $(_plural(unknowns, "unknown", "unknowns")), " *
            "$equations $(_plural(equations, "equation", "equations"))";
            hint = hint,
            path = worst.path,
            block = worst.ref,
            node = worst.node,
            related = related,
        ),
    )
    return nothing
end
