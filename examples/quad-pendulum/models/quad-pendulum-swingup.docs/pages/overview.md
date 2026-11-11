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

![The model canvas|900](assets/aee913042e6e.png)

![3D view at t = 10 s: the chain balanced upright|500](assets/60d6b8cb39e8.png)

Continue with [the swing-up](page:swingup) and [the results](page:results).
