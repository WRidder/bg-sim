@block HeatFlowSensor begin
    @ports begin
        a::Power{Thermal}
        b::Power{Thermal}
    end
    @outputs y::Real = 0.0, [unit = "W"]
    @equations begin
        # A series sensor: no temperature drop, and the heat flow from a to b is the output.
        a.e ~ b.e
        a.f ~ y
        b.f ~ -y
    end
    @orientation begin
        a => :in
        b => :in
    end
end
