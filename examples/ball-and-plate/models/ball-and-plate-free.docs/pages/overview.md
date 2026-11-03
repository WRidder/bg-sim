# Free roll on a tilted plate

**Scenario.** The servos are replaced by stiff `C`/`R` locks on the gimbal drives
([SpringX](block:SpringX), [DamperX](block:DamperX)), which hold the plate at **1°** about y. The
spring of the X lock starts preloaded with the ball's weight torque. The ball is released at rest
**0.15 m** from the centre, uphill.

**What it checks.**

- **Roll time.** A rolling solid sphere accelerates at a = 5/7 g sin α = 0.12229 m/s², so it
  reaches the centre after **1.5663 s**. The model ([Contact/u1](signal:Contact/u1)) gives
  1.5662 s.
- **Rotational energy.** It is 2/7 of the kinetic energy
  ([Energy/Ekrot](signal:Energy/Ekrot) / [Energy/Ek](signal:Energy/Ek)).
- **No slip.** The slip ([Contact/slip](signal:Contact/slip)) creeps at only 1.25e-5 m/s, the
  regularisation of the friction.
- **Energy book.** [Energy/Ebal](signal:Energy/Ebal) (stored energy plus the contact losses) stays
  constant to 2e-9 J.
- **Hollow ball.** The check run with `k_ball` = 2/3 gives 3/5 g sin α and a time of 1.7089 s.

![Free roll: position, kinetic energy and slip|900](assets/f5f421ea07a1.png)

**What to try.** On the dashboard:

- Set the ball inertia to 0.667, a hollow ball of the same mass, and it rolls slower.
- Raise the rolling resistance to 0.02 and the ball barely moves: a ball rests on a tilt smaller
  than crr.

The rig: [the ball-and-plate rig](project:rig).
