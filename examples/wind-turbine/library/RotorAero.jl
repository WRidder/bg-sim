@block RotorAero begin
    # The rotor's aerodynamics as two modulated sources (signal only): from the rotor speed, the
    # wind seen by the moving nacelle and the collective pitch it gives the tip-speed ratio and the
    # pitch in degrees for the Cp and Ct tables (two stdlib Lookup2D blocks), and from the table
    # values the aerodynamic torque on the rotor and the thrust on the tower top:
    #
    #   v_rel = v - xdot                      (the nacelle's fore-aft velocity: aerodynamic damping)
    #   lambda = Omega R / v_rel
    #   P = 1/2 rho pi R^2 Cp(lambda, beta) v_rel^3,   Ta = P / Omega
    #   T = 1/2 rho pi R^2 Ct(lambda, beta) v_rel^2
    #
    # v_rel is floored at v_min and Omega at w_min, so the law stays finite at standstill (no run
    # gets near either floor). Ta drives an MSe on the rotor's 1-junction, T an MSe on the
    # tower's.
    @inputs begin
        v::Real, [unit = "m/s", description = "Hub-height wind speed"]
        w::Real, [unit = "rad/s", description = "Rotor speed (low-speed shaft)"]
        xdot::Real, [unit = "m/s", description = "Tower-top fore-aft velocity (downwind positive)"]
        beta::Real, [unit = "rad", description = "Collective blade pitch"]
        cp::Real, [description = "Power coefficient Cp(lambda, beta)"]
        ct::Real, [description = "Thrust coefficient Ct(lambda, beta)"]
    end
    @outputs begin
        lambda::Real, [description = "Tip-speed ratio"]
        beta_deg::Real, [description = "Pitch in degrees (the tables' second axis)"]
        torque::Real, [unit = "N*m", description = "Aerodynamic torque on the rotor"]
        thrust::Real, [unit = "N", description = "Rotor thrust on the tower top"]
        power::Real, [unit = "W", description = "Aerodynamic power"]
        v_rel::Real, [unit = "m/s", description = "Wind relative to the nacelle"]
    end
    @parameters begin
        R::Real = 63.0, [unit = "m", min = 0, description = "Rotor radius"]
        rho::Real = 1.225, [unit = "kg/m^3", min = 0, description = "Air density"]
        v_min::Real = 0.5, [unit = "m/s", min = 1.0e-6, description = "Floor of the relative wind"]
        w_min::Real = 0.05, [unit = "rad/s", min = 1.0e-6, description = "Floor of the rotor speed in Ta = P / Omega"]
    end
    @variables begin
        vr::Real = 10.0, [unit = "m/s"]
        q::Real = 0.0, [unit = "N", description = "1/2 rho pi R^2 v_rel^2"]
    end
    @equations begin
        v_rel ~ v - xdot
        vr ~ max(v_rel, v_min)
        lambda ~ w * R / vr
        beta_deg ~ beta * 57.29577951308232
        q ~ 0.5 * rho * 3.141592653589793 * R * R * vr * vr
        power ~ q * vr * cp
        torque ~ power / max(w, w_min)
        thrust ~ q * ct
    end
end
