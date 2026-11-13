# Run one spider model through BGSim directly (no backend), for design iterations.
#
#   julia --project=julia/BGSim examples/spider/design/run_model.jl <model> <run_dir> [t_end|-] [overrides.json]
#
# Writes <run_dir>/columns.f64 + manifest.json (the layout `design/readrun.py` reads). Leg
# signals live inside the leg instances: `Leg1/Joints/q1`, `Leg1/IK/reach`.

using BGSim
import JSON3

const PROJECT = normpath(joinpath(@__DIR__, ".."))

todict(x::AbstractDict) = Dict{String,Any}(String(k) => todict(v) for (k, v) in pairs(x))
todict(x::AbstractVector) = Any[todict(v) for v in x]
todict(x) = x

function main(args)
    model, run_dir = args[1], abspath(args[2])
    doc = todict(JSON3.read(read(joinpath(PROJECT, "models", model * ".bgmodel.json"), String)))
    settings = doc["settings"]
    length(args) >= 3 && args[3] != "-" && (settings["t_end"] = parse(Float64, args[3]))
    if length(args) >= 4
        for (k, v) in pairs(JSON3.read(read(args[4], String)))
            if startswith(String(k), "global:")
                name = String(k)[8:end]
                g = only(filter(p -> p["name"] == name, doc["parameters"]))
                g["value"] = isinteger(Float64(v)) ? string(Int(v)) : repr(Float64(v))
            else
                # `<node>/<param>` at the top level; on a leg instance the key is the pinned
                # path inside the subsystem, `Leg3/IK/yaw` (an unpinned path is W218).
                parts = split(String(k), "/")
                node = only(filter(nn -> nn["name"] == parts[1], doc["diagram"]["nodes"]))
                node["params"][join(parts[2:end], "/")] = isinteger(Float64(v)) ? string(Int(v)) : repr(Float64(v))
            end
        end
    end
    t0 = time()
    flat = BGSim.Compile.flatten(BGSim.IR.parse_model(doc); project_dir = PROJECT)
    println("flatten        ", round(time() - t0; digits = 2), " s")
    rm(run_dir; force = true, recursive = true)
    t1 = time()
    BGSim.simulate(flat; run_dir, settings)
    println("simulate total ", round(time() - t1; digits = 2), " s")
    manifest = JSON3.read(read(joinpath(run_dir, "manifest.json"), String))
    println("status ", manifest.status)
    for d in get(manifest, :diagnostics, [])
        println(d.code, " ", first(String(d.message), 500))
    end
end

main(ARGS)
