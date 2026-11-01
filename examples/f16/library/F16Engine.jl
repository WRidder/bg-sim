@block F16Engine begin
    # The F100 engine model of Stevens & Lewis (Section 3.6, subroutines TGEAR, PDOT, RTAU, THRUST):
    # the throttle sets a commanded power level through a gearing with an afterburner knee at
    # 0.77, the actual power level `pow` (percent, 0..100; 50 is military power) follows with a
    # first-order lag whose rate depends on the power change (RTAU: 1/s for small changes,
    # down to 0.1/s for large ones; 5/s while crossing into or out of afterburner), and the
    # thrust blends the idle, military and maximum tables (inputs, in N, from stdlib Lookup2D
    # blocks over altitude and Mach) with the power level.
    @inputs begin
        thtl::Real, [description = "Throttle, 0..1"]
        tidl::Real, [unit = "N", description = "Idle thrust T_idle(h, Mach)"]
        tmil::Real, [unit = "N", description = "Military thrust T_mil(h, Mach)"]
        tmax::Real, [unit = "N", description = "Maximum (afterburner) thrust T_max(h, Mach)"]
    end
    @outputs begin
        thrust::Real, [unit = "N"]
        pow::Real, [description = "Power level, percent"]
        cpow::Real, [description = "Commanded power level (TGEAR), percent"]
    end
    @variables begin
        P::Real = 0.0, [state = :prefer, description = "Power level state, percent"]
        p2::Real = 0.0, [description = "Power level the lag is heading for"]
        rt::Real = 1.0, [description = "Lag rate (1/s)"]
        dp::Real = 0.0, [description = "Power change the rate is looked up for (RTAU)"]
        rt_mil::Real = 1.0, [description = "RTAU(cpow - P): the rate below the afterburner"]
        rt_ab::Real = 1.0, [description = "RTAU(60 - P): the rate heading into the afterburner"]
    end
    @equations begin
        cpow ~ ifelse(thtl <= 0.77, 64.94 * thtl, 217.38 * thtl - 117.38)
        p2 ~ ifelse(cpow >= 50.0, ifelse(P >= 50.0, cpow, 60.0), ifelse(P >= 50.0, 40.0, cpow))
        dp ~ ifelse(cpow >= 50.0, 60.0 - P, cpow - P)
        # RTAU(dp) = 1 for dp <= 25, 0.1 for dp >= 50, 1.9 - 0.036 dp in between, which is exactly
        # clamp(1.9 - 0.036 dp, 0.1, 1). It is evaluated on the two continuous branches of dp and
        # the branch is picked afterwards: dp itself jumps when cpow crosses 50, and a switching
        # condition that jumps across zero at another switch makes the event handling chatter.
        rt_mil ~ clamp(1.9 - 0.036 * (cpow - P), 0.1, 1.0)
        rt_ab ~ clamp(1.9 - 0.036 * (60.0 - P), 0.1, 1.0)
        rt ~ ifelse(P >= 50.0, 5.0, ifelse(cpow >= 50.0, rt_ab, rt_mil))
        ddt(P) ~ rt * (p2 - P)
        pow ~ P
        thrust ~ ifelse(P < 50.0, tidl + (tmil - tidl) * P * 0.02, tmil + (tmax - tmil) * (P - 50.0) * 0.02)
    end
end
