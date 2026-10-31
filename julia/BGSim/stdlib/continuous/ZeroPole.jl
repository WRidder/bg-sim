@block ZeroPole begin
    # Transfer function in zero-pole-gain form (Simulink's Zero-Pole, MATLAB's zpk):
    #   y/u = gain * (s - z[1]) * ... * (s - z[m]) / ((s - p[1]) * ... * (s - p[n]))
    # with n poles and m <= n zeros (proper). Each zero and pole is given as its real and
    # imaginary part: p[i] = pole_re[i] + j*pole_im[i]. A complex-conjugate pair takes two
    # consecutive entries that start at an odd index, (re, im) and (re, -im); a real root has
    # im = 0. Only the first m entries of zero_re/zero_im are used (m = 0: no zeros).
    #
    # Realisation: a cascade of sections, one per pair of entries, numerically robust at any
    # order. Section p (p odd, states p and p+1) has the poles p and p+1 and the zeros p and
    # p+1 that exist, as the controllable canonical form of
    #   (b2*s^2 + b1*s + b0) / (s^2 + a1*s + a0),
    #   a1 = -(pole_re[p] + pole_re[p+1]),  a0 = pole_re[p]*pole_re[p+1] - pole_im[p]*pole_im[p+1]
    # (b2 = 1 with two zeros, b2 = 0 and b1 = 1 with one, b0 = 1 with none); x[p] = z and
    # x[p+1] = z'. An odd n ends with the first-order section (s - z[n]) / (s - p[n]) or
    # 1 / (s - p[n]) on x[n]. c[p] is the input of the section starting at state p and c[p+1]
    # its output, so c[n] is the cascade output. The states start at zero.
    @constants begin
        n::Int = 2, [min = 1, description = "Number of poles: the order and the number of states"]
        m::Int = 1, [min = 0, description = "Number of zeros, at most n: the first m entries of zero_re and zero_im"]
    end
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        gain::Real = 6.0, [description = "Gain factor of the zero-pole product"]
        zero_re::Vec{n} = [-1.0, 0.0], [description = "Real parts of the zeros (the first m entries are used)"]
        zero_im::Vec{n} = [0.0, 0.0], [description = "Imaginary parts of the zeros; a conjugate pair is (re, im), (re, -im) from an odd index"]
        pole_re::Vec{n} = [-2.0, -3.0], [description = "Real parts of the poles"]
        pole_im::Vec{n} = [0.0, 0.0], [description = "Imaginary parts of the poles; a conjugate pair is (re, im), (re, -im) from an odd index"]
    end
    @variables begin
        x::Vec{n}, [description = "States: the canonical variable of each section and, for a second-order section, its derivative"]
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
            ddt(x[p]) ~ x[p + 1]
            ddt(x[p + 1]) ~ c[p] - (pole_re[p] * pole_re[p + 1] - pole_im[p] * pole_im[p + 1]) * x[p] +
                            (pole_re[p] + pole_re[p + 1]) * x[p + 1]
            # Two zeros: c[p] + (b0 - a0)*z + (b1 - a1)*z'; one zero: z' - z[p]*z; none: z.
            c[p + 1] ~ ifelse(
                m >= p + 1,
                c[p] + (zero_re[p] * zero_re[p + 1] - zero_im[p] * zero_im[p + 1] -
                        pole_re[p] * pole_re[p + 1] + pole_im[p] * pole_im[p + 1]) * x[p] +
                (pole_re[p] + pole_re[p + 1] - zero_re[p] - zero_re[p + 1]) * x[p + 1],
                ifelse(m >= p, x[p + 1] - zero_re[p] * x[p], x[p]),
            )
        end
        for p in 1:2 - n
            ddt(x[p]) ~ u + pole_re[p] * x[p]
            c[p] ~ ifelse(m >= p, u + (pole_re[p] - zero_re[p]) * x[p], x[p])
        end
        for p in max(3, n + 1 - mod(n, 2)):n
            ddt(x[p]) ~ c[p - 1] + pole_re[p] * x[p]
            c[p] ~ ifelse(m >= p, c[p - 1] + (pole_re[p] - zero_re[p]) * x[p], x[p])
        end
        y ~ gain * c[n]
    end
end
