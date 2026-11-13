# The microduck-policy FMU and its references (examples/microduck/README.md, "The FMU").
#
#   julia --project=julia/BGSim examples/export_microduck.jl <out_dir> [--no-reference] [--dt S] [--method M]
#                                                            [--reference RUN_DIR] [--model NAME]
#
# NAME is microduck-policy (default) or microduck-policy-backlash (the same robot with microduck_rl's
# 2 deg gear play, XL330Backlash); the FMU is named after it (microduck_policy[_backlash]).
#
# Writes, under <out_dir>:
#   fmu/                  the export of microduck/models/microduck-policy with the policy interface:
#                         the ExportInputPass markers (`<joint>_target`, `kp`) are FMU inputs (the
#                         model's scripted stimulus is cut off, `Export.host_inputs`), the
#                         ExportOutput markers FMU outputs, the supply voltage and the current
#                         limit FMU parameters with their ranges; a 20 ms communication step (one
#                         policy tick) and the internal step DT.
#   <scenario>/reference  a bg-sim run of the same model driven by the scenario's inputs
#                         (zero-order hold at the communication instants), tight tolerances, output
#                         every communication step; <scenario>/inputs.json the inputs.
#   export.jsonl          one line: the export report's method, dt, substeps, the interface.
# `examples/export_microduck_check.py` builds the FMU and compares it in fmpy.

using BGSim
import JSON3

const HERE = @__DIR__
const PROJECT = joinpath(HERE, "microduck")
const STEP = 0.02           # s, one policy tick (50 Hz): the host holds the targets for it
const T_END = 3600.0        # s, the default stop time in the modelDescription (the host runs open-ended)

# FMU parameters (set before initialization): the supply (training randomises 6.5..8.2 V) and the
# firmware current limit (BAM/training 1.75 A, the robot's impact-guard firmware 1.0 A).
const TUNABLES = ["global:v_bat" => (6.5, 8.2), "global:i_limit" => (1.0, 1.75)]
# The backlash model's play (total, rad): 0 closes it, training uses 2 deg; up to 4 deg.
const PLAY_TUNABLE = "global:backlash" => (0.0, deg2rad(4.0))

todict(x::AbstractDict) = Dict{String,Any}(String(k) => todict(v) for (k, v) in pairs(x))
todict(x::AbstractVector) = Any[todict(v) for v in x]
todict(x) = x

const LEGS = ["left_hip_pitch", "left_knee", "left_ankle", "right_hip_pitch", "right_knee", "right_ankle"]

"""Scripted input changes `(t, value)` per input path, piecewise constant after the start value."""
function scenarios(start::Dict{String,Float64}, doc)
    # the squat pose: the `final` of the model's own scripted leg steps (Cmd_<joint>)
    nodes = Dict(String(n["name"]) => n for n in doc["diagram"]["nodes"])
    squat = Dict(j => parse(Float64, String(nodes["Cmd_" * j]["params"]["final"])) for j in LEGS)
    # stand: everything at the start values (HOME, kp 200): the settling and the forward tip of
    # HOME without a policy (the robot passes 40 deg near 1 s, so the runs stop well before)
    stand = (name = "stand", t_end = 0.6, inputs = Dict{String,Vector{Tuple{Float64,Float64}}}())
    # squat: the legs step to the 15 mm squat at 0.2 s, the gain drops to the standing 160 at
    # 0.3 s and back to 200 at 0.45 s, and the head nods (neck_pitch +0.2 rad) at 0.4 s
    moves = Dict{String,Vector{Tuple{Float64,Float64}}}()
    for j in LEGS
        moves[j * "_target"] = [(0.2, Float64(squat[j]))]
    end
    moves["kp"] = [(0.3, 160.0), (0.45, 200.0)]
    moves["neck_pitch_target"] = [(0.4, start["neck_pitch_target"] + 0.2)]
    squatrun = (name = "squat", t_end = 0.6, inputs = moves)
    return [stand, squatrun]
end

function held(start, changes, t)
    v = start
    for (tk, vk) in changes
        t >= tk - 1e-9 && (v = vk)
    end
    return v
end

function main(args)
    out = abspath(args[1])
    with_reference = !("--no-reference" in args)
    getarg(name, default) = (i = findfirst(==(name), args); i === nothing ? default : args[i + 1])
    dt = parse(Float64, getarg("--dt", "0.001"))
    method = getarg("--method", "ros34pw2")
    model = getarg("--model", "microduck-policy")
    mkpath(out)
    doc = todict(JSON3.read(read(joinpath(PROJECT, "models", model * ".bgmodel.json"), String)))
    flat = BGSim.Compile.flatten(BGSim.IR.parse_model(doc); project_dir = PROJECT)
    flat = BGSim.Export.host_inputs(flat)
    tunables = any(g -> g["name"] == "backlash", doc["parameters"]) ? [TUNABLES; PLAY_TUNABLE] : TUNABLES

    settings = BGSim.Export.ExportSettings(Dict{String,Any}(
        "t_end" => T_END, "step" => STEP, "dt" => dt, "method" => method,
        "tunables" => first.(tunables), "ranges" => Dict{String,Any}(k => v for (k, v) in tunables)))
    t0 = time()
    # `--reference DIR`: a bg-sim run of this model (hosted inputs) whose states the export
    # scans besides the start: the spectrum, and the weights of the static LU's row matching
    # (a pivot chosen at the start alone can vanish once the policy moves the robot).
    reference = getarg("--reference", nothing)
    res = BGSim.Export.export_model(flat, joinpath(out, "fmu"); settings, name = replace(model, "-" => "_"),
        reference_dir = reference)
    rec = Dict{String,Any}("ok" => res.ok, "exportS" => time() - t0, "step" => STEP, "model" => model,
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

    params = Dict(p.id => p for p in flat.parameters)
    markers = BGSim.Export.input_markers(flat)
    start = Dict{String,Float64}(path => Float64(params[path * "/value"].value) for path in markers)
    for sc in scenarios(start, doc)
        dir = joinpath(out, sc.name)
        rm(dir; force = true, recursive = true)
        mkpath(dir)
        n = round(Int, sc.t_end / STEP)
        t = collect(0:n) .* STEP
        u = Dict{String,Vector{Float64}}()
        for path in markers
            ch = get(sc.inputs, path, Tuple{Float64,Float64}[])
            u[path] = [held(start[path], ch, tk) for tk in t]
        end
        write(joinpath(dir, "inputs.json"), JSON3.write(Dict("t" => t, "u" => u, "params" => Dict{String,Float64}())))
        t0 = time()
        BGSim.simulate(flat; run_dir = joinpath(dir, "reference"), settings = Dict{String,Any}(
                "t_end" => sc.t_end, "solver" => "Rodas5P", "reltol" => 1e-6, "abstol" => 1e-8,
                "output" => Dict("mode" => "interval", "interval" => STEP)),
            inputs = Dict(path * "/value" => (t, u[path]) for path in markers))
        print(stderr, "reference ", sc.name, ": ", round(time() - t0; digits = 1), " s\n")
    end
    return 0
end

exit(main(ARGS))
