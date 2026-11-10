@block PropellantTank begin
    # The vehicle's mass budget: the mass falls with the engine's propellant flow, and the principal
    # moments of inertia follow the mass linearly between two published mass-properties points
    # (A at mass m_a, B at m_b; the Apollo 11 Mission Report gives them at descent-orbit insertion
    # and at landing, and at lift-off and orbit insertion for the ascent stage):
    #
    #     dm/dt = -mdot,        J_k(m) = J_b[k] + (J_a[k] - J_b[k]) (m - m_b) / (m_a - m_b)
    #
    # It is the "tank" part of the vehicle; the momentum law is in the bond graph
    # (`VariableInertia3D` and the outflow `MR`s), which reads its outputs: the MR resistances
    # r_lin = -dm/dt = mdot and r_ang_k = -dJ_k/dt = mdot dJ_k/dm (the leaving propellant takes its
    # momentum with it). `prop` is the usable propellant left, m - m_empty: the engine shuts down
    # when it reaches zero.
    @inputs mdot::Real, [unit = "kg/s", description = "Propellant flow of the engine"]
    @parameters begin
        m_a::Real = 15150.0, [unit = "kg", description = "Mass at mass-properties point A"]
        J_a::Vec{3} = [31834.0, 35221.0, 35076.0], [unit = "kg*m^2", description = "Principal moments at A (Ixx, Iyy, Izz)"]
        m_b::Real = 7327.0, [unit = "kg", description = "Mass at mass-properties point B"]
        J_b::Vec{3} = [17059.0, 18530.0, 21970.0], [unit = "kg*m^2", description = "Principal moments at B"]
        m_empty::Real = 7000.0, [unit = "kg", description = "Mass with no usable propellant left"]
    end
    @variables begin
        m_s::Real = 15150.0, [unit = "kg", state = :prefer, description = "Mass"]
        dJdm::Vec{3}, [unit = "m^2", description = "Slope of the inertia law"]
    end
    @outputs begin
        m::Real, [unit = "kg"]
        J::Vec{3}, [unit = "kg*m^2"]
        prop::Real, [unit = "kg", description = "Usable propellant left"]
        r_lin::Real, [unit = "kg/s"]
        r_ang1::Real, [unit = "kg*m^2/s"]
        r_ang2::Real, [unit = "kg*m^2/s"]
        r_ang3::Real, [unit = "kg*m^2/s"]
    end
    @equations begin
        ddt(m_s) ~ -mdot
        for k in 1:3
            dJdm[k] ~ (J_a[k] - J_b[k]) / (m_a - m_b)
            J[k] ~ J_b[k] + dJdm[k] * (m_s - m_b)
        end
        m ~ m_s
        prop ~ m_s - m_empty
        r_lin ~ mdot
        r_ang1 ~ mdot * dJdm[1]
        r_ang2 ~ mdot * dJdm[2]
        r_ang3 ~ mdot * dJdm[3]
    end
end
