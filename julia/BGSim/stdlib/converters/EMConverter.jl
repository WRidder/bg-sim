@block EMConverter begin
    @ports begin
        p::Power{Electrical}
        n::Power{Electrical}
        shaft::Power{Rotation}
    end
    @parameters k::Real = 0.05, [unit = "N*m/A", description = "Torque and back-EMF constant"]
    @equations begin
        # Ideal gyrator, with the motor orientation of the DC-motor bond graph: the back-EMF
        # is -k*shaft.f across p and n, and the torque into the shaft is k*p.f. Power is
        # conserved: (p.e - n.e)*p.f + shaft.e*shaft.f = 0.
        p.f + n.f ~ 0.0
        p.e - n.e ~ -k * shaft.f
        shaft.e ~ k * p.f
    end
end
