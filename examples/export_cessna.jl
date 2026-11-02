# The cessna-sim FMU and its references (the cessna-sim host's FMU; examples/cessna/README.md, "The FMU").
#
#   julia --project=julia/BGSim examples/export_cessna.jl <out_dir> [--no-reference]
#
# Writes, under <out_dir>:
#   fmu/                  the export of models/cessna-sim with the host interface: the ExportInputPass
#                         markers are FMU inputs (the model's demo pilot is cut off,
#                         `Export.host_inputs`), the ExportOutput markers FMU outputs, and the
#                         TUNABLES below (the start state, set together from a trim or the runway
#                         equilibrium) FMU parameters with their ranges. The analysis picks the method
#                         and the internal step for the 5 ms communication step.
#   <scenario>/reference  a bg-sim run of the same flattened model driven by the scenario's
#                         inputs (zero-order hold at the communication instants), tight tolerances,
#                         output every communication step; <scenario>/inputs.json the inputs.
#   export.jsonl          one line: the export report's method, dt, substeps, the interface.
# `examples/export_cessna_check.py` builds the FMU and compares it in fmpy.

using BGSim
import JSON3

const HERE = @__DIR__
const PROJECT = joinpath(HERE, "cessna")
const STEP = 0.005          # s, the host's communication step (200 Hz)
const T_END = 3600.0        # s, the default stop time in the modelDescription (the host runs open-ended)

# FMU parameters: the start state (pose, body momentum, crankshaft momentum, manifold pressure,
# alpha filter, flap angle, strut compressions; design/design.py's `state_starts` sets them
# together). Ranges: the runway start and the airborne trims of the host's start list.
const TUNABLES = [
    "global:qw0" => (-1.0, 1.0), "global:qx0" => (-1.0, 1.0), "global:qy0" => (-1.0, 1.0), "global:qz0" => (-1.0, 1.0),
    "global:x0" => (-20000.0, 20000.0), "global:y0" => (-20000.0, 20000.0), "global:z0" => (0.0, 4000.0),
    "global:Pwx0" => (-20000.0, 20000.0), "global:Pwy0" => (-20000.0, 20000.0), "global:Pwz0" => (-20000.0, 20000.0),
    "global:Pvx0" => (-100000.0, 100000.0), "global:Pvy0" => (-100000.0, 100000.0), "global:Pvz0" => (-100000.0, 100000.0),
    "global:hrot0" => (0.0, 1000.0), "global:map0" => (20000.0, 110000.0), "global:xad0" => (-1.0, 1.0),
    "global:flap0" => (0.0, 30.0), "global:qn0" => (-5000.0, 0.5), "global:ql0" => (-5000.0, 0.5),
    "global:qr0" => (-5000.0, 0.5),
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

# From the runway start (engine idle, flaps 10): a full-power take-off roll with the brakes
# released, a rotation and a pedal input; a braked run-up; and the autopilot.
const SCENARIOS = [
    (name = "takeoff_roll", t_end = 25.0,
     inputs = Dict("throttle" => [(1.0, 0.5), (2.0, 1.0)], "pedals" => [(12.0, 0.2), (13.0, 0.0)],
                   "yoke_pitch" => [(20.0, 0.6)])),
    # the run-up trims nose down: with nose-up trim, the static propwash of the POH-fitted
    # propeller over the elevator lifts the nose wheel at full throttle on the brakes, and the
    # model (no tail contact) then pitches far up
    (name = "runup_brakes", t_end = 12.0,
     inputs = Dict("brake_l" => [(0.5, 1.0)], "brake_r" => [(0.5, 1.0)], "throttle" => [(1.0, 1.0), (8.0, 0.0)],
                   "mixture" => [(6.0, 0.8)], "flaps" => [(2.0, 0.0), (5.0, 3.0)], "trim" => [(3.0, -0.5)])),
    (name = "steer_wind", t_end = 15.0,
     inputs = Dict("throttle" => [(0.5, 0.6)], "pedals" => [(4.0, -1.0), (7.0, 1.0), (10.0, 0.0)],
                   "brake_l" => [(11.0, 0.6)], "wind_n" => [(2.0, -3.0)], "wind_e" => [(2.0, 2.0)])),
]

function main(args)
    out = abspath(args[1])
    with_reference = !("--no-reference" in args)
    mkpath(out)
    doc = todict(JSON3.read(read(joinpath(PROJECT, "models", "cessna-sim.bgmodel.json"), String)))
    flat = BGSim.Compile.flatten(BGSim.IR.parse_model(doc); project_dir = PROJECT)
    flat = BGSim.Export.host_inputs(flat)

    settings = BGSim.Export.ExportSettings(Dict{String,Any}(
        "t_end" => T_END, "step" => STEP,
        "tunables" => first.(TUNABLES), "ranges" => Dict{String,Any}(k => v for (k, v) in TUNABLES)))
    t0 = time()
    res = BGSim.Export.export_model(flat, joinpath(out, "fmu"); settings, name = "cessna_sim")
    rec = Dict{String,Any}("ok" => res.ok, "exportS" => time() - t0, "step" => STEP,
        "diagnostics" => [Dict("code" => d.code, "severity" => d.severity, "message" => d.message)
                          for d in res.diagnostics])
    print(stderr, "export: ", res.ok ? "ok" : "refused", " (", round(rec["exportS"]; digits = 1), " s)\n")
    for d in res.diagnostics
        print(stderr, "  ", d.code, " ", d.severity, ": ", d.message, "\n")
    end
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
    for sc in SCENARIOS
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
