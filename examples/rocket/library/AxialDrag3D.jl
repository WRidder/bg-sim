@block AxialDrag3D begin
    # Aerodynamic drag with a Mach-dependent coefficient, as a body wrench at the centre of mass
    # (for an `ExternalWrenchSpatial`):
    #
    #     M = |va| / a,   q = rho |va|^2 / 2,   D = scale q S cd(M),   F = -D va / |va|
    #
    # `va` is the velocity relative to the air in body axes, `cd(M)` a piecewise-linear table on
    # the reference area `S` (held beyond its ends). The force acts at the centre of mass and
    # along the air velocity only: no lift and no aerodynamic moment (the rockets fly at a small
    # angle of attack; see the README for this limitation).
    @constants N::Int = 2, [min = 2, description = "Number of Mach breakpoints"]
    @inputs begin
        va::Vec{3}, [unit = "m/s", description = "Air-relative velocity in body axes"]
        rho::Real, [unit = "kg/m^3", description = "Air density"]
        a::Real, [unit = "m/s", description = "Speed of sound"]
    end
    @parameters begin
        S::Real = 1.0, [unit = "m^2", min = 0, description = "Reference area"]
        mach_tab::Vec{N} = [0.0, 1.0], [description = "Mach breakpoints"]
        cd_tab::Vec{N} = [0.3, 0.3], [description = "Drag coefficient at the breakpoints"]
        scale::Real = 1.0, [min = 0, description = "Multiplier (0: no drag)"]
        v_eps::Real = 1.0e-3, [unit = "m/s", description = "Speed floor for the direction at rest"]
    end
    @variables vas::Real, [unit = "m/s"]
    @outputs begin
        mach::Real
        qbar::Real, [unit = "Pa"]
        cd::Real
        D::Real, [unit = "N"]
        tx::Real, [unit = "N*m"]
        ty::Real, [unit = "N*m"]
        tz::Real, [unit = "N*m"]
        fx::Real, [unit = "N"]
        fy::Real, [unit = "N"]
        fz::Real, [unit = "N"]
    end
    @equations begin
        vas ~ sqrt(va[1] * va[1] + va[2] * va[2] + va[3] * va[3] + v_eps * v_eps)
        mach ~ vas / a
        qbar ~ 0.5 * rho * vas * vas
        cd ~ interp1(mach, mach_tab, cd_tab)
        D ~ scale * qbar * S * cd
        fx ~ -D * va[1] / vas
        fy ~ -D * va[2] / vas
        fz ~ -D * va[3] / vas
        tx ~ 0.0
        ty ~ 0.0
        tz ~ 0.0
    end
end
