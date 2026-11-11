@block Rotor3D begin
    # Axisymmetric rotor spinning about the z axis of its carrier body (a gyrostat): a
    # flywheel, a control-moment-gyro rotor or a reaction wheel, integrated in the CARRIER
    # frame. A spinning `RigidBody3D` on a `Revolute3D` sees its own body-frame quantities turn
    # at the spin rate, so the solver has to resolve every revolution; here only the axial
    # momentum is a state, so a 15 000 rpm flywheel costs no more than a still one.
    #
    # Mounting: the carrier body's port (`RigidBody3D.p`, a 1-junction) attaches DIRECTLY to
    # `p`, with the carrier frame's z axis along the spin axis and its origin on it. As for
    # `ContactPoint`, the port flow is the carrier twist and the port effort is minus the
    # wrench on the carrier. Put the rotor's mass and
    # its TRANSVERSE inertia into the carrier body (they do not depend on the spin angle); only
    # the axial inertia `Ja` lives here. The motor between carrier and rotor bonds to `drive`
    # (a Rotation port whose flow is the spin rate relative to the carrier and whose effort is
    # the motor torque on the rotor; its reaction acts on the carrier).
    #
    # With w = p.f[1:3] the carrier's angular velocity (body frame) and h the axial momentum
    # (the state, `h = Ja (w_z + w_rel)`):
    #
    #     dh/dt      = tau                        (tau = drive.e, the motor torque on the rotor)
    #     drive.f    = w_rel = h/Ja - w_z
    #     p.e        = [w_y h, -w_x h, tau, 0, 0, 0]
    #
    # `-p.e` is the wrench the rotor exerts on the carrier: the motor reaction `-tau e_z` and
    # the gyroscopic torque `-w x (h e_z)`. Power: `p.e . p.f + drive.e drive.f = tau h/Ja =
    # d/dt(h^2/(2 Ja))`,
    # the rotor's axial kinetic energy `Ek`, so the element is lossless; the gyroscopic part
    # `(w x h e_z) . w` is identically zero.
    @ports begin
        p::Power{Spatial}, [frame = "body"]
        drive::Power{Rotation}
    end
    @parameters begin
        Ja::Real = 1.0e-3, [unit = "kg*m^2", min = 1.0e-12, description = "Axial (spin) inertia of the rotor"]
    end
    @variables begin
        h::Real = 0.0, [unit = "N*m*s", state = :prefer, description = "Axial angular momentum Ja (w_z + w_rel)"]
    end
    @outputs begin
        w_rel::Real, [unit = "rad/s", description = "Spin rate relative to the carrier"]
        w_abs::Real, [unit = "rad/s", description = "Absolute axial spin rate h/Ja"]
        H::Real, [unit = "N*m*s", description = "Axial angular momentum"]
        Ek::Real, [unit = "J", description = "Axial kinetic energy h^2/(2 Ja)"]
    end
    @equations begin
        ddt(h) ~ drive.e
        drive.f ~ h / Ja - p.f[3]
        p.e[1] ~ p.f[2] * h
        p.e[2] ~ -p.f[1] * h
        p.e[3] ~ drive.e
        p.e[4] ~ 0.0
        p.e[5] ~ 0.0
        p.e[6] ~ 0.0
        w_rel ~ drive.f
        w_abs ~ h / Ja
        H ~ h
        Ek ~ 0.5 * h * h / Ja
    end
    @causality begin
        p => (:effort_out, :fixed)
        drive => :flow_out
    end
    @orientation begin
        p => :in
        drive => :in
    end
end
