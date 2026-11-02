@block GearContact begin
    # The tyre-runway contact of one landing-gear leg: a power-conserving modulated multiport
    # transformer between the airframe's multibond and three translational bonds, one per contact
    # direction, on which the strut and the tyre elements sit:
    #
    #   n   the runway normal (up): flow = the penetration rate of the contact point; its
    #       1-junction carries the strut spring C (StrutSpring) and damper R (StrutDamper)
    #   x   along the wheel (the body x axis projected on the runway, turned by the nose-wheel
    #       steering angle): flow = the rolling speed; the rolling resistance and the brake R
    #       (WheelFriction)
    #   y   across the wheel: flow = the side-slip speed; the cornering force R (WheelSide)
    #
    # Mounting (as stdlib ContactPoint): FixedTransform3DNeutral with this element on side `a`
    # and the RigidBody3D on side `b`, mount pose = translation -r (the body origin seen from the
    # contact point; no rotation). The port flow is then the NEGATIVE point twist and the port
    # effort the wrench on the body in the point frame (the body axes):
    #
    #   v_world = -R p.f[4:6],     n.f = -v_world . z,   x.f = e_x . v_world,   y.f = e_y . v_world
    #   F_world = -n.e z + x.e e_x + y.e e_y,    p.e = [0; R^T F_world]
    #
    # so p.e . p.f + n.e n.f + x.e x.f + y.e y.f = 0. With the elements' efforts (power into each
    # element) n.e = -(strut force), x.e = -(rolling force), y.e = -(side force): the runway pushes
    # the wheel up and against its motion. `g` is the body pose (the contact point's height gives
    # the geometric penetration, an output for the host; the strut state carries it in the model).
    @ports begin
        p::Power{Spatial}
        n::Power{Translation}
        x::Power{Translation}
        y::Power{Translation}
    end
    @inputs begin
        g::Vec{7}, [description = "World pose of the airframe (qw, qx, qy, qz, x, y, z)"]
        steer::Real, [unit = "rad", description = "Wheel steering angle, positive right"]
    end
    @outputs begin
        fn::Real, [unit = "N", description = "Normal force on the wheel"]
        vx::Real, [unit = "m/s", description = "Rolling speed"]
        vy::Real, [unit = "m/s", description = "Side-slip speed"]
        delta::Real, [unit = "m", description = "Geometric penetration of the contact point"]
    end
    @parameters begin
        rx::Real = 0.0, [unit = "m", description = "Contact point from the CG, body x"]
        ry::Real = 0.0, [unit = "m", description = "Contact point, body y"]
        rz::Real = 0.0, [unit = "m", description = "Contact point, body z"]
        ground_z::Real = 0.0, [unit = "m", description = "Runway height (world z)"]
    end
    @variables begin
        s::Real = 1.0
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0]
        v1::Real = 0.0, [unit = "m/s"]
        v2::Real = 0.0, [unit = "m/s"]
        v3::Real = 0.0, [unit = "m/s"]
        hn::Real = 1.0
        hx::Real = 1.0
        hy::Real = 0.0
        ex1::Real = 1.0
        ex2::Real = 0.0
        F1::Real = 0.0, [unit = "N"]
        F2::Real = 0.0, [unit = "N"]
        F3::Real = 0.0, [unit = "N"]
    end
    @equations begin
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
        v1 ~ -(R[1, 1] * p.f[4] + R[1, 2] * p.f[5] + R[1, 3] * p.f[6])
        v2 ~ -(R[2, 1] * p.f[4] + R[2, 2] * p.f[5] + R[2, 3] * p.f[6])
        v3 ~ -(R[3, 1] * p.f[4] + R[3, 2] * p.f[5] + R[3, 3] * p.f[6])
        # the wheel axes on the runway
        hn ~ sqrt(R[1, 1] * R[1, 1] + R[2, 1] * R[2, 1])
        hx ~ R[1, 1] / hn
        hy ~ R[2, 1] / hn
        ex1 ~ cos(steer) * hx + sin(steer) * hy
        ex2 ~ -sin(steer) * hx + cos(steer) * hy
        n.f ~ -v3
        x.f ~ ex1 * v1 + ex2 * v2
        y.f ~ -ex2 * v1 + ex1 * v2
        F1 ~ x.e * ex1 - y.e * ex2
        F2 ~ x.e * ex2 + y.e * ex1
        F3 ~ -n.e
        p.e[1] ~ 0.0
        p.e[2] ~ 0.0
        p.e[3] ~ 0.0
        p.e[4] ~ R[1, 1] * F1 + R[2, 1] * F2 + R[3, 1] * F3
        p.e[5] ~ R[1, 2] * F1 + R[2, 2] * F2 + R[3, 2] * F3
        p.e[6] ~ R[1, 3] * F1 + R[2, 3] * F2 + R[3, 3] * F3
        fn ~ -n.e
        vx ~ x.f
        vy ~ y.f
        delta ~ ground_z - (g[7] + R[3, 1] * rx + R[3, 2] * ry + R[3, 3] * rz)
    end
    @causality begin
        p => (:effort_out, :fixed)
        n => :flow_out
        x => :flow_out
        y => :flow_out
    end
end
