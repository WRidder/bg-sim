# The AIM-9X FMU of the f16-sim host (examples/aim9x/README.md, "The FMU").
#
#   julia --project=julia/BGSim examples/export_aim9x.jl <out_dir>
#
# Writes, under <out_dir>:
#   fmu/                  the export of models/aim9x-fmu: the target and seeker inputs are
#                         ExportInput markers, the missile pose/status are ExportOutput markers,
#                         the launch state and guidance limits are FMU parameters (TUNABLES),
#                         at RK4 and the internal step DT. The model has no StopSimulation: the
#                         host latches `fuze`/`hit` and retires the instance.
#   export.jsonl          one line: the export report's method, dt, substeps and status.
#
# The target inputs are launch-relative NED (north/east relative to the launch point, down
# absolute), as documented by library/ExternalTarget.jl. `apps/web/build_fmu.py` builds it
# with bgsim_server.fmu_build; the F-16 game (`apps/web`) runs one instance per missile.

using BGSim
import JSON3

const HERE = @__DIR__
const PROJECT = joinpath(HERE, "aim9x")
const MODEL = "aim9x-fmu"
const STEP = 0.005          # s, the host's communication step (200 Hz)
const DT = 0.001            # s, RK4 inside the step
const T_END = 10.0          # s, only the modelDescription's default stop time

# The launch state and the guidance limits: set before initialization, one instance per shot.
const TUNABLES = [
    "global:vt0" => (100.0, 700.0), "global:h0" => (0.0, 20000.0),
    "global:alpha0" => (-5.0, 20.0), "global:tvc_on" => (0.0, 1.0),
    "global:nav_N" => (2.0, 6.0), "global:a_max_g" => (20.0, 80.0),
]

todict(x::AbstractDict) = Dict{String,Any}(String(k) => todict(v) for (k, v) in pairs(x))
todict(x::AbstractVector) = Any[todict(v) for v in x]
todict(x) = x

function main(args)
    out = abspath(args[1])
    mkpath(out)
    doc = todict(JSON3.read(read(joinpath(PROJECT, "models", MODEL * ".bgmodel.json"), String)))
    flat = BGSim.Compile.flatten(BGSim.IR.parse_model(doc); project_dir = PROJECT)
    flat = BGSim.Export.host_inputs(flat)
    settings = BGSim.Export.ExportSettings(Dict{String,Any}(
        "t_end" => T_END, "step" => STEP, "dt" => DT,
        "tunables" => first.(TUNABLES),
        "ranges" => Dict{String,Any}(k => v for (k, v) in TUNABLES)))
    t0 = time()
    res = BGSim.Export.export_model(flat, joinpath(out, "fmu"); settings, name = "aim9x_fmu")
    rec = Dict{String,Any}("ok" => res.ok, "exportS" => time() - t0, "step" => STEP,
        "diagnostics" => [Dict("code" => d.code, "severity" => d.severity, "message" => d.message,
                               "hint" => d.hint) for d in res.diagnostics])
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
    return res.ok ? 0 : 1
end

exit(main(ARGS))
