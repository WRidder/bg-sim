@block BeaverServo begin
    # Autopilot servo and control cable of one Beaver control surface: OUR FIT of the FDC
    # third-order actuator models (data/actmod35.dat, actmod45.dat, actmod55.dat). Those models
    # reach 63 % of a step in 0.08-0.11 s; their DC gain from the servo command (rad, 1 V = 1 deg)
    # to the surface deflection depends on the airspeed (the cable stretches under the hinge
    # moment). Here: a first-order lag tau with that DC gain, fitted as a quadratic in V through
    # the three FDC points (elevator 1.848/1.900/1.963, ailerons 1.662/1.429/1.196, rudder
    # 0.784/0.661/0.582 at 35/45/55 m/s):
    #
    #   tau dy/dt = (k2 V^2 + k1 V + k0) u - y
    @inputs begin
        u::Real, [description = "Servo command (1 V = 1 deg)"]
        V::Real, [description = "True airspeed"]
    end
    @outputs y::Real, [description = "Surface deflection added by the autopilot"]
    @parameters begin
        k2::Real = 0.0, [description = "DC gain, V^2 coefficient (s^2/m^2)"]
        k1::Real = 0.0, [description = "DC gain, V coefficient (s/m)"]
        k0::Real = 1.0, [description = "DC gain, constant"]
        tau::Real = 0.09, [min = 1.0e-4, description = "Time constant"]
    end
    @variables x::Real = 0.0, [state = :prefer, unit = "rad", description = "Deflection"]
    @equations begin
        ddt(x) ~ ((k2 * V * V + k1 * V + k0) * u - x) / tau
        y ~ x
    end
end
