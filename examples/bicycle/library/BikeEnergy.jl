@block BikeEnergy begin
    # Energy book of the 3D bicycle bond graph. Each rigid body (rear frame with rider, front
    # fork with handlebar, two wheels) stores `1/2 V . P` (its body twist and momentum, the
    # RigidBody3D outputs) and `m g z` (z of its centre of mass from its composed pose); the two
    # tyre contacts store `Ec` (RollingDisk) and the three compliant joints store the strain
    # `1/2 kr |dth|^2 + 1/2 kt |dl|^2` of their held directions. `loss` integrates the contact
    # dissipation `Pd` of both tyres (normal damping and the work of the friction on the tiny
    # creep) and `work` the work of the steer torque `tau_s qd_s`, so
    #
    #     Ebal = E(t) + loss(t) - work(t) = E(0)
    #
    # up to the solver tolerance, as long as the joints' held directions are undamped (br = bt
    # = 0). Their dampers (the default br, bt of the models) dissipate a fraction of a joule
    # that this book does not count.
    @parameters begin
        mB::Real = 85.0, [unit = "kg", min = 0, description = "Rear frame and rider mass"]
        mH::Real = 4.0, [unit = "kg", min = 0, description = "Front fork and handlebar mass"]
        mR::Real = 2.0, [unit = "kg", min = 0, description = "Rear wheel mass"]
        mF::Real = 3.0, [unit = "kg", min = 0, description = "Front wheel mass"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration"]
        kr::Real = 1.0e6, [unit = "N*m/rad", min = 0, description = "Stiffness of the held rotations of the joints"]
        kt::Real = 1.0e6, [unit = "N/m", min = 0, description = "Translational stiffness of the joints"]
    end
    @inputs begin
        VB::Vec{6}
        PB::Vec{6}
        VH::Vec{6}
        PH::Vec{6}
        VR::Vec{6}
        PR::Vec{6}
        VF::Vec{6}
        PF::Vec{6}
        gB::Vec{7}
        gH::Vec{7}
        gR::Vec{7}
        gF::Vec{7}
        EcR::Real
        EcF::Real
        PdR::Real
        PdF::Real
        tau_s::Real
        qd_s::Real
        angR::Vec{2}
        linR::Vec{3}
        angS::Vec{2}
        linS::Vec{3}
        angF::Vec{2}
        linF::Vec{3}
    end
    @variables begin
        lossi::Real = 0.0, [unit = "J", state = :prefer, description = "Integrated contact dissipation"]
        worki::Real = 0.0, [unit = "J", state = :prefer, description = "Integrated steer torque work"]
    end
    @outputs begin
        Ek::Real, [unit = "J", description = "Kinetic energy of the four bodies"]
        Ep::Real, [unit = "J", description = "Gravity potential energy (ground at z = 0)"]
        Ej::Real, [unit = "J", description = "Strain energy of the joints' held directions"]
        E::Real, [unit = "J", description = "Stored energy Ek + Ep + tyre springs + joint strain"]
        loss::Real, [unit = "J", description = "Energy dissipated in the tyre contacts"]
        work::Real, [unit = "J", description = "Work of the steer torque"]
        Ebal::Real, [unit = "J", description = "E + loss - work (constant)"]
    end
    @equations begin
        Ek ~ 0.5 * (VB[1] * PB[1] + VB[2] * PB[2] + VB[3] * PB[3] + VB[4] * PB[4] + VB[5] * PB[5] + VB[6] * PB[6]) +
             0.5 * (VH[1] * PH[1] + VH[2] * PH[2] + VH[3] * PH[3] + VH[4] * PH[4] + VH[5] * PH[5] + VH[6] * PH[6]) +
             0.5 * (VR[1] * PR[1] + VR[2] * PR[2] + VR[3] * PR[3] + VR[4] * PR[4] + VR[5] * PR[5] + VR[6] * PR[6]) +
             0.5 * (VF[1] * PF[1] + VF[2] * PF[2] + VF[3] * PF[3] + VF[4] * PF[4] + VF[5] * PF[5] + VF[6] * PF[6])
        Ep ~ g0 * (mB * gB[7] + mH * gH[7] + mR * gR[7] + mF * gF[7])
        Ej ~ 0.5 * kr * (angR[1] * angR[1] + angR[2] * angR[2] + angS[1] * angS[1] + angS[2] * angS[2] +
                         angF[1] * angF[1] + angF[2] * angF[2]) +
             0.5 * kt * (linR[1] * linR[1] + linR[2] * linR[2] + linR[3] * linR[3] + linS[1] * linS[1] +
                         linS[2] * linS[2] + linS[3] * linS[3] + linF[1] * linF[1] + linF[2] * linF[2] + linF[3] * linF[3])
        E ~ Ek + Ep + EcR + EcF + Ej
        ddt(lossi) ~ PdR + PdF
        ddt(worki) ~ tau_s * qd_s
        loss ~ lossi
        work ~ worki
        Ebal ~ E + loss - work
    end
end
