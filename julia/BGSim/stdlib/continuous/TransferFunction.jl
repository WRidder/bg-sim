@block TransferFunction begin
    # Continuous transfer function y/u = num(s)/den(s) of order n, with the coefficients in
    # descending powers of s as in Simulink and MATLAB's `tf`:
    #   num[1]*s^m + num[2]*s^(m-1) + ... + num[m+1]
    #   --------------------------------------------
    #   den[1]*s^n + den[2]*s^(n-1) + ... + den[n+1]
    # The numerator degree m (at most n) is a structural constant, like the number of zeros
    # of ZeroPole: m = n has a direct feedthrough num[1]/den[1]; m < n is strictly proper,
    # so the block closes no algebraic loop. m defaults to n, so a numerator padded with
    # leading zeros to n + 1 coefficients works as before, but it keeps the feedthrough path
    # (with the value 0); give a strictly proper function its m + 1 coefficients and m < n
    # to use it inside a feedback loop. den[1] must not be zero.
    #
    # Realisation: the controllable canonical form. z solves den(d/dt) z = u; the states are
    # its derivatives x[i] = z^(n-i) (x[1] the highest, x[n] = z itself), w[1] = z^(n) follows
    # from den . w = u, and y = num(d/dt) z = num . w[n-m+1 .. n+1]. The states start at zero
    # (a system at rest); set the start of x for another initial state. For a high order with
    # widely spread poles, prefer ZeroPole or a cascade of SecondOrder blocks.
    @constants begin
        n::Int = 2, [min = 1, description = "Order: the degree of den and the number of states"]
        m::Int = n, [min = 0, description = "Numerator degree, at most n: m = n has a direct feedthrough, m < n is strictly proper"]
    end
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        num::Vec{m + 1} = [0.0, 0.0, 1.0], [description = "Numerator coefficients, highest power of s first"]
        den::Vec{n + 1} = [1.0, 2.0, 1.0], [description = "Denominator coefficients, highest power of s first; den[1] is not zero"]
    end
    @variables begin
        x::Vec{n}, [description = "States: x[i] is the (n-i)-th derivative of the canonical variable z"]
        w::Vec{n + 1}, [description = "w[i] is the (n+1-i)-th derivative of z"]
        v::Vec{m + 1}, [description = "The derivatives of z that the numerator weighs: v[j] = z^(m+1-j)"]
    end
    @equations begin
        dot(den, w) ~ u
        ddt(x[1]) ~ w[1]
        for i in 1:n
            w[i + 1] ~ x[i]
        end
        for i in 2:n
            ddt(x[i]) ~ x[i - 1]
        end
        for j in 1:m + 1
            v[j] ~ w[n - m + j]
        end
        y ~ dot(num, v)
    end
end
