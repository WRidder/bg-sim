@block FlightSequence begin
    # The vehicle's mass budget and engine schedule: what is burning, how fast, and what is
    # dropped when. It is the "propellant tank and staging" part of the rocket; the momentum law
    # lives in the bond graph (`VariableInertia3D` and the outflow `MR`s), which reads its outputs.
    #
    # Engine phases (np of them) start at `t_ph[k]`; in phase k the commanded propellant flow is
    # `mdot_ph[k]`, the vacuum effective exhaust velocity `c_ph[k]` and the total nozzle exit area
    # `ae_ph[k]`. The flow follows the command through a first-order lag `tau` (the start-up and
    # thrust decay of the engines; the cutoff impulse of a lag is `T tau`).
    #
    # Jettisons (nj of them) at `t_j[k]` drop `dm_j[k]` (a stage, an interstage, the escape tower)
    # as a short constant mass flow over `tau_j`, so the separated part leaves through the same
    # outflow `MR` as the propellant and takes the vehicle's momentum with it: the vehicle's speed
    # does not jump. The radii of gyration ramp to the next configuration over the same window
    # (`rgp[k]`, `rgr[k]`: pitch/yaw and roll in configuration k, k = 1 .. nj + 1) and the gimbal
    # arm `lg[k]` (CoM to engine gimbal) switches at `t_j[k]`.
    #
    # Outputs: the mass `m`, the inertia `J`, the propellant flow `mdot` for the engine, the
    # outflow resistances `r_lin = -dm/dt` and `r_ang1..3 = -dJk/dt` for the MRs, and the phase
    # values `c`, `ae`, `l`.
    @constants begin
        np::Int = 2, [min = 1, description = "Number of engine phases"]
        nj::Int = 1, [min = 1, description = "Number of jettisons (use one with dm = 0 for none)"]
    end
    @parameters begin
        t_ph::Vec{np} = [0.0, 10.0], [unit = "s", description = "Start time of each engine phase (t_ph[1] = 0)"]
        mdot_ph::Vec{np} = [10.0, 0.0], [unit = "kg/s", description = "Commanded propellant flow in each phase"]
        c_ph::Vec{np} = [2500.0, 2500.0], [unit = "m/s", description = "Vacuum effective exhaust velocity in each phase"]
        ae_ph::Vec{np} = [0.1, 0.1], [unit = "m^2", description = "Total nozzle exit area in each phase"]
        tau::Real = 0.33, [unit = "s", min = 1.0e-3, description = "Engine flow lag (start-up and thrust decay)"]
        t_j::Vec{nj} = [1.0e9], [unit = "s", description = "Jettison times"]
        dm_j::Vec{nj} = [0.0], [unit = "kg", description = "Mass dropped at each jettison"]
        tau_j::Real = 0.2, [unit = "s", min = 1.0e-3, description = "Duration of a jettison's mass ramp"]
        rgp::Vec{nj + 1} = [3.0, 3.0], [unit = "m", description = "Pitch/yaw radius of gyration per configuration"]
        rgr::Vec{nj + 1} = [0.5, 0.5], [unit = "m", description = "Roll radius of gyration per configuration"]
        lg::Vec{nj + 1} = [5.0, 5.0], [unit = "m", description = "CoM to engine gimbal per configuration"]
    end
    @variables begin
        m_s::Real = 1000.0, [unit = "kg", state = :prefer, description = "Mass"]
        mdot_s::Real = 10.0, [unit = "kg/s", state = :prefer, description = "Propellant flow (lagged)"]
        rgp2::Real = 9.0, [unit = "m^2", state = :prefer, description = "Pitch radius of gyration squared"]
        rgr2::Real = 0.25, [unit = "m^2", state = :prefer, description = "Roll radius of gyration squared"]
        cmd::Real, [unit = "kg/s"]
        jet::Real, [unit = "kg/s", description = "Jettison mass flow"]
        drgp2::Real, [unit = "m^2/s"]
        drgr2::Real, [unit = "m^2/s"]
        on::Vec{np}, [description = "1 from the start of engine phase k on"]
        w::Vec{np}, [description = "1 inside engine phase k"]
        win::Vec{nj}, [description = "1 inside the ramp window of jettison k"]
        past::Vec{nj}, [description = "1 from jettison k on"]
        ramp::Vec{nj}, [description = "Progress of jettison k (0 .. 1)"]
        dlg::Vec{nj}, [unit = "m"]
        dp2::Vec{nj}, [unit = "m^2/s"]
        dr2::Vec{nj}, [unit = "m^2/s"]
        mdot_tot::Real, [unit = "kg/s", description = "Total mass outflow"]
    end
    @outputs begin
        m::Real, [unit = "kg"]
        J::Vec{3}, [unit = "kg*m^2"]
        mdot::Real, [unit = "kg/s"]
        r_lin::Real, [unit = "kg/s"]
        r_ang1::Real, [unit = "kg*m^2/s"]
        r_ang2::Real, [unit = "kg*m^2/s"]
        r_ang3::Real, [unit = "kg*m^2/s"]
        c::Real, [unit = "m/s"]
        ae::Real, [unit = "m^2"]
        l::Real, [unit = "m"]
        dropped::Real, [unit = "kg", description = "Mass jettisoned so far"]
    end
    @equations begin
        for k in 1:np
            on[k] ~ ifelse(t >= t_ph[k], 1.0, 0.0)
        end
        for k in 1:np - 1
            w[k] ~ on[k] - on[k + 1]
        end
        w[np] ~ on[np]
        cmd ~ dot(w, mdot_ph)
        c ~ dot(w, c_ph)
        ae ~ dot(w, ae_ph)
        for k in 1:nj
            past[k] ~ ifelse(t >= t_j[k], 1.0, 0.0)
            win[k] ~ past[k] - ifelse(t >= t_j[k] + tau_j, 1.0, 0.0)
            ramp[k] ~ clamp((t - t_j[k]) / tau_j, 0.0, 1.0)
            dlg[k] ~ lg[k + 1] - lg[k]
            dp2[k] ~ (rgp[k + 1] * rgp[k + 1] - rgp[k] * rgp[k]) / tau_j
            dr2[k] ~ (rgr[k + 1] * rgr[k + 1] - rgr[k] * rgr[k]) / tau_j
        end
        l ~ lg[1] + dot(past, dlg)
        dropped ~ dot(ramp, dm_j)
        jet ~ dot(win, dm_j) / tau_j
        drgp2 ~ dot(win, dp2)
        drgr2 ~ dot(win, dr2)
        ddt(mdot_s) ~ (cmd - mdot_s) / tau
        mdot_tot ~ mdot_s + jet
        ddt(m_s) ~ -mdot_tot
        ddt(rgp2) ~ drgp2
        ddt(rgr2) ~ drgr2
        m ~ m_s
        mdot ~ mdot_s
        J[1] ~ m_s * rgr2
        J[2] ~ m_s * rgp2
        J[3] ~ m_s * rgp2
        r_lin ~ mdot_tot
        r_ang1 ~ mdot_tot * rgr2 - m_s * drgr2
        r_ang2 ~ mdot_tot * rgp2 - m_s * drgp2
        r_ang3 ~ mdot_tot * rgp2 - m_s * drgp2
    end
end
