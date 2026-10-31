# Derivation and sizing

The ball must follow the carriage, whose acceleration is $a = (0, a_h, a_v)$. Newton for the ball, $m a = m g_{vec} + F_A + F_B$, so the jaws must supply $F_A + F_B = m(a - g_{vec})$. The jaw normal is horizontal (x) and the motion is in y and z, so all of it is friction, and two jaws with the grip force $F$ each carry at most $2\mu F$:

$$m\sqrt{(g + a_v)^2 + a_h^2} \;\le\; 2\mu F \quad\Rightarrow\quad F \;\ge\; S\,\frac{m\sqrt{(g + a_v)^2 + a_h^2}}{2\mu}.$$

| case | $a_v$, $a_h$ (m/s²) | $F$ per jaw, $S = 1$ |
| --- | --- | --- |
| at rest | 0, 0 | 10.08 N |
| lift | 4, 0 | 14.19 N |
| transfer | 0, 20 | **22.89 N** |

The lift and the transfer do not overlap, so the transfer sizes the gripper: with $S = 2$, **46 N per jaw**. The grip current is the current at which a closing drive reaches 46 N, through the forward efficiency:

$$I_{grip} = \frac{F_{set}}{\eta\, k_t\, G} = \frac{46}{0.7\cdot 0.012\cdot 6283} = 0.872\ \mathrm{A},\qquad \tau = k_t I = 10.5\ \mathrm{mN\,m}.$$

[Grip](block:Grip) evaluates the rule over time: [Grip/need](signal:Grip/need) is $m|a - g|$, [Grip/F_req](signal:Grip/F_req) the force for $S = 1$, [Grip/demand](signal:Grip/demand) the friction the jaws actually deliver and [Grip/S_act](signal:Grip/S_act) the safety in effect:

![Grip force vs requirement, friction delivered vs needed, carriage acceleration|900](assets/da3b67ce88e7.png)

## Does the gripper deliver it?

The setting is the **lower bound** of the friction band. The closing decides where in the band the force ends: the 237 kg reflected inertia meets the pads at `v_grip` and compresses them beyond the forward value, and the drive friction keeps the extra force as long as it stays below the back-driving value. A reduced 1-DOF model of the closing (in `design/design.py`: jaw mass $\eta\cdot 237$ kg, the speed loop, the Hertz pads and the guide friction) predicts it:

| `v_grip` | reduced model peak | simulation peak | after the impact |
| --- | --- | --- | --- |
| 3 mm/s (default) | 57.39 N | 56.86 N | 56.8 N, locked in |
| 10 mm/s | 93.12 N | 92.56 N | 92.4 N, locked in |
| 20 mm/s | 148.45 N | 147.45 N | 92.0 N, back-driven into the band |
| 30 mm/s | 207.28 N | 205.79 N | 50.9 N, back-driven into the band |

So the sized ball is held at 56.8 N (safety in effect 2.48), but **the extra force depends on the closing and must not be counted on**: size the setting.

![Closing at 20 mm/s: the peak exceeds the back-driving force, the drive gives way and the force falls back into the band|900](assets/c36731695447.png)
