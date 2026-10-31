@block GripperPath begin
    # The robot, as a prescribed motion: the tool centre point (TCP, placed at the parcel's
    # centre of mass) follows the transfer profile along world x and the sum of the lift, lower
    # and retract profiles along world z; the gripper frame G (the cup mount plane, z up) is
    # turned by the fixed yaw `psi` about z (the cup pattern relative to the path) and by the
    # tilt `theta` about world y (the "waiter's tray"):
    #
    #   R_G = Ry(theta) Rz(psi),   p_G = p_TCP - R_G r_TCP,
    #   theta_cmd = theta_max tanh(k_tilt atan(a_p / (g0 + a_z)) / theta_max),
    #   theta'' = w_f^2 (theta_cmd - theta) - 2 z_f w_f theta'       (tilt servo, 2nd order)
    #
    # where a_p is the path acceleration previewed by the servo lag 2 z_f / w_f (a copy of the
    # transfer profile started that much earlier: the robot knows its trajectory), so the tilt
    # arrives with the acceleration instead of after it.
    #
    # With `k_tilt = 1` the cup axes follow the specific force (a_x, 0, g0 + a_z) that the
    # cups must supply, and the parcel's centre of mass is the tilt pivot (the tilt adds no
    # linear acceleration at the parcel). Outputs: the pose `g` and the body twist `tw` of G
    # (for a `SfSpatial` on the gripper bond), and display poses for the 3D scene: `gfl` the
    # untilted flange point `h_fl` above G (the Z axis tube), `gcar` the gantry carriage.
    @inputs begin
        xq::Real, [unit = "m", description = "Transfer position (from x0)"]
        xv::Real, [unit = "m/s", description = "Transfer velocity"]
        xa::Real, [unit = "m/s^2", description = "Transfer acceleration"]
        xj::Real, [unit = "m/s^3", description = "Transfer jerk"]
        ap::Real, [unit = "m/s^2", description = "Previewed transfer acceleration (tilt command)"]
        zq1::Real
        zv1::Real
        za1::Real
        zq2::Real
        zv2::Real
        za2::Real
        zq3::Real
        zv3::Real
        za3::Real
    end
    @parameters begin
        x0::Real = 0.0, [unit = "m", description = "TCP start x"]
        z0::Real = 0.15, [unit = "m", description = "TCP start z"]
        psi::Real = 0.0, [unit = "rad", description = "Yaw of the cup pattern relative to the path"]
        k_tilt::Real = 0.0, [unit = "1", min = 0, description = "Tilt gain: 1 aligns the cup axes with the specific force"]
        th_max::Real = 0.35, [unit = "rad", min = 1.0e-6, description = "Largest tilt"]
        w_f::Real = 15.0, [unit = "rad/s", min = 1.0e-6, description = "Bandwidth of the tilt servo"]
        z_f::Real = 1.0, [unit = "1", min = 0, description = "Damping ratio of the tilt servo"]
        g0::Real = 9.81, [unit = "m/s^2", description = "Gravity"]
        tx::Real = 0.0, [unit = "m", description = "TCP x in G"]
        ty::Real = 0.0, [unit = "m", description = "TCP y in G"]
        tz::Real = -0.19, [unit = "m", description = "TCP z in G"]
        h_fl::Real = 0.12, [unit = "m", description = "Flange height above G (display)"]
        z_beam::Real = 1.6, [unit = "m", description = "Gantry carriage height (display)"]
    end
    @variables begin
        th::Real = 0.0, [unit = "rad", state = :prefer, description = "Tilt about world y"]
        thd::Real = 0.0, [unit = "rad/s", state = :prefer, description = "Tilt rate"]
        thc::Real = 0.0, [unit = "rad", description = "Tilt command"]
        zv::Real = 0.0, [unit = "m/s", description = "TCP vertical velocity"]
        cth::Real = 1.0, [unit = "1", description = "cos(theta)"]
        sth::Real = 0.0, [unit = "1", description = "sin(theta)"]
        cps::Real = 1.0, [unit = "1", description = "cos(psi)"]
        sps::Real = 0.0, [unit = "1", description = "sin(psi)"]
        w1::Real = 0.0, [unit = "m", description = "R_G r_TCP, x"]
        w2::Real = 0.0, [unit = "m", description = "R_G r_TCP, y"]
        w3::Real = 0.0, [unit = "m", description = "R_G r_TCP, z"]
        vgx::Real = 0.0, [unit = "m/s", description = "Velocity of G, world x"]
        vgz::Real = 0.0, [unit = "m/s", description = "Velocity of G, world z"]
    end
    @outputs begin
        g::Vec{7}
        tw::Vec{6}
        gfl::Vec{7}
        gcar::Vec{7}
        x::Real, [unit = "m", description = "TCP x"]
        z::Real, [unit = "m", description = "TCP z"]
        ax::Real, [unit = "m/s^2", description = "TCP acceleration along the path"]
        az::Real, [unit = "m/s^2", description = "TCP vertical acceleration"]
        jerk::Real, [unit = "m/s^3", description = "TCP jerk along the path"]
        theta::Real, [unit = "rad", description = "Gripper tilt"]
    end
    @equations begin
        x ~ x0 + xq
        z ~ z0 + zq1 + zq2 + zq3
        zv ~ zv1 + zv2 + zv3
        ax ~ xa
        az ~ za1 + za2 + za3
        jerk ~ xj
        thc ~ th_max * tanh(k_tilt * atan(ap / (g0 + az)) / th_max)
        ddt(th) ~ thd
        ddt(thd) ~ w_f * w_f * (thc - th) - 2 * z_f * w_f * thd
        theta ~ th
        cth ~ cos(th)
        sth ~ sin(th)
        cps ~ cos(psi)
        sps ~ sin(psi)
        w1 ~ cth * cps * tx - cth * sps * ty + sth * tz
        w2 ~ sps * tx + cps * ty
        w3 ~ -sth * cps * tx + sth * sps * ty + cth * tz
        vgx ~ xv - thd * w3
        vgz ~ zv + thd * w1
        g[1] ~ cos(0.5 * th) * cos(0.5 * psi)
        g[2] ~ sin(0.5 * th) * sin(0.5 * psi)
        g[3] ~ sin(0.5 * th) * cos(0.5 * psi)
        g[4] ~ cos(0.5 * th) * sin(0.5 * psi)
        g[5] ~ x - w1
        g[6] ~ -w2
        g[7] ~ z - w3
        tw[1] ~ thd * sps
        tw[2] ~ thd * cps
        tw[3] ~ 0.0
        tw[4] ~ cth * cps * vgx - sth * cps * vgz
        tw[5] ~ -cth * sps * vgx + sth * sps * vgz
        tw[6] ~ sth * vgx + cth * vgz
        gfl[1] ~ 1.0
        gfl[2] ~ 0.0
        gfl[3] ~ 0.0
        gfl[4] ~ 0.0
        gfl[5] ~ x - w1 + h_fl * sth
        gfl[6] ~ -w2
        gfl[7] ~ z - w3 + h_fl * cth
        gcar[1] ~ 1.0
        gcar[2] ~ 0.0
        gcar[3] ~ 0.0
        gcar[4] ~ 0.0
        gcar[5] ~ x - w1 + h_fl * sth
        gcar[6] ~ 0.0
        gcar[7] ~ z_beam
    end
end
