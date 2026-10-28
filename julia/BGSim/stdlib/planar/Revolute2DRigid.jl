@block Revolute2DRigid begin
    # The **rigid** planar revolute joint as a bond-graph composite (plan 5.2):
    #
    #   parent ── 0-junction ── JointTransform2D(Ad(q)) ── child
    #                  │
    #               ScrewTF(S)
    #                  │
    #            1-junction ── Df ── Integrator ── q
    #                  │
    #               drive (Rotation)
    #
    # The 0-junction makes the wrench continuous across the joint (parent, the adjoint
    # transform and the screw all see the same effort) and the 1-junction carries the joint
    # rate: `drive` and the `Df` share the screw flow, the `Df` reads `qdot`, and the
    # integrator turns it into `q` (the initial angle is `JointPose2D.theta0`). The pose is
    # composed from `q`, never integrated (D-MB6).
    #
    # **This variant is a 3-DOF body on a 1-DOF joint, so it is index-3 by construction**
    # (D-MB7, DEC-MB-2): the two pivot translations are hard constraints, `mtkcompile` puts
    # two body momentum components in derivative causality, and the run reports **exactly two
    # W201** (the two constrained translations). That is the designed behaviour, not a bug:
    # the compliant variant (`stdlib:multibond/Revolute2D`, `Revolute2DCompliant`) is the
    # default. `kt -> Inf` on the compliant pivot converges to this joint's period.
    #
    # The `drive` port has `Rotation` causality (D-MB8: the domain follows the screw), so a
    # torque source bonds to it directly.
    @ports begin
        parent::Power{Planar}, [frame = "world"]
        child::Power{Planar}, [frame = "body"]
        drive::Power{Rotation}
    end
    @parameters begin
        rx::Real = 0.0, [unit = "m", description = "Pivot x in the parent frame"]
        ry::Real = 0.0, [unit = "m", description = "Pivot y in the parent frame"]
        q0::Real = 0.0, [unit = "rad", description = "Initial joint angle"]
    end
    @outputs qout::Real, [unit = "rad"]
    @outputs qdout::Real, [unit = "rad/s"]
    @outputs pose::Vec{3}
    @components begin
        node = Junction(0)
        xform = TFAd()
        screw = ScrewTF(rx = rx, ry = ry)
        axis = Junction(1)
        rate = Df()
        qint = Integrator()
        jointpose = JointPose2D(rx = rx, ry = ry, theta0 = q0)
    end
    @connections begin
        connect(parent, node)
        connect(node, xform.a)
        connect(node, screw.a)
        connect(xform.b, child)
        connect(screw.b, axis)
        connect(drive, axis)
        connect(rate.p, axis)
        connect(rate.y, qint.u)
        connect(qint.y, jointpose.q)
        connect(qint.y, qout)
        connect(rate.y, qdout)
        connect(jointpose.g, xform.g)
        connect(jointpose.g, pose)
    end
end
