# Shared helpers for the bond-graph golden tests (work package J2.7a).
#
# The file name does not start with `test_`, so the `test/golden/**/test_*.jl` walk in
# `test/runtests.jl` does not pick it up on its own; every golden test file includes it.
# Everything here drives the **real pipeline** (`IR.parse_model` → `Compile.flatten` →
# `simulate`) and never hand-writes an MTK system, so a golden test proves that the block
# compiles and simulates, not only that its equations look right.
module BondGraphGolden

using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import JSON3

export bg_node, bg_ref, bg_junction, bg_conn, bg_model, bg_run, bg_value, bg_all

"""    bg_node(id, name, block; params = Dict(), starts = Dict()) -> Dict

One diagram node of a model document (plan 3.3). `block` is the `block` field, i.e.
[`bg_ref`](@ref) for a stdlib block, [`bg_junction`](@ref) for a junction, or
`Dict("inline" => Dict("source" => text))` for an inline block."""
function bg_node(id, name, block; params = Dict{String,Any}(), starts = Dict{String,Any}())
    return Dict{String,Any}(
        "id" => String(id),
        "name" => String(name),
        "block" => block,
        "position" => Dict{String,Any}("x" => 0.0, "y" => 0.0),
        "params" => params,
        "constants" => Dict{String,Any}(),
        "starts" => starts,
    )
end

"""    bg_ref(ref) -> Dict

The `block` field of a node that instantiates the stdlib block `ref` (plan 3.1)."""
bg_ref(ref) = Dict{String,Any}("ref" => String(ref))

"""    bg_junction(kind) -> Dict

The `block` field of a node that is a `kind`-junction (`0` or `1`)."""
bg_junction(kind) = Dict{String,Any}("junction" => string(kind))

"""    bg_conn(id, kind, from_node, from_port, to_node, to_port) -> Dict

One connection of a model document. An omitted port (`nothing`) is a junction end."""
function bg_conn(id, kind, from_node, from_port, to_node, to_port)
    from = Dict{String,Any}("node" => String(from_node))
    from_port === nothing || (from["port"] = String(from_port))
    to = Dict{String,Any}("node" => String(to_node))
    to_port === nothing || (to["port"] = String(to_port))
    return Dict{String,Any}("id" => String(id), "kind" => String(kind), "from" => from,
        "to" => to)
end

"""    bg_model(name, nodes, connections; t_end = 1.0, points = 101) -> Dict

A complete model document (plan 3.3) with the golden-test settings: `Rodas5P`, `reltol`
1e-10, `abstol` 1e-12, `points` equally spaced output points from `t = 0` to `t_end`."""
function bg_model(name, nodes, connections;
    t_start = 0.0, t_end = 1.0, solver = "Rodas5P", reltol = 1.0e-10, abstol = 1.0e-12,
    points = 101)
    return Dict{String,Any}(
        "format" => "bgsim.model",
        "language" => "0.1.0",
        "name" => String(name),
        "diagram" => Dict{String,Any}(
            "nodes" => Any[nodes...],
            "connections" => Any[connections...],
            "subsystemPorts" => Any[],
            "annotations" => Any[],
        ),
        "settings" => Dict{String,Any}(
            "t_start" => t_start,
            "t_end" => t_end,
            "solver" => solver,
            "reltol" => reltol,
            "abstol" => abstol,
            "max_step" => nothing,
            "output" => Dict{String,Any}("mode" => "points", "points" => points),
            "event_limit" => 10000,
        ),
        "plots" => Any[],
        "scene" => nothing,
        "bindings" => Any[],
    )
end

"""    bg_columns(dir) -> Dict{String,Vector{Float64}}

The run's `columns.f64` as `signal id => values`, plus `"time"`; read through the manifest's
signal order, exactly as the web playback does (plan 3.5)."""
function bg_columns(dir)
    manifest = JSON3.read(read(joinpath(dir, "manifest.json"), String))
    n = Int(manifest.time.n)
    nsignals = length(manifest.signals)
    raw = read(joinpath(dir, "columns.f64"))
    @test length(raw) == 8 * n * (nsignals + 1)
    table = reshape(reinterpret(Float64, raw), (n, nsignals + 1))
    columns = Dict{String,Vector{Float64}}("time" => collect(table[:, 1]))
    for (j, signal) in enumerate(manifest.signals)
        columns[String(signal.id)] = collect(table[:, j + 1])
    end
    return columns
end

"""    bg_run(model) -> (columns, result, flat)

Flatten and simulate one model document through the real pipeline. A flatten error raises
with the diagnostics instead of returning a half-empty run; the caller asserts
`result.status == "done"` and the golden values."""
function bg_run(model)
    parsed = IR.parse_model(model)
    flat = Compile.flatten(parsed)
    errors = [d for d in flat.diagnostics if d.severity == "error"]
    if !isempty(errors)
        error(
            "the golden model `$(model["name"])` does not flatten:\n" *
            join(["    $(d.code): $(d.message)" for d in errors], "\n"),
        )
    end
    dir = mktempdir()
    settings = BGSim.RunSettings(parsed.settings)
    result = simulate(flat; run_dir = dir, settings = settings)
    return bg_columns(dir), result, flat
end

"""    bg_value(columns, id, t) -> Float64

The recorded value of signal `id` at the grid time closest to `t` (the output grid is exact,
so this is an equality up to 1e-9, not an interpolation). When the recorder wrote an event
pair at that instant — plan 3.5 stores the left and the right limit at the same `t` — the
**right** limit is returned, which is the value the model has after the switch."""
function bg_value(columns, id, t)
    haskey(columns, id) || error("no recorded signal `$id`")
    i = findlast(x -> abs(x - t) <= 1.0e-9, columns["time"])
    i === nothing && error("no output point at t = $t")
    return columns[id][i]
end

"""    bg_all(columns, id) -> Vector{Float64}

Every recorded value of signal `id`, one per recorded row (event pairs included), aligned
with `columns["time"]`."""
function bg_all(columns, id)
    haskey(columns, id) || error("no recorded signal `$id`")
    return columns[id]
end

end # module
