@block HeliView begin
    # Scene helper (no physics): the poses of the A109 visuals. The 3D view keeps a reference
    # helicopter framed by moving the world instead of the camera: every pose is relative to the
    # reference's position, plus a formation slot (dx, dy, dz) and minus a constant drift
    # (vx, vy) t, so a helicopter in steady forward flight is shown relative to its trimmed path.
    #
    #   pose       the airframe (geometric body frame B)
    #   disc       the main rotor: at the hub, the shaft tilted forward by IS, the tip-path plane
    #              tilted by the flapping (a1 aft, b1 right) and the blades turned by the azimuth
    #   tail       the tail rotor at its hub, turned about the body y axis
    #   ground     the floor: at z_floor in the world, followed up and down by at most `reach`, under
    #              the reference helicopter; it does not move sideways, so its edges stay put
    #   stripes_x  the floor stripes across x (lines of constant x) and across y, at the floor's
    #   stripes_y  height, scrolling with the reference's ground track: each set along its own axis
    #              only, by the ground track wrapped into one stripe spacing `period` (-period/2 to
    #              period/2, 0 at the start), so the stripes stay on the floor. A wrap jumps by a whole
    #              period, which the pattern hides; the scene's bindings declare the period, so the 3D
    #              view interpolates across the wrap the short way instead of sliding the stripes back.
    #
    # The blades turn at `spin` times the real rotor speed (the real 385 rpm, 6.4 rev/s with 4
    # blades, strobes at a video's frame rate), the tail rotor at `spin` times its own speed.
    @inputs begin
        g::Vec{7}, [description = "Pose of this helicopter (qw, qx, qy, qz, x, y, z), geometric body frame"]
        g0::Vec{7}, [description = "Pose of the reference helicopter"]
        a1::Real, [description = "Longitudinal flapping, + aft (rad)"]
        b1::Real, [description = "Lateral flapping, + right (rad)"]
        om::Real, [description = "Rotor speed (rad/s)"]
    end
    @outputs begin
        pose::Vec{7}
        disc::Vec{7}
        tail::Vec{7}
        ground::Vec{7}
        stripes_x::Vec{7}
        stripes_y::Vec{7}
    end
    @parameters begin
        dx::Real = 0.0, [description = "Formation slot, x (north, m)"]
        dy::Real = 0.0, [description = "Formation slot, y (west, m)"]
        dz::Real = 0.0, [description = "Formation slot, z (up, m)"]
        vx::Real = 0.0, [description = "Drift subtracted from the position, x (m/s)"]
        vy::Real = 0.0, [description = "Drift subtracted from the position, y (m/s)"]
        z_floor::Real = 0.0, [description = "Floor height in the world (m)"]
        reach::Real = 300.0, [description = "Largest climb or descent the floor follows (m)"]
        period::Real = 20.0, [description = "Floor stripe spacing (m)"]
        hub_x::Real = 0.0, [description = "Hub in the body frame, x (m)"]
        hub_z::Real = 1.52, [description = "Hub in the body frame, z (m)"]
        IS::Real = 0.11, [description = "Shaft tilt, forward (rad)"]
        tr_x::Real = -6.56, [description = "Tail-rotor hub in the body frame, x (m)"]
        tr_y::Real = 0.25, [description = "Tail-rotor hub in the body frame, y (m)"]
        tr_z::Real = 0.8, [description = "Tail-rotor hub in the body frame, z (m)"]
        n_tr::Real = 5.4026, [description = "Tail-rotor to main-rotor speed ratio"]
        spin::Real = 0.1, [description = "Visual spin rate, fraction of the real one"]
    end
    @variables begin
        az::Real = 0.0, [state = :prefer, description = "Visual blade azimuth (rad)"]
        s::Real = 1.0
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0]
        cy::Real = 1.0
        sy::Real = 0.0
        cx::Real = 1.0
        sx::Real = 0.0
        cz::Real = 1.0
        sz::Real = 0.0
        ct::Real = 1.0
        st::Real = 0.0
        qt::Vec{4} = [1.0, 0.0, 0.0, 0.0], [description = "Tilt (shaft and flapping) then spin, in the body frame"]
        qr::Vec{4} = [1.0, 0.0, 0.0, 0.0], [description = "Tail-rotor spin about the body y axis"]
        ox::Real = 0.0
        oy::Real = 0.0
        oz::Real = 0.0
        zf::Real = 0.0, [description = "Floor height in the view (m)"]
    end
    @equations begin
        ddt(az) ~ spin * om
        s ~ g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4]
        R[1, 1] ~ (g[1] * g[1] + g[2] * g[2] - g[3] * g[3] - g[4] * g[4]) / s
        R[1, 2] ~ 2 * (g[2] * g[3] - g[1] * g[4]) / s
        R[1, 3] ~ 2 * (g[2] * g[4] + g[1] * g[3]) / s
        R[2, 1] ~ 2 * (g[2] * g[3] + g[1] * g[4]) / s
        R[2, 2] ~ (g[1] * g[1] - g[2] * g[2] + g[3] * g[3] - g[4] * g[4]) / s
        R[2, 3] ~ 2 * (g[3] * g[4] - g[1] * g[2]) / s
        R[3, 1] ~ 2 * (g[2] * g[4] - g[1] * g[3]) / s
        R[3, 2] ~ 2 * (g[3] * g[4] + g[1] * g[2]) / s
        R[3, 3] ~ (g[1] * g[1] - g[2] * g[2] - g[3] * g[3] + g[4] * g[4]) / s
        ox ~ g[5] - g0[5] - vx * t + dx
        oy ~ g[6] - g0[6] - vy * t + dy
        oz ~ g[7] - g0[7] + dz
        pose[1] ~ g[1]
        pose[2] ~ g[2]
        pose[3] ~ g[3]
        pose[4] ~ g[4]
        pose[5] ~ ox
        pose[6] ~ oy
        pose[7] ~ oz
        # tilt: about y by IS - a1 (the shaft forward, the disc aft with a1), then about x by b1
        # (FLU: + b1, the disc tilted right, is a rotation about +x), then the spin about z
        cy ~ cos(0.5 * (IS - a1))
        sy ~ sin(0.5 * (IS - a1))
        cx ~ cos(0.5 * b1)
        sx ~ sin(0.5 * b1)
        cz ~ cos(0.5 * az)
        sz ~ sin(0.5 * az)
        # (cy, 0, sy, 0) (x) (cx, sx, 0, 0) = (cy cx, cy sx, sy cx, -sy sx), then (x) (cz, 0, 0, sz)
        qt[1] ~ cy * cx * cz + sy * sx * sz
        qt[2] ~ cy * sx * cz + sy * cx * sz
        qt[3] ~ sy * cx * cz - cy * sx * sz
        qt[4] ~ cy * cx * sz - sy * sx * cz
        disc[1] ~ g[1] * qt[1] - g[2] * qt[2] - g[3] * qt[3] - g[4] * qt[4]
        disc[2] ~ g[1] * qt[2] + g[2] * qt[1] + g[3] * qt[4] - g[4] * qt[3]
        disc[3] ~ g[1] * qt[3] - g[2] * qt[4] + g[3] * qt[1] + g[4] * qt[2]
        disc[4] ~ g[1] * qt[4] + g[2] * qt[3] - g[3] * qt[2] + g[4] * qt[1]
        disc[5] ~ ox + R[1, 1] * hub_x + R[1, 3] * hub_z
        disc[6] ~ oy + R[2, 1] * hub_x + R[2, 3] * hub_z
        disc[7] ~ oz + R[3, 1] * hub_x + R[3, 3] * hub_z
        # tail rotor: about the body y axis by n_tr az
        ct ~ cos(0.5 * n_tr * az)
        st ~ sin(0.5 * n_tr * az)
        qr[1] ~ ct
        qr[2] ~ 0.0
        qr[3] ~ st
        qr[4] ~ 0.0
        tail[1] ~ g[1] * qr[1] - g[3] * qr[3]
        tail[2] ~ g[2] * qr[1] - g[4] * qr[3]
        tail[3] ~ g[3] * qr[1] + g[1] * qr[3]
        tail[4] ~ g[4] * qr[1] + g[2] * qr[3]
        tail[5] ~ ox + R[1, 1] * tr_x + R[1, 2] * tr_y + R[1, 3] * tr_z
        tail[6] ~ oy + R[2, 1] * tr_x + R[2, 2] * tr_y + R[2, 3] * tr_z
        tail[7] ~ oz + R[3, 1] * tr_x + R[3, 2] * tr_y + R[3, 3] * tr_z
        zf ~ clamp(z_floor - g0[7], -reach, reach) + dz
        ground[1] ~ 1.0
        ground[2] ~ 0.0
        ground[3] ~ 0.0
        ground[4] ~ 0.0
        ground[5] ~ 0.0
        ground[6] ~ 0.0
        ground[7] ~ zf
        stripes_x[1] ~ 1.0
        stripes_x[2] ~ 0.0
        stripes_x[3] ~ 0.0
        stripes_x[4] ~ 0.0
        stripes_x[5] ~ period * floor((g0[5] + period / 2) / period) - g0[5]
        stripes_x[6] ~ 0.0
        stripes_x[7] ~ zf
        stripes_y[1] ~ 1.0
        stripes_y[2] ~ 0.0
        stripes_y[3] ~ 0.0
        stripes_y[4] ~ 0.0
        stripes_y[5] ~ 0.0
        stripes_y[6] ~ period * floor((g0[6] + period / 2) / period) - g0[6]
        stripes_y[7] ~ zf
    end
end
