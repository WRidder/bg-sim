# Swing-up and catch

**Trajectory.** `design/design.py` finds the swing-up by Hermite–Simpson direct collocation on the Lagrangian
twin (CasADi + IPOPT): hanging rest to upright rest in T_s = 5 s, |F| ≤ 30 N, |x| ≤ 1.0 m, slew ≤ 3000 N/s.

**Tracking.** A discrete time-varying LQR (Q = diag(100, 400×4, 1, 5×4), R = 0.1) along the trajectory, with
the nominal made by a closed-loop roll-out of the 1 kHz sampled twin. The tables (10 ms knots) are parameters
of [Traj](block:Traj).

**Catch.** From τ = T_s − 0.5 s on, the firmware switches to the balance LQR as soon as the cost-to-go
z'Pz is below 1000, and latches. Here it catches at 5.50 s.

The stacked energy plot shows each link's kinetic plus potential energy (from the hanging rest), stacked:
the top curve is the total, which ends at the UPRIGHT level Σ m g 2h = 4.316 J.

![Link angles, stacked energy per link, cart and force, phase|900](assets/aae37d069f60.png)

The energy ledger: the actuator work W_in minus the friction losses W_loss equals the change of the
mechanical energy E_tot, so E_tot − W_in + W_loss stays constant.

![Energy ledger|900](assets/9919806ae99b.png)
