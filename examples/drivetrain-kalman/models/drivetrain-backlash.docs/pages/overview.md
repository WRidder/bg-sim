# LQG drivetrain with gear backlash

The same plant, firmware and signals as `drivetrain-kalman`, but the ideal gear (`TFa` and `TFb`) is replaced by the [GearWithBacklash](block:Gear) composite from library `library/GearWithBacklash.jl`: a `LossyGear` ($n = 10$, $\eta = 1$) in series with a `GearBacklash` play. The controller is **the same LQG firmware designed for the ideal gear** (the design script writes identical matrices into both models), so this variant shows how the loop behaves when the model it was designed on is wrong.

![The model canvas|900](assets/c03fbacbdf77.png)

## The backlash

`GearBacklash` has the tooth stiffness $k = 10^4$ N·m/rad, damping $d = 5$ N·m·s/rad and total play $\mathrm{gap} = 0.02$ rad. With the relative angle $\varphi$ and speed $w$ across the gear the torque is

$$T = \begin{cases} \max\big(k\,(\varphi - \tfrac{gap}{2}) + d\,w,\ 0\big) & \varphi > gap/2 \\ \min\big(k\,(\varphi + \tfrac{gap}{2}) + d\,w,\ 0\big) & \varphi < -gap/2 \\ 0 & \text{otherwise (flanks apart)} \end{cases}$$

and the ports apply $a.e = T$, $b.e = -T$.

## What changes

- The run completes (2 s, 4001 points) and the check only demands that the voltage stays within 24 V and that no E901, E106 or W206 appears. Plot [IW2/p.f](signal:IW2/p.f) against [LQG/w_load_hat](signal:LQG/w_load_hat): the loop settles into a limit cycle around 10 rad/s; the README gives an RMS of 0.43 rad/s between the estimate and the plant.
- Compare with the ideal-gear model: its estimate error RMS is 0.181 rad/s.
- The 3D scene additionally binds the gear play `Gear/play/phi` (gain -1) between the gear output and wheel 1.

![Load speed and voltage with backlash|900](assets/51308a8fe506.png)

## Modelling notes

- The composite's `LossyGear` is ideal ($\eta = 1$): the fixture's 0.9 efficiency is a loss model, and with the phase-shifted algebraic switch the stiff DAE failed the solver (E901).
- The composite's ports declare `Rotation`, so the stdlib `GY` (two `Generic` ports) would straddle a Rotation and a Generic island (E102). The variant therefore uses `library/MotorGY.jl` ([GY](block:GY)), the same gyrator equations with explicit Electrical and Rotation ports. The final bond runs wheel 1 to the gear so that the single transformer inside the composite has the same +10:1 sign as the ideal `TF(1)·TF(0.1)` chain.
