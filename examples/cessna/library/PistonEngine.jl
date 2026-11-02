@block PistonEngine begin
    # The Lycoming O-320 of the c172p (JSBSim's FGPiston without starter, magnetos and the
    # temperature models) as a modulated torque source on the crankshaft's 1-junction: an MSe
    # whose torque depends on the shaft speed (the port flow), the throttle, the mixture and the
    # manifold pressure (its one state). Port convention: power into the port is p.e p.f, so the
    # engine delivering the torque tau_e has p.e = -tau_e.
    #
    #   MAP' = (MAP_target - MAP) / lag,  MAP_target = p_tot ze / (ze + z_airbox + (1 - thr)^2 z_thr),
    #          ze = peak piston speed / sqrt(mps^2 + mps_floor^2)       (FGPiston's impedances)
    #   air mass flow   m_air = V_swept VE ve MAP / (R T),  V_swept = displacement rpm / 120
    #                   ve = (gam - 1)/gam + (cr - min(pa/MAP, cr)) / (gam (cr - 1)),  gam = 1.3
    #   fuel/air ratio  fa = 1.3 mixture (101325 / pa) / 14.7; efficiency me(fa) (FGPiston's table)
    #   indicated hp    ihp = fuel flow (lb/h) / ISFC me - static friction
    #   pumping + friction losses (PMEP + FMEP) displacement rpm / (cycles 22371)
    #   shaft power     P = (ihp + losses) 745.7 W,   torque tau_e = P w / (w^2 + w_floor^2)
    #
    # ISFC (lb/(hp h)) is FGPiston's own calibration, 0.418: it gives the rated 160 hp at
    # 2700 rpm and 28.5 inHg. The engine file's "bsfc" 0.32, which FGPiston would use instead,
    # gives about 205 hp (see the README).
    @constants NM::Int = 15
    @ports p::Power{Rotation}
    @inputs begin
        throttle::Real, [description = "Throttle 0 .. 1"]
        mixture::Real, [description = "Mixture 0 (cut-off) .. 1 (full rich)"]
        pa::Real, [unit = "Pa", description = "Static pressure"]
        p_tot::Real, [unit = "Pa", description = "Ram-air (total) pressure"]
        T::Real, [unit = "K", description = "Air temperature"]
    end
    @outputs begin
        tau::Real, [unit = "N*m", description = "Engine torque on the crankshaft"]
        P::Real, [unit = "W", description = "Shaft power"]
        hp::Real, [description = "Shaft power (hp)"]
        n_rpm::Real, [description = "Engine speed (n_rpm)"]
        map_inhg::Real, [description = "Manifold pressure (inHg)"]
        ff_gph::Real, [description = "Fuel flow (US gal/h, 6 lb/gal)"]
    end
    @parameters begin
        displacement::Real = 0.00524386, [description = "Displacement (m^3; 320 in^3)"]
        stroke_in::Real = 4.375, [description = "Stroke (in)"]
        cr::Real = 8.5, [description = "Compression ratio"]
        VE::Real = 0.85, [description = "Volumetric efficiency"]
        R_air::Real = 287.3, [unit = "J/(kg*K)", description = "Gas constant (FGPiston)"]
        isfc::Real = 0.41798, [description = "Indicated specific fuel consumption (lb/(hp h))"]
        fric_hp::Real = 1.5, [description = "Static friction (hp)"]
        fmep_dyn::Real = 18400.0, [description = "Dynamic friction MEP (Pa per m/s of piston speed)"]
        fmep_static::Real = 46500.0, [description = "Static friction MEP (Pa)"]
        cycles::Real = 4.0, [description = "Strokes per cycle (FGPiston's Cycles)"]
        peak_mps::Real = 100.0, [description = "Peak piston speed (ft/s)"]
        z_airbox::Real = 0.151853873645285, [description = "Airbox impedance (FGPiston, from MaxMP)"]
        z_thr::Real = 29.65064194555036, [description = "Throttle impedance at closed throttle (FGPiston, from MinMP at idle n_rpm)"]
        lag::Real = 1.0, [unit = "s", min = 1.0e-6, description = "Manifold pressure lag"]
        mps_floor::Real = 0.1, [description = "Piston-speed floor of the engine impedance (ft/s)"]
        w_floor::Real = 1.0, [unit = "rad/s", min = 1.0e-9, description = "Shaft-speed floor of the torque"]
        fa_tab::Vec{NM} = [0.05, 0.05137, 0.05179, 0.0543, 0.05842, 0.06312, 0.06942, 0.07786, 0.08845, 0.0927, 0.1012, 0.11455, 0.12158, 0.12435, 0.125], [description = "Fuel/air ratio breakpoints"]
        me_tab::Vec{NM} = [0.0, 0.00862, 0.21552, 0.48276, 0.7069, 0.83621, 0.93103, 1.0, 1.0, 0.98276, 0.93103, 0.72414, 0.4569, 0.23276, 0.0], [description = "Combustion efficiency"]
        one_pa::Real = 1.0, [unit = "Pa", description = "Unit pressure (makes the FGPiston formulas unit-clean)"]
        one_w::Real = 745.69987158227022, [unit = "W", description = "One horsepower"]
        one_kgs::Real = 1.0, [unit = "kg/s", description = "Unit mass flow"]
        one_m3s::Real = 1.0, [unit = "m^3/s", description = "Unit volume flow"]
        one_rads::Real = 1.0, [unit = "rad/s", description = "Unit angular speed"]
    end
    @variables begin
        MAP::Real = 101325.0, [unit = "Pa", state = :prefer, description = "Manifold pressure"]
        w::Real = 0.0, [unit = "rad/s", description = "Shaft speed (the port flow)"]
        mps::Real = 0.0, [description = "Mean piston speed (ft/s)"]
        ze::Real = 1.0
        zt::Real = 0.0
        target::Real = 101325.0, [unit = "Pa"]
        mratio::Real = 1.0
        ve::Real = 1.0
        m_air::Real = 0.0, [unit = "kg/s"]
        fa::Real = 0.088
        me::Real = 1.0
        ff_pph::Real = 0.0, [description = "Fuel flow (lb/h)"]
        ihp::Real = 0.0
        pump_hp::Real = 0.0
    end
    @equations begin
        w ~ p.f
        n_rpm ~ w / one_rads * 9.549296585513721
        mps ~ n_rpm * stroke_in / 360.0
        ze ~ peak_mps / sqrt(mps * mps + mps_floor * mps_floor)
        zt ~ (1.0 - clamp(throttle, 0.0, 1.0))^2 * z_thr
        target ~ p_tot * ze / (ze + z_airbox + zt)
        ddt(MAP) ~ (target - MAP) / lag
        mratio ~ min(pa / MAP, cr)
        ve ~ 0.3 / 1.3 + (cr - mratio) / (1.3 * (cr - 1.0))
        m_air ~ displacement * n_rpm / 120.0 * VE * ve * MAP / (R_air * T) * one_m3s
        fa ~ 1.3 * clamp(mixture, 0.0, 1.0) * (101325.0 * one_pa / pa) / 14.7
        me ~ interp1(fa, fa_tab, me_tab)
        ff_pph ~ m_air / one_kgs * fa * 2.2046 * 3600.0
        ihp ~ ff_pph / isfc * me - fric_hp
        pump_hp ~ ((MAP - pa) / one_pa * VE - (fmep_dyn * mps * 0.3048 + fmep_static)) * displacement * n_rpm / (cycles * 22371.0)
        hp ~ ihp + pump_hp
        P ~ hp * one_w
        tau ~ P * w / (w * w + w_floor * w_floor)
        p.e ~ -tau
        map_inhg ~ MAP / (3386.38 * one_pa)
        ff_gph ~ ff_pph / 6.0
    end
    @causality p => :effort_out
end
