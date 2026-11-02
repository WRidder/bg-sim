@block RotorPower begin
    # The main-rotor power and torque of the Heffley & Mnich model (lines 6780 .. 6850), an
    # energy estimate: induced T vi, climb W hdot, the fuselage's parasite power and the blade
    # profile power rho/2 (FR/4) Omega R (Omega^2 R^2 + 4.6 (u^2 + v^2)), FR = CDO R b c. The
    # torque P/Omega is the aerodynamic load on the rotor inertia of the drivetrain bond graph
    # (a modulated effort source); in the report it is the yaw moment N.MR directly.
    @inputs begin
        T::Real, [description = "Thrust (N)"]
        vi::Real, [description = "Induced velocity in the blade equation (m/s)"]
        u::Real
        v::Real
        om::Real, [description = "Rotor speed the aerodynamics see (rad/s)"]
        hdot::Real, [description = "Rate of climb (m/s)"]
        p_para::Real, [description = "Fuselage parasite power (W)"]
        rho::Real
    end
    @outputs begin
        power::Real, [description = "Main-rotor power (W)"]
        torque::Real, [description = "Main-rotor torque (N m)"]
        p_ind::Real
        p_climb::Real
        p_prof::Real
    end
    @parameters begin
        weight::Real = 24025.0, [description = "Weight (N)"]
        FR::Real = 0.0, [description = "CDO R b c (m^2)"]
        R::Real = 5.4864
    end
    @equations begin
        p_ind ~ T * vi
        p_climb ~ weight * hdot
        p_prof ~ 0.5 * rho * (FR / 4.0) * om * R * (om * om * R * R + 4.6 * (u * u + v * v))
        power ~ p_ind + p_climb + p_para + p_prof
        torque ~ power / om
    end
end
