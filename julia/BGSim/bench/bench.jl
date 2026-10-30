# PERF-1 benchmark harness.
#
#   julia --project=julia/BGSim julia/BGSim/bench/bench.jl [case-substring ...] [--runs=N] [--full] [--save=dir] [--compare=dir] [--out=file.json]
#
# For every case it times, separately: flatten (parse + library + connect + causality),
# lower_flat (expressions -> Symbolics), System + mtkcompile, ODEProblem build, then a full
# `simulate` run cold (compile cache cleared; compile + init + solve + record) and warm (cache
# hit: remake + init + solve + record), with the solver statistics. Cases may shorten `t_end`
# (and scale the number of output points); the shortened value is part of the case name.
using BGSim, JSON3, Printf
using BGSim: Compile, IR, Flat
using ModelingToolkit

const ROOT = get(ENV, "BGSIM_ROOT", normpath(joinpath(@__DIR__, "..", "..", "..")))

# (name, example, model, t_end override or nothing)
const CASES = [
    ("dc-motor/iconic", "dc-motor", "iconic", nothing),
    ("drivetrain-kalman", "drivetrain-kalman", "drivetrain-kalman", nothing),
    ("industrial-servo/switching", "industrial-servo", "switching", nothing),
    ("robot-arm-2d/arm", "robot-arm-2d", "arm", nothing),
    ("robot-arm-3d/arm (t_end 0.5)", "robot-arm-3d", "arm", 0.5),
    ("robot-arm-3d/rrr", "robot-arm-3d", "rrr", nothing),
    ("robot-arm-3d/rrr-multibond (t_end 1)", "robot-arm-3d", "rrr-multibond", 1.0),
    ("cube-3d/cube-3d-mb (t_end 1)", "cube-3d", "cube-3d-mb", 1.0),
    ("cube-3d/cube-3d (t_end 1)", "cube-3d", "cube-3d", 1.0),
    ("cube-pyramid-3d/edge-contact", "cube-pyramid-3d", "edge-contact", nothing),
    ("cube-pyramid-3d/sequence-contact (t_end 0.5)", "cube-pyramid-3d", "sequence-contact", 0.5),
]

function load_doc(example, model, t_end)
    dir = joinpath(ROOT, "examples", example)
    doc = JSON3.read(read(joinpath(dir, "models", model * ".bgmodel.json"), String))
    d = JSON3.read(JSON3.write(doc), Dict{String,Any})
    if t_end !== nothing
        s = d["settings"]
        old = Float64(s["t_end"])
        s["t_end"] = Float64(t_end)
        out = s["output"]
        if haskey(out, "points")
            out["points"] = max(11, round(Int, out["points"] * t_end / old))
        end
    end
    return d, dir
end

timed(f) = (t0 = time_ns(); r = f(); (r, (time_ns() - t0) / 1.0e9))

function bench_case(name, example, model, t_end; runs = 2, save = nothing, compare = nothing)
    row = Dict{String,Any}("case" => name)
    d, dir = load_doc(example, model, t_end)
    md = IR.parse_model(d)
    flat, row["flatten_s"] = timed(() -> Compile.flatten(md; project_dir = dir))
    row["states"] = flat.stats.states
    row["equations"] = flat.stats.equations
    row["signals"] = length(flat.signals)
    row["discrete"] = length(flat.discrete)
    # compile phases (replicates BGSim._build_compiled so each stage is timed)
    BGSim.clear_compile_cache!()
    lowered, row["lower_s"] = timed(() -> BGSim.lower_flat(flat))
    vars = Num[lowered.vars[v.id] for v in flat.variables]
    for dv in flat.derived
        push!(vars, lowered.vars[dv.id])
    end
    for p in lowered.int_states
        push!(vars, p.first)
    end
    pars = Num[lowered.params[p.id] for p in flat.parameters]
    kwargs = (; name = :benchsys)
    isempty(lowered.initial) || (kwargs = merge(kwargs, (; initialization_eqs = lowered.initial)))
    isempty(lowered.events) || (kwargs = merge(kwargs, (; continuous_events = lowered.events)))
    sys, row["system_s"] = timed(() -> System(lowered.eqs, BGSim.t, vars, pars; kwargs...))
    csys, row["mtkcompile_s"] = timed(() -> mtkcompile(sys))
    op = Pair{Num,Any}[]
    append!(op, BGSim._u0_pairs(flat, csys, lowered.int_states))
    append!(op, BGSim._p_pairs(flat, lowered.params))
    guesses = BGSim._guess_pairs(flat, csys)
    settings = BGSim.RunSettings(md.settings)
    prob, row["problem_s"] = timed(() -> ODEProblem(csys, op, (settings.t_start, settings.t_end); guesses = guesses))
    row["algebraic"] = BGSim._has_algebraic(prob)
    # full runs through simulate
    BGSim.clear_compile_cache!()
    for k in 1:runs
        dirk = mktempdir()
        res, total = timed(() -> BGSim.simulate(flat; run_dir = dirk, settings = settings))
        p = BGSim.LAST_PROFILE[]
        tag = k == 1 ? "cold" : k == 2 ? "warm" : "warm"
        if k == runs
            slug = replace(name, r"[^A-Za-z0-9]+" => "_")
            cols = joinpath(dirk, "columns.f64")
            if save !== nothing
                mkpath(save); cp(cols, joinpath(save, slug * ".f64"); force = true)
            end
            if compare !== nothing
                a = reinterpret(Float64, read(cols))
                b = reinterpret(Float64, read(joinpath(compare, slug * ".f64")))
                row["max_abs_diff"] = length(a) == length(b) ? maximum(abs.(a .- b)) : Inf
                row["identical"] = length(a) == length(b) && a == b
            end
        end
        row[tag] = Dict{String,Any}(
            "status" => res.status, "total_s" => total, "compile_s" => res.stats.compile_s,
            "init_s" => p === nothing ? NaN : p.init_s,
            "loop_s" => res.stats.sim_s,
            "step_s" => p === nothing ? NaN : p.step_s,
            "tick_s" => p === nothing ? NaN : p.tick_s,
            "values_s" => p === nothing ? NaN : p.values_s,
            "steps" => res.stats.steps, "events" => res.stats.events,
            "ticks" => p === nothing ? 0 : p.ticks,
            "nreject" => (p === nothing || p.stats === nothing) ? 0 : p.stats.nreject,
            "nf" => (p === nothing || p.stats === nothing) ? 0 : p.stats.nf,
            "njacs" => (p === nothing || p.stats === nothing) ? 0 : p.stats.njacs,
            "nw" => (p === nothing || p.stats === nothing) ? 0 : p.stats.nw,
            "nsolve" => (p === nothing || p.stats === nothing) ? 0 : p.stats.nsolve,
            "rows" => length(res.manifest.time) == 0 ? 0 : res.manifest.time.n,
        )
        rm(dirk; recursive = true, force = true)
        res.status == "done" || (println("  !! status ", res.status, " ", [d.message for d in res.diagnostics]); break)
    end
    return row
end

function main(args)
    runs = 3
    out = nothing
    save = nothing
    compare = nothing
    names = String[]
    for a in args
        if startswith(a, "--runs=")
            runs = parse(Int, a[8:end])
        elseif startswith(a, "--save=")
            save = a[8:end]
        elseif startswith(a, "--compare=")
            compare = a[11:end]
        elseif startswith(a, "--out=")
            out = a[7:end]
        elseif a == "--full"
        else
            push!(names, a)
        end
    end
    cases = isempty(names) ? CASES : [c for c in CASES if any(n -> occursin(n, c[1]), names)]
    if "--full" in ARGS
        cases = [(replace(c[1], r" \(t_end [0-9.]+\)" => ""), c[2], c[3], nothing) for c in cases]
    end
    rows = Dict{String,Any}[]
    for (name, ex, m, te) in cases
        println("== ", name); flush(stdout)
        r = bench_case(name, ex, m, te; runs = runs, save = save, compare = compare)
        push!(rows, r)
        w = get(r, "warm", get(r, "cold", Dict()))
        @printf("  states=%d flatten=%.2f lower=%.2f system=%.2f mtkcompile=%.2f problem=%.2f\n",
            r["states"], r["flatten_s"], r["lower_s"], r["system_s"], r["mtkcompile_s"], r["problem_s"])
        haskey(r, "identical") && println("  compare: identical=", r["identical"], " max_abs_diff=", r["max_abs_diff"])
        for tag in ("cold", "warm", "warm3")
            haskey(r, tag) || continue
            c = r[tag]
            @printf("  %s: total=%.2f compile=%.2f init=%.2f loop=%.2f (step=%.2f tick=%.2f values=%.2f) steps=%d rej=%d nf=%d njac=%d nw=%d nsolve=%d ticks=%d rows=%d %s\n",
                tag, c["total_s"], c["compile_s"], c["init_s"], c["loop_s"], c["step_s"], c["tick_s"],
                c["values_s"], c["steps"], c["nreject"], c["nf"], c["njacs"], c["nw"], c["nsolve"], c["ticks"], c["rows"], c["status"])
        end
        flush(stdout)
    end
    out === nothing || write(out, JSON3.write(rows))
end

main(ARGS)
