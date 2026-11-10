@block PitchAutopilot begin
    # Pitch attitude control through the engine gimbal (thrust vector control). The command is
    # the elevation of the body x axis above the launch-site horizontal, `theta_cmd` in degrees
    # (the pitch program); the loop asks for the angular acceleration of a second-order system,
    #
    #     wdot_d = -wn^2 (theta_cmd - theta) - 2 zeta wn w_y          (theta-dot = -w_y)
    #
    # and turns it into a gimbal angle with the current inertia and thrust,
    #
    #     sin(delta) = clamp(J_y wdot_d / (l max(T, T_min)), -sin(delta_max), sin(delta_max)),
    #
    # because the gimbal moment is l T sin(delta) (`RocketEngine3D`). Without thrust (a coast
    # between two stages) the command saturates and nothing happens: there is no moment to give.
    @inputs begin
        theta_cmd::Real, [description = "Commanded elevation (deg)"]
        theta::Real, [unit = "rad", description = "Elevation of the body x axis"]
        V::Vec{6}, [description = "Body twist [w; v]"]
        J::Vec{3}, [unit = "kg*m^2", description = "Principal moments of inertia"]
        T::Real, [unit = "N", description = "Thrust"]
        l::Real, [unit = "m", description = "Centre of mass to gimbal"]
    end
    @parameters begin
        wn::Real = 1.5, [unit = "rad/s", min = 0, description = "Natural frequency of the attitude loop"]
        zeta::Real = 0.8, [min = 0, description = "Damping ratio of the attitude loop"]
        delta_max::Real = 6.0, [unit = "deg", min = 0, description = "Gimbal limit"]
        T_min::Real = 1000.0, [unit = "N", min = 1.0e-6, description = "Thrust floor (no division by zero in a coast)"]
    end
    @variables wdot_d::Real, [unit = "rad/s^2"]
    @outputs begin
        delta::Real, [unit = "rad"]
        delta_deg::Real
        err_deg::Real
    end
    @equations begin
        wdot_d ~ -wn * wn * (theta_cmd * pi / 180 - theta) - 2 * zeta * wn * V[2]
        delta ~ asin(clamp(J[2] * wdot_d / (l * max(T, T_min)), -sin(delta_max * deg), sin(delta_max * deg)))
        delta_deg ~ delta * 180 / pi
        err_deg ~ theta_cmd - theta * 180 / pi
    end
end
