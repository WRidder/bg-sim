@block PropGovernor begin
    # Constant-speed propeller (Hamilton Standard, 2.59 m) on the R-985 crank: OUR ADDITION, not in
    # the source. FDC prescribes the rpm and takes the power as algebraic; here the propeller
    # absorbs the torque Q = Cq rho n^2 D^5 (n in rev/s) and a PI governor sets the torque
    # coefficient Cq (the blade pitch, implicit) to hold the commanded rpm:
    #
    #   e = (w - w_cmd)/w_cmd,   Cq = ci + Kp e,   d(ci)/dt = Ki e
    #
    # Kp and Ki place the linearised shaft-speed loop (crank + propeller inertia J) at the design
    # wn, zeta at the trim point (design/beaver_ref.py, drive_gains). Cq does not depend on the
    # advance ratio: the absorbed power Q w is independent of the airspeed, as the source's power.
    @inputs begin
        w::Real, [unit = "rad/s", description = "Crank speed"]
        n_cmd::Real, [description = "Commanded engine speed (rpm)"]
        rho::Real, [unit = "kg/m^3", description = "Air density"]
    end
    @outputs begin
        Q::Real, [unit = "N*m", description = "Torque absorbed by the propeller"]
        P_shaft::Real, [description = "Shaft power absorbed by the propeller, Q w (kW)"]
        Cq::Real, [description = "Torque coefficient"]
    end
    @parameters begin
        Kp::Real = 0.0, [description = "Proportional gain (torque coefficient per relative speed error)"]
        Ki::Real = 0.0, [unit = "1/s", description = "Integral gain"]
        D::Real = 2.59, [unit = "m", description = "Propeller diameter"]
    end
    @variables begin
        ci::Real = 0.0, [state = :prefer, description = "Governor integrator (torque coefficient)"]
        e::Real = 0.0, [description = "Relative speed error"]
    end
    @equations begin
        e ~ (w - n_cmd / 9.549296585513721) / (n_cmd / 9.549296585513721)
        ddt(ci) ~ Ki * e
        Cq ~ ci + Kp * e
        Q ~ Cq * rho * (w / 6.283185307179586)^2 * D^5
        P_shaft ~ Q * w / 1000.0
    end
end
