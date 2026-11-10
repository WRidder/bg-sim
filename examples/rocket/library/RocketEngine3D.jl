@block RocketEngine3D begin
    # Rocket engine thrust with the ambient-pressure correction, as a body wrench at the centre
    # of mass (for an `ExternalWrenchSpatial` on the body's 1-junction):
    #
    #     T = max(mdot c_vac - p_a A_e, 0)
    #
    # `c_vac` is the vacuum effective exhaust velocity (vacuum Isp times g0) and `A_e` the total
    # nozzle exit area: at sea level the ambient pressure pushes back on the exit plane. The
    # nozzle swivels by the gimbal angle `delta` about the body y axis at `l` behind the centre of
    # mass (on the -x axis), so the thrust (T cos(delta), 0, T sin(delta)) also gives the pitch
    # moment l T sin(delta). Body axes: x along the vehicle towards the nose.
    @inputs begin
        mdot::Real, [unit = "kg/s", description = "Propellant flow"]
        c::Real, [unit = "m/s", description = "Vacuum effective exhaust velocity"]
        ae::Real, [unit = "m^2", description = "Total nozzle exit area"]
        pa::Real, [unit = "Pa", description = "Ambient pressure"]
        delta::Real, [unit = "rad", description = "Gimbal angle about body y"]
        l::Real, [unit = "m", description = "Centre of mass to gimbal"]
    end
    @outputs begin
        T::Real, [unit = "N"]
        tx::Real, [unit = "N*m"]
        ty::Real, [unit = "N*m"]
        tz::Real, [unit = "N*m"]
        fx::Real, [unit = "N"]
        fy::Real, [unit = "N"]
        fz::Real, [unit = "N"]
    end
    @equations begin
        T ~ max(mdot * c - pa * ae, 0.0)
        fx ~ T * cos(delta)
        fy ~ 0.0
        fz ~ T * sin(delta)
        tx ~ 0.0
        ty ~ l * T * sin(delta)
        tz ~ 0.0
    end
end
