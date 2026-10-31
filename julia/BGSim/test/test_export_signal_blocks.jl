# The signal and control blocks in the C export (plan/EXPORT_PLAN.md): transfer functions,
# filters, routing, nonlinearities, observers and the discrete blocks export, compile with
# -std=c99 -Wall -Wextra -Werror and run without allocating after instantiate. The C
# outputs are compared against the Julia simulation of the same model at the common grid
# times, away from the switching instants of the discontinuous blocks (an event is located
# in simulation and frozen per step in C, W203). The variable transport delay runs the same
# ring in both (`delay(x, Tmax, tau)`, `bg_delay_ring_at`).
#
# The run monitors are tested at the end: StopSimulation makes bg_step return BG_STEP_STOP
# and fmi2DoStep return fmi2Discard with fmi2Terminated set; a failed Assertion makes
# bg_step return BG_STEP_ASSERT and fmi2DoStep return fmi2Error. The simulation ends at the
# located event with W217 (status done) or E902 (status failed).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using Test
using BGSim
using .BondGraphGolden
import BGSim.IR
import BGSim.Compile

const _EXB = BGSim.Export

const _EXB_RUNNER = raw"""
#include <stdio.h>
#include <stdlib.h>
#include "model.h"
static bg_model m;
int main(int argc, char **argv) {
    long n = argc > 1 ? atol(argv[1]) : 100;
    bg_reset(&m, 0.0);
    for (long k = 0; k <= n; ++k) {
        if (k > 0 && bg_step(&m) != 0) return 2;
        bg_update_outputs(&m);
        printf("%.17g", m.t);
        for (int i = 0; i < BG_NX; ++i) printf(" %.17g", m.x[i]);
        for (int i = 0; i < BG_NY; ++i) printf(" %.17g", m.y[i]);
        printf("\n");
    }
    return 0;
}
"""

# Steps until bg_step reports something; prints the code, the time and the monitor's block.
const _EXB_MONITOR_RUNNER = raw"""
#include <stdio.h>
#include "model.h"
static bg_model m;
int main(void) {
    bg_reset(&m, 0.0);
    for (long k = 0; k < 100000; ++k) {
        int rc = bg_step(&m);
        if (rc != 0) {
            printf("%d %.17g %d %s\n", rc, m.t, m.monitor, rc > 0 ? bg_monitor_name[m.monitor - 1] : "-");
            return 0;
        }
    }
    printf("0 %.17g 0 -\n", m.t);
    return 0;
}
"""

# An FMI host: doSteps of 10 internal steps until a status other than fmi2OK; prints the
# status, fmi2Terminated, fmi2LastSuccessfulTime and the output read after the stop.
const _EXB_FMU_HOST = raw"""
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include "fmi2Functions.h"
#include "model.h"
static void log_msg(fmi2ComponentEnvironment env, fmi2String name, fmi2Status s,
                    fmi2String cat, fmi2String msg, ...) {
    (void)env; (void)name;
    va_list ap;
    va_start(ap, msg);
    fprintf(stderr, "[%s %d] ", cat, (int)s);
    vfprintf(stderr, msg, ap);
    fputc('\n', stderr);
    va_end(ap);
}
int main(void) {
    fmi2CallbackFunctions cb = {log_msg, calloc, free, NULL, NULL};
    fmi2Component c = fmi2Instantiate("mon", fmi2CoSimulation, BG_GUID, "", &cb, fmi2False, fmi2False);
    if (c == NULL) return 2;
    fmi2SetupExperiment(c, fmi2False, 0.0, 0.0, fmi2False, 0.0);
    fmi2EnterInitializationMode(c);
    fmi2ExitInitializationMode(c);
    double t = 0.0, h = 10 * BG_DT;
    fmi2Status s = fmi2OK;
    for (int k = 0; k < 10000 && s == fmi2OK; ++k) {
        s = fmi2DoStep(c, t, h, fmi2True);
        if (s == fmi2OK) t += h;
    }
    fmi2Boolean term = fmi2False;
    fmi2Status bs = fmi2GetBooleanStatus(c, fmi2Terminated, &term);
    fmi2Real last = -1.0;
    fmi2GetRealStatus(c, fmi2LastSuccessfulTime, &last);
    fmi2ValueReference vr = 0;
    fmi2Real y = -1.0;
    fmi2Status gs = fmi2GetReal(c, &vr, 1, &y);
    printf("%d %d %d %.17g %d %.17g\n", (int)s, (int)bs, (int)term, last, (int)gs, y);
    fmi2FreeInstance(c);
    return 0;
}
"""

function _exb_sources(dir)
    src = joinpath(dir, "sources")
    return src, [joinpath(src, f) for f in ("model.c", "bg_solver.c", "bg_intrinsics.c", "bg_mech.c")
                 if isfile(joinpath(src, f))]
end

function _exb_build(cc, dir, name, code; fmu = false)
    src, files = _exb_sources(dir)
    fmu && push!(files, joinpath(src, "fmi2_cs.c"))
    main = joinpath(dir, name * ".c")
    write(main, code)
    exe = joinpath(dir, Sys.iswindows() ? name * ".exe" : name)
    run(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -I $src $files $main -o $exe -lm`)
    return exe
end

function _exb_run_c(cc, dir, report, n)
    exe = _exb_build(cc, dir, "runner", _EXB_RUNNER)
    rows = [parse.(Float64, split(l)) for l in eachline(`$exe $n`)]
    model_c = read(joinpath(dir, "sources", "model.c"), String)
    xnames = [String(m.captures[2]) for m in eachmatch(r"/\* x\[(\d+)\] = (\S+) \*/", model_c)]
    ynames = vcat([o["name"] for o in report["outputs"]], String.(report["locals"]))
    return permutedims(reduce(hcat, rows)), xnames, ynames
end

_exb_node(id, ref; params = Dict{String,Any}(), consts = Dict{String,Any}()) = begin
    nd = bg_node(id, id, bg_ref(ref); params = Dict{String,Any}(params))
    isempty(consts) || (nd["constants"] = Dict{String,Any}(consts))
    nd
end

# Signal, the instants where it may jump (excluded with 3 steps around them), tolerance.
# The ramp R = -3.95 + 8t puts the jumps of WrapToPi and Rounding between the 1 ms ticks of
# Backlash and VariableTransportDelay: a jump exactly at a tick instant stalls Rodas5P
# (MaxIters), an existing limitation of the simulator unrelated to these blocks.
const _EXB_CHECKS = [
    ("TF/y", Float64[], 1e-6),
    ("ZP/y", Float64[], 1e-6),
    ("BW/y", Float64[], 1e-6),
    ("BS/y", Float64[], 1e-6),
    ("NT/y", Float64[], 1e-6),
    ("BP/y", Float64[], 1e-6),
    ("PL/y", Float64[], 1e-9),
    ("WR/y", [(3.95 - pi) / 8, (3.95 + pi) / 8], 1e-9),
    ("RD/y", [(k + 4.45) / 8 for k in -4:3], 1e-9),
    ("FX/y", [(k + 3.95) / 8 for k in -3:3], 1e-9),
    ("DM/y2", Float64[], 1e-9),
    ("MS/y", [1 / 3, 2 / 3], 1e-9),
    ("BL/y", Float64[], 1e-6),
    ("VD/y", Float64[], 1e-6),
    ("HC/y", [pi / 30], 1e-9),
    ("HC/n", [pi / 30], 1e-9),
    ("LO/y_hat", Float64[], 1e-6),
    ("ME/y", Float64[], 1e-9),
    ("DD/y", Float64[], 1e-6),
    ("KF/y_hat", Float64[], 1e-6),
]

@testset "signal and control blocks in the C export" begin
    sin_ = (id, w) -> _exb_node(id, "stdlib:sources/Sine"; params = Dict("frequency" => w))
    ramp = (id, s, i) -> _exb_node(id, "stdlib:sources/Ramp"; params = Dict("slope" => s, "initial" => i))
    nodes = Any[
        sin_("S", "5.0"), ramp("R", "8.0", "-3.95"), ramp("I", "3.0", "0.5"), ramp("Dl", "0.1", "0.05"),
        _exb_node("TF", "stdlib:continuous/TransferFunction";
            params = Dict("num" => "[0.0, 1.0, 2.0]", "den" => "[1.0, 3.0, 2.0]")),
        _exb_node("ZP", "stdlib:continuous/ZeroPole"),
        _exb_node("BW", "stdlib:continuous/LowPassButterworth"; params = Dict("wc" => "20.0"), consts = Dict("n" => 3)),
        _exb_node("BS", "stdlib:continuous/LowPassBessel"; params = Dict("wc" => "20.0"), consts = Dict("n" => 4)),
        _exb_node("NT", "stdlib:continuous/Notch"; params = Dict("w0" => "5.0", "depth" => "0.1")),
        _exb_node("BP", "stdlib:continuous/BandPass"; params = Dict("w0" => "5.0")),
        _exb_node("PL", "stdlib:continuous/Polynomial"; params = Dict("p" => "[0.5, -1.0, 2.0]")),
        _exb_node("WR", "stdlib:continuous/WrapToPi"),
        _exb_node("RD", "stdlib:continuous/Rounding"),
        _exb_node("FX", "stdlib:continuous/Rounding"; params = Dict("mode" => "3")),
        _exb_node("MX", "stdlib:continuous/Mux3"),
        _exb_node("DM", "stdlib:continuous/Demux3"),
        _exb_node("MS", "stdlib:continuous/MultiportSwitch"),
        _exb_node("BL", "stdlib:continuous/Backlash"; params = Dict("width" => "0.4")),
        _exb_node("VD", "stdlib:continuous/VariableTransportDelay"),
        _exb_node("HC", "stdlib:continuous/HitCrossing"; params = Dict("level" => "0.5", "direction" => "1")),
        _exb_node("PS", "stdlib:continuous/StateSpace"),
        _exb_node("LO", "stdlib:continuous/Luenberger"),
        _exb_node("ME", "stdlib:discrete/Memory"; consts = Dict("sample_period" => 0.01)),
        _exb_node("DD", "stdlib:discrete/DiscreteDerivative"; consts = Dict("sample_period" => 0.01)),
        _exb_node("KF", "stdlib:discrete/KalmanFilter"; consts = Dict("sample_period" => 0.01),
            params = Dict("A" => "[1.0 0.01; 0.0 1.0]", "B" => "[0.0, 0.01]")),
        _exb_node("Y1", "stdlib:converters/ExportOutput"),
    ]
    wires = [
        ("S", "y", "TF", "u"), ("S", "y", "ZP", "u"), ("S", "y", "BW", "u"), ("S", "y", "BS", "u"),
        ("S", "y", "NT", "u"), ("S", "y", "BP", "u"), ("R", "y", "PL", "u"), ("R", "y", "WR", "u"),
        ("R", "y", "RD", "u"), ("R", "y", "FX", "u"),
        ("S", "y", "MX", "u1"), ("R", "y", "MX", "u2"), ("I", "y", "MX", "u3"), ("MX", "y", "DM", "u"),
        ("I", "y", "MS", "index"), ("MX", "y", "MS", "u"),
        ("S", "y", "BL", "u"), ("S", "y", "VD", "u"), ("Dl", "y", "VD", "d"), ("S", "y", "HC", "u"),
        ("S", "y", "PS", "u"), ("S", "y", "LO", "u"), ("PS", "y", "LO", "y"),
        ("S", "y", "ME", "u"), ("S", "y", "DD", "u"), ("S", "y", "KF", "u"), ("PS", "y", "KF", "y"),
        ("TF", "y", "Y1", "u"),
    ]
    conns = [bg_conn("c$i", "signal", w...) for (i, w) in enumerate(wires)]
    doc = bg_model("SignalBlocksExport", nodes, conns; t_end = 1.0, points = 101)
    flat = Compile.flatten(IR.parse_model(doc))
    @test isempty([d for d in flat.diagnostics if d.severity == "error"])

    dir = mktempdir()
    r = _EXB.export_model(flat, dir;
        settings = _EXB.ExportSettings(t_end = 1.0, dt = 1e-3, method = :rk4, expose_all = true))
    @test r.ok
    @test isempty([d for d in r.diagnostics if d.severity == "error"])
    @test r.report["runtimeVersion"] == _EXB.RUNTIME_VERSION

    cc = Sys.which("gcc")
    if cc === nothing
        @info "export: no gcc on PATH, the signal-block compile-and-run checks are skipped"
    else
        n = 1000
        rows, xn, yn = _exb_run_c(cc, dir, r.report, n)
        @test size(rows, 1) == n + 1
        t = rows[:, 1]
        @test t ≈ (0:n) .* 1e-3
        columns, result, _ = bg_run(doc)
        @test result.status == "done"
        for (sig, breaks, tol) in _EXB_CHECKS
            @testset "$sig" begin
                j = findfirst(==(sig), yn)
                @test j !== nothing
                j === nothing && continue
                iy = 1 + length(xn) + j
                away(tk) = all(abs(tk - b) > 3.5e-3 for b in breaks)
                err = maximum(abs(rows[k, iy] - bg_value(columns, sig, t[k]))
                              for k in 1:10:n + 1 if away(t[k]))
                @test err < tol
            end
        end
        # The variable delay against the ideal delay u(t - d(t)), once the line has filled.
        jv = 1 + length(xn) + findfirst(==("VD/y"), yn)
        @test maximum(abs(rows[k, jv] - sin(5 * (t[k] - (0.05 + 0.1 * t[k]))))
                      for k in 1:n + 1 if t[k] > 0.1) < 1e-3

        @testset "builds with -Werror and does not allocate after instantiate" begin
            src, files = _exb_sources(dir)
            push!(files, joinpath(src, "fmi2_cs.c"))
            for f in files
                @test success(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -I $src -c $f -o $(joinpath(dir, "x.o"))`)
            end
            harness = joinpath(_EXB.RUNTIME_DIR, "alloc_check.c")
            exe = joinpath(dir, Sys.iswindows() ? "check.exe" : "check")
            @test success(`$cc -std=c11 -O2 -I $src $harness $files -o $exe -lm`)
            out = read(`$exe 1 1000`, String)
            @test occursin("after instantiate 0", out)
        end
    end
end

@testset "run monitors: StopSimulation and Assertion" begin
    function monitor_doc(block, slope, initial)
        nodes = Any[
            _exb_node("R", "stdlib:sources/Ramp"; params = Dict("slope" => slope, "initial" => initial)),
            _exb_node("Check", "stdlib:sources/" * block),
            _exb_node("I", "stdlib:continuous/Integrator"),
            _exb_node("Y1", "stdlib:converters/ExportOutput"),
        ]
        conns = [bg_conn("c1", "signal", "R", "y", "Check", "u"), bg_conn("c2", "signal", "R", "y", "I", "u"),
                 bg_conn("c3", "signal", "I", "y", "Y1", "u")]
        return bg_model("Monitor" * block, nodes, conns; t_end = 2.0, points = 201)
    end
    cc = Sys.which("gcc")
    for (block, slope, initial, code, status, rc, fmi) in (
        ("StopSimulation", "1.0", "0.0", "W217", "done", 1, 2),
        ("Assertion", "-1.0", "1.0", "E902", "failed", 2, 3))
        @testset "$block" begin
            doc = monitor_doc(block, slope, initial)
            # Simulation: the run ends at the located crossing, t = 0.5.
            columns, result, flat = bg_run(doc)
            @test result.status == status
            d = only([d for d in result.diagnostics if d.code == code])
            @test d.severity == (code == "W217" ? "warning" : "error")
            @test d.path == "Check"
            @test occursin("`Check`", d.message)
            @test occursin("t = 0.5", d.message)
            @test abs(columns["time"][end] - 0.5) < 1e-6
            @test abs(columns["I/y"][end] - 0.5 * (code == "W217" ? 0.125 * 2 : 0.375 * 2)) < 1e-6
            # A block that does not trigger leaves the run alone.
            quiet = monitor_doc(block, code == "W217" ? "0.1" : "-0.1", initial)
            _, qr, _ = bg_run(quiet)
            @test qr.status == "done"
            @test !any(x -> x.code == code, qr.diagnostics)

            dir = mktempdir()
            r = _EXB.export_model(flat, dir; settings = _EXB.ExportSettings(t_end = 2.0, dt = 1e-3))
            @test r.ok
            model_h = read(joinpath(dir, "sources", "model.h"), String)
            @test occursin("#define BG_NMON 1", model_h)
            if cc !== nothing
                exe = _exb_build(cc, dir, "monitor", _EXB_MONITOR_RUNNER)
                f = split(readchomp(`$exe`))
                @test parse(Int, f[1]) == rc
                @test 0.5 <= parse(Float64, f[2]) <= 0.5 + 2.5e-3
                @test parse(Int, f[3]) == 1
                @test f[4] == "Check"
                host = _exb_build(cc, dir, "host", _EXB_FMU_HOST; fmu = true)
                g = split(readchomp(pipeline(`$host`; stderr = devnull)))
                @test parse(Int, g[1]) == fmi            # fmi2Discard (stop) / fmi2Error (assert)
                if code == "W217"
                    @test parse(Int, g[2]) == 0          # fmi2GetBooleanStatus answers
                    @test parse(Int, g[3]) == 1          # fmi2Terminated
                    @test 0.5 <= parse(Float64, g[4]) <= 0.5 + 2.5e-3
                    @test parse(Int, g[5]) == 0          # the outputs stay readable
                    @test abs(parse(Float64, g[6]) - 0.125) < 2e-3
                else
                    @test parse(Int, g[3]) == 0
                end
            end
        end
    end
end
