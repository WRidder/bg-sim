# The benchmark bicycle

A bicycle without a rider's hands balances itself in a band of speeds. This example builds the
standard model of that effect, the **Whipple/Carvallo bicycle**, with the benchmark parameter set of

> J. P. Meijaard, J. M. Papadopoulos, A. Ruina and A. L. Schwab, *Linearized dynamics equations for the balance and steer of a bicycle: a benchmark and review*, Proc. R. Soc. A 463 (2007) 1955–1982, doi:10.1098/rspa.2007.1857.

Four rigid bodies: the **rear frame** with a rigid rider (85 kg), the **front fork** with the handlebar (4 kg), a **rear wheel** (r = 0.3 m) and a **front wheel** (r = 0.35 m), hinged at the two hubs and the steer axis. The wheels are thin discs (knife edges) that roll without slipping on a level floor. There is no friction in the joints, no rider control and no tyre model.

![The 3D view of model balance at 6 s: the bicycle leans 0.1 rad into a right turn|800](assets/befe39c0a088.png)

## Two forms of the same bicycle

| model | form | what it shows |
| --- | --- | --- |
| [whipple](model:whipple) | 3D multibond bond graph, nonlinear | hands off at 4.6 m/s after a sideways push (the paper's figure 4): it rights itself |
| [linear](model:linear) | the paper's linearised equations as a signal diagram | the same in a fraction of a second; slide the speed through the stable band |
| [balance](model:balance) | 3D bond graph + steer-torque controller | 3 m/s, too slow to be self-stable: a controller balances it and turns it |
| [balance-linear](model:balance-linear) | linear equations + the same controller | the design model of the controller |

The 3D bond graph is the physical model. The linearised equations

$$M\ddot q + v\,C_1\dot q + (g K_0 + v^2 K_2)\,q = f, \qquad q = (\phi, \delta)$$

(lean $\phi$ and steer $\delta$, both positive to the right, $f$ the lean and steer torques) are the reference it is checked against. Their matrices are computed from the parameters by the paper's appendix A in `design/benchmark.py`.

## Self-stability

The eigenvalues of the linear equations depend on the forward speed $v$ (the paper's figure 3):

![Eigenvalues of the benchmark bicycle against the forward speed: real parts (solid), imaginary part of the weave pair (dashed), the paper's table 2 values (circles)|700](assets/31da0c829c83.svg)

- **Weave** (the complex pair): the bicycle sways and steers in an oscillation. Unstable below the **weave speed 4.292 m/s**.
- **Capsize** (real, lean-dominated): the bicycle slowly falls over into a tightening turn. Unstable above the **capsize speed 6.024 m/s**, but only mildly (0.14/s at 8 m/s, easy for a rider to correct).
- **Castering** (real, fast, steer-dominated): the front wheel trails like a caster.

Between the two speeds every mode decays: the bicycle balances itself. Hands-off balance comes from the steering: when the bicycle leans, gravity and the gyroscopic torque of the front wheel turn the handlebar into the lean, and the turn brings the wheels back under the centre of mass.

## Parameters

| parameter | value | source |
| --- | --- | --- |
| wheel base, trail, steer axis tilt | 1.02 m, 0.08 m, π/10 (18°) | Meijaard et al. 2007, table 1 |
| rear wheel radius, mass, inertias $I_{xx}, I_{yy}$ | 0.3 m, 2 kg, 0.0603, 0.12 kg m² | table 1 |
| rear frame + rider: centre of mass, mass | 0.3 m ahead of the rear contact, 0.9 m up; 85 kg | table 1 |
| rear frame + rider: $I_{xx}, I_{yy}, I_{zz}, I_{xz}$ | 9.2, 11, 2.8, 2.4 kg m² | table 1 |
| fork + handlebar: centre of mass, mass | 0.9 m ahead, 0.7 m up; 4 kg | table 1 |
| fork + handlebar: $I_{xx}, I_{yy}, I_{zz}, I_{xz}$ | 0.05892, 0.06, 0.00708, −0.00756 kg m² | table 1 |
| front wheel radius, mass, inertias | 0.35 m, 3 kg, 0.1405, 0.28 kg m² | table 1 |
| gravity | 9.81 N/kg | table 1 |
| tyre contact: stiffness, damping, friction | $k = 10^6$ N/m (Hertz), $c$ = 2 s/m, $\mu$ = 0.9, $v_s$ = 1 mm/s | **estimate**: a stiff stand-in for the ideal knife edge |
| joints: held-direction stiffness and damping | $10^6$ N m/rad and N/m; 20 N m s/rad, 500 N s/m | **estimate**: a stiff stand-in for ideal hinges |

The products of inertia are in the paper's frame (x forward, y right, z down). The model's world frame has y to the left and z up; the paper's angles keep their signs.

## Validation data

The paper's table 2 lists the eigenvalues at 0 to 10 m/s with 14 digits for exactly this purpose (`design/meijaard2007_table2.json`). The checks:

- `design/design.py` reproduces the printed matrices to 1.4e-14, table 2 to 6e-13 and both critical speeds to 12 digits.
- The **3D bond graph**, run hands off at 3, 4, 5 and 6 m/s, has the weave damping and frequency of table 2 within 1 % (fitted from the time response), and at 8 m/s it capsizes at the rate of the linear model within 0.7 %. Details on the [whipple validation page](model:whipple/validation).
- The paper's **figure 4** (nonlinear response at 4.6 m/s from a 0.5 rad/s lean rate) is the start of model `whipple`. The figure has no table, so only its range is checked (speed between 4.60 and 4.70 m/s).

No measured data exist for the benchmark bicycle: it is a computed benchmark. Kooijman, Schwab and Meijaard (Multibody Syst. Dyn. 19, 2008) confirmed the linear model against measurements on a real bicycle, but with that bicycle's own parameters, so their data do not apply here. The nonlinear results of Basu-Mandal, Chatterjee and Papadopoulos (Proc. R. Soc. A 463, 2007) are accelerations at one instant, which a model with compliant contacts cannot reproduce at an instant; they are not used.
