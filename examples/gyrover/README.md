# gyrover — a single-wheel robot balanced and steered by a tilting flywheel

A physical bond-graph model of the **Gyrover**, a robot that is only a wheel: a drive unit hangs from the axle and carries a flywheel at 15 000 rpm in a gimbal that a tilt motor turns. It follows

> S.-J. Tsai, E. D. Ferreira and C. J. J. Paredis, *Control of the Gyrover: a single-wheel gyroscopically stabilized robot*, IEEE/RSJ IROS 1999.

The model is built from library blocks (three `RigidBody3D`, two `Revolute3D`, the new `RollingDisk` contact and `Rotor3D` flywheel), validated against an independent equation-based model with exact rolling, and controlled by the paper's two state feedbacks plus speed and heading loops. The docs of model `gyrover` (Docs panel) have the full write-up; every number there is a check in `expected.json`.

| model | what it is |
| --- | --- |
| `gyrover` | the showcase: start at rest, 1.2 m/s, four 90-degree turns on the 10 m floor (30 s); dashboard with speed and turn sliders |
| `gyrover-ref` | the same mission on the reference model `GyroverRef` |
| `free`, `reference` | uncontrolled rolling at 1.5 m/s from a 0.05 rad lean: bond graph and reference, energy book |
| `steady-turn`, `steady-turn-ref` | a steady turn at 1.5 m/s, checked against the exact steady-turn solution |
| `spin`, `no-spin` | standing on the rim with the flywheel spinning (stays up, precesses) and stopped (falls) |
| `fig3`, `fig3-ref` | the paper's figure 3 scenario with the paper's gains |
| `fig3-drill` | figure 3 with tyre drilling damping: the slow precession mode becomes unstable |

Everything is generated: `uv run examples/gyrover/design/build_model.py` writes `models/*.bgmodel.json`, `uv run examples/gyrover/design/build_scene.py` writes `scenes/gyrover.sdf`, `uv run examples/gyrover/design/gen_ref.py` writes `library/GyroverRef.jl` from the symbolic derivation in `design/eom.py`. `uv run examples/gyrover/design/paper_lin.py` prints our linearisation against the paper's matrices and the closed-loop poles; `uv run examples/gyrover/design/design.py` the steady-turn table.

## What comes from the paper and what is assumed

| item | source | here |
| --- | --- | --- |
| mechanism: wheel, pendulum drive unit on the axle, flywheel in a gimbal tilted about the forward axis | paper, section 2 | same |
| flywheel speed about 15 000 rpm | paper | 1570.8 rad/s, held by a speed loop |
| linearised longitudinal and lateral models $A_1, B_1, A_2, B_2$ | paper, section 4 | reproduced by our linearisation: $A_1, B_1$ to about 1 %, $A_2, B_2$ to 5-17 % except one coupling |
| tilt servo, eq. 7, $\omega_c = 20\pi$ | paper | servo model in `GyroCtrl`, realised with a stiff PD on the tilt motor |
| gains $K_1$, $K_2$ | paper | used unchanged |
| masses and inertias | **not in the paper** | chosen to reproduce the paper's matrices (wheel radius 0.197 m, total 7.0 kg; table on the docs page "Parameters") |
| contact (stiffness, damping, friction) | **assumed** | $k = 10^6$ N/m at 1 mm, $c$ = 2 s/m, $\mu$ = 0.9, $v_s$ = 1 mm/s |
| speed and heading loops | **ours** | the paper only balances |
| state estimation (Kalman filter) | paper | not modelled: the controller reads the true states |

## Results in brief

- Bond graph against the reference: heading within 2.1e-5 rad and path within 0.27 mm over the 30 s mission; steady turn within 5e-6 rad/s; figure 3 within 4e-5 rad.
- Energy: without damping and drive the book closes to 3.4 mJ; clean rolling loses 2.6 mJ in 2 s in the contact.
- Steady turn: heading rate -0.335169 rad/s against the exact -0.335157 rad/s.
- Flywheel spinning: the robot standing on its rim keeps its 0.05 rad lean (within 1.9 mrad) for 5 s; flywheel stopped: it falls, lean 0.5 rad after 0.43 s.
- Paper's figure 3: the pendulum recovery is reproduced; the tilt does not return to zero (it cannot: vertical angular momentum is conserved and the paper's gain leaves that mode at a zero pole).
- Tyre drilling damping destabilises the slow precession under the paper's lateral gain (lean 0.53 rad after 8 s).
