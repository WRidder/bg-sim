@block Waypoints begin
    # Mission set-point generator and flight-mode logic, 50 Hz: sums of smooth moves with exact
    # velocity, acceleration and jerk feed-forward. Each move is the 7th-order smooth step
    # s^4 (35 - 84 s + 70 s^2 - 20 s^3), s = (t - ts)/dur: velocity, acceleration and jerk are
    # zero at both ends, so the tilt-rate feed-forward of the position loop (j/g) starts and ends
    # at zero. This vehicle has no yaw actuator, so the mission never asks for a heading.
    #
    # Landing (PX4's land mode): from `t_land` the height set-point descends at `v_land`, the
    # descent speed itself ramped in over `t_ramp` with the same smooth step, until touchdown.
    # The vehicle meets the ground at a steady descent speed, so the thrust is close to the
    # weight and nothing has to brake against the ground. Touchdown: after `t_land` the block
    # watches the landing-gear force `fc`, the peak hold of `AeroWrench`: the impact lasts about
    # 20 ms and falls between two 50 Hz ticks, but the peak hold keeps it, so the first tick
    # after the impact latches the touchdown time `t_td` (at most one tick late). From then on
    # the set-point is frozen and `contact` is 1: the position controller holds the thrust it
    # had before the touchdown instead of reacting to the rebound of the feet, and the rate
    # loop only damps (`RateCtrl`): the feet keep the body level, and an attitude or integral
    # term would lean on its lightly loaded feet. The drive has already braked the rotor to its
    # touchdown cap (`RotorEsc`). From `t_td + t_hold`, after the short hop, the thrust fraction
    # `thr` falls from `thr0` (the drive's cap, k_td^2) to 0 over `t_unload` along the smooth
    # step: the rotor slows gently at first, while the feet carry little weight, and faster as
    # they take it, so their friction always holds the motor reaction. Then the vehicle is `landed` (the flight controller is
    # off) and the motor is switched off `t_spin` later. `t_arm`/`t_disarm` switch everything
    # on and off.
    @constants W::Int = 8
    @inputs begin
        tm::Real
        fc::Real, [unit = "N", description = "Total landing-gear normal force, peak hold"]
    end
    @outputs begin
        p_sp::Vec{3} = [0.0, 0.0, 0.0]
        v_sp::Vec{3} = [0.0, 0.0, 0.0]
        a_sp::Vec{3} = [0.0, 0.0, 0.0]
        j_sp::Vec{3} = [0.0, 0.0, 0.0]
        armed::Real = 0.0
        motor::Real = 0.0
        landed::Real = 0.0
        contact::Real = 0.0, [description = "1 from the touchdown latch: thrust held, vertical loop off"]
        thr::Real = 1.0, [description = "Fraction of the touchdown thrust kept on the ground"]
        t_td::Real = 99.0, [unit = "s", description = "Touchdown time (99 until it happens)"]
    end
    @parameters begin
        p0::Vec{3} = [0.0, 0.0, 0.0], [unit = "m", description = "Start position"]
        ts::Vec{W} = [1.0, 5.0, 8.0, 11.0, 14.0, 99.0, 99.0, 99.0], [unit = "s", description = "Start time of each move"]
        dur::Vec{W} = [3.0, 2.5, 2.5, 3.0, 3.0, 1.0, 1.0, 1.0], [unit = "s", min = 0.01, description = "Duration of each move"]
        dx::Vec{W} = [0.0, 2.0, 0.0, -2.0, 0.0, 0.0, 0.0, 0.0], [unit = "m", description = "x displacement of each move"]
        dy::Vec{W} = [0.0, 0.0, 2.0, -2.0, 0.0, 0.0, 0.0, 0.0], [unit = "m", description = "y displacement of each move"]
        dz::Vec{W} = [1.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0], [unit = "m", description = "z displacement of each move"]
        t_arm::Real = 0.0, [unit = "s", description = "Arming time"]
        t_disarm::Real = 99.0, [unit = "s", description = "Disarming time"]
        t_land::Real = 99.0, [unit = "s", description = "Start of the landing descent; touchdown detection is active after it"]
        v_land::Real = 0.25, [unit = "m/s", min = 0, description = "Landing descent speed"]
        t_ramp::Real = 1.0, [unit = "s", min = 0.01, description = "Time to ramp in the landing descent speed"]
        f_touch::Real = 2.0, [unit = "N", description = "Landing-gear force that counts as touchdown"]
        t_hold::Real = 0.2, [unit = "s", min = 0, description = "Thrust held after the touchdown latch (longer than the hop)"]
        t_unload::Real = 1.0, [unit = "s", min = 0.01, description = "Time over which the thrust then comes off"]
        thr0::Real = 1.0, [min = 0, max = 1, description = "Thrust fraction at the start of the unload (the drive's touchdown cap squared)"]
        t_spin::Real = 2.0, [unit = "s", description = "Motor run-down time after the flight controller is off"]
    end
    @variables lat::Real = 0.0, [description = "Touchdown latch"]
    @discrete Ts = 20e-3 begin
        p = p0
        v = [0.0, 0.0, 0.0]
        a = [0.0, 0.0, 0.0]
        j = [0.0, 0.0, 0.0]
        for k in 1:W
            s = clamp((tm - ts[k]) / dur[k], 0.0, 1.0)
            u = 1.0 - s
            sg = s * s * s * s * (35.0 - 84.0 * s + 70.0 * s * s - 20.0 * s * s * s)
            ds = 140.0 * s * s * s * u * u * u / dur[k]
            dd = 420.0 * s * s * u * u * (1.0 - 2.0 * s) / (dur[k] * dur[k])
            d3 = 840.0 * s * u * (5.0 * s * s - 5.0 * s + 1.0) / (dur[k] * dur[k] * dur[k])
            p = p + [dx[k], dy[k], dz[k]] * sg
            v = v + [dx[k], dy[k], dz[k]] * ds
            a = a + [dx[k], dy[k], dz[k]] * dd
            j = j + [dx[k], dy[k], dz[k]] * d3
        end
        # landing descent: speed v_land S(s), S the smooth step, s = (t - t_land)/t_ramp; the
        # position is its integral, 7 s^5 - 14 s^6 + 10 s^7 - 5/2 s^8 (= 1/2 at s = 1)
        # (frozen at the touchdown latch)
        if lat < 0.5 && tm >= t_land && fc > f_touch
            lat = 1.0
            t_td = tm
        end
        done = ifelse(tm >= t_td, 1.0, 0.0)
        sl = max(min(tm, t_td) - t_land, 0.0) / t_ramp
        sc = min(sl, 1.0)
        uc = 1.0 - sc
        il = sc * sc * sc * sc * sc * (7.0 - 14.0 * sc + 10.0 * sc * sc - 2.5 * sc * sc * sc) + max(sl - 1.0, 0.0)
        gl = (1.0 - done) * sc * sc * sc * sc * (35.0 - 84.0 * sc + 70.0 * sc * sc - 20.0 * sc * sc * sc)
        hl = (1.0 - done) * 140.0 * sc * sc * sc * uc * uc * uc
        kl = (1.0 - done) * 420.0 * sc * sc * uc * uc * (1.0 - 2.0 * sc)
        p = p - [0.0, 0.0, v_land * t_ramp * il]
        v = v - [0.0, 0.0, v_land * gl]
        a = a - [0.0, 0.0, v_land * hl / t_ramp]
        j = j - [0.0, 0.0, v_land * kl / (t_ramp * t_ramp)]
        p_sp = p
        v_sp = v
        a_sp = a
        j_sp = j
        on = ifelse(tm >= t_arm && tm < t_disarm, 1.0, 0.0)
        contact = done
        su = clamp((tm - t_td - t_hold) / t_unload, 0.0, 1.0)
        thr = ifelse(tm >= t_td + t_hold, thr0, 1.0) * (1.0 - su * su * su * su * (35.0 - 84.0 * su + 70.0 * su * su - 20.0 * su * su * su))
        landed = ifelse(tm >= t_td + t_hold + t_unload, 1.0, 0.0)
        armed = on * (1.0 - landed)
        motor = on * ifelse(tm >= t_td + t_hold + t_unload + t_spin, 0.0, 1.0)
    end
end
