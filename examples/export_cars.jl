# The car-sim FMUs and their references (the car-sim host's FMUs; examples/cars/README.md, "The FMUs").
#
#   julia --project=julia/BGSim examples/export_cars.jl <out_dir> [racecar|buggy ...] [--no-reference]
#
# Writes, per vehicle, under <out_dir>/<vehicle>:
#   fmu/                  the export of models/<vehicle>-sim with the host interface: the ExportInputPass
#                         markers are FMU inputs (the model's test drive is cut off, `Export.host_inputs`),
#                         the ExportOutput markers FMU outputs, and the TUNABLES below FMU parameters with
#                         their ranges. The analysis picks the method and the internal step for the 5 ms
#                         communication step.
#   <scenario>/reference  a bg-sim run of the same flattened model driven by the scenario's inputs
#                         (zero-order hold at the communication instants), tight tolerances, output every
#                         communication step; <scenario>/inputs.json the inputs.
#   export.jsonl          one line: the export report's method, dt, substeps, the diagnostics.
# `examples/export_cars_check.py` builds the FMUs and compares them in fmpy.

using BGSim
import JSON3

const HERE = @__DIR__
const PROJECT = joinpath(HERE, "cars")
const STEP = 0.005          # s, the host's communication step (200 Hz)
const T_END = 3600.0        # s, the default stop time in the modelDescription (the host runs open-ended)

# FMU parameters: the start charge, the motor envelope, the brakes; ranges the host's menus cover.
const TUNABLES = Dict(
    "racecar" => ["global:soc0" => (0.05, 1.0), "global:x0" => (-1000.0, 1000.0), "global:y0" => (-1000.0, 1000.0),
                  "global:z0" => (0.2, 1.0), "global:yaw0" => (-7.0, 7.0), "MotorR/T_max" => (50.0, 400.0), "MotorR/P_max" => (20.0e3, 300.0e3),
                  "MotorR/P_regen" => (0.0, 250.0e3), "Brakes/Tf" => (500.0, 2500.0), "Brakes/Tr" => (300.0, 2000.0),
                  "Aero/ClA" => (0.0, 4.0)],
    "buggy" => ["global:soc0" => (0.05, 1.0), "global:x0" => (-380.0, 380.0), "global:y0" => (-380.0, 380.0),
                "global:z0" => (-6.0, 8.0), "global:yaw0" => (-7.0, 7.0), "MotorF/T_max" => (30.0, 200.0), "MotorR/T_max" => (30.0, 200.0),
                "MotorF/P_max" => (10.0e3, 80.0e3), "MotorR/P_max" => (10.0e3, 80.0e3),
                "Brakes/Tf" => (500.0, 2500.0), "Brakes/Tr" => (300.0, 2000.0), "Brakes/Th" => (0.0, 2500.0)],
)

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

scenarios(vehicle) = vehicle == "racecar" ? [
    (name = "launch_turn_brake", t_end = 10.0,
     inputs = Dict("throttle" => [(0.5, 1.0), (6.0, 0.3), (7.5, 0.0)], "steer" => [(4.0, 0.15), (6.0, 0.0)],
                   "brake" => [(7.5, 0.6)], "mu_rl" => [(5.0, 0.6)])),
] : [
    (name = "hills_drive", t_end = 10.0,
     inputs = Dict("throttle" => [(0.5, 0.6), (7.0, 0.0)], "steer" => [(3.0, -0.3), (5.0, 0.2)],
                   "brake" => [(7.0, 0.4)], "handbrake" => [(8.5, 1.0)])),
]

function export_vehicle(out, vehicle, with_reference)
    dir = joinpath(out, vehicle)
    mkpath(dir)
    doc = todict(JSON3.read(read(joinpath(PROJECT, "models", "$(vehicle)-sim.bgmodel.json"), String)))
    flat = BGSim.Compile.flatten(BGSim.IR.parse_model(doc); project_dir = PROJECT)
    flat = BGSim.Export.host_inputs(flat)
    tun = TUNABLES[vehicle]
    settings = BGSim.Export.ExportSettings(Dict{String,Any}(
        "t_end" => T_END, "step" => STEP,
        "tunables" => first.(tun), "ranges" => Dict{String,Any}(k => collect(v) for (k, v) in tun)))
    t0 = time()
    res = BGSim.Export.export_model(flat, joinpath(dir, "fmu"); settings, name = "$(vehicle)_sim")
    rec = Dict{String,Any}("vehicle" => vehicle, "ok" => res.ok, "exportS" => time() - t0, "step" => STEP,
        "diagnostics" => [Dict("code" => d.code, "severity" => d.severity, "message" => d.message)
                          for d in res.diagnostics])
    print(stderr, vehicle, " export: ", res.ok ? "ok" : "refused", " (", round(rec["exportS"]; digits = 1), " s)\n")
    for d in res.diagnostics
        print(stderr, "  ", d.code, ": ", first(d.message, 300), "\n")
    end
    if res.ok
        rec["method"] = res.report["method"]
        rec["dt"] = res.report["dt"]
        rec["substeps"] = res.report["substeps"]
        print(stderr, "  method ", rec["method"], ", dt ", rec["dt"], " s, ", rec["substeps"], " substeps\n")
    end
    open(joinpath(dir, "export.jsonl"), "w") do io
        JSON3.write(io, rec)
        println(io)
    end
    (res.ok && with_reference) || return res.ok
    params = Dict(p.id => p for p in flat.parameters)
    markers = BGSim.Export.input_markers(flat)
    for sc in scenarios(vehicle)
        sdir = joinpath(dir, sc.name)
        rm(sdir; force = true, recursive = true)
        mkpath(sdir)
        n = round(Int, sc.t_end / STEP)
        t = collect(0:n) .* STEP
        u = Dict{String,Vector{Float64}}()
        for path in markers
            start = Float64(params[path * "/value"].value)
            ch = get(sc.inputs, path, Tuple{Float64,Float64}[])
            u[path] = [held(start, ch, tk) for tk in t]
        end
        write(joinpath(sdir, "inputs.json"), JSON3.write(Dict("t" => t, "u" => u)))
        t0 = time()
        BGSim.simulate(flat; run_dir = joinpath(sdir, "reference"), settings = Dict{String,Any}(
                "t_end" => sc.t_end, "solver" => "auto", "reltol" => 1e-8, "abstol" => 1e-8,
                "output" => Dict("mode" => "interval", "interval" => STEP)),
            inputs = Dict(path * "/value" => (t, u[path]) for path in markers))
        print(stderr, vehicle, " reference ", sc.name, ": ", round(time() - t0; digits = 1), " s\n")
    end
    return true
end

function main(args)
    out = abspath(args[1])
    with_reference = !("--no-reference" in args)
    vehicles = [a for a in args[2:end] if a in ("racecar", "buggy")]
    isempty(vehicles) && (vehicles = ["racecar", "buggy"])
    mkpath(out)
    ok = true
    for v in vehicles
        ok &= export_vehicle(out, v, with_reference)
    end
    return ok ? 0 : 1
end

exit(main(ARGS))
