@block DescentGuidance begin
    # Powered-descent guidance of the lunar module in the inertial site frame (origin at the
    # landing site, x downrange, z up, the Moon's centre at (0, 0, -R)). It asks for an
    # acceleration a_c and turns it into a thrust request and a thrust direction:
    #
    #     a_t = a_c - g(r),       T_req = m |a_t|,       u = a_t / |a_t|
    #
    # with g(r) the inverse-square gravity. Three phases, switched at fixed times:
    #
    # * braking (P63, t < t_hg) and approach (P64, t < t_p66): Apollo's quadratic guidance
    #   (Klumpp, "Apollo lunar descent guidance", Automatica 1974). The acceleration that is
    #   quadratic in time and meets a target position, velocity and acceleration at the target
    #   time T_end is commanded now:
    #
    #       a_c = a_T + 12 (r_T - r) / tgo^2 - 6 (v + v_T) / tgo,      tgo = T_end - t
    #
    #   As in Apollo the braking target lies beyond high gate (the phase ends 60 s before it),
    #   so tgo never reaches zero.
    # * landing (P66, rate of descent): the crew flies the attitude and sets the descent rate;
    #   here a velocity loop holds the commanded descent rate `rate_cmd` through the throttle
    #   (time constant tau_v) and the commanded forward speed `fwd_cmd` (and zero cross-range)
    #   through the attitude (tau_h, horizontal acceleration limited to ah_max).
    @inputs begin
        g::Vec{7}, [description = "Body pose (qw, qx, qy, qz, x, y, z) in the site frame"]
        V::Vec{6}, [description = "Body twist [w; v] in body axes"]
        m::Real, [unit = "kg", description = "Mass"]
        rate_cmd::Real, [unit = "m/s", description = "P66: commanded descent rate (positive down)"]
        fwd_cmd::Real, [unit = "m/s", description = "P66: commanded forward (downrange) speed"]
    end
    @parameters begin
        mu::Real = 4.9028e12, [unit = "m^3/s^2"]
        R::Real = 1737400.0, [unit = "m"]
        gscale::Real = 1.0, [description = "Gravity multiplier (as in CentralGravity3D)"]
        t_hg::Real = 507.0, [unit = "s", description = "High gate: switch from P63 to P64"]
        t_p66::Real = 617.0, [unit = "s", description = "Switch from P64 to P66"]
        r63::Vec{3} = [0.0, 0.0, 0.0], [unit = "m", description = "P63 target position"]
        v63::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s", description = "P63 target velocity"]
        a63::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s^2", description = "P63 target acceleration"]
        T63::Real = 567.0, [unit = "s", description = "P63 target time"]
        r64::Vec{3} = [0.0, 0.0, 0.0], [unit = "m", description = "P64 target position"]
        v64::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s", description = "P64 target velocity"]
        a64::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s^2", description = "P64 target acceleration"]
        T64::Real = 650.0, [unit = "s", description = "P64 target time"]
        tau_v::Real = 2.0, [unit = "s", min = 1.0e-3, description = "P66 descent-rate loop time constant"]
        tau_h::Real = 5.0, [unit = "s", min = 1.0e-3, description = "P66 horizontal-velocity loop time constant"]
        ah_max::Real = 0.6, [unit = "m/s^2", min = 0, description = "P66 horizontal acceleration limit"]
        tgo_min::Real = 1.0, [unit = "s", description = "Floor of the time to go (a guard: never reached)"]
    end
    @variables begin
        s2::Real, [description = "Squared quaternion norm"]
        Rm::Mat{3,3}, [description = "Rotation body to world"]
        vw::Vec{3}, [unit = "m/s", description = "Velocity, world"]
        rc::Vec{3}, [unit = "m", description = "Position from the Moon's centre"]
        r::Real, [unit = "m"]
        gw::Vec{3}, [unit = "m/s^2", description = "Gravity, world"]
        tg63::Real, [unit = "s"]
        tg64::Real, [unit = "s"]
        ac63::Vec{3}, [unit = "m/s^2"]
        ac64::Vec{3}, [unit = "m/s^2"]
        ac66::Vec{3}, [unit = "m/s^2"]
        ac::Vec{3}, [unit = "m/s^2", description = "Commanded acceleration"]
        at::Vec{3}, [unit = "m/s^2", description = "Commanded thrust acceleration"]
        atn::Real, [unit = "m/s^2"]
    end
    @outputs begin
        u::Vec{3}, [description = "Commanded thrust direction (world, unit)"]
        T_req::Real, [unit = "N", description = "Thrust request"]
        phase::Real, [description = "63, 64 or 66"]
    end
    @equations begin
        s2 ~ g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4]
        Rm[1, 1] ~ (g[1] * g[1] + g[2] * g[2] - g[3] * g[3] - g[4] * g[4]) / s2
        Rm[1, 2] ~ 2 * (g[2] * g[3] - g[1] * g[4]) / s2
        Rm[1, 3] ~ 2 * (g[2] * g[4] + g[1] * g[3]) / s2
        Rm[2, 1] ~ 2 * (g[2] * g[3] + g[1] * g[4]) / s2
        Rm[2, 2] ~ (g[1] * g[1] - g[2] * g[2] + g[3] * g[3] - g[4] * g[4]) / s2
        Rm[2, 3] ~ 2 * (g[3] * g[4] - g[1] * g[2]) / s2
        Rm[3, 1] ~ 2 * (g[2] * g[4] - g[1] * g[3]) / s2
        Rm[3, 2] ~ 2 * (g[3] * g[4] + g[1] * g[2]) / s2
        Rm[3, 3] ~ (g[1] * g[1] - g[2] * g[2] - g[3] * g[3] + g[4] * g[4]) / s2
        for k in 1:3
            vw[k] ~ Rm[k, 1] * V[4] + Rm[k, 2] * V[5] + Rm[k, 3] * V[6]
        end
        rc[1] ~ g[5]
        rc[2] ~ g[6]
        rc[3] ~ g[7] + R
        r ~ sqrt(rc[1] * rc[1] + rc[2] * rc[2] + rc[3] * rc[3])
        for k in 1:3
            gw[k] ~ -gscale * mu * rc[k] / (r * r * r)
        end
        tg63 ~ max(T63 - t, tgo_min)
        tg64 ~ max(T64 - t, tgo_min)
        for k in 1:3
            ac63[k] ~ a63[k] + 12 * (r63[k] - g[4 + k]) / (tg63 * tg63) - 6 * (vw[k] + v63[k]) / tg63
            ac64[k] ~ a64[k] + 12 * (r64[k] - g[4 + k]) / (tg64 * tg64) - 6 * (vw[k] + v64[k]) / tg64
        end
        ac66[1] ~ clamp((fwd_cmd - vw[1]) / tau_h, -ah_max, ah_max)
        ac66[2] ~ clamp(-vw[2] / tau_h, -ah_max, ah_max)
        ac66[3] ~ (-rate_cmd - vw[3]) / tau_v
        for k in 1:3
            ac[k] ~ ifelse(t < t_hg, ac63[k], ifelse(t < t_p66, ac64[k], ac66[k]))
            at[k] ~ ac[k] - gw[k]
        end
        atn ~ sqrt(at[1] * at[1] + at[2] * at[2] + at[3] * at[3])
        for k in 1:3
            u[k] ~ at[k] / atn
        end
        T_req ~ m * atn
        phase ~ ifelse(t < t_hg, 63.0, ifelse(t < t_p66, 64.0, 66.0))
    end
end
