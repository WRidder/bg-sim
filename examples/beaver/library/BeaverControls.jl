@block BeaverControls begin
    # The cockpit of the flyable Beaver: OUR MAPPING (the source has controls in radians, no
    # cockpit). The pilot's column and pedals (-1 .. 1) and the trim offsets set the surfaces; the
    # autopilot servos add to them (in the aircraft the servo moves the cables, and the column):
    #
    #   elevator  de = elev_trim - k_col_e col_pitch + servo_e      (column aft +: trailing edge up)
    #   ailerons  da = ail_trim  - k_col_a col_roll  + servo_a      (column right +: right aileron up)
    #   rudder    dr = rud_trim  - k_ped pedals      + servo_r      (right pedal +: trailing edge right)
    #
    # FDC's sign conventions [REP]: de positive trailing edge down; da = da_right - da_left, positive
    # rolls left; dr positive trailing edge left (yaws left); df positive down. Every deflection is
    # limited to the assumed travel; flaps, manifold pressure and rpm are limited too. Outputs in
    # deg (surfaces), inch Hg and rpm.
    @inputs begin
        col_pitch::Real, [description = "Column pitch, -1 full forward .. +1 full aft"]
        col_roll::Real, [description = "Column roll (wheel), -1 full left .. +1 full right"]
        pedals::Real, [description = "Rudder pedals, -1 full left .. +1 full right"]
        flaps::Real, [description = "Flap setting (deg)"]
        elev_trim::Real, [description = "Elevator trim (deg of elevator)"]
        pz_in::Real, [description = "Manifold pressure lever (inch Hg)"]
        rpm_in::Real, [description = "Propeller lever: governed rpm"]
        servo_e::Real, [unit = "rad"]
        servo_a::Real, [unit = "rad"]
        servo_r::Real, [unit = "rad"]
    end
    @outputs begin
        de::Real, [description = "Elevator (deg)"]
        da::Real, [description = "Ailerons (deg)"]
        dr::Real, [description = "Rudder (deg)"]
        df::Real, [description = "Flaps (deg)"]
        pz::Real, [description = "Manifold pressure (inch Hg)"]
        n::Real, [description = "Commanded rpm"]
    end
    @parameters begin
        ail_trim::Real = 0.0, [description = "Aileron offset (deg) that trims the propeller's roll"]
        rud_trim::Real = 0.0, [description = "Rudder offset (deg) that trims the propeller's yaw"]
        k_col_e::Real = 15.0, [description = "Elevator per full column (deg)"]
        k_col_a::Real = 15.0, [description = "Ailerons per full column (deg)"]
        k_ped::Real = 15.0, [description = "Rudder per full pedal (deg)"]
        lim_e::Real = 20.0, [description = "Elevator travel (+- deg)"]
        lim_a::Real = 20.0, [description = "Aileron travel (+- deg)"]
        lim_r::Real = 20.0, [description = "Rudder travel (+- deg)"]
        flap_max::Real = 20.0, [description = "Largest flap setting (deg)"]
        pz_min::Real = 10.0
        pz_max::Real = 30.0
        n_min::Real = 1600.0
        n_max::Real = 2300.0
    end
    @equations begin
        de ~ clamp(elev_trim - k_col_e * col_pitch + servo_e * 57.29577951308232, -lim_e, lim_e)
        da ~ clamp(ail_trim - k_col_a * col_roll + servo_a * 57.29577951308232, -lim_a, lim_a)
        dr ~ clamp(rud_trim - k_ped * pedals + servo_r * 57.29577951308232, -lim_r, lim_r)
        df ~ clamp(flaps, 0.0, flap_max)
        pz ~ clamp(pz_in, pz_min, pz_max)
        n ~ clamp(rpm_in, n_min, n_max)
    end
end
