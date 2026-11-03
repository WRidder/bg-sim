@block CylinderMount2D begin
    # Pin-to-pin kinematics of a hydraulic cylinder in the plane: the cylinder base pin A sits
    # on one body, the rod pin B on a body that turns about the joint J relative to it. From
    # the composed world poses (theta, x, y) of the two pins and of the joint:
    #
    #   L   = |B - A|                                pin-to-pin length (a kinematic result)
    #   n   = (B - A)/L                              unit vector A -> B
    #   r   = n . (k x (B - J)) = (-dx*(yB - yJ) + dy*(xB - xJ))/L
    #                                                moment arm dL/dtheta of the joint angle
    #   ext = L - L0                                 rod extension from the closed length
    #
    # `r` is the modulus of the modulated transformer between the cylinder rod and the joint
    # (rod speed = r * joint rate, joint torque = r * rod force): the virtual-work map of the
    # cylinder's force pair onto the joint coordinate. For the 3D view, `pb` is the head end
    # of the barrel (A + lb n) and `pr` the inner end of the rod (B - lr n), so the barrel and
    # the rod can be drawn as two bars A -> pb and pr -> B.
    @inputs begin
        gA::Vec{3}, [description = "World pose of the base pin A"]
        gB::Vec{3}, [description = "World pose of the rod pin B"]
        gJ::Vec{3}, [description = "World pose of the joint that B turns about relative to A's body"]
    end
    @outputs begin
        L::Real, [unit = "m"]
        r::Real, [unit = "m"]
        ext::Real, [unit = "m"]
        pb::Vec{2}, [unit = "m"]
        pr::Vec{2}, [unit = "m"]
    end
    @parameters begin
        L0::Real = 2.0, [unit = "m", min = 0, description = "Closed (fully retracted) pin-to-pin length"]
        lb::Real = 1.8, [unit = "m", min = 0, description = "Drawn barrel length, from the pin A"]
        lr::Real = 1.5, [unit = "m", min = 0, description = "Drawn rod length, from the pin B"]
    end
    @variables begin
        dx::Real = 1.0, [unit = "m", description = "xB - xA"]
        dy::Real = 0.0, [unit = "m", description = "yB - yA"]
    end
    @equations begin
        dx ~ gB[2] - gA[2]
        dy ~ gB[3] - gA[3]
        L ~ sqrt(dx * dx + dy * dy)
        r ~ (-dx * (gB[3] - gJ[3]) + dy * (gB[2] - gJ[2])) / L
        ext ~ L - L0
        pb[1] ~ gA[2] + lb * dx / L
        pb[2] ~ gA[3] + lb * dy / L
        pr[1] ~ gB[2] - lr * dx / L
        pr[2] ~ gB[3] - lr * dy / L
    end
end
