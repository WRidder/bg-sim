@block OrbitElements begin
    # The Keplerian orbit through the current state (a tap): apolune and perilune heights above
    # the mean radius from the energy and the angular momentum. Meaningful once the vehicle is on
    # an orbit (after insertion); on the ground it is the "orbit" of a body at rest, a degenerate
    # ellipse with its apolune at the surface.
    #
    #   E = v^2/2 - mu/r,  a = -mu / (2 E),  hm = |r x v|,  e = sqrt(1 + 2 E hm^2 / mu^2)
    @inputs begin
        g::Vec{7}, [description = "Body pose (qw, qx, qy, qz, x, y, z)"]
        V::Vec{6}, [description = "Body twist [w; v] in body axes"]
    end
    @parameters begin
        mu::Real = 4.9028e12, [unit = "m^3/s^2"]
        R::Real = 1737400.0, [unit = "m"]
    end
    @variables begin
        s2::Real
        vw::Vec{3}, [unit = "m/s"]
        rc::Vec{3}, [unit = "m"]
        r::Real, [unit = "m"]
        en::Real, [unit = "m^2/s^2"]
        a::Real, [unit = "m"]
        hm::Vec{3}, [unit = "m^2/s"]
        ecc::Real
    end
    @outputs begin
        apolune_km::Real
        perilune_km::Real
    end
    @equations begin
        s2 ~ g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4]
        vw[1] ~ ((g[1] * g[1] + g[2] * g[2] - g[3] * g[3] - g[4] * g[4]) * V[4] + 2 * (g[2] * g[3] - g[1] * g[4]) * V[5] + 2 * (g[2] * g[4] + g[1] * g[3]) * V[6]) / s2
        vw[2] ~ (2 * (g[2] * g[3] + g[1] * g[4]) * V[4] + (g[1] * g[1] - g[2] * g[2] + g[3] * g[3] - g[4] * g[4]) * V[5] + 2 * (g[3] * g[4] - g[1] * g[2]) * V[6]) / s2
        vw[3] ~ (2 * (g[2] * g[4] - g[1] * g[3]) * V[4] + 2 * (g[3] * g[4] + g[1] * g[2]) * V[5] + (g[1] * g[1] - g[2] * g[2] - g[3] * g[3] + g[4] * g[4]) * V[6]) / s2
        rc[1] ~ g[5]
        rc[2] ~ g[6]
        rc[3] ~ g[7] + R
        r ~ sqrt(rc[1] * rc[1] + rc[2] * rc[2] + rc[3] * rc[3])
        en ~ 0.5 * (vw[1] * vw[1] + vw[2] * vw[2] + vw[3] * vw[3]) - mu / r
        a ~ -mu / (2 * en)
        hm[1] ~ rc[2] * vw[3] - rc[3] * vw[2]
        hm[2] ~ rc[3] * vw[1] - rc[1] * vw[3]
        hm[3] ~ rc[1] * vw[2] - rc[2] * vw[1]
        ecc ~ sqrt(max(1 + 2 * en * (hm[1] * hm[1] + hm[2] * hm[2] + hm[3] * hm[3]) / (mu * mu), 0.0))
        apolune_km ~ (a * (1 + ecc) - R) / 1000
        perilune_km ~ (a * (1 - ecc) - R) / 1000
    end
end
