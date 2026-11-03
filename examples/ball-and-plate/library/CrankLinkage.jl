@block CrankLinkage begin
    # Kinematics of the servo crank and push rod that tilt the plate (one axis): a crank of radius
    # r_arm on the servo shaft lifts the plate edge at the distance L from the gimbal centre,
    #   sin(alpha) = rho sin(theta),  rho = r_arm / L,
    # so the plate rate is alpha' = m theta' with the modulus
    #   m = dalpha/dtheta = rho cos(theta) / sqrt(1 - rho^2 sin(theta)^2).
    # `m` drives the MTF between the servo shaft and the push rod (the bond graph carries the
    # power; this block only computes the ratio). `sgn` = -1 mirrors the axis (the second gimbal
    # axis turns the other way for a positive servo angle). `alpha` is the plate angle the crank
    # sets with a rigid rod.
    @inputs theta::Real, [unit = "rad", description = "Servo (crank) angle"]
    @outputs begin
        m::Real, [unit = "1", description = "Transmission ratio dalpha/dtheta (MTF modulus)"]
        alpha::Real, [unit = "rad", description = "Plate angle of a rigid rod"]
    end
    @parameters begin
        rho::Real = 0.15875, [unit = "1", min = 0, max = 1, description = "Crank radius over the rod's distance from the gimbal centre, r_arm / L"]
        sgn::Real = 1.0, [unit = "1", description = "Direction of the plate axis: +1 or -1"]
    end
    @variables s::Real = 0.0, [unit = "1", description = "rho sin(theta) = sin(alpha)"]
    @equations begin
        s ~ rho * sin(theta)
        alpha ~ sgn * asin(s)
        m ~ sgn * rho * cos(theta) / sqrt(1 - s * s)
    end
end
