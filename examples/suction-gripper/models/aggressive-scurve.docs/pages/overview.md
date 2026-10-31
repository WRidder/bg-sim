# Aggressive S-curve: the same time, held

This model is the `transfer` plant with `kind` = 2 and `T_move` = 0.7 s. The peak acceleration is 13.1 m/s², 43 % more than the trapezoid in `aggressive-trapezoid`, but the jerk is finite (λ = 0.3).

![Utilisation and position|900](assets/7278fc749dce.png)

The maximum U reaches 1.18 for a moment, so the safety factor is gone, but no cup loses its seal. The carton slides about 1 cm on the lips during the hard deceleration and is placed at [Pose/px](signal:Pose/px) ≈ 0.99 m.
