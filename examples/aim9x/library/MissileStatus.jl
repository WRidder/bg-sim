@block MissileStatus begin
    # Telemetry, the proximity fuze and the closest-approach record (it adds no plant physics).
    #
    #   min_range   the smallest slant range reached so far, through a 5 ms lag
    #   fuze       1 inside `fuze_radius` while closing: the continuous-rod warhead fires
    #   hit        1 inside `kill_radius`: the fragments reach the target
    #   t_go        range / closing speed
    #
    # The run stops at the fuze event (`StopSimulation` in the model), so the final value of
    # `min_range` is the miss distance and `t_go` is the time to go at firing.
    @inputs begin
        g::Vec{7}, [description = "Missile pose"]
        V::Vec{6}, [description = "Missile twist"]
        alpha_deg::Real
        beta_deg::Real
        qbar::Real, [unit = "Pa"]
        mach::Real
        vt::Real, [unit = "m/s"]
        n_z::Real
        n_y::Real
        m::Real, [unit = "kg"]
        range::Real, [unit = "m"]
        range_rate::Real, [unit = "m/s"]
        lock::Real
    end
    @parameters begin
        fuze_radius::Real = 5.0, [unit = "m", min = 0, description = "Proximity-fuze radius"]
        kill_radius::Real = 8.0, [unit = "m", min = 0, description = "Warhead lethal radius"]
        tau_min::Real = 0.005, [unit = "s", min = 1.0e-6, description = "Closest-approach track lag"]
    end
    @variables begin
        rmin::Real = 2100.0, [unit = "m", state = :prefer, description = "Smallest range so far"]
        s::Real = 1.0, [description = "Squared quaternion norm"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [description = "Body-to-world rotation"]
        vw::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s", description = "World velocity"]
    end
    @outputs begin
        x::Real, [unit = "m"]
        y::Real, [unit = "m"]
        z::Real, [unit = "m"]
        qw::Real
        qx::Real
        qy::Real
        qz::Real
        phi_deg::Real
        theta_deg::Real
        psi_deg::Real
        gamma_deg::Real
        min_range::Real, [unit = "m"]
        fuze::Real
        hit::Real
        t_go::Real, [unit = "s"]
        closing::Real, [unit = "m/s"]
        alpha_deg_out::Real
        beta_deg_out::Real
        qbar_out::Real, [unit = "Pa"]
        mach_out::Real
        vt_out::Real, [unit = "m/s"]
        n_z_out::Real
        n_y_out::Real
        mass::Real, [unit = "kg"]
        lock_out::Real
    end
    @equations begin
        s ~ g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4]
        R[1, 1] ~ (g[1] * g[1] + g[2] * g[2] - g[3] * g[3] - g[4] * g[4]) / s
        R[1, 2] ~ 2 * (g[2] * g[3] - g[1] * g[4]) / s
        R[1, 3] ~ 2 * (g[2] * g[4] + g[1] * g[3]) / s
        R[2, 1] ~ 2 * (g[2] * g[3] + g[1] * g[4]) / s
        R[2, 2] ~ (g[1] * g[1] - g[2] * g[2] + g[3] * g[3] - g[4] * g[4]) / s
        R[2, 3] ~ 2 * (g[3] * g[4] - g[1] * g[2]) / s
        R[3, 1] ~ 2 * (g[2] * g[4] - g[1] * g[3]) / s
        R[3, 2] ~ 2 * (g[3] * g[4] + g[1] * g[2]) / s
        R[3, 3] ~ (g[1] * g[1] - g[2] * g[2] - g[3] * g[3] + g[4] * g[4]) / s
        for k in 1:3
            vw[k] ~ R[k, 1] * V[4] + R[k, 2] * V[5] + R[k, 3] * V[6]
        end
        ddt(rmin) ~ clamp((range - rmin) / tau_min, -5000.0, 0.0)
        x ~ g[5]
        y ~ g[6]
        z ~ g[7]
        qw ~ g[1]
        qx ~ g[2]
        qy ~ g[3]
        qz ~ g[4]
        phi_deg ~ atan(R[3, 2], R[3, 3]) * 57.29577951308232
        theta_deg ~ atan(-R[3, 1], hypot(R[3, 2], R[3, 3])) * 57.29577951308232
        psi_deg ~ atan(R[2, 1], R[1, 1]) * 57.29577951308232
        gamma_deg ~ asin(clamp(vw[3] / sqrt(vw[1] * vw[1] + vw[2] * vw[2] + vw[3] * vw[3] + 1.0), -1.0, 1.0)) * 57.29577951308232
        min_range ~ rmin
        closing ~ range_rate
        fuze ~ ifelse((range < fuze_radius) && (range_rate > 0.0), 1.0, 0.0)
        hit ~ ifelse(range < kill_radius, 1.0, 0.0)
        t_go ~ range / max(range_rate, 1.0)
        alpha_deg_out ~ alpha_deg
        beta_deg_out ~ beta_deg
        qbar_out ~ qbar
        mach_out ~ mach
        vt_out ~ vt
        n_z_out ~ n_z
        n_y_out ~ n_y
        mass ~ m
        lock_out ~ lock
    end
end
