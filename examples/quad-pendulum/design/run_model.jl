# Run one quad-pendulum model through BGSim directly (no backend), for design iterations.
#
#   julia --project=julia/BGSim examples/quad-pendulum/design/run_model.jl <model> <run_dir> [t_end|-] [overrides.json]
#
# Writes <run_dir>/columns.f64 + manifest.json (the run layout that `finish.py` and `quadlib.read_run`
# read) and prints the flatten / simulate times and the diagnostics. `overrides.json` is an object
# {"<instance>/<param>": value, "global:<name>": value} applied to the document before flattening.
# The acceptance runs go through the real backend (`examples/run_checks.py`).

using BGSim
import JSON3

const PROJECT = normpath(joinpath(@__DIR__, ".."))

todict(x::AbstractDict) = Dict{String,Any}(String(k) => todict(v) for (k, v) in pairs(x))
todict(x::AbstractVector) = Any[todict(v) for v in x]
todict(x) = x

function override!(doc, path::String, value)
    sval = value isa Bool ? string(value) : repr(Float64(value))
    if startswith(path, "global:")
        name = path[8:end]
        g = only(filter(p -> p["name"] == name, doc["parameters"]))
        g["value"] = sval
        return
    end
    parts = split(path, "/")
    node = only(filter(n -> n["name"] == parts[1], doc["diagram"]["nodes"]))
    node["params"][String(parts[2])] = sval
end

function main(args)
    model, run_dir = args[1], abspath(args[2])
    doc = todict(JSON3.read(read(joinpath(PROJECT, "models", model * ".bgmodel.json"), String)))
    settings = doc["settings"]
    length(args) >= 3 && args[3] != "-" && (settings["t_end"] = parse(Float64, args[3]))
    haskey(ENV, "QP_SOLVER") && (settings["solver"] = ENV["QP_SOLVER"])
    haskey(ENV, "QP_RELTOL") && (settings["reltol"] = parse(Float64, ENV["QP_RELTOL"]))
    haskey(ENV, "QP_ABSTOL") && (settings["abstol"] = parse(Float64, ENV["QP_ABSTOL"]))
    if length(args) >= 4
        for (k, v) in pairs(JSON3.read(read(args[4], String)))
            override!(doc, String(k), v)
        end
    end
    t0 = time()
    flat = BGSim.Compile.flatten(BGSim.IR.parse_model(doc); project_dir = PROJECT)
    t_flat = time() - t0
    rm(run_dir; force = true, recursive = true)
    t1 = time()
    BGSim.simulate(flat; run_dir, settings)
    println("flatten        ", round(t_flat; digits = 2), " s")
    println("simulate total ", round(time() - t1; digits = 2), " s")
    manifest = JSON3.read(read(joinpath(run_dir, "manifest.json"), String))
    println("status ", manifest.status)
    for key in (:stats, :solver)
        haskey(manifest, key) && println(key, " ", JSON3.write(manifest[key]))
    end
    for d in get(manifest, :diagnostics, [])
        println(d.code, " ", first(String(d.message), 400))
    end
end

if length(ARGS) >= 2 && ARGS[1] == "--many"
    # --many <run_root> <model> [<model> ..]: several models in one process (one compile of the stdlib)
    for m in ARGS[3:end]
        println("== ", m)
        main([m, joinpath(ARGS[2], m)])
    end
else
    main(ARGS)
end
