# The dynamics

The analytical model of the reference script is the standard rigid-body arm equation with the motor terms reflected to the joint:

$$
\tau = \big(M(q) + \operatorname{diag}(G_i^2 J_{m,i})\big)\,\ddot q \;+\; C(q,\dot q)\,\dot q \;+\; g(q) \;+\; \operatorname{diag}(B_i G_i^2)\,\dot q
$$

where $M(q)$ is the mass matrix of the chain (links of mass $m_i$ and inertia $I_i$ about the centre of mass, at the distance $c_i = a_i + r_i$ from joint $i$), $C(q,\dot q)\dot q$ the Coriolis and centrifugal torque, $g(q)$ the gravity torque and $G_i$, $J_{m,i}$, $B_i$ the gear ratio, motor inertia and motor-side viscous friction of joint $i$.

For the 1-link arm this reduces to $\tau = (G^2 J_m + I + m c^2)\,\ddot q + B G^2 \dot q + g\,m\,c\cos q$ with $g = 0$ in the script. Gravity acts along $-y$ and $q$ is counter-clockwise from $+x$, so $g_1 = g\,m\,c\cos q_1$ for a single link (zero at $q_1 = -\pi/2$, hanging).

## In the bond graph

Nothing of the equation above is written down in the model. The planar bodies bring $M$ and the Coriolis term through the inertia $P = M V$ and the Eulerian junction structure ($e = -\mathrm{ad}(V)^{\mathsf T} P$, `CoriolisPlanar`); `GravityPlanar` brings $g(q)$ from the composed body pose; the gear, $J_m$ and $B$ bring $G^2 J_m \ddot q$ and $B G^2 \dot q$. The sum appears as the effort at the speed source:

- **inverse**: $\dot q_j$ is prescribed, so the source effort is the left-hand side $\tau_j$ above;
- **forward**: $\tau_j$ is prescribed, so the joint accelerates by $\ddot q = (M + G^2 J_m)^{-1}\,(\tau - C\dot q - g - BG^2 \dot q)$.

The comparison is therefore a check of the bond-graph mechanics against two independent implementations of $\tau(q, \dot q, \ddot q)$.

## The payload

For the 3-link arm with the payload, the payload is a 1 kg point mass 0.1 m beyond the end of link 3 (the reference models it as a dummy fourth Robotics Toolbox link with $a = 0.1$). The model lumps it into the body of link 3 (parallel axis theorem): $m = 5$ kg, centre of mass 0.102 m from joint 3, $J = 0.1853$ kg·m². A point mass has no rotational inertia of its own, so there is no singular body in the graph.
