@block FlowSensor begin
    @ports begin
        a::Power{Hydraulic}
        b::Power{Hydraulic}
    end
    @outputs y::Real = 0.0, [unit = "m^3/s"]
    @equations begin
        # A series sensor: no pressure drop, and the flow through it is the output.
        a.e ~ b.e
        a.f ~ y
        b.f ~ -y
    end
end
