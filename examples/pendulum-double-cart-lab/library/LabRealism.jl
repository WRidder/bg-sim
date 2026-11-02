@block LabRealism begin
    # The realism terms of design/realism.json that the bond graph does not have as elements (plan/RL_PLAN.md R1),
    # as the forces of design/lablib.py's twin (`LabPlant.actuator`, quadlib `Plant.extra_forces`), so that the
    # plant FMU `pendulum-double-cart-lab-plant` is the single truth of the RL environment:
    #   F    = alpha V (ripple_rel sin(ripple_per_rev th_m)) + cogging sin(cogging_per_rev th_m)
    #          - tc_rail tanh(v / eps_base) - k_cable_base x                 force on the cart (N, + along x)
    #   tau1 = -tc_joint1 tanh(w1 / eps_joint) - k_cable (q1 - pi/2)         joint 1 torque (N m, + along q1)
    #   tau2 = -tc_joint2 tanh(w2 / eps_joint)                               joint 2 torque (N m, + along q2)
    # with th_m = n x the motor angle, n = N_gear / r_pulley, alpha = k_t n / R_m the force per volt of the twin and
    # tc_rail = tc_carriage + n tc_motor the carriage and motor Coulomb friction seen at the cart. The cable spring
    # across joint 1 is neutral at the upright (q1 = pi/2). The viscous terms (joints, carriage, cable drag, motor
    # bearing) are bond-graph elements already. Written by design/rlmodels.py: do not edit by hand.
    @inputs begin
        V::Real, [unit = "V", description = "Motor terminal voltage"]
        x::Real, [unit = "m", description = "Cart position"]
        v::Real, [unit = "m/s", description = "Cart velocity"]
        q1::Real, [unit = "rad", description = "Joint 1 angle (link 1 from the rail's x axis)"]
        w1::Real, [unit = "rad/s", description = "Joint 1 rate"]
        w2::Real, [unit = "rad/s", description = "Joint 2 rate (link 2 relative to link 1)"]
    end
    @outputs begin
        F::Real, [unit = "N", description = "Force on the cart along x: ripple, cogging, Coulomb friction, cable spring"]
        tau1::Real, [unit = "N*m", description = "Joint 1 torque: Coulomb friction and the cable spring"]
        tau2::Real, [unit = "N*m", description = "Joint 2 torque: Coulomb friction"]
    end
    @parameters begin
        tc_joint1::Real = 0.0002, [unit = "N*m", min = 0, description = "Coulomb friction of joint 1"]
        tc_joint2::Real = 0.0002, [unit = "N*m", min = 0, description = "Coulomb friction of joint 2"]
        eps_joint::Real = 0.01, [unit = "rad/s", min = 1e-9, description = "Smoothing rate of the joint Coulomb friction"]
        tc_rail::Real = 1.375, [unit = "N", min = 0, description = "Carriage + motor Coulomb friction at the cart"]
        eps_base::Real = 0.005, [unit = "m/s", min = 1e-9, description = "Smoothing speed of the cart Coulomb friction"]
        k_cable::Real = 0.0001, [unit = "N*m/rad", min = 0, description = "Cable spring across joint 1 (neutral upright)"]
        k_cable_base::Real = 0.0, [unit = "N/m", min = 0, description = "Cable-chain spring on the cart (neutral at x = 0)"]
        alpha::Real = 3.775, [unit = "N/V", min = 0, description = "Force per volt k_t n / R_m"]
        n_motor::Real = 187.5, [unit = "rad/m", min = 0, description = "Motor angle per cart metre N_gear / r_pulley"]
        ripple_rel::Real = 0.02, [min = 0, description = "Commutation ripple, relative to the force"]
        ripple_per_rev::Real = 14.0, [description = "Ripple periods per motor revolution"]
        cogging::Real = 0.2, [unit = "N", min = 0, description = "Cogging force amplitude at the cart"]
        cogging_per_rev::Real = 14.0, [description = "Cogging periods per motor revolution"]
    end
    @equations begin
        F ~ alpha * V * ripple_rel * sin(ripple_per_rev * n_motor * x) + cogging * sin(cogging_per_rev * n_motor * x) - tc_rail * tanh(v / eps_base) - k_cable_base * x
        tau1 ~ -tc_joint1 * tanh(w1 / eps_joint) - k_cable * (q1 - 1.5707963267948966)
        tau2 ~ -tc_joint2 * tanh(w2 / eps_joint)
    end
end
