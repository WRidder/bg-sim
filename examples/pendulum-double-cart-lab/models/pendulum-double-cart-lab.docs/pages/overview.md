# The double-cart lab rig: swing-up, balance and a push

A cart on a ±1.0 m rail with soft end stops carries a double pendulum of two **0.35 m** links. The motor, the
3:1 gearbox, the 16 mm belt pulley, the belt and the cart carriage are those of `pendulum-double-cart`; the
links are built the way a lab would build them: aluminium tubes 20 × 2 mm with a clamp hub at the pivot, on
link 1 a bearing head at the tip (the joint-2 bearings and encoder board), the encoder magnets and the
joint-2 cable. This example is the shared platform of the RL work and the robust classical work
(`plan/RL_PLAN.md`, `plan/ROBUST_CLASSICAL_PLAN.md`): every value comes from `design/realism.json`, which
also holds the ranges the robustness studies randomise over.

- The plant is the planar multibond bond graph of `pendulum-double-cart` ([Rail](block:Rail),
  [Joint1](block:Joint1), [Joint2](block:Joint2), [Body1](block:Body1), [Body2](block:Body2), the
  [Motor](block:Motor), [Gear](block:Gear), [Pulley](block:Pulley) and [Belt](block:Belt)), plus the
  carriage friction [RailFriction](block:RailFriction) and the rubber [EndStops](block:EndStops) at ±1.0 m.
- [Ctrl](block:Ctrl) (`DoubleCartLabCtrl`) is the 1 kHz firmware: 0 V until 1 s, the swing-up (feed-forward
  plus time-varying LQR from the tables of [Traj](block:Traj)), the discrete LQR from 4.0 s, and a 0.45 N,
  40 ms tip push ([PushPulse](block:PushPulse)) at 7.5 s.

![The model canvas|900](assets/b4d391275583.png)

![3D view at the end of the run: balanced upright, the green posts mark the ±0.8 m plan|500](assets/1a846c8ae419.png)

![Link angles, cart, voltage, current and phase over the run|900](assets/3b0b94197782.png)

Continue with [the rig](page:rig), [the design](page:design), [the realism screen](page:realism) and
[the results](page:results).
