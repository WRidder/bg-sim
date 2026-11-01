@@ figures quad-pendulum-swingup
{
  "diagram": {"kind": "diagram", "model": "quad-pendulum-swingup"},
  "scene": {"kind": "scene", "model": "quad-pendulum-swingup", "t": 10.0},
  "run": {
    "kind": "plot", "model": "quad-pendulum-swingup", "xlim": [0, 10],
    "rows": [
      {"ylabel": "link angle [deg]", "series": [{"signal": "Mon/th1", "label": "θ1"}, {"signal": "Mon/th2", "label": "θ2"}, {"signal": "Mon/th3", "label": "θ3"}, {"signal": "Mon/th4", "label": "θ4"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "stacked energy [J]", "series": [{"signal": "Mon/S1", "label": "E1"}, {"signal": "Mon/S2", "label": "E1+E2"}, {"signal": "Mon/S3", "label": "E1..E3"}, {"signal": "Mon/S4", "label": "total"}], "legend": true, "legend_loc": "right",
       "hlines": [{"y": 4.3164, "label": "UPRIGHT 4.32 J"}]},
      {"ylabel": "cart x [m], F/40 [-]", "series": [{"signal": "Rail/qout", "label": "x [m]"}, {"signal": "Ctrl/u", "label": "F / 40 N", "scale": 0.025}], "legend": true, "legend_loc": "right"},
      {"ylabel": "phase", "series": [{"signal": "Ctrl/phase", "label": "0 hold, 1 swing-up, 2 balance"}], "legend": true, "legend_loc": "right"}
    ]
  },
  "ledger": {
    "kind": "plot", "model": "quad-pendulum-swingup", "xlim": [0, 10],
    "rows": [
      {"ylabel": "energy [J]", "series": [{"signal": "Mon/E_tot", "label": "E_tot"}, {"signal": "Mon/W_in", "label": "W_in"}, {"signal": "Mon/W_loss", "label": "W_loss"}, {"signal": "Mon/ledger", "label": "E_tot − W_in + W_loss"}], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page quad-pendulum-swingup overview - | Overview
# Quad pendulum on a cart: swing-up and balance

A cart on a ±1.5 m rail carries a chain of **four** passive pendulum links (4 × 0.275 m, 0.10 kg). One
force on the cart swings the chain up from hanging at rest and balances it upright.

- The plant is a planar multibond bond graph: [Rail](block:Rail) (`Prismatic2D`), the cart and four
  `RigidBody2D` links on `Revolute2DCompliant` joints with viscous friction. The rail drive carries the
  [Force](block:Force) (ideal force source), [RailFriction](block:RailFriction) and soft [EndStops](block:EndStops).
- [Ctrl](block:Ctrl) (`QuadCartCtrl`) is the 1 kHz firmware: hold for 1 s, then **SWINGING UP** (feed-forward
  plus time-varying LQR along an offline trajectory, looked up by [Traj](block:Traj)), then **BALANCING**
  (latched infinite-horizon LQR) once the state enters the catch region.
- [Mon](block:Mon) (`QuadCartMonitor`) computes the link angles, the energy per link, the stacked energy and
  the energy ledger from the bodies' twists and poses.

![The model canvas|900](@fig:diagram)

![3D view at t = 10 s: the chain balanced upright|500](@fig:scene)

Continue with [the swing-up](page:swingup) and [the results](page:results).
@@ page quad-pendulum-swingup swingup overview | Swing-up and catch
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

![Link angles, stacked energy per link, cart and force, phase|900](@fig:run)

The energy ledger: the actuator work W_in minus the friction losses W_loss equals the change of the
mechanical energy E_tot, so E_tot − W_in + W_loss stays constant.

![Energy ledger|900](@fig:ledger)
@@ page quad-pendulum-swingup results overview | Results and checks
# Results and checks

Real worker, Rodas5P, reltol 1e-7:

| quantity | bond graph | design closed loop (twin) |
| --- | --- | --- |
| at rest before 1 s | exactly | |
| all links within 5° | 3.97 s | 3.97 s |
| catch (BALANCING) | 5.50 s | 5.50 s |
| largest link deviation from 7.5 s | 0.00066° | 0.00066° |
| peak force | 13.61 N of 40 N | 13.61 N |
| peak cart travel | 0.581 m of ±1.5 m | 0.581 m |
| stacked energy at 10 s | 4.3164 J = UPRIGHT | |
| actuator work, friction losses | 6.99 J, 2.68 J | |
| free swing vs twin (cart, largest angle) | 1.0e-7 m, 7.0e-4° | |
| balance scenario: push peak, recovery inside 0.5° | 9.36°, 1.79 s | 9.36° |

The plant agrees with the twin so closely that the closed loops agree to the printed digits. In the design
closed loop the swing-up also survives ±5 % link masses, +1 % lengths, three times the joint friction, twice
the rail friction, +10 % cart mass, 1 or 2 ms of actuator delay and quantised encoders.

`expected.json` checks the swing-up (catch, the angles against the design closed loop at two instants,
the 0.5° band from 7.5 s, the force limit, the rail, the final stacked energy and the ledger), the balance
scenario and the free swing against the twin. The tolerances are named in every check's note.
@@ figures quad-pendulum-balance
{
  "run": {
    "kind": "plot", "model": "quad-pendulum-balance", "xlim": [0, 7],
    "rows": [
      {"ylabel": "link angle [deg]", "series": [{"signal": "Mon/th1", "label": "θ1"}, {"signal": "Mon/th2", "label": "θ2"}, {"signal": "Mon/th3", "label": "θ3"}, {"signal": "Mon/th4", "label": "θ4"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "cart x [m]", "series": [{"signal": "Rail/qout", "label": "x"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "F [N]", "series": [{"signal": "Ctrl/u", "label": "F"}], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page quad-pendulum-balance overview - | Overview
# Quad pendulum on a cart: balance only

The model `quad-pendulum-swingup` with the firmware in the balance phase from
the start (`Ctrl/balance_only`). The chain starts leaning 2° per link (globals `th0_1..th0_4`), the LQR
catches it, and a 50 ms push on the tip at 3 s (half of the largest push the design closed loop survives)
tests the recovery.

![Link angles, cart position and force|900](@fig:run)

Try the dashboard inputs: the start angles, an actuator delay (whole 1 ms samples), quantised encoders
(16-bit joints, 10 µm cart, filtered difference rates), a heavier or lighter chain (the gains stay nominal)
and a lower force limit.
@@ figures quad-pendulum-free
{
  "run": {
    "kind": "plot", "model": "quad-pendulum-free", "xlim": [0, 1.5],
    "rows": [
      {"ylabel": "link angle [deg]", "series": [{"signal": "Mon/th1", "label": "θ1"}, {"signal": "Mon/th2", "label": "θ2"}, {"signal": "Mon/th3", "label": "θ3"}, {"signal": "Mon/th4", "label": "θ4"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "cart x [m]", "series": [{"signal": "Rail/qout", "label": "x"}], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page quad-pendulum-free overview - | Overview
# Quad pendulum on a cart: free swing, the twin check

No control (the swing-up never starts). The chain starts from a tilted pose at rest and swings freely for
1.5 s, with the cart free on the rail. `expected.json` compares the cart position and the four link angles
every 0.25 s with the Python twin (the Lagrangian of `design/quadlib.py`, integrated by SciPy DOP853 at
rtol 1e-11): the largest difference is 1.0e-7 m on the cart and 7.0e-4° on the link angles. The energy ledger (mechanical energy plus friction losses)
stays constant to 1e-6 J.

![Free swing: link angles and cart|900](@fig:run)
@@ figures quad-rotary-swingup
{
  "diagram": {"kind": "diagram", "model": "quad-rotary-swingup"},
  "scene": {"kind": "scene", "model": "quad-rotary-swingup", "t": 10.0},
  "run": {
    "kind": "plot", "model": "quad-rotary-swingup", "xlim": [0, 10],
    "rows": [
      {"ylabel": "link angle [deg]", "series": [{"signal": "Mon/th1", "label": "θ1"}, {"signal": "Mon/th2", "label": "θ2"}, {"signal": "Mon/th3", "label": "θ3"}, {"signal": "Mon/th4", "label": "θ4"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "stacked energy [J]", "series": [{"signal": "Mon/S1", "label": "E1"}, {"signal": "Mon/S2", "label": "E1+E2"}, {"signal": "Mon/S3", "label": "E1..E3"}, {"signal": "Mon/S4", "label": "total"}], "legend": true, "legend_loc": "right",
       "hlines": [{"y": 0.70632, "label": "UPRIGHT 0.706 J"}]},
      {"ylabel": "arm [rad], torque [N m]", "series": [{"signal": "J1/qout", "label": "arm angle [rad]"}, {"signal": "Ctrl/u", "label": "torque [N m]"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "phase", "series": [{"signal": "Ctrl/phase", "label": "0 hold, 1 swing-up, 2 balance"}], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page quad-rotary-swingup overview - | Overview
# Quad pendulum on a rotary arm: swing-up and balance

The Furuta version: a horizontal arm (0.30 m) turns about the vertical axis, driven by an ideal torque
(±3 N m), and carries a chain of four links (4 × 0.15 m, 0.03 kg) at its tip. The pendulum joints point
along the arm, so the links swing in the vertical plane tangent to the arm circle.

- The plant is a spatial multibond bond graph: [J1](block:J1) (`Revolute3D` about world z) with
  [Motor](block:Motor) (ideal torque source) and [ArmBearing](block:ArmBearing) on its drive, the
  [Arm](block:Arm) body (the hub/rotor inertia is lumped into it), and four `Revolute3D` + `RigidBody3D`
  links with viscous bearing friction.
- [Ctrl](block:Ctrl) (`QuadRotaryCtrl`), [Traj](block:Traj) and [Mon](block:Mon) follow the cart version.

![The model canvas|900](@fig:diagram)

![3D view at t = 10 s: the chain balanced upright on the arm|500](@fig:scene)

**Design.** The same method as the cart (collocation, TVLQR, discrete LQR). The rotary rig has much less
authority over the chain: the trajectory runs at its bounds (|u| ≤ 2.5 N m, |θ_arm| ≤ 2.5 rad) and the TVLQR
saturates the torque at 3 N m for short moments. In the design closed loop the swing-up is robust to ±5 %
masses, +1 % lengths, three times the joint friction and 1 ms delay, but **not** to a 2 ms delay or to
quantised encoders; the balance alone is robust to both.

![Link angles, stacked energy per link, arm and torque, phase|900](@fig:run)

## Results

| quantity | bond graph | design closed loop (twin) |
| --- | --- | --- |
| all links within 5° | 4.42 s | 4.42 s |
| catch (BALANCING) | 5.50 s | 5.50 s |
| largest link deviation from 7.5 s | 0.0030° | 0.0030° |
| peak torque | 3.00 N m of 3 N m | 3.00 N m |
| peak arm travel | 2.50 rad of ±3 rad | 2.50 rad |
| stacked energy at 10 s | 0.7063 J = UPRIGHT | |
| free swing vs twin (arm, largest angle) | 1.7e-6 rad, 2.6e-3° | |
| balance scenario: push peak, recovery inside 0.5° | 10.05°, 1.60 s | 10.05° |
@@ figures quad-rotary-balance
{
  "run": {
    "kind": "plot", "model": "quad-rotary-balance", "xlim": [0, 7],
    "rows": [
      {"ylabel": "link angle [deg]", "series": [{"signal": "Mon/th1", "label": "θ1"}, {"signal": "Mon/th2", "label": "θ2"}, {"signal": "Mon/th3", "label": "θ3"}, {"signal": "Mon/th4", "label": "θ4"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "arm [rad]", "series": [{"signal": "J1/qout", "label": "arm angle"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "torque [N m]", "series": [{"signal": "Ctrl/u", "label": "torque"}], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page quad-rotary-balance overview - | Overview
# Quad pendulum on a rotary arm: balance only

The rotary model in the balance phase from the start: the chain leans 2° per link, the LQR catches it and a
50 ms tip push at 3 s tests the recovery.

![Link angles, arm angle and torque|900](@fig:run)
@@ figures quad-rotary-free
{
  "run": {
    "kind": "plot", "model": "quad-rotary-free", "xlim": [0, 1.5],
    "rows": [
      {"ylabel": "link angle [deg]", "series": [{"signal": "Mon/th1", "label": "θ1"}, {"signal": "Mon/th2", "label": "θ2"}, {"signal": "Mon/th3", "label": "θ3"}, {"signal": "Mon/th4", "label": "θ4"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "arm [rad]", "series": [{"signal": "J1/qout", "label": "arm angle"}], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page quad-rotary-free overview - | Overview
# Quad pendulum on a rotary arm: free swing, the twin check

No control: the arm and the chain start tilted at rest and swing freely for 1.5 s. `expected.json` compares
the arm angle and the link angles every 0.25 s with the Python twin (the spatial Lagrangian of
`design/quadlib.py`): the largest difference is 1.7e-6 rad on the arm and 2.6e-3° on the link angles.

![Free swing: link angles and arm|900](@fig:run)
