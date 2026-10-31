@block Pipe begin
    # Lumped hydraulic line of length L and inner diameter d, cut into N segments (a
    # structural constant). Each segment has the fluid compliance V/(N*beta) (V = A*L,
    # A = pi*d^2/4) at its centre, and the fluid inertance I = rho*L/A and the friction
    # resistance between the centres; the half segments at both ends join the ports. So
    # there are N chamber pressures p[i] and N + 1 flows: qa from a into chamber 1, q[i]
    # from chamber i to i + 1, and q[N] from chamber N out through b. The pressure drop of a
    # whole line at the flow q is
    #   dp = R_lam*q + K_t*q*sqrt(q^2 + q_eps^2),
    #   R_lam = 128*rho*nu*L/(pi*d^4)       (laminar, Hagen-Poiseuille),
    #   K_t   = f_t*(L/d)*rho/(2*A^2)       (turbulent, Darcy-Weisbach with factor f_t),
    # with q_eps = nu*A/d (the flow at Reynolds number 1) only rounding |q| at zero flow.
    # f_t = 0 (the default) is a purely laminar line. Both ports are inertial (flow) ends:
    # they take a pressure, so connect them to a volume, accumulator, cylinder chamber,
    # valve, orifice or pressure source, not straight to a pump or flow source.
    @constants N::Int = 1, [min = 1, description = "Number of segments"]
    @ports begin
        a::Power{Hydraulic}
        b::Power{Hydraulic}
    end
    @parameters begin
        L::Real = 1.0, [unit = "m", min = 1.0e-12, description = "Line length"]
        d::Real = 0.01, [unit = "m", min = 1.0e-12, description = "Inner diameter"]
        rho::Real = 850.0, [unit = "kg/m^3", min = 1.0e-12, description = "Fluid density"]
        nu::Real = 3.2e-5, [unit = "m^2/s", min = 1.0e-12, description = "Kinematic viscosity"]
        beta::Real = 1.4e9, [unit = "Pa", min = 1.0e-12, description = "Effective bulk modulus (fluid and wall)"]
        f_t::Real = 0.0, [unit = "1", min = 0, description = "Turbulent Darcy friction factor (0: laminar only)"]
    end
    @variables begin
        qa::Real = 0.0, [unit = "m^3/s", state = :prefer, description = "Flow from a into the first chamber"]
        q::Vec{N}, [unit = "m^3/s", state = :prefer, description = "Flow out of each chamber towards b (q[N] leaves through b)"]
        p::Vec{N}, [unit = "Pa", state = :prefer, description = "Chamber pressure of each segment"]
    end
    @equations begin
        # Half segment from a to chamber 1: inertance I/(2N), resistance R/(2N).
        ddt(qa) ~ (a.e - p[1] - (128.0 * rho * nu * L / (3.141592653589793 * d^4) * qa +
                                 f_t * (L / d) * rho / (2.0 * (3.141592653589793 * d * d / 4.0)^2) *
                                 qa * sqrt(qa * qa + (nu * 3.141592653589793 * d / 4.0)^2)) / (2 * N)) /
                  (rho * L / (3.141592653589793 * d * d / 4.0) / (2 * N))
        # Full segments between the chambers.
        for i in 1:N-1
            ddt(q[i]) ~ (p[i] - p[i + 1] - (128.0 * rho * nu * L / (3.141592653589793 * d^4) * q[i] +
                                             f_t * (L / d) * rho / (2.0 * (3.141592653589793 * d * d / 4.0)^2) *
                                             q[i] * sqrt(q[i] * q[i] + (nu * 3.141592653589793 * d / 4.0)^2)) / N) /
                        (rho * L / (3.141592653589793 * d * d / 4.0) / N)
        end
        # Half segment from chamber N to b.
        ddt(q[N]) ~ (p[N] - b.e - (128.0 * rho * nu * L / (3.141592653589793 * d^4) * q[N] +
                                   f_t * (L / d) * rho / (2.0 * (3.141592653589793 * d * d / 4.0)^2) *
                                   q[N] * sqrt(q[N] * q[N] + (nu * 3.141592653589793 * d / 4.0)^2)) / (2 * N)) /
                    (rho * L / (3.141592653589793 * d * d / 4.0) / (2 * N))
        # Chamber compliance V/(N*beta).
        ddt(p[1]) ~ beta * (qa - q[1]) / (3.141592653589793 * d * d / 4.0 * L / N)
        for i in 2:N
            ddt(p[i]) ~ beta * (q[i - 1] - q[i]) / (3.141592653589793 * d * d / 4.0 * L / N)
        end
        a.f ~ qa
        b.f ~ -q[N]
    end
end
