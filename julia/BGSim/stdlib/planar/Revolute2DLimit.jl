@block Revolute2DLimit begin
    # Planar revolute joint with **one-sided limits** (D-MB9 variant): the compliant pivot of
    # `stdlib:multibond/Revolute2D` plus a one-sided spring-damper that only acts outside
    # `[lower, upper]`,
    #
    #     tau_l = kL * (g(q - upper) + g(lower - q)) + bL * (gU + gL) * qdot
    #     g(y)  = y * (1 + tanh(y/delta)) / 2          (smooth one-sided ramp)
    #     gU    = (1 + tanh((q - upper)/delta)) / 2,   gL = (1 + tanh((lower - q)/delta)) / 2
    #
    # applied between the drive and the link (`drive.e = -child.e[1] + tau_l`), so the link
    # feels the stop torque and the stop only ever removes or returns energy
    # (`tau_l*qdot <= 0` outside the limits for `bL >= 0`). Inside the limits the joint is the
    # plain compliant revolute.
    #
    # The ramp is smoothed over `delta` (default 1 mrad) on purpose: a discontinuous
    # `ifelse` guard on the joint angle the solver watches re-fires the condition-only
    # callback at every step near the stop and ends in W206/MaxIters (the Zeno behaviour of
    # NOTES FIX-M2 chattering; X2.5's valve uses the same smoothed-max device). The limit
    # constants are `kL`/`bL`; `delta -> 0` recovers the hard stop.
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
        lower::Real = -1.0, [unit = "rad", description = "Lower joint limit"]
        upper::Real = 1.0, [unit = "rad", description = "Upper joint limit"]
        kL::Real = 1.0e4, [unit = "N*m/rad", min = 0, description = "Limit stop stiffness"]
        bL::Real = 0.0, [unit = "N*m*s/rad", min = 0, description = "Limit stop damping"]
        delta::Real = 1.0e-3, [unit = "rad", min = 0, description = "Smoothing width of the limit ramp"]
        q0::Real = 0.0, [unit = "rad", description = "Initial link angle"]
    end
    @variables begin
        q::Real = 0.0, [unit = "rad", description = "Link angle"]
        qdot::Real = 0.0, [unit = "rad/s", description = "Link rate"]
        d::Vec{2} = [0.0, 0.0], [unit = "m", state = :prefer, description = "Pivot translational deflection"]
        Vrel::Vec{3} = [0.0, 0.0, 0.0], [description = "Relative twist child - Ad(g)^-1 parent"]
        fs::Vec{3} = [0.0, 0.0, 0.0], [description = "Pivot spring/damper effort in the child frame"]
        tl::Real = 0.0, [unit = "N*m", description = "Limit stop torque on the link"]
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
        tl ~ kL * ((q - upper) * (1 + tanh((q - upper) / delta)) / 2 +
                   (q - lower) * (1 + tanh((lower - q) / delta)) / 2) +
             bL * ((1 + tanh((q - upper) / delta)) / 2 +
                   (1 + tanh((lower - q) / delta)) / 2) * qdot
        child.e[2] ~ fs[2]
        child.e[3] ~ fs[3]
        parent.e[1] ~ -(child.e[1] + (sin(q) * rx - cos(q) * ry) * child.e[2] +
                        (cos(q) * rx + sin(q) * ry) * child.e[3])
        parent.e[2] ~ -(cos(q) * child.e[2] - sin(q) * child.e[3])
        parent.e[3] ~ -(sin(q) * child.e[2] + cos(q) * child.e[3])
        drive.e ~ -child.e[1] + tl
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
        tauout ~ tl
    end
    @causality begin
        parent => :effort_out
        child => :effort_out
        drive => :flow_out
    end
end
