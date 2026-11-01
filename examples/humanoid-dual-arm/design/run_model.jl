# Run one humanoid-dual-arm model through BGSim (no backend) and time its phases.
#
#   julia --project=julia/BGSim examples/humanoid-dual-arm/design/run_model.jl <model> <run_dir> [t_end] [overrides.json]
#
# Writes <run_dir>/columns.f64 + manifest.json (the run layout of plan 3.5, which
# `build_expected.py` reads) and prints the flatten / simulate times and the diagnostics.
# `overrides.json` is an object {"<instance path>/<param>": value} applied to the document
# before flattening (the scenarios of expected.json: the 6-DOF switch, other poses).

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

function main(args)
    model, run_dir = args[1], abspath(args[2])
    doc = todict(JSON3.read(read(joinpath(PROJECT, "models", model * ".bgmodel.json"), String)))
    settings = doc["settings"]
    length(args) >= 3 && args[3] != "-" && (settings["t_end"] = parse(Float64, args[3]))
    # development aid: try another solver or tolerances without editing the model
    haskey(ENV, "HUMANOID_SOLVER") && (settings["solver"] = ENV["HUMANOID_SOLVER"])
    haskey(ENV, "HUMANOID_RELTOL") && (settings["reltol"] = parse(Float64, ENV["HUMANOID_RELTOL"]))
    haskey(ENV, "HUMANOID_ABSTOL") && (settings["abstol"] = parse(Float64, ENV["HUMANOID_ABSTOL"]))
    if length(args) >= 4
        for (k, v) in pairs(JSON3.read(read(args[4], String)))
            override!(doc, String(k), v)
        end
    end
    t0 = time()
    flat = BGSim.Compile.flatten(BGSim.IR.parse_model(doc); project_dir = PROJECT)
    t_flat = time() - t0
    marks = Pair{String,Float64}[]
    phase = (name, t) -> push!(marks, String(name) => time())
    rm(run_dir; force = true, recursive = true)
    t1 = time()
    BGSim.simulate(flat; run_dir, settings, phase)
    t_end = time()
    println("flatten        ", round(t_flat; digits = 2), " s")
    for (name, t) in marks
        println(rpad("start " * name, 15), round(t - t1; digits = 2), " s after simulate()")
    end
    println("simulate total ", round(t_end - t1; digits = 2), " s")
    manifest = JSON3.read(read(joinpath(run_dir, "manifest.json"), String))
    println("status ", manifest.status)
    for key in (:stats, :solver)
        haskey(manifest, key) && println(key, " ", JSON3.write(manifest[key]))
    end
    for d in get(manifest, :diagnostics, [])
        println(d.code, " ", first(String(d.message), 300))
    end
end

main(ARGS)
