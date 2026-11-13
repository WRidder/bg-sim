# Limits

The goal is a model in which a policy behaves as it does on the real robot. **That transfer is not shown here.** The checks cover the actuator and the body without a policy. The limits, most important first:

1. **No real robot.** Nothing here is checked against hardware. The published walking policy runs on the exported `microduck-policy` FMU in the browser demo; that shows what the policy does on this model, not that it would transfer. The demo feeds the policy joint velocities one control tick old, as training does. At zero command it stands (10 s, at most 2.31° of tilt). Up to 0.24 m/s asked (half forward is 0.2 m/s) it shifts its weight and stands. From 0.28 m/s it walks, slower than asked and on a curve: at full forward (0.4 m/s asked) 1.85 m in 10 s, 0.195 m/s over the last 5 s, heading turned 38°, without falling. One run each, in this model only.
2. **Differences from the training simulator** (mjlab with BAM), each of which can change a gait: no backlash in `microduck-policy` (velstand was trained with 2° of play in every joint; `microduck-policy-backlash` has it, `XL330Rigid` has none); a fixed 20 ms latency where training randomises 15 to 30 ms; an ideal supply; the deploy action scale 0.9 where training used 1.0; a flat floor; this model's contact law, four points per sole; friction smoothed instead of BAM's.
3. **Current limit.** Training and this model use BAM's 1.75 A window. The robot's impact-guard firmware limits the current to 1.0 A, derates the PWM with speed and brakes; none of that is modelled.
4. **Two BAM fits disagree**, by 6 % in $k_t$, 11 % in $R$ and 13 % in the armature. The newer fit is not the one the policies were trained with.
5. **Latency** is assumed (20 ms). The newer BAM fit identifies 10 ms.
6. **Backlash and gear stiffness** are training assumptions and guesses.
7. **Firmware** is modelled as a continuous law: no control period, and no encoder or PWM quantisation.
8. **Friction** is regularised: a held joint creeps slowly instead of sticking. Its external torque is the transmitted gear torque, where BAM uses gravity.
9. **No winding inductance and no heating.** The 8.2 V pack is above the servo's 6 V rating, as on the robot.
10. **Contacts.** Each sole has four contact points. In the policy robot the trunk, the head and the shins have frictionless bumper points too, so a fall lands; in the others nothing else touches the ground.
