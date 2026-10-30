# Run one panda-3d model through BGSim (no backend) and time its phases.
#
#   julia --project=julia/BGSim examples/panda-3d/design/run_model.jl <model> <run_dir> [t_end]
#
# Writes <run_dir>/columns.f64 + manifest.json (the run layout of plan 3.5, which
# `validate.py` reads) and prints the flatten / mtkcompile / init / simulate times.

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
    length(args) >= 3 && (settings["t_end"] = parse(Float64, args[3]))
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
    prev = t1
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
