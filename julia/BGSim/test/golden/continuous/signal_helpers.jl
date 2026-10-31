# Shared helpers for the golden tests of the signal and control blocks (filters, routing,
# nonlinearities, observers, run monitors). The file name does not start with `test_`, so the
# `test/golden/**/test_*.jl` walk in `test/runtests.jl` does not pick it up on its own; each
# golden test file includes it once.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using .BondGraphGolden

"""    sb_node(id, ref; params, consts, starts) -> Dict

A diagram node named `id` for the stdlib block `ref` ("continuous/TransferFunction"), with
its parameter expressions, structural constants and start values."""
function sb_node(id, ref; params = Dict{String,Any}(), consts = Dict{String,Any}(),
    starts = Dict{String,Any}())
    node = bg_node(id, id, bg_ref("stdlib:" * ref); params = Dict{String,Any}(params),
        starts = Dict{String,Any}(starts))
    isempty(consts) || (node["constants"] = Dict{String,Any}(consts))
    return node
end

sb_sine(id, w; amplitude = "1.0") =
    sb_node(id, "sources/Sine"; params = Dict("frequency" => w, "amplitude" => amplitude))
sb_ramp(id, slope, initial) =
    sb_node(id, "sources/Ramp"; params = Dict("slope" => slope, "initial" => initial))
sb_const(id, value) = sb_node(id, "sources/Constant"; params = Dict("value" => value))
sb_step(id) = sb_node(id, "sources/Step"; params = Dict("t_step" => "0.0"))

"""    sb_run(name, nodes, wires; t_end, points) -> (columns, result, flat)

Runs the model through the real pipeline; `wires` are `(from, port, to, port)` signal
connections. The default output grid is every 0.01 s."""
function sb_run(name, nodes, wires; t_end = 1.0, points = round(Int, 100 * t_end) + 1,
    solver = "Rodas5P")
    conns = [bg_conn("c$i", "signal", w...) for (i, w) in enumerate(wires)]
    return bg_run(bg_model(name, nodes, conns; t_end = t_end, points = points, solver = solver))
end

"""    sb_amplitude(columns, id, w, t0) -> Float64

The amplitude of the sinusoid of angular frequency `w` in signal `id` after `t0`, by a least
squares fit of `a·sin(w t) + b·cos(w t) + c` to the recorded rows (exact for a steady state,
unlike the largest sample)."""
function sb_amplitude(columns, id, w, t0)
    t = columns["time"]
    keep = findall(>=(t0), t)
    M = hcat(sin.(w .* t[keep]), cos.(w .* t[keep]), ones(length(keep)))
    a, b, _ = M \ columns[id][keep]
    return hypot(a, b)
end
