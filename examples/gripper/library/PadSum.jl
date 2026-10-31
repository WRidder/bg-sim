@block PadSum begin
    # The four point contacts of one flat jaw pad on a flat part face, summed into the pad's
    # resultant for the grip monitor: the world force on the part, the normal force (the grip
    # force of the jaw), the mean slip speed and the friction utilisation: the mean of the four
    # contacts (a tilting moment loads them in torsion) and that of the resultant. A sensor, not
    # physics.
    @inputs begin
        F1::Vec{3}, [unit = "N", description = "World force of contact 1 on the part"]
        F2::Vec{3}, [unit = "N", description = "World force of contact 2 on the part"]
        F3::Vec{3}, [unit = "N", description = "World force of contact 3 on the part"]
        F4::Vec{3}, [unit = "N", description = "World force of contact 4 on the part"]
        fn1::Real, [unit = "N", description = "Normal force of contact 1"]
        fn2::Real, [unit = "N", description = "Normal force of contact 2"]
        fn3::Real, [unit = "N", description = "Normal force of contact 3"]
        fn4::Real, [unit = "N", description = "Normal force of contact 4"]
        s1::Real, [unit = "m/s", description = "Slip speed at contact 1"]
        s2::Real, [unit = "m/s", description = "Slip speed at contact 2"]
        s3::Real, [unit = "m/s", description = "Slip speed at contact 3"]
        s4::Real, [unit = "m/s", description = "Slip speed at contact 4"]
        u1::Real, [unit = "1", description = "Friction utilisation of contact 1"]
        u2::Real, [unit = "1", description = "Friction utilisation of contact 2"]
        u3::Real, [unit = "1", description = "Friction utilisation of contact 3"]
        u4::Real, [unit = "1", description = "Friction utilisation of contact 4"]
    end
    @outputs begin
        F::Vec{3}, [unit = "N", description = "Resultant world force of the pad on the part"]
        f_n::Real, [unit = "N", description = "Pad normal force (the grip force of this jaw)"]
        slip::Real, [unit = "m/s", description = "Mean slip speed of the four contacts"]
        util::Real, [unit = "1", description = "Mean friction utilisation of the four contacts (1 = sliding)"]
        util_res::Real, [unit = "1", description = "Utilisation of the resultant, |F_t| / (mu f_n + 0.01 N), 0 without contact: blind to the torsion of a tilting moment"]
    end
    @parameters begin
        mu::Real = 0.25, [unit = "1", min = 1.0e-6, description = "Pad friction coefficient"]
        nx::Real = 1.0, [unit = "1", description = "Pad normal, world x (unit)"]
        ny::Real = 0.0, [unit = "1", description = "Pad normal, world y (unit)"]
        nz::Real = 0.0, [unit = "1", description = "Pad normal, world z (unit)"]
    end
    @variables begin
        Fn::Real = 0.0, [unit = "N", description = "Normal component of the resultant"]
        Ft::Real = 0.0, [unit = "N", description = "Tangential magnitude of the resultant"]
    end
    @equations begin
        F[1] ~ F1[1] + F2[1] + F3[1] + F4[1]
        F[2] ~ F1[2] + F2[2] + F3[2] + F4[2]
        F[3] ~ F1[3] + F2[3] + F3[3] + F4[3]
        f_n ~ fn1 + fn2 + fn3 + fn4
        slip ~ 0.25 * (s1 + s2 + s3 + s4)
        Fn ~ nx * F[1] + ny * F[2] + nz * F[3]
        Ft ~ sqrt((F[1] - Fn * nx)^2 + (F[2] - Fn * ny)^2 + (F[3] - Fn * nz)^2 + 1.0e-12)
        util ~ 0.25 * (u1 + u2 + u3 + u4)
        util_res ~ Ft / (mu * f_n + 0.01)
    end
end
