@block MissileMotor begin
    # The Mk. 36 solid rocket motor with its propellant budget and its two-axis thrust-vector
    # control, as a wrench (for an `ExternalWrenchSpatial`) plus the mass and inertia signals
    # of the modulated inertia and the outflow `MR` elements.
    #
    #   mdot(t)   the boost profile: 0 before ignition, a 0.05 s rise, a plateau, a 0.15 s
    #             tail-off; it stops when the dry mass is reached
    #   T         max(mdot c_vac - p_a A_e, 0): the vacuum thrust minus the ambient pressure
    #             on the nozzle exit
    #   m, J      the propellant leaves the body, so the mass and the principal inertias fall
    #             linearly with the burned fraction; `r_lin = mdot` and `r_ang = -dJ/dt` are
    #             the resistances of the outflow MRs on the body's 1-junction
    #   TVC       the nozzle swivels by `tvc_p` about body y and `tvc_y` about body z at
    #             `l_eng` behind the centre of mass: F = T (1, sin tvc_y, -sin tvc_p) in FLU,
    #             so a positive `tvc_p` pushes the tail down and pitches the nose up.
    #
    # The exhaust leaves at the body's own velocity, so the linear momentum law is m dv/dt = F
    # and the inertia change does not add a spurious acceleration (README, "Variable mass").
    @inputs begin
        pa::Real, [unit = "Pa", description = "Ambient static pressure"]
        tvc_p::Real, [unit = "rad", description = "Nozzle gimbal about body y (positive pitches up)"]
        tvc_y::Real, [unit = "rad", description = "Nozzle gimbal about body z (positive pushes left)"]
    end
    @parameters begin
        m0::Real = 85.3, [unit = "kg", min = 1.0e-6, description = "Launch mass"]
        m_dry::Real = 64.3, [unit = "kg", min = 1.0e-6, description = "Mass after the motor"]
        j0::Vec{3} = [0.80, 55.0, 55.0], [unit = "kg*m^2", description = "Launch principal inertias"]
        j_dry::Vec{3} = [0.55, 42.0, 42.0], [unit = "kg*m^2", description = "Burnout principal inertias"]
        mdot0::Real = 8.75, [unit = "kg/s", min = 0, description = "Plateau propellant flow"]
        c_vac::Real = 2304.6, [unit = "m/s", min = 0, description = "Vacuum effective exhaust velocity"]
        ae::Real = 0.0060, [unit = "m^2", min = 0, description = "Nozzle exit area"]
        t_ign::Real = 0.10, [unit = "s", min = 0, description = "Ignition time"]
        t_burn::Real = 2.40, [unit = "s", min = 0, description = "Boost duration"]
        tau_ign::Real = 0.05, [unit = "s", min = 1.0e-6, description = "Ignition ramp"]
        tau_tail::Real = 0.15, [unit = "s", min = 1.0e-6, description = "Tail-off ramp"]
        l_eng::Real = 1.30, [unit = "m", min = 0, description = "Centre of mass to the nozzle gimbal"]
    end
    @variables begin
        ms::Real = 85.3, [unit = "kg", state = :prefer, description = "Current mass"]
        mdot_raw::Real = 0.0, [unit = "kg/s"]
        gate::Real = 0.0, [description = "Flow gate: 1 while propellant remains"]
        frac::Real = 1.0, [description = "Burned mass fraction"]
        fy::Real = 0.0, [unit = "N", description = "Thrust force, body y (left)"]
        fz::Real = 0.0, [unit = "N", description = "Thrust force, body z (up)"]
    end
    @outputs begin
        m::Real, [unit = "kg"]
        J::Vec{3}, [unit = "kg*m^2"]
        mdot::Real, [unit = "kg/s"]
        T::Real, [unit = "N"]
        r_lin::Real, [unit = "kg/s"]
        r_ang1::Real, [unit = "kg*m^2/s"]
        r_ang2::Real, [unit = "kg*m^2/s"]
        r_ang3::Real, [unit = "kg*m^2/s"]
        tx::Real, [unit = "N*m"]
        ty::Real, [unit = "N*m"]
        tz::Real, [unit = "N*m"]
        fx::Real, [unit = "N"]
        fy_out::Real, [unit = "N"]
        fz_out::Real, [unit = "N"]
        t_tvc_p::Real, [unit = "rad"]
        t_tvc_y::Real, [unit = "rad"]
        ignited::Real
    end
    @equations begin
        mdot_raw ~ mdot0 * clamp((t - t_ign) / tau_ign, 0.0, 1.0) *
                   clamp((t_ign + t_burn - t) / tau_tail, 0.0, 1.0)
        gate ~ clamp((ms - m_dry) / 0.02, 0.0, 1.0)
        mdot ~ mdot_raw * gate
        ddt(ms) ~ -mdot
        frac ~ clamp((ms - m_dry) / max(m0 - m_dry, 1.0e-9), 0.0, 1.0)
        m ~ ms
        J[1] ~ j_dry[1] + frac * (j0[1] - j_dry[1])
        J[2] ~ j_dry[2] + frac * (j0[2] - j_dry[2])
        J[3] ~ j_dry[3] + frac * (j0[3] - j_dry[3])
        r_lin ~ mdot
        r_ang1 ~ mdot * (j0[1] - j_dry[1]) / max(m0 - m_dry, 1.0e-9)
        r_ang2 ~ mdot * (j0[2] - j_dry[2]) / max(m0 - m_dry, 1.0e-9)
        r_ang3 ~ mdot * (j0[3] - j_dry[3]) / max(m0 - m_dry, 1.0e-9)
        T ~ max(mdot * c_vac - pa * ae * clamp(mdot / max(mdot0, 1.0e-9), 0.0, 1.0), 0.0)
        fy ~ T * sin(tvc_y)
        fz ~ -T * sin(tvc_p)
        fx ~ T
        fy_out ~ fy
        fz_out ~ fz
        tx ~ 0.0
        ty ~ l_eng * fz
        tz ~ -l_eng * fy
        t_tvc_p ~ tvc_p
        t_tvc_y ~ tvc_y
        ignited ~ clamp((t - t_ign) / tau_ign, 0.0, 1.0) * gate
    end
end
