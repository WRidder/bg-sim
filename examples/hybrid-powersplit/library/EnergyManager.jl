@block EnergyManager begin
    # The supervisory energy management of the power-split hybrid (sampled, 10 Hz). It decides
    # whether the engine runs and at which operating point (speed w_ref, torque T_ref); the
    # continuous PowerSplitControl then holds that point with MG1 and fills the wheel torque
    # with MG2. Two strategies, chosen at run time by `strategy` (no recompile):
    #
    #   SOC target     soc_t = soc_ref - eta_kin (m v^2 / 2) / E_bat: at speed the target leaves
    #                  room for the kinetic energy regenerative braking will return (a
    #                  velocity-dependent reference, cf. Ambuehl & Guzzella 2009)
    #
    #   0 rule-based   P_req = F_dem v + P_chg, P_chg = k_soc (soc_t - soc) (clamped).
    #                  The engine starts when P_req > P_on (or soc < soc_low, or v > v_ev: MG1
    #                  would overspeed with the engine at rest) and stops when P_req < P_off or
    #                  the driver brakes. Running, it delivers P_e = max(P_req, P_min) on the
    #                  optimal operating line: w_ref = OOL(P_e), T_ref = P_e / w_ref.
    #   1 ECMS         the equivalent consumption minimisation (Paganelli et al. 2002,
    #                  Sciarretta et al. 2004): every tick it evaluates the engine off and NW x NT
    #                  operating points (w_i, frac_j WOT(w_i)) and picks the least
    #                    m_eq = m_fuel(w, T) + s p(soc) (P_batt + R_bat P_batt^2 / V_bat^2) / LHV,
    #                    p(soc) = 1 - k_p (soc - soc_t) / dsoc              (SOC correction)
    #                  with the battery power P_batt of the quasi-static power balance of the
    #                  planetary set: T_g = -Zs/(Zs+Zr) T, w_s = ((Zs+Zr) w - Zr w_r)/Zs,
    #                  T_m = T_rdem - Zr/(Zs+Zr) T, P_batt = T_g w_s + c1 T_g^2 + b1 w_s^2 +
    #                  T_m w_r + c2 T_m^2 + b2 w_r^2. Points beyond the MG1 speed, MG2 torque or
    #                  battery power limits are skipped; an engine start costs m_start extra.
    #
    # The fuel rate of every candidate (fuel_g) is the engine's own fuel map at that point
    # (design/design.py), so the ECMS and the plant agree. Between ticks the outputs are held.
    @constants begin
        sample_period::Real = 0.1, [unit = "s", description = "Sample period"]
        NO::Int = 15
        NW::Int = 16
        NT::Int = 12
    end
    @inputs begin
        F_dem::Real, [unit = "N", description = "Driver's tractive force demand at the wheels"]
        v::Real, [unit = "m/s", description = "Vehicle speed"]
        w_r::Real, [unit = "rad/s", description = "Ring (MG2) speed"]
        soc::Real, [unit = "1", description = "Battery state of charge"]
    end
    @outputs begin
        on::Real = 0.0, [unit = "1", description = "1: the engine runs (fuel on), 0: off or spinning without fuel"]
        w_ref::Real = 0.0, [unit = "rad/s", description = "Engine speed reference"]
        T_ref::Real = 0.0, [unit = "N*m", description = "Engine torque reference"]
        P_e::Real = 0.0, [unit = "W", description = "Engine power reference"]
        P_req::Real = 0.0, [unit = "W", description = "Power demand at the wheels"]
        P_bat_est::Real = 0.0, [unit = "W", description = "Battery power of the chosen point (quasi-static estimate)"]
        s_eq::Real = 0.0, [unit = "1", description = "Equivalence factor with the SOC correction (ECMS)"]
        sel::Real = 0.0, [unit = "1", description = "The strategy in use (0 rule-based, 1 ECMS)"]
    end
    @parameters begin
        strategy::Int = 0, [options = ["rule-based", "ECMS"], description = "Energy management: 0 rule-based, 1 ECMS"]
        Zs::Real = 30.0, [unit = "1", description = "Sun teeth"]
        Zr::Real = 78.0, [unit = "1", description = "Ring teeth"]
        FD::Real = 4.113, [unit = "1", description = "Ring to axle ratio"]
        r_w::Real = 0.3, [unit = "m", description = "Rolling radius"]
        LHV::Real = 43.0e6, [unit = "J/kg", description = "Lower heating value of the fuel"]
        w_min::Real = 104.72, [unit = "rad/s", description = "Lowest firing engine speed"]
        w_max::Real = 523.6, [unit = "rad/s", description = "Highest engine speed"]
        w1_max::Real = 1047.2, [unit = "rad/s", description = "MG1 speed limit"]
        w_margin::Real = 50.0, [unit = "rad/s", description = "MG1 speed margin kept below its limit"]
        w_eps::Real = 1.0, [unit = "rad/s", description = "Speed regularisation of P/|w|"]
        T2_max::Real = 400.0, [unit = "N*m", description = "MG2 torque limit"]
        P2_max::Real = 50000.0, [unit = "W", description = "MG2 power limit"]
        c1::Real = 0.66, [unit = "W/(N*m)^2", description = "MG1 copper loss coefficient"]
        b1::Real = 0.002, [unit = "N*m*s/rad", description = "MG1 iron loss coefficient"]
        c2::Real = 0.1, [unit = "W/(N*m)^2", description = "MG2 copper loss coefficient"]
        b2::Real = 0.014, [unit = "N*m*s/rad", description = "MG2 iron loss coefficient"]
        P_dis::Real = 21000.0, [unit = "W", description = "Battery discharge power limit"]
        P_chg::Real = 25000.0, [unit = "W", description = "Battery charge power limit"]
        soc_ref::Real = 0.6, [unit = "1", description = "Target state of charge"]
        soc_low::Real = 0.45, [unit = "1", description = "Below this the engine runs to charge"]
        v_ev::Real = 19.4, [unit = "m/s", description = "Above this speed the engine keeps turning (MG1 speed)"]
        # rule-based
        P_on::Real = 9000.0, [unit = "W", description = "Rule-based: engine start threshold"]
        P_off::Real = 5000.0, [unit = "W", description = "Rule-based: engine stop threshold"]
        P_min::Real = 9000.0, [unit = "W", description = "Rule-based: least engine power while running"]
        k_soc::Real = 100000.0, [unit = "W", description = "Rule-based: charge power per unit of SOC error"]
        P_chg_max::Real = 8000.0, [unit = "W", description = "Rule-based: charge power limit"]
        ool_P::Vec{NO} = [0.0, 4000.0, 8000.0, 12000.0, 16000.0, 20000.0, 24000.0, 28000.0, 32000.0, 36000.0, 40000.0, 44000.0, 48000.0, 52000.0, 56000.0], [unit = "W", description = "Optimal operating line: engine power"]
        ool_w::Vec{NO} = [104.7, 104.7, 113.0, 156.0, 182.0, 227.0, 260.0, 283.0, 323.0, 363.0, 376.0, 400.0, 436.0, 471.0, 523.6], [unit = "rad/s", description = "Optimal operating line: engine speed"]
        # ECMS
        s0::Real = 2.6, [unit = "1", description = "ECMS: equivalence factor"]
        k_p::Real = 1.0, [unit = "1", description = "ECMS: SOC correction gain"]
        R_bat::Real = 0.4, [unit = "Ohm", description = "ECMS: battery resistance (R0 + R1) for the internal loss R P^2 / V^2"]
        V_bat::Real = 220.0, [unit = "V", description = "ECMS: nominal battery voltage"]
        m_kin::Real = 1435.0, [unit = "kg", description = "Vehicle mass for the kinetic-energy SOC target"]
        E_bat::Real = 5.15e6, [unit = "J", description = "Battery energy content (capacity x nominal voltage)"]
        eta_kin::Real = 0.6, [unit = "1", description = "Share of the kinetic energy the SOC target keeps room for"]
        f0::Real = 7.0, [unit = "N*m", description = "Engine friction torque: constant part"]
        f1::Real = 0.00955, [unit = "N*m*s/rad", description = "Engine friction torque: linear part"]
        f2::Real = 1.824e-5, [unit = "N*m*s^2/rad^2", description = "Engine friction torque: quadratic part"]
        dsoc::Real = 0.1, [unit = "1", description = "ECMS: half width of the SOC window of the correction"]
        m_start::Real = 0.4e-3, [unit = "kg/s", description = "ECMS: penalty on an engine start (fuel rate added for one tick)"]
        wg::Vec{NW} = [104.7, 120.4, 136.1, 151.8, 167.6, 188.5, 209.4, 235.6, 261.8, 293.2, 324.6, 356.0, 397.9, 439.8, 481.7, 523.6], [unit = "rad/s", description = "ECMS: candidate engine speeds"]
        Tg_cand::Mat{NW,NT} = [12.0 20.0 28.0 36.0 44.0 49.6 54.400000000000006 59.2 64.0 68.0 72.0 76.0; 12.54 20.9 29.259999999999994 37.62 45.980000000000004 51.831999999999994 56.848 61.864 66.88 71.05999999999999 75.24 79.41999999999999; 13.08 21.8 30.52 39.24 47.96000000000001 54.064 59.29600000000001 64.528 69.76 74.12 78.48 82.84; 13.62 22.7 31.779999999999998 40.86 49.940000000000005 56.296 61.744 67.192 72.64 77.17999999999999 81.72 86.25999999999999; 14.04 23.4 32.76 42.12 51.480000000000004 58.032 63.648 69.264 74.88 79.55999999999999 84.24 88.91999999999999; 14.52 24.2 33.879999999999995 43.56 53.24 60.016 65.824 71.63199999999999 77.44 82.28 87.12 91.96; 15.0 25.0 35.0 45.0 55.00000000000001 62.0 68.0 74.0 80.0 85.0 90.0 95.0; 15.299999999999999 25.5 35.699999999999996 45.9 56.1 63.24 69.36 75.48 81.60000000000001 86.7 91.8 96.89999999999999; 15.6 26.0 36.4 46.800000000000004 57.2 64.48 70.72 76.96 83.2 88.39999999999999 93.60000000000001 98.8; 15.96 26.6 37.24 47.88 58.52000000000001 65.968 72.352 78.736 85.12 90.44 95.76 101.08; 16.29 27.15 38.01 48.87 59.730000000000004 67.332 73.848 80.36399999999999 86.88 92.30999999999999 97.74 103.16999999999999; 16.56 27.6 38.64 49.68000000000001 60.720000000000006 68.44800000000001 75.072 81.696 88.32000000000001 93.84 99.36000000000001 104.88; 16.919999999999998 28.2 39.48 50.76 62.040000000000006 69.93599999999999 76.70400000000001 83.472 90.24000000000001 95.88 101.52 107.16; 17.25 28.75 40.25 51.75 63.25000000000001 71.3 78.2 85.1 92.0 97.75 103.5 109.25; 16.94585943224569 28.24309905374282 39.540338675239944 50.83757829673708 62.13481791823421 70.0428856532822 76.82122942618048 83.59957319907875 90.37791697197703 96.02653678272559 101.67515659347416 107.32377640422271; 16.32929716122846 27.215495268714104 38.10169337619974 48.98789148368539 59.874089591171035 67.49442826641098 74.02614713090237 80.55786599539374 87.08958485988514 92.53268391362795 97.97578296737078 103.41888202111359], [unit = "N*m", description = "ECMS: candidate engine torques (row: speed)"]
        fuel_g::Mat{NW,NT} = [0.00012321055291480626 0.00017200681149492756 0.0002208030700750489 0.0002695993286551702 0.0003183955872352915 0.0003525529682413764 0.0003818307233894492 0.000411108478537522 0.00044038623368559477 0.00046608832149180526 0.0004930943678141655 0.0005201004141365259; 0.00014658923255404818 0.00020486083941842053 0.00026313244628279285 0.00032140405314716523 0.00037967566001153766 0.0004204657848165982 0.00045542874893522164 0.0004903917130538451 0.0005257562963954426 0.0005567997911367559 0.0005878432858780694 0.0006270450938647671; 0.00017090832821960554 0.00023928222738577257 0.0003076561265519397 0.00037603002571810675 0.00044440392488427383 0.0004922656543005907 0.0005332899938002909 0.0005743143332999912 0.000616319249603836 0.0006516432510130022 0.0006904146722499265 0.00073589458612465; 0.00019616783991147833 0.00027527097539698376 0.00035437411088248914 0.0004334772463679945 0.0005125803818534999 0.0005679525766933536 0.0006154144579846568 0.0006629540552035225 0.000710771134794625 0.0007508504460125954 0.0007965431335047068 0.000842235820996818; 0.00022217756000292088 0.0003118117133308279 0.0004014458666587349 0.000491080019986642 0.000580714173314549 0.0006434580806440838 0.0006972385726408281 0.0007510190646375722 0.0008047995566343165 0.0008515421279242868 0.0008998792494514275 0.0009527849318225172; 0.00025776627946090384 0.0003615822800849529 0.0004653982807090019 0.000569214281333051 0.0006730302819571001 0.0007457014823939342 0.0008079910827683637 0.0008702806831427931 0.0009327357557116459 0.000986463950162327 0.0010401921446130083 0.001109519371399345; 0.00029445755413849857 0.00041319043887176415 0.0005319233236050297 0.0006506562083382952 0.000769389093071561 0.0008525021123848468 0.0009237418432248061 0.0009949815740647654 0.0010662213049047247 0.0011255877472713576 0.0011907791339482495 0.0012647079370905303; 0.0003412358368689996 0.00047705662837445306 0.0006128774198799064 0.0007486982113853601 0.0008845190028908136 0.000979593556944631 0.0010610860318479032 0.0011425785067511753 0.0012240709816544475 0.0012919813774071739 0.0013683501819249573 0.001447612652599207; 0.0003888796048393549 0.0005423652932768991 0.0006958509817144434 0.0008493366701519877 0.001002822358589532 0.0011102623404958128 0.0012023537535583394 0.001294445166620866 0.0013865365796833925 0.0014638951526748612 0.0015486424709386935 0.001633389789202525; 0.00045250234903440216 0.0006283156276146798 0.0008041289061949575 0.0009799421847752354 0.0011557554633555133 0.0012788247583617074 0.0013843127255098741 0.0014898006926580408 0.0015952886598062073 0.0016854014370413738 0.0017781181803755894 0.0018859203419715241; 0.0005190977643857917 0.0007179436751785771 0.0009167895859713625 0.0011156354967641478 0.0013144814075569332 0.0014536735451118829 0.0015729810915875542 0.0016922886380632254 0.0018115961845388967 0.001912728120026969 0.0020143041524298168 0.002143550875135041; 0.0005901776597802396 0.0008124923787453302 0.0010348070977104207 0.0012571218166755114 0.0014794365356406022 0.0016350568389161657 0.0017684456702952197 0.001901834501674274 0.0020352693905880104 0.002147221242543814 0.002261319585200003 0.0024061842945617066; 0.0006949463147142425 0.0009506019546364499 0.0012062575945586572 0.0014619132344808646 0.0017175688744030721 0.001896527822348617 0.002049921206301942 0.0022033145902552657 0.0023567614964941285 0.002484724077924176 0.0026244512366521387 0.0027787440625108525; 0.000810601578185531 0.0011016061559611674 0.0013926107337368038 0.0016836153115124405 0.001974619889288077 0.0021783230937310223 0.0023529258403964044 0.002527528587061786 0.002702131333727168 0.002847633622614986 0.0030120357658335083 0.0031816878685883366; 0.0009215384836639156 0.001238785320250726 0.001556032156837536 0.0018732789934243464 0.002190525830011157 0.002412598615621924 0.0026029467175740103 0.0027932948195260963 0.002983912495932088 0.0031431762745150857 0.0033183590542974987 0.003511235962579781; 0.0010339231727928976 0.0013716288385468387 0.0017093345043007794 0.0020470401700547203 0.0023847458358086616 0.0026211398018364204 0.002823763201288785 0.003026386600741149 0.003229010000193514 0.0034004320897037953 0.003572370228906131 0.0037950646879480656], [unit = "kg/s", description = "ECMS: fuel rate of every candidate (the engine map)"]
    end
    @variables begin
        st::Real = 0.0, [unit = "1", description = "Engine state held between ticks (1 running)"]
    end
    @discrete Ts = sample_period begin
        Zc = Zs + Zr
        Pw = F_dem * v
        Trd = F_dem * r_w / FD
        aw = sqrt(w_r * w_r + w_eps * w_eps)
        Tl2 = min(T2_max, P2_max / aw)
        # least engine speed that keeps MG1 below its limit (0 at low vehicle speed)
        wspin = max(0.0, (Zr * w_r - Zs * (w1_max - w_margin)) / Zc)
        fast = v > v_ev
        # SOC target lowered by the share eta_kin of the kinetic energy that braking will return
        soc_t = soc_ref - eta_kin * 0.5 * m_kin * v * v / E_bat
        if strategy == 0
            Pc = clamp(k_soc * (soc_t - soc), -P_chg_max, P_chg_max)
            Pr = Pw + Pc
            run = st > 0.5
            if run
                if Pw <= 0.0 || (Pr < P_off && soc > soc_low + 0.02 && !fast)
                    run = false
                end
            else
                if (Pw > 0.0 && (Pr > P_on || fast)) || soc < soc_low
                    run = true
                end
            end
            if run
                Pe = clamp(max(Pr, P_min), 0.0, ool_P[NO])
                we = ool_w[1]
                for k in 1:(NO - 1)
                    if Pe >= ool_P[k] && Pe <= ool_P[k + 1]
                        we = ool_w[k] + (ool_w[k + 1] - ool_w[k]) * (Pe - ool_P[k]) / (ool_P[k + 1] - ool_P[k])
                    end
                end
                we = clamp(we, max(w_min, wspin), w_max)
                on = 1.0
                w_ref = we
                T_ref = Pe / we
                P_e = Pe
                st = 1.0
            else
                on = 0.0
                w_ref = wspin
                T_ref = 0.0
                P_e = 0.0
                st = 0.0
            end
            # quasi-static battery power of the decision (for the display)
            Tg = -Zs / Zc * T_ref
            ws = (Zc * w_ref - Zr * w_r) / Zs
            Tm = clamp(Trd - Zr / Zc * T_ref, -Tl2, Tl2)
            P_bat_est = Tg * ws + c1 * Tg * Tg + b1 * ws * ws + Tm * w_r + c2 * Tm * Tm + b2 * w_r * w_r
            s_eq = 0.0
            sel = 0.0
        else
            s = s0 * (1.0 - k_p * (soc - soc_t) / dsoc)
            # engine off: at rest, or above the MG1 speed limit spun by MG1 without fuel against
            # its friction torque Tf0 (MG1 and MG2 carry its reaction)
            Tf0 = 0.0
            if wspin > 0.0
                Tf0 = f0 + f1 * wspin + f2 * wspin * wspin
            end
            ws0 = (Zc * wspin - Zr * w_r) / Zs
            Tg0 = Zs / Zc * Tf0
            Tm0 = Trd + Zr / Zc * Tf0
            Pb0 = Tg0 * ws0 + c1 * Tg0 * Tg0 + b1 * ws0 * ws0 + Tm0 * w_r + c2 * Tm0 * Tm0 + b2 * w_r * w_r
            best = s * (Pb0 + R_bat * Pb0 * Pb0 / (V_bat * V_bat)) / LHV
            if abs(Tm0) > Tl2 || Pb0 > P_dis
                best = 1.0e3
            end
            bw = wspin
            bT = 0.0
            bon = 0.0
            bP = Pb0
            # the engine stays off while the driver brakes
            if Pw > 0.0
                for i in 1:NW
                    wi = wg[i]
                    ws = (Zc * wi - Zr * w_r) / Zs
                    for j in 1:NT
                        T = Tg_cand[i, j]
                        Tg = -Zs / Zc * T
                        Tm = Trd - Zr / Zc * T
                        Pb = Tg * ws + c1 * Tg * Tg + b1 * ws * ws + Tm * w_r + c2 * Tm * Tm + b2 * w_r * w_r
                        cost = fuel_g[i, j] + s * (Pb + R_bat * Pb * Pb / (V_bat * V_bat)) / LHV
                        if st < 0.5
                            cost = cost + m_start
                        end
                        ok = abs(ws) < w1_max - w_margin && abs(Tm) <= Tl2 && Pb <= P_dis && Pb >= -P_chg
                        if ok && cost < best
                            best = cost
                            bw = wi
                            bT = T
                            bon = 1.0
                            bP = Pb
                        end
                    end
                end
            end
            on = bon
            w_ref = bw
            T_ref = bT
            P_e = bT * bw
            P_bat_est = bP
            st = bon
            s_eq = s
            sel = 1.0
        end
        P_req = Pw
    end
end
