# Plant and controller

## Bond graph

Velocities are positive **upward**; the gap is $h = z_\mathrm{rail} - z_\mathrm{bogie}$.

| part | bond graph |
| --- | --- |
| chopper | `MSe` [Amp](block:Amp) (voltage), limited to ±800 V by the controller |
| coil | 1-junction [Jc](block:Jc) (coil current) with the resistance [Rc](block:Rc), a current detector [Imeas](block:Imeas), and, through the 0-junction [Jv](block:Jv) with the voltage detector [Vcoil](block:Vcoil), the coil port of [EM](block:EM) |
| magnet | [EM](block:EM): `converters/Electromagnet`, co-energy $W' = L(h) i^2/2$, $L(h) = L_\infty + 2\alpha/h$. Its port $b$ is on the rail junction [Jr](block:Jr), its port $a$ on the bogie junction [Jb](block:Jb). |
| bogie | 1-junction [Jb](block:Jb) with the chassis mass [Chassis](block:Chassis) (`I`), its weight [Weight](block:Weight) (`Se`), the skid contact [Skid](block:Skid) (`HardStop`, 16 mm to 4 mm free travel) and the secondary suspension [Sus](block:Sus) (`SpringDamper`) |
| body | 1-junction [Jq](block:Jq) with the body mass [Body](block:Body), its weight [BodyWeight](block:BodyWeight) and the payload [Load](block:Load) |
| guideway | flow source [Rail](block:Rail) on [Jr](block:Jr): the rail velocity from a smoothed step |
| gap sensor | 0-junction [Jg](block:Jg) between rail and bogie; its flow is $\dot h$, and the integrator [Gap](block:Gap) gives the gap |

The coil carries $L(h)\,\dot i = v - R i + \dfrac{2\alpha i}{h^2}\,\dot h$ and the magnet pulls with $F = \alpha i^2/h^2$. The field stores exactly what flows in: the electrical port power $v\,i$ and the mechanical port power $F\,\dot h$ add up to $\mathrm{d}W/\mathrm{d}t$.

## Trim and the unstable pole

At the gap $h$ the magnet carries the weight $W = (m_b + m_c)\,g$ when the current is
$$ i_\mathrm{trim} = c_\mathrm{trim}\,h, \qquad c_\mathrm{trim} = \sqrt{W/\alpha} = 15000\ \mathrm{A/m}, $$
so 150 A at 10 mm. Linearised about this point (states $h$, $v_b$, spring stretch, $v_c$, $i$), the voltage-driven plant has the poles $+52.7$, $-67.1$, $-18.7$ and $-2.0 \pm 5.9\mathrm{j}$ 1/s: one **unstable real pole** at 52.7 1/s (8.4 Hz), the secondary-suspension mode at 1 Hz, and the coil/back-EMF modes.

## Controller

The block [Ctl](block:Ctl) (`GapController`, in `library/`) is full state feedback on the measured gap, its filtered rate (1 ms filter) and the coil current, with an integrator on the gap error and the trim feedforward:

$$ v = R\,i_\mathrm{ff} + a_1 (h - h_\mathrm{ref}) + a_2 \dot h_f + a_3 (i - i_\mathrm{ff}) + a_4 \!\int\!(h - h_\mathrm{ref}),\qquad i_\mathrm{ff} = c_\mathrm{trim}\,h_\mathrm{ref}, $$

limited to ±800 V with back-calculation anti-windup. The gains $a_k$ are the LQR solution on the bogie plant (`design/design.py`: weights 1 mm, 0.05 m/s, 20 A, and a small integral weight): $a_1 = 1.03\cdot10^6$ V/m, $a_2 = 7025$ V·s/m, $a_3 = -49$ V/A, $a_4 = 2\cdot10^6$ V/(m·s). With these gains the seven closed-loop poles (the five plant states, the derivative filter and the integrator) lie at $-1073$, $-126 \pm 176\mathrm{j}$, $-36$, $-8.6$ and $-1.8 \pm 6.1\mathrm{j}$ 1/s: stable, with the slow integral pole at $-8.6$ and the body mode left almost as it is.

Continue with [the results](page:results).
