@block BeaverPitchAP begin
    # The symmetric channel of the FDC 'Beaver' autopilot [FDC apilot/aplib.mdl, REP chapter 11]:
    # pitch attitude hold (PAH) with the altitude hold (ALH) as its outer loop. FDC 1.4 works in
    # radians with 1 V of servo command = 1 deg, so the gains are rad/rad; they are scheduled on
    # the true airspeed V (m/s):
    #
    #   Ktheta = -1.375e-3 V^2 + 0.1575 V - 4.8031      Kq = -4.75e-4 V^2 + 0.054 V - 1.5931 (s)
    #   Kd = -2.5e-3 V + 0.2875 (1/s)                   KH = (-1e-4 V^2 + 0.015 V - 0.5975) pi/180 (rad/m)
    #
    #   dtheta_ref = clamp(PAH: theta_ref - theta0, ALH: KH (H_ref - H)/Ktheta;  -8 .. 18 deg)
    #   e   = dtheta_ref - [(theta - theta0) - clamp(Kd xw, +-20 deg)]     (washout xw in ALH)
    #   u1  = clamp(Ktheta e, +-2 deg),   d(I)/dt = 0.5 u1, I limited to +-10 deg
    #   de  = u1 + I - Kq (q - tc)
    #   tc  = r tan(phi) + Ktc (1/cos(phi + dphi) - 1)   turn compensation;
    #         PAH: Ktc = 5e-4 V^2 - 0.03 V + 0.9375, dphi = 0;  ALH: Ktc = 0.03 V + 0.25, dphi = 0.03491
    #
    # Ours (see the README): mode 0 off (output 0, the integrator bleeds to zero in t_off), 1 PAH,
    # 2 ALH; absolute references; the limited integrator as back-calculation (t_aw); the ALH turn
    # compensation in ALH (FDC's switch always picks the PAH formula).
    @inputs begin
        mode::Real, [description = "0 off, 1 pitch attitude hold, 2 altitude hold"]
        theta::Real
        q::Real
        r::Real
        phi::Real
        V::Real
        H::Real
        theta_ref::Real, [description = "Pitch attitude reference (PAH)"]
        H_ref::Real, [description = "Altitude reference (ALH)"]
    end
    @outputs begin
        de::Real, [description = "Elevator servo command (1 V = 1 deg)"]
        dth_ref::Real, [description = "Limited pitch-attitude reference, relative to theta0"]
    end
    @parameters begin
        theta0::Real = 0.0, [description = "Trim pitch angle"]
        t_aw::Real = 0.05, [description = "Back-calculation time of the limited integrator"]
        t_off::Real = 0.5, [description = "Bleed time of the integrator while the loop is off"]
    end
    @variables begin
        I::Real = 0.0, [state = :prefer, description = "Integrator (rad)"]
        xw::Real = 0.0, [state = :prefer, description = "Washout state (rad s)"]
        Kth::Real = 0.0
        Kq::Real = 0.0
        Kd::Real = 0.0
        KH::Real = 0.0
        on::Real = 0.0
        alh::Real = 0.0
        e::Real = 0.0
        u1::Real = 0.0
        Il::Real = 0.0
        tc::Real = 0.0
    end
    @equations begin
        on ~ ifelse(mode > 0.5, 1.0, 0.0)
        alh ~ ifelse(mode > 1.5, 1.0, 0.0)
        Kth ~ -1.375e-3 * V * V + 0.1575 * V - 4.8031
        Kq ~ -4.75e-4 * V * V + 0.054 * V - 1.5931
        Kd ~ -2.5e-3 * V + 0.2875
        KH ~ (-1.0e-4 * V * V + 0.015 * V - 0.5975) * 0.017453292519943295
        dth_ref ~ clamp(ifelse(alh > 0.5, KH * (H_ref - H) / Kth, theta_ref - theta0), -0.13962634015954636, 0.3141592653589793)
        e ~ dth_ref - ((theta - theta0) - clamp(Kd * xw, -0.3490658503988659, 0.3490658503988659))
        u1 ~ clamp(Kth * e, -0.03490658503988659, 0.03490658503988659)
        Il ~ clamp(I, -0.17453292519943295, 0.17453292519943295)
        tc ~ ifelse(alh > 0.5,
                    r * tan(phi) + (0.03 * V + 0.25) * (1.0 / cos(phi + 0.03491) - 1.0),
                    r * tan(phi) + (5.0e-4 * V * V - 0.03 * V + 0.9375) * (1.0 / cos(phi) - 1.0))
        de ~ on * (u1 + Il - Kq * (q - tc))
        ddt(I) ~ ifelse(on > 0.5, 0.5 * u1 + (Il - I) / t_aw, -I / t_off)
        ddt(xw) ~ alh * (theta - theta0) - Kd * xw
    end
end
