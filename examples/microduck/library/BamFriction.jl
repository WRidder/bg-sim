@block BamFriction begin
    # Gearbox friction of a Dynamixel XL330 as a nonlinear bond-graph R element: the BAM M6
    # friction budget (Duclusaud, Passault et al., "Extended Friction Models for the Physics
    # Simulation of Servo Actuators", arXiv:2410.08650; code and the XL330 fit in
    # github.com/Rhoban/bam, bam/model.py). Effort from flow, no state.
    #
    # The budget is load dependent: it grows with the motor torque `tau_m` and with the
    # external torque `tau_e` the load puts on the gear output, and it has a Stribeck part
    # that is only present near rest:
    #
    #   S   = exp(-(|w| / dtheta_s)^alpha)
    #   F   = fb + |tau_e lfe - tau_m lfm|
    #       + S (fs + |tau_e lfes - tau_m lfms| + quad)
    #   quad = lfeq tau_e^2  if |tau_m| > |tau_e|,  lfmq tau_m^2  otherwise
    #          (only when tau_m and tau_e have opposite signs, as in bam/model.py)
    #
    # BAM clips the stopping torque to [-(F + fv |w|), F + fv |w|] (static friction). A
    # continuous model cannot clip, so the dry part is regularised:
    #
    #   p.e = scale F tanh(w / ws) + fv w
    #
    # A joint held below the budget creeps at `ws atanh(tau / F)` instead of sticking
    # (ws = 2 mrad/s: 0.1 deg/s at 90 % of the budget). `scale` multiplies the velocity-independent
    # budget only, like the friction domain randomisation of microduck_rl (FrictionDRBamActuator).
    #
    # The kinks are smoothed so that the law raises no solver events (a robot holds 14 of them
    # near rest, where |w| and the torque signs change all the time): |x| is
    # sqrt(x^2 + ts^2) - ts (off by at most ts = 0.1 mN m), the sign tests are tanh steps over
    # ts, and S uses (w^2)^(alpha/2), which is smooth at w = 0 for alpha > 2.
    #
    # `tau_l` is the torque the gear output transmits to the link (the backlash spring torque,
    # positive when it drives the link forward). The load acts back on the gear with
    # `tau_e = -tau_l`. BAM uses gravity, Coriolis and contact torques instead (no inertial
    # part); the transmitted torque is what the gear teeth really carry.
    @ports p::Power{Rotation}
    @orientation p => :in
    @inputs begin
        tau_m::Real, [unit = "N*m", description = "Motor torque at the gear output, kt i"]
        tau_l::Real, [unit = "N*m", description = "Torque transmitted from the gear output to the link"]
    end
    @outputs begin
        F::Real, [unit = "N*m", description = "Velocity-independent friction budget (before scale)"]
        tau_f::Real, [unit = "N*m", description = "Friction torque opposing the motion"]
    end
    @parameters begin
        fb::Real = 0.004771183165566, [unit = "N*m", min = 0, description = "Coulomb friction (BAM friction_base)"]
        fs::Real = 0.004676345799486616, [unit = "N*m", min = 0, description = "Stribeck friction at rest (BAM friction_stribeck)"]
        lfm::Real = 0.2667860954283698, [unit = "1", min = 0, description = "Load friction per motor torque (BAM load_friction_motor)"]
        lfe::Real = 8.515871897059342e-6, [unit = "1", min = 0, description = "Load friction per external torque (BAM load_friction_external)"]
        lfms::Real = 1.0722918395099123e-5, [unit = "1", min = 0, description = "Stribeck load friction per motor torque (BAM load_friction_motor_stribeck)"]
        lfes::Real = 0.08077928978935671, [unit = "1", min = 0, description = "Stribeck load friction per external torque (BAM load_friction_external_stribeck)"]
        lfmq::Real = 0.009972471242139415, [unit = "1/(N*m)", min = 0, description = "Quadratic load friction, motor side (BAM load_friction_motor_quad)"]
        lfeq::Real = 0.004902565732332559, [unit = "1/(N*m)", min = 0, description = "Quadratic load friction, external side (BAM load_friction_external_quad)"]
        dtheta_s::Real = 2.890372094130307, [unit = "rad/s", min = 1.0e-9, description = "Stribeck velocity (BAM dtheta_stribeck)"]
        alpha::Real = 8.683259907618984, [unit = "1", min = 2, description = "Stribeck exponent (BAM alpha)"]
        fv::Real = 0.005359668274599504, [unit = "N*m*s/rad", min = 0, description = "Viscous friction (BAM friction_viscous)"]
        scale::Real = 1.0, [unit = "1", min = 0, description = "Multiplier on the velocity-independent budget (domain randomisation)"]
        ws::Real = 0.002, [unit = "rad/s", min = 1.0e-9, description = "Regularisation speed of the dry friction (tanh(w/ws))"]
        ts::Real = 1.0e-4, [unit = "N*m", min = 1.0e-12, description = "Smoothing torque of the kinks (|x| and the sign tests)"]
    end
    @variables begin
        tau_e::Real = 0.0, [unit = "N*m", description = "External torque on the gear output, -tau_l"]
        S::Real = 1.0, [unit = "1", description = "Stribeck coefficient, 1 at rest and 0 when moving"]
        am::Real = 0.0, [unit = "N*m", description = "Smooth |tau_m|"]
        ae::Real = 0.0, [unit = "N*m", description = "Smooth |tau_e|"]
        opp::Real = 0.0, [unit = "1", description = "1 when tau_m and tau_e have opposite signs, else 0 (smooth)"]
        big::Real = 0.5, [unit = "1", description = "1 when |tau_m| > |tau_e|, else 0 (smooth)"]
        quad::Real = 0.0, [unit = "N*m", description = "Quadratic Stribeck load term"]
        g1::Real = 0.0, [unit = "N*m", description = "Smooth |tau_e lfe - tau_m lfm|"]
        g2::Real = 0.0, [unit = "N*m", description = "Smooth |tau_e lfes - tau_m lfms|"]
    end
    @equations begin
        tau_e ~ -tau_l
        S ~ exp(-((p.f / dtheta_s)^2)^(alpha / 2))
        am ~ sqrt(tau_m^2 + ts^2) - ts
        ae ~ sqrt(tau_e^2 + ts^2) - ts
        opp ~ 0.5 * (1 - tanh(tau_m * tau_e / (ts * ts)))
        big ~ 0.5 * (1 + tanh((am - ae) / ts))
        quad ~ opp * (big * lfeq * tau_e^2 + (1 - big) * lfmq * tau_m^2)
        g1 ~ sqrt((tau_e * lfe - tau_m * lfm)^2 + ts^2) - ts
        g2 ~ sqrt((tau_e * lfes - tau_m * lfms)^2 + ts^2) - ts
        F ~ fb + g1 + S * (fs + g2 + quad)
        tau_f ~ scale * F * tanh(p.f / ws) + fv * p.f
        p.e ~ tau_f
    end
end
