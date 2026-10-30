# Planar multibond pendulum

The M3 vertical slice and the gate for the multibond plan (plan 9.3, row X-MB1): a rigid link hanging from a **compliant-pivot planar revolute joint**, built from the `Power{Planar}` primitives of `stdlib/multibond/`. A planar multibond is drawn as **two parallel strokes**; this model shows the 2-stroke convention end to end (editor, worker, run, plot). The pendulum is torque-free and the run is conservative.

![The model canvas: two-stroke planar bonds|900](assets/de1b2886abd1.png)

## What to try

- **Run** (Ctrl+Enter) and open the Plots tab: "Joint angle and pivot deflection", "Body momentum" and "CoM height and body twist".
- Set `Joint.q0` to 0.2 rad and rerun: the period rises by about $q_0^2/16 \approx 0.25\,\%$. The period check then fails until you update `expected.json`, which is the intended signal that the physical input changed.
- Lower `Joint.kt` and recompute the start of `Joint.d` from the formula on [the physics page](page:physics): the released-from-rest value keeps the fast $\sqrt{k_t/m}$ mode out of the energy budget. Changing one without the other makes the energy check report the leftover transient (at $k_t = 10^6$ the deflection is 9.8 µm, a hundred times larger).
- Put a torque on [Drive](block:Drive) (`e` = 0.01 N·m): the pendulum gains energy linearly and the `energy` check fails: the budget tells you the drive does work.
- Plot the pivot reaction `De/y[2]`, `De/y[3]` next to `Df/y[1]`: the vertical reaction peaks at the bottom of the swing, once per half period.

## 3D view

`scenes/multibond-pendulum-2d.sdf` draws the pendulum in the vertical X-Z plane (the model's x-y plane, gravity along -z). The revolute joint `pivot` follows `Joint/qout`; the bob is the 0.5 m centre of mass, and `expected.json` checks the SDF kinematics against the composed CoM pose.

![3D view at t = 0.35 s|500](assets/8e8f3562a427.png)
