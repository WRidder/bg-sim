@block DoubleCartLabRobustCtrl begin
    # Robust classical firmware of the double-cart lab rig, 1 kHz (plan/ROBUST_CLASSICAL_PLAN.md C1-C3; the bgsim
    # counterpart of design/robust_ctrl.py, written by design/robustmodels.py: do not edit the numbers by hand).
    # Modes (output phase): 0 hold, 1 swing-up, 2 balance, 3 settle (energy removal, hanging LQR).
    #   rearm = 0 (timed): 0 V until t_on, the swing-up from t_on (u = u_ff - K(tau) (z - z*(tau))), balance from tau = T_s.
    #   rearm = 1 (state-driven, C3): settle from t_on; 50 ticks at the hanging rest arm the swing-up (the plan shifted
    #   to the cart position and the links' turn count); the catch when z'Pz < catch_tol from tau = T_s - catch_lead
    #   (at T_s at the latest); a link more than `drop` from upright in balance switches back to settle.
    # Balance: u = -Kb [x_hat; u_{k-1}; u_{k-2}] with the observer x_hat = x_m + Lo (y - H x_m),
    #   x_m = Am x_hat_{k-1} + Bm u_{k-3}, y = [x, th1, th2 - th1] (angles wrapped), x_hat starts at the state at the catch.
    # Settle: the rail guard (brake when the stopping point passes x_guard), else while the links' energy E (cart frame,
    #   zero at the hanging rest) exceeds e_lqr the energy removal a = -k_e P_x - kc_x x - kc_v v through the collocated
    #   partial feedback linearisation V = (m_all a + beta v) / alpha, then the hanging LQR u = -Kh (z - z_hang).
    # The output u is the command of two ticks ago (the rig's 2 ms loop delay), clamped to +-u_max.
    # z = [x, th1, th2, v, w1, w2], absolute link angles from the upward vertical (sums of the joint angles).
    @inputs begin
        x::Real, [unit = "m", description = "Cart position"]
        v::Real, [unit = "m/s", description = "Cart velocity"]
        q1::Real, [unit = "rad", description = "Joint 1 angle: link 1 from the rail's x axis"]
        q2::Real, [unit = "rad", description = "Joint 2 angle: link 2 relative to link 1"]
        wq1::Real, [unit = "rad/s"]
        wq2::Real, [unit = "rad/s"]
        ff::Real, [unit = "V", description = "Feed-forward voltage (tables)"]
        xs::Vec{6}
        Ks::Vec{6}
    end
    @outputs begin
        u::Real = 0.0, [unit = "V", description = "Motor terminal voltage (the command of two ticks ago)"]
        phase::Real = 0.0, [description = "0 hold, 1 swing-up, 2 balance, 3 settle"]
        th1::Real = -3.1415926535897931, [unit = "rad", description = "Absolute angle of link 1 from the upward vertical, wrapped to [-pi, pi)"]
        th2::Real = -3.1415926535897931, [unit = "rad", description = "Absolute angle of link 2 from the upward vertical, wrapped to [-pi, pi)"]
        tau::Real = 0.0, [unit = "s", description = "Plan time at the next tick in the swing-up, else 0 (drives the tables)"]
        energy::Real = 0.0, [unit = "J", description = "Energy of the links in the cart frame, 0 at the hanging rest"]
        drops::Real = 0.0, [description = "Number of drops out of balance"]
    end
    @parameters begin
        t_on::Real = 1, [unit = "s", description = "Start of the firmware (the hold before)"]
        rearm::Real = 0, [description = "0: timed swing-up and catch; 1: state-driven (C3 settle, arm, region catch, re-arm)"]
        T_s::Real = 3, [unit = "s", description = "Swing-up duration"]
        u_max::Real = 24, [unit = "V", min = 0, description = "Voltage limit"]
        Kb::Vec{8} = [10.7219087584, 67.422503623, -123.856515295, 5.36844005802, -1.38167334172, -15.190536443, 0.157802409411, -0.347682712425], [description = "Balance gain (mm_lqr) on [x_hat, u_k-1, u_k-2]"]
        Lo::Mat{6,3} = [0.605449137093 -8.89193562218e-08 5.61697731122e-07; -0.00435442318138 0.162709688476 -0.0346943802781; 0.0231521819634 0.128015308198 0.162687168343; 249.86901216 0.000648437415323 -2.69859742621e-05; -27.6805472813 15.1626880737 -7.17404259477; 3.59563747011 7.96557988366 15.1689292104], [description = "Observer gain on [x, th1, th2 - th1]"]
        Am::Mat{6,6} = [1 1.40645333826e-06 -3.51756464646e-08 0.000991892642149 -1.42087434617e-11 2.34634234003e-10; 0 1.00002715598 -7.78564235971e-06 -2.50239264468e-05 0.000999995596449 6.28067362829e-09; 0 -2.80841580322e-05 1.0000263387 2.25755932879e-06 1.51549744204e-08 0.000999989001189; 0 0.00280528400849 -7.01577728862e-05 0.983829219319 4.41750352654e-07 4.56238722358e-07; 0 0.0542883400873 -0.0155706094148 -0.0499122287113 1.00000024911 9.96206414296e-06; 0 -0.0561658801239 0.0526771812743 0.00450269861637 2.09480541845e-05 0.999986782419], [description = "1 ms ZOH model at the upright"]
        Bm::Vec{6} = [1.38196199755e-06, 4.26552225937e-06, -3.84818489188e-07, 0.00275643493007, 0.00850792632546, -0.000767519886067], [description = "1 ms ZOH input vector (V)"]
        P::Mat{6,6} = [326037.400598 -54386.9561095 -484857.756236 171776.87636 -61246.0204444 -79934.9350795; -54386.9561095 330702.911343 -485876.359315 2580.83255905 33.3547138371 -75182.805642; -484857.756236 -485876.359315 2502763.2631 -444182.478394 161590.152114 380431.745509; 171776.87636 2580.83255906 -444182.478394 131713.007118 -47361.2258402 -72172.2156029; -61246.0204444 33.3547138361 161590.152114 -47361.2258402 17289.7303495 25947.6561948; -79934.9350795 -75182.805642 380431.745509 -72172.2156029 25947.6561948 60857.0764449], [description = "Catch metric (the balance law's cost-to-go)"]
        catch_tol::Real = 25, [description = "Catch region z'Pz < catch_tol"]
        catch_lead::Real = 0.6, [unit = "s", description = "Region catch allowed from T_s - catch_lead"]
        drop::Real = 0.349065850399, [unit = "rad", description = "Drop detection (rearm)"]
        Kh::Vec{6} = [12.7896787608, -29.1831473147, 4.62964714247, 5.35927955992, -0.530790175709, -1.17283583288], [description = "Hanging LQR on the deviation from the hanging rest"]
        k_e::Real = 40, [unit = "1/(kg*s)", description = "Energy removal gain on P_x"]
        a_max::Real = 25, [unit = "m/s^2", description = "Cart acceleration limit"]
        e_lqr::Real = 3.8, [unit = "J", description = "Hand-over energy to the hanging LQR"]
        kc_x::Real = 1, [unit = "1/s^2", description = "Cart centring (position)"]
        kc_v::Real = 2, [unit = "1/s", description = "Cart centring (velocity)"]
        k_guard::Real = 4, [unit = "1/s^2", description = "Rail guard centring"]
        x_guard::Real = 0.8, [unit = "m", description = "Rail guard on the stopping point"]
        m_all::Real = 1.7402875, [unit = "kg", description = "Cart, reflected rotor and both links"]
        beta::Real = 22.14625, [unit = "N*s/m", description = "Back-EMF and viscous friction at the cart"]
        alpha::Real = 3.775, [unit = "N/V", description = "Force per volt"]
        m1::Real = 0.2481, [unit = "kg"]
        m2::Real = 0.2, [unit = "kg"]
        c1::Real = 0.229312777106, [unit = "m"]
        c2::Real = 0.175875, [unit = "m"]
        L1::Real = 0.35, [unit = "m"]
        J1::Real = 0.00467562649516, [unit = "kg*m^2"]
        J2::Real = 0.003956296375, [unit = "kg*m^2"]
        g0::Real = 9.81, [unit = "m/s^2"]
    end
    @variables begin
        mode::Real = 0.0, [description = "Latched mode"]
        t_arm::Real = 0.0, [unit = "s", description = "Start of the current swing-up"]
        ox::Real = 0.0, [unit = "m", description = "Plan offset: cart position at the arming"]
        o1::Real = 0.0, [unit = "rad", description = "Plan offset: turns of link 1"]
        o2::Real = 0.0, [unit = "rad", description = "Plan offset: turns of link 2"]
        xo::Vec{6} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [description = "Observer estimate"]
        binit::Real = 1.0, [description = "Initialise the observer at the next balance tick"]
        damping::Real = 1.0, [description = "Energy removal latched on"]
        rest::Real = 0.0, [description = "Ticks at the hanging rest"]
        u1::Real = 0.0, [unit = "V", description = "Command of the previous tick"]
        u2::Real = 0.0, [unit = "V", description = "Command of two ticks ago"]
        u3::Real = 0.0, [unit = "V", description = "Command of three ticks ago"]
    end
    @discrete Ts = 0.001 begin
        t1 = q1 - 1.5707963267948966
        t2 = t1 + q2
        w1 = wq1
        w2 = w1 + wq2
        r1 = mod(t1 + 3.141592653589793, 6.283185307179586) - 3.141592653589793
        r2 = mod(t2 + 3.141592653589793, 6.283185307179586) - 3.141592653589793
        th1 = r1
        th2 = r2
        # energy of the links in the cart frame and their horizontal momentum relative to the cart
        v1x = -c1 * cos(t1) * w1
        v1y = -c1 * sin(t1) * w1
        v2x = -L1 * cos(t1) * w1 - c2 * cos(t2) * w2
        v2y = -L1 * sin(t1) * w1 - c2 * sin(t2) * w2
        ek = 0.5 * m1 * (v1x * v1x + v1y * v1y) + 0.5 * J1 * w1 * w1 + 0.5 * m2 * (v2x * v2x + v2y * v2y) + 0.5 * J2 * w2 * w2
        ep = g0 * (m1 * c1 * (cos(t1) + 1.0) + m2 * (L1 * (cos(t1) + 1.0) + c2 * (cos(t2) + 1.0)))
        E = ek + ep
        Px = -(m1 * v1x + m2 * v2x)
        energy = E
        # mode transitions
        if mode < 0.5 && t >= t_on - 1.0e-9
            if rearm > 0.5
                mode = 3.0
                damping = 1.0
                rest = 0.0
            else
                mode = 1.0
                t_arm = t_on
            end
        end
        if mode > 2.5
            h1 = mod(t1 + 6.283185307179586, 6.283185307179586) - 3.141592653589793
            h2 = mod(t2 + 6.283185307179586, 6.283185307179586) - 3.141592653589793
            if abs(h1) < 0.0698131700797732 && abs(h2) < 0.0698131700797732 && abs(w1) < 0.25 && abs(w2) < 0.25 && abs(x) < 0.1 && abs(v) < 0.1
                rest = rest + 1.0
                if rest >= 50.0
                    mode = 1.0
                    t_arm = t
                    ox = x
                    o1 = 6.283185307179586 * round((t1 + 3.141592653589793) / 6.283185307179586)
                    o2 = 6.283185307179586 * round((t2 + 3.141592653589793) / 6.283185307179586)
                end
            else
                rest = 0.0
            end
        end
        ta = t - t_arm
        if mode > 0.5 && mode < 1.5
            if rearm > 0.5
                if ta >= T_s - catch_lead
                    zc = [x - ox, mod(t1 - o1 + 3.141592653589793, 6.283185307179586) - 3.141592653589793, mod(t2 - o2 + 3.141592653589793, 6.283185307179586) - 3.141592653589793, v, w1, w2]
                    if dot(zc, P * zc) < catch_tol || ta >= T_s - 1.0e-9
                        mode = 2.0
                        binit = 1.0
                    end
                end
            else
                if ta >= T_s - 1.0e-9
                    mode = 2.0
                    binit = 1.0
                end
            end
        end
        if mode > 1.5 && mode < 2.5 && rearm > 0.5
            if abs(r1) > drop || abs(r2) > drop
                mode = 3.0
                damping = 1.0
                rest = 0.0
                drops = drops + 1.0
            end
        end
        # the law of the mode
        out = 0.0
        if mode > 0.5 && mode < 1.5
            out = ff - (Ks[1] * (x - xs[1] - ox) + Ks[2] * (t1 - xs[2] - o1) + Ks[3] * (t2 - xs[3] - o2) + Ks[4] * (v - xs[4]) + Ks[5] * (w1 - xs[5]) + Ks[6] * (w2 - xs[6]))
        end
        if mode > 1.5 && mode < 2.5
            zb = [x, r1, r2, v, w1, w2]
            if binit > 0.5
                xo = zb
                binit = 0.0
            else
                xm = Am * xo + Bm * u3
                e1 = x - xm[1]
                e2 = mod(r1 - xm[2] + 3.141592653589793, 6.283185307179586) - 3.141592653589793
                e3 = mod(r2 - r1 - (xm[3] - xm[2]) + 3.141592653589793, 6.283185307179586) - 3.141592653589793
                xo = xm + Lo * [e1, e2, e3]
            end
            out = -(Kb[1] * xo[1] + Kb[2] * xo[2] + Kb[3] * xo[3] + Kb[4] * xo[4] + Kb[5] * xo[5] + Kb[6] * xo[6] + Kb[7] * u1 + Kb[8] * u2)
        end
        if mode > 2.5
            zh = [x, mod(t1 + 6.283185307179586, 6.283185307179586) - 3.141592653589793, mod(t2 + 6.283185307179586, 6.283185307179586) - 3.141592653589793, v, w1, w2]
            xstop = x + v * abs(v) / (1.2 * a_max)
            acc = 0.0
            lqr = 0.0
            if abs(xstop) > x_guard
                acc = ifelse(v >= 0.0, -a_max, a_max) - k_guard * x
            elseif E > e_lqr || damping > 0.5
                if E > 0.5 * e_lqr
                    damping = 1.0
                else
                    damping = 0.0
                end
                acc = -k_e * Px - kc_x * x - kc_v * v
            else
                lqr = 1.0
            end
            if lqr > 0.5
                out = -dot(Kh, zh)
            else
                out = (m_all * clamp(acc, -a_max, a_max) + beta * v) / alpha
            end
        end
        out = clamp(out, -u_max, u_max)
        tau = 0.0
        if mode > 0.5 && mode < 1.5
            tau = t + 0.001 - t_arm
        end
        phase = mode
        u = u2
        u3 = u2
        u2 = u1
        u1 = out
    end
end
