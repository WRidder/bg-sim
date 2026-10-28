@block Revolute2D begin
    # Compliant-pivot planar revolute joint (plan Mode A, D-MB7): the rotation is exact
    # (q is the link-side angle) and the two pivot translations are compliant spring states.
    # Every storage element stays in integral causality, so a 3-DOF IPlanar body attached
    # through the child port keeps all three momentum components differential.
    #
    # `d` lives in the rotating child frame, so the spring state integrates the full
    # relative displacement: ddt(d) = V_rel[2:3] + qdot * [-d2, d1] (the omega x d
    # transport term). The term is power-neutral because d . (z_hat x d) = 0, so the
    # fs . V_rel power identity and the 1/2 kt |d|^2 energy budget stay exact.
    #
    # The spring sign is fs = +kt*d + bt*V_rel (positive into the joint); it gives the body
    # the restoring force -fs through the child/parent effort pair under the e.f-into-
    # element convention. Do not flip it.
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
        q0::Real = 0.0, [unit = "rad", description = "Initial link angle"]
    end
    @variables begin
        q::Real = 0.0, [unit = "rad", description = "Link angle"]
        qdot::Real = 0.0, [unit = "rad/s", description = "Link rate"]
        d::Vec{2} = [0.0, 0.0], [unit = "m", state = :prefer, description = "Pivot translational deflection"]
        Vrel::Vec{3} = [0.0, 0.0, 0.0], [description = "Relative twist child - Ad(g)^-1 parent"]
        fs::Vec{3} = [0.0, 0.0, 0.0], [description = "Pivot spring/damper effort in the child frame"]
    end
    @outputs begin
        qout::Real, [unit = "rad"]
        qdout::Real, [unit = "rad/s"]
        pose::Vec{3}
        dout::Vec{2}
        Vrelout::Vec{3}
    end
    @equations begin
        # g(q) = (q, rx, ry); Ad(g) and its inverse in the angular-first ordering.
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
        # The axial torque is S^T child.e = child.e[1] (the drive reads it); the translations
        # carry the spring effort. parent.e is the reaction, drive.e the negative torque.
        child.e[2] ~ fs[2]
        child.e[3] ~ fs[3]
        parent.e[1] ~ -(child.e[1] + (sin(q) * rx - cos(q) * ry) * child.e[2] +
                        (cos(q) * rx + sin(q) * ry) * child.e[3])
        parent.e[2] ~ -(cos(q) * child.e[2] - sin(q) * child.e[3])
        parent.e[3] ~ -(sin(q) * child.e[2] + cos(q) * child.e[3])
        drive.e ~ -child.e[1]
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
    end
    @causality begin
        # parent and child receive the ground/link flows and impose their reactions; the
        # drive is a zero-torque rate tap (the Se supplies the effort).
        parent => :effort_out
        child => :effort_out
        drive => :flow_out
    end
end
