@block SoilCutting2D begin
    # Soil-tool interaction at the bucket teeth, as a nonlinear resistive element on the
    # bucket's planar bond, plus the bucket fill and the weight of the soil it carries.
    #
    # Cutting resistance: the fundamental earthmoving equation (Reece 1964, in McKyes' form,
    # "Soil Cutting and Tillage", 1985) for a tool of width w at the cutting depth d,
    #   F_fee = w (gamma d^2 N_gamma + c d N_c)
    # with constant factors N_gamma, N_c (computed in design/design.py for the nominal rake
    # angle by minimising N_gamma over the failure angle), plus the momentum flux of the
    # soil that the tool accelerates to its own speed, rho_s w d |v|^2. The force acts
    # against the tooth velocity v (world frame):
    #   F = -(F_fee + rho_s w d |v|^2) v / sqrt(|v|^2 + v_eps^2)
    # d is the smooth positive part of y_s - y_tip (rounded over d_eps), so the force is
    # continuous when the teeth enter and leave the soil and there is no event.
    #
    # Fill: the bucket takes the swept volume w d |v| (bank volume, times the swell factor
    # to loose volume) until it is full (V_max, heaped), and spills with the time constant
    # tau_dump once its mouth faces down (cos(theta) > c_dump, theta the bucket angle):
    #   dV/dt = swell w d |v| (1 - V/V_max) - V/tau_dump * (1 + tanh((cos(theta) - c_dump)/0.1))/2
    # The soil in the bucket weighs m_s = rho_s V/swell; its weight acts at (rsx, rsy) in the
    # bucket frame (its inertia is not modelled).
    #
    # Port and sign (as `DeckContact2D`): the bucket body's junction bonds into this port. The
    # port flow is the bucket twist (omega, vx, vy) in the body frame, `g` the bucket's
    # centre-of-mass pose (theta, x, y), and the port effort is minus the wrench of the
    # cutting force and the soil weight on the body, so the port power is the power the soil
    # absorbs (cutting) minus the work of the carried soil's weight.
    @ports p::Power{Planar}, [frame = "body"]
    @inputs g::Vec{3}, [description = "Bucket centre-of-mass pose (theta, x, y)"]
    @parameters begin
        rtx::Real = 1.0, [unit = "m", description = "Tooth tip x in the bucket body frame"]
        rty::Real = 0.0, [unit = "m", description = "Tooth tip y in the bucket body frame"]
        rsx::Real = 0.2, [unit = "m", description = "Centre of the carried soil, x in the bucket body frame"]
        rsy::Real = 0.0, [unit = "m", description = "Centre of the carried soil, y in the bucket body frame"]
        y_s::Real = -2.0, [unit = "m", description = "Height of the soil surface"]
        w::Real = 1.2, [unit = "m", min = 0, description = "Cutting width (bucket width)"]
        gamma::Real = 1.8e4, [unit = "N/m^3", min = 0, description = "Unit weight of the soil (bank)"]
        c::Real = 1.0e4, [unit = "Pa", min = 0, description = "Cohesion"]
        N_g::Real = 2.0, [unit = "1", min = 0, description = "Weight factor N_gamma of the earthmoving equation"]
        N_c::Real = 2.5, [unit = "1", min = 0, description = "Cohesion factor N_c of the earthmoving equation"]
        rho_s::Real = 1835.0, [unit = "kg/m^3", min = 0, description = "Bank density of the soil"]
        swell::Real = 1.25, [unit = "1", min = 1.0e-3, description = "Swell factor: loose volume per bank volume"]
        V_max::Real = 0.93, [unit = "m^3", min = 1.0e-6, description = "Heaped bucket capacity (loose)"]
        tau_dump::Real = 0.6, [unit = "s", min = 1.0e-6, description = "Spill time constant when the mouth faces down"]
        c_dump::Real = 0.3, [unit = "1", description = "Spill when cos(bucket angle) exceeds it"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration"]
        v_eps::Real = 0.02, [unit = "m/s", min = 1.0e-9, description = "Speed below which the force fades in linearly"]
        d_eps::Real = 0.01, [unit = "m", min = 1.0e-9, description = "Rounding of the depth at the surface"]
    end
    @variables begin
        V::Real = 0.0, [unit = "m^3", state = :prefer, description = "Loose soil volume in the bucket"]
        ct::Real = 1.0, [unit = "1", description = "cos(theta)"]
        st::Real = 0.0, [unit = "1", description = "sin(theta)"]
        vx::Real = 0.0, [unit = "m/s", description = "Tooth velocity x (world)"]
        vy::Real = 0.0, [unit = "m/s", description = "Tooth velocity y (world)"]
        v2::Real = 0.0, [unit = "m^2/s^2", description = "Squared tooth speed"]
        dd::Real = 0.0, [unit = "m", description = "Signed depth of the teeth below the surface"]
        F::Real = 0.0, [unit = "N", description = "Cutting force magnitude"]
        Fx::Real = 0.0, [unit = "N", description = "Cutting force on the teeth, x (world)"]
        Fy::Real = 0.0, [unit = "N", description = "Cutting force on the teeth, y (world)"]
        Wy::Real = 0.0, [unit = "N", description = "Weight of the carried soil, y (world)"]
        fbx::Real = 0.0, [unit = "N", description = "Cutting force in the body frame, x"]
        fby::Real = 0.0, [unit = "N", description = "Cutting force in the body frame, y"]
        wbx::Real = 0.0, [unit = "N", description = "Soil weight in the body frame, x"]
        wby::Real = 0.0, [unit = "N", description = "Soil weight in the body frame, y"]
    end
    @outputs begin
        depth::Real, [unit = "m"]
        Fcut::Real, [unit = "N"]
        P_cut::Real, [unit = "W"]
        fillr::Real, [unit = "1"]
        m_soil::Real, [unit = "kg"]
        tip::Vec{2}, [unit = "m"]
    end
    @equations begin
        ct ~ cos(g[1])
        st ~ sin(g[1])
        tip[1] ~ g[2] + ct * rtx - st * rty
        tip[2] ~ g[3] + st * rtx + ct * rty
        vx ~ ct * (p.f[2] - p.f[1] * rty) - st * (p.f[3] + p.f[1] * rtx)
        vy ~ st * (p.f[2] - p.f[1] * rty) + ct * (p.f[3] + p.f[1] * rtx)
        v2 ~ vx * vx + vy * vy
        dd ~ y_s - tip[2]
        depth ~ 0.5 * (dd + sqrt(dd * dd + d_eps * d_eps))
        F ~ w * (gamma * depth * depth * N_g + c * depth * N_c + rho_s * depth * v2)
        Fx ~ -F * vx / sqrt(v2 + v_eps * v_eps)
        Fy ~ -F * vy / sqrt(v2 + v_eps * v_eps)
        Fcut ~ F * sqrt(v2) / sqrt(v2 + v_eps * v_eps)
        P_cut ~ -(Fx * vx + Fy * vy)
        ddt(V) ~ swell * w * depth * sqrt(v2 + 1.0e-8) * (1.0 - V / V_max) -
                 V / tau_dump * 0.5 * (1.0 + tanh((ct - c_dump) / 0.1))
        fillr ~ V / V_max
        m_soil ~ rho_s * V / swell
        Wy ~ -m_soil * g0
        fbx ~ ct * Fx + st * Fy
        fby ~ -st * Fx + ct * Fy
        wbx ~ st * Wy
        wby ~ ct * Wy
        p.e[1] ~ -(rtx * fby - rty * fbx + rsx * wby - rsy * wbx)
        p.e[2] ~ -(fbx + wbx)
        p.e[3] ~ -(fby + wby)
    end
    @orientation p => :in
end
