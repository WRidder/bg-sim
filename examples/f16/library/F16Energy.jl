@block F16Energy begin
    # Total mechanical energy of the airframe: rotational and translational kinetic energy of the
    # rigid body (principal axes, so 1/2 sum J_k w_k^2) plus the potential energy m g0 h.
    # dE/dt equals the power of the aerodynamic forces, the thrust and the aerodynamic moments
    # (`F16Forces.P_ext`); gravity is inside E, and the engine's gyroscopic torque does no work.
    @inputs begin
        gP::Vec{7}, [description = "Pose of the principal frame"]
        VP::Vec{6}, [description = "Twist of the principal frame [w; v]"]
    end
    @outputs begin
        E::Real, [unit = "J", description = "Total energy"]
        Ekin::Real, [unit = "J", description = "Kinetic energy"]
        Epot::Real, [unit = "J", description = "Potential energy m g0 h"]
    end
    @parameters begin
        J::Vec{3} = [1.0, 1.0, 1.0], [description = "Principal moments of inertia (kg m^2)"]
        m::Real = 1.0, [description = "Mass (kg)"]
        g0::Real = 9.81, [description = "Gravity (m/s^2)"]
    end
    @equations begin
        Ekin ~ 0.5 * (J[1] * VP[1] * VP[1] + J[2] * VP[2] * VP[2] + J[3] * VP[3] * VP[3]) +
               0.5 * m * (VP[4] * VP[4] + VP[5] * VP[5] + VP[6] * VP[6])
        Epot ~ m * g0 * gP[7]
        E ~ Ekin + Epot
    end
end
