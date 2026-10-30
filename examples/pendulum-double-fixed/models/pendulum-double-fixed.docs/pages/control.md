# TVLQR and LQR

[Ctrl](block:Ctrl) is the project block `DoublePendCtrl` (`library/DoublePendCtrl.jl`), a `@discrete Ts = 1e-3` scope that reads the joint angles and rates and the time and holds the voltage until the next tick.

## Phases

| phase | condition | law |
| --- | --- | --- |
| 0 | $t < t_{on} = 1$ s | $u = 0$ |
| 1 | swing-up, not caught | $u = u_{ff}(\tau) - K(\tau)\,\big(x - x_{ref}(\tau)\big)$, $\tau = t - t_{on}$ |
| 2 | caught (latched) | $u = -K_{lqr}\,(x - x_{up})$ |

The output is clamped to $\pm 12$ V. The table lookup is linear interpolation: the weights are the hat functions $\max(0, 1 - \lvert s - (k-1) \rvert)$ of the row position $s = \tau/\Delta t$ over the rows $k$, and the last row is held after the trajectory.

## Time-varying LQR

Along the nominal trajectory $(x^*, u^*)$ the linearisation is discretised exactly (zero-order hold at 1 ms) at every sample, $x_{k+1} = A_k x_k + B_k u_k$, and the gains come from the backward Riccati recursion

$$K_k = (R + B_k^T S_{k+1} B_k)^{-1} B_k^T S_{k+1} A_k, \qquad S_k = Q + A_k^T S_{k+1} (A_k - B_k K_k),$$

terminated by the Riccati matrix $S_N = P$ of the balance LQR, so the gain schedule ends in the LQR gain. The weights are $Q = \mathrm{diag}(100, 100, 1, 1)$ (angles in rad, rates in rad/s) and $R = 1$ V$^{-2}$.

## Balance LQR

At upright the 1 ms zero-order-hold model gives the discrete Riccati solution $P$ and the gain

$$K_{lqr} = (-99.69,\ -93.59,\ -24.43,\ -13.59)\ \text{ in V/rad and V·s/rad,}$$

for $u = -K_{lqr}(x - x_{up})$. The same $Q$ and $R$ are used for the TVLQR.

## Switching rule

The catch is a state test, not a timer: the first tick of phase 1 at which the LQR cost-to-go $V(x) = (x - x_{up})^T P\,(x - x_{up})$ is below $V_{catch} = 3.3$ latches phase 2 (`caught` is a discrete state of the block). $V_{catch}$ is the value of $V$ on the nominal trajectory 0.2 s before its end, so the LQR takes over inside the region where it is verified to hold the pendulum; the nominal trajectory itself reaches upright at 3.5 s. The block outputs the phase ([Ctrl/phase](signal:Ctrl/phase): 0, 1, 2) and the cost-to-go ([Ctrl/V](signal:Ctrl/V)).

## Disturbance

At $t = 7$ s, 3.7 s after the catch, [Hit](block:Hit) applies a force of 0.4 N for 50 ms to the last link, perpendicular to it at the tip: the force $F$ on the body $y$ axis and the torque $F \cdot 0.18$ m about the centre of mass (the lever arm from the centre of mass to the tip). The balance LQR recovers it with no change of controller.
