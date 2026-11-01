# Run suction-cup models through BGSim directly (no backend), for design/analysis.py.
#
#   julia --project=julia/BGSim examples/suction-cup/design/run_model.jl <jobs.json> <out_dir>
#
# `jobs.json` is a list of {"id", "model", "globals": {name: value}, "t_end"?, "signals": [...]}.
# Every job overrides global parameters of the model (`IR.override_globals`); jobs with the same
# structure hit the in-process compile cache, so only the first job of a structure compiles.
# For each job the script writes <out_dir>/<id>.json with the requested signals (time column
# first) or the error, and prints one line with the wall time.

using BGSim
import JSON3

const PROJECT = normpath(joinpath(@__DIR__, ".."))

todict(x::AbstractDict) = Dict{String,Any}(String(k) => todict(v) for (k, v) in pairs(x))
todict(x::AbstractVector) = Any[todict(v) for v in x]
todict(x) = x

function read_columns(run_dir)
    manifest = JSON3.read(read(joinpath(run_dir, "manifest.json"), String))
    n = Int(manifest.time.n)
    data = reinterpret(Float64, read(joinpath(run_dir, "columns.f64")))
    cols = Dict{String,Vector{Float64}}()
    cols["time"] = collect(data[1:n])
    for (k, s) in enumerate(manifest.signals)
        cols[String(s.id)] = collect(data[k*n+1:(k+1)*n])
    end
    return manifest, cols
end

function run_job(job, out_dir)
    id = String(job["id"])
    doc = todict(JSON3.read(read(joinpath(PROJECT, "models", String(job["model"]) * ".bgmodel.json"), String)))
    settings = doc["settings"]
    haskey(job, "t_end") && (settings["t_end"] = Float64(job["t_end"]))
    haskey(job, "solver") && (settings["solver"] = String(job["solver"]))
    if haskey(job, "points")
        settings["output"]["points"] = Int(job["points"])
    else
        settings["output"]["points"] = Int(round(settings["t_end"] * 500)) + 1
    end
    overrides = Dict{String,Any}("global:" * String(k) => v for (k, v) in get(job, "globals", Dict()))
    md = BGSim.IR.parse_model(doc)
    isempty(overrides) || (md = BGSim.IR.override_globals(md, overrides))
    t0 = time()
    flat = BGSim.Compile.flatten(md; project_dir = PROJECT)
    run_dir = joinpath(out_dir, "_run_" * id)
    rm(run_dir; force = true, recursive = true)
    result = BGSim.simulate(flat; run_dir, settings)
    if !isfile(joinpath(run_dir, "columns.f64"))
        m = JSON3.read(read(joinpath(run_dir, "manifest.json"), String))
        for d in get(m, :diagnostics, [])
            println("  ", d.code, " ", get(d, :path, ""), " ", first(String(d.message), 1500))
        end
        error("run $(id) ended $(m.status) without columns")
    end
    manifest, cols = read_columns(run_dir)
    wanted = get(job, "signals", nothing)
    keep = Dict{String,Any}("time" => cols["time"])
    for (k, v) in cols
        (wanted === nothing || k in wanted) && (keep[k] = v)
    end
    out = Dict{String,Any}("id" => id, "status" => String(manifest.status),
        "seconds" => time() - t0, "signals" => keep,
        "diagnostics" => [Dict("code" => String(d.code), "message" => String(d.message)) for d in get(manifest, :diagnostics, [])])
    open(joinpath(out_dir, id * ".json"), "w") do io
        JSON3.write(io, out)
    end
    rm(run_dir; force = true, recursive = true)
    println(rpad(id, 40), " ", manifest.status, " ", round(time() - t0; digits = 1), " s")
    flush(stdout)
end

function main(args)
    jobs = JSON3.read(read(args[1], String))
    out_dir = abspath(args[2])
    mkpath(out_dir)
    for job in jobs
        try
            run_job(todict(job), out_dir)
        catch err
            msg = sprint(showerror, err)
            println(rpad(String(job["id"]), 40), " ERROR ", first(msg, 2000))
            open(joinpath(out_dir, String(job["id"]) * ".json"), "w") do io
                JSON3.write(io, Dict("id" => String(job["id"]), "status" => "error", "error" => msg))
            end
        end
    end
end

main(ARGS)
