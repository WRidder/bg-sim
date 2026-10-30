# Torque-free arm: an energy budget

The same plant as the `arm` model with both drives removed ([Drive1](block:Drive1), [Drive2](block:Drive2) are `Se` with $e = 0$), no pivot damping ($b_t = 0$) and no controller. The start pose is $q_1 = 0.6$ rad, $q_2 = -0.4$ rad (the `q0` of the joints) at rest with relaxed pivot springs ($d = 0$). The arm falls under gravity and swings; the plant is conservative.

![The model canvas|900](assets/2ff166f43812.png)

![Joint angles and end effector of the falling arm|900](assets/627c7b72f1e2.png)

## Energy budget

The total mechanical energy, kinetic plus gravitational plus the two pivot strain terms, must stay constant:

$$E = \sum_i \Big[\tfrac12 P_i^T M_i^{-1} P_i + m_i g\,h_i\Big] + \sum_j \tfrac12 k_t\,\lvert d_j\rvert^2, \qquad h_i = y_{pose,i} + \sin q_1\,d_1 + \cos q_1\,d_2\ \big[+ \sin\theta_2\,e_1 + \cos\theta_2\,e_2\ \text{for link 2}\big],$$

with `PoseJ2/g[1]` $= \theta_2 = q_1 + q_2$ (the absolute angle of the joint-2 child frame) and the swing being the potential drop from the start pose to the hanging pose, $6.1238265 - (-12.7530) = 18.8768265$ J. The README measures a drift of $5.82\cdot10^{-6}$ J over 3 s, that is $3.09\cdot10^{-7}$ of the swing, with 262891 adaptive steps.

## Checks

The start pose ([Joint1/qout](signal:Joint1/qout) = 0.6, [Joint2/qout](signal:Joint2/qout) = -0.4 at $t = 0$); the `planar_fk` check to 1e-6 m; the multi-body `energy` drift (tolerance 1e-6 of the swing); an `energy_ledger` check with tolerance 2e-6 and zero source work; no W201, E101, E102, E103, E106, W206.
