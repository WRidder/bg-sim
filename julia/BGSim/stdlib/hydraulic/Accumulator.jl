@block Accumulator begin
    # Gas-charged (bladder or piston) accumulator, a nonlinear C element. The state is the
    # fluid volume V_f, the net flow in through a. The gas, precharged to p0 in the volume
    # V0, is compressed polytropically by the fluid:
    #   p_gas * V_gas^n = p0 * V0^n,   V_gas = V0 - V_f   (V_f >= 0).
    # Below the precharge pressure the accumulator is empty: the bladder seals the port, and
    # the pressure follows the fluid compressibility of the dead volume V_dead instead,
    #   p = p0 + beta*V_f/V_dead   (V_f < 0).
    # The switch between the two is smooth: V_f is split into its positive and negative
    # parts with sqrt(V_f^2 + eps^2), eps = p_tr*V_dead/beta, so the pressure is rounded
    # over about p_tr around p0 and there is no switching event.
    @ports a::Power{Hydraulic}
    @parameters begin
        p0::Real = 5.0e6, [unit = "Pa", min = 1.0e-12, description = "Gas precharge pressure"]
        V0::Real = 1.0e-3, [unit = "m^3", min = 1.0e-12, description = "Gas volume at the precharge pressure (the accumulator size)"]
        n::Real = 1.4, [unit = "1", min = 1.0, max = 1.67, description = "Polytropic index: 1 isothermal, 1.4 adiabatic (nitrogen)"]
        V_dead::Real = 1.0e-5, [unit = "m^3", min = 1.0e-12, description = "Fluid dead volume at the port when the accumulator is empty"]
        beta::Real = 1.4e9, [unit = "Pa", min = 1.0e-12, description = "Bulk modulus of the fluid in the dead volume"]
        p_tr::Real = 1.0e4, [unit = "Pa", min = 1.0e-12, description = "Pressure band over which the empty and charged laws blend"]
    end
    @variables begin
        V_f::Real = 0.0, [unit = "m^3", state = :prefer, description = "Fluid volume in the accumulator (negative: the dead volume is compressed below p0)"]
        V_gas::Real = 1.0e-3, [unit = "m^3", description = "Gas volume"]
        p_gas::Real = 5.0e6, [unit = "Pa", description = "Gas pressure"]
        p::Real = 5.0e6, [unit = "Pa", description = "Port pressure"]
    end
    @equations begin
        ddt(V_f) ~ a.f
        V_gas ~ V0 - 0.5 * (V_f + sqrt(V_f * V_f + (p_tr * V_dead / beta) * (p_tr * V_dead / beta)))
        p_gas ~ p0 * (V0 / V_gas)^n
        p ~ p_gas + beta / V_dead * 0.5 * (V_f - sqrt(V_f * V_f + (p_tr * V_dead / beta) * (p_tr * V_dead / beta)))
        a.e ~ p
    end
    @orientation a => :in
end
