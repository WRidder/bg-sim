# Validation

Every claim is a check in `expected.json` (`uv run examples/run_checks.py --only gripper`); the reference values come from `design/design.py`.

**(a) Static slip threshold and the regularisation error.** With the transfer, lowering and opening moved past the end, the grip setting falls at 10 N/s from 0.8 s while the ball hangs in the jaws. The Coulomb threshold is $F^* = m g/(2\mu) = 10.080$ N. The regularised friction slips earlier: the slip ODE

$$m\,\dot s = m g - 2\mu F(t)\tanh(s/v_s),\qquad \dot F = -\frac{10}{\eta\,\eta_b}\ \mathrm{N/s}$$

(the force of a back-driven drive follows the band top) reaches the detection speed 2 mm/s at **10.4242 N**, 3.4 % above $F^*$; the simulation latches [Grip/F_slip](signal:Grip/F_slip) = **10.4249 N**. While held, the ball creeps at $v_s\,\mathrm{atanh}(\text{need}/(2\mu F))$: 0.149 mm/s at 0.9 s (checked to 1 %).

![Slip-threshold run: the setting falls, the band top follows it, the ball slips|900](assets/658d8a7c7988.png)

**(b) Friction demand vs requirement.** [Grip/demand](signal:Grip/demand) follows [Grip/need](signal:Grip/need) $= m\sqrt{(g + a_v)^2 + a_h^2}$ to 6 mN over the whole move; the peak is 11.445 N in the transfer.

**(c) Under-gripped vs sized.** At a 12 N setting the drive holds 21.8 N: enough for the lift (14.2 N), not for the transfer (22.9 N). The ball starts to slip at 0.98 s as the transfer acceleration builds up, and [Grip/holds](signal:Grip/holds) drops. At 46 N it holds and moves less than 0.25 mm in the jaws.

![Under-gripped (12 N): the ball slips in the transfer|900](assets/9658b1c9e3bf.png)

**(d) Motor current and torque.** 0.872 A and 10.46 mN·m hold the ball; the delivered force (56.8 N) lies inside the friction band [46, 115] N.

**(e) Closing impact vs closing speed.** The peaks of the table on [the sizing page](page:sizing) agree with the reduced model within 1 %.

| check | reference | simulation |
| --- | --- | --- |
| transfer requirement per jaw | 22.890 N | 22.890 N |
| slip detection force | 10.4242 N | 10.4249 N |
| grip force after closing (3 mm/s) | 57.37 N | 56.83 N |
| grip current | 0.8716 A | 0.8716 A |
| under-grip force at the slip | 22.41 N | 21.81 N |
| impact peak, 10 / 20 / 30 mm/s | 93.1 / 148.5 / 207.3 N | 92.6 / 147.4 / 205.8 N |
