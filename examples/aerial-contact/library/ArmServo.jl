@block ArmServo begin
    # Position servo of the manipulator (Dynamixel MX-106R class): a PD law on the joint angle with a
    # smooth torque limit,
    #
    #   tau = tau_max tanh( (Kp (q_sp - q) - Kd q') / tau_max ),     q_sp = -mu_sp
    #
    # The joint `Revolute3D` turns about the body y axis (its z axis is mounted on y_b), so the
    # servo angle is q = -mu where mu is the elevation of the arm above the body x axis (design.py).
    # `tau` is the torque on the arm; the joint puts the reaction on the airframe. Continuous and
    # smooth (tanh), so the saturation creates no solver events.
    @inputs begin
        mu_sp::Real
        q::Real
        qd::Real
    end
    @outputs begin
        tau::Real, [unit = "N*m"]
        mu::Real, [unit = "rad"]
    end
    @parameters begin
        Kp::Real = 139.4, [unit = "N*m/rad", min = 0, description = "Position gain"]
        Kd::Real = 5.58, [unit = "N*m*s/rad", min = 0, description = "Rate gain"]
        tau_max::Real = 8.4, [unit = "N*m", min = 1.0e-6, description = "Stall torque"]
    end
    @equations begin
        tau ~ tau_max * tanh((Kp * (-mu_sp - q) - Kd * qd) / tau_max)
        mu ~ -q
    end
end
