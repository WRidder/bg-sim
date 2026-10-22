@block VoltageSource begin
    @ports begin
        p::Power{Electrical}
        n::Power{Electrical}
    end
    @inputs u::Real
    @parameters V::Real = 1.0, [unit = "V", description = "Voltage gain on the control input"]
    @equations begin
        p.e - n.e ~ V * u
        p.f + n.f ~ 0.0
    end
end
