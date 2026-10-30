# RRR arm on the spatial multibond stdlib

The same three-joint arm as `rrr-torque`, built from the M3 spatial stdlib following the patterns of the six-axis `arm`, driven by the same torque sources, controller and references (DEC-M5-2). The two are compared joint by joint.

![The model canvas|900](assets/8ca3c8379cf8.png)

## Construction

- a base body (1 kg at the pivot, isotropic inertia $J_b$ = 0.05 kg·m², so its yaw inertia is the plan's $J_b$; [B1](block:B1)) on a compliant `Revolute3D` about world $z$ ([J1](block:J1));
- joints 2 and 3 about world $-y$: the joint frame is $R_x(90^\circ)$ (local $z = -y$), so a positive $q$ raises the arm; `LN2` places joint 2 at the shoulder, `LN3` places joint 3 $l_2$ along the upper arm, `T2` and `T3` are $LN^{-1}\circ LC$;
- point masses as `RigidBody3D` bodies ($m_2$ at the elbow, $m_3$ at the tip, $10^{-8}$ kg·m² principal moments because a point has none), links $l_2$ and $l_3$ as `FixedTransform3DNeutral`; the body poses for gravity come from a `ComposePose3D` chain as in the six-axis arm;
- held directions $k_t = k_r = 10^7$ with 0.7-critical damping, released on their **static deflections** (`dth`, `dl` from the weight of everything distal; `design/build_models.py`);
- the settings: 5 s with `Rodas5P`, `reltol` 1e-8, `abstol` 1e-10, 2001 points.

The joint angles are [J1/qout](signal:J1/qout), [J2/qout](signal:J2/qout), [J3/qout](signal:J3/qout); the controller [Ctrl](block:Ctrl) is the `ArmCtrl3R` of `rrr` (gains 354/334/46 and 35.4/33.4/4.6).

![Joint angles and tracking errors of the multibond arm|900](assets/9039d4598cd3.png)

## Tolerance of the comparison

The difference between the models is the compliance of the held directions (and the $10^{-8}$ point-mass inertias), an $O(1/k)$ effect: the static sag $m g/k$ of the held translations (3 to 4e-6 m at $k = 10^7$) moves the masses by a fraction of a link length. The maximum difference $\max\lvert\Delta q\rvert$ over the whole 5 s motion (the `compare` entries of `expected.json`, bound $C_i/k$ with $C = 820, 500, 250$ N·m/rad, 5x the measurement at $k = 10^7$):

| $k$ (N/m, N·m/rad) | joint 1 | joint 2 | joint 3 |
| --- | --- | --- | --- |
| $10^6$ (`rrr-multibond-soft`) | 1.11e-4 | 4.4e-5 | 2.7e-5 |
| $10^7$ (`rrr-multibond`) | 1.64e-5 | 1.00e-5 | 4.98e-6 |
| $10^8$ (`rrr-multibond-stiff`) | 1.81e-6 | 1.32e-6 | 6.7e-7 |

The error falls with $k$ (ratios of 4 to 9.5 per decade; the soft case carries second-order terms, and the largest joint 2 and 3 values sit in the first millisecond, when the arm is released and the controller's first command is still to come). From 0.1 s on, joints 2 and 3 differ by 2.4e-5 / 2.7e-5, 4.0e-6 / 3.5e-6 and 5.4e-7 / 4.3e-7 rad at the three stiffnesses. The settled values agree to 1e-8 rad.

The run times in the README (loaded machine, including the first compile) are 224 s for `rrr-multibond`, 103 s for `-soft` and 114 s for `-stiff`.
