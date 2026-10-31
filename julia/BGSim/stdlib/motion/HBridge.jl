@block HBridge begin
    # Averaged H-bridge (four-quadrant chopper) between a DC bus (dc_p, dc_n) and a load
    # (out_p, out_n): the duty input d = clamp(duty, -1, 1) scales the bus voltage onto the
    # output and the output current back onto the bus, a power-conserving modulated
    # transformer with conduction losses,
    #   out_p.e - out_n.e = d*(dc_p.e - dc_n.e) - R_on*i - R_limit*deadzone(i, I_max)
    #   i_dc = d*i
    # with i = -out_p.f the current driven out of out_p through the load and i_dc = dc_p.f
    # the current drawn from the bus. The output voltage can never exceed the bus voltage,
    # the supply limit of a real bridge. R_on is the resistance of the conducting path (two
    # switches in series); the current limit is the fold-back of PowerAmplifier (default:
    # none). Fed with a PWM output of low = -1 and high = 1, the bridge switches the full
    # bus voltage (bipolar switching); fed with PWMAverage or any duty signal, it is the
    # averaged model.
    @ports begin
        dc_p::Power{Electrical}
        dc_n::Power{Electrical}
        out_p::Power{Electrical}
        out_n::Power{Electrical}
    end
    @inputs duty::Real, [description = "Duty command, -1..1 (clamped); the sign sets the polarity"]
    @outputs begin
        i::Real, [unit = "A", description = "Output current, out of out_p into the load"]
        i_dc::Real, [unit = "A", description = "Current drawn from the DC bus, into dc_p"]
    end
    @parameters begin
        R_on::Real = 0.01, [unit = "Ohm", min = 0, description = "Resistance of the conducting path (two switches in series)"]
        I_max::Real = 1.0e12, [unit = "A", min = 0, description = "Current limit; the default 1e12 A is no limit"]
        R_limit::Real = 100.0, [unit = "Ohm", min = 0, description = "Fold-back slope of the current limit: volts lost per ampere above I_max"]
    end
    @variables d::Real = 0.0, [description = "Duty after the clamp to -1..1"]
    @equations begin
        d ~ clamp(duty, -1.0, 1.0)
        dc_p.f + dc_n.f ~ 0.0
        out_p.f + out_n.f ~ 0.0
        i ~ -out_p.f
        i_dc ~ dc_p.f
        i_dc ~ d * i
        out_p.e - out_n.e ~ d * (dc_p.e - dc_n.e) - R_on * i - R_limit * deadzone(i, I_max)
    end
end
