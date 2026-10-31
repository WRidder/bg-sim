# Export every example model and run its reference simulation (plan/EXPORT_PLAN.md X-EX1).
#
#   julia --project=julia/BGSim examples/export_examples.jl <out_root> [--resume]
#         [--settings=<json>] [project[/model] ...]
#
# `--resume` appends to an existing results.jsonl and skips the models already in it.
# `--settings` overrides export settings for every model, e.g.
# `{"method": "ros2", "linear_solver": "sparse"}` (see `BGSim.Export.ExportSettings`).
# Before each model, <out_root>/current.json names it; the Python harness uses that to kill
# and log a model that exceeds its time budget, then restarts this script with --resume.
#
# For each model of each example project (or only the ones named):
#   1. flatten it with the example's `expected.json` settings overlay applied;
#   2. export it once without a reference: a refused model (E110/E111/...) stops here;
#   3. run the reference simulation: the model's own solver and horizon, tolerances tightened
#      to at most 1e-6/1e-8, output every communication step, cancelled after
#      BGSIM_EXPORT_REF_BUDGET seconds (default 300; the model is then `reference_timeout`);
#   4. export again with the reference trajectory (the spectrum scan uses it) and
#      `expose_all = true`, so every recorded signal can be compared.
# X-EX1: a model with export input markers is flattened in its exported form
# (`Export.host_inputs`: a pass-through `ExportInputPass` takes its value from the host), and
# its reference run is driven by a deterministic input trajectory (`input_trajectory`, written
# to <model>/inputs.json; zero-order hold at the communication instants, `simulate(...;
# inputs)`), which export_checks.py feeds to the FMU through its inputs. A model with markers
# is also exported without `expose_all` into <model>/export-markers (the deliverable FMU).
# One JSON line per model goes to <out_root>/results.jsonl; `examples/export_checks.py`
# builds the FMUs and compares them with the references.

using BGSim
import JSON3

const EXAMPLES = @__DIR__

function overlay!(target::Dict{String,Any}, over)
    for (k, v) in pairs(over)
        key = String(k)
        if v isa AbstractDict && get(target, key, nothing) isa AbstractDict
            overlay!(target[key], v)
        else
            target[key] = v
        end
    end
    return target
end

todict(x::AbstractDict) = Dict{String,Any}(String(k) => todict(v) for (k, v) in pairs(x))
todict(x::AbstractVector) = Any[todict(v) for v in x]
todict(x) = x

# The communication step: 1 ms, or finer for short horizons (rlc-dual runs 10 ms), on a
# 1-2-5 grid of whole nanoseconds.
function comm_step(t_end)
    t_end >= 0.5 && return 1.0e-3
    target = t_end / 500
    best = 1.0e-9
    for e in -9:-3, m in (1, 2, 5)
        v = m * 10.0^e
        v <= target && (best = v)
    end
    return round(best; sigdigits = 1)
end

function models_to_run(filters)
    out = Tuple{String,String}[]
    for dir in sort(readdir(EXAMPLES))
        proj = joinpath(EXAMPLES, dir)
        isfile(joinpath(proj, "bgsim.project.json")) || continue
        meta = JSON3.read(read(joinpath(proj, "bgsim.project.json"), String))
        for m in meta.models
            key = dir * "/" * String(m)
            if isempty(filters) || dir in filters || key in filters
                push!(out, (dir, String(m)))
            end
        end
    end
    return out
end

# ---- X-EX1: the input trajectory of the export markers
#
# Deterministic (splitmix64, no dependence on Julia's RNG streams) and sampled at the
# communication instants k*step, k = 0..N: the FMU host and the reference run both hold
# sample k on [t_k, t_k+1) (zero-order hold). Each input gets five segments over the horizon,
# all within its range [lo, hi] (from expected.json `export.inputs`, else the marker's
# declared range, else start +- 1):
#   0-5 %   the marker's start value (the export's baked start state belongs to it),
#   5-20 %  a step to mid + 0.4 half,
#   20-40 % a ramp down to mid - 0.6 half,
#   40-70 % a linear chirp mid + 0.5 half sin(...) from 1/segment to 1/(20 step) Hz,
#   70-100 % a PRBS-like sequence: levels mid +- 0.5 half, held 2 to 40 steps at random.

mutable struct SplitMix
    s::UInt64
end
function next!(r::SplitMix)
    r.s += 0x9e3779b97f4a7c15
    z = r.s
    z = (z ⊻ (z >> 30)) * 0xbf58476d1ce4e5b9
    z = (z ⊻ (z >> 27)) * 0x94d049bb133111eb
    return z ⊻ (z >> 31)
end
uniform!(r::SplitMix) = (next!(r) >> 11) * 2.0^-53

function input_trajectory(start, lo, hi, t_end, step, seed)
    n = round(Int, t_end / step)
    t = [k * step for k in 0:n]
    mid, half = (lo + hi) / 2, (hi - lo) / 2
    a, b, c, d = 0.05t_end, 0.2t_end, 0.4t_end, 0.7t_end
    f0, f1 = 1 / (d - c), 1 / (20step)
    rng = SplitMix(UInt64(seed))
    prbs_level, prbs_left = mid + 0.5half, 0
    u = similar(t)
    for (k, tk) in enumerate(t)
        v = if tk < a
            start
        elseif tk < b
            mid + 0.4half
        elseif tk < c
            mid + 0.4half + (tk - b) / (c - b) * (-0.6half - 0.4half)
        elseif tk < d
            s = tk - c
            mid + 0.5half * sin(2pi * (f0 * s + (f1 - f0) / (2 * (d - c)) * s^2))
        else
            if prbs_left <= 0
                prbs_level = uniform!(rng) < 0.5 ? mid - 0.5half : mid + 0.5half
                prbs_left = 2 + floor(Int, 39 * uniform!(rng))
            end
            prbs_left -= 1
            prbs_level
        end
        u[k] = clamp(v, lo, hi)
    end
    return t, u
end

function marker_inputs(flat, ranges, t_end, step)
    out = Dict{String,Any}[]
    params = Dict(p.id => p for p in flat.parameters)
    for (k, path) in enumerate(BGSim.Export.input_markers(flat))
        p = params[path * "/value"]
        start = Float64(p.value)
        r = get(ranges, path, nothing)
        lo, hi = if r !== nothing
            (Float64(r["min"]), Float64(r["max"]))
        elseif get(p.attrs, :min, nothing) isa Real && get(p.attrs, :max, nothing) isa Real
            (Float64(p.attrs[:min]), Float64(p.attrs[:max]))
        else
            (start - 1.0, start + 1.0)
        end
        t, u = input_trajectory(start, lo, hi, t_end, step, 0x5eed + k)
        push!(out, Dict{String,Any}("name" => path, "id" => path * "/value", "start" => start,
            "min" => lo, "max" => hi, "t" => t, "u" => u))
    end
    return out
end

function run_one(out_root, project, model; overrides = Dict{String,Any}())
    proj = joinpath(EXAMPLES, project)
    doc = todict(JSON3.read(read(joinpath(proj, "models", model * ".bgmodel.json"), String)))
    expected_path = joinpath(proj, "expected.json")
    input_ranges = Dict{String,Any}()
    if isfile(expected_path)
        expected = JSON3.read(read(expected_path, String))
        m = get(get(expected, :models, Dict()), Symbol(model), nothing)
        if m !== nothing && haskey(m, :settings)
            overlay!(get!(doc, "settings", Dict{String,Any}()), todict(m.settings))
        end
        if m !== nothing && haskey(m, :export) && haskey(m.export, :inputs)
            input_ranges = todict(m.export.inputs)
        end
    end
    settings = get(doc, "settings", Dict{String,Any}())
    t_end = Float64(get(settings, "t_end", 1.0))
    step = comm_step(t_end)
    dir = joinpath(out_root, project, model)
    rm(dir; force = true, recursive = true)
    mkpath(dir)
    rec = Dict{String,Any}("project" => project, "model" => model, "dir" => dir,
        "tEnd" => t_end, "step" => step)

    flat = BGSim.Compile.flatten(BGSim.IR.parse_model(doc); project_dir = proj)
    # X-EX1: the host supplies the export inputs (a pass-through marker's wire is cut), and
    # the reference is driven by the same trajectory the FMU gets through its inputs.
    flat = BGSim.Export.host_inputs(flat)
    inputs = marker_inputs(flat, input_ranges, t_end, step)
    if !isempty(inputs)
        rec["inputs"] = [Dict(k => v for (k, v) in i if !(k in ("t", "u"))) for i in inputs]
        rec["inputFile"] = joinpath(dir, "inputs.json")
        write(rec["inputFile"], JSON3.write(Dict("t" => inputs[1]["t"],
            "u" => Dict(i["name"] => i["u"] for i in inputs))))
    end
    has_markers = !isempty(inputs) || any(i -> i.ref == BGSim.Export.MARKER_OUTPUT, flat.instances)
    es = BGSim.Export.ExportSettings(merge(Dict{String,Any}("t_end" => t_end, "step" => step,
        "expose_all" => true), overrides))
    t0 = time()
    first = BGSim.Export.export_model(flat, joinpath(dir, "export"); settings = es,
        name = replace(model, "-" => "_"))
    rec["firstExportS"] = time() - t0
    if !first.ok
        rec["status"] = "refused"
        rec["diagnostics"] = [Dict("code" => d.code, "message" => d.message, "hint" => d.hint)
                              for d in first.diagnostics if d.severity == "error"]
        return rec
    end

    ref_dir = joinpath(dir, "reference")
    run_settings = Dict{String,Any}(
        "t_end" => t_end,
        "solver" => String(get(settings, "solver", "auto")),
        "reltol" => min(Float64(get(settings, "reltol", 1e-6)), 1e-6),
        "abstol" => min(Float64(get(settings, "abstol", 1e-8)), 1e-8),
        "output" => Dict("mode" => "interval", "interval" => step),
    )
    t0 = time()
    budget = parse(Float64, get(ENV, "BGSIM_EXPORT_REF_BUDGET", "300"))
    BGSim.simulate(flat; run_dir = ref_dir, settings = run_settings,
        cancel = () -> time() - t0 > budget,
        inputs = isempty(inputs) ? nothing :
                 Dict(i["id"] => (i["t"], i["u"]) for i in inputs))
    rec["referenceS"] = time() - t0
    manifest = JSON3.read(read(joinpath(ref_dir, "manifest.json"), String))
    if String(manifest.status) != "done"
        rec["status"] = time() - t0 > budget ? "reference_timeout" : "reference_failed"
        rec["diagnostics"] = [Dict("code" => String(d.code), "message" => String(d.message))
                              for d in get(manifest, :diagnostics, [])]
        return rec
    end

    t0 = time()
    result = BGSim.Export.export_model(flat, joinpath(dir, "export"); settings = es,
        reference_dir = ref_dir, name = replace(model, "-" => "_"))
    rec["exportS"] = time() - t0
    rec["status"] = result.ok ? "exported" : "refused"
    rec["warnings"] = [Dict("code" => d.code, "message" => d.message) for d in result.diagnostics]
    # X-EX1: the deliverable FMU, the markers only (no `expose_all`): its modelDescription and
    # its outputs driven through its inputs are checked by export_checks.py.
    if result.ok && has_markers
        t0 = time()
        markers = BGSim.Export.export_model(flat, joinpath(dir, "export-markers");
            settings = BGSim.Export.ExportSettings(merge(Dict{String,Any}("t_end" => t_end,
                "step" => step, "expose_all" => false), overrides)),
            reference_dir = ref_dir, name = replace(model, "-" => "_"))
        rec["markersExportS"] = time() - t0
        rec["markersExport"] = markers.ok ? "exported" : "refused"
    end
    return rec
end

function main(args)
    out_root = abspath(args[1])
    mkpath(out_root)
    rest = args[2:end]
    resume = "--resume" in rest
    overrides = Dict{String,Any}()
    for a in rest
        startswith(a, "--settings=") || continue
        merge!(overrides, todict(JSON3.read(a[length("--settings=") + 1:end])))
    end
    filters = filter(a -> a != "--resume" && !startswith(a, "--settings="), rest)
    todo = models_to_run(filters)
    results = joinpath(out_root, "results.jsonl")
    done = Set{String}()
    if resume && isfile(results)
        for line in eachline(results)
            isempty(strip(line)) && continue
            r = JSON3.read(line)
            push!(done, String(r.project) * "/" * String(r.model))
        end
    end
    open(results, resume ? "a" : "w") do io
        for (project, model) in todo
            project * "/" * model in done && continue
            write(joinpath(out_root, "current.json"),
                JSON3.write((project = project, model = model, started = time())))
            print(stderr, "export ", project, "/", model, " ... ")
            flush(stderr)
            rec = try
                run_one(out_root, project, model; overrides)
            catch err
                Dict{String,Any}("project" => project, "model" => model, "status" => "crashed",
                    "error" => first(sprint(showerror, err), 2000))
            end
            println(stderr, rec["status"], " (", round(Int, get(rec, "referenceS", 0.0)), " s reference)")
            flush(stderr)
            JSON3.write(io, rec)
            println(io)
            flush(io)
        end
    end
end

main(ARGS)
