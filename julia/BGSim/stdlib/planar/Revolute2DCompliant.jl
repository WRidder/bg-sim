@block Revolute2DCompliant begin
    # Compliant planar revolute joint, **per-axis compliance variant** (D-MB9): the
    # compliant-pivot joint of `stdlib:multibond/Revolute2D` (exact rotation `q`, compliant
    # pivot translations `d` with `kt`/`bt`) plus a **torsional** spring-damper `k`/`b` on the
    # joint angle about its rest angle `qrest`.
    #
    #   kt -> Inf  and  k -> Inf   =>  the rigid revolute (`Revolute2DRigid`): the pivot
    #   translations and the joint angle become hard constraints and the period converges to
    #   the rigid one.
    #
    # The joint pose uses the **link-side** coordinate (plan 6, compliance convention): `q` is
    # the link angle, so the spring acts on the link's own angle and the pose composed from
    # `q` is the geometric pose of the link. Every state is integral (no W201).
    #
    # Effort chain: the axial torque is `S^T child.e = child.e[1]`; the drive sees the
    # reaction plus the spring torque, `drive.e = -child.e[1] + k(q - qrest) + b*qdot`, so the
    # drive/child pair carries exactly the spring's power and the port power identity becomes
    # `parent.e.parent.f + child.e.child.f + drive.e*qdot = fs.Vrel + tau_spring*qdot`.
    @ports begin
        parent::Power{Planar}
        child::Power{Planar}
        drive::Power{Rotation}
    end
    @parameters begin
        rx::Real = 0.0, [unit = "m", description = "Pivot x in the parent frame"]
        ry::Real = 0.0, [unit = "m", description = "Pivot y in the parent frame"]
        kt::Real = 1.0e6, [unit = "N/m", min = 0, description = "Pivot translational stiffness"]
        bt::Real = 0.0, [unit = "N*s/m", min = 0, description = "Pivot translational damping"]
        k::Real = 0.0, [unit = "N*m/rad", min = 0, description = "Joint torsional stiffness"]
        b::Real = 0.0, [unit = "N*m*s/rad", min = 0, description = "Joint torsional damping"]
        q0::Real = 0.0, [unit = "rad", description = "Initial link angle"]
        qrest::Real = 0.0, [unit = "rad", description = "Torsional spring rest angle"]
    end
    @variables begin
        q::Real = 0.0, [unit = "rad", description = "Link angle"]
        qdot::Real = 0.0, [unit = "rad/s", description = "Link rate"]
        d::Vec{2} = [0.0, 0.0], [unit = "m", state = :prefer, description = "Pivot translational deflection"]
        Vrel::Vec{3} = [0.0, 0.0, 0.0], [description = "Relative twist child - Ad(g)^-1 parent"]
        fs::Vec{3} = [0.0, 0.0, 0.0], [description = "Pivot spring/damper effort in the child frame"]
        taus::Real = 0.0, [unit = "N*m", description = "Torsional spring/damper torque on the link"]
    end
    @outputs begin
        qout::Real, [unit = "rad"]
        qdout::Real, [unit = "rad/s"]
        pose::Vec{3}
        dout::Vec{2}
        Vrelout::Vec{3}
        tauout::Real, [unit = "N*m"]
    end
    @equations begin
        Vrel[1] ~ child.f[1] - parent.f[1]
        Vrel[2] ~ child.f[2] - ((sin(q) * rx - cos(q) * ry) * parent.f[1] +
                                cos(q) * parent.f[2] + sin(q) * parent.f[3])
        Vrel[3] ~ child.f[3] - ((cos(q) * rx + sin(q) * ry) * parent.f[1] -
                                sin(q) * parent.f[2] + cos(q) * parent.f[3])
        qdot ~ Vrel[1]
        q ~ q0 + int(qdot, 0.0)
        ddt(d[1]) ~ Vrel[2] + qdot * d[2]
        ddt(d[2]) ~ Vrel[3] - qdot * d[1]
        fs[1] ~ 0.0
        fs[2] ~ kt * d[1] + bt * Vrel[2]
        fs[3] ~ kt * d[2] + bt * Vrel[3]
        taus ~ k * (q - qrest) + b * qdot
        child.e[2] ~ fs[2]
        child.e[3] ~ fs[3]
        parent.e[1] ~ -(child.e[1] + (sin(q) * rx - cos(q) * ry) * child.e[2] +
                        (cos(q) * rx + sin(q) * ry) * child.e[3])
        parent.e[2] ~ -(cos(q) * child.e[2] - sin(q) * child.e[3])
        parent.e[3] ~ -(sin(q) * child.e[2] + cos(q) * child.e[3])
        drive.e ~ -child.e[1] + taus
        drive.f ~ qdot
        qout ~ q
        qdout ~ qdot
        pose[1] ~ q
        pose[2] ~ rx
        pose[3] ~ ry
        dout[1] ~ d[1]
        dout[2] ~ d[2]
        Vrelout[1] ~ Vrel[1]
        Vrelout[2] ~ Vrel[2]
        Vrelout[3] ~ Vrel[3]
        tauout ~ taus
    end
    @causality begin
        parent => :effort_out
        child => :effort_out
        drive => :flow_out
    end
end
