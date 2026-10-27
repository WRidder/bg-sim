@block HydraulicCylinder begin
    @ports begin
        A::Power{Hydraulic}
        B::Power{Hydraulic}
        rod::Power{Translation}
    end
    @parameters begin
        Ap::Real = 2.0e-3, [unit = "m^2", min = 1.0e-12, description = "Piston area of chamber A"]
        Ar::Real = 1.0e-3, [unit = "m^2", min = 1.0e-12, description = "Annulus area of chamber B"]
        V0A::Real = 5.0e-5, [unit = "m^3", min = 1.0e-12, description = "Dead volume of chamber A"]
        V0B::Real = 5.0e-5, [unit = "m^3", min = 1.0e-12, description = "Dead volume of chamber B at zero stroke"]
        beta::Real = 1.4e9, [unit = "Pa", min = 1.0e-12, description = "Bulk modulus of the fluid"]
        stroke::Real = 0.2, [unit = "m", min = 0, description = "Cylinder stroke: chamber B holds the annulus volume over stroke minus x"]
    end
    @variables begin
        x::Real = 0.0, [unit = "m", state = :prefer, description = "Rod extension"]
        pA::Real = 0.0, [unit = "Pa", state = :prefer, description = "Chamber A pressure"]
        pB::Real = 0.0, [unit = "Pa", state = :prefer, description = "Chamber B pressure"]
    end
    @equations begin
        ddt(x) ~ rod.f
        A.e ~ pA
        B.e ~ pB
        # Chamber compressibility: the dead volume plus the swept volume, fed by the port
        # flow minus the piston displacement flow (chamber A) or plus it (chamber B).
        ddt(pA) ~ beta * (A.f - Ap * rod.f) / (V0A + Ap * x)
        ddt(pB) ~ beta * (B.f + Ar * rod.f) / (V0B + Ar * (stroke - x))
        # Mechanical power balance: pA*Ap extends, pB*Ar retracts, and rod.e is positive
        # into the cylinder.
        rod.e ~ pB * Ar - pA * Ap
    end
end
