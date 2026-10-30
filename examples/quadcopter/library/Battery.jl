@block Battery begin
    # LiPo pack: linear open-circuit voltage over the state of charge and a series resistance.
    # The ESCs are lossless buck converters, so the pack delivers the total electrical power of
    # the motors, P = sum(u_k i_k) (the `P_el` taps of the `ElectricDrive`s). With the terminal
    # voltage V = Voc(soc) - R_int I and I = P / V the terminal voltage is explicit:
    #
    #   V = (Voc + sqrt(Voc^2 - 4 R_int P)) / 2
    #
    # `V` is what the ESCs see as their supply (voltage limit), `I` the pack current.
    @constants N::Int = 4
    @inputs P::Vec{N}
    @outputs begin
        V::Real, [unit = "V", description = "Terminal voltage seen by the ESCs"]
        I::Real, [unit = "A", description = "Discharge current"]
        soc::Real, [description = "State of charge, 1 = full"]
    end
    @parameters begin
        V_full::Real = 12.6, [unit = "V", description = "Open-circuit voltage when full (3S)"]
        V_empty::Real = 9.9, [unit = "V", description = "Open-circuit voltage when empty (3S)"]
        R_int::Real = 0.02, [unit = "Ohm", min = 0, description = "Pack series resistance"]
        capacity::Real = 10800.0, [unit = "A*s", min = 1.0, description = "Charge capacity (3 Ah = 10800 C)"]
        onev::Vec{N} = [1.0, 1.0, 1.0, 1.0], [description = "Summation vector"]
    end
    @variables begin
        q::Real = 1.0, [state = :prefer, description = "State of charge"]
        Voc::Real = 12.6, [unit = "V", description = "Open-circuit voltage"]
        Pt::Real = 0.0, [unit = "W", description = "Total electrical power"]
    end
    @equations begin
        Voc ~ V_empty + (V_full - V_empty) * q
        Pt ~ dot(P, onev)
        V ~ 0.5 * (Voc + sqrt(Voc * Voc - 4.0 * R_int * Pt))
        I ~ Pt / V
        ddt(q) ~ -I / capacity
        soc ~ q
    end
end
