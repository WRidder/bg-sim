# The electromagnet as an IC-field

## One energy, two ports

A magnetic circuit with a moving armature stores energy in its field. With flux linkage $\lambda$ and gap $h$ as the energy variables,

$$W(\lambda, h) = \frac{\lambda^2}{2 L(h)}, \qquad L(h) = L_\infty + \frac{2\alpha}{h + h_0}.$$

The port laws are the partial derivatives of $W$; this is what makes a two-port field:

$$i = \frac{\partial W}{\partial\lambda} = \frac{\lambda}{L(h)}, \qquad F = \frac{\partial W}{\partial h}\Big|_\lambda = -\frac{\lambda^2 L'(h)}{2 L^2} = -\tfrac12 i^2 L'(h) = \frac{\alpha i^2}{(h + h_0)^2}.$$

The electrical port is integral in $\lambda$ ($\dot\lambda = v$, an I-type port: voltage in, current out), the mechanical port integral in $h$ ($\dot h$ = velocity, a C-type port: velocity in, force out), hence **IC-field**. The power into the field is then

$$v\,i + F\,\dot h = \frac{\partial W}{\partial\lambda}\dot\lambda + \frac{\partial W}{\partial h}\dot h = \frac{dW}{dt},$$

exactly: the field conserves energy, and the coil resistance is a separate R.

## Why the co-energy gives the force

We know the current, not the flux linkage, so it is natural to work with the **co-energy**, the Legendre transform of $W$ in $\lambda$:

$$W'(i, h) = \lambda i - W = \tfrac12 L(h)\, i^2.$$

From $dW' = \lambda\,di - F\,dh$ the force is $F = -\partial W'/\partial h|_i = -\tfrac12 i^2 L'(h)$: the same value as from $W$ at constant flux. Moving the armature toward the magnet ($dh < 0$) at constant current raises the co-energy, so the force pulls the armature in. With $L'(h) = -2\alpha/(h + h_0)^2$ the force is $\alpha i^2/(h + h_0)^2$, which for $h_0 = 0$ is the reference's inverse-square law. This is why the stdlib block takes the reference's $\alpha$ directly, and why $L(h)$ has the form $L_\infty + 2\alpha/h$: it is the only inductance (up to the constant $L_\infty$) whose co-energy gives that force. $L_\infty$ (0.03 H here, our choice) is the inductance with the ball far away; the reference has no coil model, so it is an assumption.

## The coil equation

Differentiating $\lambda = L(h)\,i$:

$$v = L(h)\,\frac{di}{dt} + L'(h)\,\dot h\, i = L(h)\,\frac{di}{dt} - \frac{2\alpha\, i\,\dot h}{(h + h_0)^2}.$$

The second term is the back-EMF of the moving ball. [EM](block:EM) uses $i$ and $h$ as its states and writes this equation for $di/dt$. At 0.15 m, $L$ = 30.33 mH.

## The bond graph

- Electrical 1-junction [Jc](block:Jc) (common current): $v_{Amp} = R\,i + v_{field}$, with [Rc](block:Rc) = 2 Ω. [Imeas](block:Imeas) is a flow detector (zero effort) that reads $i$.
- [Jv](block:Jv) is a 0-junction in front of the coil port: [Vcoil](block:Vcoil) (an effort detector, zero flow) reads the field voltage $v$ without disturbing it.
- Mechanical 1-junction [Jb](block:Jb) (common ball velocity $\dot h$, down positive): $m\ddot h = m g - F$, with [Grav](block:Grav) = $m g$ and [Ball](block:Ball) = $m$.
- [Jf](block:Jf) is the 0-junction at the gap port: [Fmag](block:Fmag) reads $F$; [Vball](block:Vball) on Jb reads $\dot h$.
- The stator side `a` of [EM](block:EM) is wired to [Frame](block:Frame) (fixed), the coil return `n` to [Gnd](block:Gnd).

The causality is integral everywhere: Amp and Grav impose effort, the field gives the current at the coil and the force at the gap, the mass gives the velocity. No algebraic loop or derivative causality is reported.

## Energy check

[Pel](block:Pel) = $v\,i$ and [Pmech](block:Pmech) = $F\,\dot h$ are the two port powers; [Eel](block:Eel) and [Emech](block:Emech) integrate them. The field must satisfy

$$W(t) - \int_0^t v\,i\,d\tau - \int_0^t F\,\dot h\,d\tau = W(0) = \tfrac12 L(0.15)\,(13.333\ \mathrm{A})^2 = 2.69605\ \mathrm{J}.$$

The run keeps this within 6.2·10⁻⁹ J over the whole step (2.3·10⁻⁹ of $W(0)$). The golden test `test/golden/converters/test_Electromagnet.jl` checks the same balance with a free armature to 10⁻⁷ of the throughput.
