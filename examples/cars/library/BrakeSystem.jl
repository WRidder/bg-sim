@block BrakeSystem begin
    # Brake pedal and handbrake to the four friction brake torques (the clamping forces of stdlib
    # `Brake` elements with n_faces = 1, r_eff = 1 m, mu = 1, so a force in N is a torque in N m),
    # blended with the regenerative braking of the traction motors. The pedal asks Tf (Tr) per
    # wheel; the axle's demand `dem_f` (`dem_r`, both wheels) goes to the motor of that axle, which
    # supplies `regen_f` (`regen_r`) of it, never more, and the friction brakes take the rest:
    # Tf b - regen_f/2 per wheel, which is never negative. An axle without a motor feeds 0 as its
    # regen. The front/rear balance is in the maximum torques; the handbrake works on the rear
    # friction brakes only. While the motor covers the whole demand the friction share is zero
    # up to rounding, and the `max(f_n, 0)` kink of the stdlib Brake would fire an event at every
    # sign flip of that noise (W206); `f_min`, a negligible floor, keeps every clamping force
    # strictly positive so that kink is never crossed. For the same reason the pedals are not
    # clamped here (a released pedal at exactly 0 would sit on the clamp's corner); the host and
    # the stimuli keep them in 0..1.
    @inputs begin
        brake::Real, [unit = "1", description = "Brake pedal 0..1"]
        handbrake::Real, [unit = "1", description = "Handbrake 0..1"]
        regen_f::Real, [unit = "N*m", description = "Regenerative brake torque of the front axle (both wheels)"]
        regen_r::Real, [unit = "N*m", description = "Regenerative brake torque of the rear axle (both wheels)"]
    end
    @outputs begin
        fl::Real, [unit = "N", description = "Brake clamping force (= torque capacity in N m), front left"]
        fr::Real, [unit = "N", description = "Brake clamping force (= torque capacity in N m), front right"]
        rl::Real, [unit = "N", description = "Brake clamping force (= torque capacity in N m), rear left"]
        rr::Real, [unit = "N", description = "Brake clamping force (= torque capacity in N m), rear right"]
        dem_f::Real, [unit = "N*m", description = "Brake torque the pedal asks of the front axle (both wheels)"]
        dem_r::Real, [unit = "N*m", description = "Brake torque the pedal asks of the rear axle (both wheels)"]
    end
    @parameters begin
        Tf::Real = 1900.0, [unit = "N", min = 0, description = "Front brake torque per wheel at full pedal"]
        Tr::Real = 1300.0, [unit = "N", min = 0, description = "Rear brake torque per wheel at full pedal"]
        Th::Real = 0.0, [unit = "N", min = 0, description = "Rear brake torque per wheel of the handbrake"]
        k_t::Real = 1.0, [unit = "N/(N*m)", description = "Clamping force per brake torque (r_eff = 1 m, mu = 1)"]
        f_min::Real = 1.0e-3, [unit = "N", min = 0, description = "Floor of every clamping force (keeps the Brake off its kink at zero)"]
    end
    @variables begin
        b::Real = 0.0, [unit = "1", description = "Pedal 0..1"]
        ff::Real = 0.0, [unit = "N", description = "Front friction share per wheel"]
        fq::Real = 0.0, [unit = "N", description = "Rear friction share per wheel"]
    end
    @equations begin
        b ~ brake
        dem_f ~ 2 * Tf * b / k_t
        dem_r ~ 2 * Tr * b / k_t
        ff ~ Tf * b - 0.5 * k_t * regen_f + f_min
        fq ~ Tr * b - 0.5 * k_t * regen_r + f_min
        fl ~ ff
        fr ~ ff
        rl ~ fq + Th * handbrake
        rr ~ fq + Th * handbrake
    end
end
