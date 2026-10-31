# Backward compatibility of the signal sources that gained parameters: `Sine` (t_start),
# `Ramp` (duration), `Pulse` (offset) and `Chirp` (amplitude, offset, start_phase, method).
#
# Each case runs the same model twice, once with the stdlib block at the defaults of its
# new parameters and once with the block's previous source inline (verbatim, renamed), and
# requires the two recordings to be **bit-identical**: same rows, same times, same values.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

const _SC_OLD = Dict(
    "Sine" => """
@block OldSine begin
    @outputs y::Real
    @parameters begin
        amplitude::Real = 1.0, [description = "Amplitude"]
        frequency::Real = 1.0, [unit = "rad/s", description = "Angular frequency"]
        phase::Real = 0.0, [unit = "rad", description = "Phase"]
        offset::Real = 0.0, [description = "Offset"]
    end
    @equations y ~ offset + amplitude * sin(frequency * t + phase)
end
""",
    "Ramp" => """
@block OldRamp begin
    @outputs y::Real
    @parameters begin
        t_start::Real = 0.0, [unit = "s", description = "Time at which the ramp starts"]
        slope::Real = 1.0, [unit = "1/s", description = "Rate of change of the output"]
        initial::Real = 0.0, [description = "Output value before the ramp starts"]
    end
    @equations y ~ ifelse(t >= t_start, initial + slope * (t - t_start), initial)
end
""",
    "Pulse" => """
@block OldPulse begin
    @outputs y::Real
    @parameters begin
        amplitude::Real = 1.0, [description = "Pulse amplitude"]
        period::Real = 1.0, [unit = "s", min = 1.0e-12, description = "Pulse period"]
        duty::Real = 0.5, [min = 0, max = 1, description = "Duty cycle: the high fraction of each period"]
        t_start::Real = 0.0, [unit = "s", description = "Time of the first rising edge"]
    end
    @equations begin
        y ~ ifelse(
            t >= t_start && sin(
                6.283185307179586 * (t - t_start) / period + 1.5707963267948966 -
                3.141592653589793 * duty,
            ) > cos(3.141592653589793 * duty),
            amplitude,
            0.0,
        )
    end
end
""",
    "Chirp" => """
@block OldChirp begin
    @outputs y::Real
    @parameters begin
        f_start::Real = 1.0, [unit = "Hz", min = 0, description = "Start frequency of the sweep"]
        f_end::Real = 10.0, [unit = "Hz", min = 0, description = "End frequency of the sweep"]
        duration::Real = 1.0, [unit = "s", min = 1.0e-12, description = "Duration of the sweep; afterwards the frequency stays at f_end"]
    end
    @variables phase::Real = 0.0, [unit = "1", description = "Accumulated phase in cycles"]
    @equations begin
        phase ~ ifelse(
            t <= duration,
            f_start * t + (f_end - f_start) * t * t / (2.0 * duration),
            f_start * duration + (f_end - f_start) * duration / 2.0 +
            f_end * (t - duration),
        )
        y ~ sin(6.283185307179586 * phase)
    end
end
""",
)

function _sc_run(block, params; t_end = 2.0)
    model = bg_model("Compat" * (block isa String ? "Stdlib" : "Inline"),
        [bg_node("n1", "S", block isa String ? bg_ref("stdlib:sources/" * block) :
                block; params = Dict{String,Any}(params)),
            bg_node("n2", "I", bg_ref("stdlib:continuous/Integrator"))],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u")]; t_end = t_end, points = 201)
    columns, result, _ = bg_run(model)
    return columns, result
end

@testset "signal sources: new parameters keep the old results bit for bit" begin
    cases = (
        ("Sine", Dict("amplitude" => "2.0", "frequency" => "7.0", "phase" => "0.4",
            "offset" => "0.1")),
        ("Ramp", Dict("t_start" => "0.33", "slope" => "-2.5", "initial" => "1.0")),
        ("Pulse", Dict("amplitude" => "3.0", "period" => "0.37", "duty" => "0.3",
            "t_start" => "0.023")),
        ("Chirp", Dict("f_start" => "0.5", "f_end" => "6.0", "duration" => "1.3")),
        ("Chirp", Dict{String,Any}()),
    )
    @testset "$name $(sort(collect(keys(params))))" for (name, params) in cases
        new, rnew = _sc_run(name, params)
        old, rold = _sc_run(Dict{String,Any}("inline" =>
            Dict{String,Any}("source" => _SC_OLD[name])), params)
        @test rnew.status == "done"
        @test rold.status == "done"
        @test rnew.stats.steps == rold.stats.steps
        @test rnew.stats.events == rold.stats.events
        @test new["time"] == old["time"]
        @test new["S/y"] == old["S/y"]
        @test new["I/y"] == old["I/y"]
        name == "Chirp" && @test new["S/phase"] == old["S/phase"]
    end
end
