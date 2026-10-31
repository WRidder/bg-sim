@block LowPassBessel begin
    # Bessel (Thomson) low-pass filter of order n (1 to 8): the maximally flat group delay, so
    # a step response with (almost) no overshoot. The poles are those of the reverse Bessel
    # polynomial, scaled so that the gain is k/sqrt(2) (-3 dB) at the cutoff wc for every
    # order (the magnitude normalisation, as Modelica's Filter and scipy's norm = "mag"). The
    # frequency is angular (rad/s).
    #
    # Realisation: a cascade of second-order sections, as in LowPassButterworth. Section p
    # (states p and p+1, p odd) is wp^2 / (s^2 + 2*zeta*wp*s + wp^2) with wp = W[n, p]*wc and
    # zeta = Z[n, p]; an odd order ends with the first-order section wr / (s + wr) on x[n],
    # wr = W[n, n]*wc. Row n of the tables W (natural frequency over wc) and Z (damping
    # ratio) holds order n: the sections in the odd columns, the real pole of an odd order in
    # column n. g[i] is the natural frequency of the section that state i belongs to. x[p] is
    # the section output and x[p+1] its derivative divided by wp; every section has unit DC
    # gain, and the states start at zero (a filter at rest).
    @constants n::Int = 2, [min = 1, max = 8, description = "Filter order: the number of poles and states"]
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        k::Real = 1.0, [description = "DC gain"]
        wc::Real = 10.0, [unit = "rad/s", min = 1.0e-9, description = "Cutoff frequency, where the gain is k/sqrt(2) (-3 dB)"]
    end
    @variables begin
        x::Vec{n}, [description = "States: each section's output and, for a second-order section, its derivative over wp"]
        c::Vec{n}, [description = "Cascade signals: input and output of each section"]
        g::Vec{n}, [unit = "rad/s", description = "Natural frequency of the section of each state"]
    end
    @equations begin
        for i in 1:n
            g[i] ~ wc * [
                1.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
                1.2720196495140699 0.0 0.0 0.0 0.0 0.0 0.0 0.0
                1.4476171331469878 0.0 1.322675799910447 0.0 0.0 0.0 0.0 0.0
                1.4301715599939893 0.0 1.603357516216976 0.0 0.0 0.0 0.0 0.0
                1.5563471222968852 0.0 1.7553777766370988 0.0 1.5023162714475584 0.0 0.0 0.0
                1.603919128773764 0.0 1.6891682676204964 0.0 1.9047076123027553 0.0 0.0 0.0
                1.7163560448708837 0.0 1.822417478857984 0.0 2.0494909002691037 0.0 1.6843681792731648 0.0
                1.7784659117746113 0.0 1.8320926011986656 0.0 1.9531957590219993 0.0 2.188726230527449 0.0
            ][n, i - 1 + mod(i, 2)]
        end
        for p in 1:2:min(1, n - 1)
            c[p] ~ u
        end
        for p in 3:2:n - 1
            c[p] ~ c[p - 1]
        end
        for p in 1:2:n - 1
            ddt(x[p]) ~ g[p] * x[p + 1]
            ddt(x[p + 1]) ~ g[p] * (c[p] - x[p] - 2.0 * [
                0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
                0.8660254037844386 0.0 0.0 0.0 0.0 0.0 0.0 0.0
                0.7235401799452065 0.0 0.0 0.0 0.0 0.0 0.0 0.0
                0.9579744618591075 0.0 0.620702965049499 0.0 0.0 0.0 0.0 0.0
                0.8872553597313634 0.0 0.545567205708492 0.0 0.0 0.0 0.0 0.0
                0.9797815709183962 0.0 0.8180701260408895 0.0 0.48860860162243663 0.0 0.0 0.0
                0.9392216556951538 0.0 0.7566341043105731 0.0 0.44394819245303574 0.0 0.0 0.0
                0.9881597329285687 0.0 0.8934807209284286 0.0 0.7033812208999677 0.0 0.40794033826328835 0.0
            ][n, p] * x[p + 1])
            c[p + 1] ~ x[p]
        end
        for p in 1:2 - n
            ddt(x[p]) ~ g[p] * (u - x[p])
            c[p] ~ x[p]
        end
        for p in max(3, n + 1 - mod(n, 2)):n
            ddt(x[p]) ~ g[p] * (c[p - 1] - x[p])
            c[p] ~ x[p]
        end
        y ~ k * c[n]
    end
end
