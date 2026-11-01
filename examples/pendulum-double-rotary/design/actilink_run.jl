# Run ACTILINK models of pendulum-double-rotary through BGSim directly (no backend), several in one
# Julia process (one JIT warm-up), and time them.
#
#   julia --project=julia/BGSim examples/pendulum-double-rotary/design/actilink_run.jl <out_dir> <model>[:t_end][@overrides.json] ...
#
# Writes <out_dir>/<tag>/columns.f64 + manifest.json (the run layout of plan 3.5, read by
# actilink_io.py). `tag` is the model name, or `<model>-<overrides file stem>` with overrides.
# A model argument may carry ":t_end" to shorten the run and "@overrides.json"
# ({"<instance>/<param>": value}) to change parameters before flattening.

using BGSim
import JSON3

const PROJECT = normpath(joinpath(@__DIR__, ".."))

todict(x::AbstractDict) = Dict{String,Any}(String(k) => todict(v) for (k, v) in pairs(x))
todict(x::AbstractVector) = Any[todict(v) for v in x]
todict(x) = x

function override!(doc, path::String, value)
    parts = split(path, "/")
    node = only(filter(n -> n["name"] == parts[1], doc["diagram"]["nodes"]))
    node["params"][String(parts[2])] = value isa Bool ? string(value) : repr(Float64(value))
end

function run_one(spec::String, out_root::String)
    over = nothing
    if occursin('@', spec)
        spec, over = split(spec, '@'; limit = 2)
    end
    parts = split(spec, ':')
    model = String(parts[1])
    doc = todict(JSON3.read(read(joinpath(PROJECT, "models", model * ".bgmodel.json"), String)))
    settings = doc["settings"]
    length(parts) >= 2 && (settings["t_end"] = parse(Float64, parts[2]))
    if over !== nothing
        for (k, v) in pairs(JSON3.read(read(String(over), String)))
            override!(doc, String(k), v)
        end
    end
    tag = over === nothing ? model : model * "-" * splitext(basename(String(over)))[1]
    run_dir = joinpath(out_root, tag)
    t0 = time()
    flat = BGSim.Compile.flatten(BGSim.IR.parse_model(doc); project_dir = PROJECT)
    t_flat = time() - t0
    rm(run_dir; force = true, recursive = true)
    t1 = time()
    BGSim.simulate(flat; run_dir, settings)
    t2 = time()
    manifest = JSON3.read(read(joinpath(run_dir, "manifest.json"), String))
    println(tag, ": flatten ", round(t_flat; digits = 1), " s, simulate ", round(t2 - t1; digits = 1),
            " s, status ", manifest.status)
    for d in get(manifest, :diagnostics, [])
        println("  ", d.code, " ", first(String(d.message), 400))
    end
    flush(stdout)
end

function main(args)
    out_root = abspath(args[1])
    mkpath(out_root)
    for spec in args[2:end]
        try
            run_one(String(spec), out_root)
        catch err
            println(spec, ": FAILED ", first(sprint(showerror, err), 3000))
            flush(stdout)
        end
    end
end

main(ARGS)
