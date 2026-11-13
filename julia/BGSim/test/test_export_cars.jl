# The racecar-sim and buggy-sim FMUs of examples/cars (the FMUs of the apps/web host): the
# export with the host's interface and settings (examples/export_cars.jl) is accepted, fixed-step
# RK4 inside the 5 ms communication step, the ExportInputPass markers are the FMU inputs and the
# ExportOutput markers its outputs, the start pose and charge and the motor and brake limits are FMU
# parameters (the start state is recomputed from them at initialization), and the flattened race
# car (test drive cut off, inputs at their start values) stands still on its springs. The fmpy
# comparison against bg-sim, the build and the doStep timing are `examples/export_cars_check.py`.

using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import JSON3

const _CARS_PROJECT = normpath(joinpath(@__DIR__, "..", "..", "..", "examples", "cars"))
const _CARS_INPUTS = ["steer", "throttle", "brake", "reverse", "handbrake", "mu_fl", "mu_fr", "mu_rl", "mu_rr"]

_cars_todict(x::AbstractDict) = Dict{String,Any}(String(k) => _cars_todict(v) for (k, v) in pairs(x))
_cars_todict(x::AbstractVector) = Any[_cars_todict(v) for v in x]
_cars_todict(x) = x

function _cars_flat(vehicle)
    doc = _cars_todict(JSON3.read(read(joinpath(_CARS_PROJECT, "models", "$(vehicle)-sim.bgmodel.json"), String)))
    return BGSim.Export.host_inputs(Compile.flatten(IR.parse_model(doc); project_dir = _CARS_PROJECT))
end

@testset "car-sim FMUs (examples/cars)" begin
    for (vehicle, motors, tunables) in (
            ("racecar", ["r"], ["global:soc0", "global:x0", "global:y0", "global:z0", "global:yaw0",
                                "MotorR/T_max", "MotorR/P_max", "Brakes/Tf", "Brakes/Tr"]),
            ("buggy", ["f", "r"], ["global:soc0", "global:x0", "global:y0", "global:z0", "global:yaw0",
                                   "MotorF/T_max", "MotorR/T_max", "Brakes/Tf", "Brakes/Tr"]))
        @testset "$vehicle" begin
            flat = _cars_flat(vehicle)
            @test sort(BGSim.Export.input_markers(flat)) == sort(_CARS_INPUTS)
            dir = mktempdir()
            ranges = Dict{String,Any}(k => [0.0, 1.0] for k in ("global:soc0",))
            r = BGSim.Export.export_model(flat, dir; name = "$(vehicle)_sim",
                settings = BGSim.Export.ExportSettings(Dict{String,Any}(
                    "t_end" => 3600.0, "step" => 0.005, "tunables" => tunables, "ranges" => ranges)))
            @test r.ok
            r.ok || continue
            @test r.report["method"] == "rk4"
            @test r.report["substeps"] >= 1
            @test r.report["dt"] * r.report["substeps"] ≈ 0.005
            @test sort([i["name"] for i in r.report["inputs"]]) == sort(_CARS_INPUTS)
            outs = [o["name"] for o in r.report["outputs"]]
            want = ["chassis_px", "chassis_qw", "speed", "kmh", "yaw", "beta", "soc", "battery_v", "battery_a",
                    "steer_fl", "steer_fr"]
            for w in ("fl", "fr", "rl", "rr"), s in ("px", "qz", "spin", "fz", "kappa", "alpha", "travel", "zc")
                push!(want, "$(w)_$(s)")
            end
            for a in motors, s in ("rpm", "torque", "tlim", "power", "regen")
                push!(want, "motor_$(a)_$(s)")
            end
            @test all(n -> n in outs, want)
            tu = r.report["tunables"]
            @test sort(tu["globals"]) == sort([t[8:end] for t in tunables if startswith(t, "global:")])
            @test tu["starts"] > 0
            @test !any(d -> d.severity == "error", r.diagnostics)
        end
    end

    # The race car at its start values (on the track at the origin, no pedals) stands still.
    flat = _cars_flat("racecar")
    t = collect(0.0:0.005:1.5)
    params = Dict(p.id => p for p in flat.parameters)
    inputs = Dict(m * "/value" => (t, fill(Float64(params[m * "/value"].value), length(t)))
                  for m in BGSim.Export.input_markers(flat))
    run = mktempdir()
    BGSim.simulate(flat; run_dir = run, inputs, settings = Dict{String,Any}("t_end" => 1.5,
        "solver" => "auto", "reltol" => 1e-7, "abstol" => 1e-8,
        "output" => Dict("mode" => "interval", "interval" => 0.25)))
    man = JSON3.read(read(joinpath(run, "manifest.json"), String))
    @test String(man.status) == "done"
    ids = [String(s.id) for s in man.signals]
    rows = reshape(reinterpret(Float64, read(joinpath(run, "stream.f64"))), 1 + length(ids), :)
    col(name) = rows[1 + findfirst(==(name), ids), :]
    @test maximum(abs.(col("speed/u"))) < 0.05
    @test maximum(abs.(col("chassis_px/u"))) < 0.01
    @test all(>(1000.0), col("fl_fz/u")[3:end])
    @test 0.05 < col("soc/u")[1] <= 1.0
    @test maximum(abs.(col("soc/u") .- col("soc/u")[1])) < 1e-5
end
