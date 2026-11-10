@block GapController begin
    # Gap controller of one levitation module: full state feedback on the measured gap h, its
    # filtered derivative and the coil current i, with an integrator on the gap error and the
    # trim feedforward (gains from the LQR design in design/design.py):
    #   e_h  = h - h_ref
    #   i_ff = c_trim * h_ref                      (current that carries the weight at the gap h_ref)
    #   v_u  = R*i_ff + a1*e_h + a2*hd + a3*(i - i_ff) + a4*xi,    hd = (h - xf)/Tf
    #   v    = clamp(v_u, -v_max, v_max)           (the chopper rail)
    #   dxi/dt = e_h + (v - v_u)/(a4*Tt)           (back-calculation anti-windup, tracking time Tt)
    # A gap larger than the reference (the module sinks) raises the voltage: a1, a2, a4 > 0,
    # a3 < 0 is the current feedback.
    @inputs begin
        h::Real, [unit = "m", description = "Measured gap"]
        i::Real, [unit = "A", description = "Measured coil current"]
        h_ref::Real, [unit = "m", description = "Gap reference"]
    end
    @outputs begin
        v::Real, [unit = "V", description = "Voltage command to the chopper"]
        i_ff::Real, [unit = "A", description = "Trim current at the reference gap"]
        hd::Real, [unit = "m/s", description = "Filtered gap rate"]
    end
    @parameters begin
        a1::Real = 1.0e6, [unit = "V/m", description = "Gap feedback gain"]
        a2::Real = 7.0e3, [unit = "V*s/m", description = "Gap-rate feedback gain"]
        a3::Real = -50.0, [unit = "V/A", description = "Current feedback gain"]
        a4::Real = 1.0e6, [unit = "V/(m*s)", min = 1.0e-9, description = "Integral gain on the gap error"]
        Tf::Real = 0.001, [unit = "s", min = 1.0e-9, description = "Derivative filter time constant"]
        Tt::Real = 0.05, [unit = "s", min = 1.0e-9, description = "Anti-windup tracking time constant"]
        R::Real = 0.5, [unit = "Ohm", min = 0, description = "Coil resistance (trim voltage feedforward R*i_ff)"]
        c_trim::Real = 15000.0, [unit = "A/m", min = 0, description = "Trim law i = c_trim*h that carries the weight"]
        v_max::Real = 800.0, [unit = "V", min = 0, description = "Chopper voltage limit"]
    end
    @variables begin
        xf::Real = 0.01, [unit = "m", state = :prefer, description = "Derivative filter state"]
        xi::Real = 0.0, [unit = "m*s", state = :prefer, description = "Integral of the gap error"]
        v_u::Real = 0.0, [unit = "V", description = "Unlimited voltage command"]
    end
    @equations begin
        hd ~ (h - xf) / Tf
        ddt(xf) ~ hd
        i_ff ~ c_trim * h_ref
        v_u ~ R * i_ff + a1 * (h - h_ref) + a2 * hd + a3 * (i - i_ff) + a4 * xi
        v ~ clamp(v_u, -v_max, v_max)
        ddt(xi) ~ (h - h_ref) + (v - v_u) / (a4 * Tt)
    end
end
