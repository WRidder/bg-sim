# Analytic sizing

`design/sizing.py` contains the hand calculation. `design/design.py` runs it together with the simulations, and `design/results.json` holds the numbers.

## Operating vacuum

The steady state is found by bisection on the manifold vacuum $\Delta p_m$. For each $\Delta p_m$ the cup vacuum $\Delta p_c$ follows from the balance between the line flow and the cup leaks, $Q_{line}(\Delta p_c - \Delta p_m) = Q_{leak}(\Delta p_c) + Q_{por}(\Delta p_c)$. The line law is inverted in closed form. The operating point is where the generator flow $Q_{gen}(\Delta p_m)$ equals the sum of the six line flows.

| parcel | 20 l/min | 30 l/min | 45 l/min | 60 l/min | 90 l/min |
| --- | --- | --- | --- | --- | --- |
| sealed | 54.1 | 56.0 | 57.3 | 58.0 | 58.6 |
| cardboard | 34.4 | 40.3 | 45.4 | 48.3 | 51.7 |
| porous | 14.1 | 19.1 | 24.7 | 29.0 | 35.0 |

The table gives the operating vacuum per cup in kPa. A sealed parcel is limited by the generator's end vacuum, so a larger generator adds little. A porous parcel is limited by the flow, so the vacuum scales almost with the generator size.

## Cup loads

For a steady acceleration $a$ along the path, the cups must apply the specific force $\mathbf f = \mathbf a - \mathbf g$ to the carton, expressed in the gripper frame (rotated by yaw ψ and tilt θ). The bellows are linear springs. The carton moves rigidly relative to the gripper by a translation $\mathbf u$ and a small rotation $\boldsymbol\varphi$. Cup $i$ at $\mathbf r_i$ from the centre of mass deflects by $\mathbf d_i = \mathbf u + \boldsymbol\varphi\times\mathbf r_i$, so the 6 x 6 statics are

$$\sum_i K\mathbf d_i = -m\mathbf f,\qquad \sum_i \mathbf r_i\times K\mathbf d_i + K_r\boldsymbol\varphi = 0$$

with $K = \mathrm{diag}(k_{lat}, k_{lat}, k_{ax})$. The axial load per cup follows the bolt-group formula: an equal share $m f_z/6$ plus a linear couple that balances the moment $m h f_x$ of the shear about the centre of mass. Here h = 0.15 m is the height of the cup plane above the centre of mass. The leading cups take more pull: under acceleration the inertia acts backwards at the centre of mass, below the cups, and tips the carton nose-down. The U of each cup is computed from $T_i$, $F_{lat,i}$ and $M$, as defined in [the cup model](page:plant).

At rest the U is 0.20 (sealed), 0.24 (cardboard) and 0.40 (porous). Solving max U = 1/S = 0.5 for $a$ gives the quasi-static limit:

| parcel | Δp [kPa] | yaw 0 | yaw 0, tilt | yaw 45° | yaw 45°, tilt | yaw 90° | yaw 90°, tilt |
| --- | --- | --- | --- | --- | --- | --- | --- |
| sealed | 58.0 | 4.11 | 7.18 | 3.01 | 6.13 | 3.07 | 6.19 |
| cardboard | 48.3 | 2.96 | 5.97 | 2.17 | 5.17 | 2.21 | 5.21 |
| porous | 29.0 | 0.67 | 2.97 | 0.49 | 2.67 | 0.50 | 2.68 |

Values are in m/s², at S = 2 and 60 l/min. Tilt means k_tilt = 1, with θ ≤ 20°.

## Generator size for S = 2

Turned around, a required acceleration needs a vacuum, and that vacuum needs a generator flow:

| acceleration | vacuum needed | sealed | cardboard | porous |
| --- | --- | --- | --- | --- |
| 1 m/s² | 31.8 kPa | 3.2 l/min | 16.8 l/min | 72 l/min |
| 2 m/s² | 40.2 kPa | 5.1 l/min | 29.8 l/min | 131 l/min |
| 3 m/s² | 48.6 kPa | 9.8 l/min | 62 l/min | 287 l/min |

Porous parcels need a pump-sized generator or a slower move. For a sealed parcel the ejector size hardly matters.

## Pick-up time

`sizing.pickup` integrates the lumped manifold and six-chamber model. "Lift-ready" is the time at which the cup vacuum reaches 29.3 kPa, the vacuum at which the lift acceleration of 2.5 m/s² keeps S = 2.

| parcel | 20 l/min | 30 l/min | 45 l/min | 60 l/min | 90 l/min |
| --- | --- | --- | --- | --- | --- |
| sealed | 0.285 s | 0.185 s | 0.121 s | 0.090 s | 0.060 s |
| cardboard | 0.442 s | 0.233 s | 0.139 s | 0.100 s | 0.064 s |
| porous | never | never | never | never | 0.094 s |

Below 90 l/min a porous parcel never reaches the lift-ready vacuum, because 29.0 kPa is the operating point at 60 l/min. The lift at 0.35 s therefore runs at S < 2 for porous parcels.
