# Suction cup: one bellows cup and a box

One bellows suction cup holds a small box. The cup is a [SuctionCup](block:Cup), the 1.5-fold bellows cup of the `fanuc-pick` example (lip 32 mm, rest length 30 mm), with the nonlinear bellows switched on. It sits on a tool with a prescribed motion ([CupTool](block:Tool)). One compact ejector ([Gen](block:Gen)) evacuates it. The box is a free [RigidBody3D](block:Box) of 0.6 kg (120 x 120 x 40 mm). It starts on a table (four corner contacts [Floor1](block:Floor1) to `Floor4`, instances of the library subsystem `ContactFoot`: a mount and a [ContactPoint](block:Floor1/Contact) each), is lifted 60 mm, put through one motion, put back and released.

![The model canvas|900](assets/3110cdc3a111.png)

![The 3D view: the see-through bellows between the tool flange and the box, the lip coloured by U|700](assets/0fd115267d4c.png)

The example shows what the cup model does dynamically:

1. **Vacuum lift stroke.** The vacuum on the folds pulls the bellows shut. At 59 kPa that is 10 N, more than the weight of the box, so the cup lifts the box off the table before the tool moves.
2. **Axial spring-mass mode and bottoming.** The box rings on the bellows at 10.3 Hz. Driven hard, the folds stack up and the bellows hardens.
3. **Sway and tilt.** A lateral load moves the bellows sideways and tilts the box. That gives two lateral modes and a peeling moment on the lip.
4. **Holding limit.** The utilisation [U](signal:Cup/U) shows the margin. Past 1 the lip lifts, leaks and the seal is lost.

Every model is the same plant. The global `motion` picks the excitation:

| model | motion |
| --- | --- |
| `hold-release` (this one) | vacuum build-up, lift, hold, lower, release |
| `bounce` | a 4 mm step down, then a vertical chirp 3 to 20 Hz |
| `steps` | horizontal acceleration pulses of 1.5, 3 and 4.5 m/s² |
| `swing` | a slow tool tilt to 30° and back, then a fast ±10° swing |
| `chirp` | a lateral chirp 1.5 to 20 Hz, with the transmissibility |
| `overload` | a 0.8 kg box on pulses of 3, 6 and 9 m/s²: lost |
| `linear-vs-nonlinear` | the bounce with a second cup whose nonlinear terms are 0 |

## What to try

1. Press **Run** and open the **Dashboard** tab. The XY plot shows the force the cup transmits against its stroke while it is sealed ([Mon/T_c](signal:Mon/T_c) against [Mon/ext_c](signal:Mon/ext_c)). U, the vacuum, the lip gap and the deflections are read out next to it.
2. Raise **Payload mass** to 1.5 kg. The box now weighs more than the 10 N vacuum lift, so it stays on the table until the tool lifts it. The lift acceleration takes U to 0.86.
3. Lower **Vacuum level** to 30 kPa. The operating vacuum falls to 29.7 kPa, the capacity halves and the hold U doubles to 0.39. The lift force (5 N) no longer lifts the box off the table.
4. Open `bounce` and raise **Motion amplitude** to 1.05. The folds bottom harder (135 N), and the rebound tears the cup off at 4.93 s.
5. Move **Centre of mass offset x** to 0.03 m. The box hangs off-centre: the peeling moment $m g c_x$ = 0.18 N·m counts as $4M/D_{lip}$ = 22 N against the 29.6 N capacity, and the lip peels as soon as the box leaves the table.
