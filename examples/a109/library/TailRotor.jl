@block TailRotor begin
    # The tail rotor of the Heffley & Mnich model (lines 7060 .. 7330), a modulated source
    # applied at the tail-rotor hub: thrust from the same blade-element / momentum balance as
    # the main rotor (8 unrolled Newton steps), with the flow through the disc
    # VR = -(v - r D.TR + p H.TR) and the edgewise flow U^2 = (w + q D.TR)^2 + u^2. Thrust is
    # + right (FRD y), the output fy is in FLU. Its power T vi and torque T vi/Omega_TR load the
    # tail-rotor junction of the drivetrain bond graph.
    @inputs begin
        u::Real
        v::Real
        w::Real
        p::Real
        q::Real
        r::Real
        om::Real, [description = "Tail-rotor speed from the drivetrain (rad/s)"]
        thtr::Real, [description = "Tail-rotor collective (rad, pedals)"]
        rho::Real
    end
    @outputs begin
        fy::Real
        T::Real, [description = "Thrust, + to the right (N)"]
        vi::Real, [description = "Induced velocity (m/s)"]
        power::Real, [description = "Induced power T vi (W)"]
        torque::Real, [description = "Torque T vi / Omega_TR (N m)"]
        om_a::Real
    end
    @parameters begin
        R::Real = 0.945, [description = "Radius (m)"]
        a::Real = 3.0, [description = "Lift-curve slope (1/rad)"]
        sol::Real = 0.134, [description = "Solidity"]
        twist::Real = -0.137, [description = "Twist (rad)"]
        d_tr::Real = 6.56, [description = "Hub aft of the CG (m)"]
        h_tr::Real = 0.8, [description = "Hub above the CG (m)"]
        rpm_mode::Real = 0.0, [description = "0: aerodynamics at om0 (constant RPM); 1: at the drivetrain speed"]
        om0::Real = 217.8, [description = "Nominal speed (rad/s)"]
    end
    @variables begin
        vr::Real = 0.0
        vb::Real = 0.0
        kt::Real = 1.0
        u2::Real = 0.0
        cq::Real = 1.0
        bq::Real = 1.0
        dq::Real = 0.0
        vn::Vec{9} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        sn::Vec{8} = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    end
    @equations begin
        om_a ~ rpm_mode * om + (1.0 - rpm_mode) * om0
        vr ~ -(v - r * d_tr + p * h_tr)
        vb ~ vr + 2.0 / 3.0 * om_a * R * (thtr + 0.75 * twist)
        kt ~ om_a * R * rho * a * sol * pi * R * R / 4.0
        u2 ~ (w + q * d_tr)^2 + u * u
        cq ~ kt / (2.0 * rho * pi * R * R)
        bq ~ sqrt(u2 + vr * vr) + cq
        dq ~ bq * bq + 4.0 * cq * vb
        vn[1] ~ 2.0 * cq * vb / (bq + sqrt(sqrt(dq * dq + 1.0)))
        for k in 1:8
            sn[k] ~ sqrt(u2 + (vr - vn[k])^2 + 1.0e-4)
            vn[k + 1] ~ vn[k] - (vn[k] * sn[k] - cq * (vb - vn[k])) / (sn[k] - vn[k] * (vr - vn[k]) / sn[k] + cq)
        end
        vi ~ vn[9]
        T ~ kt * (vb - vn[9])
        fy ~ -T
        power ~ T * vn[9]
        torque ~ power / om_a
    end
end
