@block FuselageAero begin
    # Air load of the fuselage (body, head and the fixed part of the tail): quadratic drag against the
    # velocity relative to the air, per body axis, with the drag areas `cdax`, `cday`, `cdaz` (C_D times
    # reference area, m^2), and a rotational damping of the body about its axes (the viscous moment of
    # the long body). Output: the wrench of `stdlib:multibond/ExternalWrenchSpatial`, `Pa` the power
    # given to the air.
    @inputs begin
        V::Vec{6}
        pose::Vec{7}
        wind::Vec{3}
    end
    @outputs begin
        tx::Real, [unit = "N*m"]
        ty::Real, [unit = "N*m"]
        tz::Real, [unit = "N*m"]
        fx::Real, [unit = "N"]
        fy::Real, [unit = "N"]
        fz::Real, [unit = "N"]
        Pa::Real, [unit = "W"]
    end
    @parameters begin
        rho::Real = 1.2, [unit = "kg/m^3", min = 0]
        cdax::Real = 0.0030, [unit = "m^2", min = 0, description = "Drag area along body x"]
        cday::Real = 0.0300, [unit = "m^2", min = 0, description = "Drag area along body y"]
        cdaz::Real = 0.0200, [unit = "m^2", min = 0, description = "Drag area along body z"]
        cdr::Vec{3} = [0.002, 0.01, 0.01], [description = "Rotational damping about x, y, z (N m s/rad)"]
    end
    @variables begin
        s::Real = 1.0
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0]
        vax::Real = 0.0
        vay::Real = 0.0
        vaz::Real = 0.0
        va::Real = 1.0
    end
    @equations begin
        s ~ pose[1] * pose[1] + pose[2] * pose[2] + pose[3] * pose[3] + pose[4] * pose[4]
        R[1, 1] ~ (pose[1] * pose[1] + pose[2] * pose[2] - pose[3] * pose[3] - pose[4] * pose[4]) / s
        R[1, 2] ~ 2 * (pose[2] * pose[3] - pose[1] * pose[4]) / s
        R[1, 3] ~ 2 * (pose[2] * pose[4] + pose[1] * pose[3]) / s
        R[2, 1] ~ 2 * (pose[2] * pose[3] + pose[1] * pose[4]) / s
        R[2, 2] ~ (pose[1] * pose[1] - pose[2] * pose[2] + pose[3] * pose[3] - pose[4] * pose[4]) / s
        R[2, 3] ~ 2 * (pose[3] * pose[4] - pose[1] * pose[2]) / s
        R[3, 1] ~ 2 * (pose[2] * pose[4] - pose[1] * pose[3]) / s
        R[3, 2] ~ 2 * (pose[3] * pose[4] + pose[1] * pose[2]) / s
        R[3, 3] ~ (pose[1] * pose[1] - pose[2] * pose[2] - pose[3] * pose[3] + pose[4] * pose[4]) / s
        vax ~ V[4] - (R[1, 1] * wind[1] + R[2, 1] * wind[2] + R[3, 1] * wind[3])
        vay ~ V[5] - (R[1, 2] * wind[1] + R[2, 2] * wind[2] + R[3, 2] * wind[3])
        vaz ~ V[6] - (R[1, 3] * wind[1] + R[2, 3] * wind[2] + R[3, 3] * wind[3])
        va ~ sqrt(vax * vax + vay * vay + vaz * vaz + 0.01)
        fx ~ -0.5 * rho * cdax * va * vax
        fy ~ -0.5 * rho * cday * va * vay
        fz ~ -0.5 * rho * cdaz * va * vaz
        tx ~ -cdr[1] * V[1]
        ty ~ -cdr[2] * V[2]
        tz ~ -cdr[3] * V[3]
        Pa ~ -(fx * vax + fy * vay + fz * vaz) - (tx * V[1] + ty * V[2] + tz * V[3])
    end
end
