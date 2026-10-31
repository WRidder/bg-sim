@block TransferFunction begin
    # Continuous transfer function y/u = num(s)/den(s) of order n, with the coefficients in
    # descending powers of s as in Simulink and MATLAB's `tf`:
    #   num[1]*s^n + num[2]*s^(n-1) + ... + num[n+1]
    #   --------------------------------------------
    #   den[1]*s^n + den[2]*s^(n-1) + ... + den[n+1]
    # The function is proper: num has as many coefficients as den (pad it with leading zeros);
    # num[1] other than zero is a direct feedthrough. den[1] must not be zero.
    #
    # Realisation: the controllable canonical form. z solves den(d/dt) z = u; the states are
    # its derivatives x[i] = z^(n-i) (x[1] the highest, x[n] = z itself), w[1] = z^(n) follows
    # from den . w = u, and y = num . w = num(d/dt) z. The states start at zero (a system at
    # rest); set the start of x for another initial state. For a high order with widely
    # spread poles, prefer ZeroPole or a cascade of SecondOrder blocks.
    @constants n::Int = 2, [min = 1, description = "Order: the degree of den and the number of states"]
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        num::Vec{n + 1} = [0.0, 0.0, 1.0], [description = "Numerator coefficients, highest power of s first"]
        den::Vec{n + 1} = [1.0, 2.0, 1.0], [description = "Denominator coefficients, highest power of s first; den[1] is not zero"]
    end
    @variables begin
        x::Vec{n}, [description = "States: x[i] is the (n-i)-th derivative of the canonical variable z"]
        w::Vec{n + 1}, [description = "w[i] is the (n+1-i)-th derivative of z"]
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
        y ~ dot(num, w)
    end
end
