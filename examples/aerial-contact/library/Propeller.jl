@block Propeller begin
    # Fixed-pitch propeller as a one-port load on a rotation bond: the standard quadratic
    # aerodynamic laws
    #
    #   thrust   T = kT w |w|       (N, along the rotor axis)
    #   drag     Q = kQ w |w|       (N m, opposing the rotation; the load torque of the shaft)
    #
    # The port is power-positive into the block, so `shaft.e = Q` is the torque the motor has to
    # supply (a quadratic rotational damper) and the dissipated power is `Q w`. `w |w|` is
    # smoothed by `eps` (rad/s) so that the law has no zero-crossing event at standstill.
    # The thrust is a signal output: the airframe wrench is assembled by `RotorWrench`.
    @ports shaft::Power{Rotation}
    @outputs begin
        T::Real, [unit = "N", description = "Thrust along the rotor axis"]
        Q::Real, [unit = "N*m", description = "Aerodynamic drag torque on the rotor"]
    end
    @parameters begin
        kT::Real = 1.42e-5, [min = 0, description = "Thrust coefficient, T = kT w^2 (N s^2/rad^2)"]
        kQ::Real = 2.03e-7, [min = 0, description = "Drag torque coefficient, Q = kQ w^2 (N m s^2/rad^2)"]
        eps::Real = 1.0, [unit = "rad/s", min = 1.0e-9, description = "Smoothing speed of w |w|"]
    end
    @variables a::Real = 0.0, [description = "Smooth w |w|"]
    @equations begin
        a ~ shaft.f * sqrt(shaft.f * shaft.f + eps * eps)
        shaft.e ~ kQ * a
        Q ~ kQ * a
        T ~ kT * a
    end
    @causality shaft => (:effort_out, :fixed)
end
