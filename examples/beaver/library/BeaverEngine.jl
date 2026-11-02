@block BeaverEngine begin
    # The P&W R-985 engine of the FDC 'Beaver' model, as the torque source of the drivetrain.
    #
    # Engine power (kW) from the manifold pressure pz (inch Hg), the engine speed n (rpm) and the
    # density [FDC fdclib3.mdl, REP eq. 3.15, from Tjee & Mulder's flight tests]:
    #
    #   P(pz, n, rho) = 0.7355 (-326.5 + 0.00412 (pz + 7.4)(n + 2010) + (408.0 - 0.0965 n)(1 - rho/1.225))
    #
    #   Te     the crank torque P(pz, n(w), rho)/w (N m) at the shaft speed w (rad/s): the MSe of the drivetrain
    #   P_src  P at the commanded rpm n_cmd: the source's algebraic power (FDC takes the rpm as an input)
    #   P_eng  P at the shaft speed
    @inputs begin
        pz::Real, [description = "Manifold pressure (inch Hg)"]
        n_cmd::Real, [description = "Commanded (governed) engine speed (rpm)"]
        w::Real, [unit = "rad/s", description = "Crank speed"]
        rho::Real, [unit = "kg/m^3", description = "Air density"]
    end
    @outputs begin
        Te::Real, [unit = "N*m", description = "Engine torque on the crank"]
        P_src::Real, [description = "Engine power at n_cmd (the source's power, kW)"]
        P_eng::Real, [description = "Engine power at the shaft speed (kW)"]
        n_shaft::Real, [description = "Shaft speed (rpm)"]
    end
    @parameters begin
        k::Real = 0.7355, [description = "kW per metric horsepower"]
        c0::Real = -326.5
        c1::Real = 0.00412
        pz0::Real = 7.4
        n0::Real = 2010.0
        c2::Real = 408.0
        c3::Real = 0.0965
        rho0::Real = 1.225, [unit = "kg/m^3"]
    end
    @equations begin
        n_shaft ~ w * 9.549296585513721
        P_src ~ k * (c0 + c1 * (pz + pz0) * (n_cmd + n0) + (c2 - c3 * n_cmd) * (1.0 - rho / rho0))
        P_eng ~ k * (c0 + c1 * (pz + pz0) * (n_shaft + n0) + (c2 - c3 * n_shaft) * (1.0 - rho / rho0))
        Te ~ 1000.0 * P_eng / w
    end
end
