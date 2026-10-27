# Shared helpers for the discrete and logic golden tests (work package J2.7d).
#
# Every golden test drives the **real pipeline** (`parse` -> `flatten` -> `lower` ->
# `simulate`) through [`bg_run`](@ref); nothing here hand-writes an MTK system. The file name
# does not start with `test_`, so the `test/golden/**/test_*.jl` walk in `test/runtests.jl`
# does not pick it up on its own; each golden test file includes it once.
#
# Two differences from the bond-graph helper:
#
#   * `dg_model` defaults the solver to `"auto"`, which picks `Tsit5` for a model without a
#     non-identity mass matrix. A purely discrete model has no continuous state, and
#     `Rodas5P` cannot step such a problem.
#   * `dg_node` also takes the instance's structural `constants`, which the bond-graph helper
#     does not need.
#
# The input signals of these tests are **inline discrete generators** (`dg_ramp`, `dg_toggle`,
# `dg_pattern`), not `Ramp`/`Step`/`Sine`: a continuous source whose output is a `t`-dependent
# observed value and whose only consumer is a discrete block leaves the compiled problem with
# no continuous state, and the run loop's `step!` then fails (E901). A discrete generator is
# also what makes the arithmetic sequences bit-exact. See the J2.7d report in `plan/STATUS.md`.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using .BondGraphGolden

export dg_node, dg_model, dg_ramp, dg_toggle, dg_pattern, dg_grid, dg_values

"""    dg_node(id, name, block; params, constants, starts) -> Dict

One diagram node, like [`bg_node`](@ref) but with the instance's structural `constants`
(plan 3.3)."""
function dg_node(id, name, block; params = Dict{String,Any}(),
    constants = Dict{String,Any}(), starts = Dict{String,Any}())
    node = bg_node(id, name, block; params = params, starts = starts)
    node["constants"] = Dict{String,Any}(constants)
    return node
end

"""    dg_model(name, nodes, connections; kwargs...) -> Dict

A model document with the same settings as [`bg_model`](@ref), except that the solver is
`"auto"`: a discrete-only model has no state for a Rosenbrock method to step."""
dg_model(name, nodes, connections; kwargs...) =
    bg_model(name, nodes, connections; solver = "auto", kwargs...)

"""    dg_ramp(; increment = 1.0, period = 1.0e-3) -> String

The source of an inline test block whose output `y` counts up by `increment` on every tick of
its `period`. With whole-number values the sequence is exact in Float64."""
function dg_ramp(; increment = 1.0, period = 1.0e-3)
    return """
    @block DiscreteTestRamp begin
        @constants sample_period::Real = $period, [unit = "s", min = 1.0e-12, description = "Test clock"]
        @outputs y::Real = 0.0, [description = "Test ramp"]
        @discrete Ts = sample_period begin
            y = y + $increment
        end
    end
    """
end

"""    dg_toggle(; period = 1.0e-3) -> String

The source of an inline test block whose Bool output `q` toggles on every tick: false before
the first tick, then true, false, true, ..."""
function dg_toggle(; period = 1.0e-3)
    return """
    @block DiscreteTestToggle begin
        @constants sample_period::Real = $period, [unit = "s", min = 1.0e-12, description = "Test clock"]
        @outputs q::Bool = false, [description = "Test toggle"]
        @discrete Ts = sample_period begin
            q = !q
        end
    end
    """
end

"""    dg_pattern(; period = 1.0e-3, expr = "k >= 2") -> String

The source of an inline test block with the tick index `k` (`Int`, incremented before `expr` is
evaluated) and the Bool output `y = expr`. `expr` is language source over `k`, for example
`"k == 2 || k == 3"` or `"mod(k, 4) == 1"`."""
function dg_pattern(; period = 1.0e-3, expr = "k >= 2")
    return """
    @block DiscreteTestPattern begin
        @constants sample_period::Real = $period, [unit = "s", min = 1.0e-12, description = "Test clock"]
        @outputs k::Int = 0, [description = "Tick index"]
        @outputs y::Bool = false, [description = "Test pattern"]
        @discrete Ts = sample_period begin
            k = k + 1
            y = $expr
        end
    end
    """
end

"""    dg_grid(t_end; points) -> Vector{Float64}

The output grid the run records, `points` equally spaced values from 0 to `t_end`."""
dg_grid(t_end; points = 9) = collect(range(0.0, Float64(t_end); length = points))

"""    dg_values(columns, id, times) -> Vector{Float64}

The recorded value of signal `id` at every time in `times` (see [`bg_value`](@ref))."""
dg_values(columns, id, times) = Float64[bg_value(columns, id, t) for t in times]
