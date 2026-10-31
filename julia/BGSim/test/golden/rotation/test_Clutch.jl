# Golden tests for `stdlib:rotation/Clutch` and `stdlib:rotation/Brake`, through the real
# pipeline.
#
# Clutch, constant slip: a `SpeedSource` holds the slip speed `w = a.f - b.f` (b is a
# `FixedShaft`) and a Constant is the normal force f_n. The block law is
#
#   s = w_eps > 0 ? tanh(w/w_eps) : sign(w)
#   T = n_faces * r_eff * max(f_n, 0) * (mu_c + (mu_s - mu_c)*exp(-|w|/w_s)) * s,
#   a.e = T, b.e = -T,
#
# swept over slip speeds of both signs, both smoothing branches and a negative (opening)
# normal force; the dissipated power T*w is never negative.
#
# Brake, spin-down: an `Inertia` J that starts at w0 is braked to the housing with a
# constant normal force and mu_s = mu_c, so the braking torque is the constant
# T_b = n_faces*r_eff*mu*f_n while w >> w_eps. Analytic: w(t) = w0 - T_b*t/J until the stop
# at t_stop = J*w0/T_b, phi(t) = w0*t - T_b*t^2/(2J); after the stop the speed stays at zero
# (to the creep of the tanh smoothing). The kinetic energy lost equals the integral of the
# brake's dissipated power.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

const CLUTCH_PARAMS = Dict{String,Any}(
    "mu_s" => "0.6", "mu_c" => "0.4", "r_eff" => "0.08", "n_faces" => "2.0",
    "w_s" => "0.05")

"""The exact clutch law, written from the block's specification."""
function clutch_torque(w, f_n, w_eps; mu_s = 0.6, mu_c = 0.4, r_eff = 0.08, n_faces = 2.0,
    w_s = 0.05)
    s = w_eps > 0.0 ? tanh(w / w_eps) : (w > 0.0 ? 1.0 : (w < 0.0 ? -1.0 : 0.0))
    return n_faces * r_eff * max(f_n, 0.0) * (mu_c + (mu_s - mu_c) * exp(-abs(w) / w_s)) * s
end

function clutch_model(w, f_n, w_eps)
    params = copy(CLUTCH_PARAMS)
    params["w_eps"] = string(w_eps)
    return bg_model(
        "ClutchConstantSlip",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "W1", bg_ref("stdlib:rotation/SpeedSource");
                params = Dict{String,Any}("w" => string(w))),
            bg_node("n3", "CL1", bg_ref("stdlib:rotation/Clutch"); params = params),
            bg_node("n4", "F1", bg_ref("stdlib:rotation/FixedShaft")),
            bg_node("n5", "FN", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => string(f_n))),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n3", "b", "n4", "a"),
            bg_conn("c4", "signal", "n5", "y", "n3", "f_n"),
        ];
        t_end = 0.01, points = 11,
    )
end

@testset "golden: Clutch" begin
    for (w, f_n, w_eps) in ((0.3, 500.0, 1e-3), (-0.3, 500.0, 1e-3), (0.02, 500.0, 1e-3),
        (-0.02, 800.0, 1e-3), (2e-4, 500.0, 1e-3), (0.0, 500.0, 1e-3), (0.3, -100.0, 1e-3),
        (0.05, 500.0, 0.0), (-0.05, 500.0, 0.0))
        columns, result, flat = bg_run(clutch_model(w, f_n, w_eps))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        @test flat.stats.states == 0
        expected = clutch_torque(w, f_n, w_eps)
        for t in (0.0, 0.005, 0.01)
            @test isapprox(bg_value(columns, "CL1/w", t), w; rtol = 1e-9, atol = 1e-15)
            @test isapprox(bg_value(columns, "CL1/T", t), expected; rtol = 1e-6, atol = 1e-12)
            @test isapprox(bg_value(columns, "CL1/a.e", t), expected; rtol = 1e-6, atol = 1e-12)
            @test isapprox(bg_value(columns, "CL1/b.e", t), -expected; rtol = 1e-6, atol = 1e-12)
            @test isapprox(bg_value(columns, "W1/a.e", t), -expected; rtol = 1e-6, atol = 1e-12)
            # Dissipation: the power into the clutch is T*w >= 0.
            p = bg_value(columns, "CL1/a.P", t) + bg_value(columns, "CL1/b.P", t)
            @test p >= 0.0
            @test isapprox(p, expected * w; rtol = 1e-6, atol = 1e-12)
        end
    end
    # A negative normal force opens the clutch completely.
    columns, _, _ = bg_run(clutch_model(0.3, -100.0, 1e-3))
    @test bg_value(columns, "CL1/T", 0.0) == 0.0
end

@testset "golden: Brake" begin
    J = 0.05
    w0 = 20.0
    f_n = 400.0
    mu = 0.5
    r_eff = 0.1
    n_faces = 2.0
    T_b = n_faces * r_eff * mu * f_n           # 40 N*m
    t_stop = J * w0 / T_b                       # 0.025 s
    model = bg_model(
        "BrakeSpinDown",
        [
            bg_node("n1", "In1", bg_ref("stdlib:rotation/Inertia");
                params = Dict{String,Any}("J" => string(J)),
                starts = Dict{String,Any}("w" => string(w0))),
            bg_node("n2", "F1", bg_ref("stdlib:rotation/FixedShaft")),
            bg_node("n3", "BR1", bg_ref("stdlib:rotation/Brake");
                params = Dict{String,Any}("mu_s" => string(mu), "mu_c" => string(mu),
                    "r_eff" => string(r_eff), "n_faces" => string(n_faces),
                    "w_eps" => "1.0e-3")),
            bg_node("n4", "FN", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => string(f_n))),
        ],
        [
            bg_conn("c1", "wire", "n1", "a", "n3", "a"),
            bg_conn("c2", "wire", "n1", "b", "n2", "a"),
            bg_conn("c3", "signal", "n4", "y", "n3", "f_n"),
        ];
        t_end = 0.04, points = 401,
    )
    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 2
    for t in (0.0, 0.005, 0.01, 0.02, 0.024)
        @test isapprox(bg_value(columns, "In1/w", t), w0 - T_b * t / J; rtol = 1e-6)
        @test isapprox(bg_value(columns, "In1/phi", t), w0 * t - T_b * t^2 / (2J); rtol = 1e-6)
        @test isapprox(bg_value(columns, "BR1/T", t), T_b; rtol = 1e-6)
    end
    # Stopped: the speed stays at zero to the creep of the tanh smoothing, and the angle
    # stays at the stopping angle.
    phi_stop = w0 * t_stop - T_b * t_stop^2 / (2J)
    for t in (0.03, 0.035, 0.04)
        @test abs(bg_value(columns, "In1/w", t)) < 1e-3
        @test isapprox(bg_value(columns, "In1/phi", t), phi_stop; atol = 1e-4)
    end
    # Energy: the kinetic energy lost is what the brake dissipated (trapezoidal integral of
    # its power on the 0.1 ms grid), and the dissipation is never negative.
    times = columns["time"]
    power = bg_all(columns, "BR1/a.P")
    @test all(p -> p >= -1e-9, power)
    keep = times .<= 0.02
    tt = times[keep]
    pp = power[keep]
    dissipated = sum(0.5 * (pp[i] + pp[i - 1]) * (tt[i] - tt[i - 1]) for i in 2:length(tt))
    w_end = bg_value(columns, "In1/w", 0.02)
    @test isapprox(dissipated, 0.5 * J * (w0^2 - w_end^2); rtol = 1e-6)
end
