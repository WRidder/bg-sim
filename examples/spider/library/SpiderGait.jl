@block SpiderGait begin
    # The Bigfoot-style outer loop of the T8X: a gait clock, eight leg phases, a foot
    # trajectory and the body height/attitude correction. The output of leg i is the foot
    # point in the body frame, which the leg IK turns into three joint commands.
    #
    # Gait: an alternating tetrapod. Legs in group A (offsets 0) swing together and group B
    # (offsets 0.5) half a cycle later. The phase of leg i is `s = frac(t/T + off - phi0)`.
    #   stance, s < duty:  the foot moves from +A to -A at the constant speed 2A/(duty T).
    #                      Its height offset `z_unload (2 s/duty - 1)^8` is zero through the
    #                      middle of the stance and rises to `z_unload` at touchdown and
    #                      liftoff, so the foot takes its load gradually in the first part of
    #                      the stance and gives it up in the last part, while the other group is
    #                      also down (the double-support phases), instead of being pushed into
    #                      the floor at touchdown or snatched off it at liftoff;
    #   swing,  s >= duty: u = (s - duty)/(1 - duty); the foot returns from -A to +A on a cubic
    #                      Hermite curve whose end slopes equal the stance slope, and its height
    #                      is `z_unload + lift 16 u^2 (1-u)^2 + m u (1-u)` with m the stance
    #                      ramp's slope, so position and velocity are continuous at liftoff and
    #                      touchdown in all three directions.
    # `duty` is the stance fraction of the command. The stride is `A = v duty T / 2` with
    # `v = (vx - wz y, vy + wz x)` at the nominal foot point, so the stance foot moves at
    # exactly `-v` relative to the body and a foot that does not slip carries the body at `v`.
    # The stance/swing switch is a steep smooth blend, not an `ifelse`: the two branches agree
    # in value and slope at the switch, so the blend changes nothing measurable, and the gait
    # creates no events. (Eight `ifelse` switches, four of them on the same root, made the
    # event handling chatter at a touchdown in some runs: W206.) `phi0` delays the whole clock
    # by a fixed fraction of a cycle, which puts the switch instants between output samples.
    #
    # Body loop: the nominal foot height is `-h_stand` in the body frame. A body that has
    # sunk raises the target (negative `dz`, off by default: `k_h = 0`). The attitude
    # correction moves each foot target by `k_att (roll_f y - pitch_f x)`: a body rolled left
    # side up (roll > 0) raises the left foot targets, which lowers the left side. `roll_f`
    # and `pitch_f` are the body attitude through a first-order filter `tau_att`, so the
    # loop corrects slow tilts (an off-centre load, the four-foot phase) and stays out of the
    # 17 Hz roll mode of the servo legs.
    @inputs begin
        g::Vec{7}, [description = "Body pose (qw qx qy qz x y z)"]
        V::Vec{6}, [description = "Body twist [w; v] in the body frame"]
        vx_cmd::Real, [unit = "m/s", description = "Forward body velocity command"]
        vy_cmd::Real, [unit = "m/s", description = "Left body velocity command"]
        wz_cmd::Real, [unit = "rad/s", description = "Yaw-rate command"]
    end
    @parameters begin
        T_gait::Real = 0.8, [unit = "s", min = 1.0e-3, description = "Gait cycle time"]
        duty::Real = 0.7, [unit = "1", min = 0.5, max = 0.95, description = "Stance fraction of the foot command"]
        lift::Real = 0.035, [unit = "m", min = 0, description = "Swing apex height of the foot command"]
        h_stand::Real = 0.110, [unit = "m", min = 1.0e-3, description = "Commanded body height above the feet"]
        nx::Vec{8} = [0.203064, 0.091619, -0.091619, -0.203064,
                        0.203064, 0.091619, -0.091619, -0.203064],
            [unit = "m", description = "Nominal foot x in the body frame, legs 1..8"]
        ny::Vec{8} = [0.123772, 0.185009, 0.185009, 0.123772,
                        -0.123772, -0.185009, -0.185009, -0.123772],
            [unit = "m", description = "Nominal foot y in the body frame, legs 1..8"]
        off::Vec{8} = [0.0, 0.5, 0.0, 0.5, 0.5, 0.0, 0.5, 0.0],
            [unit = "1", description = "Phase offset of each leg (alternating tetrapod)"]
        phi0::Real = 0.0123, [unit = "1", description = "Clock delay in cycles (puts the switch instants between output samples)"]
        w_sw::Real = 1.0e-3, [unit = "1", min = 1.0e-9, description = "Width of the stance/swing blend (in cos of the phase angle, about 0.2 ms)"]
        z_unload::Real = 0.0, [unit = "m", min = 0, description = "Foot height at touchdown and liftoff above the stance height (load hand-over)"]
        k_h::Real = 0.0, [unit = "1", min = 0, description = "Body-height proportional gain (0: no height loop)"]
        kd_h::Real = 0.0, [unit = "s", min = 0, description = "Body-height vertical-rate damping"]
        k_att::Real = 1.0, [unit = "1", min = 0, description = "Roll/pitch foot correction gain"]
        tau_att::Real = 0.1, [unit = "s", min = 1.0e-4, description = "Attitude filter time constant"]
        dz_max::Real = 0.020, [unit = "m", min = 0, description = "Height correction saturation"]
        ramp_t::Real = 0.8, [unit = "s", min = 1.0e-3, description = "Command ramp-in time"]
    end
    @outputs begin
        foot1::Vec{3}, [unit = "m"]
        foot2::Vec{3}, [unit = "m"]
        foot3::Vec{3}, [unit = "m"]
        foot4::Vec{3}, [unit = "m"]
        foot5::Vec{3}, [unit = "m"]
        foot6::Vec{3}, [unit = "m"]
        foot7::Vec{3}, [unit = "m"]
        foot8::Vec{3}, [unit = "m"]
        phase::Vec{8}, [unit = "1", description = "Gait phase of each leg, 0..1 (stance below duty)"]
        stance::Vec{8}, [unit = "1", description = "1 while the foot command is on the ground"]
        lift_cmd::Vec{8}, [unit = "m", description = "Height of each foot command above the stance height"]
        roll::Real, [unit = "rad", description = "Body roll from the pose"]
        pitch::Real, [unit = "rad", description = "Body pitch from the pose"]
        yaw::Real, [unit = "rad", description = "Body yaw from the pose"]
        height::Real, [unit = "m", description = "Body origin height"]
        vx_body::Real, [unit = "m/s", description = "Body x velocity in the world"]
        vy_body::Real, [unit = "m/s", description = "Body y velocity in the world"]
        dz::Real, [unit = "m", description = "Common foot-height correction"]
        ramp::Real, [unit = "1", description = "Command ramp factor"]
    end
    @variables begin
        sb::Real = 1.0, [unit = "1"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1"]
        tx::Vec{8} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [unit = "m"]
        ty::Vec{8} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [unit = "m"]
        tz::Vec{8} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [unit = "m"]
        u::Vec{8} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [unit = "1"]
        ps::Vec{8} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [unit = "1"]
        pw::Vec{8} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [unit = "1"]
        xs::Vec{8} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [unit = "1"]
        xw::Vec{8} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [unit = "1"]
        xn::Vec{8} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [unit = "1"]
        zn::Vec{8} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [unit = "m"]
        c::Vec{8} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [unit = "1"]
        vz::Real = 0.0, [unit = "m/s"]
        att::Vec{8} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [unit = "m"]
        roll_f::Real = 0.0, [unit = "rad", state = :prefer]
        pitch_f::Real = 0.0, [unit = "rad", state = :prefer]
    end
    @equations begin
        sb ~ g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4]
        R[1, 1] ~ (g[1] * g[1] + g[2] * g[2] - g[3] * g[3] - g[4] * g[4]) / sb
        R[1, 2] ~ 2.0 * (g[2] * g[3] - g[1] * g[4]) / sb
        R[1, 3] ~ 2.0 * (g[2] * g[4] + g[1] * g[3]) / sb
        R[2, 1] ~ 2.0 * (g[2] * g[3] + g[1] * g[4]) / sb
        R[2, 2] ~ (g[1] * g[1] - g[2] * g[2] + g[3] * g[3] - g[4] * g[4]) / sb
        R[2, 3] ~ 2.0 * (g[3] * g[4] - g[1] * g[2]) / sb
        R[3, 1] ~ 2.0 * (g[2] * g[4] - g[1] * g[3]) / sb
        R[3, 2] ~ 2.0 * (g[3] * g[4] + g[1] * g[2]) / sb
        R[3, 3] ~ (g[1] * g[1] - g[2] * g[2] - g[3] * g[3] + g[4] * g[4]) / sb
        roll ~ atan(2.0 * (g[1] * g[2] + g[3] * g[4]), 1.0 - 2.0 * (g[2] * g[2] + g[3] * g[3]))
        pitch ~ asin(clamp(2.0 * (g[1] * g[3] - g[4] * g[2]), -1.0, 1.0))
        yaw ~ atan(2.0 * (g[1] * g[4] + g[2] * g[3]), 1.0 - 2.0 * (g[3] * g[3] + g[4] * g[4]))
        height ~ g[7]
        vx_body ~ R[1, 1] * V[4] + R[1, 2] * V[5] + R[1, 3] * V[6]
        vy_body ~ R[2, 1] * V[4] + R[2, 2] * V[5] + R[2, 3] * V[6]
        vz ~ R[3, 1] * V[4] + R[3, 2] * V[5] + R[3, 3] * V[6]
        ramp ~ 1.0 - exp(-t / ramp_t)
        dz ~ clamp(k_h * (height - h_stand) - kd_h * vz, -dz_max, dz_max)
        ddt(roll_f) ~ (roll - roll_f) / tau_att
        ddt(pitch_f) ~ (pitch - pitch_f) / tau_att
        for i in 1:8
            c[i] ~ t / T_gait + off[i] - phi0
            # The phase is unwrapped by atan2, with its cut placed where the branch that uses
            # it is not active: `ps` (stance) is continuous through the stance and cuts at
            # mid-swing, `pw` (swing) is continuous through the swing and cuts at mid-stance.
            # The stance/swing switch is a smooth periodic function, zero at liftoff and at
            # touchdown, so there is no floor/mod wrap event, and both branches agree (value
            # and slope) at the switch. The tanh blend is 0.2 ms wide (where the branches
            # differ by less than 1e-7 m) and reaches 0 and 1 to machine precision within 3 ms
            # of the switch, long before either atan2 cut (0.12 s away).
            ps[i] ~ 0.5 * duty + atan(sin(2.0 * pi * (c[i] - 0.5 * duty)),
                                      cos(2.0 * pi * (c[i] - 0.5 * duty))) / (2.0 * pi)
            pw[i] ~ 0.5 * (1.0 + duty) + atan(sin(2.0 * pi * (c[i] - 0.5 * (1.0 + duty))),
                                              cos(2.0 * pi * (c[i] - 0.5 * (1.0 + duty)))) / (2.0 * pi)
            phase[i] ~ 0.5 + atan(-sin(2.0 * pi * c[i]), -cos(2.0 * pi * c[i])) / (2.0 * pi)
            stance[i] ~ 0.5 * (1.0 + tanh((cos(2.0 * pi * (c[i] - 0.5 * duty)) - cos(pi * duty)) / w_sw))
            # swing coordinate (0 at liftoff, 1 at touchdown)
            u[i] ~ (pw[i] - duty) / (1.0 - duty)
            # stance: +1 -> -1 at constant speed
            xs[i] ~ 1.0 - 2.0 * ps[i] / duty
            # swing: cubic Hermite -1 -> +1 with end slopes m = -2 (1 - duty)/duty
            xw[i] ~ -(2.0 * u[i]^3 - 3.0 * u[i]^2 + 1.0) + (-2.0 * u[i]^3 + 3.0 * u[i]^2) -
                    2.0 * (1.0 - duty) / duty * ((u[i]^3 - 2.0 * u[i]^2 + u[i]) + (u[i]^3 - u[i]^2))
            xn[i] ~ stance[i] * xs[i] + (1.0 - stance[i]) * xw[i]
            # height above the stance height: the load hand-over ramp in stance, the lift in
            # swing (16 z_unload (1 - duty)/duty is the ramp's slope per unit u at either end)
            zn[i] ~ stance[i] * z_unload * (2.0 * ps[i] / duty - 1.0)^8 +
                    (1.0 - stance[i]) * (z_unload + lift * 16.0 * u[i]^2 * (1.0 - u[i])^2 +
                                         16.0 * z_unload * (1.0 - duty) / duty * u[i] * (1.0 - u[i]))
            att[i] ~ k_att * (roll_f * ny[i] - pitch_f * nx[i])
            tx[i] ~ nx[i] + ramp * (vx_cmd - wz_cmd * ny[i]) * duty * T_gait * 0.5 * xn[i]
            ty[i] ~ ny[i] + ramp * (vy_cmd + wz_cmd * nx[i]) * duty * T_gait * 0.5 * xn[i]
            lift_cmd[i] ~ ramp * zn[i]
            tz[i] ~ -h_stand + dz + att[i] + lift_cmd[i]
        end
        foot1[1] ~ tx[1]
        foot1[2] ~ ty[1]
        foot1[3] ~ tz[1]
        foot2[1] ~ tx[2]
        foot2[2] ~ ty[2]
        foot2[3] ~ tz[2]
        foot3[1] ~ tx[3]
        foot3[2] ~ ty[3]
        foot3[3] ~ tz[3]
        foot4[1] ~ tx[4]
        foot4[2] ~ ty[4]
        foot4[3] ~ tz[4]
        foot5[1] ~ tx[5]
        foot5[2] ~ ty[5]
        foot5[3] ~ tz[5]
        foot6[1] ~ tx[6]
        foot6[2] ~ ty[6]
        foot6[3] ~ tz[6]
        foot7[1] ~ tx[7]
        foot7[2] ~ ty[7]
        foot7[3] ~ tz[7]
        foot8[1] ~ tx[8]
        foot8[2] ~ ty[8]
        foot8[3] ~ tz[8]
    end
end
