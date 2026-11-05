@block GearDrag begin
    # The drag of the extended gear (a modulated wrench on the airframe, in the geometric body
    # frame x forward, y left, z up): D = pos cd qbar S (JSBSim f16.xml, CDgear = 0.0270 times the
    # gear position) against the air-relative velocity, at z_arm below the centre of gravity.
    #
    #   air-relative velocity / vt in FLU = (cos(a) cos(b), -sin(b), -sin(a) cos(b))
    @inputs begin
        pos::Real, [description = "Gear position, 0 up .. 1 down"]
        qbar::Real, [unit = "Pa", description = "Dynamic pressure"]
        alpha::Real, [description = "Angle of attack (deg)"]
        beta::Real, [description = "Sideslip (deg)"]
    end
    @outputs begin
        tx::Real, [unit = "N*m"]
        ty::Real, [unit = "N*m"]
        tz::Real, [unit = "N*m"]
        fx::Real, [unit = "N"]
        fy::Real, [unit = "N"]
        fz::Real, [unit = "N"]
        drag::Real, [unit = "N"]
    end
    @parameters begin
        cd::Real = 0.027, [description = "Drag coefficient of the extended gear, on the wing area"]
        S::Real = 27.870912, [unit = "m^2", description = "Wing area"]
        z_arm::Real = 1.2, [unit = "m", description = "How far below the CG the drag acts"]
    end
    @equations begin
        drag ~ pos * cd * qbar * S
        fx ~ -drag * cos(alpha / 57.29577951308232) * cos(beta / 57.29577951308232)
        fy ~ drag * sin(beta / 57.29577951308232)
        fz ~ drag * sin(alpha / 57.29577951308232) * cos(beta / 57.29577951308232)
        # r = (0, 0, -z_arm), t = r x f
        tx ~ z_arm * fy
        ty ~ -z_arm * fx
        tz ~ 0.0 * drag
    end
end
