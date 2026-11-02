# R0.1 (plan/RL_PLAN.md): export the plant-only double cart as an FMU with its physical
# parameters exposed (globals with ranges, set before initialisation).
#
#   julia --project=julia/BGSim rl/export_plant.jl <out_dir> [--rig=cart|lab] [--no-reference]
#         [--t-end=3] [--settings=<json>]   default {"method": "rodas4p", "dt": 1e-3}
#
# --rig=cart (default): examples/pendulum-double-cart, model pendulum-double-cart-plant, the
# ranges below. --rig=lab (R0.7): examples/pendulum-double-cart-lab, model
# pendulum-double-cart-lab-plant, the exposed globals and ranges of its design/realism.json
# (design/rl_ranges.json, written by its design/rlmodels.py).
#
# The automatic step rule (D-EX7) resolves every lightly damped mode, and this plant has the
# parasitic ones of its compliant joints (pivot springs kt = 1e8 N/m, the rail's rotation
# spring): |lambda| up to 1.05e5 1/s, so `auto` picks RK4 at 2.5 us (400 substeps per ms,
# 942 us per doStep estimated). Those modes stand for rigid joints, so the RL export fixes the
# L-stable, stiffly accurate Rodas4P at 1 ms, which damps them; build_plant.py measures the
# error against Rodas5P (mechanics 1.4e-4 of the peak; ROS2 at 0.5 ms: 1e-2).
#
# Writes under <out_dir>:
#   export/         the FMU sources, modelDescription.xml, export.json (markers only)
#   reference/      a Julia run (Rodas5P, reltol 1e-8) driven by the voltage trajectory
#   reference_mod/  the same with changed globals (MODIFIED below), for the before-init check
#   inputs.json     the voltage trajectory (zero-order hold at the communication instants)
#   case.json       the globals, ranges, the modified values and the timings
# `rl/build_plant.py` builds the FMU and compares it with the references in fmpy.

using BGSim
import JSON3

const ROOT = normpath(joinpath(@__DIR__, ".."))
const RIGS = Dict(
    "cart" => (joinpath(ROOT, "examples", "pendulum-double-cart"), "pendulum-double-cart-plant"),
    "lab" => (joinpath(ROOT, "examples", "pendulum-double-cart-lab"), "pendulum-double-cart-lab-plant"))

# The ranges of the exposed globals: kept in one place, the table of
# examples/pendulum-double-cart/design/rlmodels.py (GLOBALS), copied here as id => (min, max).
const RANGES = Dict(
    "m_cart" => (0.6, 1.0), "m1" => (0.08, 0.12), "m2" => (0.064, 0.096),
    "L1" => (0.23, 0.27), "L2" => (0.23, 0.27), "b1" => (5.0e-5, 1.0e-3), "b2" => (5.0e-5, 1.0e-3),
    "R_m" => (1.2, 1.9), "k_t" => (0.027, 0.033), "J_m" => (1.1e-5, 1.7e-5), "b_m" => (0.0, 1.0e-5))

# Values set before initialisation in the second check (inside the ranges, away from nominal).
const MODIFIED = Dict("m1" => 0.115, "m2" => 0.07, "L1" => 0.26, "b1" => 6e-4, "R_m" => 1.8,
    "m_cart" => 0.7)
const MODIFIED_LAB = Dict("m_tube1" => 0.11, "m_head1" => 0.112, "m_tip2" => 0.044, "L1" => 0.351,
    "com_shift2" => 0.015, "b_joint1" => 5e-4, "R_m" => 1.7, "m_cart" => 0.78, "k_belt" => 3.0e5,
    # R1: the realism forces of library/LabRealism.jl
    "tc_joint2" => 4e-4, "tc_carriage" => 1.6, "ripple_rel" => 0.035, "cogging" => 0.4, "k_cable" => 2.5e-4)

function rig_setup(rig)
    project, model = RIGS[rig]
    rig == "cart" && return project, model, RANGES, MODIFIED
    raw = JSON3.read(read(joinpath(project, "design", "rl_ranges.json"), String))
    ranges = Dict(String(k) => (Float64(v[1]), Float64(v[2])) for (k, v) in pairs(raw))
    return project, model, ranges, MODIFIED_LAB
end

todict(x::AbstractDict) = Dict{String,Any}(String(k) => todict(v) for (k, v) in pairs(x))
todict(x::AbstractVector) = Any[todict(v) for v in x]
todict(x) = x

mutable struct SplitMix
    s::UInt64
end
function next!(r::SplitMix)
    r.s += 0x9e3779b97f4a7c15
    z = r.s
    z = (z ⊻ (z >> 30)) * 0xbf58476d1ce4e5b9
    z = (z ⊻ (z >> 27)) * 0x94d049bb133111eb
    return z ⊻ (z >> 31)
end
uniform!(r::SplitMix) = (next!(r) >> 11) * 2.0^-53

# A voltage that excites the plant without driving the cart far: 0.2 s at rest, then levels in
# [-6, 6] V held 20 to 120 ms (a PRBS-like sequence), mean-reverting on the cart position is not
# possible open loop, so the horizon is short.
function voltage_trajectory(t_end, step)
    n = round(Int, t_end / step)
    t = [k * step for k in 0:n]
    u = zeros(length(t))
    rng = SplitMix(0x5eed)
    level, left = 0.0, 0
    for k in eachindex(t)
        if t[k] >= 0.2
            if left <= 0
                level = -6.0 + 12.0 * uniform!(rng)
                left = 20 + floor(Int, 100 * uniform!(rng))
            end
            left -= 1
            u[k] = level
        end
    end
    return t, u
end

function main(args)
    out = abspath(args[1])
    mkpath(out)
    with_ref = !("--no-reference" in args)
    t_end = 3.0
    overrides = Dict{String,Any}("method" => "rodas4p", "dt" => 1.0e-3)
    rig = "cart"
    for a in args
        startswith(a, "--t-end=") && (t_end = parse(Float64, a[9:end]))
        startswith(a, "--rig=") && (rig = a[7:end])
        startswith(a, "--settings=") && merge!(overrides, todict(JSON3.read(a[12:end])))
    end
    step = 1e-3
    PROJECT, MODEL, RANGES, MODIFIED = rig_setup(rig)
    doc = todict(JSON3.read(read(joinpath(PROJECT, "models", MODEL * ".bgmodel.json"), String)))
    rec = Dict{String,Any}("tEnd" => t_end, "step" => step, "rig" => rig,
        "ranges" => Dict(k => [v[1], v[2]] for (k, v) in RANGES), "modified" => MODIFIED)

    t0 = time()
    md = BGSim.IR.parse_model(doc)
    flat = BGSim.Export.host_inputs(BGSim.Compile.flatten(md; project_dir = PROJECT))
    rec["flattenS"] = time() - t0
    t, u = voltage_trajectory(t_end, step)
    write(joinpath(out, "inputs.json"), JSON3.write(Dict("t" => t, "u" => Dict("V" => u))))
    inputs = Dict("V/value" => (t, u))
    run_settings = Dict{String,Any}("t_end" => t_end, "solver" => "Rodas5P", "reltol" => 1e-8,
        "abstol" => 1e-10, "output" => Dict("mode" => "interval", "interval" => step))
    ref_dir = nothing
    if with_ref
        ref_dir = joinpath(out, "reference")
        t0 = time()
        BGSim.simulate(flat; run_dir = ref_dir, settings = run_settings, inputs)
        rec["referenceS"] = time() - t0
        over = Dict{String,Any}("global:" * k => v for (k, v) in MODIFIED)
        mflat = BGSim.Export.host_inputs(BGSim.Compile.flatten(
            BGSim.IR.override_globals(BGSim.IR.parse_model(doc), over); project_dir = PROJECT))
        t0 = time()
        BGSim.simulate(mflat; run_dir = joinpath(out, "reference_mod"), settings = run_settings, inputs)
        rec["referenceModS"] = time() - t0
    end

    rec["overrides"] = overrides
    settings = BGSim.Export.ExportSettings(merge(Dict{String,Any}(
        "t_end" => t_end, "step" => step,
        "tunables" => ["global:" * k for k in keys(RANGES)],
        "ranges" => Dict{String,Any}("global:" * k => v for (k, v) in RANGES)), overrides))
    t0 = time()
    res = BGSim.Export.export_model(flat, joinpath(out, "export"); settings,
        reference_dir = ref_dir, name = replace(MODEL, "-" => "_"))
    rec["exportS"] = time() - t0
    rec["ok"] = res.ok
    rec["diagnostics"] = [Dict("code" => d.code, "severity" => d.severity, "message" => d.message)
                          for d in res.diagnostics]
    if res.ok
        rec["method"] = res.report["method"]
        rec["dt"] = res.report["dt"]
    end
    write(joinpath(out, "case.json"), JSON3.write(rec))
    println(stderr, "export ", res.ok ? "ok" : "refused", ": ",
        res.ok ? "$(res.report["method"]) dt=$(res.report["dt"])" : "",
        " in ", round(rec["exportS"]; digits = 1), " s")
    for d in res.diagnostics
        println(stderr, "  ", d.code, " ", d.message)
    end
end

main(ARGS)
