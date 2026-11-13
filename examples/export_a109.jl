# The a109-sim FMU of the A109 web game (apps/web/build_fmu.py runs this).
#
#   julia --project=julia/BGSim examples/export_a109.jl <out_dir> [--method=rk4] [--dt=0.00125]
#
# Exports examples/a109/models/a109-sim with the host interface into <out_dir>/fmu:
#   * the ExportInputPass markers are FMU inputs: collective, cyclic_lon, cyclic_lat, pedals, the
#     wind (wind_n, wind_e, wind_d) and the SCAS switch (scas). The model's demonstration pilot
#     is cut off (`Export.host_inputs`);
#   * the ExportOutput markers are FMU outputs (pose, attitude, rates, air data, rotor, power,
#     flapping, blade angles, wheel loads, weight on wheels);
#   * TUNABLES below (the start state, set together: the hover trim, a forward-flight trim or the
#     helicopter parked on its gear) are FMU parameters with their ranges.
# The internal method and step: the analysis picks them at the model's default start (the hover at
# 15 m, where the gear carries nothing), so the host's export fixes them for the stiffest case,
# the gear on the ground (`--method`, `--dt`; build_fmu.py passes RK4 at 1.25 ms).
# <out_dir>/export.jsonl gets one line: ok, method, dt, substeps, the diagnostics.

using BGSim
import JSON3

const HERE = @__DIR__
const PROJECT = joinpath(HERE, "a109")
const STEP = 0.005          # s, the host's communication step (200 Hz)
const T_END = 3600.0        # s, the default stop time in the modelDescription (the host runs open-ended)

# FMU parameters: the start state (examples/a109/design/build_model.py, SIM_START). Ranges: every
# start of the game's start list (apps/web/src/a109/starts.json), with margin.
const TUNABLES = [
    "global:qw0" => (-1.0, 1.0), "global:qx0" => (-1.0, 1.0), "global:qy0" => (-1.0, 1.0), "global:qz0" => (-1.0, 1.0),
    "global:x0" => (-20000.0, 20000.0), "global:y0" => (-20000.0, 20000.0), "global:z0" => (0.5, 3000.0),
    "global:Pwx0" => (-50000.0, 50000.0), "global:Pwy0" => (-50000.0, 50000.0), "global:Pwz0" => (-50000.0, 50000.0),
    "global:Pvx0" => (-300000.0, 300000.0), "global:Pvy0" => (-300000.0, 300000.0), "global:Pvz0" => (-300000.0, 300000.0),
    "global:a10" => (-0.3, 0.3), "global:b10" => (-0.3, 0.3), "global:Lrot0" => (20000.0, 80000.0),
    "global:xi0" => (-30000.0, 30000.0),
]

todict(x::AbstractDict) = Dict{String,Any}(String(k) => todict(v) for (k, v) in pairs(x))
todict(x::AbstractVector) = Any[todict(v) for v in x]
todict(x) = x

function option(args, name, default)
    for a in args
        startswith(a, "--$name=") && return a[length(name) + 4:end]
    end
    return default
end

function main(args)
    out = abspath(args[1])
    mkpath(out)
    doc = todict(JSON3.read(read(joinpath(PROJECT, "models", "a109-sim.bgmodel.json"), String)))
    flat = BGSim.Compile.flatten(BGSim.IR.parse_model(doc); project_dir = PROJECT)
    flat = BGSim.Export.host_inputs(flat)
    s = Dict{String,Any}("t_end" => T_END, "step" => STEP, "tunables" => first.(TUNABLES),
                         "ranges" => Dict{String,Any}(k => v for (k, v) in TUNABLES))
    method = option(args, "method", "auto")
    s["method"] = method
    dt = option(args, "dt", "")
    isempty(dt) || (s["dt"] = parse(Float64, dt))
    t0 = time()
    res = BGSim.Export.export_model(flat, joinpath(out, "fmu"); settings = BGSim.Export.ExportSettings(s),
                                    name = "a109_sim")
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
    return res.ok ? 0 : 1
end

exit(main(ARGS))
