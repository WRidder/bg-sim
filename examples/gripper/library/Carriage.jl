@block Carriage begin
    # The prescribed pick-and-place carriage (a Cartesian gantry flange): it only translates,
    # and its motion is the sum of the motion-profile moves. The horizontal transfer moves it
    # along y; the lift, lower and retreat moves add up along z. Its origin is the gripping
    # point between the jaw faces.
    #
    #   pc = (x0, y0 + y, z0 + z1 + z2 + z3),  vc = d/dt pc,  ac = d^2/dt^2 pc
    #
    # `pose` is the carriage pose on the D-MB6 chart (identity rotation) for the 3D view.
    @inputs begin
        yq::Real, [unit = "m", description = "Transfer move: position"]
        yv::Real, [unit = "m/s", description = "Transfer move: velocity"]
        ya::Real, [unit = "m/s^2", description = "Transfer move: acceleration"]
        z1q::Real, [unit = "m", description = "Lift move: position"]
        z1v::Real, [unit = "m/s", description = "Lift move: velocity"]
        z1a::Real, [unit = "m/s^2", description = "Lift move: acceleration"]
        z2q::Real, [unit = "m", description = "Lower move: position"]
        z2v::Real, [unit = "m/s", description = "Lower move: velocity"]
        z2a::Real, [unit = "m/s^2", description = "Lower move: acceleration"]
        z3q::Real, [unit = "m", description = "Retreat move: position"]
        z3v::Real, [unit = "m/s", description = "Retreat move: velocity"]
        z3a::Real, [unit = "m/s^2", description = "Retreat move: acceleration"]
    end
    @outputs begin
        pc::Vec{3}, [unit = "m", description = "Carriage (gripping point) position in the world"]
        vc::Vec{3}, [unit = "m/s", description = "Carriage velocity in the world"]
        ac::Vec{3}, [unit = "m/s^2", description = "Carriage acceleration in the world"]
        pose::Vec{7}, [description = "Carriage pose (qw, qx, qy, qz, x, y, z) for the 3D view"]
        a_h::Real, [unit = "m/s^2", description = "Horizontal acceleration"]
        a_v::Real, [unit = "m/s^2", description = "Vertical acceleration"]
    end
    @parameters begin
        x0::Real = 0.0, [unit = "m", description = "Start position x"]
        y0::Real = 0.0, [unit = "m", description = "Start position y"]
        z0::Real = 0.0, [unit = "m", description = "Start position z"]
    end
    @equations begin
        pc[1] ~ x0
        pc[2] ~ y0 + yq
        pc[3] ~ z0 + z1q + z2q + z3q
        vc[1] ~ 0.0
        vc[2] ~ yv
        vc[3] ~ z1v + z2v + z3v
        ac[1] ~ 0.0
        ac[2] ~ ya
        ac[3] ~ z1a + z2a + z3a
        pose[1] ~ 1.0
        pose[2] ~ 0.0
        pose[3] ~ 0.0
        pose[4] ~ 0.0
        pose[5] ~ pc[1]
        pose[6] ~ pc[2]
        pose[7] ~ pc[3]
        a_h ~ ac[2]
        a_v ~ ac[3]
    end
end
