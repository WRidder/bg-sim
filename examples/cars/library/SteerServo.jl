@block SteerServo begin
    # The steering rack and column of one front wheel as a stiff position servo on the steering
    # joint (an `MSe` on the `Revolute3D` drive): the torque about the steering axis that pulls
    # the joint angle to the commanded road-wheel angle,
    #
    #   tau = k (ref - q) - c qd
    #
    # i.e. the torsional stiffness and damping of the linkage seen at the wheel. The tyre's
    # moments about the steering axis deflect the wheel by tau/k (steering compliance).
    @inputs begin
        ref::Real, [unit = "rad", description = "Commanded road-wheel angle"]
        q::Real, [unit = "rad", description = "Steering joint angle"]
        qd::Real, [unit = "rad/s", description = "Steering joint rate"]
    end
    @outputs tau::Real, [unit = "N*m", description = "Torque on the steering joint"]
    @parameters begin
        k::Real = 2.0e4, [unit = "N*m/rad", min = 0, description = "Steering stiffness at the wheel"]
        c::Real = 300.0, [unit = "N*m*s/rad", min = 0, description = "Steering damping at the wheel"]
    end
    @equations tau ~ k * (ref - q) - c * qd
end
