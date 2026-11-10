@block FlightPlan begin
    # Guidance: the flight plan as a sum of smooth moves, sampled at 50 Hz. Ingenuity's flights were
    # uploaded as waypoint sequences and flown autonomously (Grip et al. 2018). At `ts[k]` the
    # set-point moves by (dx, dy, dz, dpsi)[k] over `dur[k]` seconds with the minimum-jerk profile
    # s(u) = 10u^3 - 15u^4 + 6u^5 (zero velocity and acceleration at both ends); the velocity,
    # acceleration and yaw-rate feedforward are its exact derivatives. A climb of h metres over
    # 1.875 h seconds peaks at 1 m/s, the climb and descent rate of the Mars flights (NASA 2021).
    #
    # `mode` is the flight phase: 0 on the ground (blade pitch at ground idle, loops off) before
    # `t_takeoff` and after `t_cut` (the touchdown cut once the set-point is below the ground), 1 in
    # flight. The time is the stdlib `Time` source, sampled at the tick.
    @constants W::Int = 8
    @inputs tm::Real
    @outputs begin
        p_sp::Vec{3} = [0.0, 0.0, 0.0]
        v_sp::Vec{3} = [0.0, 0.0, 0.0]
        a_sp::Vec{3} = [0.0, 0.0, 0.0]
        psi_sp::Real = 0.0
        psi_rate::Real = 0.0
        mode::Real = 0.0
        alt_sp::Real = 0.0
    end
    @parameters begin
        p0::Vec{3} = [0.0, 0.0, 0.0], [unit = "m", description = "Start position (CoM resting on the gear)"]
        ts::Vec{W} = [1.0, 99.0, 99.0, 99.0, 99.0, 99.0, 99.0, 99.0], [unit = "s", description = "Start time of each move"]
        dur::Vec{W} = [5.625, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0], [unit = "s", min = 0.01, description = "Duration of each move"]
        dx::Vec{W} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [unit = "m", description = "x displacement (east) of each move"]
        dy::Vec{W} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [unit = "m", description = "y displacement (north) of each move"]
        dz::Vec{W} = [3.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [unit = "m", description = "z displacement (up) of each move"]
        dpsi::Vec{W} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [unit = "rad", description = "Heading change of each move"]
        t_takeoff::Real = 1.0, [unit = "s", description = "Start of closed-loop flight"]
        t_cut::Real = 99.0, [unit = "s", description = "Touchdown cut: back to ground idle"]
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
        alt_sp = p[3] - p0[3]
        mode = ifelse(tm >= t_takeoff && tm < t_cut, 1.0, 0.0)
    end
end
