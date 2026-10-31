@block StaticCarrier begin
    # A carrier that does not move (the table under the parts): constant position, zero velocity
    # and slide position, for the carrier inputs of a MovingPlaneContact on a fixed face.
    @outputs begin
        pc::Vec{3}, [unit = "m", description = "Carrier position in the world"]
        vc::Vec{3}, [unit = "m/s", description = "Carrier velocity (zero)"]
        xs::Real, [unit = "m", description = "Slide position (zero)"]
    end
    @parameters begin
        x0::Real = 0.0, [unit = "m", description = "Position x"]
        y0::Real = 0.0, [unit = "m", description = "Position y"]
        z0::Real = 0.0, [unit = "m", description = "Position z"]
    end
    @equations begin
        pc[1] ~ x0
        pc[2] ~ y0
        pc[3] ~ z0
        vc[1] ~ 0.0
        vc[2] ~ 0.0
        vc[3] ~ 0.0
        xs ~ 0.0
    end
end
