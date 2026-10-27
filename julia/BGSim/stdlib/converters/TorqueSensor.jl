@block TorqueSensor begin
    @ports begin
        a::Power{Rotation}
        b::Power{Rotation}
    end
    @outputs y::Real = 0.0, [unit = "N*m"]
    @equations begin
        # A series sensor: it passes the angular velocity through unchanged and reads the torque.
        a.f ~ b.f
        a.e ~ y
        b.e ~ -y
    end
end
