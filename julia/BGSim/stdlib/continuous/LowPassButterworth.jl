@block LowPassButterworth begin
    # Butterworth low-pass filter of order n (1 to 8): the maximally flat magnitude
    # |y/u| = k / sqrt(1 + (w/wc)^(2n)), so the gain is k/sqrt(2) (-3 dB) at the cutoff wc
    # for every order. The frequency is angular (rad/s).
    #
    # Realisation: a cascade of second-order sections (numerically robust at every order,
    # unlike one polynomial of degree n). Section p (states p and p+1, p odd) is
    #   wc^2 / (s^2 + 2*zeta_p*wc*s + wc^2),  zeta_p = sin(p*pi/(2n)),
    # with x[p] its output and x[p+1] its derivative divided by wc; an odd order ends with the
    # first-order section wc / (s + wc) on x[n]. c[p] is the input of the section starting at
    # state p and c[p+1] its output, so c[n] is the cascade output. Every section has unit DC
    # gain, and the states start at zero (a filter at rest).
    @constants n::Int = 2, [min = 1, max = 8, description = "Filter order: the number of poles and states"]
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        k::Real = 1.0, [description = "DC gain"]
        wc::Real = 10.0, [unit = "rad/s", min = 1.0e-9, description = "Cutoff frequency, where the gain is k/sqrt(2) (-3 dB)"]
    end
    @variables begin
        x::Vec{n}, [description = "States: each section's output and, for a second-order section, its derivative over wc"]
        c::Vec{n}, [description = "Cascade signals: input and output of each section"]
    end
    @equations begin
        for p in 1:2:min(1, n - 1)
            c[p] ~ u
        end
        for p in 3:2:n - 1
            c[p] ~ c[p - 1]
        end
        for p in 1:2:n - 1
            ddt(x[p]) ~ wc * x[p + 1]
            ddt(x[p + 1]) ~ wc * (c[p] - x[p] - 2.0 * sin(p * 3.141592653589793 / (2 * n)) * x[p + 1])
            c[p + 1] ~ x[p]
        end
        for p in 1:2 - n
            ddt(x[p]) ~ wc * (u - x[p])
            c[p] ~ x[p]
        end
        for p in max(3, n + 1 - mod(n, 2)):n
            ddt(x[p]) ~ wc * (c[p - 1] - x[p])
            c[p] ~ x[p]
        end
        y ~ k * c[n]
    end
end
