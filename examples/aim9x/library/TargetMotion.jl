@block TargetMotion begin
    # A manoeuvring target aircraft, as a scenario source (it is not part of the missile plant).
    # The target flies at a constant true airspeed and flight-path angle and starts a level turn
    # at `t_turn`, ramped in over `turn_ramp`; the position is integrated from its velocity.
    #
    #   pose       (qw, qx, qy, qz, x, y, z), heading about world z
    #   vw         inertial velocity (north, west, up)
    #   ir         infrared intensity: brighter from the rear aspect
    @inputs pm::Vec{3}, [unit = "m", description = "Missile position (for the aspect angle)"]
    @parameters begin
        v0::Real = 220.0, [unit = "m/s", min = 0, description = "True airspeed"]
        gamma0::Real = 0.0, [unit = "deg", description = "Flight-path angle"]
        turn_rate::Real = 0.0698, [unit = "rad/s", description = "Turn rate after t_turn"]
        t_turn::Real = 4.0, [unit = "s", description = "Start of the turn"]
        turn_ramp::Real = 0.2, [unit = "s", min = 1.0e-6, description = "Turn-in ramp"]
        ir0::Real = 1.0e6, [unit = "W", min = 0, description = "Nose-aspect infrared intensity"]
        rear_factor::Real = 0.65, [min = 0, description = "Rear-aspect intensity increase"]
    end
    @variables begin
        ps::Vec{3} = [5500.0, 2500.0, 6000.0], [unit = "m", state = :prefer, description = "Target position"]
        psis::Real = 1.5707963, [unit = "rad", state = :prefer, description = "Target heading"]
        vw::Vec{3} = [0.0, 220.0, 0.0], [unit = "m/s", description = "Target velocity"]
        dhat::Vec{3} = [1.0, 0.0, 0.0], [description = "Target-to-missile unit vector"]
        vhat::Vec{3} = [0.0, 1.0, 0.0], [description = "Target velocity unit vector"]
        rear::Real = 0.0, [description = "0 nose aspect, 1 rear aspect"]
        range2::Real = 1.0, [unit = "m^2"]
    end
    @outputs begin
        pose::Vec{7}
        vw_out::Vec{3}, [unit = "m/s"]
        ir::Real, [unit = "W"]
        psi::Real, [unit = "rad"]
        psi_deg::Real
        x::Real, [unit = "m"]
        y::Real, [unit = "m"]
        z::Real, [unit = "m"]
    end
    @equations begin
        ddt(psis) ~ turn_rate * clamp((t - t_turn) / turn_ramp, 0.0, 1.0)
        vw[1] ~ v0 * cos(gamma0 * pi / 180) * cos(psis)
        vw[2] ~ v0 * cos(gamma0 * pi / 180) * sin(psis)
        vw[3] ~ v0 * sin(gamma0 * pi / 180)
        ddt(ps[1]) ~ vw[1]
        ddt(ps[2]) ~ vw[2]
        ddt(ps[3]) ~ vw[3]
        range2 ~ (pm[1] - ps[1]) * (pm[1] - ps[1]) + (pm[2] - ps[2]) * (pm[2] - ps[2]) +
                 (pm[3] - ps[3]) * (pm[3] - ps[3])
        dhat[1] ~ (pm[1] - ps[1]) / sqrt(max(range2, 1.0))
        dhat[2] ~ (pm[2] - ps[2]) / sqrt(max(range2, 1.0))
        dhat[3] ~ (pm[3] - ps[3]) / sqrt(max(range2, 1.0))
        vhat[1] ~ vw[1] / max(v0, 1.0)
        vhat[2] ~ vw[2] / max(v0, 1.0)
        vhat[3] ~ vw[3] / max(v0, 1.0)
        rear ~ 0.5 * (1.0 - (dhat[1] * vhat[1] + dhat[2] * vhat[2] + dhat[3] * vhat[3]))
        ir ~ ir0 * (1.0 + rear_factor * rear)
        pose[1] ~ cos(psis / 2)
        pose[2] ~ 0.0
        pose[3] ~ 0.0
        pose[4] ~ sin(psis / 2)
        pose[5] ~ ps[1]
        pose[6] ~ ps[2]
        pose[7] ~ ps[3]
        vw_out ~ vw
        psi ~ psis
        psi_deg ~ psis * 180.0 / pi
        x ~ ps[1]
        y ~ ps[2]
        z ~ ps[3]
    end
end
