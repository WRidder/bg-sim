# Maglev: open loop and the frozen linear model

Two questions about the LPV model (derived on the *Plant and LPV model* page of `maglev-current-driven`): how fast does the uncontrolled ball fall or jump, and how far can a linearisation frozen at one gap be trusted?

![The model canvas|900](assets/d40dbdf0d3eb.png)

**Open loop (top row).** Three balls, at 0.05, 0.15 and 0.25 m, each get exactly the trim current of their gap ([I05](block:I05), [I15](block:I15), [I25](block:I25) = $c\,p$) and start at rest 10 nm too low. The deviation then grows as $\delta h_0\cosh(\sqrt{a_0}\,t)$, and [Grow05](block:Grow05), [Grow15](block:Grow15), [Grow25](block:Grow25) compute the growth rate $\lambda = v/(h - p)$, which tends to the unstable pole $\sqrt{2g/p}$.

**Closed loop (middle and bottom).** One fixed PID (the 0.15 m gains from the controller design of `maglev-current-driven`, in the constant blocks [Kp](block:Kp), [Ki](block:Ki), [Kd](block:Kd)) with the trim feedforward closes the loop twice per row: around the nonlinear ball ([BallS](block:BallS), [BallL](block:BallL)) and around the LPV model frozen at 0.15 m ([LinS](block:LinS), [LinL](block:LinL), the project block `LinearBall`: $A(0.15)$, $B(0.15)$, absolute current in, absolute gap out). The small row steps from 0.15 to 0.155 m, the large row to 0.21 m. [DiffS](block:DiffS) and [DiffL](block:DiffL) subtract the two gaps.

## 3D view

`scenes/maglev-open-loop.sdf` shows the three open-loop rigs side by side, the dark discs marking their trim gaps. At 1.0 s the 0.05 m ball (the fastest pole) has almost reached the pedestal, the 0.15 m ball has just started to fall (0.5 mm) and the 0.25 m ball has not visibly moved:

![The three released balls at t = 1.0 s|700](assets/f86bb7b6797a.png)

Continue with [the results](page:results).
