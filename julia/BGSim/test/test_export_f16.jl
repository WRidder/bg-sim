# The f16-sim FMU of examples/f16 (the FMU of the apps/web host): the export with the host's
# interface and settings (examples/export_f16.jl) is accepted, RK4 at the 5 ms communication step
# with one substep, the ExportInputPass markers are the FMU inputs and the ExportOutput markers its
# outputs, the trim globals, CG, mass and law switches are FMU parameters (every start computed
# from them is recomputed at initialization), and the flattened host model (stimulus cut off,
# inputs at their start values) holds its trim. The fmpy comparison against bg-sim on four
# manoeuvres, the build and the doStep timing are `examples/export_f16_check.py`.

using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import JSON3

const _F16_PROJECT = normpath(joinpath(@__DIR__, "..", "..", "..", "examples", "f16"))
const _F16_INPUTS = ["stick_pitch", "stick_roll", "pedals", "throttle", "wind_n", "wind_e", "wind_d",
                     "gear_cmd", "brake_l", "brake_r"]
const _F16_GLOBALS = ["vt0", "h0", "alpha0", "el0", "thtl0", "xcg", "mass", "limiter", "turn_comp",
                      "roll_law", "yaw_damper", "beta_hold", "ari", "vv_roll"]

_f16_todict(x::AbstractDict) = Dict{String,Any}(String(k) => _f16_todict(v) for (k, v) in pairs(x))
_f16_todict(x::AbstractVector) = Any[_f16_todict(v) for v in x]
_f16_todict(x) = x

@testset "f16-sim FMU (examples/f16)" begin
    doc = _f16_todict(JSON3.read(read(joinpath(_F16_PROJECT, "models", "f16-sim.bgmodel.json"), String)))
    flat = BGSim.Export.host_inputs(Compile.flatten(IR.parse_model(doc); project_dir = _F16_PROJECT))
    @test BGSim.Export.input_markers(flat) == _F16_INPUTS

    # the ranges of examples/export_f16.jl: the spectrum scan of the step rule covers them
    ranges = Dict{String,Any}("global:vt0" => (90.0, 400.0), "global:h0" => (300.0, 12000.0),
        "global:alpha0" => (-5.0, 25.0), "global:el0" => (-25.0, 25.0), "global:thtl0" => (0.0, 1.0),
        "global:xcg" => (0.2, 0.45), "global:mass" => (7000.0, 14000.0))
    for g in _F16_GLOBALS[8:end]
        ranges["global:" * g] = (0.0, 1.0)
    end
    dir = mktempdir()
    r = BGSim.Export.export_model(flat, dir; name = "f16_sim", settings = BGSim.Export.ExportSettings(Dict{String,Any}(
        "t_end" => 3600.0, "step" => 0.005, "tunables" => ["global:" * g for g in _F16_GLOBALS],
        "ranges" => ranges)))
    @test r.ok
    if r.ok
        @test r.report["method"] == "rk4"
        @test r.report["dt"] ≈ 0.005
        @test r.report["substeps"] == 1
        @test [i["name"] for i in r.report["inputs"]] == _F16_INPUTS
        outs = [o["name"] for o in r.report["outputs"]]
        @test length(outs) == 42
        @test all(n -> n in outs, ["alt_m", "q_w", "alpha_deg", "nz_g", "cas_mps", "ail_deg", "rdr_deg",
                                    "thrust_n", "limiter_active", "departed", "ground_contact"])
        tu = r.report["tunables"]
        @test sort(tu["globals"]) == sort(_F16_GLOBALS)
        @test tu["starts"] > 0 && tu["calculated"] > 0      # the start state follows vt0, h0, alpha0, ...
        @test !any(d -> d.severity == "error", r.diagnostics)
    end

    # The host model at its start values holds the trim: 500 ft/s, 10 000 ft, level.
    t = collect(0.0:0.005:2.0)
    params = Dict(p.id => p for p in flat.parameters)
    inputs = Dict(m * "/value" => (t, fill(Float64(params[m * "/value"].value), length(t)))
                  for m in BGSim.Export.input_markers(flat))
    run = mktempdir()
    BGSim.simulate(flat; run_dir = run, inputs, settings = Dict{String,Any}("t_end" => 2.0,
        "solver" => "auto", "reltol" => 1e-8, "abstol" => 1e-8,
        "output" => Dict("mode" => "interval", "interval" => 0.5)))
    man = JSON3.read(read(joinpath(run, "manifest.json"), String))
    @test String(man.status) == "done"
    ids = [String(s.id) for s in man.signals]
    rows = reshape(reinterpret(Float64, read(joinpath(run, "stream.f64"))), 1 + length(ids), :)
    col(name) = rows[1 + findfirst(==(name), ids), :]
    globals = Dict(String(g["name"]) => parse(Float64, String(g["value"])) for g in doc["parameters"])
    @test maximum(abs.(col("alpha_deg/u") .- globals["alpha0"])) < 1e-3
    @test maximum(abs.(col("alt_m/u") .- globals["h0"])) < 0.05
    @test maximum(abs.(col("tas_mps/u") .- globals["vt0"])) < 1e-3
    @test maximum(abs.(col("nz_g/u") .- 1.0)) < 3e-3
end
