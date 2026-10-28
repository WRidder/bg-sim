@block FixedJoint2D begin
    # A rigid fixed connection between two bodies: the child pose in the parent frame is the
    # constant `(theta, x, y)`, and the frame bridge is the only legal way between the joint
    # role frames `parent` and `child` (D-MB5). `ComposePose2D` composes the *pose* of a
    # fixed-base chain; this block carries the *power* through the same constant adjoint.
    #
    # The equations are written in the causal direction of a parent -> child chain
    # (FIX-MB-2): `parent` has flow-out causality (it receives the parent effort and imposes
    # the parent flow) and `child` effort-out (it imposes the child effort and received the
    # child flow). Concretely `parent.f = -Ad(g) child.f` and `child.e = Ad(g)^T parent.e`;
    # the two are exactly `child.e = Ad(g)^-T parent.e`, but written this way MTK's alias
    # elimination never has to solve the 2x2 rotation block implicitly. Written the other way
    # round it eliminates one row by dividing by sin(theta), which is singular at theta = 0
    # and is why the J-MB4 slice only ran near +-pi/2. Power continuity is exact:
    # `parent.e . parent.f + child.e . child.f = 0`.
    @ports begin
        # `parent` is frame-neutral: it adopts the joint's child frame (a joint port leaves it
        # neutral) or another body frame. `child` declares the body frame, so the fixed joint
        # is the world(body) -> body bridge of a chain and the only block that has to name a
        # frame (D-MB5).
        parent::Power{Planar}
        child::Power{Planar}, [frame = "body"]
    end
    @parameters begin
        x::Real = 0.0, [unit = "m", description = "Child origin x in the parent frame"]
        y::Real = 0.0, [unit = "m", description = "Child origin y in the parent frame"]
        theta::Real = 0.0, [unit = "rad", description = "Child frame angle in the parent frame"]
    end
    @outputs pose::Vec{3}
    @equations begin
        parent.f[1] ~ -child.f[1]
        parent.f[2] ~ -(y * child.f[1] + cos(theta) * child.f[2] - sin(theta) * child.f[3])
        parent.f[3] ~ x * child.f[1] - sin(theta) * child.f[2] - cos(theta) * child.f[3]
        child.e[1] ~ parent.e[1] + y * parent.e[2] - x * parent.e[3]
        child.e[2] ~ cos(theta) * parent.e[2] + sin(theta) * parent.e[3]
        child.e[3] ~ -sin(theta) * parent.e[2] + cos(theta) * parent.e[3]
        pose[1] ~ theta
        pose[2] ~ x
        pose[3] ~ y
    end
    @causality (parent, child) => :transformer
end
