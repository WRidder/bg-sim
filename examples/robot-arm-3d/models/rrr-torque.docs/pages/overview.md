# RRR arm with ideal torque sources

The equation-block arm [Arm](block:Arm) driven by ideal joint-torque sources ([Drive1](block:Drive1), [Drive2](block:Drive2), [Drive3](block:Drive3), `MSe` with gain 1) from the same `ArmCtrl3R` firmware ([Ctrl](block:Ctrl)) and the same `TimeTable` references as `rrr-multibond`. It is the comparison partner of the multibond arm (DEC-M5-2): a clean comparison needs the plants to be the only difference, and the motors cannot be shared because a rotor inertia rigidly coupled to the multibond joint's rate is derivative-causal with the body inertia; the multibond arm behind the `DCMotor` and `IdealGear` chain compiled with W201 on every body momentum and then stopped at $t = 0$ with E901 (retcode `Unstable`), measured. The controller's `tc` output (joint torque command, [Ctrl/tc1](signal:Ctrl/tc1)) drives the sources.

![The model canvas|900](assets/835567525112.png)

![Joint angles and torque commands|900](assets/0e3b974d62d3.png)

The closed loop pulls both arms to the same references, so the comparison is of the dynamics under the same feedback. This model is the reference for the `compare` checks of `rrr-multibond`; see that model for the tolerances. The run lasts 5 s with `reltol` 1e-8, `abstol` 1e-10 and 2001 points.
