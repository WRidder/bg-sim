@block BeaverPropulsion begin
    # Forces and moments of engine operation (propeller thrust and slipstream) of the FDC 'Beaver'
    # model, as coefficients [FDC modbuild.m, REP Table C.4, from Tjee & Mulder's flight tests].
    # They are polynomials in dpt, the dimensionless total-pressure increase across the propeller:
    #
    #   dpt = c1 + c2 P/(rho V^3/2)      (P in kW)
    #   CXp = CXdpt dpt + CXadpt2 alpha dpt^2      CYp = 0
    #   CZp = CZdpt dpt                            Clp = Cla2dpt alpha^2 dpt
    #   Cmp = Cmdpt dpt                            Cnp = Cndpt3 dpt^3
    #
    # This is where the model stays algebraic: the source identified the thrust and the slipstream
    # effects together from the power, so there is no thrust force element to put on a bond.
    # `drivetrain` selects the power: 0 the source's P(pz, n_cmd, rho) (exact FDC), 1 the shaft
    # power the propeller absorbs from the crank (the bond-graph drivetrain, our addition).
    @inputs begin
        P_src::Real, [description = "Engine power at the commanded rpm (source)"]
        P_shaft::Real, [description = "Shaft power absorbed by the propeller (drivetrain)"]
        rho::Real, [unit = "kg/m^3"]
        V::Real, [unit = "m/s"]
        alpha::Real, [unit = "rad"]
    end
    @outputs begin
        P::Real, [description = "The power that drives dpt (kW)"]
        dpt::Real
        CXp::Real
        CYp::Real
        CZp::Real
        Clp::Real
        Cmp::Real
        Cnp::Real
    end
    @parameters begin
        drivetrain::Real = 0.0, [description = "1: thrust from the drivetrain's shaft power; 0: the source's algebraic power"]
        c1::Real = 0.08696
        c2::Real = 191.18
        CXdpt::Real = 0.1161
        CXadpt2::Real = 0.1453
        CZdpt::Real = -0.1563
        Cla2dpt::Real = -0.01406
        Cmdpt::Real = -0.07895
        Cndpt3::Real = -0.003026
    end
    @equations begin
        P ~ ifelse(drivetrain > 0.5, P_shaft, P_src)
        dpt ~ c1 + c2 * P / (0.5 * rho * V * V * V)
        CXp ~ CXdpt * dpt + CXadpt2 * alpha * dpt * dpt
        CYp ~ 0.0
        CZp ~ CZdpt * dpt
        Clp ~ Cla2dpt * alpha * alpha * dpt
        Cmp ~ Cmdpt * dpt
        Cnp ~ Cndpt3 * dpt * dpt * dpt
    end
end
