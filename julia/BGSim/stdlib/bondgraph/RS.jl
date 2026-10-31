@block RS begin
    @ports begin
        p::Power{Generic}
        heat::Power{Thermal}
    end
    # `effort*flow` is a watt on every energetic domain (V*A, N*m/s, N*m*rad/s, Pa*m^3/s), so
    # this constant is 1 W per unit of bond power: it states that conversion for the unit
    # checker, and adoption turns it into the dimensionless 1 on a concrete island.
    @constants watt::Real = 1.0, [unit = "W/(effort*flow)", description = "One watt per unit of bond power"]
    @parameters r::Real = 1.0, [unit = "effort/flow", min = 0, description = "Resistance"]
    @variables P::Real = 0.0, [unit = "W", description = "Dissipated power, delivered as heat flow"]
    @equations begin
        p.e ~ r * p.f
        # The entropy-producing side of the R: all dissipated power leaves through the heat
        # port as heat flow (port flows count into the block), so energy is conserved exactly.
        P ~ watt * p.e * p.f
        heat.f ~ -P
    end
end
