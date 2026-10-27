@block BallScrew begin
    @ports begin
        a::Power{Rotation}
        b::Power{Translation}
    end
    @parameters begin
        lead::Real = 0.01, [unit = "m", min = 1.0e-9, description = "Lead per revolution"]
        eta::Real = 0.9, [unit = "1", min = 0, max = 1, description = "Efficiency when driven from the screw; the reciprocal applies when back-driven"]
    end
    @equations begin
        # One revolution advances the nut by the lead, so the linear speed is lead/(2*pi)
        # times the angular speed. The efficiency follows the power direction, like LossyGear.
        b.f ~ lead * a.f / 6.283185307179586
        b.e ~ -6.283185307179586 / lead * a.e *
              ifelse(a.e * a.f > 0.0, eta, 1.0 / eta)
    end
    @causality (a, b) => :transformer
end
