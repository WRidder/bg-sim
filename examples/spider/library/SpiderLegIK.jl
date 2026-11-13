@block SpiderLegIK begin
    # Analytic inverse kinematics of one T8X leg: coxa yaw about the body z axis, then the
    # two-link femur/tibia chain in the leg plane. The target `p` is the foot point in the
    # body frame; `hx, hy, hz` is the hip joint and `yaw` turns the hip x axis from the body
    # x axis. The joint frames in the model are exactly the chain used here:
    #
    #   hip = T(h) Rz(yaw),  C1 = Rz(q1),  F2 = T(a,0,0) Rx90,
    #   C2 = Rz(q2),          F3 = T(b,0,0),  C3 = Rz(q3),  foot = T(c,0,0).
    #
    # A target outside the annulus is projected onto the reachable annulus, so an aggressive
    # gait command bends the leg instead of asking the servo for a pose the chain cannot
    # reach. `reach` is 1 inside the annulus and falls linearly to 0 over the last `band`
    # before either limit: the straight leg (outer) or the folded leg (inner).
    @inputs p::Vec{3}, [unit = "m", description = "Foot point in the body frame"]
    @parameters begin
        hx::Real = 0.0, [unit = "m", description = "Hip x in the body frame"]
        hy::Real = 0.0, [unit = "m", description = "Hip y in the body frame"]
        hz::Real = 0.0, [unit = "m", description = "Hip z in the body frame"]
        yaw::Real = 0.0, [unit = "rad", description = "Hip x axis direction in the body frame"]
        a::Real = 0.045, [unit = "m", min = 1.0e-6, description = "Coxa length"]
        b::Real = 0.110, [unit = "m", min = 1.0e-6, description = "Femur length"]
        c::Real = 0.140, [unit = "m", min = 1.0e-6, description = "Tibia length"]
        d_margin::Real = 1.0e-4, [unit = "m", min = 1.0e-9, description = "Reach margin at the chain limits"]
        band::Real = 0.02, [unit = "m", min = 1.0e-9, description = "Width of the reach indicator band at either limit"]
    end
    @outputs begin
        q1::Real, [unit = "rad", description = "Coxa yaw"]
        q2::Real, [unit = "rad", description = "Femur angle in the leg plane, positive up"]
        q3::Real, [unit = "rad", description = "Tibia angle relative to the femur, negative bends down"]
        qcmd::Vec{3}, [unit = "rad", description = "The three joint commands"]
        reach::Real, [unit = "1", description = "1 inside the workspace, 0 at either clamped limit"]
        rho::Real, [unit = "m", description = "Horizontal distance from the hip to the foot"]
    end
    @variables begin
        dx::Real = 0.0, [unit = "m"]
        dy::Real = 0.0, [unit = "m"]
        x::Real = 0.0, [unit = "m"]
        z::Real = 0.0, [unit = "m"]
        d::Real = 0.0, [unit = "m"]
        dmin::Real = 0.0, [unit = "m"]
        dmax::Real = 0.0, [unit = "m"]
        dc::Real = 0.0, [unit = "m"]
        xs::Real = 0.0, [unit = "m"]
        zs::Real = 0.0, [unit = "m"]
        ck::Real = 0.0, [unit = "1"]
    end
    @equations begin
        dx ~ cos(yaw) * (p[1] - hx) + sin(yaw) * (p[2] - hy)
        dy ~ -sin(yaw) * (p[1] - hx) + cos(yaw) * (p[2] - hy)
        rho ~ sqrt(dx * dx + dy * dy)
        q1 ~ atan(dy / max(rho, 1.0e-9), dx / max(rho, 1.0e-9))
        x ~ rho - a
        z ~ p[3] - hz
        d ~ sqrt(x * x + z * z)
        dmin ~ abs(b - c) + d_margin
        dmax ~ b + c - d_margin
        dc ~ clamp(d, dmin, dmax)
        xs ~ x * dc / max(d, 1.0e-9)
        zs ~ z * dc / max(d, 1.0e-9)
        ck ~ clamp((dc * dc - b * b - c * c) / (2.0 * b * c), -1.0, 1.0)
        q3 ~ -acos(ck)
        q2 ~ atan(zs / max(dc, 1.0e-9), xs / max(dc, 1.0e-9)) -
              atan(c * sin(q3) / (b + c), (b + c * cos(q3)) / (b + c))
        reach ~ clamp(min(dmax - d, d - dmin) / band, 0.0, 1.0)
        qcmd[1] ~ q1
        qcmd[2] ~ q2
        qcmd[3] ~ q3
    end
end
