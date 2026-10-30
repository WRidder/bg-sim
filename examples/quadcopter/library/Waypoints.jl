@block Waypoints begin
    # Mission set-point generator, 50 Hz. The set-point is the start pose plus a sum of minimum-jerk
    # moves, one per table entry k: at `ts[k]` the pose moves by (dx, dy, dz, dpsi)[k] over `dur[k]`
    # seconds with the quintic profile s(u) = 10u^3 - 15u^4 + 6u^5 (zero velocity and acceleration
    # at both ends). Moves may overlap. The velocity, acceleration (and yaw rate) feedforward is the exact
    # derivative. `armed` is 1 between `t_arm` and `t_disarm` (motors off on the ground outside it).
    # The time is the stdlib `Time` source, sampled at the tick.
    @constants W::Int = 8
    @inputs tm::Real
    @outputs begin
        p_sp::Vec{3} = [0.0, 0.0, 0.0]
        v_sp::Vec{3} = [0.0, 0.0, 0.0]
        a_sp::Vec{3} = [0.0, 0.0, 0.0]
        psi_sp::Real = 0.0
        psi_rate::Real = 0.0
        armed::Real = 0.0
    end
    @parameters begin
        p0::Vec{3} = [0.0, 0.0, 0.0], [unit = "m", description = "Start position"]
        ts::Vec{W} = [1.0, 5.0, 8.0, 11.0, 14.0, 99.0, 99.0, 99.0], [unit = "s", description = "Start time of each move"]
        dur::Vec{W} = [3.0, 2.5, 2.5, 3.0, 3.0, 1.0, 1.0, 1.0], [unit = "s", min = 0.01, description = "Duration of each move"]
        dx::Vec{W} = [0.0, 2.0, 0.0, -2.0, 0.0, 0.0, 0.0, 0.0], [unit = "m", description = "x displacement of each move"]
        dy::Vec{W} = [0.0, 0.0, 2.0, -2.0, 0.0, 0.0, 0.0, 0.0], [unit = "m", description = "y displacement of each move"]
        dz::Vec{W} = [1.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0], [unit = "m", description = "z displacement of each move"]
        dpsi::Vec{W} = [0.0, 0.0, 1.5707963267948966, -1.5707963267948966, 0.0, 0.0, 0.0, 0.0], [unit = "rad", description = "Yaw change of each move"]
        t_arm::Real = 0.5, [unit = "s", description = "Arming time"]
        t_disarm::Real = 99.0, [unit = "s", description = "Disarming time"]
    end
    @discrete Ts = 20e-3 begin
        p = p0
        v = [0.0, 0.0, 0.0]
        a = [0.0, 0.0, 0.0]
        psi = 0.0
        psr = 0.0
        for k in 1:W
            s = clamp((tm - ts[k]) / dur[k], 0.0, 1.0)
            sg = s * s * s * (10.0 - 15.0 * s + 6.0 * s * s)
            ds = s * s * (30.0 - 60.0 * s + 30.0 * s * s) / dur[k]
            dd = s * (60.0 - 180.0 * s + 120.0 * s * s) / (dur[k] * dur[k]) * ifelse(s > 0.0 && s < 1.0, 1.0, 0.0)
            p = p + [dx[k], dy[k], dz[k]] * sg
            a = a + [dx[k], dy[k], dz[k]] * dd
            v = v + [dx[k], dy[k], dz[k]] * ds
            psi = psi + dpsi[k] * sg
            psr = psr + dpsi[k] * ds
        end
        p_sp = p
        v_sp = v
        a_sp = a
        psi_sp = psi
        psi_rate = psr
        armed = ifelse(tm >= t_arm && tm < t_disarm, 1.0, 0.0)
    end
end
