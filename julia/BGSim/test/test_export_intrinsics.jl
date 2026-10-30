# Work package J-EX5: the C twins of the intrinsics (plan/EXPORT_PLAN.md, section 8).
#
# Golden tests: every function of `bg_intrinsics.c` and `bg_mech.c` against its Julia twin
# (src/lower/fnmap.jl) on random inputs that cover every branch: small-angle series and
# their switch points, rotations near pi (all four Shepperd branches), non-unit and
# negative-w quaternions, table edges and breakpoints.
# A test driver (`export_intrinsics_driver.c`) is compiled with gcc and fed one call per
# line; every number travels as the hex bit pattern of its double, so nothing is rounded.
#
# The error is measured norm-wise, in ulp of a scale per group of results: the largest
# component of the group, and for a position or a translation part also the largest input
# it is computed from (`exp` of `[w; v]` scales with `|v|`), and for the folded angle of
# `log2` at least pi (its principal range). A component that cancels to nearly zero has no
# meaningful relative error: `log2(4pi, ...)` returns an angle of -4.9e-16, whose value is
# a rounding residue of `sin(4pi)`. Scalar results are measured against themselves. The
# bound is 4 ulp unless `_GOLDEN_BOUND` gives a documented exception.
#
# Then the emitter is checked on nested symbolic mechanics calls (one C call per argument
# tuple), and one model with tables goes through the real pipeline: each table is written
# once, the sources compile with -Werror (and as C++17), and the C run matches simulation.
# A CSV source is refused at its block (simulation data; the host supplies such a signal
# through an ExportInput).

if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using Test
using BGSim
using .BondGraphGolden
using Random
using StaticArrays: SVector
import BGSim.IR
import BGSim.Compile
import JSON3
import Symbolics

const _EXI = BGSim.Export
const _MECH = BGSim.Mech

# function => (number of results, groups: (result indices, input indices, floor) of the
# ulp scale)
const _GN = 1:0
const _GOLDEN_SHAPES = Dict{String,Tuple{Int,Vector{Tuple{UnitRange{Int},UnitRange{Int},Float64}}}}(
    "bg_exp2" => (3, [(1:1, _GN, 0.0), (2:3, 2:3, 0.0)]),
    "bg_log2" => (3, [(1:1, _GN, Float64(π)), (2:3, 2:3, 0.0)]),
    "bg_exp3" => (7, [(1:4, _GN, 0.0), (5:7, 4:6, 0.0)]),
    "bg_log3" => (6, [(1:3, _GN, 0.0), (4:6, 5:7, 0.0)]),
    "bg_quat_exp" => (4, [(1:4, _GN, 0.0)]), "bg_quat_log" => (3, [(1:3, _GN, 0.0)]),
    "bg_quat_from_rotation" => (4, [(1:4, _GN, 0.0)]),
    "bg_inertia2" => (1, [(1:1, _GN, 0.0)]), "bg_inertia3" => (1, [(1:1, _GN, 0.0)]),
    "bg_interp1" => (1, [(1:1, _GN, 0.0)]), "bg_interp2" => (1, [(1:1, _GN, 0.0)]),
)

# Documented exceptions to the 4-ulp bound, each the maximum over 20 000 cases (seed 7) with
# a margin. The C and Julia bodies do the same operations; the difference is libm's last bit
# of `sin`/`cos`/`tan`/`atan2` against Julia's own, amplified where the closed form cancels.
# `bg_exp2` (6 ulp): `(1 - cos θ)/θ` just above the 1e-2 series switch. `bg_exp3` (8.9 ulp):
# the same cancellation in `(1 - cos θ)/θ²`, and a quaternion that passes three rounding
# stages as in Julia's `chart(exp(V))` (exponential, rotation matrix, Shepperd back).
# `bg_log2`, `bg_log3`, `bg_quat_log` (4 ulp): `atan2` and `tan`, plus StaticArrays'
# `muladd` chains (FMA in Julia) against plain C arithmetic in `log3`.
const _GOLDEN_BOUND = Dict{String,Float64}("bg_exp2" => 8.0, "bg_exp3" => 12.0,
    "bg_log2" => 6.0, "bg_log3" => 6.0, "bg_quat_log" => 6.0)

_gnum(x) = string(reinterpret(UInt64, Float64(x)); base = 16, pad = 16)
_gval(s) = reinterpret(Float64, parse(UInt64, s; base = 16))

function _gaxis(rng)
    v = randn(rng, 3)
    return v / sqrt(sum(abs2, v))
end

# Angles that hit every branch: wide, log-uniform small, around the 1e-2 and 1e-8 series
# switches, near pi, and exactly zero.
function _gangle(rng)
    r = rand(rng)
    r < 0.30 && return 3π * rand(rng)
    r < 0.55 && return 10.0^(-12 * rand(rng))
    r < 0.70 && return 1.0e-2 * (1 + 1.0e-3 * randn(rng))
    r < 0.78 && return 2.0e-8 * (1 + 0.3 * randn(rng))
    r < 0.95 && return π - 10.0^(-8 * rand(rng))
    return 0.0
end

function _gquat(rng)
    r = rand(rng)
    s = 0.3 + 2.7 * rand(rng)  # non-unit on purpose: every function normalises
    if r < 0.4
        q = randn(rng, 4)
    elseif r < 0.6                      # near pi: w tiny, either sign
        q = vcat(1.0e-9 * randn(rng), _gaxis(rng))
    elseif r < 0.8                      # small rotation, either sign of w
        q = vcat(rand(rng, (-1.0, 1.0)), 10.0^(-13 * rand(rng)) * _gaxis(rng))
    else                                # about one axis, near pi: Shepperd's x/y/z branches
        a = zeros(3)
        a[rand(rng, 1:3)] = 1.0
        q = vcat(1.0e-3 * randn(rng), a .+ 1.0e-3 .* randn(rng, 3))
    end
    return s * q / sqrt(sum(abs2, q))
end

function _gsorted(rng, n)
    return cumsum(0.05 .+ rand(rng, n)) .- 2.0
end

# One random case per call: (driver line, Julia results).
function _golden_cases(rng, n)
    cases = Tuple{String,String,Vector{Float64}}[]
    add(fn, line, ref) = push!(cases, (fn, line, Float64.(ref)))
    for _ in 1:n
        # SE(2)
        w = rand(rng, (-1, 1)) * (rand(rng) < 0.2 ? 20 * rand(rng) : _gangle(rng))
        vx, vy = 3 .* randn(rng, 2)
        add("bg_exp2", "bg_exp2 $(_gnum(w)) $(_gnum(vx)) $(_gnum(vy))",
            [BGSim.bg_exp2(w, vx, vy, k) for k in 1:3])
        th = rand(rng) < 0.3 ? 40 * (rand(rng) - 0.5) :
             rand(rng, (-1, 1)) * _gangle(rng) + 2π * rand(rng, -2:2)
        add("bg_log2", "bg_log2 $(_gnum(th)) $(_gnum(vx)) $(_gnum(vy))",
            [BGSim.bg_log2(th, vx, vy, k) for k in 1:3])
        # SE(3) and the rotation vector
        ω = _gangle(rng) * _gaxis(rng)
        v = 2 .* randn(rng, 3)
        add("bg_exp3", "bg_exp3 " * join(_gnum.(vcat(ω, v)), " "),
            [BGSim.bg_exp3(ω..., v..., k) for k in 1:7])
        add("bg_quat_exp", "bg_quat_exp " * join(_gnum.(ω), " "),
            [BGSim.bg_quat_exp(ω..., k) for k in 1:4])
        q = _gquat(rng)
        p = 2 .* randn(rng, 3)
        add("bg_log3", "bg_log3 " * join(_gnum.(vcat(q, p)), " "),
            [BGSim.bg_log3(q..., p..., k) for k in 1:6])
        add("bg_quat_log", "bg_quat_log " * join(_gnum.(q), " "),
            [BGSim.bg_quat_log(q..., k) for k in 1:3])
        R = _MECH.quat_to_matrix(_MECH.Quat(_gquat(rng)...))
        r = [R[i, j] for i in 1:3 for j in 1:3]  # row-major
        add("bg_quat_from_rotation", "bg_quat_from_rotation " * join(_gnum.(r), " "),
            [BGSim.bg_quat_from_rotation(r..., k) for k in 1:4])
        # inertia, every entry
        m = 0.1 + 10 * rand(rng)
        J = rand(rng, 3)
        c = randn(rng, 3)
        i, j = rand(rng, 1:3), rand(rng, 1:3)
        add("bg_inertia2", "bg_inertia2 " * join(_gnum.((m, J[1], c[1], c[2], i, j)), " "),
            [BGSim.bg_inertia2(m, J[1], c[1], c[2], i, j)])
        i, j = rand(rng, 1:6), rand(rng, 1:6)
        add("bg_inertia3", "bg_inertia3 " * join(_gnum.((m, J..., c..., i, j)), " "),
            [BGSim.bg_inertia3(m, J..., c..., i, j)])
        # interp1: inside, outside, on a breakpoint, one-point tables
        nt = rand(rng, 1:12)
        xs = _gsorted(rng, nt)
        ys = randn(rng, nt)
        u = rand(rng) < 0.3 ? xs[rand(rng, 1:nt)] : xs[1] - 1 + (xs[end] - xs[1] + 2) * rand(rng)
        add("bg_interp1", "bg_interp1 $(_gnum(nt)) $(_gnum(u)) " * join(_gnum.(vcat(xs, ys)), " "),
            [BGSim.bg_interp1(u, xs, ys)])
        # interp2 on an n x n grid
        ng = rand(rng, 2:6)
        br = permutedims(hcat(_gsorted(rng, ng), _gsorted(rng, ng)))  # 2 x n
        tb = randn(rng, ng, ng)
        uu = rand(rng) < 0.2 ? br[1, rand(rng, 1:ng)] : -3 + 6 * rand(rng)
        vv = rand(rng) < 0.2 ? br[2, rand(rng, 1:ng)] : -3 + 6 * rand(rng)
        flat = vcat(vec(permutedims(br)), vec(permutedims(tb)))  # both row-major
        add("bg_interp2", "bg_interp2 $(_gnum(ng)) $(_gnum(uu)) $(_gnum(vv)) " * join(_gnum.(flat), " "),
            [BGSim.bg_interp2(uu, vv, br, tb)])
    end
    return cases
end

function _golden_ulps(fn, line, c::Vector{Float64}, ref::Vector{Float64})
    worst = 0.0
    for (g, gin, floor_) in _GOLDEN_SHAPES[fn][2]
        scale = max(maximum(abs, ref[g]), floor_)
        if !isempty(gin)
            args = _gval.(split(line)[2:end])
            scale = max(scale, maximum(abs, args[gin]))
        end
        for i in g
            (c[i] == ref[i] || (isnan(c[i]) && isnan(ref[i]))) && continue
            worst = max(worst, abs(c[i] - ref[i]) / eps(max(scale, floatmin(Float64))))
        end
    end
    return worst
end

const _EXI_STEPPER = """
#include <stdio.h>
#include "model.h"
static bg_model m;
int main(int argc, char **argv) {
    long n = 0, k;
    int i;
    if (argc > 1) sscanf(argv[1], "%ld", &n);
    bg_reset(&m, 0.0);
    for (k = 0; k < n; ++k) {
        if (bg_step(&m) != 0) { printf("step failed at %ld\\n", k); return 3; }
    }
    bg_update_outputs(&m);
    for (i = 0; i < BG_NY; ++i) printf("y %d %.17g\\n", i, m.y[i]);
    return 0;
}
"""

const _EXI_LAG = """
@block Lag begin
    @inputs begin
        u::Real
        v::Real
    end
    @outputs y::Real
    @variables x::Real = 0.0
    @equations begin
        ddt(x) ~ (u + v - x) / 0.2
        y ~ x
    end
end
"""

# A table in the loop: the lag's state goes through Lookup1D and back into its derivative,
# so the Jacobian needs the derivative of `bg_interp1`, which has no symbolic rule.
function _exi_feedback_model()
    nodes = Any[
        bg_node("n1", "Ramp", bg_ref("stdlib:sources/Ramp")),
        bg_node("n2", "L1", bg_ref("stdlib:continuous/Lookup1D")),
        bg_node("n5", "P", Dict{String,Any}("inline" => Dict{String,Any}("source" => _EXI_LAG))),
        bg_node("n6", "Y", bg_ref("stdlib:converters/ExportOutput")),
    ]
    conns = Any[
        bg_conn("c1", "signal", "n1", "y", "n5", "v"),
        bg_conn("c2", "signal", "n5", "y", "n2", "u"),
        bg_conn("c3", "signal", "n2", "y", "n5", "u"),
        bg_conn("c4", "signal", "n5", "y", "n6", "u"),
    ]
    return bg_model("ExportTableLoop", nodes, conns; t_end = 1.0, points = 11)
end

function _exi_model()
    nodes = Any[
        bg_node("n1", "Ramp", bg_ref("stdlib:sources/Ramp")),
        bg_node("n2", "L1", bg_ref("stdlib:continuous/Lookup1D")),
        bg_node("n3", "L2", bg_ref("stdlib:continuous/Lookup2D")),
        bg_node("n4", "L3", bg_ref("stdlib:continuous/Lookup1D")),
        bg_node("n5", "P", Dict{String,Any}("inline" => Dict{String,Any}("source" => _EXI_LAG))),
        bg_node("n6", "Y", bg_ref("stdlib:converters/ExportOutput")),
    ]
    conns = Any[
        bg_conn("c1", "signal", "n1", "y", "n2", "u"),
        bg_conn("c2", "signal", "n1", "y", "n3", "u"),
        bg_conn("c3", "signal", "n2", "y", "n3", "v"),
        bg_conn("c4", "signal", "n1", "y", "n4", "u"),
        bg_conn("c5", "signal", "n3", "y", "n5", "u"),
        bg_conn("c6", "signal", "n4", "y", "n5", "v"),
        bg_conn("c7", "signal", "n5", "y", "n6", "u"),
    ]
    return bg_model("ExportIntrinsics", nodes, conns; t_end = 1.0, points = 11)
end

"""Export `flat`, compile the sources with -Werror (and model.c as C++17), step the C model
to `t_end` and compare every recorded signal with the simulation `columns` at `t_end`."""
function _exi_export_and_compare(cc, dir, flat, columns; t_end = 1.0, dt = 1.0e-4,
    min_compared = 1, rtol = 1.0e-7, method = :auto)
    out = joinpath(dir, "model")
    r = _EXI.export_model(flat, out;
        settings = _EXI.ExportSettings(t_end = t_end, dt = dt, expose_all = true, method = method))
    @test r.ok
    r.ok || return r, ""
    src = joinpath(out, "sources")
    model_c = read(joinpath(src, "model.c"), String)
    files = [joinpath(src, f) for f in ("model.c", "bg_solver.c", "bg_intrinsics.c", "bg_mech.c")]
    for f in files
        @test success(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -fno-math-errno -I $src -c $f -o $(joinpath(dir, "x.o"))`)
    end
    cxx = Sys.which("g++")
    if cxx !== nothing
        @test success(`$cxx -x c++ -std=c++17 -fsyntax-only -Wall -Werror -I $src $(joinpath(src, "model.c"))`)
    end
    stepper = joinpath(dir, "stepper.c")
    write(stepper, _EXI_STEPPER)
    sexe = joinpath(dir, Sys.iswindows() ? "stepper.exe" : "stepper")
    @test success(`$cc -std=c99 -O2 -I $src $stepper $files -o $sexe -lm`)
    res = read(`$sexe $(round(Int, t_end / r.report["dt"]))`, String)
    ys = Dict(parse(Int, m.captures[1]) => parse(Float64, m.captures[2])
              for m in eachmatch(r"y (\d+) (\S+)", res))
    names = vcat([o["id"] for o in r.report["outputs"]], r.report["locals"])
    @test length(ys) == length(names)
    compared = 0
    for (k, id) in enumerate(names)
        haskey(columns, id) || continue
        ref = bg_value(columns, id, t_end)
        @test isapprox(ys[k - 1], ref; rtol = rtol, atol = 1.0e-9)
        compared += 1
    end
    @test compared >= min_compared
    return r, model_c
end


@testset "export intrinsics (J-EX5)" begin
    cc = Sys.which("gcc")
    if cc === nothing
        @info "export intrinsics: no gcc on PATH, the golden tests are skipped"
    else
        dir = mktempdir()
        rt = _EXI.RUNTIME_DIR
        exe = joinpath(dir, Sys.iswindows() ? "driver.exe" : "driver")
        @test success(`$cc -std=c99 -O2 -Wall -Wextra -Werror -fno-math-errno -I $rt
            $(joinpath(@__DIR__, "export_intrinsics_driver.c")) $(joinpath(rt, "bg_intrinsics.c"))
            $(joinpath(rt, "bg_mech.c")) -o $exe -lm`)

        @testset "golden: C twins against Julia" begin
            cases = _golden_cases(Xoshiro(0x4a455835), 2000)
            input = joinpath(dir, "input.txt")
            open(input, "w") do io
                foreach(c -> println(io, c[2]), cases)
            end
            lines = split(chomp(read(pipeline(`$exe`; stdin = input), String)), '\n')
            @test length(lines) == length(cases)
            worst = Dict{String,Float64}()
            count = Dict{String,Int}()
            for (k, (fn, line, ref)) in enumerate(cases)
                c = _gval.(split(lines[k]))
                length(c) == _GOLDEN_SHAPES[fn][1] || (@test false; continue)
                worst[fn] = max(get(worst, fn, 0.0), _golden_ulps(fn, line, c, ref))
                count[fn] = get(count, fn, 0) + 1
            end
            table = join(["  $(rpad(fn, 24)) $(lpad(count[fn], 5)) cases  max $(worst[fn]) ulp"
                          for fn in sort(collect(keys(worst)))], "\n")
            @info "export intrinsics: golden deviation, C against Julia\n" * table
            for fn in keys(_GOLDEN_SHAPES)
                @test haskey(worst, fn)
                @test get(worst, fn, Inf) <= get(_GOLDEN_BOUND, fn, 4.0)
            end
        end

        # The language checker does not pass vector arguments to `exp`/`log`/`quat_*` yet, so
        # no block reaches these calls; the emitter is tested on the symbolic calls that
        # `lower_mech` builds, nested as a model would nest them.
        @testset "emitter: one call per argument tuple, components read from it" begin
            xs = [BGSim.mtk_variable("g/x$i") for i in 1:10]
            env = Dict{Any,String}(Symbolics.unwrap(xs[i]) => "x[$(i - 1)]" for i in 1:10)
            e3 = [BGSim.bg_exp3(xs[1:6]..., k) for k in 1:7]
            l3 = [BGSim.bg_log3(e3..., k) for k in 1:6]
            qe = [BGSim.bg_quat_exp(xs[1:3]..., k) for k in 1:4]
            ql = [BGSim.bg_quat_log(qe..., k) for k in 1:3]
            R = [xs[7] xs[8] 0.0; -xs[8] xs[7] 0.0; 0.0 0.0 1.0]
            qr = [BGSim.bg_quat_from_rotation(permutedims(R)[:]..., k) for k in 1:4]
            e2 = [BGSim.bg_exp2(xs[9], xs[10], xs[1], k) for k in 1:3]
            l2 = [BGSim.bg_log2(e2..., k) for k in 1:3]
            in2 = [BGSim.bg_inertia2(xs[9], 0.5, xs[2], xs[3], 1, 1)]
            in3 = [BGSim.bg_inertia3(xs[9], 0.5, 0.6, 0.7, xs[2], xs[3], xs[4], 2, 6)]
            exprs = vcat(e3, l3, qe, ql, qr, e2, l2, in2, in3, [e3[5] * l3[2] + ql[1]])
            obs = (lhs = Any[], rhs = Any[], names = String[], index = Dict{Any,Int}())
            io = IOBuffer()
            print(io, "#include <math.h>\n#include <stdio.h>\n#include \"bg_runtime.h\"\n")
            ctx = _EXI.with_intrinsics() do
                _EXI.emit_function(io, "static void f(const void *m, double t, const double *x, double *y)",
                    [("y[$(i - 1)]", e, nothing) for (i, e) in enumerate(exprs)], env, obs)
            end
            θ = 0.7
            vals = [0.3, -0.2, 0.5, 1.0, 2.0, -1.5, cos(θ), sin(θ), 0.4, -0.8]
            main = """
            int main(void) {
                const double x[10] = {$(join(repr.(vals), ", "))};
                double y[$(length(exprs))];
                int i;
                f(0, 0.0, x, y);
                for (i = 0; i < $(length(exprs)); ++i) printf("%.17g\\n", y[i]);
                return 0;
            }
            """
            csrc = _EXI.splice_intrinsics(String(take!(io)), ctx) * main
            body = csrc[findfirst("static void f", csrc).start:end]
            for (fn, n) in (("bg_exp3(", 1), ("bg_log3(", 1), ("bg_quat_exp(", 1),
                ("bg_quat_log(", 1), ("bg_quat_from_rotation(", 1), ("bg_exp2(", 1),
                ("bg_log2(", 1), ("bg_inertia2(", 1), ("bg_inertia3(", 1))
                @test count(fn, body) == n
            end
            cfile = joinpath(dir, "mech_emit.c")
            write(cfile, csrc)
            mexe = joinpath(dir, Sys.iswindows() ? "mech_emit.exe" : "mech_emit")
            @test success(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -I $rt $cfile $(joinpath(rt, "bg_mech.c")) $(joinpath(rt, "bg_intrinsics.c")) -o $mexe -lm`)
            got = parse.(Float64, split(chomp(read(`$mexe`, String)), '\n'))
            fj = Symbolics.build_function(exprs, xs; expression = Val(false))
            want = Float64.((fj isa Tuple ? first(fj) : fj)(vals))
            @test length(got) == length(want)
            @test maximum(abs.(got .- want)) <= 1.0e-14
        end

        @testset "a model with tables exports, shares its tables and matches" begin
            columns, result, flat = bg_run(_exi_model())
            @test result.status == "done"
            r, model_c = _exi_export_and_compare(cc, mktempdir(), flat, columns; min_compared = 6)
            # `L1` and `L3` have the same default tables, so there are four, not six: the
            # breakpoints and values of Lookup1D, the breaks and the grid of Lookup2D.
            tabs = r.report["tables"]
            @test tabs["count"] == length(tabs["tables"]) == 4
            @test tabs["bytes"] == sum(t["bytes"] for t in tabs["tables"]) == 8 * (3 + 3 + 6 + 9)
            @test count("static const double bg_tab", model_c) == 4
            @test occursin("bg_interp1(", model_c) && occursin("bg_interp2(", model_c)
        end

        # J-EX5 open issue 3: an opaque intrinsic has no symbolic derivative, so a Rosenbrock
        # export of a table in the loop falls back to the coloured finite-difference
        # Jacobian (W212) instead of failing, and still matches the simulation.
        @testset "a table in the loop exports with Rodas4P and a finite-difference Jacobian" begin
            columns, result, flat = bg_run(_exi_feedback_model())
            @test result.status == "done"
            r, model_c = _exi_export_and_compare(cc, mktempdir(), flat, columns; dt = 1.0e-3,
                method = :rodas4p, rtol = 1.0e-5)
            @test r.report["method"] == "rodas4p"
            @test r.report["jacobian"]["kind"] == "fd"
            @test occursin("symbolic derivative", r.report["jacobian"]["fallbackReason"])
            @test any(d -> d.code == "W212", r.diagnostics)
            @test occursin("bg_fd_cols", model_c) && occursin("bg_interp1(", model_c)
        end

        @testset "a CSV source is refused at its block" begin
            project = mktempdir()
            mkpath(joinpath(project, "data"))
            write(joinpath(project, "data", "traj.csv"), "t [s],a\n0.0,0.0\n1.0,1.0\n2.0,4.0\n")
            for ref in ("stdlib:sources/CsvSource", "stdlib:sources/CsvSourceSampled")
                csv = Dict{String,Any}(
                    "id" => "n1", "name" => "Csv", "block" => Dict{String,Any}("ref" => ref),
                    "position" => Dict{String,Any}("x" => 0.0, "y" => 0.0),
                    "params" => Dict{String,Any}(), "starts" => Dict{String,Any}(),
                    "constants" => Dict{String,Any}("file" => "data/traj.csv"))
                flat = Compile.flatten(IR.parse_model(bg_model("ExportCsv", Any[csv], Any[]));
                    project_dir = project)
                @test !any(d -> d.severity == "error", flat.diagnostics)
                r = _EXI.export_model(flat, mktempdir())
                @test !r.ok
                d = only(r.diagnostics)
                @test d.code == "E110" && d.path == "Csv"
                @test occursin("ExportInput", d.hint)
            end
        end
    end
end
