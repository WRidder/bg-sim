@block Revolute2DFriction begin
    # Planar revolute joint with **joint friction** (D-MB9 variant): the compliant pivot of
    # `stdlib:multibond/Revolute2D` plus a viscous + regularised-Coulomb torque on the joint
    # rate,
    #
    #     tau_f = bv*qdot + Fc*tanh(qdot/v_eps)
    #
    # acting between the drive and the link (`drive.e = -child.e[1] + tau_f`), so the link
    # feels `-tau_f` and the joint's port power identity gains exactly `tau_f*qdot <= 0`:
    # friction can only remove energy. `tanh` is the regularisation the plan asks for
    # (`ContactPoint`'s scheme, D-MB11); `v_eps` is the width over which it becomes Coulomb.
    #
    # Stick/slip: for `|tau_applied| < Fc` the drive holds the link (`qdot -> 0`), above it
    # the link slips and `tau_f -> Fc*sign(qdot)`.
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
        Fc::Real = 0.0, [unit = "N*m", min = 0, description = "Coulomb friction torque"]
        Fv::Real = 0.0, [unit = "N*m*s/rad", min = 0, description = "Viscous friction coefficient"]
        v_eps::Real = 1.0e-3, [unit = "rad/s", min = 0, description = "Regularisation speed of the Coulomb term"]
        q0::Real = 0.0, [unit = "rad", description = "Initial link angle"]
    end
    @variables begin
        q::Real = 0.0, [unit = "rad", description = "Link angle"]
        qdot::Real = 0.0, [unit = "rad/s", description = "Link rate"]
        d::Vec{2} = [0.0, 0.0], [unit = "m", state = :prefer, description = "Pivot translational deflection"]
        Vrel::Vec{3} = [0.0, 0.0, 0.0], [description = "Relative twist child - Ad(g)^-1 parent"]
        fs::Vec{3} = [0.0, 0.0, 0.0], [description = "Pivot spring/damper effort in the child frame"]
        tf::Real = 0.0, [unit = "N*m", description = "Friction torque on the link"]
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
        tf ~ Fv * qdot + Fc * tanh(qdot / v_eps)
        child.e[2] ~ fs[2]
        child.e[3] ~ fs[3]
        parent.e[1] ~ -(child.e[1] + (sin(q) * rx - cos(q) * ry) * child.e[2] +
                        (cos(q) * rx + sin(q) * ry) * child.e[3])
        parent.e[2] ~ -(cos(q) * child.e[2] - sin(q) * child.e[3])
        parent.e[3] ~ -(sin(q) * child.e[2] + cos(q) * child.e[3])
        drive.e ~ -child.e[1] + tf
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
        tauout ~ tf
    end
    @causality begin
        parent => :effort_out
        child => :effort_out
        drive => :flow_out
    end
end
