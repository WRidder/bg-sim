@block BucketLinkage2D begin
    # Closure of the bucket four-bar, in the arm frame (origin the arm pin C, x towards the
    # bucket pin Q). The links: the arm itself (ground link R -> Q), the bucket (crank Q -> P,
    # turned by the bucket angle q), the H-link (coupler P -> J, length lc) and the rocker or
    # side link (R -> J, length lr). For the bucket angle q:
    #
    #   P   = Q + Rot(q) (Px, Py)                    bucket link pin
    #   J   = R + a e + s h n,   a = (lr^2 - lc^2 + |P - R|^2)/(2|P - R|),  h = sqrt(lr^2 - a^2)
    #                                                rocker/H-link junction (e = (P - R)/|P - R|,
    #                                                n = k x e, s = +-1 the assembly branch)
    #   phi = atan2(J - R)                           rocker angle
    #   k   = dphi/dq = ((J - P) . (k x (P - Q))) / ((J - P) . (k x (J - R)))
    #
    # `k` is the modulus of the modulated transformer between the rocker (where the bucket
    # cylinder pushes) and the bucket joint: the velocity ratio of the four-bar. The links are
    # massless (their mass is lumped into the arm and the bucket), so the four-bar is a pure
    # kinematic transformer. `gJ` is the local pose of J on the rocker, (phi, xJ, yJ), to be
    # composed with the arm pose; `mu` the transmission angle between rocker and H-link.
    @inputs q::Real, [unit = "rad", description = "Bucket joint angle relative to the arm"]
    @outputs begin
        gJ::Vec{3}
        gP::Vec{3}
        k::Real, [unit = "1"]
        phi::Real, [unit = "rad"]
        hlink::Real, [unit = "rad"]
        mu::Real, [unit = "rad"]
    end
    @parameters begin
        Qx::Real = 2.9, [unit = "m", description = "Bucket pin x in the arm frame (the arm length)"]
        Rx::Real = 2.54, [unit = "m", description = "Rocker pivot x in the arm frame"]
        Ry::Real = 0.052, [unit = "m", description = "Rocker pivot y in the arm frame"]
        Px::Real = 0.193, [unit = "m", description = "Bucket link pin x in the bucket frame"]
        Py::Real = 0.359, [unit = "m", description = "Bucket link pin y in the bucket frame"]
        lr::Real = 0.725, [unit = "m", min = 1.0e-6, description = "Rocker (side link) length R -> J"]
        lc::Real = 0.714, [unit = "m", min = 1.0e-6, description = "H-link length J -> P"]
        branch::Real = 1.0, [unit = "1", description = "Assembly branch: +1 J left of R -> P, -1 right"]
    end
    @variables begin
        xP::Real = 3.0, [unit = "m", description = "Link pin P, x"]
        yP::Real = 0.3, [unit = "m", description = "Link pin P, y"]
        dist::Real = 0.5, [unit = "m", description = "|P - R|"]
        ex::Real = 1.0, [unit = "1", description = "Unit vector R -> P, x"]
        ey::Real = 0.0, [unit = "1", description = "Unit vector R -> P, y"]
        a::Real = 0.25, [unit = "m", description = "Distance from R to the chord foot along e"]
        h::Real = 0.5, [unit = "m", description = "Distance of J from the line R -> P"]
        xJ::Real = 3.0, [unit = "m", description = "Junction J, x"]
        yJ::Real = 0.5, [unit = "m", description = "Junction J, y"]
    end
    @equations begin
        xP ~ Qx + cos(q) * Px - sin(q) * Py
        yP ~ sin(q) * Px + cos(q) * Py
        dist ~ sqrt((xP - Rx)^2 + (yP - Ry)^2)
        ex ~ (xP - Rx) / dist
        ey ~ (yP - Ry) / dist
        a ~ (lr * lr - lc * lc + dist * dist) / (2.0 * dist)
        h ~ sqrt(lr * lr - a * a)
        xJ ~ Rx + a * ex - branch * h * ey
        yJ ~ Ry + a * ey + branch * h * ex
        phi ~ atan((yJ - Ry) / lr, (xJ - Rx) / lr)
        k ~ ((xJ - xP) * (-yP) + (yJ - yP) * (xP - Qx)) /
            ((xJ - xP) * (-(yJ - Ry)) + (yJ - yP) * (xJ - Rx))
        hlink ~ atan((yP - yJ) / lc, (xP - xJ) / lc) - phi
        mu ~ acos(-((xJ - Rx) * (xP - xJ) + (yJ - Ry) * (yP - yJ)) / (lr * lc))
        gJ[1] ~ phi
        gJ[2] ~ xJ
        gJ[3] ~ yJ
        gP[1] ~ q
        gP[2] ~ xP
        gP[3] ~ yP
    end
end
