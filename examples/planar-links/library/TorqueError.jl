@block TorqueError begin
    # Joint torque of the bond-graph arm against the two reference torques of the CSV file
    # (Robotics Toolbox `rne_python` and the closed-form analytical model).
    @inputs begin
        tau::Real, [unit = "N*m", description = "Torque the bond-graph model needs at the joint"]
        ref_rtb::Real, [unit = "N*m", description = "Robotics Toolbox torque"]
        ref_an::Real, [unit = "N*m", description = "Analytical torque"]
    end
    @outputs begin
        e_rtb::Real, [unit = "N*m", description = "tau - ref_rtb"]
        e_an::Real, [unit = "N*m", description = "tau - ref_an"]
    end
    @equations begin
        e_rtb ~ tau - ref_rtb
        e_an ~ tau - ref_an
    end
end
