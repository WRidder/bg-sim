@block Volume begin
    @ports a::Power{Hydraulic}
    @parameters begin
        V::Real = 1.0e-4, [unit = "m^3", min = 1.0e-12, description = "Fluid volume"]
        beta::Real = 1.4e9, [unit = "Pa", min = 1.0e-12, description = "Bulk modulus"]
    end
    @variables p::Real = 0.0, [unit = "Pa", state = :prefer, description = "Fluid pressure"]
    @equations begin
        # Fluid compressibility: the pressure integrates the net flow into the volume.
        ddt(p) ~ beta * a.f / V
        a.e ~ p
    end
end
