# The beaver-sim FMU and its references (examples/beaver/README.md, "The FMU").
#
#   julia --project=julia/BGSim examples/export_beaver.jl <out_dir> [--no-reference]
#
# Writes, under <out_dir>:
#   fmu/                  the export of models/beaver-sim with the host interface: the ExportInputPass
#                         markers are FMU inputs (the model's demo stimulus is cut off,
#                         `Export.host_inputs`), the ExportOutput markers FMU outputs, and the
#                         TUNABLES below FMU parameters with their ranges. The analysis picks the
#                         method and the internal step for the 5 ms communication step.
#   <scenario>/reference  a bg-sim run of the same flattened model driven by the scenario's
#                         inputs (zero-order hold at the communication instants), tight tolerances,
#                         output every communication step; <scenario>/inputs.json the inputs.
#   export.jsonl          one line: the export report's method, dt, substeps, the interface.
# `examples/export_beaver_check.py` builds the FMU and compares it in fmpy.

using BGSim
import JSON3

const HERE = @__DIR__
const PROJECT = joinpath(HERE, "beaver")
const STEP = 0.005          # s, the communication step (200 Hz)
const T_END = 3600.0        # s, the default stop time in the modelDescription (a host runs open-ended)

# FMU parameters: the drivetrain switch (1 the bond-graph drivetrain, 0 the source's algebraic
# power) and the aileron and rudder trim offsets.
const TUNABLES = ["global:drivetrain" => (0.0, 1.0), "global:ail_trim" => (-5.0, 5.0),
                  "global:rud_trim" => (-5.0, 5.0)]

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

function scenarios(globals, starts)
    pz0, n0, th0, h0 = starts["pz_inhg"], starts["rpm"], starts["theta_ref_deg"], starts["h_ref_m"]
    return [
        # the model's demo as held inputs: climb, turn to 090, level-off 150 m up, cruise power
        (name = "demo", t_end = 150.0,
         inputs = Dict("pz_inhg" => [(5.0, globals["climb_pz"]), (85.0, pz0)],
                       "rpm" => [(5.0, globals["climb_rpm"]), (85.0, n0)],
                       "theta_ref_deg" => [(5.0, th0 + globals["climb_dtheta"])],
                       "ap_roll" => [(30.0, 2.0)], "psi_ref_deg" => [(30.0, globals["turn_psi"])],
                       "ap_pitch" => [(70.0, 2.0)], "h_ref_m" => [(70.0, h0 + globals["level_dh"])])),
        # hand flown: autopilot off, a column doublet, a roll and back, a pedal pulse
        (name = "hand_flown", t_end = 30.0,
         inputs = Dict("ap_pitch" => [(0.0, 0.0)], "ap_roll" => [(0.0, 0.0)],
                       "col_pitch" => [(2.0, 0.1), (4.0, -0.1), (6.0, 0.0)],
                       "col_roll" => [(10.0, 0.15), (12.0, 0.0), (16.0, -0.15), (18.0, 0.0)],
                       "pedals" => [(22.0, 0.2), (24.0, 0.0)])),
        # on the autopilot: flaps 10 deg and a wind change, the rpm lever back
        (name = "flaps_wind", t_end = 40.0,
         inputs = Dict("flaps_deg" => [(2.0, 10.0)], "wind_n" => [(10.0, -3.0)], "wind_e" => [(15.0, 2.0)],
                       "rpm" => [(25.0, 1700.0)])),
    ]
end

function main(args)
    out = abspath(args[1])
    with_reference = !("--no-reference" in args)
    mkpath(out)
    doc = todict(JSON3.read(read(joinpath(PROJECT, "models", "beaver-sim.bgmodel.json"), String)))
    globals = Dict(String(g["name"]) => parse(Float64, String(g["value"])) for g in doc["parameters"])
    flat = BGSim.Compile.flatten(BGSim.IR.parse_model(doc); project_dir = PROJECT)
    flat = BGSim.Export.host_inputs(flat)

    settings = BGSim.Export.ExportSettings(Dict{String,Any}(
        "t_end" => T_END, "step" => STEP,
        "tunables" => first.(TUNABLES), "ranges" => Dict{String,Any}(k => v for (k, v) in TUNABLES)))
    t0 = time()
    res = BGSim.Export.export_model(flat, joinpath(out, "fmu"); settings, name = "beaver_sim")
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
    starts = Dict(path => Float64(params[path * "/value"].value) for path in markers)
    for sc in scenarios(globals, starts)
        dir = joinpath(out, sc.name)
        rm(dir; force = true, recursive = true)
        mkpath(dir)
        n = round(Int, sc.t_end / STEP)
        t = collect(0:n) .* STEP
        u = Dict{String,Vector{Float64}}()
        for path in markers
            ch = get(sc.inputs, path, Tuple{Float64,Float64}[])
            u[path] = [held(starts[path], ch, tk) for tk in t]
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
