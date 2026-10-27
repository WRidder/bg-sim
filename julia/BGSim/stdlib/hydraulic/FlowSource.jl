@block FlowSource begin
    @ports begin
        a::Power{Hydraulic}
        b::Power{Hydraulic}
    end
    @inputs u::Real
    @parameters Q::Real = 1.0e-4, [unit = "m^3/s", description = "Volume-flow gain on the control input"]
    @equations begin
        # The source drives Q*u into a and returns it through b. The two-terminal fixed flow
        # cannot be written as a one-port D6 causality entry, so the equations carry it.
        a.f ~ Q * u
        b.f ~ -Q * u
    end
end
