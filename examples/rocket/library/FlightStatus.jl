@block FlightStatus begin
    # Readouts of the propulsion (a tap: no physics).
    #
    #   acc    sensed (non-gravitational) acceleration |F_thrust + F_drag| / m, what an
    #          accelerometer on the vehicle reads (the AS-506 report's "total inertial acceleration")
    #   acc_g  the same in g (9.80665 m/s^2)
    #   dv     the ideal velocity gain integral T / m dt. In vacuum (no ambient pressure, no drag,
    #          no gravity) and between jettisons it is Tsiolkovsky's c ln(m0 / m).
    #   tw     thrust-to-weight ratio T / (m g0)
    @inputs begin
        m::Real, [unit = "kg"]
        T::Real, [unit = "N"]
        fex::Real, [unit = "N", description = "Engine force x, body axes"]
        fez::Real, [unit = "N", description = "Engine force z, body axes"]
        fax::Real, [unit = "N", description = "Aerodynamic force x, body axes"]
        fay::Real, [unit = "N", description = "Aerodynamic force y, body axes"]
        faz::Real, [unit = "N", description = "Aerodynamic force z, body axes"]
    end
    @parameters g0::Real = 9.80665, [unit = "m/s^2", description = "Standard gravity"]
    @variables dv_s::Real = 0.0, [unit = "m/s", state = :prefer, description = "Integral of T/m"]
    @outputs begin
        acc::Real, [unit = "m/s^2"]
        acc_g::Real
        dv::Real, [unit = "m/s"]
        tw::Real
    end
    @equations begin
        acc ~ sqrt((fex + fax) * (fex + fax) + fay * fay + (fez + faz) * (fez + faz)) / m
        acc_g ~ acc / g0
        ddt(dv_s) ~ T / m
        dv ~ dv_s
        tw ~ T / (m * g0)
    end
end
