@block PowerAmplifier begin
    # Linear power amplifier (a servo amplifier or an averaged H-bridge on an ideal supply):
    # a signal-controlled voltage source between p and n with a saturated command, an output
    # resistance and an optional current limit,
    #   p.e - n.e = clamp(gain*u, -V_max, V_max) - R_out*i - R_limit*deadzone(i, I_max)
    # with i = -p.f the current the amplifier drives out of p, through the load and back
    # into n. The current limit is a fold-back: above |i| = I_max the output voltage drops by
    # R_limit per ampere of excess current, a steep but finite slope, so the amplifier stays
    # a voltage source for an inductive load (a motor winding) and never imposes a current.
    # The default I_max = 1e12 A is no limit. Power comes from an ideal supply; use HBridge
    # to draw it from an electrical DC bus.
    @ports begin
        p::Power{Electrical}
        n::Power{Electrical}
    end
    @inputs u::Real, [description = "Command; the output voltage is gain*u before the limits"]
    @outputs begin
        i::Real, [unit = "A", description = "Output current, out of p into the load"]
        v::Real, [unit = "V", description = "Output voltage p.e - n.e"]
    end
    @parameters begin
        gain::Real = 1.0, [unit = "V", description = "Output voltage per unit of command"]
        V_max::Real = 24.0, [unit = "V", min = 0, description = "Supply limit: the commanded voltage is clamped to -V_max..V_max"]
        R_out::Real = 0.0, [unit = "Ohm", min = 0, description = "Output (internal) resistance"]
        I_max::Real = 1.0e12, [unit = "A", min = 0, description = "Current limit; the default 1e12 A is no limit"]
        R_limit::Real = 100.0, [unit = "Ohm", min = 0, description = "Fold-back slope of the current limit: volts lost per ampere above I_max"]
    end
    @variables v_cmd::Real = 0.0, [unit = "V", description = "Commanded voltage after the supply limit"]
    @equations begin
        p.f + n.f ~ 0.0
        i ~ -p.f
        v ~ p.e - n.e
        v_cmd ~ clamp(gain * u, -V_max, V_max)
        v ~ v_cmd - R_out * i - R_limit * deadzone(i, I_max)
    end
end
