@block PropRotor begin
    # The single propeller as a gyrostat with its own aerodynamic load (the "one motor" of the
    # vehicle). The carrier port `p` is a body 1-junction: the block stores only the axial spin
    # momentum `h = Ja (w_z + w_rel)`, so a 540 rad/s propeller costs no more than a still one
    # and the body does not resolve the revolution. The `motor` port is a Rotation port whose
    # flow is the spin rate relative to the carrier and whose effort is the net shaft torque on
    # the rotor; its reaction `-motor.e` reaches the carrier through `p.e[3]`, and the
    # gyroscopic torque `-w x h e_z` through `p.e[1]`, `p.e[2]`.
    #
    # Aerodynamics of a fixed-pitch propeller on the absolute spin rate `W = h/Ja` (the blades
    # see the air, not the carrier):
    #
    #   T = kT W |W| (1 - 2 k_thrust tau_net^2)     thrust along the carrier +z
    #   Q = kQ W |W|                                drag torque on the rotor
    #
    # Swashplateless hub moment. `tau_net = motor.e - Q = Ja dW/dt` is the torque that
    # accelerates the rotor. The blades sit on lag-pitch hinges: an angular acceleration of the
    # hub makes the blades lag, the skewed hinges turn the lag into pitch (up on one blade, down
    # on the other), and the lift difference is a moment along the blade-normal direction that
    # turns with the rotor. Quasi-static hinges (the pitch follows the acceleration, and the
    # lift change per unit pitch scales with W^2 while the hinge lag per unit acceleration
    # scales with 1/W^2) give a hub moment proportional to the acceleration alone:
    #
    #   Mx = 2 kM tau_net cos(psi),   My = 2 kM tau_net sin(psi)
    #
    # in body axes, with `psi` the rotor azimuth (the hinge phase is absorbed in the azimuth
    # reference). Nothing here knows the cyclic command: a once-per-revolution torque
    # `tau_net = c_x cos psi + c_y sin psi` gives the mean moment kM (c_x, c_y) plus a 2/rev
    # ripple, a steady acceleration gives a 1/rev moment with zero mean, and whatever the speed
    # loop adds to the ripple changes the moment too. `kM` is an assumed gain (no bench data).
    # The same pitch difference costs a little mean thrust (the `k_thrust` term, `k_thrust A^2`
    # for a cyclic amplitude A).
    @ports begin
        p::Power{Spatial}, [frame = "body"]
        motor::Power{Rotation}
    end
    @inputs psi::Real, [unit = "rad", description = "Rotor azimuth relative to the body"]
    @outputs begin
        T::Real, [unit = "N", description = "Thrust along the carrier +z"]
        Q::Real, [unit = "N*m", description = "Propeller drag torque on the rotor"]
        w::Real, [unit = "rad/s", description = "Spin rate relative to the carrier"]
        w_abs::Real, [unit = "rad/s", description = "Absolute axial spin rate h/Ja"]
        h::Real, [unit = "N*m*s", description = "Axial angular momentum"]
        tau::Real, [unit = "N*m", description = "Net shaft torque on the rotor (motor.e)"]
        tau_net::Real, [unit = "N*m", description = "Accelerating torque motor.e - Q = Ja dW/dt"]
        Mx::Real, [unit = "N*m", description = "Hub moment about body x"]
        My::Real, [unit = "N*m", description = "Hub moment about body y"]
    end
    @parameters begin
        Ja::Real = 3.5e-4, [unit = "kg*m^2", min = 1.0e-9, description = "Axial inertia of the rotor and propeller"]
        kT::Real = 4.35e-5, [min = 0, description = "Thrust coefficient, T = kT W^2 (N s^2/rad^2)"]
        kQ::Real = 1.05e-6, [min = 0, description = "Drag torque coefficient, Q = kQ W^2 (N m s^2/rad^2)"]
        kM::Real = 0.25, [min = 0, description = "Mean hub moment per N m of once-per-revolution torque amplitude"]
        k_thrust::Real = 0.02, [min = 0, description = "Mean thrust lost per (N m)^2 of cyclic torque amplitude"]
        eps_w::Real = 1.0, [unit = "rad/s", min = 1.0e-9, description = "Smoothing speed of W |W|"]
    end
    @variables begin
        a::Real = 0.0, [description = "Smooth W |W|"]
        h_s::Real = 0.0, [state = :prefer, unit = "N*m*s", description = "Axial angular momentum state"]
    end
    @equations begin
        motor.f ~ h_s / Ja - p.f[3]
        w ~ motor.f
        w_abs ~ h_s / Ja
        a ~ w_abs * sqrt(w_abs * w_abs + eps_w * eps_w)
        Q ~ kQ * a
        tau ~ motor.e
        tau_net ~ motor.e - Q
        T ~ kT * a * (1.0 - 2.0 * k_thrust * tau_net * tau_net)
        ddt(h_s) ~ motor.e - Q
        Mx ~ 2.0 * kM * tau_net * cos(psi)
        My ~ 2.0 * kM * tau_net * sin(psi)
        p.e[1] ~ p.f[2] * h_s
        p.e[2] ~ -p.f[1] * h_s
        p.e[3] ~ motor.e
        p.e[4] ~ 0.0
        p.e[5] ~ 0.0
        p.e[6] ~ 0.0
        h ~ h_s
    end
    @causality begin
        p => (:effort_out, :fixed)
        motor => :flow_out
    end
    @orientation begin
        p => :in
        motor => :in
    end
end
