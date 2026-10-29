@block ArmCtrl3R begin
    # 1 ms joint-space PD + gravity compensation for the RRR arm (plan 9.8). The firmware
    # samples the three joint angles and rates and holds the three motor voltages until the
    # next tick (zero-order hold), so no algebraic loop closes through the plant.
    #
    #   e_i   = ref_i - q_i,    rd_i = (ref_i - ref_i at the previous tick) / Ts
    #   tc_i  = Kp_i e_i + Kd_i (rd_i - qd_i) + dV/dq_i(q)   joint torque command
    #   u_i   = clamp(R tc_i / (n k_t) + n k_t qd_i, -umax, umax)
    #
    # Outputs: `u_i` (motor voltage, V) for the motor-driven models and `tc_i` (the joint torque
    # command before the motor, N*m) for the ideal-torque-source models used in the comparison
    # with the multibond arm.
    #
    # The gravity term is the same dV/dq as the plant (r_e = l2 cos q2, r_t = r_e + l3 cos(q2+q3)):
    #   dV/dq1 = 0,  dV/dq2 = g (m2 r_e + m3 r_t),  dV/dq3 = g m3 l3 cos(q2+q3)
    # so a settled arm sits on the reference instead of the PD droop dV/dq / Kp. The joint torque
    # reaches the joint through the gear (ratio n) and the motor constant k_t, so the static
    # voltage that produces `tc` is R tc / (n k_t); the second term cancels the back-EMF
    # n k_t qd. The reference rate `rd` is the backward difference of the sampled TimeTable
    # reference (zero at the first tick), so the PD follows a moving reference without the
    # lag Kd v / Kp of a derivative on the measurement. `clamp` in `@discrete` is generated
    # code, not a symbolic ifelse: no event.
    @parameters begin
        Kp1::Real = 400.0, [unit = "N*m/rad", min = 0, description = "Joint 1 proportional gain"]
        Kd1::Real = 40.0, [unit = "N*m*s/rad", min = 0, description = "Joint 1 rate gain"]
        Kp2::Real = 400.0, [unit = "N*m/rad", min = 0, description = "Joint 2 proportional gain"]
        Kd2::Real = 40.0, [unit = "N*m*s/rad", min = 0, description = "Joint 2 rate gain"]
        Kp3::Real = 100.0, [unit = "N*m/rad", min = 0, description = "Joint 3 proportional gain"]
        Kd3::Real = 10.0, [unit = "N*m*s/rad", min = 0, description = "Joint 3 rate gain"]
        l2::Real = 0.4, [unit = "m", min = 0, description = "Upper arm length"]
        l3::Real = 0.3, [unit = "m", min = 0, description = "Forearm length"]
        m2::Real = 2.0, [unit = "kg", min = 0, description = "Elbow point mass"]
        m3::Real = 1.0, [unit = "kg", min = 0, description = "Tip point mass"]
        g::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration"]
        R::Real = 1.0, [unit = "Ohm", min = 0, description = "Motor winding resistance"]
        k_t::Real = 0.1, [unit = "N*m/A", min = 0, description = "Motor torque constant"]
        n::Real = 50.0, [min = 0, description = "Gear ratio (motor rate = n joint rate)"]
        umax::Real = 48.0, [unit = "V", min = 0, description = "Motor voltage limit"]
    end
    @inputs begin
        q1::Real
        q2::Real
        q3::Real
        qd1::Real
        qd2::Real
        qd3::Real
        ref1::Real
        ref2::Real
        ref3::Real
    end
    @outputs begin
        u1::Real = 0.0
        u2::Real = 0.0
        u3::Real = 0.0
        tc1::Real = 0.0, [unit = "N*m"]
        tc2::Real = 0.0, [unit = "N*m"]
        tc3::Real = 0.0, [unit = "N*m"]
        e1::Real = 0.0
        e2::Real = 0.0
        e3::Real = 0.0
    end
    @variables begin
        rp1::Real = 0.0, [description = "Reference 1 at the previous tick"]
        rp2::Real = 0.0, [description = "Reference 2 at the previous tick"]
        rp3::Real = 0.0, [description = "Reference 3 at the previous tick"]
        started::Int = 0, [description = "0 before the first tick, 1 afterwards"]
    end
    @discrete Ts = 1e-3 begin
        e1 = ref1 - q1
        e2 = ref2 - q2
        e3 = ref3 - q3
        re = l2 * cos(q2)
        rt = re + l3 * cos(q2 + q3)
        G2 = g * (m2 * re + m3 * rt)
        G3 = g * m3 * l3 * cos(q2 + q3)
        rd1 = ifelse(started == 0, 0.0, (ref1 - rp1) / Ts)
        rd2 = ifelse(started == 0, 0.0, (ref2 - rp2) / Ts)
        rd3 = ifelse(started == 0, 0.0, (ref3 - rp3) / Ts)
        tc1 = Kp1 * e1 + Kd1 * (rd1 - qd1)
        tc2 = Kp2 * e2 + Kd2 * (rd2 - qd2) + G2
        tc3 = Kp3 * e3 + Kd3 * (rd3 - qd3) + G3
        # joint torque command (the output `tc_i` drives an ideal torque source; `u_i` the motor)
        u1 = clamp(R * tc1 / (n * k_t) + n * k_t * qd1, -umax, umax)
        u2 = clamp(R * tc2 / (n * k_t) + n * k_t * qd2, -umax, umax)
        u3 = clamp(R * tc3 / (n * k_t) + n * k_t * qd3, -umax, umax)
        rp1 = ref1
        rp2 = ref2
        rp3 = ref3
        started = 1
    end
end
