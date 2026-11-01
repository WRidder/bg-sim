# Golden test for `stdlib:continuous/StateSpace` (plan section 8, M2 row: state space),
# through the real pipeline.
#
# Model: the classical second-order system
#   A = [0 1; -2 -3],  B = [0, 1],  C = [1, 0],  D = 0,
# started at x = [1, 0] with a zero input. The eigenvalues are -1 and -2, so
#   y(t) = 2*exp(-t) - exp(-2t).
#
# Reference: that analytic free response. Tolerance: rtol 1e-6 at the sampled points.
#
# Feedthrough in a loop (regression): D is a structural constant, so D = 0 folds the D*u
# term away and a strictly proper StateSpace inside a nonlinear feedback loop runs like
# the equivalent strictly proper TransferFunction (before, tearing solved the loop through
# the runtime parameter D and divided by it: NaN at t = 0). D = 0.5 keeps a genuine
# algebraic loop, which is solved. A block that still carries a runtime D = 0 in such a loop
# fails with E903, which names the loop and the zero coefficient.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden
import BGSim
import BGSim.IR, BGSim.Compile

@testset "golden: StateSpace" begin
    model = bg_model(
        "StateSpaceFreeResponse",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "0.0")),
            bg_node("n2", "S1", bg_ref("stdlib:continuous/StateSpace");
                params = Dict{String,Any}(
                    "A" => "[0.0 1.0; -2.0 -3.0]",
                    "B" => "[0.0, 1.0]",
                    "C" => "[1.0, 0.0]",
                ),
                starts = Dict{String,Any}("x" => "[1.0, 0.0]")),
        ],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u")];
        t_end = 4.0, points = 81,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 2

    exact(t) = 2.0 * exp(-t) - exp(-2.0 * t)
    for t in (0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0)
        @test isapprox(bg_value(columns, "S1/y", t), exact(t); rtol = 1e-6, atol = 1e-9)
    end
    # The second state is recorded too, and it is the derivative of the response.
    @test isapprox(bg_value(columns, "S1/x[2]", 1.0), -2.0 * exp(-1.0) + 2.0 * exp(-2.0);
        rtol = 1e-6, atol = 1e-9)
end

# r -> E -> Gain(2) -> plant -> back to E, with the nonlinear error e = (1 + y^2)*(r - y), so
# the loop cannot be torn by a linear solve around the plant.
const _SS_LOOP_ERR = """
@block LoopError begin
    @inputs begin
        r::Real
        y::Real
    end
    @outputs e::Real
    @equations e ~ (1.0 + y * y) * (r - y)
end
"""
# The StateSpace of before: D a runtime parameter.
const _SS_PARAM_D = """
@block StateSpaceParamD begin
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        A::Mat{2,2} = [0.0 1.0; -1.0 -2.0]
        B::Vec{2} = [0.0, 1.0]
        C::Vec{2} = [1.0, 0.0]
        D::Real = 0.0
    end
    @variables x::Vec{2} = [0.0, 0.0]
    @equations begin
        ddt(x) ~ A * x + B * u
        y ~ dot(C, x) + D * u
    end
end
"""

function _ss_loop(name, plant; params = Dict{String,Any}(), constants = Dict{String,Any}())
    node = bg_node("n4", "P", plant; params = params)
    isempty(constants) || (node["constants"] = Dict{String,Any}(constants))
    return bg_model(name,
        [
            bg_node("n1", "R", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "E", Dict{String,Any}("inline" => Dict{String,Any}("source" => _SS_LOOP_ERR))),
            bg_node("n3", "K", bg_ref("stdlib:continuous/Gain"); params = Dict{String,Any}("k" => "2.0")),
            node,
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "r"),
            bg_conn("c2", "signal", "n2", "e", "n3", "u"),
            bg_conn("c3", "signal", "n3", "y", "n4", "u"),
            bg_conn("c4", "signal", "n4", "y", "n2", "y"),
        ];
        t_end = 2.0, points = 21)
end

@testset "StateSpace feedthrough in a feedback loop" begin
    # D = 0 (default): strictly proper, the same loop as TransferFunction 1/(s^2 + 2s + 1)
    # written strictly proper (m = 0).
    ss, ss_result, ss_flat = bg_run(_ss_loop("SSLoop", bg_ref("stdlib:continuous/StateSpace");
        params = Dict{String,Any}("A" => "[0.0 1.0; -1.0 -2.0]")))
    tf, tf_result, _ = bg_run(_ss_loop("TFLoop", bg_ref("stdlib:continuous/TransferFunction");
        params = Dict{String,Any}("num" => "[1.0]", "den" => "[1.0, 2.0, 1.0]"),
        constants = Dict{String,Any}("m" => 0)))
    @test ss_result.status == "done"
    @test tf_result.status == "done"
    @test ss_flat.stats.states == 2
    for t in (0.0, 0.5, 1.0, 2.0)
        y = bg_value(ss, "P/y", t)
        @test isfinite(y)
        @test isapprox(y, bg_value(tf, "P/y", t); atol = 1e-7)
    end
    @test bg_value(ss, "P/y", 2.0) > 0.3

    # D = 0.5: a genuine algebraic loop, solved; y = C*x + D*u holds at every sample.
    fd, fd_result, _ = bg_run(_ss_loop("SSLoopFeedthrough", bg_ref("stdlib:continuous/StateSpace");
        constants = Dict{String,Any}("D" => "0.5")))
    @test fd_result.status == "done"
    for t in (0.0, 1.0, 2.0)
        @test isapprox(bg_value(fd, "P/y", t),
            bg_value(fd, "P/x[1]", t) + 0.5 * bg_value(fd, "P/u", t); atol = 1e-8)
    end
    @test isapprox(bg_value(fd, "P/y", 0.0), 0.5698402909982413; atol = 1e-6)

    # A model saved with D as a parameter value says where the value went.
    legacy = Compile.flatten(IR.parse_model(_ss_loop("SSLegacyD",
        bg_ref("stdlib:continuous/StateSpace"); params = Dict{String,Any}("D" => "0.5"))))
    e003 = [d for d in legacy.diagnostics if d.code == "E003"]
    @test length(e003) == 1
    @test occursin("`D` of `P` is a constant", only(e003).message)

    # A runtime D = 0 in the loop: tearing divides by it. E903 names the coefficient and the
    # loop, next to the generic failure diagnostic (it adds to it, never replaces it).
    model = _ss_loop("SSLoopParamD", Dict{String,Any}("inline" => Dict{String,Any}("source" => _SS_PARAM_D)))
    flat = Compile.flatten(IR.parse_model(model))
    @test isempty([d for d in flat.diagnostics if d.severity == "error"])
    result = BGSim.simulate(flat; run_dir = mktempdir(),
        settings = BGSim.RunSettings(IR.parse_model(model).settings))
    @test result.status == "failed"
    e903 = [d for d in result.diagnostics if d.code == "E903"]
    @test length(e903) == 1
    d = only(e903)
    @test d.severity == "error"
    @test occursin("algebraic loop", d.message)
    @test occursin("P/D", d.message)
    @test occursin("`P`", d.message) && occursin("`K`", d.message)
    @test d.path == "P"
    @test any(x -> x.code in ("E900", "E901", "E103"), result.diagnostics)
    println("runtime-D loop diagnostics: ", [(x.code, x.message) for x in result.diagnostics])

    # The same zero as a parameter of a block whose output is not computed from its input in
    # that equation (an offset, not a feedthrough) is not blamed: E903 only names a
    # direct-feedthrough coefficient.
    @test BGSim._feedthrough_coefficient(flat, "P/D", "P")
    @test !BGSim._feedthrough_coefficient(flat, "P/A[1]", "P")
    @test !BGSim._feedthrough_coefficient(flat, "R/value", "R")
end
