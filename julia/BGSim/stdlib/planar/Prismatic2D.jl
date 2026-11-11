@block Prismatic2D begin
    # Planar prismatic joint: **exact translation along one axis**, compliant in the two
    # directions the joint has to hold (the rotation and the perpendicular translation).
    #
    # D-MB8: the drive domain follows the screw, so this joint exposes a **`Translation`**
    # drive (effort N, flow m/s), never `Rotation`: a prismatic drive carries a force and a
    # velocity, and hard-coding `Rotation` would make the scalar unit checker reject a valid
    # prismatic drive.
    #
    # Kinematics. With the axis direction n = (cos phi, sin phi) and the perpendicular
    # m = (-sin phi, cos phi), the joint pose is g(q) = (0, q*n), the screw is S = [0, n] and
    #
    #     V_rel = V_c - Ad(g(q))^-1 parent.f,
    #     qdot  = n . V_rel[2:3],   ddt(q) = qdot,
    #     dr    = V_rel[1]        (rotation deflection,      ddt(dr) = V_rel[1]),
    #     d     = m . V_rel[2:3]  (perpendicular deflection, ddt(d)  = m . V_rel[2:3]),
    #     fr = kr*dr + br*V_rel[1],   fd = kd*d + bd*(m . V_rel[2:3]),
    #     W_c = [fr, -sin(phi)*fd + cos(phi)*tau, cos(phi)*fd + sin(phi)*tau],
    #     tau = n . W_c[2:3]  (the axial force the drive balances),  drive.e = -tau,
    #     parent.e = -Ad(g)^-T W_c.
    #
    # Power: `parent.e.parent.f + W_c.V_c + drive.e*qdot = fr*V_rel[1] + fd*d_dot`,
    # i.e. exactly the two spring/damper powers, so with br = bd = 0 the joint is conservative.
    # Both hard directions are compliant, so every state stays integral (no W201); `kr, kd ->
    # Inf` gives the rigid prismatic joint.
    #
    # Optional hard stops (as `Revolute3D`): below `q_min` and above `q_max` a stiff
    # spring-damper acts on the joint displacement, `fs = k_stop (x_hi - x_lo) + d_stop (s_hi +
    # s_lo) qdot` with the smooth positive part `x = (d + sqrt(d^2 + w_stop^2))/2` of the
    # overshoot and `s = dx/dd`, applied like the drive (`drive.e = -tau + fs`). No `ifelse`,
    # so no switching event. The limits are structural constants; the default `-Inf`/`Inf`
    # leaves each stop out of the equations.
    #
    # Child side: `V_c = -child.f` is the child body's twist and `W_c = -child.e` the wrench the
    # child body exerts on the joint (port variables count into the joint).
    @ports begin
        parent::Power{Planar}
        child::Power{Planar}
        drive::Power{Translation}
    end
    @constants begin
        q_min::Real = -Inf, [unit = "m", description = "Lower hard stop (-Inf: none)"]
        q_max::Real = Inf, [unit = "m", description = "Upper hard stop (Inf: none)"]
    end
    @parameters begin
        phi::Real = 0.0, [unit = "rad", description = "Axis direction in the parent frame"]
        kr::Real = 1.0e6, [unit = "N*m/rad", min = 0, description = "Rotational stiffness"]
        br::Real = 0.0, [unit = "N*m*s/rad", min = 0, description = "Rotational damping"]
        kd::Real = 1.0e6, [unit = "N/m", min = 0, description = "Perpendicular translational stiffness"]
        bd::Real = 0.0, [unit = "N*s/m", min = 0, description = "Perpendicular translational damping"]
        q0::Real = 0.0, [unit = "m", description = "Initial displacement"]
        k_stop::Real = 1.0e6, [unit = "N/m", min = 0, description = "Hard-stop stiffness beyond q_min/q_max"]
        d_stop::Real = 1.0e3, [unit = "N*s/m", min = 0, description = "Hard-stop damping beyond q_min/q_max"]
        w_stop::Real = 1.0e-6, [unit = "m", min = 1.0e-12, description = "Smoothing width of the stop onset"]
    end
    @variables begin
        q::Real = 0.0, [unit = "m", description = "Joint displacement along the axis"]
        qdot::Real = 0.0, [unit = "m/s", description = "Joint rate"]
        dr::Real = 0.0, [unit = "rad", state = :prefer, description = "Rotational deflection"]
        d::Real = 0.0, [unit = "m", state = :prefer, description = "Perpendicular deflection"]
        Vrel::Vec{3} = [0.0, 0.0, 0.0], [description = "Relative twist child - Ad(g)^-1 parent"]
        fr::Real = 0.0, [unit = "N*m", description = "Rotational spring/damper effort"]
        fd::Real = 0.0, [unit = "N", description = "Perpendicular spring/damper force"]
        tau::Real = 0.0, [unit = "N", description = "Axial force carried by the drive"]
    end
    @outputs begin
        qout::Real, [unit = "m"]
        qdout::Real, [unit = "m/s"]
        pose::Vec{3}
        drout::Real, [unit = "rad"]
        dout::Real, [unit = "m"]
        Vrelout::Vec{3}
        f_stop::Real, [unit = "N", description = "Hard-stop force on the joint displacement (0 without stops)"]
    end
    @equations begin
        Vrel[1] ~ -child.f[1] - parent.f[1]
        Vrel[2] ~ -child.f[2] + q * sin(phi) * parent.f[1] - parent.f[2]
        Vrel[3] ~ -child.f[3] - q * cos(phi) * parent.f[1] - parent.f[3]
        qdot ~ cos(phi) * Vrel[2] + sin(phi) * Vrel[3] + parent.f[1] * d
        q ~ q0 + int(qdot, 0.0)
        ddt(dr) ~ Vrel[1]
        ddt(d) ~ -sin(phi) * Vrel[2] + cos(phi) * Vrel[3]
        fr ~ kr * dr + br * Vrel[1]
        fd ~ kd * d + bd * (-sin(phi) * Vrel[2] + cos(phi) * Vrel[3])
        child.e[1] ~ -fr
        child.e[2] ~ sin(phi) * fd - cos(phi) * tau
        child.e[3] ~ -cos(phi) * fd - sin(phi) * tau
        parent.e[1] ~ child.e[1] - q * sin(phi) * child.e[2] + q * cos(phi) * child.e[3]
        parent.e[2] ~ child.e[2]
        parent.e[3] ~ child.e[3]
        if q_min > -Inf || q_max < Inf
            f_stop ~ ifelse(q_max < Inf,
                0.5 * k_stop * ((q - q_max) + sqrt((q - q_max) * (q - q_max) + w_stop * w_stop)) +
                0.5 * d_stop * (1.0 + (q - q_max) / sqrt((q - q_max) * (q - q_max) + w_stop * w_stop)) * qdot,
                0.0) +
                ifelse(q_min > -Inf,
                -0.5 * k_stop * ((q_min - q) + sqrt((q_min - q) * (q_min - q) + w_stop * w_stop)) +
                0.5 * d_stop * (1.0 + (q_min - q) / sqrt((q_min - q) * (q_min - q) + w_stop * w_stop)) * qdot,
                0.0)
            drive.e ~ -tau + f_stop
        else
            f_stop ~ 0.0
            drive.e ~ -tau
        end
        drive.f ~ qdot
        qout ~ q
        qdout ~ qdot
        pose[1] ~ 0.0
        pose[2] ~ q * cos(phi)
        pose[3] ~ q * sin(phi)
        drout ~ dr
        dout ~ d
        Vrelout[1] ~ Vrel[1]
        Vrelout[2] ~ Vrel[2]
        Vrelout[3] ~ Vrel[3]
    end
    @causality begin
        parent => :effort_out
        child => :effort_out
        drive => :flow_out
    end
    @orientation begin
        parent => :in
        child => :out
        drive => :in
    end
end
