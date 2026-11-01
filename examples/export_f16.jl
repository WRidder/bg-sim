# The f16-sim FMU and its references (the f16-sim host's FMU; examples/f16/README.md, "The FMU").
#
#   julia --project=julia/BGSim examples/export_f16.jl <out_dir> [--no-reference]
#
# Writes, under <out_dir>:
#   fmu/                  the export of models/f16-sim with the host interface: the ExportInputPass
#                         markers are FMU inputs (the model's test stimulus is cut off,
#                         `Export.host_inputs`), the ExportOutput markers FMU outputs, and the
#                         TUNABLES below FMU parameters with their ranges. The analysis picks the
#                         method and the internal step for the 5 ms communication step.
#   <scenario>/reference  a bg-sim run of the same flattened model driven by the scenario's
#                         inputs (zero-order hold at the communication instants), tight tolerances,
#                         output every communication step; <scenario>/inputs.json the inputs.
#   export.jsonl          one line: the export report's method, dt, substeps, the interface.
# `examples/export_f16_check.py` builds the FMU and compares it in fmpy.

using BGSim
import JSON3

const HERE = @__DIR__
const PROJECT = joinpath(HERE, "f16")
const STEP = 0.005          # s, the host's communication step (200 Hz)
const T_END = 3600.0        # s, the default stop time in the modelDescription (the host runs open-ended)

# FMU parameters: the trim globals (set together, from a trim), the CG and the mass, and the
# switches of the law. Ranges: what the trims of the host's start list and the tests cover.
const TUNABLES = [
    "global:vt0" => (90.0, 400.0), "global:h0" => (300.0, 12000.0), "global:alpha0" => (-5.0, 25.0),
    "global:el0" => (-25.0, 25.0), "global:thtl0" => (0.0, 1.0), "global:xcg" => (0.2, 0.45),
    "global:mass" => (7000.0, 14000.0),
    "global:limiter" => (0.0, 1.0), "global:turn_comp" => (0.0, 1.0), "global:roll_law" => (0.0, 1.0),
    "global:yaw_damper" => (0.0, 1.0), "global:beta_hold" => (0.0, 1.0), "global:ari" => (0.0, 1.0),
    "global:vv_roll" => (0.0, 1.0),
]

todict(x::AbstractDict) = Dict{String,Any}(String(k) => todict(v) for (k, v) in pairs(x))
todict(x::AbstractVector) = Any[todict(v) for v in x]
todict(x) = x

"""A piecewise-constant input: `(t_on, value)` pairs after the start value, sampled at the
communication instants (the FMU sees the value set before each doStep)."""
function held(start, changes, t)
    v = start
    for (tk, vk) in changes
        t >= tk - 1e-9 && (v = vk)
    end
    return v
end

function scenarios(globals)
    thr0 = globals["thtl0"]
    turn_stick = globals["roll_amp"]           # the model's default test input: banks to 60 deg in 1 s
    return [
        (name = "pitch_doublet", t_end = 10.0,
         inputs = Dict("stick_pitch" => [(1.0, 0.3), (2.0, -0.3), (3.0, 0.0)])),
        (name = "roll", t_end = 10.0,
         inputs = Dict("stick_roll" => [(1.0, 0.6), (3.0, 0.0), (5.0, -0.6), (7.0, 0.0)])),
        (name = "turn", t_end = 20.0,
         inputs = Dict("stick_roll" => [(1.0, turn_stick), (2.0, 0.0)], "throttle" => [(1.0, 0.33)])),
        (name = "throttle_step", t_end = 15.0,
         inputs = Dict("throttle" => [(1.0, 1.0)], "pedals" => [(8.0, 0.3), (10.0, 0.0)])),
    ]
end

function main(args)
    out = abspath(args[1])
    with_reference = !("--no-reference" in args)
    mkpath(out)
    doc = todict(JSON3.read(read(joinpath(PROJECT, "models", "f16-sim.bgmodel.json"), String)))
    globals = Dict(String(g["name"]) => parse(Float64, String(g["value"])) for g in doc["parameters"])
    flat = BGSim.Compile.flatten(BGSim.IR.parse_model(doc); project_dir = PROJECT)
    flat = BGSim.Export.host_inputs(flat)

    settings = BGSim.Export.ExportSettings(Dict{String,Any}(
        "t_end" => T_END, "step" => STEP,
        "tunables" => first.(TUNABLES), "ranges" => Dict{String,Any}(k => v for (k, v) in TUNABLES)))
    t0 = time()
    res = BGSim.Export.export_model(flat, joinpath(out, "fmu"); settings, name = "f16_sim")
    rec = Dict{String,Any}("ok" => res.ok, "exportS" => time() - t0, "step" => STEP,
        "diagnostics" => [Dict("code" => d.code, "severity" => d.severity, "message" => d.message)
                          for d in res.diagnostics])
    print(stderr, "export: ", res.ok ? "ok" : "refused", " (", round(rec["exportS"]; digits = 1), " s)\n")
    if res.ok
        rec["method"] = res.report["method"]
        rec["dt"] = res.report["dt"]
        rec["substeps"] = res.report["substeps"]
    end
    open(joinpath(out, "export.jsonl"), "w") do io
        JSON3.write(io, rec)
        println(io)
    end
    (res.ok && with_reference) || return res.ok ? 0 : 1

    params = Dict(p.id => p for p in flat.parameters)
    markers = BGSim.Export.input_markers(flat)
    for sc in scenarios(globals)
        dir = joinpath(out, sc.name)
        rm(dir; force = true, recursive = true)
        mkpath(dir)
        n = round(Int, sc.t_end / STEP)
        t = collect(0:n) .* STEP
        u = Dict{String,Vector{Float64}}()
        for path in markers
            start = Float64(params[path * "/value"].value)
            ch = get(sc.inputs, path, Tuple{Float64,Float64}[])
            u[path] = [held(start, ch, tk) for tk in t]
        end
        write(joinpath(dir, "inputs.json"), JSON3.write(Dict("t" => t, "u" => u)))
        t0 = time()
        BGSim.simulate(flat; run_dir = joinpath(dir, "reference"), settings = Dict{String,Any}(
                "t_end" => sc.t_end, "solver" => "auto", "reltol" => 1e-9, "abstol" => 1e-9,
                "output" => Dict("mode" => "interval", "interval" => STEP)),
            inputs = Dict(path * "/value" => (t, u[path]) for path in markers))
        print(stderr, "reference ", sc.name, ": ", round(time() - t0; digits = 1), " s\n")
    end
    return 0
end

exit(main(ARGS))
