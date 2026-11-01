# The textbook Van der Pol equation

$$x'' - \mu\,(1 - x^2)\,x' + x = 0$$

The term $-\mu(1 - x^2)x'$ is a damping that is negative for $|x| < 1$ and positive beyond. Every motion except the rest point $x = 0$ ends on one closed orbit, the limit cycle. The two physical models in this project reduce to this equation: the tunnel-diode oscillator (model `vdp-tunnel-diode`) in its capacitor voltage, and the belt-driven block (model `vdp-belt`) in its velocity.

![Root diagram: four subsystems|700](assets/6dd7e1044fc2.png)

The four subsystems [Mu01](block:Mu01), [Mu1](block:Mu1), [Mu5](block:Mu5) and [Mu20](block:Mu20) run the equation at $\mu$ = 0.1, 1, 5 and 20, all from $x = 0.5$, $x' = 0$. The run time is $\tau$. Each subsystem holds:

- the **block diagram**: [Mu1/Sq](block:Mu1/Sq) forms $1 - x^2$, [Mu1/Prod](block:Mu1/Prod) multiplies by $x'$, [Mu1/Mu](block:Mu1/Mu) by $\mu$, and [Mu1/Acc](block:Mu1/Acc) subtracts $x$. The integrators [Mu1/Y](block:Mu1/Y) and [Mu1/X](block:Mu1/X) give $x'$ and $x$;
- the same equation as an **equation block**, [Mu1/Eq](block:Mu1/Eq) (`VanDerPol`);
- the cycle meter [Mu1/Meter](block:Mu1/Meter), which reads the period and the amplitude from events.

The plots of BG-Sim are against time. The phase portraits on the [results page](page:results) are drawn by the docs build from the same run.

Continue with [the theory](page:theory) and [the results](page:results).
