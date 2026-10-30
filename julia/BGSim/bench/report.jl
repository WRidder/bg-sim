# Turn two bench.jl JSON outputs (before, after) into the markdown tables of RESULTS.md.
#   julia --project=julia/BGSim julia/BGSim/bench/report.jl before.json after.json
using JSON3, Printf
rows(path) = JSON3.read(read(path, String), Vector{Dict{String,Any}})
before, after = rows(ARGS[1]), rows(ARGS[2])
byname(rs) = Dict(replace(r["case"], r" \(t_end [0-9.]+\)" => "") => r for r in rs)
b, a = byname(before), byname(after)
f(x) = x isa Number ? @sprintf("%.1f", x) : string(x)
println("| case | states | signals | cold total before -> after (s) | warm total before -> after (s) | warm solve loop before -> after | steps / rejects |")
println("|---|---:|---:|---|---|---|---|")
for r in after
    key = replace(r["case"], r" \(t_end [0-9.]+\)" => "")
    haskey(b, key) || continue
    x = b[key]
    cb, ca, wb, wa = x["cold"], r["cold"], x["warm"], r["warm"]
    println("| ", r["case"], " | ", r["states"], " | ", r["signals"], " | ", f(cb["total_s"]), " -> ", f(ca["total_s"]),
        " | ", f(wb["total_s"]), " -> ", f(wa["total_s"]),
        " | ", f(wb["loop_s"]), " -> ", f(wa["loop_s"]), " | ", wa["steps"], " / ", wa["nreject"], " |")
end
println()
println("| case | phase (cold, after) flatten / lower / System / mtkcompile / ODEProblem | compile (remake) | init | loop: step / tick / values |")
println("|---|---|---:|---:|---|")
for r in after
    c = r["cold"]
    println("| ", r["case"], " | ", join([f(r[k]) for k in ("flatten_s", "lower_s", "system_s", "mtkcompile_s", "problem_s")], " / "),
        " | ", f(c["compile_s"]), " | ", f(c["init_s"]), " | ", f(c["step_s"]), " / ", f(c["tick_s"]), " / ", f(c["values_s"]), " |")
end
