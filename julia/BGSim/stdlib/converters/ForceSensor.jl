@block ForceSensor begin
    @ports begin
        a::Power{Translation}
        b::Power{Translation}
    end
    @outputs y::Real = 0.0, [unit = "N"]
    @equations begin
        # A series sensor: it passes the velocity through unchanged and reads the force.
        a.f ~ b.f
        a.e ~ y
        b.e ~ -y
    end
end
