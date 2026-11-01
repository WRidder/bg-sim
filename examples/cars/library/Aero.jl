@block Aero begin
    # Aerodynamic forces on the chassis in still air, as the six inputs of
    # `stdlib:multibond/ExternalWrenchSpatial` in the chassis frame (x forward, y left, z up,
    # about the sprung centre of gravity). With u, v the forward and lateral body velocities and
    # V = sqrt(u^2 + v^2):
    #
    #   drag       Fx = -rho/2 CdA u V            acting at the height zd above the CG
    #   side drag  Fy = -rho/2 CyA v V
    #   downforce  D  =  rho/2 ClA u^2, split `front` at the front axle (x = a) and the rest at
    #              the rear axle (x = -b):  Fz = -D,  My = D (front a - (1 - front) b)
    #   drag pitch My += zd Fx
    #
    # The power F.v + M.w is -rho/2 (CdA u^2 + CyA v^2) V <= 0 plus the work of the downforce
    # moment on the pitch rate (zero on average).
    @inputs V::Vec{6}, [description = "Chassis twist [w; v] in the chassis frame"]
    @outputs begin
        tx::Real, [unit = "N*m"]
        ty::Real, [unit = "N*m"]
        tz::Real, [unit = "N*m"]
        fx::Real, [unit = "N"]
        fy::Real, [unit = "N"]
        fz::Real, [unit = "N"]
        drag::Real, [unit = "N", description = "Drag force"]
        downforce::Real, [unit = "N", description = "Downforce"]
    end
    @parameters begin
        rho::Real = 1.225, [unit = "kg/m^3", min = 0, description = "Air density"]
        CdA::Real = 0.95, [unit = "m^2", min = 0, description = "Drag area"]
        CyA::Real = 1.5, [unit = "m^2", min = 0, description = "Side drag area"]
        ClA::Real = 2.6, [unit = "m^2", min = 0, description = "Downforce area"]
        front::Real = 0.42, [unit = "1", description = "Front share of the downforce"]
        a::Real = 1.6, [unit = "m", description = "CG to front axle"]
        b::Real = 1.2, [unit = "m", description = "CG to rear axle"]
        zd::Real = 0.05, [unit = "m", description = "Height of the drag force above the CG"]
    end
    @variables sp::Real = 0.0, [unit = "m/s", description = "Speed sqrt(u^2 + v^2)"]
    @equations begin
        sp ~ sqrt(V[4] * V[4] + V[5] * V[5] + 1.0e-6)
        drag ~ 0.5 * rho * CdA * V[4] * sp
        downforce ~ 0.5 * rho * ClA * V[4] * V[4]
        fx ~ -drag
        fy ~ -0.5 * rho * CyA * V[5] * sp
        fz ~ -downforce
        tx ~ 0.0
        ty ~ downforce * (front * a - (1 - front) * b) - zd * drag
        tz ~ 0.0
    end
end
