@block TetraSense begin
    # Attitude and contact-load sensor of the tetrahedron (X5.6): algebraic, no plant physics.
    #
    # Inputs are the body pose `g` (quaternion first) and the normal forces `fn1..fn4` of the four
    # vertex contacts. Vertex 1..3 are the base vertices (azimuth 90, 210, 330 deg, z = -r),
    # vertex 4 is the apex (0, 0, R), L the edge length, R = L sqrt 6 / 4, r = R / 3.
    #
    # Outputs
    #   ux, uy, uz   the world vertical seen from the body (third row of R(q))
    #   tilt         acos(uz): angle between the base normal (-z) and the downward vertical, i.e. 0 on the
    #                base face, 54.7356 deg on the edge v2-v3, 70.5288 deg on the vertex v3
    #   ang_edge     angle between u and the edge balance direction u_e = (0, sqrt(2/3), 1/sqrt 3)
    #   ang_vert     angle between u and the vertex balance direction u_v = -v3 / R
    #                = (-sqrt(2/3), sqrt(2)/3, 1/3)
    #   px, py, zc   world position of the centre of mass
    #   sumfn        total normal force of the four contacts
    #   ratio        sumfn / (m g0)
    #   nload        smooth count of loaded vertices, sum f^2 / (f^2 + f0^2) with f0 = 0.1 N: 1 for a
    #                vertex carrying more than about 1 N, 0 for a free vertex
    #   qerr         squared quaternion norm minus one (drift of the pose integrator)
    @parameters begin
        m::Real = 1.4, [unit = "kg", min = 0, description = "Total mass"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration"]
        f0::Real = 0.1, [unit = "N", min = 1.0e-12, description = "Force at which a vertex counts as half loaded"]
    end
    @inputs begin
        g::Vec{7}
        fn1::Real, [unit = "N"]
        fn2::Real, [unit = "N"]
        fn3::Real, [unit = "N"]
        fn4::Real, [unit = "N"]
    end
    @outputs begin
        ux::Real, [unit = "1"]
        uy::Real, [unit = "1"]
        uz::Real, [unit = "1"]
        tilt::Real, [unit = "rad"]
        ang_edge::Real, [unit = "rad"]
        ang_vert::Real, [unit = "rad"]
        zc::Real, [unit = "m"]
        px::Real, [unit = "m"]
        py::Real, [unit = "m"]
        sumfn::Real, [unit = "N"]
        ratio::Real, [unit = "1"]
        nload::Real, [unit = "1"]
        qerr::Real, [unit = "1"]
    end
    @variables s::Real = 1.0, [unit = "1", description = "Squared quaternion norm"]
    @equations begin
        s ~ g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4]
        ux ~ 2 * (g[2] * g[4] - g[1] * g[3]) / s
        uy ~ 2 * (g[3] * g[4] + g[1] * g[2]) / s
        uz ~ (g[1] * g[1] - g[2] * g[2] - g[3] * g[3] + g[4] * g[4]) / s
        tilt ~ acos(uz)
        ang_edge ~ acos(0.816496580927726 * uy + 0.5773502691896258 * uz)
        ang_vert ~ acos(-0.816496580927726 * ux + 0.4714045207910317 * uy + 0.3333333333333333 * uz)
        zc ~ g[7]
        px ~ g[5]
        py ~ g[6]
        sumfn ~ fn1 + fn2 + fn3 + fn4
        ratio ~ sumfn / (m * g0)
        nload ~ fn1 * fn1 / (fn1 * fn1 + f0 * f0) + fn2 * fn2 / (fn2 * fn2 + f0 * f0) +
                fn3 * fn3 / (fn3 * fn3 + f0 * f0) + fn4 * fn4 / (fn4 * fn4 + f0 * f0)
        qerr ~ s - 1
    end
end
