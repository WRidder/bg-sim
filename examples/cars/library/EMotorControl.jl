@block EMotorControl begin
    # Inverter and motor control of one traction motor. The motor itself is the modulated
    # transformer `TractionMachine` between the battery bus (dc: voltage, current) and the rotor
    # 1-junction (shaft: torque, speed) of the vehicle bond graph: shaft.e = u dc.e,
    # dc.f = -u shaft.f, so the rotor torque is u V and the bus current u w (power conserving, the
    # losses are the battery resistance and the rotor drag).
    # This block sets the modulus u for the torque command tau:
    #
    #   envelope   Tlim = min(T_max, P_max/|w|) (1 - tanh((|w| - w_max)/w_cut))/2
    #              (constant torque up to the base speed P_max/T_max, constant power above,
    #              a soft speed limit at w_max)
    #   drive      tau_d = thr Tlim (1 - 2 rev) clamp(soc/0.02) tc, with the traction
    #              control tc = clamp(((1 + kappa_tc) v + v_tc - |w| R_w/n)/v_band): the torque fades
    #              out when the driven wheels run faster than the vehicle speed v allows
    #   regen      the brake system asks `dem` at the wheels of this axle (the pedal times the
    #              axle's friction brake torque); the motor takes what it can,
    #              min(dem/n, min(T_regen, P_regen/|w|)) clamp((1-soc)/0.02), against the motion
    #              (tanh(w/w_fade): it fades out near standstill); `regen` is that torque at the
    #              wheels, n treg tanh(w/w_fade) w/|w| (a smooth |tanh|), never more than `dem`,
    #              so the friction brakes' share dem - regen needs no clamp at zero
    #   modulus    the bus voltage at the bus power P + p_aux (P = tau w, p_aux the other motors
    #              on the bus) is the root of V^2 - ocv V + R (P + p_aux) = 0
    #              (battery ocv and R), V = (ocv + sqrt(ocv^2 - 4 R (P + p_aux)))/2, u = tau/V
    #              makes the rotor torque exactly tau (explicit: no algebraic loop)
    #
    # The pedal inputs are used as they come (0..1; the host and the stimuli keep them in range).
    # A clamp would put a kink at the released pedal, and a pedal that comes to rest exactly at 0
    # would sit on that kink for the rest of the run.
    @inputs begin
        thr::Real, [unit = "1", description = "Accelerator pedal 0..1"]
        dem::Real, [unit = "N*m", description = "Brake torque the brake system asks at the wheels of this axle (both wheels)"]
        rev::Real, [unit = "1", description = "Reverse: 0 forward, 1 reverse"]
        w::Real, [unit = "rad/s", description = "Rotor speed"]
        ocv::Real, [unit = "V", description = "Battery open-circuit voltage"]
        soc::Real, [unit = "1", description = "Battery state of charge"]
        p_aux::Real, [unit = "W", description = "Mechanical power of the other motors on the same bus"]
        v::Real, [unit = "m/s", description = "Vehicle speed (the traction control reference)"]
    end
    @outputs begin
        u::Real, [unit = "N*m/V", description = "Modulus of the motor MTF (rotor torque per bus volt)"]
        tau::Real, [unit = "N*m", description = "Motor torque"]
        regen::Real, [unit = "N*m", description = "Regenerative brake torque at the wheels of the axle"]
        tlim::Real, [unit = "N*m", description = "Torque envelope at the present speed"]
        P::Real, [unit = "W", description = "Mechanical power tau w (negative when regenerating)"]
        n_rpm::Real, [unit = "1", description = "Rotor speed in rpm (`rpm` itself is the built-in constant 2 pi/60)"]
    end
    @parameters begin
        T_max::Real = 300.0, [unit = "N*m", min = 0, description = "Peak torque"]
        P_max::Real = 260000.0, [unit = "W", min = 0, description = "Peak power"]
        w_max::Real = 2094.0, [unit = "rad/s", min = 0, description = "Maximum speed (soft limit)"]
        w_cut::Real = 20.0, [unit = "rad/s", min = 1.0e-6, description = "Width of the speed limit"]
        T_regen::Real = 300.0, [unit = "N*m", min = 0, description = "Peak regenerative torque"]
        P_regen::Real = 200000.0, [unit = "W", min = 0, description = "Peak regenerative power"]
        w_fade::Real = 30.0, [unit = "rad/s", min = 1.0e-6, description = "Rotor speed over which the regen fades in"]
        n::Real = 7.0, [unit = "1", min = 1.0e-6, description = "Reduction ratio (rotor per carrier)"]
        R::Real = 0.06, [unit = "Ohm", min = 0, description = "Battery internal resistance"]
        w_eps::Real = 1.0, [unit = "rad/s", min = 1.0e-6, description = "Speed regularisation of P/|w|"]
        R_w::Real = 0.32, [unit = "m", min = 1.0e-6, description = "Rolling radius of the driven wheels (traction control)"]
        kappa_tc::Real = 0.1, [unit = "1", min = 0, description = "Traction control: wheel slip allowed"]
        v_tc::Real = 1.0, [unit = "m/s", min = 0, description = "Traction control: slip speed allowed at standstill"]
        v_band::Real = 0.5, [unit = "m/s", min = 1.0e-6, description = "Traction control: slip speed over which the torque fades out"]
        k_rpm::Real = 9.549296585513721, [unit = "s", description = "rpm per rad/s"]
    end
    @variables begin
        aw::Real = 1.0, [unit = "rad/s", description = "|w|, regularised"]
        tdrv::Real = 0.0, [unit = "N*m", description = "Drive torque"]
        tc::Real = 1.0, [unit = "1", description = "Traction control factor (1: no intervention)"]
        treg::Real = 0.0, [unit = "N*m", description = "Regenerative torque magnitude"]
        vbus::Real = 400.0, [unit = "V", description = "Bus voltage at the commanded power"]
    end
    @equations begin
        aw ~ sqrt(w * w + w_eps * w_eps)
        tlim ~ min(T_max, P_max / aw) * 0.5 * (1 - tanh((aw - w_max) / w_cut))
        tc ~ clamp(((1 + kappa_tc) * v + v_tc - aw * R_w / n) / v_band, 0.0, 1.0)
        tdrv ~ thr * tlim * (1 - 2 * rev) * clamp(soc / 0.02, 0.0, 1.0) * tc
        treg ~ min(dem / n, min(T_regen, P_regen / aw)) * clamp((1 - soc) / 0.02, 0.0, 1.0)
        tau ~ tdrv - treg * tanh(w / w_fade)
        regen ~ n * treg * tanh(w / w_fade) * w / aw
        P ~ tau * w
        vbus ~ 0.5 * (ocv + sqrt(max(ocv * ocv - 4 * R * (P + p_aux), 0.01 * ocv * ocv)))
        u ~ tau / vbus
        n_rpm ~ w * k_rpm
    end
end
