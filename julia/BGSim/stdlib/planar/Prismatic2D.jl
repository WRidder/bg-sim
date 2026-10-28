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
    #     V_rel = child.f - Ad(g(q))^-1 parent.f,
    #     qdot  = n . V_rel[2:3],   ddt(q) = qdot,
    #     dr    = V_rel[1]        (rotation deflection,      ddt(dr) = V_rel[1]),
    #     d     = m . V_rel[2:3]  (perpendicular deflection, ddt(d)  = m . V_rel[2:3]),
    #     fr = kr*dr + br*V_rel[1],   fd = kd*d + bd*(m . V_rel[2:3]),
    #     child.e = [fr, -sin(phi)*fd + cos(phi)*tau, cos(phi)*fd + sin(phi)*tau],
    #     tau = n . child.e[2:3]  (the axial force the drive balances),  drive.e = -tau,
    #     parent.e = -Ad(g)^-T child.e.
    #
    # Power: `parent.e.parent.f + child.e.child.f + drive.e*qdot = fr*V_rel[1] + fd*d_dot`,
    # i.e. exactly the two spring/damper powers, so with br = bd = 0 the joint is conservative.
    # Both hard directions are compliant, so every state stays integral (no W201); `kr, kd ->
    # Inf` gives the rigid prismatic joint.
    @ports begin
        parent::Power{Planar}
        child::Power{Planar}
        drive::Power{Translation}
    end
    @parameters begin
        phi::Real = 0.0, [unit = "rad", description = "Axis direction in the parent frame"]
        kr::Real = 1.0e6, [unit = "N*m/rad", min = 0, description = "Rotational stiffness"]
        br::Real = 0.0, [unit = "N*m*s/rad", min = 0, description = "Rotational damping"]
        kd::Real = 1.0e6, [unit = "N/m", min = 0, description = "Perpendicular translational stiffness"]
        bd::Real = 0.0, [unit = "N*s/m", min = 0, description = "Perpendicular translational damping"]
        q0::Real = 0.0, [unit = "m", description = "Initial displacement"]
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
    end
    @equations begin
        Vrel[1] ~ child.f[1] - parent.f[1]
        Vrel[2] ~ child.f[2] + q * sin(phi) * parent.f[1] - parent.f[2]
        Vrel[3] ~ child.f[3] - q * cos(phi) * parent.f[1] - parent.f[3]
        qdot ~ cos(phi) * Vrel[2] + sin(phi) * Vrel[3]
        q ~ q0 + int(qdot, 0.0)
        ddt(dr) ~ Vrel[1]
        ddt(d) ~ -sin(phi) * Vrel[2] + cos(phi) * Vrel[3]
        fr ~ kr * dr + br * Vrel[1]
        fd ~ kd * d + bd * (-sin(phi) * Vrel[2] + cos(phi) * Vrel[3])
        child.e[1] ~ fr
        child.e[2] ~ -sin(phi) * fd + cos(phi) * tau
        child.e[3] ~ cos(phi) * fd + sin(phi) * tau
        parent.e[1] ~ -(child.e[1] - q * sin(phi) * child.e[2] + q * cos(phi) * child.e[3])
        parent.e[2] ~ -child.e[2]
        parent.e[3] ~ -child.e[3]
        drive.e ~ -tau
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
end
