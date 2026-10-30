@block EngageCtrl begin
    # Engage-phase controller (50 Hz): the three body angles are the references (phi_sp = 0, theta_sp,
    # psi_sp) and the height set-point is z_sp = z_b(t_e); there is NO horizontal position loop, so the
    # tilted thrust carries the multirotor into the wall. Outputs are the desired attitude quaternion
    # `qd` (Z-Y-X Euler angles (0, theta_sp, psi_sp), straight into the attitude controller) and the
    # collective thrust that keeps the height: F = m (g + a_z) / (cos(phi) cos(theta)) with
    # a_z = Kv (clamp(Kp (z_sp - z)) - v_z) + I (PI on the vertical velocity, integral held at zero
    # while the phase is not active).
    @inputs begin
        p::Vec{3}
        v::Vec{3}
        q::Vec{4}
        theta_sp::Real
        psi_sp::Real
        z_sp::Real
        active::Real
    end
    @outputs begin
        qd::Vec{4} = [1.0, 0.0, 0.0, 0.0]
        F::Real = 0.0, [unit = "N"]
    end
    @parameters begin
        m_nom::Real = 2.5, [unit = "kg", min = 0, description = "Nominal mass of the thrust feedforward"]
        g0::Real = 9.81, [unit = "m/s^2"]
        Kp_z::Real = 1.5, [unit = "1/s", description = "Height gain"]
        Kv_z::Real = 5.0, [unit = "1/s", description = "Vertical velocity P gain"]
        Ki_z::Real = 3.0, [unit = "1/s^2", description = "Vertical velocity I gain"]
        i_max::Real = 3.0, [unit = "m/s^2", description = "Integral limit"]
        F_max::Real = 60.0, [unit = "N", description = "Collective thrust limit"]
    end
    @variables iz::Real = 0.0, [description = "Vertical velocity integral (acceleration)"]
    @discrete Ts = 20e-3 begin
        vc = clamp(Kp_z * (z_sp - p[3]), -0.5, 0.5)
        ev = vc - v[3]
        if active > 0.5
            iz = clamp(iz + Ki_z * ev * Ts, -i_max, i_max)
        else
            iz = 0.0
        end
        az = Kv_z * ev + iz
        r31 = 2 * (q[2] * q[4] - q[1] * q[3])
        r32 = 2 * (q[3] * q[4] + q[1] * q[2])
        r33 = 1 - 2 * (q[2] * q[2] + q[3] * q[3])
        c33 = max(r33, 0.5)
        F = clamp(m_nom * (g0 + az) / c33, 0.0, F_max)
        ch = cos(0.5 * theta_sp)
        sh = sin(0.5 * theta_sp)
        cp = cos(0.5 * psi_sp)
        sp = sin(0.5 * psi_sp)
        qd = [cp * ch, -sp * sh, cp * sh, sp * ch]
    end
end
