@block TunnelDiode begin
    # Tunnel diode biased in the middle of its negative-resistance region, as a nonlinear R in
    # conductance causality (the tank capacitor sets the voltage, the diode answers with a
    # current). Small-signal (AC) model about the bias point (V0, I0): v = p.e is the voltage
    # deviation, p.f the current deviation, and the static curve is fitted by the cubic
    #   i = -a v + b v^3,
    # whose maximum and minimum sit at the peak and the valley of the real diode when
    # a = 3 (I_p - I_v) / (2 (V_v - V_p)) and b = a / (3 A^2), A = (V_v - V_p)/2.
    # P = v i is the power the diode absorbs: negative (it supplies energy, taken from the bias
    # source) for |v| < sqrt(a/b), positive (it dissipates) beyond.
    @ports p::Power{Generic}
    @parameters begin
        a::Real = 0.0212, [unit = "flow/effort", min = 0, description = "Negative differential conductance at the bias point (A/V)"]
        b::Real = 0.336, [min = 0, description = "Cubic coefficient of i = -a v + b v^3 (A/V^3)"]
    end
    @outputs begin
        i::Real, [description = "Diode current deviation from the bias current"]
        P::Real, [description = "Power absorbed by the diode, v*i (negative: supplied to the tank)"]
    end
    @equations begin
        p.f ~ -a * p.e + b * p.e^3
        i ~ p.f
        P ~ p.e * p.f
    end
    @causality p => :flow_out
end
