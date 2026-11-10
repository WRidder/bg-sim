@block FlightControl begin
    # Ingenuity-style flight controller at 500 Hz (the GNC rate of Grip et al. 2018), with the
    # loop structure of that paper: heave and yaw are decoupled by a collective mixing (symmetric
    # collective for heave, antisymmetric for yaw), roll and pitch are an inner PD loop on cyclic,
    # and the horizontal position is an outer PID loop that commands roll and pitch (rotated by the
    # heading). Gains come from `design/design.py`: every loop has its three closed-loop poles at
    # -p, which puts the crossovers at heave 1.7 Hz, yaw 2.2 Hz, inner roll/pitch 2.9 Hz and outer
    # position 0.5 Hz (the paper: 1.2, 1.9, 2.6 and 0.3 Hz). The paper adds higher-order loop
    # shaping on top; this example keeps plain PID laws.
    #
    #   heave   a_z = a_sp + Kp_z e_z + Kd_z e_vz + I_z;  T = m (g + a_z) / (cos roll cos pitch)
    #           th_s = th_hover + (T - m g) / Z_th                     (Z_th = dT/d th_s at hover)
    #   yaw     r_dot = Kp_psi e_psi + Kd_psi (r_sp - r) + I_psi;  th_a = th_a_trim + Izz r_dot / N_th
    #   rotors  th_upper = th_s - th_a,  th_lower = th_s + th_a        (clamped to the swashplate range)
    #   outer   a_xy = a_sp + Kp_xy e_xy + Kd_xy e_vxy + I_xy  -> pitch_d = a_fwd / g, roll_d = -a_left / g
    #   inner   M = I_rp (Kp_att (att_d - att) - Kd_att w + I_att) -> cyclic = M / (2 k_c), both rotors
    #
    # `mode` 0 (on the ground): collective at ground idle, cyclic zero, integrators reset.
    @inputs begin
        p::Vec{3}
        vw::Vec{3}
        wb::Vec{3}
        roll::Real
        pitch::Real
        yaw::Real
        p_sp::Vec{3}
        v_sp::Vec{3}
        a_sp::Vec{3}
        psi_sp::Real
        psi_rate::Real
        mode::Real
    end
    @outputs begin
        th_u::Real = 0.0, [unit = "rad", description = "Upper rotor collective command"]
        th_l::Real = 0.0, [unit = "rad", description = "Lower rotor collective command"]
        cx::Real = 0.0, [unit = "rad", description = "Roll cyclic command (both rotors)"]
        cy::Real = 0.0, [unit = "rad", description = "Pitch cyclic command (both rotors)"]
        roll_d::Real = 0.0, [unit = "rad", description = "Roll set-point of the inner loop"]
        pitch_d::Real = 0.0, [unit = "rad", description = "Pitch set-point of the inner loop"]
        T_cmd::Real = 0.0, [unit = "N", description = "Thrust command"]
    end
    @parameters begin
        m::Real = 1.8, [unit = "kg", min = 0, description = "Vehicle mass"]
        g0::Real = 3.71, [unit = "m/s^2", description = "Gravity"]
        Ixx::Real = 0.05, [unit = "kg*m^2", description = "Roll (apparent) inertia"]
        Iyy::Real = 0.05, [unit = "kg*m^2", description = "Pitch (apparent) inertia"]
        Izz::Real = 0.015, [unit = "kg*m^2", description = "Yaw inertia"]
        th_hover::Real = 0.16, [unit = "rad", description = "Symmetric collective at hover (feedforward)"]
        th_a_trim::Real = 0.01, [unit = "rad", description = "Antisymmetric collective at hover (torque balance)"]
        th_idle::Real = 0.0, [unit = "rad", description = "Ground-idle collective"]
        Z_th::Real = 40.0, [unit = "N/rad", description = "Thrust per radian of symmetric collective"]
        N_th::Real = -2.0, [unit = "N*m/rad", description = "Yaw torque per radian of antisymmetric collective"]
        k_c::Real = 6.5, [unit = "N*m/rad", description = "Hub moment per radian of cyclic, one rotor"]
        Kp_z::Real = 25.0, [unit = "1/s^2"]
        Kd_z::Real = 7.0, [unit = "1/s"]
        Ki_z::Real = 10.0, [unit = "1/s^3"]
        Kp_psi::Real = 36.0, [unit = "1/s^2"]
        Kd_psi::Real = 8.0, [unit = "1/s"]
        Ki_psi::Real = 10.0, [unit = "1/s^3"]
        Kp_xy::Real = 1.2, [unit = "1/s^2"]
        Kd_xy::Real = 1.8, [unit = "1/s"]
        Ki_xy::Real = 0.2, [unit = "1/s^3"]
        Kp_att::Real = 100.0, [unit = "1/s^2"]
        Kd_att::Real = 14.0, [unit = "1/s"]
        Ki_att::Real = 20.0, [unit = "1/s^3"]
        tilt_max::Real = 0.1745, [unit = "rad", description = "Roll/pitch set-point limit"]
        th_min::Real = -0.0785, [unit = "rad", description = "Collective lower limit (-4.5 deg)"]
        th_max::Real = 0.3054, [unit = "rad", description = "Collective upper limit (17.5 deg)"]
        cyc_max::Real = 0.1745, [unit = "rad", description = "Cyclic limit (10 deg)"]
        i_max::Real = 2.0, [unit = "m/s^2", description = "Integrator limit of the heave, yaw and position loops"]
        i_att_max::Real = 30.0, [unit = "rad/s^2", description = "Integrator limit of the roll/pitch loop (trims the edgewise-flow moment)"]
    end
    @variables begin
        iz::Real = 0.0
        ipsi::Real = 0.0
        ix::Real = 0.0
        iy::Real = 0.0
        ir::Real = 0.0
        ip::Real = 0.0
    end
    @discrete Ts = 2e-3 begin
        if mode > 0.5
            ez = p_sp[3] - p[3]
            iz = clamp(iz + Ki_z * ez * Ts, -i_max, i_max)
            az = a_sp[3] + Kp_z * ez + Kd_z * (v_sp[3] - vw[3]) + iz
            tc = m * (g0 + az) / max(cos(roll) * cos(pitch), 0.8)
            ths = th_hover + (tc - m * g0) / Z_th
            epsi = atan(sin(psi_sp - yaw), cos(psi_sp - yaw))
            ipsi = clamp(ipsi + Ki_psi * epsi * Ts, -i_max, i_max)
            rdd = Kp_psi * epsi + Kd_psi * (psi_rate - wb[3]) + ipsi
            tha = th_a_trim + Izz * rdd / N_th
            ex = p_sp[1] - p[1]
            ey = p_sp[2] - p[2]
            ix = clamp(ix + Ki_xy * ex * Ts, -i_max, i_max)
            iy = clamp(iy + Ki_xy * ey * Ts, -i_max, i_max)
            ax = a_sp[1] + Kp_xy * ex + Kd_xy * (v_sp[1] - vw[1]) + ix
            ay = a_sp[2] + Kp_xy * ey + Kd_xy * (v_sp[2] - vw[2]) + iy
            af = cos(yaw) * ax + sin(yaw) * ay
            al = -sin(yaw) * ax + cos(yaw) * ay
            pd = clamp(af / g0, -tilt_max, tilt_max)
            rd = clamp(-al / g0, -tilt_max, tilt_max)
            ir = clamp(ir + Ki_att * (rd - roll) * Ts, -i_att_max, i_att_max)
            ip = clamp(ip + Ki_att * (pd - pitch) * Ts, -i_att_max, i_att_max)
            mx = Ixx * (Kp_att * (rd - roll) - Kd_att * wb[1] + ir)
            my = Iyy * (Kp_att * (pd - pitch) - Kd_att * wb[2] + ip)
            th_u = clamp(ths - tha, th_min, th_max)
            th_l = clamp(ths + tha, th_min, th_max)
            cx = clamp(mx / (2.0 * k_c), -cyc_max, cyc_max)
            cy = clamp(my / (2.0 * k_c), -cyc_max, cyc_max)
            roll_d = rd
            pitch_d = pd
            T_cmd = tc
        else
            iz = 0.0
            ipsi = 0.0
            ix = 0.0
            iy = 0.0
            ir = 0.0
            ip = 0.0
            th_u = th_idle
            th_l = th_idle
            cx = 0.0
            cy = 0.0
            roll_d = 0.0
            pitch_d = 0.0
            T_cmd = 0.0
        end
    end
end
