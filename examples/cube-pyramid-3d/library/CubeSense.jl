@block CubeSense begin
    # Attitude and contact-load sensor of the pyramid cube (X-MB5): algebraic, no plant physics.
    #
    # Inputs are the cube pose `g` (quaternion first) and the normal forces `fn1..fn8` of the eight
    # vertex contacts. Vertex k (k = 1..8) sits at (x, y, z) = (+-h, +-h, +-h) with
    # k - 1 = bx + 2 by + 4 bz and the sign - for a zero bit; so vertices 1 and 2 form the edge
    # y = z = -h and vertex 1 is the corner (-h, -h, -h).
    #
    # Outputs
    #   ux, uy, uz   the world vertical seen from the body (third row of R(q))
    #   tilt         acos(uz): 0 on the face, 45 deg on the edge balance, atan(sqrt 2) = 54.7356 deg on
    #                the corner balance
    #   phie         atan2(uy, uz): the roll about the x axis (edge angle)
    #   px, py, zc   world position of the centre of mass
    #   sumfn        total normal force of the eight contacts
    #   ratio        sumfn / (m g0)
    #   nload        smooth count of loaded vertices, sum f^2 / (f^2 + f0^2) with f0 = 0.1 N: 1 for a
    #                vertex carrying more than about 1 N, 0 for a free vertex
    #   fedge        fn1 + fn2: the load of the two edge vertices
    @parameters begin
        m::Real = 1.2, [unit = "kg", min = 0, description = "Total mass"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration"]
        f0::Real = 0.1, [unit = "N", min = 1.0e-12, description = "Force at which a vertex counts as half loaded"]
    end
    @inputs begin
        g::Vec{7}
        fn1::Real, [unit = "N"]
        fn2::Real, [unit = "N"]
        fn3::Real, [unit = "N"]
        fn4::Real, [unit = "N"]
        fn5::Real, [unit = "N"]
        fn6::Real, [unit = "N"]
        fn7::Real, [unit = "N"]
        fn8::Real, [unit = "N"]
    end
    @outputs begin
        ux::Real, [unit = "1"]
        uy::Real, [unit = "1"]
        uz::Real, [unit = "1"]
        tilt::Real, [unit = "rad"]
        phie::Real, [unit = "rad"]
        zc::Real, [unit = "m"]
        px::Real, [unit = "m"]
        py::Real, [unit = "m"]
        sumfn::Real, [unit = "N"]
        ratio::Real, [unit = "1"]
        nload::Real, [unit = "1"]
        fedge::Real, [unit = "N"]
    end
    @variables s::Real = 1.0, [unit = "1", description = "Squared quaternion norm"]
    @equations begin
        s ~ g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4]
        ux ~ 2 * (g[2] * g[4] - g[1] * g[3]) / s
        uy ~ 2 * (g[3] * g[4] + g[1] * g[2]) / s
        uz ~ (g[1] * g[1] - g[2] * g[2] - g[3] * g[3] + g[4] * g[4]) / s
        tilt ~ acos(uz)
        phie ~ atan(uy, uz)
        zc ~ g[7]
        px ~ g[5]
        py ~ g[6]
        sumfn ~ fn1 + fn2 + fn3 + fn4 + fn5 + fn6 + fn7 + fn8
        ratio ~ sumfn / (m * g0)
        nload ~ fn1 * fn1 / (fn1 * fn1 + f0 * f0) + fn2 * fn2 / (fn2 * fn2 + f0 * f0) +
                fn3 * fn3 / (fn3 * fn3 + f0 * f0) + fn4 * fn4 / (fn4 * fn4 + f0 * f0) +
                fn5 * fn5 / (fn5 * fn5 + f0 * f0) + fn6 * fn6 / (fn6 * fn6 + f0 * f0) +
                fn7 * fn7 / (fn7 * fn7 + f0 * f0) + fn8 * fn8 / (fn8 * fn8 + f0 * f0)
        fedge ~ fn1 + fn2
    end
end
