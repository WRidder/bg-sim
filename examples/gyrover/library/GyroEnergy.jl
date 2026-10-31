@block GyroEnergy begin
    # Energy book of the Gyrover bond graph. Each rigid body stores `1/2 V . P` (its body
    # twist and momentum, the outputs of RigidBody3D) and `m g z` (z of its centre of mass from
    # its composed pose); the flywheel's axial energy is Rotor3D's `Ek`, the contact spring's
    # RollingDisk's `Ec`. `loss` integrates the contact dissipation `Pd` (the normal damper
    # and the friction work of the creep) and `work` the work of the three motors
    # (`tau1 qda + tau2 qdt + tau3 w3`, joint torque times joint rate), so
    #
    #     E(t) + loss(t) - work(t) = E(0)
    #
    # up to the solver tolerance and the strain of the stiff joint springs (micro-joules).
    @parameters begin
        m_w::Real = 2.0, [unit = "kg", min = 0, description = "Wheel mass"]
        m_p::Real = 3.417, [unit = "kg", min = 0, description = "Pendulum mass"]
        m_g::Real = 1.6, [unit = "kg", min = 0, description = "Gimbal and flywheel mass"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration"]
    end
    @inputs begin
        Vw::Vec{6}
        Pw::Vec{6}
        Vp::Vec{6}
        Pp::Vec{6}
        Vg::Vec{6}
        Pg::Vec{6}
        gw::Vec{7}
        gp::Vec{7}
        gg::Vec{7}
        tau1::Real
        qda::Real
        tau2::Real
        qdt::Real
        tau3::Real
        w3::Real
        Er::Real
        Ec::Real
        Pd::Real
    end
    @variables begin
        lossi::Real = 0.0, [unit = "J", state = :prefer, description = "Integrated contact dissipation"]
        wini::Real = 0.0, [unit = "J", state = :prefer, description = "Integrated motor work"]
    end
    @outputs begin
        Ek::Real, [unit = "J", description = "Kinetic energy (bodies + flywheel spin)"]
        Ep::Real, [unit = "J", description = "Gravity potential energy (ground at z = 0)"]
        E::Real, [unit = "J", description = "Total stored energy Ek + Ep + contact spring"]
        loss::Real, [unit = "J", description = "Energy dissipated in the contact"]
        work::Real, [unit = "J", description = "Work done by the three motors"]
        Ebal::Real, [unit = "J", description = "E + loss - work (constant)"]
    end
    @equations begin
        Ek ~ 0.5 * (Vw[1] * Pw[1] + Vw[2] * Pw[2] + Vw[3] * Pw[3] + Vw[4] * Pw[4] + Vw[5] * Pw[5] + Vw[6] * Pw[6]) +
             0.5 * (Vp[1] * Pp[1] + Vp[2] * Pp[2] + Vp[3] * Pp[3] + Vp[4] * Pp[4] + Vp[5] * Pp[5] + Vp[6] * Pp[6]) +
             0.5 * (Vg[1] * Pg[1] + Vg[2] * Pg[2] + Vg[3] * Pg[3] + Vg[4] * Pg[4] + Vg[5] * Pg[5] + Vg[6] * Pg[6]) + Er
        Ep ~ g0 * (m_w * gw[7] + m_p * gp[7] + m_g * gg[7])
        E ~ Ek + Ep + Ec
        ddt(lossi) ~ Pd
        loss ~ lossi
        ddt(wini) ~ tau1 * qda + tau2 * qdt + tau3 * w3
        work ~ wini
        Ebal ~ E + lossi - wini
    end
end
