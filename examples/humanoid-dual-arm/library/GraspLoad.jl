@block GraspLoad begin
    # The load carried by one compliant grasp (a Revolute3D weld whose axis is held by the
    # torsion spring kq): the force kt |dl| [N] and the moment |(kr dth, kq q)| [N m], from the
    # weld's deflection outputs. Observed only.
    @parameters begin
        kt::Real = 1.0e5, [unit = "N/m", min = 0, description = "Translational grasp stiffness"]
        kr::Real = 1.0e3, [unit = "N*m/rad", min = 0, description = "Rotational grasp stiffness (two held axes)"]
        kq::Real = 1.0e3, [unit = "N*m/rad", min = 0, description = "Rotational grasp stiffness (the weld axis)"]
    end
    @inputs begin
        dl::Vec{3}, [unit = "m"]
        dth::Vec{2}, [unit = "rad"]
        q::Real, [unit = "rad"]
    end
    @outputs begin
        F::Real, [unit = "N"]
        M::Real, [unit = "N*m"]
    end
    @equations begin
        F ~ kt * sqrt(dl[1] * dl[1] + dl[2] * dl[2] + dl[3] * dl[3] + 1.0e-30)
        M ~ sqrt((kr * dth[1])^2 + (kr * dth[2])^2 + (kq * q)^2 + 1.0e-30)
    end
end
