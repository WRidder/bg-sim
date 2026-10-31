@block PlanetaryGear begin
    @ports begin
        sun::Power{Rotation}
        ring::Power{Rotation}
        carrier::Power{Rotation}
    end
    @parameters ratio::Real = 2.0, [unit = "1", min = 1.0e-12, description = "Tooth ratio z_ring / z_sun"]
    @equations begin
        # The Willis equation of an ideal planetary set:
        # w_sun + ratio * w_ring = (1 + ratio) * w_carrier.
        sun.f + ratio * ring.f ~ (1.0 + ratio) * carrier.f
        # The torques split 1 : ratio : -(1 + ratio), so the set is power conserving (power
        # positive into every flange): the sum of torque times speed is zero.
        ring.e ~ ratio * sun.e
        carrier.e ~ -(1.0 + ratio) * sun.e
    end
end
