@block Propeller begin
    # The fixed-pitch 75-inch propeller of the c172p (JSBSim's FGPropeller with the
    # prop_75in2f tables) as the crankshaft's load: an R on the rotational 1-junction whose
    # torque depends on the shaft speed (the port flow), the airspeed and the density. Its thrust
    # is the propeller's force on the airframe, applied at the hub through an
    # ExternalWrenchSpatial (the outputs tx .. fz: the thrust, its moment about the centre of
    # gravity and the aerodynamic torque -tau about the shaft, which the airframe does not get
    # from the crankshaft: the rotor's reaction there is the net torque tau_e - tau).
    #
    #   n = w / 2 pi,  J = u / (D sqrt(n^2 + n_floor^2)),  tip Mach M = sqrt((pi D n)^2 + u^2) / a
    #   thrust = CT(J) CT_M(M) rho n^2 D^4,   tau = CP(J) CP_M(M) rho n^2 D^5 / (2 pi)
    #   induced velocity vi = (-u + sgn(s) sqrt|s|) / 2,  s = u |u| + 2 thrust / (rho A)
    @constants begin
        NT::Int = 25
        NP::Int = 26
        NTM::Int = 2
        NPM::Int = 3
    end
    @ports p::Power{Rotation}
    @inputs begin
        u::Real, [unit = "m/s", description = "Axial airspeed (body x)"]
        rho::Real, [unit = "kg/m^3"]
        a::Real, [unit = "m/s", description = "Speed of sound"]
    end
    @outputs begin
        thrust::Real, [unit = "N"]
        torque::Real, [unit = "N*m"]
        vi::Real, [unit = "m/s", description = "Induced velocity (propwash: u + 2 vi)"]
        J::Real, [description = "Advance ratio"]
        tx::Real, [unit = "N*m"]
        ty::Real, [unit = "N*m"]
        tz::Real, [unit = "N*m"]
        fx::Real, [unit = "N"]
        fy::Real, [unit = "N"]
        fz::Real, [unit = "N"]
    end
    @parameters begin
        D::Real = 1.905, [unit = "m", description = "Diameter (75 in)"]
        ry::Real = 0.0, [unit = "m", description = "Hub from the CG, body y"]
        rz::Real = 0.0, [unit = "m", description = "Hub from the CG, body z"]
        n_floor::Real = 0.1, [unit = "1/s", min = 1.0e-9, description = "Rotation-rate floor of the advance ratio"]
        j_ct::Vec{NT} = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 5.0], [description = "Advance ratios of the thrust table"]
        ct_tab::Vec{NT} = [0.073, 0.073, 0.072, 0.071, 0.069, 0.066, 0.062, 0.055, 0.045, 0.034, 0.024, 0.013, -0.006, -0.013, -0.024, -0.034, -0.045, -0.055, -0.062, -0.066, -0.069, -0.071, -0.072, -0.073, -0.073], [description = "Thrust coefficient (prop_75in2f)"]
        j_cp::Vec{NP} = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.4, 5.0], [description = "Advance ratios of the power table"]
        cp_tab::Vec{NP} = [0.066, 0.07, 0.07, 0.066, 0.06, 0.053, 0.0501, 0.0469, 0.0426, 0.036, 0.0282, 0.0191, 0.0155, 0.0191, 0.0282, 0.036, 0.0426, 0.0469, 0.0501, 0.0516, 0.0525, 0.0525, 0.0522, 0.0511, 0.0504, 0.0493], [description = "Power coefficient (prop_75in2f)"]
        m_ct::Vec{NTM} = [0.85, 1.05], [description = "Tip Mach of the thrust factor"]
        f_ct::Vec{NTM} = [1.0, 0.8], [description = "Thrust factor"]
        m_cp::Vec{NPM} = [0.85, 1.05, 2.0], [description = "Tip Mach of the power factor"]
        f_cp::Vec{NPM} = [1.0, 1.8, 1.4], [description = "Power factor"]
    end
    @variables begin
        w::Real = 0.0, [unit = "rad/s"]
        n::Real = 0.0, [unit = "1/s"]
        mtip::Real = 0.0
        ct::Real = 0.0
        cp::Real = 0.0
        s::Real = 0.0, [unit = "m^2/s^2"]
    end
    @equations begin
        w ~ p.f
        n ~ w / 6.283185307179586
        J ~ u / (D * sqrt(n * n + n_floor * n_floor))
        mtip ~ sqrt((3.141592653589793 * D * n)^2 + u * u) / a
        ct ~ interp1(J, j_ct, ct_tab) * interp1(mtip, m_ct, f_ct)
        cp ~ interp1(J, j_cp, cp_tab) * interp1(mtip, m_cp, f_cp)
        thrust ~ ct * rho * n * n * D^4
        torque ~ cp * rho * n * n * D^5 / 6.283185307179586
        p.e ~ torque
        s ~ u * abs(u) + 2.0 * thrust / (rho * 0.7853981633974483 * D * D)
        vi ~ 0.5 * (-u + ifelse(s >= 0.0, sqrt(abs(s)), -sqrt(abs(s))))
        fx ~ thrust
        fy ~ 0.0
        fz ~ 0.0
        tx ~ -torque
        ty ~ rz * thrust
        tz ~ -ry * thrust
    end
    @causality p => :effort_out
end
