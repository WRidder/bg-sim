# Export job (plan/EXPORT_PLAN.md P-EX1, W-EX1): one export request from the editor, from the
# model document to the export directory. The backend runs it in a Julia process of its own
# (`julia/BGSim/export/export_job.jl`), never in the interactive worker: an export can take
# minutes and the worker must keep answering its health ping.
#
# The request is the `ExportRequest` contract (contracts/schemas/export-request.schema.json)
# plus `projectDir`:
#
#   1. scope: `scope_document` when `scope` names a subsystem (E112 refuses a bad scope);
#   2. flatten (a model error refuses the export with the flattener's diagnostics);
#   3. reference run: the model's solver and horizon, tolerances tightened to 1e-6/1e-8,
#      output every communication step, cancelled after `referenceBudgetS` (default 120 s).
#      Its trajectory widens the spectrum scan; without it the scan covers the start point;
#   4. `export_model` with the reference into `<job_dir>/export`.
#
# The result is a Dict: `status` ("exported", "refused" or "failed"), `diagnostics`,
# `timings` (seconds per step), `notes` (plain sentences for the report) and `exportDir`.

const _JOB_SETTINGS = (("method", "method"), ("dt", "dt"), ("step", "step"),
    ("damping", "damping"), ("jacobian", "jacobian"), ("linearSolver", "linear_solver"),
    ("exposeAll", "expose_all"))

_job_dict(x::AbstractDict) = Dict{String,Any}(String(k) => _job_dict(v) for (k, v) in pairs(x))
_job_dict(x::AbstractVector) = Any[_job_dict(v) for v in x]
_job_dict(x) = x

"""    default_step(t_end) -> Float64

The communication step when the request leaves it open: 1 ms, or finer for horizons below
0.5 s (t_end/500 rounded down to a 1-2-5 grid of whole nanoseconds), as the X-EX0 gate does."""
function default_step(t_end::Real)
    t_end >= 0.5 && return 1.0e-3
    target = t_end / 500
    best = 1.0e-9
    for e in -9:-3, m in (1, 2, 5)
        v = m * 10.0^e
        v <= target && (best = v)
    end
    return round(best; sigdigits = 1)
end

"""    job_settings(request_settings, t_end) -> ExportSettings

The request's camelCase settings (`null` = automatic) as `ExportSettings`."""
function job_settings(s::AbstractDict, t_end::Real)
    d = Dict{String,Any}("t_end" => Float64(t_end))
    for (from, to) in _JOB_SETTINGS
        v = get(s, from, nothing)
        v === nothing && continue
        d[to] = v
    end
    haskey(d, "step") || (d["step"] = default_step(t_end))
    # J-EX8 / W-EX1: the tunables editor's picks, each with an optional range, and the
    # "expose all globals" switch.
    tunables = something(get(s, "tunables", nothing), Any[])
    d["tunables"] = String[String(t["id"]) for t in tunables]
    d["ranges"] = Dict{String,Any}(String(t["id"]) => (get(t, "min", nothing), get(t, "max", nothing))
                                   for t in tunables)
    d["expose_globals"] = Bool(something(get(s, "exposeGlobals", nothing), false))
    return ExportSettings(d)
end

_job_diags(ds) = Any[BGSim.to_namedtuple(d) for d in sort_diagnostics(collect(Diagnostic, ds))]

"""    export_job(request, job_dir; progress = phase -> nothing) -> Dict

Run one export request (see the file header). `progress(phase)` is called at the start of
`scope`, `flatten`, `reference` and `export`."""
function export_job(request::AbstractDict, job_dir::AbstractString; progress = _ -> nothing)
    req = _job_dict(request)
    timings = Dict{String,Any}()
    notes = String[]
    out = Dict{String,Any}("timings" => timings, "notes" => notes, "diagnostics" => Any[],
        "exportDir" => joinpath(String(job_dir), "export"))
    refused(ds) = (out["status"] = "refused"; out["diagnostics"] = _job_diags(ds); out)
    doc = req["model"]
    project_dir = get(req, "projectDir", nothing)
    scope = get(req, "scope", nothing)
    scope = scope === nothing || isempty(strip(String(scope))) ? nothing : String(scope)

    if scope !== nothing
        progress("scope")
        t0 = time()
        scoped, ds = scope_document(doc, scope;
            power_inputs = something(get(req, "powerInputs", nothing), Dict{String,Any}()),
            input_values = something(get(req, "inputValues", nothing), Dict{String,Any}()))
        timings["scopeS"] = time() - t0
        scoped === nothing && return refused(ds)
        doc = scoped
    end

    model_settings = something(get(doc, "settings", nothing), Dict{String,Any}())
    t_end = Float64(get(model_settings, "t_end", 1.0))
    es = job_settings(something(get(req, "settings", nothing), Dict{String,Any}()), t_end)
    name = String(get(doc, "name", "model"))

    progress("flatten")
    t0 = time()
    flat = Compile.flatten(IR.parse_model(doc); project_dir = project_dir)
    timings["flattenS"] = time() - t0
    errors = filter(d -> d.severity == "error", flat.diagnostics)
    isempty(errors) || return refused(flat.diagnostics)
    # A CSV source is refused by the export up front (E110); no reference run is needed.
    if any(i -> i.ref in CSV_SOURCES, flat.instances)
        return refused(export_model(flat, out["exportDir"]; settings = es, name = name).diagnostics)
    end

    progress("reference")
    ref_dir = joinpath(String(job_dir), "reference")
    budget = Float64(something(get(req, "referenceBudgetS", nothing), 120.0))
    run_settings = Dict{String,Any}(
        "t_end" => t_end,
        "solver" => String(something(get(model_settings, "solver", nothing), "auto")),
        "reltol" => min(Float64(something(get(model_settings, "reltol", nothing), 1e-6)), 1e-6),
        "abstol" => min(Float64(something(get(model_settings, "abstol", nothing), 1e-8)), 1e-8),
        "output" => Dict{String,Any}("mode" => "interval", "interval" => es.step),
    )
    t0 = time()
    reference = nothing
    try
        BGSim.simulate(flat; run_dir = ref_dir, settings = run_settings,
            cancel = () -> time() - t0 > budget)
        manifest = JSON3.read(read(joinpath(ref_dir, "manifest.json"), String))
        if String(manifest.status) == "done"
            reference = ref_dir
        elseif time() - t0 > budget
            push!(notes, "The reference run did not finish within $(round(Int, budget)) s, so the spectrum was scanned at the start point only.")
        else
            push!(notes, "The reference run failed ($(String(manifest.status))), so the spectrum was scanned at the start point only.")
        end
    catch err
        push!(notes, "The reference run failed ($(first(sprint(showerror, err), 300))), so the spectrum was scanned at the start point only.")
    end
    timings["referenceS"] = time() - t0

    progress("export")
    t0 = time()
    result = export_model(flat, out["exportDir"]; settings = es, reference_dir = reference,
        name = name)
    timings["exportS"] = time() - t0
    result.ok || return refused(result.diagnostics)
    out["status"] = "exported"
    out["diagnostics"] = _job_diags(result.diagnostics)
    return out
end
