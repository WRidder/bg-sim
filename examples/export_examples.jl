# Export every example model and run its reference simulation (plan/EXPORT_PLAN.md X-EX1).
#
#   julia --project=julia/BGSim examples/export_examples.jl <out_root> [--resume] [project[/model] ...]
#
# `--resume` appends to an existing results.jsonl and skips the models already in it.
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

function run_one(out_root, project, model)
    proj = joinpath(EXAMPLES, project)
    doc = todict(JSON3.read(read(joinpath(proj, "models", model * ".bgmodel.json"), String)))
    expected_path = joinpath(proj, "expected.json")
    if isfile(expected_path)
        expected = JSON3.read(read(expected_path, String))
        m = get(get(expected, :models, Dict()), Symbol(model), nothing)
        if m !== nothing && haskey(m, :settings)
            overlay!(get!(doc, "settings", Dict{String,Any}()), todict(m.settings))
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
    es = BGSim.Export.ExportSettings(t_end = t_end, step = step, expose_all = true)
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
        cancel = () -> time() - t0 > budget)
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
    return rec
end

function main(args)
    out_root = abspath(args[1])
    mkpath(out_root)
    rest = args[2:end]
    resume = "--resume" in rest
    filters = filter(!=("--resume"), rest)
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
                run_one(out_root, project, model)
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
