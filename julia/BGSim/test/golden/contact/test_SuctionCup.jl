# Golden tests for `stdlib:contact/SuctionCup` and `stdlib:contact/VacuumGenerator`, through
# the real pipeline.
#
# Rig: the cup hangs from the ground (`GroundSpatial` -> `FixedTransform3DNeutral` mount, cup
# on side `a`), a free part (`RigidBody3D` + `PoseIntegrator3D`) hangs from the cup through a
# second neutral mount, and a `VacuumGenerator` evacuates the cup chamber directly. The cup
# frame may be turned (`qc`) so that gravity loads the cup axially or in shear. Checks:
#
#   * statics: the axial bellows stiffness (ext = m g / k_ax), the lateral stiffness
#     (deflection m g / k_lat) and the tilt stiffness (moment m g dx = 2 qw qy k_tilt);
#   * pull-off at Fcap = A_eff dp: a part of 0.95 Fcap / g holds, 1.05 Fcap / g is lost
#     (the lip lifts, the leak destroys the vacuum, the `lost` latch trips, the part falls);
#   * shear at mu N: 0.9 mu Fcap / g holds in a horizontal cup, 1.1 mu Fcap / g slides off;
#   * vacuum build-up: dp(t) = dp_max (1 - exp(-t / tau)), tau = V dp_max / (p_atm Q_max),
#     and with a porous part the steady vacuum dp_max / (1 + perm A_eff dp_max / Q_max) with
#     tau' = V / (p_atm (Q_max / dp_max + perm A_eff));
#   * the pump-like generator curve (n = 3) against an RK4 reference, and the release path.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

const _SC_G = 9.81
const _SC_A = 1.4e-3
const _SC_DP = 6.0e4
const _SC_QMAX = 1.0e-3
const _SC_PATM = 101325.0
const _SC_FCAP = _SC_A * _SC_DP          # 84 N

_sc_str(d) = Dict{String,Any}(String(k) => string(v) for (k, v) in d)

"""Quaternion product (w, x, y, z)."""
function _sc_qmul(a, b)
    return (a[1] * b[1] - a[2] * b[2] - a[3] * b[3] - a[4] * b[4],
        a[1] * b[2] + a[2] * b[1] + a[3] * b[4] - a[4] * b[3],
        a[1] * b[3] - a[2] * b[4] + a[3] * b[1] + a[4] * b[2],
        a[1] * b[4] + a[2] * b[3] - a[3] * b[2] + a[4] * b[1])
end

function _sc_rot(q)
    w, x, y, z = q
    return [w^2+x^2-y^2-z^2 2(x*y-w*z) 2(x*z+w*y);
        2(x*y+w*z) w^2-x^2+y^2-z^2 2(y*z-w*x);
        2(x*z-w*y) 2(y*z+w*x) w^2-x^2-y^2+z^2]
end

"""
The rig. `qc` is the cup frame in the world; the part's body frame starts aligned with the
cup frame, its centre of mass at `(dx, 0, -hcm)` from the attach point (point frame), the
attach point at `r0` (cup frame, default `(0, 0, -L0)`). `cup`/`gen` are parameter overrides.
"""
function _sc_rig(; m = 4.0, J = 0.01, g0 = _SC_G, qc = (1.0, 0.0, 0.0, 0.0), hcm = 0.0, dx = 0.0,
    r0 = nothing, e0 = (0.0, 0.0), p0 = -_SC_DP, cup = Dict(), gen = Dict(), u = 1.0,
    t_end = 4.0, points = 401)
    L0 = 0.04
    r0 = r0 === nothing ? (0.0, 0.0, -L0) : r0
    cupp = merge(Dict("d_ax" => 100.0, "d_lat" => 100.0, "d_rot" => 0.2), cup)
    genp = merge(Dict("dp_max" => _SC_DP, "Q_max" => _SC_QMAX), gen)
    R = _sc_rot(qc)
    point = R * collect(r0)                         # attach point in the world
    com = point + R * [dx, 0.0, -hcm]
    qci = (qc[1], -qc[2], -qc[3], -qc[4])
    nodes = Any[
        bg_node("gr", "Ground", bg_ref("stdlib:multibond/GroundSpatial")),
        bg_node("gm", "GMount", bg_ref("stdlib:multibond/FixedTransform3DNeutral");
            params = _sc_str(Dict("qw" => qci[1], "qx" => qci[2], "qy" => qci[3], "qz" => qci[4]))),
        bg_node("cu", "Cup", bg_ref("stdlib:contact/SuctionCup"); params = _sc_str(cupp),
            starts = _sc_str(Dict("rx" => r0[1], "ry" => r0[2], "rz" => r0[3], "p" => p0,
                "ex" => e0[1], "ey" => e0[2]))),
        bg_node("pm", "PMount", bg_ref("stdlib:multibond/FixedTransform3DNeutral");
            params = _sc_str(Dict("x" => dx, "y" => 0.0, "z" => -hcm))),
        bg_node("b", "Part", bg_ref("stdlib:spatial/RigidBody3D");
            params = Dict{String,Any}("m" => string(m), "J" => "[$J, $J, $J]", "g0" => string(g0)),
            starts = Dict{String,Any}("inertia/P" => "[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]")),
        bg_node("po", "Pose", bg_ref("stdlib:multibond/PoseIntegrator3D");
            starts = _sc_str(Dict("qw" => qc[1], "qx" => qc[2], "qy" => qc[3], "qz" => qc[4],
                "px" => com[1], "py" => com[2], "pz" => com[3]))),
        bg_node("ge", "Gen", bg_ref("stdlib:contact/VacuumGenerator"); params = _sc_str(genp)),
        bg_node("on", "On", bg_ref("stdlib:sources/Constant"); params = _sc_str(Dict("value" => u))),
    ]
    conns = Any[
        bg_conn("c1", "bond", "gr", "p", "gm", "b"),
        bg_conn("c2", "bond", "gm", "a", "cu", "a"),
        bg_conn("c3", "bond", "b", "p", "pm", "b"),
        bg_conn("c4", "bond", "pm", "a", "cu", "b"),
        bg_conn("c5", "signal", "b", "V", "po", "tw"),
        bg_conn("c6", "signal", "po", "g", "b", "g"),
        bg_conn("c7", "wire", "ge", "a", "cu", "vac"),
        bg_conn("c8", "signal", "on", "y", "ge", "u"),
    ]
    return bg_model("SuctionCupRig", nodes, conns; t_end = t_end, points = points,
        reltol = 1.0e-9, abstol = 1.0e-11)
end

_sc_ok(result) = result.status == "done" &&
                 isempty([e for e in result.diagnostics if e.severity == "error"])

@testset "golden: SuctionCup" begin
    k_ax, k_lat, k_tilt = 5000.0, 2500.0, 3.0

    @testset "axial bellows stiffness under a hanging part" begin
        m = 4.0
        cols, result, _ = bg_run(_sc_rig(; m = m, cup = Dict("A_lip0" => 0.0), t_end = 6.0, points = 61))
        @test _sc_ok(result)
        t = 6.0
        @test isapprox(bg_value(cols, "Cup/T", t), m * _SC_G; rtol = 1e-6)
        @test isapprox(bg_value(cols, "Cup/ext", t), m * _SC_G / k_ax; rtol = 1e-5)
        @test isapprox(bg_value(cols, "Cup/dp", t), _SC_DP; rtol = 1e-6)
        @test isapprox(bg_value(cols, "Cup/Fcap", t), _SC_FCAP; rtol = 1e-6)
        @test isapprox(bg_value(cols, "Cup/N_lip", t), _SC_FCAP - m * _SC_G; rtol = 1e-5)
        @test isapprox(bg_value(cols, "Cup/U", t), m * _SC_G / (_SC_FCAP + 0.1); rtol = 1e-4)
        @test bg_value(cols, "Cup/h", t) < 1e-6
        @test bg_value(cols, "Cup/sealed", t) == 1.0
    end

    @testset "pull-off at A_eff dp" begin
        for (frac, holds) in ((0.95, true), (1.05, false))
            m = frac * _SC_FCAP / _SC_G
            ext0 = min(m * _SC_G, _SC_FCAP) / k_ax       # start at the bellows' static stretch
            cols, result, _ = bg_run(_sc_rig(; m = m, r0 = (0.0, 0.0, -0.04 - ext0),
                t_end = 1.0, points = 101))
            @test _sc_ok(result)
            if holds
                @test isapprox(bg_value(cols, "Cup/T", 1.0), m * _SC_G; rtol = 1e-4)
                @test maximum(bg_all(cols, "Cup/h")) < 1e-5
                @test bg_value(cols, "Cup/sealed", 1.0) == 1.0
            else
                @test bg_value(cols, "Cup/sealed", 1.0) == 0.0      # the latch tripped
                @test bg_value(cols, "Cup/dp", 1.0) < 0.1 * _SC_DP   # the leak killed the vacuum
                @test bg_value(cols, "Pose/pz", 1.0) < -0.3          # the part fell
                @test maximum(bg_all(cols, "Cup/T")) <= _SC_FCAP + 0.05  # never pulled above Fcap
            end
        end
    end

    @testset "shear at mu N (horizontal cup)" begin
        qc = (cos(pi / 4), sin(pi / 4), 0.0, 0.0)         # cup axis along world -y
        mu = 0.5
        for (frac, holds) in ((0.9, true), (1.1, false))
            m = frac * mu * _SC_FCAP / _SC_G
            e = -m * _SC_G / k_lat                          # static lateral deflection (cup y)
            cols, result, _ = bg_run(_sc_rig(; m = m, qc = qc, hcm = 1.0e-3,
                r0 = (0.0, e, -0.04), e0 = (0.0, e), t_end = 1.0, points = 101))
            @test _sc_ok(result)
            if holds
                @test isapprox(bg_value(cols, "Cup/F_lat", 1.0), m * _SC_G; rtol = 2e-3)
                @test isapprox(bg_value(cols, "Cup/ey", 1.0), e; rtol = 2e-3)
                @test abs(bg_value(cols, "Cup/ry", 1.0) - e) < 1e-4   # no sliding
            else
                # Sliding at mu N: the part runs down the cup (world -z) under m g - mu Fcap.
                drop = bg_value(cols, "Pose/pz", 0.0) - bg_value(cols, "Pose/pz", 1.0)
                @test drop > 0.2
                Fl1 = bg_value(cols, "Cup/F_lat", 1.0)
                @test isapprox(Fl1, mu * bg_value(cols, "Cup/N_lip", 1.0) + 0.5; rtol = 0.02)
                @test maximum(bg_all(cols, "Cup/F_lat")) < 1.15 * mu * _SC_FCAP
            end
        end
    end

    @testset "tilt stiffness" begin
        m, dx = 2.0, 0.01
        cols, result, _ = bg_run(_sc_rig(; m = m, dx = dx, t_end = 6.0, points = 61))
        @test _sc_ok(result)
        qw, qy = bg_value(cols, "Cup/qw", 6.0), bg_value(cols, "Cup/qy", 6.0)
        phi = 2 * atan(qy, qw)
        # Moment balance about the attach point: the bellows moment 2 qw qy k_tilt carries the
        # weight's lever dx cos(phi) (the centre of mass is level with the point).
        @test isapprox(2 * qw * qy * k_tilt, m * _SC_G * dx * cos(phi); rtol = 1e-4)
        @test isapprox(bg_value(cols, "Cup/M_tilt", 6.0), m * _SC_G * dx * cos(phi); rtol = 1e-4)
        @test bg_value(cols, "Cup/sealed", 6.0) == 1.0
    end

    @testset "vacuum build-up: time constant and porous steady state" begin
        V = 2.0e-5
        for perm in (0.0, 2.0e-6)
            cols, result, _ = bg_run(_sc_rig(; g0 = 0.0, p0 = 0.0,
                cup = Dict("perm" => perm, "A_lip0" => 0.0), t_end = 0.1, points = 101))
            @test _sc_ok(result)
            G = perm * _SC_A
            dp_inf = _SC_DP / (1 + G * _SC_DP / _SC_QMAX)
            tau = V / (_SC_PATM * (_SC_QMAX / _SC_DP + G))
            for t in (0.005, 0.01, 0.02, 0.05, 0.1)
                @test isapprox(bg_value(cols, "Cup/dp", t), dp_inf * (1 - exp(-t / tau)); rtol = 1e-5)
            end
            @test isapprox(bg_value(cols, "Cup/Q_por", 0.1), G * bg_value(cols, "Cup/dp", 0.1); rtol = 1e-9)
            perm == 0 && @test isapprox(tau, V * _SC_DP / (_SC_PATM * _SC_QMAX); rtol = 1e-12)
        end
    end
end

@testset "golden: VacuumGenerator" begin
    @testset "pump-like curve (n = 3) against RK4" begin
        V, n = 2.0e-5, 3.0
        cols, result, _ = bg_run(_sc_rig(; g0 = 0.0, p0 = 0.0, cup = Dict("A_lip0" => 0.0),
            gen = Dict("n" => n), t_end = 0.1, points = 101))
        @test _sc_ok(result)
        f(dp) = _SC_PATM / V * _SC_QMAX * (1 - (dp / _SC_DP)^3)
        dp, h = 0.0, 1.0e-6
        ref = Dict{Float64,Float64}()
        for k in 1:100_000
            k1 = f(dp); k2 = f(dp + h / 2 * k1); k3 = f(dp + h / 2 * k2); k4 = f(dp + h * k3)
            dp += h / 6 * (k1 + 2k2 + 2k3 + k4)
            k % 10_000 == 0 && (ref[round(k * h; digits = 6)] = dp)
        end
        for t in (0.01, 0.02, 0.05, 0.1)
            @test isapprox(bg_value(cols, "Cup/dp", t), ref[t]; rtol = 1e-6)
            dpt = bg_value(cols, "Gen/dp", t)
            @test isapprox(bg_value(cols, "Gen/Q", t), _SC_QMAX * (1 - (dpt / _SC_DP)^3); rtol = 1e-9, atol = 1e-6 * _SC_QMAX)
        end
    end

    @testset "release vents the cup" begin
        # u = 0: the generator is a conductance G_rel to atmosphere; a sealed cup at -60 kPa
        # relaxes with tau = V / (p_atm G_rel).
        V, G = 2.0e-5, 1.0e-7
        cols, result, _ = bg_run(_sc_rig(; g0 = 0.0, u = 0.0, cup = Dict("A_lip0" => 0.0),
            t_end = 0.01, points = 101))
        @test _sc_ok(result)
        tau = V / (_SC_PATM * G)
        for t in (0.001, 0.002, 0.005)
            @test isapprox(bg_value(cols, "Cup/dp", t), _SC_DP * exp(-t / tau); rtol = 1e-5)
        end
    end
end
