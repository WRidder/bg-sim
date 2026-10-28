@block Revolute2D begin
    # Native minimal joint for J-MB4; J-MB6 replaces it with a composite of documented
    # primitives (the signal-wiring probe in NOTES.md records why it is native here).
    # Frames are neutral so one joint joins any two body frames (D-MB5: null unifies).
    @ports begin
        parent::Power{Planar}
        child::Power{Planar}
        drive::Power{Rotation}
    end
    @parameters begin
        rx::Real = 0.0, [unit = "m", description = "Joint axis point x in the parent frame"]
        ry::Real = 0.0, [unit = "m", description = "Joint axis point y in the parent frame"]
        q0::Real = 0.0, [unit = "rad", description = "Initial joint angle"]
    end
    # `int` is the language's sugar for a state: q = q0 + integral(qdot), so the start
    # value is the q0 parameter and the integrated state is the hidden `__bgint` variable.
    @variables q::Real = 0.0, [unit = "rad", description = "Joint angle"]
    @outputs begin
        qout::Real, [unit = "rad"]
        qdout::Real, [unit = "rad/s"]
        pose::Vec{3}
    end
    @equations begin
        # g(q) = (q, rx, ry): the child frame sits at the axis point and turns by q.
        # S = [1, ry, -rx] (plan 3.1). The four relations below are the frozen joint
        # equations; they are power-continuous:
        #   child.f = Ad(g)^-1 parent.f + S qdot, parent.e = -Ad(g)^-T child.e,
        #   drive.e = -S^T child.e, qdot = drive.f.
        child.f[1] ~ parent.f[1] + qdout
        child.f[2] ~ (sin(q) * rx - cos(q) * ry) * parent.f[1] + cos(q) * parent.f[2] +
                     sin(q) * parent.f[3] + ry * qdout
        child.f[3] ~ (cos(q) * rx + sin(q) * ry) * parent.f[1] - sin(q) * parent.f[2] +
                     cos(q) * parent.f[3] - rx * qdout
        parent.e[1] ~ -(child.e[1] + (sin(q) * rx - cos(q) * ry) * child.e[2] +
                        (cos(q) * rx + sin(q) * ry) * child.e[3])
        parent.e[2] ~ -(cos(q) * child.e[2] - sin(q) * child.e[3])
        parent.e[3] ~ -(sin(q) * child.e[2] + cos(q) * child.e[3])
        drive.e ~ -(child.e[1] + ry * child.e[2] - rx * child.e[3])
        qdout ~ drive.f
        q ~ q0 + int(qdout, 0.0)
        qout ~ q
        pose[1] ~ q
        pose[2] ~ rx
        pose[3] ~ ry
    end
    @causality begin
        # The frozen joint equations give BOTH body ports effort-out causality in an
        # anchored chain: the body twist arrives through the child and the ground twist
        # through the parent, and the joint computes qdot. A 2-port :transformer relation
        # would force the child to impose flow instead and push the body inertia into
        # derivative causality (W201), so the three ports declare their own preferences.
        parent => :effort_out
        child => :effort_out
        drive => :flow_out
    end
end
