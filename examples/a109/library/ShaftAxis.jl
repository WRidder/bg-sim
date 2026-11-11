@block ShaftAxis begin
    # A transformer between the airframe (a spatial multibond) and the rotor shaft (a rotation
    # bond): the shaft port's flow is the airframe's angular velocity about the shaft axis k,
    # its effort the shaft torque, which acts on the airframe as the torque k tau.
    #
    # Bond it like a contact, from the frame it is mounted on to this element (body -> b of a
    # FixedTransform3DNeutral at the hub, its `a` -> `p`): the spatial port then carries the
    # frame's twist and the negative wrench on the airframe. With `s` on the mast 0-junction,
    #
    #     s.f   = -k . omega        (so the 0-junction gives Omega_rotor = Omega_rel + k . omega)
    #     p.e   = [k s.e; 0]        (the airframe feels -k tau, the reaction of the mast torque)
    #
    # and p.e . p.f + s.e s.f = 0: the element is power-continuous. Only the torque about the
    # shaft passes; the rotor's flapping carries its other moments to the hub (MainRotor), so the
    # rotor's transverse gyroscopic moment is not added a second time here.
    @ports begin
        p::Power{Spatial}
        s::Power{Rotation}
    end
    @parameters begin
        kx::Real = 0.0, [description = "Shaft axis in the port frame, x"]
        ky::Real = 0.0, [description = "Shaft axis in the port frame, y"]
        kz::Real = 1.0, [description = "Shaft axis in the port frame, z"]
    end
    @equations begin
        s.f ~ -(kx * p.f[1] + ky * p.f[2] + kz * p.f[3])
        p.e[1] ~ kx * s.e
        p.e[2] ~ ky * s.e
        p.e[3] ~ kz * s.e
        p.e[4] ~ 0.0
        p.e[5] ~ 0.0
        p.e[6] ~ 0.0
    end
    @causality (p, s) => :transformer
    @orientation begin
        p => :in
        s => :out
    end
end
