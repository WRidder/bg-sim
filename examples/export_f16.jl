# The f16-sim FMU and its references (the f16-sim host's FMU; examples/f16/README.md, "The FMU").
#
#   julia --project=julia/BGSim examples/export_f16.jl <out_dir> [--no-reference]
#
# Writes, under <out_dir>:
#   fmu/                  the export of models/f16-sim with the host interface: the ExportInputPass
#                         markers are FMU inputs (the model's test stimulus is cut off,
#                         `Export.host_inputs`), the ExportOutput markers FMU outputs, and the
#                         TUNABLES below FMU parameters with their ranges, at RK4 and the internal
#                         step DT (not left to the analysis, see below).
#   <scenario>/reference  a bg-sim run of the same model, with the scenario's start globals, driven
#                         by the scenario's inputs (zero-order hold at the communication instants),
#                         tight tolerances, output every communication step; <scenario>/inputs.json
#                         the inputs and the start parameters.
#   export.jsonl          one line: the export report's method, dt, substeps, the interface.
# `examples/export_f16_check.py` builds the FMU and compares it in fmpy.

using BGSim
import JSON3

const HERE = @__DIR__
const PROJECT = joinpath(HERE, "f16")
const STEP = 0.005          # s, the host's communication step (200 Hz)
const T_END = 3600.0        # s, the default stop time in the modelDescription (the host runs open-ended)
# The internal step is set here, not left to the analysis: the analysis looks at the model's own start,
# in the air with the gear up, and does not see the tyres and struts of a run on the ground. From a start
# on the wheels RK4 is stable to 22 ms and its accuracy bound is 2.4 ms; the comparison in
# export_f16_check.py holds this step to account (examples/f16/README.md, "The FMU").
const DT = 0.0025           # s

# FMU parameters: the trim globals (set together, from a trim), the CG and the mass, and the
# switches of the law. Ranges: what the trims of the host's start list and the tests cover.
const TUNABLES = [
    "global:vt0" => (0.0, 400.0), "global:h0" => (0.0, 12000.0), "global:alpha0" => (-5.0, 25.0),
    "global:el0" => (-25.0, 25.0), "global:thtl0" => (0.0, 1.0), "global:xcg" => (0.2, 0.45),
    "global:mass" => (7000.0, 14000.0),
    "global:limiter" => (0.0, 1.0), "global:turn_comp" => (0.0, 1.0), "global:roll_law" => (0.0, 1.0),
    "global:yaw_damper" => (0.0, 1.0), "global:beta_hold" => (0.0, 1.0), "global:ari" => (0.0, 1.0),
    "global:vv_roll" => (0.0, 1.0),
    "global:gamma0" => (-20.0, 20.0), "global:gear0" => (0.0, 1.0),
    "global:north0" => (-100000.0, 100000.0), "global:east0" => (-100000.0, 100000.0),
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
    gear = todict(JSON3.read(read(joinpath(PROJECT, "design", "gear.json"), String)))
    rest = Dict("h0" => gear["static"]["h"], "alpha0" => gear["static"]["theta_deg"], "vt0" => 0.0, "el0" => 0.0,
                "thtl0" => 0.0, "gear0" => 1.0)
    ld = gear["scenarios"]["landing"]["spec"]
    approach = Dict(k => Float64(ld[k]) for k in ("vt0", "h0", "alpha0", "el0", "thtl0", "gamma0"))
    approach["gear0"] = 1.0
    down = [(0.0, 1.0)]
    # the wheels: taxi, steering and a stop in a crosswind; the take-off with the gear coming up; a landing
    ground = [
        (name = "taxi_stop", t_end = 25.0, globals = rest,
         inputs = Dict("gear_cmd" => down, "throttle" => [(0.0, 0.0), (1.0, 0.25), (14.0, 0.0)],
                       "pedals" => [(5.0, 0.4), (9.0, -0.4), (12.0, 0.0)], "wind_e" => [(0.0, 3.0)],
                       "brake_l" => [(15.0, 1.0)], "brake_r" => [(15.0, 1.0)])),
        (name = "takeoff", t_end = 22.0, globals = rest,
         inputs = Dict("gear_cmd" => [(0.0, 1.0), (16.0, 0.0)], "throttle" => [(0.0, 0.0), (1.0, 1.0)],
                       "stick_pitch" => [(12.0, 1.0), (13.8, 0.0)])),
        (name = "landing", t_end = 30.0, globals = approach,
         inputs = Dict("gear_cmd" => down, "throttle" => [(0.0, approach["thtl0"]), (12.0, 0.0)],
                       "brake_l" => [(17.0, 1.0)], "brake_r" => [(17.0, 1.0)])),
    ]
    flight = [
        (name = "pitch_doublet", t_end = 10.0,
         inputs = Dict("stick_pitch" => [(1.0, 0.3), (2.0, -0.3), (3.0, 0.0)])),
        (name = "roll", t_end = 10.0,
         inputs = Dict("stick_roll" => [(1.0, 0.6), (3.0, 0.0), (5.0, -0.6), (7.0, 0.0)])),
        (name = "turn", t_end = 20.0,
         inputs = Dict("stick_roll" => [(1.0, turn_stick), (2.0, 0.0)], "throttle" => [(1.0, 0.33)])),
        (name = "throttle_step", t_end = 15.0,
         inputs = Dict("throttle" => [(1.0, 1.0)], "pedals" => [(8.0, 0.3), (10.0, 0.0)])),
    ]
    return [[(; s..., globals = Dict{String,Float64}()) for s in flight]; ground]
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
        "t_end" => T_END, "step" => STEP, "dt" => DT,
        "tunables" => first.(TUNABLES), "ranges" => Dict{String,Any}(k => v for (k, v) in TUNABLES)))
    t0 = time()
    res = BGSim.Export.export_model(flat, joinpath(out, "fmu"); settings, name = "f16_sim")
    rec = Dict{String,Any}("ok" => res.ok, "exportS" => time() - t0, "step" => STEP,
        "diagnostics" => [Dict("code" => d.code, "severity" => d.severity, "message" => d.message, "hint" => d.hint)
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

    md = BGSim.IR.parse_model(doc)
    for sc in scenarios(globals)
        run_flat = isempty(sc.globals) ? flat : BGSim.Export.host_inputs(BGSim.flatten_with_overrides(
            md, ["global:$k" => v for (k, v) in sc.globals]; project_dir = PROJECT))
        params = Dict(p.id => p for p in run_flat.parameters)
        markers = BGSim.Export.input_markers(run_flat)
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
        write(joinpath(dir, "inputs.json"), JSON3.write(Dict("t" => t, "u" => u, "params" => sc.globals)))
        t0 = time()
        BGSim.simulate(run_flat; run_dir = joinpath(dir, "reference"), settings = Dict{String,Any}(
                "t_end" => sc.t_end, "solver" => "auto", "reltol" => 1e-9, "abstol" => 1e-9,
                "output" => Dict("mode" => "interval", "interval" => STEP)),
            inputs = Dict(path * "/value" => (t, u[path]) for path in markers))
        print(stderr, "reference ", sc.name, ": ", round(time() - t0; digits = 1), " s\n")
    end
    return 0
end

exit(main(ARGS))
