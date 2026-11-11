@block Revolute2D begin
    # Compliant-pivot planar revolute joint (plan Mode A, D-MB7): the rotation is exact
    # (q is the link-side angle) and the two pivot translations are compliant spring states.
    # Every storage element stays in integral causality, so a 3-DOF IPlanar body attached
    # through the child port keeps all three momentum components differential.
    #
    # `d` lives in the rotating child frame, so the spring state integrates the full
    # relative displacement: ddt(d) = V_rel[2:3] + omega_child * [-d2, d1] (the omega x d
    # transport term), with omega_child = V_c[1] = parent.f[1] + qdot the **absolute**
    # child angular rate. Using the relative qdot here is wrong whenever the parent rotates
    # (the double pendulum, every link after the first): V_rel already contains the lever
    # term R(q) d, so the coordinate rate must use the full frame rotation. The term is
    # power-neutral because d . (z_hat x d) = 0, so the fs . V_rel power identity and the
    # 1/2 kt |d|^2 energy budget stay exact.
    #
    # The spring sign is fs = +kt*d + bt*V_rel (positive into the joint); it gives the body
    # the restoring force -fs through the child/parent effort pair under the e.f-into-
    # element convention. Do not flip it.
    #
    # Optional hard stops (as `Revolute3D`): below `q_min` and above `q_max` a stiff
    # spring-damper acts on the joint angle, `ts = k_stop (x_hi - x_lo) + d_stop (s_hi + s_lo)
    # qdot` with the smooth positive part `x = (d + sqrt(d^2 + w_stop^2))/2` of the overshoot
    # and `s = dx/dd`, between the drive and the link (`drive.e = -W_c[1] + ts`). No
    # `ifelse`, so no switching event. The limits are structural constants; the default
    # `-Inf`/`Inf` leaves each stop out of the equations.
    #
    # Child side: `V_c = -child.f` is the child body's twist and `W_c = -child.e` the wrench the
    # child body exerts on the joint (port variables count into the joint).
    @ports begin
        parent::Power{Planar}
        child::Power{Planar}
        drive::Power{Rotation}
    end
    @constants begin
        q_min::Real = -Inf, [unit = "rad", description = "Lower hard stop (-Inf: none)"]
        q_max::Real = Inf, [unit = "rad", description = "Upper hard stop (Inf: none)"]
    end
    @parameters begin
        rx::Real = 0.0, [unit = "m", description = "Pivot x in the parent frame"]
        ry::Real = 0.0, [unit = "m", description = "Pivot y in the parent frame"]
        kt::Real = 1.0e6, [unit = "N/m", min = 0, description = "Pivot translational stiffness"]
        bt::Real = 0.0, [unit = "N*s/m", min = 0, description = "Pivot translational damping"]
        q0::Real = 0.0, [unit = "rad", description = "Initial link angle"]
        k_stop::Real = 1.0e5, [unit = "N*m/rad", min = 0, description = "Hard-stop stiffness beyond q_min/q_max"]
        d_stop::Real = 100.0, [unit = "N*m*s/rad", min = 0, description = "Hard-stop damping beyond q_min/q_max"]
        w_stop::Real = 1.0e-5, [unit = "rad", min = 1.0e-12, description = "Smoothing width of the stop onset"]
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
        tau_stop::Real, [unit = "N*m", description = "Hard-stop torque on the joint angle (0 without stops)"]
    end
    @equations begin
        # g(q) = (q, rx, ry); Ad(g) and its inverse in the angular-first ordering.
        Vrel[1] ~ -child.f[1] - parent.f[1]
        Vrel[2] ~ -child.f[2] - ((sin(q) * rx - cos(q) * ry) * parent.f[1] +
                                cos(q) * parent.f[2] + sin(q) * parent.f[3])
        Vrel[3] ~ -child.f[3] - ((cos(q) * rx + sin(q) * ry) * parent.f[1] -
                                sin(q) * parent.f[2] + cos(q) * parent.f[3])
        qdot ~ Vrel[1]
        q ~ q0 + int(qdot, 0.0)
        ddt(d[1]) ~ Vrel[2] - child.f[1] * d[2]
        ddt(d[2]) ~ Vrel[3] + child.f[1] * d[1]
        fs[1] ~ 0.0
        fs[2] ~ kt * d[1] + bt * Vrel[2]
        fs[3] ~ kt * d[2] + bt * Vrel[3]
        # The axial torque is S^T W_c = W_c[1] (the drive reads it); the translations
        # carry the spring effort. parent.e is the reaction, drive.e the negative torque.
        child.e[2] ~ -fs[2]
        child.e[3] ~ -fs[3]
        parent.e[1] ~ (child.e[1] + (sin(q) * rx - cos(q) * ry) * child.e[2] +
                       (cos(q) * rx + sin(q) * ry) * child.e[3])
        parent.e[2] ~ cos(q) * child.e[2] - sin(q) * child.e[3]
        parent.e[3] ~ sin(q) * child.e[2] + cos(q) * child.e[3]
        if q_min > -Inf || q_max < Inf
            tau_stop ~ ifelse(q_max < Inf,
                0.5 * k_stop * ((q - q_max) + sqrt((q - q_max) * (q - q_max) + w_stop * w_stop)) +
                0.5 * d_stop * (1.0 + (q - q_max) / sqrt((q - q_max) * (q - q_max) + w_stop * w_stop)) * qdot,
                0.0) +
                ifelse(q_min > -Inf,
                -0.5 * k_stop * ((q_min - q) + sqrt((q_min - q) * (q_min - q) + w_stop * w_stop)) +
                0.5 * d_stop * (1.0 + (q_min - q) / sqrt((q_min - q) * (q_min - q) + w_stop * w_stop)) * qdot,
                0.0)
            drive.e ~ child.e[1] + tau_stop
        else
            tau_stop ~ 0.0
            drive.e ~ child.e[1]
        end
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
    @orientation begin
        parent => :in
        child => :out
        drive => :in
    end
end
