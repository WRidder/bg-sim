@block PitchFBW begin
    # Pitch-rate control law with scheduled gains (inputs Ka, Kq, Ki, from Lookup2D blocks over
    # dynamic pressure and Mach) and back-calculation anti-windup:
    #     u    = Ka*(alpha - alpha_ref) + Kq*(q - kff*q_cmd) + xi   (elevator command, deg)
    #     d xi/dt = Ki*(q - q_cmd) + (clamp(u, -u_max, u_max) - u)/t_aw
    # On the ground (`w`, the weight on wheels, from GearLogic; 0 in the models without gear) the
    # law hands over to the direct stick command `u_ground`, and the integrator follows it, so
    # the law takes over without a step at lift-off:
    #     y = (1 - w) sat(u) + w u_ground
    #     d xi/dt = (1 - w) (the above) + w (u_ground - u)/t_track
    # Ka, Kq, Ki come from an LQR design on the short-period model (alpha, q and the integral of
    # the pitch-rate error) at every grid point; see design/fbw.py. A share kff of the command
    # goes straight into the proportional path, so the response does not wait for the
    # integrator. The integral accumulates Ki times the error (not Ki times the integral of the
    # error), so a gain that changes with the operating point does not make the output jump.
    # alpha_ref (default 0) shifts the alpha feedback by a constant, which the integrator absorbs:
    # the response is the same, but with alpha_ref at the trim alpha the integrator's start is
    # the trim elevator (the f16-sim model sets both from its trim globals).
    # Signs: the book's positive elevator is trailing edge down (nose down), so a positive
    # pitch-rate error (q above the command) asks for more elevator.
    @inputs begin
        alpha::Real, [description = "Angle of attack (deg)"]
        q::Real, [description = "Pitch rate (deg/s)"]
        q_cmd::Real, [description = "Pitch-rate command (deg/s)"]
        Ka::Real, [description = "Alpha gain (deg/deg)"]
        Kq::Real, [description = "Pitch-rate gain (deg per deg/s)"]
        Ki::Real, [description = "Integral gain (deg/s per deg/s)"]
        w::Real, [description = "Weight on wheels, 0 .. 1"]
        u_ground::Real, [description = "Elevator command on the ground (deg)"]
    end
    @outputs begin
        u::Real, [description = "Elevator command, limited to +-u_max (deg)"]
        u_raw::Real, [description = "Elevator command before the limit (deg)"]
        y::Real, [description = "Elevator command after the ground hand-over (deg)"]
    end
    @parameters begin
        alpha_ref::Real = 0.0, [description = "Alpha the alpha feedback is measured from (deg)"]
        kff::Real = 0.5, [description = "Share of q_cmd in the proportional path"]
        u_max::Real = 25.0, [description = "Elevator travel (deg)"]
        t_aw::Real = 0.1, [unit = "s", min = 1.0e-6, description = "Anti-windup time constant"]
        t_track::Real = 0.1, [unit = "s", min = 1.0e-6, description = "Time constant of the integrator on the ground"]
    end
    @variables xi::Real = 0.0, [state = :prefer, description = "Integral part of the command (deg)"]
    @equations begin
        u_raw ~ Ka * (alpha - alpha_ref) + Kq * (q - kff * q_cmd) + xi
        u ~ clamp(u_raw, -u_max, u_max)
        y ~ (1.0 - w) * u + w * u_ground
        ddt(xi) ~ (1.0 - w) * (Ki * (q - q_cmd) + (u - u_raw) / t_aw) + w * (u_ground - u_raw) / t_track
    end
end
