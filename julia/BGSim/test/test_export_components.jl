# The common rotation and electrical components in the C export (plan/EXPORT_PLAN.md):
# RotationalHardStop, Clutch, Brake, PlanetaryGear, BeltDrive, WormGear, OpAmp (ideal and
# finite gain), VCVS, VCCS, CCVS, CCCS, MutualInductance, Battery, MOSFET and IGBT. Two
# models, one per domain, hold one small rig per block; each model exports, builds with
# -std=c99 -Wall -Wextra -Werror, runs, matches the Julia simulation at the common grid
# times, and its FMU does not allocate after instantiate.
#
# The smooth rigs (planetary gear, belt, the tanh-smoothed clutch, brake and worm gear, op-amp
# integrator, controlled sources, coupled coils, battery) agree with the simulation to the
# accuracy of the fixed-step method. The rigs with a switching condition on a continuous
# signal (the hard stop, the diodes of the switches, the op-amp rail limit) evaluate it once
# per step in C (W203), so they agree to the frozen-mode error of one step per switch.
# No emitter or runtime change was needed (the runtime stays at RUNTIME_VERSION 0.5.0).
# The gates come from a discrete `Compare` on the 1 ms clock, which C and the simulation
# sample at the same instants.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using Test
using BGSim
using .BondGraphGolden
import BGSim.IR
import BGSim.Compile

const _EXC = BGSim.Export

const _EXC_RUNNER = raw"""
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

function _exc_files(src; fmu = false)
    names = ["model.c", "bg_solver.c", "bg_intrinsics.c", "bg_mech.c"]
    fmu && push!(names, "fmi2_cs.c")
    return [joinpath(src, f) for f in names if isfile(joinpath(src, f))]
end

function _exc_run_c(cc, dir, report, n)
    src = joinpath(dir, "sources")
    runner = joinpath(dir, "runner.c")
    write(runner, _EXC_RUNNER)
    exe = joinpath(dir, Sys.iswindows() ? "runner.exe" : "runner")
    run(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -I $src $(_exc_files(src)) $runner -o $exe -lm`)
    rows = [parse.(Float64, split(l)) for l in eachline(`$exe $n`)]
    model_c = read(joinpath(src, "model.c"), String)
    xnames = [String(m.captures[2]) for m in eachmatch(r"/\* x\[(\d+)\] = (\S+) \*/", model_c)]
    ynames = vcat([o["name"] for o in report["outputs"]], String.(report["locals"]))
    return permutedims(reduce(hcat, rows)), xnames, ynames
end

_p(pairs...) = Dict{String,Any}(k => string(v) for (k, v) in pairs)
_const(id, name, value) = bg_node(id, name, bg_ref("stdlib:sources/Constant"); params = _p("value" => value))

# ---------------------------------------------------------------------------------------
# The rotation model: one rig per block, all grounded on one FixedShaft.
# ---------------------------------------------------------------------------------------
function _exc_rotation_model()
    R(name) = bg_ref("stdlib:rotation/" * name)
    nodes = Any[
        bg_node("gnd", "F0", R("FixedShaft")),
        _const("one", "One", 1.0),
        # Hard stop: an inertia that starts spinning bounces between the two stops.
        bg_node("hs_j", "HSJ", R("Inertia"); params = _p("J" => 0.01), starts = _p("w" => 1.0)),
        bg_node("hs", "HS", R("RotationalHardStop");
            params = _p("lower" => -0.2, "upper" => 0.2, "k" => 4.0, "d" => 0.01)),
        # Clutch: a torque drives J1, the engaged clutch drags J2 along.
        bg_node("cl_t", "CLT", R("TorqueSource"); params = _p("T" => 1.0)),
        bg_node("cl_j1", "CLJ1", R("Inertia"); params = _p("J" => 0.02)),
        bg_node("cl", "CL", R("Clutch"); params = _p("w_eps" => 0.01)),
        bg_node("cl_j2", "CLJ2", R("Inertia"); params = _p("J" => 0.03)),
        _const("cl_fn", "CLFN", 100.0),
        # Brake: a spinning inertia is braked to a stop.
        bg_node("br_j", "BRJ", R("Inertia"); params = _p("J" => 0.05), starts = _p("w" => 4.0)),
        bg_node("br", "BR", R("Brake"); params = _p("w_eps" => 0.01)),
        _const("br_fn", "BRFN", 5.0),
        # Planetary gear: a torque on the sun inertia, ring fixed, carrier inertia + damper.
        bg_node("pg_t", "PGT", R("TorqueSource"); params = _p("T" => 0.5)),
        bg_node("pg_js", "PGJS", R("Inertia"); params = _p("J" => 0.01)),
        bg_node("pg", "PG", R("PlanetaryGear"); params = _p("ratio" => 3.0)),
        bg_node("pg_jc", "PGJC", R("Inertia"); params = _p("J" => 0.1)),
        bg_node("pg_d", "PGD", R("RotationalDamper"); params = _p("d" => 0.2)),
        # Belt drive: a sine speed on pulley a, an inertia and a damper on pulley b.
        bg_node("bd_s", "BDS", bg_ref("stdlib:sources/Sine");
            params = _p("amplitude" => 5.0, "frequency" => 6.0)),
        bg_node("bd_w", "BDW", R("SpeedSource"); params = _p("w" => 1.0)),
        bg_node("bd", "BD", R("BeltDrive"); params = _p("k" => 2.0e3, "d" => 5.0)),
        bg_node("bd_j", "BDJ", R("Inertia"); params = _p("J" => 0.01)),
        bg_node("bd_d", "BDD", R("RotationalDamper"); params = _p("d" => 0.05)),
        # Worm gear: a sine torque on the worm inertia, the wheel inertia with a damper.
        bg_node("wg_s", "WGS", bg_ref("stdlib:sources/Sine");
            params = _p("amplitude" => 0.2, "frequency" => 4.0)),
        bg_node("wg_t", "WGT", R("TorqueSource"); params = _p("T" => 1.0)),
        bg_node("wg_ja", "WGJA", R("Inertia"); params = _p("J" => 1.0e-3)),
        bg_node("wg", "WG", R("WormGear"); params = _p("n" => 10.0, "w_eps" => 0.01)),
        bg_node("wg_jb", "WGJB", R("Inertia"); params = _p("J" => 0.05)),
        bg_node("wg_d", "WGD", R("RotationalDamper"); params = _p("d" => 0.1)),
        bg_node("y1", "Y1", bg_ref("stdlib:converters/ExportOutput")),
    ]
    c = 0
    conns = Any[]
    wire(a, pa, b, pb) = push!(conns, bg_conn("w$(c += 1)", "wire", a, pa, b, pb))
    sig(a, pa, b, pb) = push!(conns, bg_conn("s$(c += 1)", "signal", a, pa, b, pb))
    wire("hs_j", "a", "hs", "a"); wire("hs", "b", "gnd", "a"); wire("hs_j", "b", "gnd", "a")
    sig("one", "y", "cl_t", "u"); wire("cl_t", "a", "gnd", "a"); wire("cl_t", "b", "cl_j1", "a")
    wire("cl_j1", "b", "gnd", "a"); wire("cl_j1", "a", "cl", "a"); wire("cl", "b", "cl_j2", "a")
    wire("cl_j2", "b", "gnd", "a"); sig("cl_fn", "y", "cl", "f_n")
    wire("br_j", "a", "br", "a"); wire("br_j", "b", "gnd", "a"); sig("br_fn", "y", "br", "f_n")
    sig("one", "y", "pg_t", "u"); wire("pg_t", "a", "gnd", "a"); wire("pg_t", "b", "pg_js", "a")
    wire("pg_js", "b", "gnd", "a"); wire("pg_js", "a", "pg", "sun"); wire("pg", "ring", "gnd", "a")
    wire("pg", "carrier", "pg_jc", "a"); wire("pg_jc", "b", "gnd", "a")
    wire("pg_jc", "a", "pg_d", "a"); wire("pg_d", "b", "gnd", "a")
    sig("bd_s", "y", "bd_w", "u"); wire("bd_w", "a", "bd", "a"); wire("bd", "b", "bd_j", "a")
    wire("bd_j", "b", "gnd", "a"); wire("bd_j", "a", "bd_d", "a"); wire("bd_d", "b", "gnd", "a")
    sig("wg_s", "y", "wg_t", "u"); wire("wg_t", "a", "gnd", "a"); wire("wg_t", "b", "wg_ja", "a")
    wire("wg_ja", "b", "gnd", "a"); wire("wg_ja", "a", "wg", "a"); wire("wg", "b", "wg_jb", "a")
    wire("wg_jb", "b", "gnd", "a"); wire("wg_jb", "a", "wg_d", "a"); wire("wg_d", "b", "gnd", "a")
    sig("cl_fn", "y", "y1", "u")
    return bg_model("RotationComponentsExport", nodes, conns; t_end = 1.0, points = 101)
end

# ---------------------------------------------------------------------------------------
# The electrical model: one rig per block, all on one Ground.
# ---------------------------------------------------------------------------------------
function _exc_electrical_model()
    E(name) = bg_ref("stdlib:electrical/" * name)
    sine(id, name, amp, freq) = bg_node(id, name, bg_ref("stdlib:sources/Sine");
        params = _p("amplitude" => amp, "frequency" => freq))
    opamp(id, name, ideal) = begin
        node = bg_node(id, name, E("OpAmp"); params = _p("A" => 200.0, "V_pos" => 5.0,
            "V_neg" => -4.0))
        node["constants"] = Dict{String,Any}("ideal" => ideal)
        node
    end
    nodes = Any[
        bg_node("gnd", "G0", E("Ground")),
        sine("sin", "Sin", 2.0, 10.0),
        bg_node("vs", "VS", E("VoltageSource")),
        # Op-amp integrator (ideal) and saturating inverting amplifier (finite gain).
        bg_node("oi_r", "OIR", E("Resistor"); params = _p("R" => 1.0e3)),
        bg_node("oi_c", "OIC", E("Capacitor"); params = _p("C" => 1.0e-4)),
        opamp("oi", "OI", 1),
        bg_node("oa_r1", "OAR1", E("Resistor"); params = _p("R" => 1.0e3)),
        bg_node("oa_rf", "OARF", E("Resistor"); params = _p("R" => 5.0e3)),
        bg_node("oa_cl", "OACL", E("Capacitor"); params = _p("C" => 1.0e-4)),
        bg_node("oa_rl", "OARL", E("Resistor"); params = _p("R" => 100.0)),
        opamp("oa", "OA", 0),
        # The four controlled sources, each into an RC load.
        bg_node("vcvs", "VCVS", E("VCVS"); params = _p("gain" => 2.0)),
        bg_node("vccs", "VCCS", E("VCCS"); params = _p("transconductance" => 0.01)),
        bg_node("ccvs", "CCVS", E("CCVS"); params = _p("transresistance" => 300.0)),
        bg_node("cccs", "CCCS", E("CCCS"); params = _p("gain" => 3.0)),
        bg_node("cc_rs", "CCRS", E("Resistor"); params = _p("R" => 100.0)),
        bg_node("cc_rs2", "CCRS2", E("Resistor"); params = _p("R" => 100.0)),
        # Coupled coils: primary through a resistor, secondary into a resistor.
        bg_node("mi_r1", "MIR1", E("Resistor"); params = _p("R" => 5.0)),
        bg_node("mi", "MI", E("MutualInductance"); params = _p("L1" => 0.05, "L2" => 0.1, "k" => 0.7)),
        bg_node("mi_r2", "MIR2", E("Resistor"); params = _p("R" => 20.0)),
        # Battery: a sine current in and out.
        bg_node("bat_i", "BATI", E("CurrentSource"); params = _p("I" => 1.0)),
        bg_node("bat", "BAT", E("Battery"); params = _p("capacity" => 0.001),
            starts = _p("soc" => 0.6)),
        # MOSFET and IGBT: a sine supply through R into a node with C, the switch to
        # ground, the gate on a slower sine (Compare > 0 on the 1 ms clock).
        sine("gs", "GS", 1.0, 7.0),
        _const("zero", "Zero", 0.0),
        bg_node("cmp", "Cmp", bg_ref("stdlib:discrete/Compare"); params = _p("op" => 4)),
        bg_node("mo_r", "MOR", E("Resistor"); params = _p("R" => 10.0)),
        bg_node("mo_c", "MOC", E("Capacitor"); params = _p("C" => 1.0e-3)),
        bg_node("mo", "MO", E("MOSFET"); params = _p("R_on" => 0.5, "R_d" => 0.5)),
        bg_node("ig_r", "IGR", E("Resistor"); params = _p("R" => 10.0)),
        bg_node("ig_c", "IGC", E("Capacitor"); params = _p("C" => 1.0e-3)),
        bg_node("ig", "IG", E("IGBT"); params = _p("R_on" => 0.5, "V_ce0" => 0.3, "R_d" => 0.5)),
        bg_node("y1", "Y1", bg_ref("stdlib:converters/ExportOutput")),
    ]
    c = 0
    conns = Any[]
    wire(a, pa, b, pb) = push!(conns, bg_conn("w$(c += 1)", "wire", a, pa, b, pb))
    sig(a, pa, b, pb) = push!(conns, bg_conn("s$(c += 1)", "signal", a, pa, b, pb))
    g(a, pa) = wire(a, pa, "gnd", "p")
    sig("sin", "y", "vs", "u"); g("vs", "n")
    # Integrator: VS -> R -> in_n, C from in_n to out, in_p grounded.
    wire("vs", "p", "oi_r", "p"); wire("oi_r", "n", "oi", "in_n"); wire("oi", "in_n", "oi_c", "p")
    wire("oi_c", "n", "oi", "out"); g("oi", "in_p")
    # Finite-gain inverting amplifier (gain -5, so the 2 V sine saturates at the rails),
    # with an RC load on the output.
    wire("vs", "p", "oa_r1", "p"); wire("oa_r1", "n", "oa", "in_n"); wire("oa", "in_n", "oa_rf", "p")
    wire("oa_rf", "n", "oa", "out"); g("oa", "in_p"); wire("oa", "out", "oa_rl", "p")
    wire("oa_rl", "n", "oa_cl", "p"); g("oa_cl", "n")
    # Voltage control: p1 at the source, n1 grounded; the outputs drive the RC loads of
    # their own (the shared resistor/capacitor pairs below).
    for (id, name) in (("vcvs", "VCVS"), ("vccs", "VCCS"))
        wire("vs", "p", id, "p1"); g(id, "n1"); g(id, "n2")
        push!(nodes, bg_node("$(id)_r", "$(name)R", E("Resistor"); params = _p("R" => 50.0)))
        push!(nodes, bg_node("$(id)_c", "$(name)C", E("Capacitor"); params = _p("C" => 1.0e-3)))
        wire(id, "p2", "$(id)_r", "p"); wire("$(id)_r", "n", "$(id)_c", "p"); g("$(id)_c", "n")
    end
    # Current control: the source drives the sensing short through a resistor.
    for (id, name, rs) in (("ccvs", "CCVS", "cc_rs"), ("cccs", "CCCS", "cc_rs2"))
        wire("vs", "p", rs, "p"); wire(rs, "n", id, "p1"); g(id, "n1"); g(id, "n2")
        push!(nodes, bg_node("$(id)_r", "$(name)R", E("Resistor"); params = _p("R" => 50.0)))
        push!(nodes, bg_node("$(id)_c", "$(name)C", E("Capacitor"); params = _p("C" => 1.0e-3)))
        wire(id, "p2", "$(id)_r", "p"); wire("$(id)_r", "n", "$(id)_c", "p"); g("$(id)_c", "n")
    end
    wire("vs", "p", "mi_r1", "p"); wire("mi_r1", "n", "mi", "p1"); g("mi", "n1")
    wire("mi", "p2", "mi_r2", "p"); g("mi_r2", "n"); g("mi", "n2")
    sig("sin", "y", "bat_i", "u"); wire("bat_i", "p", "bat", "p"); g("bat_i", "n"); g("bat", "n")
    sig("gs", "y", "cmp", "u1"); sig("zero", "y", "cmp", "u2")
    for (id, hi, lo) in (("mo", "d", "s"), ("ig", "c", "e"))
        wire("vs", "p", "$(id)_r", "p"); wire("$(id)_r", "n", "$(id)_c", "p"); g("$(id)_c", "n")
        wire("$(id)_c", "p", id, hi); g(id, lo); sig("cmp", "y", id, "gate")
    end
    sig("sin", "y", "y1", "u")
    return bg_model("ElectricalComponentsExport", nodes, conns; t_end = 1.0, points = 101)
end

"""Compare every C state and local that the simulation also recorded, on the 10 ms grid,
relative to the signal's range; returns name => error."""
function _exc_compare(rows, xn, yn, columns, n)
    t = rows[:, 1]
    errs = Dict{String,Float64}()
    for (j, name) in enumerate(vcat(xn, yn))
        haskey(columns, name) || continue
        col = rows[:, 1 + j]
        sim = [bg_value(columns, name, t[k]) for k in 1:10:n + 1]
        scale = max(maximum(abs, sim), 1e-6)
        errs[name] = maximum(abs(col[k] - s) for (k, s) in zip(1:10:n + 1, sim)) / scale
    end
    return errs
end

function _exc_check(doc, tolerances; n = 1000)
    flat = Compile.flatten(IR.parse_model(doc))
    @test isempty([d for d in flat.diagnostics if d.severity == "error"])
    dir = mktempdir()
    r = _EXC.export_model(flat, dir;
        settings = _EXC.ExportSettings(t_end = 1.0, dt = 1e-3, expose_all = true))
    @test r.ok
    errors = [d for d in r.diagnostics if d.severity == "error"]
    @test isempty(errors)
    isempty(errors) || foreach(d -> @info("export error", d.code, d.message), errors)
    r.ok || return nothing
    cc = Sys.which("gcc")
    if cc === nothing
        @info "export: no gcc on PATH, the component compile-and-run checks are skipped"
        return nothing
    end
    rows, xn, yn = _exc_run_c(cc, dir, r.report, n)
    @test size(rows, 1) == n + 1
    @test rows[:, 1] ≈ (0:n) .* 1e-3
    @test all(isfinite, rows)
    columns, result, _ = bg_run(doc)
    @test result.status == "done"
    errs = _exc_compare(rows, xn, yn, columns, n)
    if get(ENV, "BG_EXC_DEBUG", "") != ""
        println("states: ", join(xn, ", "))
        for (k, v) in sort(collect(errs); by = first)
            println(rpad(k, 24), " ", v)
        end
    end
    # Every block instance has at least one compared signal.
    for (prefix, tol) in tolerances
        mine = [(k, v) for (k, v) in errs if k == prefix || startswith(k, prefix * "/")]
        @test !isempty(mine)
        worst = isempty(mine) ? 0.0 : maximum(last, mine)
        worst <= tol || @info "export vs simulation" prefix worst tol sort(mine; by = last)[end]
        @test worst <= tol
    end
    # A second run of the C model (bg_reset, as fmi2Reset) repeats the first bit for bit.
    rows2, _, _ = _exc_run_c(cc, dir, r.report, n)
    @test rows2 == rows

    src = joinpath(dir, "sources")
    files = _exc_files(src; fmu = true)
    for f in files
        @test success(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -I $src -c $f -o $(joinpath(dir, "x.o"))`)
    end
    harness = joinpath(_EXC.RUNTIME_DIR, "alloc_check.c")
    exe = joinpath(dir, Sys.iswindows() ? "check.exe" : "check")
    @test success(`$cc -std=c11 -O2 -I $src $harness $files -o $exe -lm`)
    out = read(`$exe 1 1000`, String)
    @test occursin("after instantiate 0", out)
    return errs
end

@testset "rotation components in the C export" begin
    # Relative errors against the simulation (scaled by each signal's range).
    _exc_check(_exc_rotation_model(), [
        # The contact switches once per step: the states drift by the frozen-mode error,
        # and the small contact torque differs by a larger share of its own range.
        "HSJ/phi" => 5e-3, "HSJ/w" => 2e-2, "HSJ" => 0.15, "HS" => 0.15,
        "CLJ1" => 1e-6, "CLJ2" => 1e-6, "CL" => 1e-6,
        "BRJ" => 1e-4, "BR" => 1e-4,               # the tanh stop at zero speed
        "PGJS" => 1e-6, "PGJC" => 1e-6, "PG" => 1e-6,
        "BD" => 1e-6, "BDJ" => 1e-6,
        "WGJA" => 1e-5, "WGJB" => 1e-5, "WG" => 1e-5,
    ])
end

@testset "electrical components in the C export" begin
    _exc_check(_exc_electrical_model(), [
        "OIC" => 1e-6, "OI" => 1e-6,
        "OACL" => 1e-2, "OA" => 1e-2,              # the rail limit switches once per step
        "VCVSC" => 1e-6, "VCCSC" => 1e-6, "CCVSC" => 1e-6, "CCCSC" => 1e-6,
        "MI" => 1e-6,
        "BAT" => 1e-6,
        # The diodes switch once per step. The capacitor voltages (the states) stay close;
        # the capacitor currents jump at every gate edge with a time constant R_on*C = 0.5 ms
        # below the 1 ms step, so they differ by a larger share of their range.
        "MOC/v" => 5e-3, "MOC" => 0.1, "MO" => 5e-2,
        "IGC/v" => 5e-3, "IGC" => 0.15, "IG" => 5e-2,
    ])
end
