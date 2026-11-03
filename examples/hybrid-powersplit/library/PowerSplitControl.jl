@block PowerSplitControl begin
    # The hybrid control unit below the energy manager (continuous): it holds the engine at the
    # operating point the EnergyManager chose and makes the wheels deliver the driver's force.
    #
    #   references   w_f' = (w_ref - w_f)/tau_w,  T_f' = (on T_ref - T_f)/tau_T (smooth steps)
    #   engine       fire = on (1 + tanh((w_e - w_fire)/w_fw_e))/2: fuel and spark fade in as
    #                MG1 cranks the engine through w_fire (a hard switch there made the
    #                solver chatter on w_e = w_fire); the engine torque command
    #                T_e = fire min(T_f, T_wot), the throttle thr = T_e / T_wot. Unfired, the
    #                engine drags with its friction and pumping torque (the Willans friction
    #                of the fuel model, f0 + f1 w + f2 w^2, tanh-smoothed sign): T_drag
    #   MG1          speed control of the engine through the sun gear: a PI on w_f - w_e
    #                (anti-windup by back-calculation) plus the reaction-torque feed-forward
    #                -Zs/(Zs+Zr) T_e:  T_g = clamp(-Zs/(Zs+Zr) T_e + Kp (e + x), +-T1_max)
    #   MG2          fills in the ring torque: the ring needs T_rd = F_dem r_w / FD and gets
    #                -(Zr/Zs) T_g through the planetary set, so T_m = T_rd + (Zr/Zs) T_g,
    #                within the MG2 envelope min(T2_max, P2_max/|w_r|) and the battery power
    #                limits (discharge: MG2's electrical power T w + R2 T^2/k2^2 within what
    #                MG1 leaves of P_dis); while braking the regenerative torque fades out
    #                around w_fade (a tanh step of width w_fw), where the friction brakes
    #                take over
    #   brakes       the braking torque MG2 cannot take goes to the friction brakes:
    #                T_m,lo = smax(T_m,raw, T_lo) (a hyperbolic smooth max, width dT),
    #                T_m = min(T_m,lo, T_hi), T_b = FD (T_m,lo - T_m,raw) at the wheels, so
    #                MG2 and the brakes always sum to the demand. A hard clamp here slides
    #                along T_m,raw = T_lo while the regenerative limit fades (event chatter).
    #                The brake is a modulated R (T = u w_w) with u = T_b / sqrt(w_w^2 + w_beps^2)
    #   inverters    each machine is a DC-equivalent PM machine (stdlib EMConverter, constant k)
    #                with the stator resistance R_s and a small stator inductance behind its
    #                inverter (MTF from the DC bus). The inverter applies v = k w + R_s T/k, so
    #                the machine torque follows T with the stator time constant L/R_s = 10 ms:
    #                the MTF modulus is d = v / V_bus.
    @inputs begin
        F_dem::Real, [unit = "N", description = "Driver's tractive force demand"]
        on::Real, [unit = "1", description = "Engine runs (EnergyManager)"]
        w_ref::Real, [unit = "rad/s", description = "Engine speed reference"]
        T_ref::Real, [unit = "N*m", description = "Engine torque reference"]
        w_e::Real, [unit = "rad/s", description = "Engine speed"]
        w_s::Real, [unit = "rad/s", description = "Sun (MG1) speed"]
        w_r::Real, [unit = "rad/s", description = "Ring (MG2) speed"]
        w_w::Real, [unit = "rad/s", description = "Wheel speed"]
        V::Real, [unit = "V", description = "DC bus voltage"]
        T_wot::Real, [unit = "N*m", description = "Full-load engine torque at the present speed"]
    end
    @outputs begin
        thr::Real, [unit = "1", description = "Throttle 0..1"]
        fire::Real, [unit = "1", description = "Fuel and spark: 1 on, 0 off (fades in around w_fire)"]
        d1::Real, [unit = "1", description = "MG1 inverter modulus (machine voltage / bus voltage)"]
        d2::Real, [unit = "1", description = "MG2 inverter modulus"]
        u_b::Real, [unit = "N*m*s/rad", description = "Friction brake modulus (brake torque per wheel speed)"]
        T_e::Real, [unit = "N*m", description = "Engine torque command"]
        T_drag::Real, [unit = "N*m", description = "Friction and pumping drag of the engine while it turns without fuel"]
        T_g::Real, [unit = "N*m", description = "MG1 torque"]
        T_m::Real, [unit = "N*m", description = "MG2 torque"]
        T_b::Real, [unit = "N*m", description = "Friction brake torque at the wheels"]
        T_rd::Real, [unit = "N*m", description = "Ring torque the driver demands"]
        P_brk::Real, [unit = "W", description = "Braking power the driver demands at the ring (smooth positive part of -T_rd w_r)"]
    end
    @parameters begin
        Zs::Real = 30.0, [unit = "1", description = "Sun teeth"]
        Zr::Real = 78.0, [unit = "1", description = "Ring teeth"]
        FD::Real = 4.113, [unit = "1", description = "Ring to axle ratio"]
        r_w::Real = 0.3, [unit = "m", description = "Rolling radius"]
        tau_w::Real = 0.3, [unit = "s", min = 1.0e-6, description = "Speed reference filter"]
        tau_T::Real = 0.3, [unit = "s", min = 1.0e-6, description = "Torque reference filter"]
        w_fire::Real = 83.8, [unit = "rad/s", description = "Engine firing speed (fuel and spark half on)"]
        w_fw_e::Real = 5.0, [unit = "rad/s", min = 1.0e-6, description = "Width of the fuel and spark fade-in around w_fire"]
        f0::Real = 7.0, [unit = "N*m", description = "Engine friction torque: constant part"]
        f1::Real = 0.00955, [unit = "N*m*s/rad", description = "Engine friction torque: linear part"]
        f2::Real = 1.824e-5, [unit = "N*m*s^2/rad^2", description = "Engine friction torque: quadratic part"]
        w_d::Real = 5.0, [unit = "rad/s", min = 1.0e-6, description = "Speed smoothing of the drag direction"]
        Kp::Real = 0.7, [unit = "N*m*s/rad", description = "MG1 engine speed PI: gain"]
        Ti::Real = 0.5, [unit = "s", min = 1.0e-6, description = "MG1 engine speed PI: integral time"]
        Tt::Real = 0.2, [unit = "s", min = 1.0e-6, description = "MG1 engine speed PI: anti-windup time"]
        T1_max::Real = 70.0, [unit = "N*m", description = "MG1 torque limit"]
        T2_max::Real = 400.0, [unit = "N*m", description = "MG2 torque limit"]
        P2_max::Real = 50000.0, [unit = "W", description = "MG2 power limit"]
        P_dis::Real = 21000.0, [unit = "W", description = "Battery discharge power limit"]
        P_chg::Real = 25000.0, [unit = "W", description = "Battery charge power limit"]
        w_fade::Real = 25.0, [unit = "rad/s", description = "Ring speed at which the regenerative torque has faded to half (25 rad/s: 6.6 km/h)"]
        w_fw::Real = 5.0, [unit = "rad/s", min = 1.0e-6, description = "Width of the regenerative fade-out"]
        w_eps::Real = 1.0, [unit = "rad/s", min = 1.0e-6, description = "Speed regularisation of P/|w|"]
        dT::Real = 1.0, [unit = "N*m", min = 1.0e-6, description = "Smoothing of the regenerative/friction brake blend"]
        w_beps::Real = 0.5, [unit = "rad/s", min = 1.0e-6, description = "Wheel speed smoothing of the friction brake"]
        k1::Real = 0.477, [unit = "V*s/rad", description = "MG1 torque constant (DC equivalent)"]
        R1::Real = 0.15, [unit = "Ohm", description = "MG1 stator resistance (DC equivalent)"]
        k2::Real = 0.796, [unit = "V*s/rad", description = "MG2 torque constant (DC equivalent)"]
        R2::Real = 0.062, [unit = "Ohm", description = "MG2 stator resistance (DC equivalent)"]
    end
    @variables begin
        wf::Real = 0.0, [unit = "rad/s", state = :prefer, description = "Filtered engine speed reference"]
        Tf::Real = 0.0, [unit = "N*m", state = :prefer, description = "Filtered engine torque reference"]
        x::Real = 0.0, [unit = "rad/s", state = :prefer, description = "MG1 speed PI integral state"]
        e::Real = 0.0, [unit = "rad/s", description = "Engine speed error"]
        Tg_raw::Real = 0.0, [unit = "N*m"]
        aw::Real = 1.0, [unit = "rad/s"]
        Tl2::Real = 400.0, [unit = "N*m", description = "MG2 torque envelope"]
        Pg::Real = 0.0, [unit = "W", description = "MG1 electrical power (mechanical plus copper loss)"]
        Pav::Real = 0.0, [unit = "W", description = "Battery discharge power left for MG2"]
        Thi::Real = 0.0, [unit = "N*m"]
        Tlo::Real = 0.0, [unit = "N*m"]
        Tm_raw::Real = 0.0, [unit = "N*m"]
        Tm_lo::Real = 0.0, [unit = "N*m", description = "MG2 torque above the regenerative limit (smooth max)"]
    end
    @equations begin
        ddt(wf) ~ (w_ref - wf) / tau_w
        ddt(Tf) ~ (on * T_ref - Tf) / tau_T
        fire ~ on * 0.5 * (1.0 + tanh((w_e - w_fire) / w_fw_e))
        T_e ~ fire * min(Tf, T_wot)
        T_drag ~ (1.0 - fire) * (f0 + f1 * sqrt(w_e * w_e + 1.0) + f2 * w_e * w_e) * tanh(w_e / w_d)
        thr ~ T_e / max(T_wot, 1.0)
        e ~ wf - w_e
        Tg_raw ~ -Zs / (Zs + Zr) * T_e + Kp * (e + x)
        T_g ~ clamp(Tg_raw, -T1_max, T1_max)
        ddt(x) ~ e / Ti + (T_g - Tg_raw) / (Kp * Tt)
        T_rd ~ F_dem * r_w / FD
        aw ~ sqrt(w_r * w_r + w_eps * w_eps)
        Tl2 ~ min(T2_max, P2_max / aw)
        Pg ~ T_g * w_s + R1 * T_g * T_g / (k1 * k1)
        Pav ~ max(P_dis - Pg, 0.0)
        Thi ~ min(Tl2, 2.0 * Pav / (aw + sqrt(aw * aw + 4.0 * R2 / (k2 * k2) * Pav)))
        Tlo ~ -max(min(Tl2, (P_chg + Pg) / aw), 0.0) * 0.5 * (1.0 + tanh((w_r - w_fade) / w_fw))
        P_brk ~ 0.5 * (sqrt(T_rd * w_r * T_rd * w_r + 1.0) - T_rd * w_r)
        Tm_raw ~ T_rd + Zr / Zs * T_g
        Tm_lo ~ 0.5 * (Tm_raw + Tlo + sqrt((Tm_raw - Tlo) * (Tm_raw - Tlo) + dT * dT))
        T_m ~ min(Tm_lo, Thi)
        T_b ~ FD * (Tm_lo - Tm_raw)
        u_b ~ T_b / sqrt(w_w * w_w + w_beps * w_beps)
        d1 ~ (k1 * w_s + R1 * T_g / k1) / V
        d2 ~ (k2 * w_r + R2 * T_m / k2) / V
    end
end
