# Export scope: export one subsystem instead of the whole model (plan/EXPORT_PLAN.md J-EX11).
#
# The scope is a model-document transform that runs before flattening. The selected
# subsystem node becomes the only node of a new root diagram, and every port it exposes gets
# an export marker:
#   * a signal input port  -> an `ExportInput` named after the port;
#   * a signal output port -> an `ExportOutput` named after the port;
#   * a scalar power port  -> an adapter that imposes the chosen variable (effort or flow)
#     from an `ExportInput` `<port>_e`/`<port>_f` and measures the conjugate into an
#     `ExportOutput` `<port>_f`/`<port>_e`. The flow is the flow into the subsystem in both
#     directions. The adapter replaces the outside of the port with the same connection kind
#     and orientation as in the original model.
# Everything outside the subsystem (test harness, CSV sources, plots, the scene) is dropped,
# so unsupported elements can stay in the model as long as they sit outside the scope.
# Export markers inside the subsystem stay valid; their names gain the subsystem's prefix.

const _SCOPE_DOMAINS = ("Generic", "Electrical", "Translation", "Rotation", "Hydraulic")

_scope_err(message; hint = nothing, path = nothing) =
    diag("E112", message; hint = hint, path = path, scope = "export")

function _scope_node(diagram, name)
    for n in get(diagram, "nodes", Any[])
        String(n["name"]) == name && return n
    end
    return nothing
end

# The interface flow is the flow *into the subsystem*, so `<port>_e * <port>_f` is the power
# the subsystem absorbs. Port variables count power into their own element, so the adapter's
# flow has the opposite sign; the effort is shared.
function _adapter_source(domain, imposed)
    imposes, measures = imposed === :effort ? ("p.e ~ u", "y ~ -p.f") : ("p.f ~ -u", "y ~ p.e")
    causality = imposed === :effort ? ":effort_out" : ":flow_out"
    return """
    @block ScopeAdapter_$(domain)_$(imposed === :effort ? "e" : "f") begin
        @ports p::Power{$domain}
        @inputs u::Real
        @outputs y::Real
        @equations begin
            $imposes
            $measures
        end
        @causality p => ($causality, :fixed)
    end
    """
end

_scope_marker(id, name, ref; value = nothing) = Dict{String,Any}(
    "id" => id, "name" => name, "block" => Dict{String,Any}("ref" => ref),
    "params" => value === nothing ? Dict{String,Any}() :
                Dict{String,Any}("value" => repr(Float64(value))))

_scope_ep(node, port) = Dict{String,Any}("node" => node, "port" => port)

_scope_conn(id, kind, from, to) =
    Dict{String,Any}("id" => id, "kind" => kind, "from" => from, "to" => to)

"""    scope_document(doc, path; power_inputs = Dict(), input_values = Dict()) -> (doc, diagnostics)

The model document `doc` (a parsed `.bgmodel.json`) reduced to the subsystem at the instance
path `path` (`"Plant"`, `"Plant/Drive"`), with export markers on its ports.
`power_inputs[port]` is `"effort"` or `"flow"`: the variable the host imposes on a power port
(required for each power port). `input_values[port]` is the start value of an input
(default 0). Returns `(nothing, diagnostics)` with E112 when the scope cannot be built."""
function scope_document(doc::AbstractDict, path::AbstractString;
                        power_inputs = Dict{String,Any}(), input_values = Dict{String,Any}())
    segments = split(String(path), "/")
    diagram = doc["diagram"]
    node = nothing
    for (k, seg) in enumerate(segments)
        node = _scope_node(diagram, seg)
        where = join(segments[1:k], "/")
        node === nothing && return nothing, [_scope_err("the export scope `$path` does not exist";
            hint = "no instance `$where` in the model", path = where)]
        haskey(node["block"], "subsystem") || return nothing, [_scope_err(
            "the export scope `$where` is not a subsystem";
            hint = "select a subsystem; a library block can be wrapped in one", path = where)]
        k < length(segments) && (diagram = node["block"]["subsystem"]["diagram"])
    end
    parent = diagram                                   # the diagram that holds `node`
    id = String(node["id"])
    nodes = Any[deepcopy(node)]
    conns = Any[]
    diags = Diagnostic[]
    taken = Set{String}([String(node["name"])])
    function fresh(base)
        candidate, j = base, 1
        while candidate in taken
            j += 1
            candidate = "$(base)_$j"
        end
        push!(taken, candidate)
        return candidate
    end

    for p in get(node["block"]["subsystem"], "ports", Any[])
        pname = String(p["name"])
        kind = String(get(p, "kind", "signal"))
        here = String(path) * "/" * pname
        start = get(input_values, pname, 0.0)
        if kind == "signal"
            dir = String(get(p, "direction", "input"))
            size = get(p, "size", Any[1])
            prod(Int.(size); init = 1) == 1 || (push!(diags, _scope_err(
                "the vector signal port `$pname` cannot be an export interface yet";
                hint = "export a scalar signal (a Select block inside the subsystem)", path = here)); continue)
            mid = "scope_" * pname
            if dir == "input"
                push!(nodes, _scope_marker(mid, fresh(pname), MARKER_INPUT; value = start))
                push!(conns, _scope_conn("scope_c_" * pname, "signal", _scope_ep(mid, "y"), _scope_ep(id, pname)))
            else
                push!(nodes, _scope_marker(mid, fresh(pname), MARKER_OUTPUT))
                push!(conns, _scope_conn("scope_c_" * pname, "signal", _scope_ep(id, pname), _scope_ep(mid, "u")))
            end
        elseif kind == "power"
            domain = String(something(get(p, "domain", nothing), "Generic"))
            size = get(p, "size", Any[1])
            if !(domain in _SCOPE_DOMAINS) || prod(Int.(size); init = 1) != 1
                push!(diags, _scope_err("the power port `$pname` ($domain) cannot be an export interface yet";
                    hint = "only scalar Electrical, Translation, Rotation, Hydraulic or generic bond ports", path = here))
                continue
            end
            choice = get(power_inputs, pname, nothing)
            if !(choice in ("effort", "flow"))
                push!(diags, _scope_err("the power port `$pname` needs the variable the host imposes";
                    hint = "set power_inputs[\"$pname\"] to \"effort\" or \"flow\"", path = here))
                continue
            end
            imposed = Symbol(choice)
            # The outside connection of this port in the original model: its kind and which
            # end the subsystem is (a bond's orientation is the power direction).
            outside = nothing
            for c in get(parent, "connections", Any[])
                for (side, other) in (("from", "to"), ("to", "from"))
                    ep = c[side]
                    if String(ep["node"]) == id && String(get(ep, "port", "")) == pname
                        outside = (kind = String(c["kind"]), sub_is = side)
                        break
                    end
                end
                outside === nothing || break
            end
            ckind = outside === nothing ? (domain == "Generic" ? "bond" : "wire") : outside.kind
            aid = "scope_a_" * pname
            push!(nodes, Dict{String,Any}("id" => aid, "name" => fresh(pname * "_port"),
                "block" => Dict{String,Any}("inline" => Dict{String,Any}("source" => _adapter_source(domain, imposed)))))
            sub_ep, a_ep = _scope_ep(id, pname), _scope_ep(aid, "p")
            push!(conns, outside !== nothing && outside.sub_is == "from" ?
                _scope_conn("scope_c_" * pname, ckind, sub_ep, a_ep) :
                _scope_conn("scope_c_" * pname, ckind, a_ep, sub_ep))
            iname, oname = imposed === :effort ? (pname * "_e", pname * "_f") : (pname * "_f", pname * "_e")
            iid, oid = "scope_i_" * pname, "scope_o_" * pname
            push!(nodes, _scope_marker(iid, fresh(iname), MARKER_INPUT; value = start))
            push!(nodes, _scope_marker(oid, fresh(oname), MARKER_OUTPUT))
            push!(conns, _scope_conn("scope_ci_" * pname, "signal", _scope_ep(iid, "y"), _scope_ep(aid, "u")))
            push!(conns, _scope_conn("scope_co_" * pname, "signal", _scope_ep(aid, "y"), _scope_ep(oid, "u")))
        else
            push!(diags, _scope_err("the port `$pname` has an unknown kind `$kind`"; path = here))
        end
    end
    isempty(diags) || return nothing, diags
    out = Dict{String,Any}(k => deepcopy(v) for (k, v) in doc if !(k in ("diagram", "plots", "bindings", "scene")))
    out["name"] = String(get(doc, "name", "model")) * "_" * replace(String(path), "/" => "_")
    out["diagram"] = Dict{String,Any}("nodes" => nodes, "connections" => conns)
    return out, diags
end
