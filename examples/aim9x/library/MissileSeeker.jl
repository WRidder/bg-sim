@block MissileSeeker begin
    # Imaging-infrared seeker of the AIM-9X, as a sensor and tracking loop (it adds no plant
    # physics). From the missile pose and twist and the target pose, velocity and intensity it
    # produces
    #
    #   los_pitch, los_yaw   inertial line-of-sight rates in body axes (rad/s), filtered:
    #                        positive pitch is a nose-down LOS rotation, positive yaw a nose-left one
    #   range, range_rate    slant range (m) and closing speed (m/s, positive closing)
    #   gimbal_p, gimbal_y   the stabilised gimbal angles (rad)
    #   off_boresight        angle between the body x axis and the target
    #   lock                 seeker_on and the target inside the field of view and bright enough
    #   ir_target            irradiance of the target (W/m^2)
    #
    # The LOS rate is *inertial*: the body-frame derivative of the LOS vector plus the body
    # rate, omega_LOS = d x (v_rel - omega x d) / |d|^2. That is what a stabilised seeker
    # measures and what proportional navigation needs. The gimbal follows the LOS through a
    # 20 ms lag and a 180 deg/s rate limit; its mechanical stop is a little wider than the
    # 90 deg off-boresight field of view.
    @inputs begin
        gm::Vec{7}, [description = "Missile pose"]
        Vm::Vec{6}, [description = "Missile twist [w; v]"]
        gt::Vec{7}, [description = "Target pose"]
        Vt::Vec{3}, [unit = "m/s", description = "Target velocity, world"]
        I_t::Real, [unit = "W", description = "Target infrared intensity"]
        seeker_on::Real, [description = "1: seeker enabled"]
    end
    @parameters begin
        fov::Real = 1.5707963, [unit = "rad", description = "Full field of view"]
        gimbal_max::Real = 1.0471976, [unit = "rad", description = "Gimbal mechanical limit"]
        tau_track::Real = 0.020, [unit = "s", min = 1.0e-6, description = "Gimbal tracking lag"]
        rate_max::Real = 3.14159, [unit = "rad/s", min = 0, description = "Gimbal rate limit"]
        tau_rate::Real = 0.030, [unit = "s", min = 1.0e-6, description = "LOS-rate filter"]
        r0::Real = 10.0, [unit = "m", min = 1.0e-6, description = "Range floor of the 1/r^2 law"]
        atten::Real = 1.0e-4, [unit = "1/m", min = 0, description = "Atmospheric attenuation"]
        ir_min::Real = 0.02, [unit = "W/m^2", min = 0, description = "Detection threshold"]
        t_lock::Real = 1.0, [unit = "s", min = 0, description = "Track initiation time after launch"]
    end
    @variables begin
        s::Real = 1.0, [description = "Squared quaternion norm"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [description = "Missile body-to-world rotation"]
        d::Vec{3} = [1.0, 0.0, 0.0], [unit = "m", description = "Missile-to-target vector, body axes"]
        r::Real = 1.0, [unit = "m"]
        dhat::Vec{3} = [1.0, 0.0, 0.0], [description = "Unit LOS, target"]
        vrel::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s", description = "Target minus missile velocity, body axes"]
        vw::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s", description = "Missile velocity, world"]
        ddot::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s", description = "Body-frame LOS derivative"]
        lom::Vec{3} = [0.0, 0.0, 0.0], [unit = "1/s", description = "Inertial LOS rate vector"]
        ir_t::Real = 0.0, [unit = "W/m^2"]
        rr::Real = 0.0, [unit = "m/s"]
        off::Real = 0.0, [unit = "rad"]
        fov_ok::Real = 1.0
        ir_ok::Real = 1.0
        gsum::Real = 1.0, [unit = "m^2"]
        gp::Real = 0.0, [unit = "rad", state = :prefer, description = "Gimbal pitch state"]
        gy::Real = 0.0, [unit = "rad", state = :prefer, description = "Gimbal yaw state"]
        lrp::Real = 0.0, [unit = "rad/s", state = :prefer, description = "Filtered LOS pitch rate"]
        lry::Real = 0.0, [unit = "rad/s", state = :prefer, description = "Filtered LOS yaw rate"]
    end
    @outputs begin
        los_pitch::Real, [unit = "rad/s"]
        los_yaw::Real, [unit = "rad/s"]
        range::Real, [unit = "m"]
        range_rate::Real, [unit = "m/s"]
        gimbal_p::Real, [unit = "rad"]
        gimbal_y::Real, [unit = "rad"]
        off_boresight::Real, [unit = "rad"]
        lock::Real
        ir_target::Real, [unit = "W/m^2"]
        snr::Real
        fov_flag::Real
        ir_flag::Real
        track_error::Real, [unit = "rad"]
    end
    @equations begin
        s ~ gm[1] * gm[1] + gm[2] * gm[2] + gm[3] * gm[3] + gm[4] * gm[4]
        R[1, 1] ~ (gm[1] * gm[1] + gm[2] * gm[2] - gm[3] * gm[3] - gm[4] * gm[4]) / s
        R[1, 2] ~ 2 * (gm[2] * gm[3] - gm[1] * gm[4]) / s
        R[1, 3] ~ 2 * (gm[2] * gm[4] + gm[1] * gm[3]) / s
        R[2, 1] ~ 2 * (gm[2] * gm[3] + gm[1] * gm[4]) / s
        R[2, 2] ~ (gm[1] * gm[1] - gm[2] * gm[2] + gm[3] * gm[3] - gm[4] * gm[4]) / s
        R[2, 3] ~ 2 * (gm[3] * gm[4] - gm[1] * gm[2]) / s
        R[3, 1] ~ 2 * (gm[2] * gm[4] - gm[1] * gm[3]) / s
        R[3, 2] ~ 2 * (gm[3] * gm[4] + gm[1] * gm[2]) / s
        R[3, 3] ~ (gm[1] * gm[1] - gm[2] * gm[2] - gm[3] * gm[3] + gm[4] * gm[4]) / s
        for k in 1:3
            d[k] ~ R[1, k] * (gt[5] - gm[5]) + R[2, k] * (gt[6] - gm[6]) + R[3, k] * (gt[7] - gm[7])
            vw[k] ~ R[k, 1] * Vm[4] + R[k, 2] * Vm[5] + R[k, 3] * Vm[6]
            vrel[k] ~ R[1, k] * (Vt[1] - vw[1]) + R[2, k] * (Vt[2] - vw[2]) + R[3, k] * (Vt[3] - vw[3])
        end
        r ~ sqrt(d[1] * d[1] + d[2] * d[2] + d[3] * d[3] + r0 * r0)
        dhat[1] ~ d[1] / r
        dhat[2] ~ d[2] / r
        dhat[3] ~ d[3] / r
        ir_t ~ I_t / (r * r) * exp(-atten * r)
        # body-frame LOS derivative: v_rel minus the rotation of the body
        ddot[1] ~ vrel[1] - (Vm[2] * d[3] - Vm[3] * d[2])
        ddot[2] ~ vrel[2] - (Vm[3] * d[1] - Vm[1] * d[3])
        ddot[3] ~ vrel[3] - (Vm[1] * d[2] - Vm[2] * d[1])
        gsum ~ max(r * r, 1.0)
        lom[1] ~ (d[2] * ddot[3] - d[3] * ddot[2]) / gsum
        lom[2] ~ (d[3] * ddot[1] - d[1] * ddot[3]) / gsum
        lom[3] ~ (d[1] * ddot[2] - d[2] * ddot[1]) / gsum
        rr ~ -(dhat[1] * vrel[1] + dhat[2] * vrel[2] + dhat[3] * vrel[3])
        off ~ acos(clamp(dhat[1], -1.0, 1.0))
        fov_ok ~ clamp((min(fov * 0.5, gimbal_max) - off) / 0.02 + 1.0, 0.0, 1.0)
        ir_ok ~ clamp((ir_t / ir_min - 1.0) * 10.0 + 1.0, 0.0, 1.0)
        ddt(gp) ~ clamp((atan(dhat[3], dhat[1]) - gp) / tau_track, -rate_max, rate_max) * fov_ok
        ddt(gy) ~ clamp((atan(dhat[2], dhat[1]) - gy) / tau_track, -rate_max, rate_max) * fov_ok
        ddt(lrp) ~ (lom[2] - lrp) / tau_rate
        ddt(lry) ~ (lom[3] - lry) / tau_rate
        los_pitch ~ lrp
        los_yaw ~ lry
        range ~ r
        range_rate ~ rr
        gimbal_p ~ gp
        gimbal_y ~ gy
        off_boresight ~ off
        lock ~ clamp(seeker_on, 0.0, 1.0) * fov_ok * ir_ok * clamp((t - t_lock) / 0.2, 0.0, 1.0)
        ir_target ~ ir_t
        snr ~ ir_t / max(ir_min, 1.0e-12)
        fov_flag ~ fov_ok
        ir_flag ~ ir_ok
        track_error ~ acos(clamp(cos(gp) * cos(gy) * dhat[1] + cos(gp) * sin(gy) * dhat[2] + sin(gp) * dhat[3], -1.0, 1.0))
    end
end
