# Work package J-EX8 (plan/EXPORT_PLAN.md) and "expose global parameters as FMU parameters"
# (plan/GLOBAL_PARAMETERS.md): values the host sets before initialization.
#
#   * a picked block parameter stays an FMU parameter with variability fixed and its range
#     (user range, else the catalog's); an exposed global does too, and every block parameter
#     and start computed from it becomes a calculated parameter that the generated
#     `bg_init_values` recomputes once in fmi2ExitInitializationMode;
#   * a DAE re-solves its algebraic unknowns there by a bounded Newton (`bg_init`);
#   * refusals: W215 for what cannot be exposed (unknown, driven or structural globals, a
#     parameter computed from a global), E110 when the model's value lies outside the range;
#     the initialization check (C start against MTK's for a changed value) runs for a DAE and
#     reports its probes;
#   * with gcc on PATH: a value set before initialization gives the same trajectory as a Julia
#     run (or a folded export) with that value, an out-of-range value, a late set of a fixed
#     parameter and a set of a calculated one are refused with fmi2Error and a logged reason,
#     and the hot path still does not allocate.

if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using Test
using BGSim
using .BondGraphGolden
import BGSim.IR
import BGSim.Compile
import JSON3

const _TU = BGSim.Export
const _TU_FIXTURES = normpath(joinpath(@__DIR__, "..", "..", "..", "contracts", "fixtures"))

_tu_inline(source) = Dict{String,Any}("inline" => Dict{String,Any}("source" => source))
_tu_flat(doc) = Compile.flatten(IR.parse_model(doc))
_tu_codes(r) = Set(d.code for d in r.diagnostics)
_tu_diags(r, code) = [d for d in r.diagnostics if d.code == code]

const _TU_LAG = """
@block Lag begin
    @inputs u::Real
    @outputs y::Real
    @parameters tau::Real = 0.01, [unit = "s", tunable = true, min = 0.001, max = 1.0]
    @parameters gain::Real = 1.0
    @variables x::Real = 0.0
    @equations begin
        ddt(x) ~ (gain * u - x) / tau
        y ~ x
    end
end
"""

# An index-1 DAE whose consistent start depends on `c`: z^3 + c z = u + x at t = 0.
const _TU_DAE = """
@block DaeC begin
    @inputs u::Real
    @outputs y::Real
    @parameters tau::Real = 0.05
    @parameters c::Real = 1.0
    @variables x::Real = 0.0
    @variables z::Real = 1.0
    @equations begin
        ddt(x) ~ (z - x) / tau
        z^3 + c * z ~ u + x
        y ~ x + z
    end
end
"""

# `@initial x ~ k`: parsed, not flattened yet (so an ODE's initialization check is skipped).
const _TU_INIT = """
@block InitLag begin
    @inputs u::Real
    @outputs y::Real
    @parameters k::Real = 2.0
    @variables x::Real = 0.0
    @initial x ~ k
    @equations begin
        ddt(x) ~ u - x
        y ~ x
    end
end
"""

function _tu_model(block; params = Dict{String,Any}(), name = "Tun", t_end = 0.1)
    nodes = Any[bg_node("n2", "Plant", _tu_inline(block); params),
        bg_node("n1", "U", bg_ref("stdlib:converters/ExportInput");
            params = Dict{String,Any}("value" => "2.0")),
        bg_node("n3", "Y", bg_ref("stdlib:converters/ExportOutput"))]
    conns = Any[bg_conn("c1", "signal", "n1", "y", "n2", "u"),
        bg_conn("c2", "signal", "n2", "y", "n3", "u")]
    return bg_model(name, nodes, conns; t_end, points = 11)
end

_tu_globals_doc() = JSON3.read(read(joinpath(_TU_FIXTURES, "model", "valid",
    "model.global-parameters.json"), String), Dict{String,Any})

# An FMI driver: sets `vr=value` before fmi2ExitInitializationMode (the ones after `--late`
# after it), runs n doSteps of `per` internal steps, prints every status, y and p.
const _TU_DRIVER = """
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fmi2Functions.h"
#include "model.h"
static void log_msg(fmi2ComponentEnvironment env, fmi2String name, fmi2Status s,
                    fmi2String cat, fmi2String msg, ...) {
    (void)env; (void)name; (void)cat;
    va_list ap;
    va_start(ap, msg);
    printf("log %d ", (int)s);
    vprintf(msg, ap);
    printf("\\n");
    va_end(ap);
}
static void set(fmi2Component c, const char *arg) {
    unsigned vr;
    double v;
    if (sscanf(arg, "%u=%lf", &vr, &v) != 2) return;
    fmi2ValueReference r = vr;
    printf("set %u %d\\n", vr, (int)fmi2SetReal(c, &r, 1, &v));
}
int main(int argc, char **argv) {
    long n = atol(argv[1]), per = atol(argv[2]);
    fmi2CallbackFunctions cb = {log_msg, calloc, free, NULL, NULL};
    fmi2Component c = fmi2Instantiate("t", fmi2CoSimulation, BG_GUID, "", &cb, fmi2False, fmi2False);
    if (c == NULL) return 2;
    fmi2SetupExperiment(c, fmi2False, 0.0, 0.0, fmi2False, 0.0);
    fmi2EnterInitializationMode(c);
    int i = 3;
    for (; i < argc && strcmp(argv[i], "--late") != 0; ++i) set(c, argv[i]);
    printf("init %d\\n", (int)fmi2ExitInitializationMode(c));
    for (; i < argc; ++i) set(c, argv[i]);
    double t = 0.0, h = per * BG_DT;
    for (long k = 0; k < n; ++k, t += h)
        if (fmi2DoStep(c, t, h, fmi2True) != fmi2OK) { printf("step failed\\n"); return 3; }
    for (fmi2ValueReference r = 0; r < BG_VR_U0; ++r) {
        double v;
        fmi2GetReal(c, &r, 1, &v);
        printf("v %u %.17g\\n", (unsigned)r, v);
    }
    fmi2FreeInstance(c);
    return 0;
}
"""

"""Compile the export in `dir` with the FMI driver (-Werror) and return a runner:
`run(n, per, sets...; late = [])` -> (status lines, values by FMI name)."""
function _tu_build(cc, dir)
    src = joinpath(dir, "sources")
    write(joinpath(dir, "driver.c"), _TU_DRIVER)
    exe = joinpath(dir, Sys.iswindows() ? "driver.exe" : "driver")
    files = [joinpath(src, f) for f in ("model.c", "bg_solver.c", "fmi2_cs.c")]
    for f in files
        run(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -c $f -I $src -o $(joinpath(dir, "o.o"))`)
    end
    run(`$cc -std=c11 -O2 -I $src $(joinpath(dir, "driver.c")) $files -o $exe -lm`)
    xml = read(joinpath(dir, "modelDescription.xml"), String)
    vr = Dict(String(m.captures[1]) => parse(Int, m.captures[2])
              for m in eachmatch(r"name=\"([^\"]+)\" valueReference=\"(\d+)\"", xml))
    name_of = Dict(v => k for (k, v) in vr)
    function runner(n, per, sets::Pair...; late = Pair[])
        args = String[string(vr[k], "=", repr(Float64(v))) for (k, v) in sets]
        isempty(late) || push!(args, "--late")
        append!(args, String[string(vr[k], "=", repr(Float64(v))) for (k, v) in late])
        # A refused set leaves the instance in its error state, so the steps then fail (exit 3).
        lines = readlines(ignorestatus(`$exe $n $per $args`))
        vals = Dict{String,Float64}()
        for l in lines
            m = match(r"^v (\d+) (\S+)$", l)
            m === nothing || (vals[name_of[parse(Int, m.captures[1])]] = parse(Float64, m.captures[2]))
        end
        return lines, vals
    end
    return runner, vr
end

function _tu_reference(flat, t_end; tstops = Float64[])
    low = BGSim.lower_model(flat; t_start = 0.0, t_end)
    return BGSim.ModelingToolkit.SciMLBase.solve(low.problem,
        BGSim.OrdinaryDiffEqRosenbrock.Rodas5P(); reltol = 1e-11, abstol = 1e-13, tstops)
end

@testset "export tunables (J-EX8)" begin
    @testset "a picked block parameter: fixed, ranged, scanned" begin
        flat = _tu_flat(_tu_model(_TU_LAG))
        r = _TU.export_model(flat, mktempdir(); settings = _TU.ExportSettings(t_end = 0.1,
            tunables = ["Plant/gain"], ranges = Dict("Plant/gain" => (0.5, 3.0))))
        @test r.ok
        ps = Dict(p["id"] => p for p in r.report["parameters"])
        @test ps["Plant/gain"]["variability"] == "fixed"
        @test ps["Plant/gain"]["causality"] == "parameter"
        @test ps["Plant/gain"]["min"] == 0.5 && ps["Plant/gain"]["max"] == 3.0
        @test ps["Plant/tau"]["variability"] == "tunable"   # the catalog's tunable is unchanged
        tu = r.report["tunables"]
        @test tu["requested"] == ["Plant/gain"] && isempty(tu["globals"])
        @test tu["rhsOps"] >= tu["rhsOpsFolded"]
        xml = read(joinpath(r.dir, "modelDescription.xml"), String)
        @test occursin(r"name=\"Plant/gain\"[^>]*causality=\"parameter\" variability=\"fixed\"", xml)
        @test occursin(r"<Real start=\"1.0\" min=\"0.5\" max=\"3.0\"", xml)
        @test occursin("bg_init_values", read(joinpath(r.dir, "sources", "model.c"), String))

        # Without the pick the parameter is folded, as before.
        r0 = _TU.export_model(flat, mktempdir(); settings = _TU.ExportSettings(t_end = 0.1))
        @test r0.ok && !any(p -> p["id"] == "Plant/gain", r0.report["parameters"])
        @test !haskey(r0.report, "tunables") || r0.report["tunables"]["requested"] == String[]

        # `gain` does not move the Jacobian, so its open range is not a stability question;
        # the DAE's `c` does: an open range is W210, a closed one joins the scan.
        r = _TU.export_model(flat, mktempdir(); settings = _TU.ExportSettings(t_end = 0.1,
            tunables = ["Plant/gain"]))
        @test r.ok && !("W210" in _tu_codes(r))
        dae = _tu_flat(_tu_model(_TU_DAE; t_end = 0.2))
        r = _TU.export_model(dae, mktempdir(); settings = _TU.ExportSettings(t_end = 0.2,
            tunables = ["Plant/c"]))
        @test r.ok && occursin("before initialization", only(_tu_diags(r, "W210")).message)
        r = _TU.export_model(dae, mktempdir(); settings = _TU.ExportSettings(t_end = 0.2,
            tunables = ["Plant/c"], ranges = Dict("Plant/c" => (0.5, 4.0))))
        @test r.ok && !("W210" in _tu_codes(r))
        @test r.report["spectrum"]["rangedValues"] == 1
    end

    @testset "refusals: W215 and E110" begin
        flat = _tu_flat(_tu_model(_TU_LAG))
        r = _TU.export_model(flat, mktempdir(); settings = _TU.ExportSettings(t_end = 0.1,
            tunables = ["Plant/nope", "global:m"]))
        @test r.ok
        msgs = [d.message for d in _tu_diags(r, "W215")]
        @test any(m -> occursin("Plant/nope", m), msgs) && any(m -> occursin("global:m", m), msgs)
        # The model's own value must lie in the range.
        r = _TU.export_model(flat, mktempdir(); settings = _TU.ExportSettings(t_end = 0.1,
            tunables = ["Plant/gain"], ranges = Dict("Plant/gain" => (2.0, 3.0))))
        @test !r.ok && "E110" in _tu_codes(r)
        # An ODE without @initial equations needs no initialization check: MTK starts at the
        # starts, which the C recomputes. (@initial is parsed but not flattened yet.)
        r = _TU.export_model(_tu_flat(_tu_model(_TU_INIT)), mktempdir();
            settings = _TU.ExportSettings(t_end = 0.1, tunables = ["Plant/k"],
                ranges = Dict("Plant/k" => (1.0, 3.0))))
        @test r.ok && isempty(r.report["tunables"]["initializationChecks"])

        # A driven global is recomputed, never set; a parameter computed from a global is
        # exposed through the global.
        doc = _tu_globals_doc()
        r = _TU.export_model(_tu_flat(doc), mktempdir(); settings = _TU.ExportSettings(
            t_end = 1.0, tunables = ["global:rate", "Source/Rate/value"]))
        @test r.ok
        msgs = [d.message for d in _tu_diags(r, "W215")]
        @test any(m -> occursin("rate", m), msgs) && any(m -> occursin("Source/Rate/value", m), msgs)
        @test !any(p -> get(p, "variability", "") == "fixed", r.report["parameters"])
    end

    @testset "exposed globals: calculated parameters and starts" begin
        doc = _tu_globals_doc()
        r = _TU.export_model(_tu_flat(doc), mktempdir(); settings = _TU.ExportSettings(
            t_end = 1.0, expose_globals = true, expose_all = true,
            ranges = Dict("global:m" => (1.0, 4.0))))
        @test r.ok
        ps = Dict(p["id"] => p for p in r.report["parameters"])
        @test ps["global:m"]["name"] == "m" && ps["global:m"]["variability"] == "fixed"
        @test ps["global:m"]["unit"] == "kg" && ps["global:m"]["description"] == "Base mass"
        @test (ps["global:m"]["min"], ps["global:m"]["max"]) == (1.0, 4.0)
        @test ps["Source/Rate/value"]["causality"] == "calculatedParameter"
        @test ps["Source/Rate/value"]["dependsOn"] == ["m"]
        @test !haskey(ps, "global:rate") && !haskey(ps, "global:x0")   # driven: recomputed
        tu = r.report["tunables"]
        @test tu["globals"] == ["m"] && tu["calculated"] == 1 && tu["starts"] == 1
        model_c = read(joinpath(r.dir, "sources", "model.c"), String)
        @test occursin(r"x\[0\] = .*sqrt\(m->p\[\d\]\)", model_c)
        xml = read(joinpath(r.dir, "modelDescription.xml"), String)
        @test occursin("causality=\"calculatedParameter\" variability=\"fixed\" initial=\"calculated\"", xml)
        @test occursin("<UnitDefinitions>", xml) && occursin("<Unit name=\"kg\"", xml)
        @test occursin(r"<InitialUnknowns>\s*<Unknown index=", xml)
        # A structural global (a size) is never exposed: W215, still folded.
        sized = deepcopy(doc)
        push!(sized["parameters"], Dict{String,Any}("name" => "n", "value" => "3"))
        push!(sized["diagram"]["nodes"], bg_node("n9", "Rep", _tu_inline("""
            @block Rep begin
                @constants n::Int = 2
                @outputs y::Real
                @variables x::Real = 0.0
                @equations begin
                    ddt(x) ~ n - x
                    y ~ x
                end
            end
            """)))
        sized["diagram"]["nodes"][end]["constants"] = Dict{String,Any}("n" => "n")
        r = _TU.export_model(_tu_flat(sized), mktempdir(); settings = _TU.ExportSettings(
            t_end = 1.0, expose_globals = true, ranges = Dict("global:m" => (1.0, 4.0))))
        @test r.ok && r.report["tunables"]["globals"] == ["m"]
        @test any(d -> occursin("`n`", d.message), _tu_diags(r, "W215"))
    end

    cc = Sys.which("gcc")
    if cc === nothing
        @info "export tunables: no gcc on PATH, the compile-and-run checks are skipped"
    else
        @testset "C: a parameter set before initialization equals a run with that value" begin
            flat = _tu_flat(_tu_model(_TU_LAG))
            dir = mktempdir()
            r = _TU.export_model(flat, dir; settings = _TU.ExportSettings(t_end = 0.1,
                tunables = ["Plant/gain"], ranges = Dict("Plant/gain" => (0.5, 3.0))))
            @test r.ok
            run_c, _ = _tu_build(cc, dir)
            per = round(Int, r.report["step"] / r.report["dt"])
            lines, v = run_c(100, per, "Plant/gain" => 2.5)
            @test "init 0" in lines
            @test v["Plant/gain"] == 2.5
            @test isapprox(v["Y"], 2.5 * 2.0 * (1 - exp(-0.1 / 0.01)); rtol = 1e-6)
            # Out of range, late, and on a tunable parameter at runtime.
            lines, _ = run_c(1, per, "Plant/gain" => 3.5)
            @test any(l -> occursin(r"^set \d+ 3$", l), lines)   # fmi2Error
            @test any(l -> occursin("Plant/gain = 3.5 is outside its declared range [0.5, 3]", l), lines)
            lines, _ = run_c(1, per; late = ["Plant/gain" => 2.0])
            @test any(l -> occursin("Plant/gain is a fixed parameter; set it before fmi2ExitInitializationMode", l), lines)
            lines, v = run_c(2, per; late = ["Plant/tau" => 0.02])
            @test any(l -> occursin(r"^set \d+ 0$", l), lines) && v["Plant/tau"] == 0.02
            # The hot path still does not allocate.
            exe = joinpath(dir, Sys.iswindows() ? "check.exe" : "check")
            src = joinpath(dir, "sources")
            files = [joinpath(src, f) for f in ("model.c", "bg_solver.c", "fmi2_cs.c")]
            run(`$cc -std=c11 -O2 -I $src $(joinpath(_TU.RUNTIME_DIR, "alloc_check.c")) $files -o $exe -lm`)
            @test occursin("after instantiate 0", read(`$exe $per 100`, String))
        end

        @testset "C: an exposed global equals a folded export with that value" begin
            doc = _tu_globals_doc()
            dir = mktempdir()
            settings = _TU.ExportSettings(t_end = 1.0, step = 1e-2, expose_all = true,
                expose_globals = true, ranges = Dict("global:m" => (1.0, 4.0)))
            r = _TU.export_model(_tu_flat(doc), dir; settings)
            @test r.ok
            run_c, _ = _tu_build(cc, dir)
            per = round(Int, r.report["step"] / r.report["dt"])
            lines, v = run_c(100, per, "m" => 3.0)
            @test "init 0" in lines
            @test v["Source/Rate/value"] == 12.0                       # calculated
            @test isapprox(v["Int1/y"], sqrt(3.0) + 0.5 + 12.0; rtol = 1e-12)
            lines, _ = run_c(1, per; late = ["Source/Rate/value" => 1.0])
            @test any(l -> occursin("Source/Rate/value is a calculated parameter", l), lines)
            lines, _ = run_c(1, per, "m" => 5.0)
            @test any(l -> occursin("m = 5 is outside its declared range [1, 4]", l), lines)

            # (b) the folded export with the same global value, at the same dt.
            md = IR.override_globals(IR.parse_model(doc), Dict("global:m" => 3.0))
            fdir = mktempdir()
            rf = _TU.export_model(Compile.flatten(md), fdir; settings = _TU.ExportSettings(
                t_end = 1.0, step = 1e-2, dt = r.report["dt"], method = Symbol(r.report["method"]),
                expose_all = true))
            @test rf.ok
            run_f, _ = _tu_build(cc, fdir)
            _, vf = run_f(100, per)
            @test isapprox(vf["Int1/y"], v["Int1/y"]; rtol = 1e-13)
        end

        @testset "C: a DAE re-solves its algebraic start by Newton (bg_init)" begin
            flat = _tu_flat(_tu_model(_TU_DAE; t_end = 0.2))
            dir = mktempdir()
            r = _TU.export_model(flat, dir; settings = _TU.ExportSettings(t_end = 0.2,
                step = 1e-2, dt = 1e-3, method = :rodas4p, expose_all = true,
                tunables = ["Plant/c", "Plant/tau"],
                ranges = Dict("Plant/c" => (0.5, 4.0), "Plant/tau" => (0.02, 0.1))))
            @test r.ok && r.report["algebraic"] == 1
            tu = r.report["tunables"]
            @test tu["newton"] && length(tu["initializationChecks"]) == 3
            @test all(p -> p["maxStartDeviation"] < 1e-9, tu["initializationChecks"])
            run_c, _ = _tu_build(cc, dir)
            # At t = 0: z^3 + 3 z = 2 (u = 2, x = 0).
            lines, v0 = run_c(0, 10, "Plant/c" => 3.0)
            @test "init 0" in lines
            z0 = v0["Y"]
            @test isapprox(z0^3 + 3z0, 2.0; atol = 1e-12)
            # The trajectory against Julia with c = 3, tau = 0.08.
            _, v = run_c(20, 10, "Plant/c" => 3.0, "Plant/tau" => 0.08)
            doc = _tu_model(_TU_DAE; t_end = 0.2,
                params = Dict{String,Any}("c" => "3.0", "tau" => "0.08"))
            sol = _tu_reference(_tu_flat(doc), 0.2)
            @test length(sol.u[end]) == 2               # the unknowns are x and z
            yref = sum(sol(0.2))                        # y = x + z
            @test isapprox(v["Y"], yref; rtol = 1e-6)
            lines, _ = run_c(1, 10, "Plant/c" => 0.1)
            @test any(l -> occursin("outside its declared range", l), lines)
            # Without tunables the C start is the folded one and bg_init leaves it.
            r0 = _TU.export_model(flat, mktempdir(); settings = _TU.ExportSettings(t_end = 0.2,
                step = 1e-2, dt = 1e-3, method = :rodas4p))
            @test r0.ok
            cxx = Sys.which("g++")
            src = joinpath(dir, "sources")
            cxx === nothing || @test success(`$cxx -x c++ -std=c++17 -fsyntax-only -Wall -Werror -I $src $(joinpath(src, "model.c")) $(joinpath(src, "bg_solver.c"))`)
        end
    end
end
