@block AttitudeControl begin
    # An ideal attitude loop on the reaction-control torques (the LM's digital autopilot, much
    # simplified): it points the body x axis (the thrust axis) along the commanded thrust
    # direction `u` and turns the body about it by the roll angle `phi` (the "windows" angle:
    # 0 puts the body z axis, the crew's line of sight through the windows, up and forward;
    # pi puts it towards the surface). The desired body axes are
    #
    #     x_d = u,   z_0 = e_y x u / |e_y x u|,   z_d = cos(phi) z_0 + sin(phi) (x_d x z_0),
    #     y_d = z_d x x_d,
    #
    # the attitude error is the SO(3) error e = vee(R_d^T R - R^T R_d) / 2 and the torque is a
    # PD law scaled by the current principal moments, clamped to the RCS authority:
    #
    #     tau_k = clamp(J_k (-wn^2 e_k - 2 zeta wn w_k), -tau_max, tau_max).
    #
    # The descent engine's trim gimbal and the jets' quantised (pulsed) firing are not modelled.
    @inputs begin
        g::Vec{7}, [description = "Body pose (qw, qx, qy, qz, x, y, z)"]
        V::Vec{6}, [description = "Body twist [w; v] in body axes"]
        J::Vec{3}, [unit = "kg*m^2", description = "Principal moments of inertia"]
        u::Vec{3}, [description = "Commanded thrust direction (world, unit)"]
        phi::Real, [unit = "rad", description = "Roll (windows) angle about the thrust axis"]
    end
    @parameters begin
        wn::Real = 0.9, [unit = "rad/s", min = 0, description = "Natural frequency of the attitude loop"]
        zeta::Real = 0.9, [min = 0, description = "Damping ratio of the attitude loop"]
        tau_max::Real = 2970.0, [unit = "N*m", min = 0, description = "RCS torque authority per axis"]
    end
    @variables begin
        s2::Real
        Rm::Mat{3,3}, [description = "Rotation body to world"]
        Rd::Mat{3,3}, [description = "Desired rotation body to world (columns x_d, y_d, z_d)"]
        un::Real
        n0::Real
        z0::Vec{3}
        xz::Vec{3}, [description = "x_d x z_0"]
        e::Vec{3}, [description = "Attitude error (rad, small angles)"]
    end
    @outputs begin
        tx::Real, [unit = "N*m"]
        ty::Real, [unit = "N*m"]
        tz::Real, [unit = "N*m"]
        fx::Real, [unit = "N"]
        fy::Real, [unit = "N"]
        fz::Real, [unit = "N"]
        err_deg::Real, [description = "Attitude error magnitude (deg)"]
    end
    @equations begin
        s2 ~ g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4]
        Rm[1, 1] ~ (g[1] * g[1] + g[2] * g[2] - g[3] * g[3] - g[4] * g[4]) / s2
        Rm[1, 2] ~ 2 * (g[2] * g[3] - g[1] * g[4]) / s2
        Rm[1, 3] ~ 2 * (g[2] * g[4] + g[1] * g[3]) / s2
        Rm[2, 1] ~ 2 * (g[2] * g[3] + g[1] * g[4]) / s2
        Rm[2, 2] ~ (g[1] * g[1] - g[2] * g[2] + g[3] * g[3] - g[4] * g[4]) / s2
        Rm[2, 3] ~ 2 * (g[3] * g[4] - g[1] * g[2]) / s2
        Rm[3, 1] ~ 2 * (g[2] * g[4] - g[1] * g[3]) / s2
        Rm[3, 2] ~ 2 * (g[3] * g[4] + g[1] * g[2]) / s2
        Rm[3, 3] ~ (g[1] * g[1] - g[2] * g[2] - g[3] * g[3] + g[4] * g[4]) / s2
        un ~ sqrt(u[1] * u[1] + u[2] * u[2] + u[3] * u[3])
        for k in 1:3
            Rd[k, 1] ~ u[k] / un
        end
        # z_0 = e_y x x_d = (x_d3, 0, -x_d1) / n0
        n0 ~ sqrt(Rd[3, 1] * Rd[3, 1] + Rd[1, 1] * Rd[1, 1])
        z0[1] ~ Rd[3, 1] / n0
        z0[2] ~ 0.0
        z0[3] ~ -Rd[1, 1] / n0
        xz[1] ~ Rd[2, 1] * z0[3] - Rd[3, 1] * z0[2]
        xz[2] ~ Rd[3, 1] * z0[1] - Rd[1, 1] * z0[3]
        xz[3] ~ Rd[1, 1] * z0[2] - Rd[2, 1] * z0[1]
        for k in 1:3
            Rd[k, 3] ~ cos(phi) * z0[k] + sin(phi) * xz[k]
        end
        # y_d = z_d x x_d
        Rd[1, 2] ~ Rd[2, 3] * Rd[3, 1] - Rd[3, 3] * Rd[2, 1]
        Rd[2, 2] ~ Rd[3, 3] * Rd[1, 1] - Rd[1, 3] * Rd[3, 1]
        Rd[3, 2] ~ Rd[1, 3] * Rd[2, 1] - Rd[2, 3] * Rd[1, 1]
        # e = vee(Rd^T R - R^T Rd) / 2
        e[1] ~ 0.5 * (Rd[1, 3] * Rm[1, 2] + Rd[2, 3] * Rm[2, 2] + Rd[3, 3] * Rm[3, 2] - Rm[1, 3] * Rd[1, 2] - Rm[2, 3] * Rd[2, 2] - Rm[3, 3] * Rd[3, 2])
        e[2] ~ 0.5 * (Rd[1, 1] * Rm[1, 3] + Rd[2, 1] * Rm[2, 3] + Rd[3, 1] * Rm[3, 3] - Rm[1, 1] * Rd[1, 3] - Rm[2, 1] * Rd[2, 3] - Rm[3, 1] * Rd[3, 3])
        e[3] ~ 0.5 * (Rd[1, 2] * Rm[1, 1] + Rd[2, 2] * Rm[2, 1] + Rd[3, 2] * Rm[3, 1] - Rm[1, 2] * Rd[1, 1] - Rm[2, 2] * Rd[2, 1] - Rm[3, 2] * Rd[3, 1])
        tx ~ clamp(J[1] * (-wn * wn * e[1] - 2 * zeta * wn * V[1]), -tau_max, tau_max)
        ty ~ clamp(J[2] * (-wn * wn * e[2] - 2 * zeta * wn * V[2]), -tau_max, tau_max)
        tz ~ clamp(J[3] * (-wn * wn * e[3] - 2 * zeta * wn * V[3]), -tau_max, tau_max)
        fx ~ 0.0
        fy ~ 0.0
        fz ~ 0.0
        err_deg ~ asin(min(sqrt(e[1] * e[1] + e[2] * e[2] + e[3] * e[3]), 1.0)) * 180 / pi
    end
end
