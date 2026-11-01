# R0.4/R0.5 (plan/RL_PLAN.md): run model documents of the double cart with the policy block in
# bgsim and record the compile and run times.
#
#   julia --project=julia/BGSim rl/closed_loop.jl <out_dir> <model.bgmodel.json> ...
#
# Each model runs with its own settings (Rodas5P, reltol 1e-8), output every 1 ms, into
# <out_dir>/<model name>/ (manifest.json, stream.f64). <out_dir>/timings.json gets, per model,
# flatten seconds (parse + library + flatten, which includes parsing the generated block), and
# the simulator's own compile_s / sim_s. The first model also pays Julia's JIT warm-up, so the
# first one is run twice and the second timing is reported as well.

using BGSim
import JSON3

const ROOT = normpath(joinpath(@__DIR__, ".."))
const PROJECT = joinpath(ROOT, "examples", "pendulum-double-cart")

todict(x::AbstractDict) = Dict{String,Any}(String(k) => todict(v) for (k, v) in pairs(x))
todict(x::AbstractVector) = Any[todict(v) for v in x]
todict(x) = x

function run_one(out, path; tag = "")
    doc = todict(JSON3.read(read(path, String)))
    name = doc["name"] * tag
    t0 = time()
    flat = BGSim.Compile.flatten(BGSim.IR.parse_model(doc); project_dir = PROJECT)
    flatten_s = time() - t0
    s = doc["settings"]
    settings = Dict{String,Any}("t_end" => Float64(s["t_end"]), "solver" => "Rodas5P",
        "reltol" => 1e-8, "abstol" => 1e-10, "output" => Dict("mode" => "interval", "interval" => 1e-3))
    t0 = time()
    BGSim.simulate(flat; run_dir = joinpath(out, name), settings)
    total = time() - t0
    m = JSON3.read(read(joinpath(out, name, "manifest.json"), String))
    rec = Dict{String,Any}("model" => name, "flattenS" => flatten_s, "simulateS" => total,
        "status" => String(m.status), "stats" => todict(m.stats),
        "diagnostics" => [String(d.code) for d in get(m, :diagnostics, [])])
    println(stderr, name, ": ", rec["status"], " flatten ", round(flatten_s; digits = 2), " s, compile ",
        round(m.stats.compile_s; digits = 2), " s, run ", round(m.stats.sim_s; digits = 2), " s")
    return rec
end

function main(args)
    out = abspath(args[1])
    mkpath(out)
    recs = Any[]
    for (k, path) in enumerate(args[2:end])
        k == 1 && push!(recs, run_one(out, path; tag = "-cold"))
        push!(recs, run_one(out, path))
    end
    write(joinpath(out, "timings.json"), JSON3.write(recs))
end

main(ARGS)
