# J-EX8 acceptance: FMU parameters set before initialization (plan/EXPORT_PLAN.md J-EX8, W-EX1;
# plan/GLOBAL_PARAMETERS.md "Expose global parameters as FMU parameters").
#
#   julia --project=julia/BGSim examples/export_tunables.jl <out_root> [case ...]
#
# For each case it writes, under <out_root>/<case>/:
#   tunable/    the export with the tunables (fixed parameters with ranges, or exposed globals)
#   folded/     the same model folded at the model's values (the step time and op baseline)
#   reference/  a Julia run with the changed values (tight tolerances, output every step)
#   override/   (globals case) a folded export with the changed global values, same dt/method
# and one JSON line in <out_root>/cases.jsonl with the values to set and the out-of-range probe.
# `examples/export_tunables_check.py` builds the FMUs and compares.

using BGSim
import JSON3

const EXAMPLES = @__DIR__

todict(x::AbstractDict) = Dict{String,Any}(String(k) => todict(v) for (k, v) in pairs(x))
todict(x::AbstractVector) = Any[todict(v) for v in x]
todict(x) = x

load(project, model) = todict(JSON3.read(read(joinpath(EXAMPLES, project, "models",
    model * ".bgmodel.json"), String)))

function node!(doc, path)
    parts = split(path, "/")
    nodes = doc["diagram"]["nodes"]
    for (k, name) in enumerate(parts)
        n = only(filter(n -> n["name"] == name, nodes))
        k == length(parts) && return n
        nodes = n["block"]["subsystem"]["diagram"]["nodes"]
    end
end

function set_params!(doc, values)
    for (id, v) in values
        k = findlast('/', id)
        inst, name = id[1:k - 1], id[k + 1:end]
        get!(node!(doc, inst), "params", Dict{String,Any}())[name] = repr(Float64(v))
    end
    return doc
end

# dc-motor/speed-control with the motor parameters as globals: Rm and Jr independent, the
# inductance a driven global (Lm = 2.5e-4 Rm), so exposing Rm makes Motor1/L calculated.
function speed_control_globals()
    doc = load("dc-motor", "speed-control")
    doc["name"] = "speed-control-globals"
    doc["parameters"] = Any[
        Dict{String,Any}("name" => "Rm", "value" => "2.0", "unit" => "Ohm", "description" => "winding resistance"),
        Dict{String,Any}("name" => "Lm", "value" => "2.5e-4*Rm", "unit" => "H", "description" => "winding inductance"),
        Dict{String,Any}("name" => "Jr", "value" => "1e-5", "unit" => "kg*m^2", "description" => "rotor inertia"),
    ]
    motor = node!(doc, "Motor1")
    motor["params"]["R"] = "Rm"
    motor["params"]["L"] = "Lm"
    motor["params"]["J"] = "Jr"
    return doc
end

const CASES = [
    (name = "speed-control", project = "dc-motor", doc = () -> load("dc-motor", "speed-control"),
     tunables = Dict("Motor1/R" => (1.0, 4.0), "Motor1/J" => (5e-6, 4e-5)),
     values = Dict("Motor1/R" => 3.0, "Motor1/J" => 2e-5),
     outside = ("Motor1/R", 5.0), globals = false),
    (name = "drivetrain-kalman", project = "drivetrain-kalman",
     doc = () -> load("drivetrain-kalman", "drivetrain-kalman"),
     tunables = Dict("IW1/i" => (5e-4, 2e-3), "R/r" => (0.5, 2.0), "IJm/i" => (2.5e-5, 1e-4)),
     values = Dict("IW1/i" => 1.5e-3, "R/r" => 1.5, "IJm/i" => 7e-5),
     outside = ("IJm/i", 1e-3), globals = false),
    (name = "speed-control-globals", project = "dc-motor", doc = speed_control_globals,
     tunables = Dict("global:Rm" => (1.0, 4.0), "global:Jr" => (5e-6, 4e-5)),
     values = Dict("global:Rm" => 3.0, "global:Jr" => 2e-5),
     outside = ("global:Jr", 1e-4), globals = true),
]

fmi_name(id) = startswith(id, "global:") ? id[8:end] : id

function export_dir(flat, dir, settings; ref = nothing)
    t0 = time()
    r = BGSim.Export.export_model(flat, dir; settings, reference_dir = ref)
    return r, time() - t0
end

function run_case(out_root, c)
    dir = joinpath(out_root, c.name)
    rm(dir; force = true, recursive = true)
    mkpath(dir)
    proj = joinpath(EXAMPLES, c.project)
    doc = c.doc()
    t_end = Float64(doc["settings"]["t_end"])
    step = 1e-3
    md = BGSim.IR.parse_model(doc)
    flat = BGSim.Compile.flatten(md; project_dir = proj)
    rec = Dict{String,Any}("case" => c.name, "dir" => dir, "tEnd" => t_end, "step" => step,
        "values" => Dict(fmi_name(k) => v for (k, v) in c.values),
        "outside" => Dict(fmi_name(c.outside[1]) => c.outside[2]))

    # The reference: the model with the changed values, run in Julia.
    rdoc = deepcopy(doc)
    rmd = if c.globals
        BGSim.IR.override_globals(BGSim.IR.parse_model(rdoc), Dict(k => v for (k, v) in c.values))
    else
        BGSim.IR.parse_model(set_params!(rdoc, c.values))
    end
    rflat = BGSim.Compile.flatten(rmd; project_dir = proj)
    t0 = time()
    BGSim.simulate(rflat; run_dir = joinpath(dir, "reference"), settings = Dict{String,Any}(
        "t_end" => t_end, "solver" => "auto", "reltol" => 1e-8, "abstol" => 1e-10,
        "output" => Dict("mode" => "interval", "interval" => step)))
    rec["referenceS"] = time() - t0

    base = Dict{String,Any}("t_end" => t_end, "step" => step, "expose_all" => true)
    folded, rec["foldedExportS"] = export_dir(flat, joinpath(dir, "folded"),
        BGSim.Export.ExportSettings(base))
    folded.ok || error("$(c.name): the folded export was refused")
    tset = merge(base, Dict{String,Any}(
        "tunables" => collect(keys(c.tunables)),
        "ranges" => Dict{String,Any}(k => v for (k, v) in c.tunables)))
    tun, rec["tunableExportS"] = export_dir(flat, joinpath(dir, "tunable"),
        BGSim.Export.ExportSettings(tset))
    rec["ok"] = tun.ok
    rec["diagnostics"] = [Dict("code" => d.code, "message" => d.message)
                          for d in tun.diagnostics if d.code != "W203"]
    tun.ok || return rec
    rec["method"] = tun.report["method"]
    rec["dt"] = tun.report["dt"]
    rec["foldedMethod"] = folded.report["method"]
    rec["foldedDt"] = folded.report["dt"]
    if c.globals
        # (b) the folded export with the changed globals, at the tunable export's step.
        oflat = BGSim.Compile.flatten(rmd; project_dir = proj)
        over, _ = export_dir(oflat, joinpath(dir, "override"), BGSim.Export.ExportSettings(merge(
            base, Dict{String,Any}("dt" => tun.report["dt"], "method" => tun.report["method"]))))
        over.ok || error("$(c.name): the override export was refused")
    end
    # (c) a range that leaves out the model's value is refused at export (E110).
    bad = merge(tset, Dict{String,Any}("ranges" => Dict{String,Any}(
        k => (v[2] * 2, v[2] * 3) for (k, v) in c.tunables)))
    rb = BGSim.Export.export_model(flat, joinpath(dir, "bad"); settings = BGSim.Export.ExportSettings(bad))
    rec["badRangeRefused"] = !rb.ok && any(d -> d.code == "E110", rb.diagnostics)
    rm(joinpath(dir, "bad"); force = true, recursive = true)
    return rec
end

function main(args)
    out_root = abspath(args[1])
    mkpath(out_root)
    only_cases = args[2:end]
    open(joinpath(out_root, "cases.jsonl"), "w") do io
        for c in CASES
            isempty(only_cases) || c.name in only_cases || continue
            print(stderr, "case ", c.name, " ... ")
            flush(stderr)
            rec = run_case(out_root, c)
            println(stderr, rec["ok"] ? "exported" : "refused")
            JSON3.write(io, rec)
            println(io)
            flush(io)
        end
    end
end

main(ARGS)
