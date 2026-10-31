# Pass-through export inputs (plan/EXPORT_PLAN.md X-EX1, D-EX9).
#
# `stdlib:converters/ExportInputPass` is an export input that is inert in simulation: it
# passes its wired input through (`y = u`), so a model keeps its own stimulus (a Step, a
# Chirp) and simulates exactly as without the marker. In the export the host supplies the
# signal instead: `host_inputs(flat)` replaces the marker's equation `y ~ u` by `y ~ value`,
# so `value` becomes the FMU input exactly like an `ExportInput`'s, and the wire into `u` is
# cut (its source is still computed and recorded, but nothing reads it). The transform is
# what `export_model` compiles; a reference run that must match the FMU (the export job, the
# X-EX0/X-EX1 gate) simulates the same transformed model, driven through
# `simulate(...; inputs)` if it is not left at the start values.

const MARKER_INPUT_PASS = "stdlib:converters/ExportInputPass"

"""    input_markers(flat) -> Vector{String}

The instance paths of every export input marker (`ExportInput` and `ExportInputPass`), in
model order. A path is also the FMI name of the input; its parameter is `<path>/value`."""
input_markers(flat::Flat.FlatModel) =
    String[i.path for i in flat.instances if i.ref == MARKER_INPUT || i.ref == MARKER_INPUT_PASS]

"""    host_inputs(flat) -> FlatModel

`flat` with every pass-through export input (`ExportInputPass`) switched to its exported
form `y = value`. Returns `flat` itself when there is nothing to switch (so the transform is
idempotent). The structure changes, so the result has its own `compile_key`."""
function host_inputs(flat::Flat.FlatModel)
    passes = Set(String[i.path for i in flat.instances if i.ref == MARKER_INPUT_PASS])
    isempty(passes) && return flat
    eqs = copy(flat.equations)
    changed = false
    for (k, e) in enumerate(eqs)
        o = e.origin
        (o.kind === :block && o.path !== nothing && o.path in passes) || continue
        e.lhs isa BGSim.Name && e.lhs.name === Symbol(o.path * "/y") || continue
        e.rhs isa BGSim.Name && e.rhs.name === Symbol(o.path * "/u") || continue
        eqs[k] = Flat.FlatEq(e.lhs, BGSim.Name(Symbol(o.path * "/value"), e.rhs.range), o)
        changed = true
    end
    changed || return flat
    return Flat.FlatModel((f === :equations ? eqs : getfield(flat, f)
                           for f in fieldnames(Flat.FlatModel))...)
end
