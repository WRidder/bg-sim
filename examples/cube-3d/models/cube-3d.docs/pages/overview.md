# Cube balanced on a corner by three reaction wheels

A 0.15 m cube stands on one corner (a ball joint at the world origin) with its body diagonal vertical and starts 2 deg off. Three reaction wheels spin about the body axes $x$, $y$, $z$ (the three cube edges that meet at the pivot). Each wheel is mounted on the inside of a face: wheel $i$ on the face opposite the pivot corner along axis $i$, centred on the face (a wheel at the cube centre is not buildable). Three DC motors spin them; their reaction torques hold the cube up. A 2 ms discrete LQR on the tilt, the body rates and the wheel rates sets the three motor voltages, clamped to $\pm12$ V. It is the last example of M5 (plan 9.9): an equation-block plant, a controller designed from a numpy replica, a 3D scene, and a cross-check against the same cube built from the M3 multibond library (DEC-M5-3).

![The model canvas|900](assets/7a1a19a978bd.png)

```
Cube.pose  --+
Cube.omega --+-> Ctrl (CubeLQR, 2 ms, +-12 V) - u1,u2,u3 -> Drv1..3 (ElectricDrive) - shaft -> Cube.m1..m3
Cube.wheel --+                                        (stator fixed)                     (CornerCube)
```

| model | what it is | run time (README, real worker) |
| --- | --- | --- |
| `cube-3d` (this one) | the equation-block plant (`library/CornerCube.jl`), the plan 9.9 model, with the 3D scene | about 7 s |
| `cube-3d-mb` | the same cube from the M3 spatial stdlib, compliant ball joint $k_t = 10^8$ N/m | about 12 s |
| `cube-3d-mb-soft` | the same, $k_t = 10^6$ N/m (100 times softer) | about 10 s |

All three run 4 s (4001 points, `reltol` 1e-8) with the same controller block and the same gain $K$.

## Run it

Press **Run**, then plot [Cube/tilt](signal:Cube/tilt) (it falls from 2 deg to 0.66 deg at 0.1 s and below 0.5 deg from 0.12 s), the wheel rates [Cube/wheel[1]](signal:Cube/wheel[1]) and the motor voltages [Ctrl/u1](signal:Ctrl/u1). Open the **3D View** tab to watch it.

## 3D view

`scenes/cube-3d.sdf`: the pivot corner at the world origin, a 0.15 m semi-transparent cube whose visual is offset by $(a/2, a/2, a/2)$ inside the link `cube`, and three wheel discs (orange, green, red; radius 0.055 m, thickness 0.012 m, with a dark spoke), one against the inside of each face opposite the pivot corner. Bindings: `link:cube` `pose` to the quaternion `Cube/pose[1..4]` and the position (0, 0, 0) (three inline `Origin` blocks with output unit m, `PosX`, `PosY`, `PosZ`, so that the pose binding passes the E303 unit check), and `joint:wheel_x`, `wheel_y`, `wheel_z` to the integrated wheel angles `Cube/phi1..3` (9.15, -2.46 and -6.69 rad after 4 s). The multibond models have no scene (their body frame sits on the structure centre, not at the pivot).

![3D view at t = 0 s|500](assets/cb695e3e4e88.png)

Continue with [the equation block](page:block), [the motors and the design](page:design), [the results](page:results) and [the multibond comparison](page:multibond).
