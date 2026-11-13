@block StabComp begin
    # Phase-compensated rate limiter ahead of the stabilator servo of f16-sim:
    #     du   = (u - xf)/tf,  d xf/dt = du                    (the command's filtered derivative)
    #     e    = u - x
    #     d x/dt = clamp(du + (k + w k_ground) e + k2 (e - clamp(e, -e0, e0)), -rate, rate),    y = x
    # Below about 150 KEAS the pitch law's gains are large (Kq is 3.2 deg per deg/s at 80 psf), so
    # a small pitch rate already asks for more than the servo's 60 deg/s. A plain rate limit only
    # turns round when the command crosses its output: it lags by up to a quarter period, and the
    # loop settles in a limit cycle, the stabilator swinging +-20 deg at 60 deg/s. Here the output
    # turns round as soon as the command does (the derivative term), and the slow pull-back k
    # brings it onto the command again. It is the compensator of f16-pio.
    # k has to stay small: from about 2 1/s the limit cycle is back. But a stick reversal at full
    # rate leaves the output up to 20 deg off the command, and at k that offset would keep the
    # stabilator away from the law for seconds. Beyond e0 the pull-back is therefore k2: small
    # errors keep the phase compensation, large ones are taken out in a fraction of a second.
    # On the wheels the stick commands the stabilator directly, so the weight on wheels `w`
    # (GearLogic) raises the gain to k + k_ground: a plain rate limit, as the servo's own. In the
    # air w is exactly 0.
    @inputs begin
        u::Real, [description = "Stabilator command of the law (deg)"]
        w::Real, [description = "Weight on wheels, 0 .. 1"]
    end
    @outputs begin
        y::Real, [description = "Command to the servo (deg)"]
        rate_cmd::Real, [description = "Rate of that command (deg/s)"]
    end
    @parameters begin
        rate::Real = 60.0, [description = "Rate limit (deg/s)"]
        k::Real = 0.5, [unit = "1/s", description = "Pull-back gain in the air"]
        k2::Real = 6.0, [unit = "1/s", description = "Pull-back gain on the part of the error beyond e0"]
        e0::Real = 12.0, [description = "Error up to which only k pulls back (deg)"]
        k_ground::Real = 20.0, [unit = "1/s", description = "Pull-back gain added on the wheels"]
        tf::Real = 0.01, [unit = "s", min = 1.0e-6, description = "Filter time of the derivative"]
    end
    @variables begin
        x::Real = 0.0, [state = :prefer, description = "Compensated command (deg)"]
        xf::Real = 0.0, [state = :prefer, description = "Filtered command (deg)"]
        du::Real = 0.0, [description = "Filtered derivative of the command (deg/s)"]
        e::Real = 0.0, [description = "Command minus output (deg)"]
    end
    @equations begin
        du ~ (u - xf) / tf
        ddt(xf) ~ du
        e ~ u - x
        rate_cmd ~ clamp(du + (k + w * k_ground) * e + k2 * (e - clamp(e, -e0, e0)), -rate, rate)
        ddt(x) ~ rate_cmd
        y ~ x
    end
end
