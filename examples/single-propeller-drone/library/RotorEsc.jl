@block RotorEsc begin
    # The moteus drive in velocity mode: a 400 Hz rotor-speed loop that produces the collective
    # motor torque. The reference is ramped with an acceleration limit (the real controller's
    # `mcout.accel_limit`), because a fast speed change kicks the body in yaw through the motor
    # reaction.
    #
    #   w_ref <- w_ref + clamp(w_cmd - w_ref, -accel_max Ts, accel_max Ts)
    #   tau_ff = kQ w_ref |w_ref| + b_m w_ref + Ja (w_ref - w_ref_old)/Ts   (drag, loss, acceleration)
    #   tau    = tau_ff + Kp (w_ref - w) + I                                 (PI, conditional integration)
    #
    # The torque limit is `tau_max - cyc_amp`: the cyclic modulation is added on top of the
    # collective torque in `CyclicDrive`, so the drive leaves headroom for it. The lower limit
    # lets the drive brake the propeller. Disarmed, the reference is zero, the integral is
    # cleared and the torque request is zero (the propeller coasts). The loop samples the
    # rotor speed, which carries the once-per-revolution ripple of the cyclic torque, so its
    # P term pushes back on that ripple. The block also samples the bus voltage for the
    # inverter duty (`v_bus_s`).
    #
    # Landing. In landing mode (`land` = 1, from the mission) the drive watches the four foot
    # loads `f` (`FootSensor`, sampled at the same 400 Hz). On the first tick with a total load
    # above `f_touch` it latches the touchdown (`td`) and sets its own speed cap, `k_td` times the
    # speed reference of that tick; the mission's ground thrust fraction `thr` then scales the
    # cap down to idle (wt = min(w_cmd, w_cap sqrt(thr))), so the unload starts exactly at the
    # cap. The latch is cleared whenever landing mode is off or the drive is disarmed.
    #
    # While latched the drive never asks the feet for more than they can hold. The fins carry
    # the rotor's drag torque in any state, so the body only feels the rotor's change of angular
    # momentum Ja dw/dt. Two loaded feet a distance s apart hold a yaw torque mu s min(N_a, N_b)
    # as a friction couple; one foot alone holds none (the body pivots about it). With the loads
    # l_i = max(f_i - f_min, 0) and the feet on a square of side d, the drive takes the best
    # pairing,
    #
    #   t_pair = k_mu max( sqrt(2) d (min(l1, l3) + min(l2, l4)),      the two diagonals
    #                      d (min(l1, l2) + min(l3, l4)),              opposite edges
    #                      d (min(l2, l3) + min(l4, l1)) )
    #
    # (k_mu: a fraction of the friction coefficient) and limits the slew of its reference, and
    # the torque it adds to the drag torque, to Ja |dw/dt| <= t_pair, from the last load samples,
    # and to `accel_max`. With the feet in the air, or on one foot, the limit is zero: the
    # reference stays where it is and the torque is the drag torque plus the integral, so a
    # bounce neither slows nor re-accelerates the rotor.
    #
    # The first brake, down to the cap, is the exception: it uses the total load,
    # t_any = k_mu (d / sqrt(2)) sum(l_i), and slews at up to `accel_td`. This is the same as
    # t_pair when the feet land together. On one foot the body pivots about that foot, which
    # takes (Jz + m r^2)/Jz times less yaw rate from the same brake than a free body; the brake
    # must not wait, because until it is done the thrust carries the whole weight and the rebound
    # would float the vehicle.
    #
    # In this mode the speed error compares the measured speed with the reference of the same
    # tick (in flight: with the next one), so the brake ends without an undershoot.
    @inputs begin
        w_cmd::Real, [unit = "rad/s", description = "Speed command from the allocation"]
        w::Real, [unit = "rad/s", description = "Measured rotor speed"]
        armed::Real, [description = "1 = drive enabled"]
        cyc_amp::Real, [unit = "N*m", description = "Cyclic torque amplitude to reserve"]
        v_bus::Real, [unit = "V", description = "Bus voltage"]
        f::Vec{4}, [unit = "N", description = "Foot loads from the load sensor"]
        land::Real, [description = "1 = landing mode: touchdown detection enabled"]
        thr::Real, [description = "Ground thrust fraction of the mission (scales the touchdown cap)"]
    end
    @outputs begin
        tau::Real = 0.0, [unit = "N*m", description = "Collective motor torque command"]
        w_ref::Real = 0.0, [unit = "rad/s", description = "Ramped speed reference"]
        sat::Real = 0.0, [description = "1 while the torque limit is active"]
        v_bus_s::Real = 25.2, [unit = "V", description = "Sampled bus voltage"]
        td::Real = 0.0, [description = "1 once the drive has seen the touchdown"]
        w_cap::Real = 1.0e4, [unit = "rad/s", description = "Speed cap set at touchdown"]
        t_hold::Real = 0.0, [unit = "N*m", description = "Yaw torque the measured foot loads can hold (0 until the touchdown)"]
    end
    @parameters begin
        Kp::Real = 0.03, [unit = "N*m*s/rad", description = "Speed loop P gain"]
        Ki::Real = 0.5, [unit = "N*m/rad", description = "Speed loop I gain"]
        tau_max::Real = 1.6, [unit = "N*m", min = 0, description = "Positive torque limit"]
        tau_min::Real = -0.4, [unit = "N*m", description = "Negative (braking) torque limit"]
        accel_max::Real = 260.0, [unit = "rad/s^2", min = 0, description = "Reference acceleration limit"]
        w_idle::Real = 90.0, [unit = "rad/s", min = 0, description = "Idle speed"]
        w_max::Real = 720.0, [unit = "rad/s", min = 0, description = "Speed limit"]
        kQ::Real = 1.05e-6, [description = "Propeller drag coefficient (N m s^2/rad^2)"]
        b_m::Real = 0.0, [unit = "N*m*s/rad", description = "Viscous loss of the motor"]
        Ja::Real = 3.5e-4, [unit = "kg*m^2", description = "Rotor plus propeller inertia"]
        i_max::Real = 0.5, [unit = "N*m", description = "Integral limit"]
        f_touch::Real = 2.0, [unit = "N", description = "Foot load that counts as touchdown"]
        k_td::Real = 1.0, [min = 0, max = 1, description = "Fraction of the speed reference kept at touchdown (1: no brake)"]
        accel_td::Real = 2000.0, [unit = "rad/s^2", min = 0, description = "Largest reference deceleration of the touchdown brake"]
        k_mu::Real = 0.4, [min = 0, description = "Friction coefficient the drive counts on (a fraction of the feet's)"]
        d_foot::Real = 0.2, [unit = "m", min = 0, description = "Side of the square the feet stand on"]
        f_min::Real = 0.1, [unit = "N", min = 0, description = "Load below which a foot counts as unloaded (sensor noise)"]
    end
    @variables begin
        I::Real = 0.0, [unit = "N*m", description = "Integral state"]
        wr::Real = 0.0, [unit = "rad/s", description = "Ramped reference state"]
        first::Real = 0.0, [description = "1 once the reference has caught the rotor"]
    end
    @discrete Ts = 2.5e-3 begin
        v_bus_s = v_bus
        if armed > 0.5
            if first < 0.5
                # catch the rotor where it is on the first armed tick
                wr = w
                wt = w
                first = 1.0
            else
                wt = clamp(w_cmd, w_idle, w_max)
            end
            if land < 0.5
                td = 0.0
                w_cap = 1.0e4
            elseif td < 0.5 && f[1] + f[2] + f[3] + f[4] > f_touch
                td = 1.0
                w_cap = k_td * wr
            end
            gr = ifelse(td > 0.5, 1.0, 0.0)
            wt = ifelse(gr > 0.5, min(wt, max(w_cap * sqrt(clamp(thr, 0.0, 1.0)), w_idle)), wt)
            # the yaw torque the measured foot loads hold: t_h, as a rotor acceleration ah
            l1 = max(f[1] - f_min, 0.0)
            l2 = max(f[2] - f_min, 0.0)
            l3 = max(f[3] - f_min, 0.0)
            l4 = max(f[4] - f_min, 0.0)
            t_pair = k_mu * d_foot * max(1.4142135623730951 * (min(l1, l3) + min(l2, l4)), max(min(l1, l2) + min(l3, l4), min(l2, l3) + min(l4, l1)))
            t_any = k_mu * d_foot * 0.7071067811865476 * (l1 + l2 + l3 + l4)
            brk = ifelse(wr > w_cap, 1.0, 0.0)
            t_h = ifelse(brk > 0.5, max(t_any, t_pair), t_pair)
            ah = t_h / Ja
            dn = ifelse(gr > 0.5, min(ifelse(brk > 0.5, accel_td, accel_max), ah), accel_max)
            up = ifelse(gr > 0.5, min(accel_max, ah), accel_max)
            dw = clamp(wt - wr, -dn * Ts, up * Ts)
            wn_ = wr + dw
            alpha = dw / Ts
            e = ifelse(gr > 0.5, wr - w, wn_ - w)
            uff = kQ * wn_ * abs(wn_) + b_m * wn_ + Ja * alpha
            tlim = max(tau_max - cyc_amp, 0.15)
            # latched: the part of the torque that changes the rotor speed stays inside t_h
            dyn = clamp(Ja * alpha + Kp * e, -t_h, t_h)
            held = ifelse(gr > 0.5 && abs(Ja * alpha + Kp * e) > t_h, 1.0, 0.0)
            ugr = kQ * wn_ * abs(wn_) + b_m * wn_ + dyn
            raw = ifelse(gr > 0.5, ugr + I, uff + Kp * e + I)
            if (raw > tlim && e > 0.0) || (raw < tau_min && e < 0.0) || held > 0.5
                I = I
            else
                I = clamp(I + Ki * e * Ts, -i_max, i_max)
            end
            raw = ifelse(gr > 0.5, ugr + I, uff + Kp * e + I)
            tau = clamp(raw, tau_min, tlim)
            sat = ifelse(raw > tlim || raw < tau_min, 1.0, 0.0)
            t_hold = gr * t_h
            wr = wn_
        else
            I = 0.0
            wr = 0.0
            tau = 0.0
            sat = 0.0
            first = 0.0
            td = 0.0
            w_cap = 1.0e4
            t_hold = 0.0
        end
        w_ref = wr
    end
end
