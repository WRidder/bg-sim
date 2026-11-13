@block MotorGY begin
    # The electromechanical gyrator of a DC motor as a plain bond-graph GY between an Electrical
    # bond and a Rotation bond: the winding current i makes the torque k i at the shaft, the shaft
    # speed w makes the back-EMF k w on the winding. It is `stdlib:bondgraph/GY` with typed ports
    # (a Generic GY cannot join two domains) and, unlike `stdlib:converters/EMConverter`, a
    # declared gyrator causality and no electrical return pin, so a motor whose winding is an R
    # between a voltage source and this element compiles without an algebraic loop.
    #
    # Port `e` is the winding side (power in), `m` the shaft side (power out). Port variables
    # count into the block, as in GY: e.e = -k m.f, m.e = k e.f.
    @ports begin
        e::Power{Electrical}
        m::Power{Rotation}
    end
    @parameters k::Real = 0.05, [unit = "N*m/A", description = "Torque and back-EMF constant"]
    @equations begin
        e.e ~ -k * m.f
        m.e ~ k * e.f
    end
    @causality (e, m) => :gyrator
    @orientation (e, m) => :through
end
