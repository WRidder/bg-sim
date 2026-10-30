# Motors and LQR design

## The motors

Each wheel is driven by the stdlib `drives/ElectricDrive` ([Drv1](block:Drv1), [Drv2](block:Drv2), [Drv3](block:Drv3); $R = 1\ \Omega$, $L = 0.1$ mH, $k = 0.0335$ N·m/A): the DC motor of plan 9.9 as a composite of the same primitives, with a fixed stator and one `shaft` port. The plan asks for rotor inertia 0 because $\Theta_w$ already contains it, but a rotor of exactly 0 does not work: the rotor `Inertia` has its rate imposed by the block, a derivative-causal element. $J_m = 0$ fails at $t = 0$ (`Unstable`) and $J_m \le 10^{-8}$ fails at the controller ticks (`InitialFailure`); $10^{-6}$ and $10^{-5}$ run. The model uses $J_m = 10^{-6}$ kg·m², which adds 0.5 % of $\Theta_w$ to the wheel momentum and no more. `design.py` includes it exactly, and the multibond models use the same motor.

## The design (`design/design.py`)

A numpy replica of the equations (independent of the Julia code, with the mass model built body by body) is linearised by central differences at the equilibrium. The reduced state is $z = (\text{tilt}_1, \text{tilt}_2, \omega_{1..3}, w_{r,1..3})$ with $\text{tilt}_k = e_k\cdot \text{up}_b$, $\text{up}_b = R^T (0,0,1)^T$, $e_1 = (1,-1,0)/\sqrt2$, $e_2 = (1,1,-2)/\sqrt6$. The motor is the quasi-static $T = k\,(u - k\,w_r)/R$ ($L/R = 0.1$ ms against the 2 ms sample). The vertical angular momentum is conserved (gravity has no torque about a vertical axis through the pivot), so one mode of $z$ is uncontrollable at eigenvalue 1 once discretised: the Riccati equation is solved on $(A_d/\rho, B_d/\rho)$ with $\rho = 1.0005$ and the gain is applied to the true $(A_d, B_d)$.

Weights $Q = \mathrm{diag}(\sigma^{-2})$ with $\sigma_{tilt} = 0.02$, $\sigma_\omega = 0.2$ rad/s, $\sigma_{w_r} = 40$ rad/s, $R = I/12^2$, $T_s = 2$ ms. The gain for $u = -K z$ is

$$K = \begin{pmatrix} 243.44 & -421.64 & -53.955 & 14.533 & 14.533 & -0.16979 & 0.071768 & 0.071768 \\ 243.44 & 421.64 & 14.533 & -53.955 & 14.533 & 0.071768 & -0.16979 & 0.071768 \\ -486.87 & 0 & 14.533 & 14.533 & -53.955 & 0.071768 & 0.071768 & -0.16979 \end{pmatrix}.$$

Discrete closed-loop eigenvalues 0.17065, 0.69506 (x2), 0.98086 (x2), 0.99728 (x2) and 1 (the vertical-momentum mode); continuous equivalents $-884$, $-181.9$ (x2), $-9.66$ (x2), $-1.359$ (x2) and 0 s$^{-1}$ (open loop $+7.36$ (x2), $-7.61$ (x2), $-6.43$, $-5.73$ (x2), 0). `design.py` then integrates the non-linear closed loop (Radau, with the winding inductance, the 2 ms hold and the clamp) and writes $K$ as a Julia matrix literal into the `K` parameter of the controller node of all three models.

The controller block `CubeLQR` ([Ctrl](block:Ctrl), `library/CubeLQR.jl`) forms $z$ from the pose quaternion, the body rates and the wheel rates in a `@discrete Ts = 2e-3` scope ($\text{up}_b$ is the third row of $R(q)$, no trigonometry), computes $K z$ with the `Mat{3,8}` parameter and clamps to $\pm12$ V. The first sample is at $t = T_s$; the declared 0 V is held before it. The clamp is active only at the start: wheels 1 and 3 hit 12 V in the first samples; after 0.1 s the voltage of wheel 1 stays below 0.21 V.
