@@ figures @project
{
  "eigen": {"kind": "svg", "svg": "eigen"},
  "scene": {"kind": "scene", "model": "balance", "t": 6.0, "zoom": 8}
}
@@ page @project benchmark - | The benchmark bicycle
# The benchmark bicycle

A bicycle without a rider's hands balances itself in a band of speeds. This example builds the
standard model of that effect, the **Whipple/Carvallo bicycle**, with the benchmark parameter set of

> J. P. Meijaard, J. M. Papadopoulos, A. Ruina and A. L. Schwab, *Linearized dynamics equations for the balance and steer of a bicycle: a benchmark and review*, Proc. R. Soc. A 463 (2007) 1955–1982, doi:10.1098/rspa.2007.1857.

Four rigid bodies: the **rear frame** with a rigid rider (85 kg), the **front fork** with the handlebar (4 kg), a **rear wheel** (r = 0.3 m) and a **front wheel** (r = 0.35 m), hinged at the two hubs and the steer axis. The wheels are thin discs (knife edges) that roll without slipping on a level floor. There is no friction in the joints, no rider control and no tyre model.

![The 3D view of model balance at 6 s: the bicycle leans 0.1 rad into a right turn|800](@fig:scene)

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

![Eigenvalues of the benchmark bicycle against the forward speed: real parts (solid), imaginary part of the weave pair (dashed), the paper's table 2 values (circles)|700](@fig:eigen)

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
@@ svg @project eigen
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 400" width="640" height="400" font-family="sans-serif" font-size="12">
<rect x="0" y="0" width="640" height="400" fill="#ffffff"/>
<rect x="298.1" y="20" width="97.7" height="336" fill="#e3f1e3"/>
<line x1="56" y1="356.0" x2="620" y2="356.0" stroke="#e4e4e4" stroke-width="1"/>
<text x="50" y="360.0" text-anchor="end">-10</text>
<line x1="56" y1="322.4" x2="620" y2="322.4" stroke="#e4e4e4" stroke-width="1"/>
<text x="50" y="326.4" text-anchor="end">-8</text>
<line x1="56" y1="288.8" x2="620" y2="288.8" stroke="#e4e4e4" stroke-width="1"/>
<text x="50" y="292.8" text-anchor="end">-6</text>
<line x1="56" y1="255.2" x2="620" y2="255.2" stroke="#e4e4e4" stroke-width="1"/>
<text x="50" y="259.2" text-anchor="end">-4</text>
<line x1="56" y1="221.6" x2="620" y2="221.6" stroke="#e4e4e4" stroke-width="1"/>
<text x="50" y="225.6" text-anchor="end">-2</text>
<line x1="56" y1="188.0" x2="620" y2="188.0" stroke="#888" stroke-width="1"/>
<text x="50" y="192.0" text-anchor="end">0</text>
<line x1="56" y1="154.4" x2="620" y2="154.4" stroke="#e4e4e4" stroke-width="1"/>
<text x="50" y="158.4" text-anchor="end">2</text>
<line x1="56" y1="120.8" x2="620" y2="120.8" stroke="#e4e4e4" stroke-width="1"/>
<text x="50" y="124.8" text-anchor="end">4</text>
<line x1="56" y1="87.2" x2="620" y2="87.2" stroke="#e4e4e4" stroke-width="1"/>
<text x="50" y="91.2" text-anchor="end">6</text>
<line x1="56" y1="53.6" x2="620" y2="53.6" stroke="#e4e4e4" stroke-width="1"/>
<text x="50" y="57.6" text-anchor="end">8</text>
<line x1="56" y1="20.0" x2="620" y2="20.0" stroke="#e4e4e4" stroke-width="1"/>
<text x="50" y="24.0" text-anchor="end">10</text>
<line x1="56.0" y1="20" x2="56.0" y2="356" stroke="#e4e4e4" stroke-width="1"/>
<text x="56.0" y="372" text-anchor="middle">0</text>
<line x1="112.4" y1="20" x2="112.4" y2="356" stroke="#e4e4e4" stroke-width="1"/>
<text x="112.4" y="372" text-anchor="middle">1</text>
<line x1="168.8" y1="20" x2="168.8" y2="356" stroke="#e4e4e4" stroke-width="1"/>
<text x="168.8" y="372" text-anchor="middle">2</text>
<line x1="225.2" y1="20" x2="225.2" y2="356" stroke="#e4e4e4" stroke-width="1"/>
<text x="225.2" y="372" text-anchor="middle">3</text>
<line x1="281.6" y1="20" x2="281.6" y2="356" stroke="#e4e4e4" stroke-width="1"/>
<text x="281.6" y="372" text-anchor="middle">4</text>
<line x1="338.0" y1="20" x2="338.0" y2="356" stroke="#e4e4e4" stroke-width="1"/>
<text x="338.0" y="372" text-anchor="middle">5</text>
<line x1="394.4" y1="20" x2="394.4" y2="356" stroke="#e4e4e4" stroke-width="1"/>
<text x="394.4" y="372" text-anchor="middle">6</text>
<line x1="450.8" y1="20" x2="450.8" y2="356" stroke="#e4e4e4" stroke-width="1"/>
<text x="450.8" y="372" text-anchor="middle">7</text>
<line x1="507.2" y1="20" x2="507.2" y2="356" stroke="#e4e4e4" stroke-width="1"/>
<text x="507.2" y="372" text-anchor="middle">8</text>
<line x1="563.6" y1="20" x2="563.6" y2="356" stroke="#e4e4e4" stroke-width="1"/>
<text x="563.6" y="372" text-anchor="middle">9</text>
<line x1="620.0" y1="20" x2="620.0" y2="356" stroke="#e4e4e4" stroke-width="1"/>
<text x="620.0" y="372" text-anchor="middle">10</text>
<text x="338" y="394" text-anchor="middle">forward speed v [m/s]</text>
<text x="14" y="188" text-anchor="middle" transform="rotate(-90 14 188)">eigenvalue [1/s]</text>
<polyline points="56.0,280.9 57.4,281.6 58.8,282.3 60.2,283.0 61.6,283.7 63.0,284.4 64.5,285.1 65.9,285.8 67.3,286.5 68.7,287.2 70.1,287.9 71.5,288.5 72.9,289.2 74.3,289.9 75.7,290.6 77.2,291.2 78.6,291.9 80.0,292.5 81.4,293.2 82.8,293.9 84.2,294.5 85.6,295.2 87.0,295.8 88.4,296.5 89.8,297.1 91.2,297.8 92.7,298.4 94.1,299.1 95.5,299.7 96.9,300.4 98.3,301.0 99.7,301.7 101.1,302.3 102.5,302.9 103.9,303.6 105.3,304.2 106.8,304.9 108.2,305.5 109.6,306.2 111.0,306.8 112.4,307.4 113.8,308.1 115.2,308.7 116.6,309.4 118.0,310.0 119.5,310.7 120.9,311.3 122.3,312.0 123.7,312.6 125.1,313.3 126.5,313.9 127.9,314.6 129.3,315.2 130.7,315.8 132.1,316.5 133.6,317.1 135.0,317.8 136.4,318.5 137.8,319.1 139.2,319.8 140.6,320.4 142.0,321.1 143.4,321.7 144.8,322.4 146.2,323.0 147.7,323.7 149.1,324.4 150.5,325.0 151.9,325.7 153.3,326.3 154.7,327.0 156.1,327.7 157.5,328.3 158.9,329.0 160.3,329.7 161.8,330.4 163.2,331.0 164.6,331.7 166.0,332.4 167.4,333.0 168.8,333.7 170.2,334.4 171.6,335.1 173.0,335.8 174.4,336.4 175.8,337.1 177.3,337.8 178.7,338.5 180.1,339.2 181.5,339.9 182.9,340.6 184.3,341.2 185.7,341.9 187.1,342.6 188.5,343.3 189.9,344.0 191.4,344.7 192.8,345.4 194.2,346.1 195.6,346.8 197.0,347.5 198.4,348.2 199.8,348.9 201.2,349.6 202.6,350.4 204.1,351.1 205.5,351.8 206.9,352.5 208.3,353.2 209.7,353.9 211.1,354.6 212.5,355.4 213.9,356.0 215.3,356.0 216.7,356.0 218.1,356.0 219.6,356.0 221.0,356.0 222.4,356.0 223.8,356.0 225.2,356.0 226.6,356.0 228.0,356.0 229.4,356.0 230.8,356.0 232.2,356.0 233.7,356.0 235.1,356.0 236.5,356.0 237.9,356.0 239.3,356.0 240.7,356.0 242.1,356.0 243.5,356.0 244.9,356.0" fill="none" stroke="#1f5fa8" stroke-width="2"/>
<polyline points="56.0,240.6 57.4,240.6 58.8,240.5 60.2,240.5 61.6,240.5 63.0,240.4 64.5,240.4 65.9,240.4 67.3,240.4 68.7,240.4 70.1,240.4 71.5,240.3 72.9,240.3 74.3,240.3 75.7,240.3 77.2,240.3 78.6,240.3 80.0,240.4 81.4,240.4 82.8,240.4 84.2,240.4 85.6,240.4 87.0,240.4 88.4,240.4 89.8,240.4 91.2,240.4 92.7,240.5 94.1,240.5 95.5,240.5 96.9,240.5 98.3,240.5 99.7,240.5 101.1,240.5 102.5,240.6 103.9,240.6 105.3,240.6 106.8,240.6 108.2,240.6 109.6,240.6 111.0,240.6 112.4,240.7 113.8,240.7 115.2,240.7 116.6,240.7 118.0,240.7 119.5,240.7 120.9,240.7 122.3,240.7 123.7,240.7 125.1,240.7 126.5,240.7 127.9,240.7 129.3,240.7 130.7,240.7 132.1,240.7 133.6,240.7 135.0,240.7 136.4,240.7 137.8,240.6 139.2,240.6 140.6,240.6 142.0,240.6 143.4,240.6 144.8,240.5 146.2,240.5 147.7,240.5 149.1,240.4 150.5,240.4 151.9,240.3 153.3,240.3 154.7,240.3 156.1,240.2 157.5,240.2 158.9,240.1 160.3,240.0 161.8,240.0 163.2,239.9 164.6,239.8 166.0,239.8 167.4,239.7 168.8,239.6 170.2,239.5 171.6,239.4 173.0,239.3 174.4,239.2 175.8,239.1 177.3,239.0 178.7,238.9 180.1,238.8 181.5,238.7 182.9,238.6 184.3,238.4 185.7,238.3 187.1,238.2 188.5,238.0 189.9,237.9 191.4,237.7 192.8,237.6 194.2,237.4 195.6,237.2 197.0,237.1 198.4,236.9 199.8,236.7 201.2,236.5 202.6,236.3 204.1,236.1 205.5,235.9 206.9,235.7 208.3,235.5 209.7,235.2 211.1,235.0 212.5,234.8 213.9,234.5 215.3,234.2 216.7,234.0 218.1,233.7 219.6,233.4 221.0,233.2 222.4,232.9 223.8,232.6 225.2,232.2 226.6,231.9 228.0,231.6 229.4,231.3 230.8,230.9 232.2,230.6 233.7,230.2 235.1,229.8 236.5,229.5 237.9,229.1 239.3,228.7 240.7,228.3 242.1,227.8 243.5,227.4 244.9,227.0 246.4,226.5 247.8,226.1 249.2,225.6 250.6,225.1 252.0,224.6 253.4,224.1 254.8,223.6 256.2,223.1 257.6,222.5 259.0,222.0 260.4,221.4 261.9,220.9 263.3,220.3 264.7,219.7 266.1,219.1 267.5,218.5 268.9,217.9 270.3,217.2 271.7,216.6 273.1,216.0 274.6,215.3 276.0,214.7 277.4,214.0 278.8,213.3 280.2,212.7 281.6,212.0 283.0,211.3 284.4,210.7 285.8,210.0 287.2,209.4 288.6,208.7 290.1,208.1 291.5,207.4 292.9,206.8 294.3,206.2 295.7,205.6 297.1,205.0 298.5,204.4 299.9,203.8 301.3,203.2 302.8,202.7 304.2,202.2 305.6,201.6 307.0,201.1 308.4,200.7 309.8,200.2 311.2,199.7 312.6,199.3 314.0,198.9 315.4,198.4 316.9,198.0 318.3,197.6 319.7,197.3 321.1,196.9 322.5,196.6 323.9,197.0 325.3,197.5 326.7,197.9 328.1,198.3 329.5,198.7 330.9,199.1 332.4,199.5 333.8,199.9 335.2,200.3 336.6,200.6 338.0,201.0 339.4,201.4 340.8,201.8 342.2,202.1 343.6,202.5 345.0,202.8 346.5,203.2 347.9,203.5 349.3,203.9 350.7,204.2 352.1,204.6 353.5,204.9 354.9,205.2 356.3,205.6 357.7,205.9 359.1,206.2 360.6,206.5 362.0,206.9 363.4,207.2 364.8,207.5 366.2,207.8 367.6,208.1 369.0,208.4 370.4,208.7 371.8,209.0 373.2,209.3 374.7,209.6 376.1,209.9 377.5,210.2 378.9,210.5 380.3,210.8 381.7,211.1 383.1,211.4 384.5,211.7 385.9,212.0 387.4,212.2 388.8,212.5 390.2,212.8 391.6,213.1 393.0,213.4 394.4,213.6 395.8,213.9 397.2,214.2 398.6,214.5 400.0,214.7 401.5,215.0 402.9,215.3 404.3,215.6 405.7,215.8 407.1,216.1 408.5,216.4 409.9,216.6 411.3,216.9 412.7,217.1 414.1,217.4 415.5,217.7 417.0,217.9 418.4,218.2 419.8,218.4 421.2,218.7 422.6,219.0 424.0,219.2 425.4,219.5 426.8,219.7 428.2,220.0 429.6,220.2 431.1,220.5 432.5,220.7 433.9,221.0 435.3,221.2 436.7,221.5 438.1,221.7 439.5,222.0 440.9,222.2 442.3,222.5 443.8,222.7 445.2,223.0 446.6,223.2 448.0,223.4 449.4,223.7 450.8,223.9 452.2,224.2 453.6,224.4 455.0,224.7 456.4,224.9 457.9,225.1 459.3,225.4 460.7,225.6 462.1,225.9 463.5,226.1 464.9,226.3 466.3,226.6 467.7,226.8 469.1,227.0 470.5,227.3 472.0,227.5 473.4,227.7 474.8,228.0 476.2,228.2 477.6,228.4 479.0,228.7 480.4,228.9 481.8,229.1 483.2,229.4 484.6,229.6 486.0,229.8 487.5,230.1 488.9,230.3 490.3,230.5 491.7,230.8 493.1,231.0 494.5,231.2 495.9,231.4 497.3,231.7 498.7,231.9 500.1,232.1 501.6,232.3 503.0,232.6 504.4,232.8 505.8,233.0 507.2,233.3 508.6,233.5 510.0,233.7 511.4,233.9 512.8,234.1 514.2,234.4 515.7,234.6 517.1,234.8 518.5,235.0 519.9,235.3 521.3,235.5 522.7,235.7 524.1,235.9 525.5,236.2 526.9,236.4 528.4,236.6 529.8,236.8 531.2,237.0 532.6,237.3 534.0,237.5 535.4,237.7 536.8,237.9 538.2,238.1 539.6,238.4 541.0,238.6 542.5,238.8 543.9,239.0 545.3,239.2 546.7,239.4 548.1,239.7 549.5,239.9 550.9,240.1 552.3,240.3 553.7,240.5 555.1,240.7 556.5,241.0 558.0,241.2 559.4,241.4 560.8,241.6 562.2,241.8 563.6,242.0 565.0,242.3 566.4,242.5 567.8,242.7 569.2,242.9 570.6,243.1 572.1,243.3 573.5,243.5 574.9,243.8 576.3,244.0 577.7,244.2 579.1,244.4 580.5,244.6 581.9,244.8 583.3,245.0 584.8,245.2 586.2,245.5 587.6,245.7 589.0,245.9 590.4,246.1 591.8,246.3 593.2,246.5 594.6,246.7 596.0,246.9 597.4,247.1 598.9,247.4 600.3,247.6 601.7,247.8 603.1,248.0 604.5,248.2 605.9,248.4 607.3,248.6 608.7,248.8 610.1,249.0 611.5,249.2 613.0,249.5 614.4,249.7 615.8,249.9 617.2,250.1 618.6,250.3 620.0,250.5" fill="none" stroke="#1f5fa8" stroke-width="2"/>
<polyline points="56.0,135.4 57.4,135.3 58.8,135.3 60.2,135.2 61.6,135.1 63.0,135.1 64.5,135.0 65.9,134.9 67.3,134.8 68.7,134.7 70.1,134.6 71.5,134.4 72.9,134.3 74.3,134.1 75.7,133.9 77.2,133.7 78.6,133.5 80.0,133.2 81.4,133.0 82.8,132.7 84.2,132.3 85.6,131.9 87.0,131.5 88.4,130.9 89.8,130.3 91.2,129.5 92.7,128.4 94.1,126.6 95.5,124.7 96.9,125.0 98.3,125.3 99.7,125.7 101.1,126.0 102.5,126.4 103.9,126.7 105.3,127.0 106.8,127.4 108.2,127.7 109.6,128.1 111.0,128.4 112.4,128.7 113.8,129.1 115.2,129.4 116.6,129.8 118.0,130.1 119.5,130.5 120.9,130.8 122.3,131.2 123.7,131.5 125.1,131.8 126.5,132.2 127.9,132.5 129.3,132.9 130.7,133.2 132.1,133.6 133.6,133.9 135.0,134.3 136.4,134.6 137.8,135.0 139.2,135.3 140.6,135.7 142.0,136.0 143.4,136.4 144.8,136.8 146.2,137.1 147.7,137.5 149.1,137.8 150.5,138.2 151.9,138.5 153.3,138.9 154.7,139.3 156.1,139.6 157.5,140.0 158.9,140.4 160.3,140.7 161.8,141.1 163.2,141.5 164.6,141.8 166.0,142.2 167.4,142.6 168.8,142.9 170.2,143.3 171.6,143.7 173.0,144.1 174.4,144.4 175.8,144.8 177.3,145.2 178.7,145.6 180.1,146.0 181.5,146.3 182.9,146.7 184.3,147.1 185.7,147.5 187.1,147.9 188.5,148.3 189.9,148.7 191.4,149.1 192.8,149.5 194.2,149.9 195.6,150.3 197.0,150.7 198.4,151.1 199.8,151.5 201.2,151.9 202.6,152.3 204.1,152.8 205.5,153.2 206.9,153.6 208.3,154.0 209.7,154.4 211.1,154.9 212.5,155.3 213.9,155.7 215.3,156.2 216.7,156.6 218.1,157.1 219.6,157.5 221.0,158.0 222.4,158.4 223.8,158.9 225.2,159.3 226.6,159.8 228.0,160.3 229.4,160.7 230.8,161.2 232.2,161.7 233.7,162.2 235.1,162.6 236.5,163.1 237.9,163.6 239.3,164.1 240.7,164.6 242.1,165.1 243.5,165.6 244.9,166.1 246.4,166.7 247.8,167.2 249.2,167.7 250.6,168.3 252.0,168.8 253.4,169.3 254.8,169.9 256.2,170.4 257.6,171.0 259.0,171.5 260.4,172.1 261.9,172.7 263.3,173.3 264.7,173.8 266.1,174.4 267.5,175.0 268.9,175.6 270.3,176.2 271.7,176.8 273.1,177.4 274.6,178.0 276.0,178.6 277.4,179.2 278.8,179.8 280.2,180.4 281.6,181.1 283.0,181.7 284.4,182.3 285.8,182.9 287.2,183.5 288.6,184.1 290.1,184.7 291.5,185.3 292.9,185.9 294.3,186.5 295.7,187.0 297.1,187.6 298.5,188.2 299.9,188.7 301.3,189.3 302.8,189.8 304.2,190.4 305.6,190.9 307.0,191.4 308.4,191.9 309.8,192.4 311.2,192.9 312.6,193.4 314.0,193.9 315.4,194.3 316.9,194.8 318.3,195.3 319.7,195.7 321.1,196.2 322.5,196.6 323.9,197.0 325.3,197.5 326.7,197.9 328.1,198.3 329.5,198.7 330.9,199.1 332.4,199.5 333.8,199.9 335.2,200.3 336.6,200.6 338.0,201.0 339.4,201.4 340.8,201.8 342.2,202.1 343.6,202.5 345.0,202.8 346.5,203.2 347.9,203.5 349.3,203.9 350.7,204.2 352.1,204.6 353.5,204.9 354.9,205.2 356.3,205.6 357.7,205.9 359.1,206.2 360.6,206.5 362.0,206.9 363.4,207.2 364.8,207.5 366.2,207.8 367.6,208.1 369.0,208.4 370.4,208.7 371.8,209.0 373.2,209.3 374.7,209.6 376.1,209.9 377.5,210.2 378.9,210.5 380.3,210.8 381.7,211.1 383.1,211.4 384.5,211.7 385.9,212.0 387.4,212.2 388.8,212.5 390.2,212.8 391.6,213.1 393.0,213.4 394.4,213.6 395.8,213.9 397.2,214.2 398.6,214.5 400.0,214.7 401.5,215.0 402.9,215.3 404.3,215.6 405.7,215.8 407.1,216.1 408.5,216.4 409.9,216.6 411.3,216.9 412.7,217.1 414.1,217.4 415.5,217.7 417.0,217.9 418.4,218.2 419.8,218.4 421.2,218.7 422.6,219.0 424.0,219.2 425.4,219.5 426.8,219.7 428.2,220.0 429.6,220.2 431.1,220.5 432.5,220.7 433.9,221.0 435.3,221.2 436.7,221.5 438.1,221.7 439.5,222.0 440.9,222.2 442.3,222.5 443.8,222.7 445.2,223.0 446.6,223.2 448.0,223.4 449.4,223.7 450.8,223.9 452.2,224.2 453.6,224.4 455.0,224.7 456.4,224.9 457.9,225.1 459.3,225.4 460.7,225.6 462.1,225.9 463.5,226.1 464.9,226.3 466.3,226.6 467.7,226.8 469.1,227.0 470.5,227.3 472.0,227.5 473.4,227.7 474.8,228.0 476.2,228.2 477.6,228.4 479.0,228.7 480.4,228.9 481.8,229.1 483.2,229.4 484.6,229.6 486.0,229.8 487.5,230.1 488.9,230.3 490.3,230.5 491.7,230.8 493.1,231.0 494.5,231.2 495.9,231.4 497.3,231.7 498.7,231.9 500.1,232.1 501.6,232.3 503.0,232.6 504.4,232.8 505.8,233.0 507.2,233.3 508.6,233.5 510.0,233.7 511.4,233.9 512.8,234.1 514.2,234.4 515.7,234.6 517.1,234.8 518.5,235.0 519.9,235.3 521.3,235.5 522.7,235.7 524.1,235.9 525.5,236.2 526.9,236.4 528.4,236.6 529.8,236.8 531.2,237.0 532.6,237.3 534.0,237.5 535.4,237.7 536.8,237.9 538.2,238.1 539.6,238.4 541.0,238.6 542.5,238.8 543.9,239.0 545.3,239.2 546.7,239.4 548.1,239.7 549.5,239.9 550.9,240.1 552.3,240.3 553.7,240.5 555.1,240.7 556.5,241.0 558.0,241.2 559.4,241.4 560.8,241.6 562.2,241.8 563.6,242.0 565.0,242.3 566.4,242.5 567.8,242.7 569.2,242.9 570.6,243.1 572.1,243.3 573.5,243.5 574.9,243.8 576.3,244.0 577.7,244.2 579.1,244.4 580.5,244.6 581.9,244.8 583.3,245.0 584.8,245.2 586.2,245.5 587.6,245.7 589.0,245.9 590.4,246.1 591.8,246.3 593.2,246.5 594.6,246.7 596.0,246.9 597.4,247.1 598.9,247.4 600.3,247.6 601.7,247.8 603.1,248.0 604.5,248.2 605.9,248.4 607.3,248.6 608.7,248.8 610.1,249.0 611.5,249.2 613.0,249.5 614.4,249.7 615.8,249.9 617.2,250.1 618.6,250.3 620.0,250.5" fill="none" stroke="#1f5fa8" stroke-width="2"/>
<polyline points="56.0,95.1 57.4,95.8 58.8,96.5 60.2,97.3 61.6,98.0 63.0,98.7 64.5,99.5 65.9,100.3 67.3,101.0 68.7,101.8 70.1,102.6 71.5,103.4 72.9,104.3 74.3,105.1 75.7,106.0 77.2,106.8 78.6,107.7 80.0,108.6 81.4,109.6 82.8,110.6 84.2,111.6 85.6,112.7 87.0,113.8 88.4,115.0 89.8,116.3 91.2,117.8 92.7,119.5 94.1,122.0 95.5,124.7 96.9,125.0 98.3,125.3 99.7,125.7 101.1,126.0 102.5,126.4 103.9,126.7 105.3,127.0 106.8,127.4 108.2,127.7 109.6,128.1 111.0,128.4 112.4,128.7 113.8,129.1 115.2,129.4 116.6,129.8 118.0,130.1 119.5,130.5 120.9,130.8 122.3,131.2 123.7,131.5 125.1,131.8 126.5,132.2 127.9,132.5 129.3,132.9 130.7,133.2 132.1,133.6 133.6,133.9 135.0,134.3 136.4,134.6 137.8,135.0 139.2,135.3 140.6,135.7 142.0,136.0 143.4,136.4 144.8,136.8 146.2,137.1 147.7,137.5 149.1,137.8 150.5,138.2 151.9,138.5 153.3,138.9 154.7,139.3 156.1,139.6 157.5,140.0 158.9,140.4 160.3,140.7 161.8,141.1 163.2,141.5 164.6,141.8 166.0,142.2 167.4,142.6 168.8,142.9 170.2,143.3 171.6,143.7 173.0,144.1 174.4,144.4 175.8,144.8 177.3,145.2 178.7,145.6 180.1,146.0 181.5,146.3 182.9,146.7 184.3,147.1 185.7,147.5 187.1,147.9 188.5,148.3 189.9,148.7 191.4,149.1 192.8,149.5 194.2,149.9 195.6,150.3 197.0,150.7 198.4,151.1 199.8,151.5 201.2,151.9 202.6,152.3 204.1,152.8 205.5,153.2 206.9,153.6 208.3,154.0 209.7,154.4 211.1,154.9 212.5,155.3 213.9,155.7 215.3,156.2 216.7,156.6 218.1,157.1 219.6,157.5 221.0,158.0 222.4,158.4 223.8,158.9 225.2,159.3 226.6,159.8 228.0,160.3 229.4,160.7 230.8,161.2 232.2,161.7 233.7,162.2 235.1,162.6 236.5,163.1 237.9,163.6 239.3,164.1 240.7,164.6 242.1,165.1 243.5,165.6 244.9,166.1 246.4,166.7 247.8,167.2 249.2,167.7 250.6,168.3 252.0,168.8 253.4,169.3 254.8,169.9 256.2,170.4 257.6,171.0 259.0,171.5 260.4,172.1 261.9,172.7 263.3,173.3 264.7,173.8 266.1,174.4 267.5,175.0 268.9,175.6 270.3,176.2 271.7,176.8 273.1,177.4 274.6,178.0 276.0,178.6 277.4,179.2 278.8,179.8 280.2,180.4 281.6,181.1 283.0,181.7 284.4,182.3 285.8,182.9 287.2,183.5 288.6,184.1 290.1,184.7 291.5,185.3 292.9,185.9 294.3,186.5 295.7,187.0 297.1,187.6 298.5,188.2 299.9,188.7 301.3,189.3 302.8,189.8 304.2,190.4 305.6,190.9 307.0,191.4 308.4,191.9 309.8,192.4 311.2,192.9 312.6,193.4 314.0,193.9 315.4,194.3 316.9,194.8 318.3,195.3 319.7,195.7 321.1,196.2 322.5,196.6 323.9,196.2 325.3,195.9 326.7,195.6 328.1,195.3 329.5,195.0 330.9,194.7 332.4,194.4 333.8,194.2 335.2,193.9 336.6,193.7 338.0,193.4 339.4,193.2 340.8,193.0 342.2,192.8 343.6,192.5 345.0,192.3 346.5,192.1 347.9,192.0 349.3,191.8 350.7,191.6 352.1,191.4 353.5,191.3 354.9,191.1 356.3,190.9 357.7,190.8 359.1,190.6 360.6,190.5 362.0,190.4 363.4,190.2 364.8,190.1 366.2,190.0 367.6,189.8 369.0,189.7 370.4,189.6 371.8,189.5 373.2,189.4 374.7,189.3 376.1,189.2 377.5,189.1 378.9,189.0 380.3,188.9 381.7,188.8 383.1,188.7 384.5,188.6 385.9,188.5 387.4,188.4 388.8,188.4 390.2,188.3 391.6,188.2 393.0,188.1 394.4,188.1 395.8,188.0 397.2,187.9 398.6,187.9 400.0,187.8 401.5,187.7 402.9,187.7 404.3,187.6 405.7,187.6 407.1,187.5 408.5,187.4 409.9,187.4 411.3,187.3 412.7,187.3 414.1,187.2 415.5,187.2 417.0,187.1 418.4,187.1 419.8,187.0 421.2,187.0 422.6,187.0 424.0,186.9 425.4,186.9 426.8,186.8 428.2,186.8 429.6,186.8 431.1,186.7 432.5,186.7 433.9,186.6 435.3,186.6 436.7,186.6 438.1,186.5 439.5,186.5 440.9,186.5 442.3,186.4 443.8,186.4 445.2,186.4 446.6,186.4 448.0,186.3 449.4,186.3 450.8,186.3 452.2,186.2 453.6,186.2 455.0,186.2 456.4,186.2 457.9,186.2 459.3,186.1 460.7,186.1 462.1,186.1 463.5,186.1 464.9,186.0 466.3,186.0 467.7,186.0 469.1,186.0 470.5,186.0 472.0,185.9 473.4,185.9 474.8,185.9 476.2,185.9 477.6,185.9 479.0,185.9 480.4,185.8 481.8,185.8 483.2,185.8 484.6,185.8 486.0,185.8 487.5,185.8 488.9,185.7 490.3,185.7 491.7,185.7 493.1,185.7 494.5,185.7 495.9,185.7 497.3,185.7 498.7,185.7 500.1,185.6 501.6,185.6 503.0,185.6 504.4,185.6 505.8,185.6 507.2,185.6 508.6,185.6 510.0,185.6 511.4,185.6 512.8,185.6 514.2,185.5 515.7,185.5 517.1,185.5 518.5,185.5 519.9,185.5 521.3,185.5 522.7,185.5 524.1,185.5 525.5,185.5 526.9,185.5 528.4,185.5 529.8,185.5 531.2,185.5 532.6,185.4 534.0,185.4 535.4,185.4 536.8,185.4 538.2,185.4 539.6,185.4 541.0,185.4 542.5,185.4 543.9,185.4 545.3,185.4 546.7,185.4 548.1,185.4 549.5,185.4 550.9,185.4 552.3,185.4 553.7,185.4 555.1,185.4 556.5,185.4 558.0,185.4 559.4,185.4 560.8,185.4 562.2,185.4 563.6,185.3 565.0,185.3 566.4,185.3 567.8,185.3 569.2,185.3 570.6,185.3 572.1,185.3 573.5,185.3 574.9,185.3 576.3,185.3 577.7,185.3 579.1,185.3 580.5,185.3 581.9,185.3 583.3,185.3 584.8,185.3 586.2,185.3 587.6,185.3 589.0,185.3 590.4,185.3 591.8,185.3 593.2,185.3 594.6,185.3 596.0,185.3 597.4,185.3 598.9,185.3 600.3,185.3 601.7,185.3 603.1,185.3 604.5,185.3 605.9,185.3 607.3,185.3 608.7,185.3 610.1,185.3 611.5,185.3 613.0,185.3 614.4,185.3 615.8,185.3 617.2,185.3 618.6,185.3 620.0,185.3" fill="none" stroke="#1f5fa8" stroke-width="2"/>
<polyline points="95.5,185.0 96.9,183.1 98.3,181.8 99.7,180.7 101.1,179.8 102.5,178.9 103.9,178.2 105.3,177.5 106.8,176.8 108.2,176.2 109.6,175.6 111.0,175.0 112.4,174.4 113.8,173.9 115.2,173.4 116.6,172.9 118.0,172.4 119.5,171.9 120.9,171.5 122.3,171.1 123.7,170.6 125.1,170.2 126.5,169.8 127.9,169.4 129.3,169.0 130.7,168.6 132.1,168.2 133.6,167.8 135.0,167.5 136.4,167.1 137.8,166.7 139.2,166.4 140.6,166.0 142.0,165.7 143.4,165.3 144.8,165.0 146.2,164.7 147.7,164.3 149.1,164.0 150.5,163.7 151.9,163.4 153.3,163.1 154.7,162.8 156.1,162.4 157.5,162.1 158.9,161.8 160.3,161.5 161.8,161.2 163.2,160.9 164.6,160.6 166.0,160.3 167.4,160.1 168.8,159.8 170.2,159.5 171.6,159.2 173.0,158.9 174.4,158.6 175.8,158.3 177.3,158.1 178.7,157.8 180.1,157.5 181.5,157.2 182.9,157.0 184.3,156.7 185.7,156.4 187.1,156.2 188.5,155.9 189.9,155.6 191.4,155.4 192.8,155.1 194.2,154.8 195.6,154.6 197.0,154.3 198.4,154.0 199.8,153.8 201.2,153.5 202.6,153.2 204.1,153.0 205.5,152.7 206.9,152.5 208.3,152.2 209.7,151.9 211.1,151.7 212.5,151.4 213.9,151.2 215.3,150.9 216.7,150.7 218.1,150.4 219.6,150.1 221.0,149.9 222.4,149.6 223.8,149.4 225.2,149.1 226.6,148.8 228.0,148.6 229.4,148.3 230.8,148.0 232.2,147.8 233.7,147.5 235.1,147.2 236.5,147.0 237.9,146.7 239.3,146.4 240.7,146.2 242.1,145.9 243.5,145.6 244.9,145.3 246.4,145.0 247.8,144.8 249.2,144.5 250.6,144.2 252.0,143.9 253.4,143.6 254.8,143.3 256.2,143.0 257.6,142.7 259.0,142.3 260.4,142.0 261.9,141.7 263.3,141.3 264.7,141.0 266.1,140.7 267.5,140.3 268.9,139.9 270.3,139.6 271.7,139.2 273.1,138.8 274.6,138.4 276.0,138.0 277.4,137.6 278.8,137.2 280.2,136.7 281.6,136.3 283.0,135.8 284.4,135.3 285.8,134.9 287.2,134.4 288.6,133.9 290.1,133.4 291.5,132.9 292.9,132.3 294.3,131.8 295.7,131.2 297.1,130.7 298.5,130.1 299.9,129.5 301.3,129.0 302.8,128.4 304.2,127.8 305.6,127.2 307.0,126.6 308.4,126.0 309.8,125.4 311.2,124.8 312.6,124.2 314.0,123.6 315.4,122.9 316.9,122.3 318.3,121.7 319.7,121.1 321.1,120.5 322.5,119.8 323.9,119.2 325.3,118.6 326.7,118.0 328.1,117.3 329.5,116.7 330.9,116.1 332.4,115.5 333.8,114.8 335.2,114.2 336.6,113.6 338.0,113.0 339.4,112.4 340.8,111.8 342.2,111.1 343.6,110.5 345.0,109.9 346.5,109.3 347.9,108.7 349.3,108.1 350.7,107.5 352.1,106.9 353.5,106.3 354.9,105.7 356.3,105.1 357.7,104.5 359.1,103.9 360.6,103.3 362.0,102.7 363.4,102.1 364.8,101.5 366.2,100.9 367.6,100.3 369.0,99.7 370.4,99.1 371.8,98.5 373.2,97.9 374.7,97.4 376.1,96.8 377.5,96.2 378.9,95.6 380.3,95.0 381.7,94.4 383.1,93.9 384.5,93.3 385.9,92.7 387.4,92.1 388.8,91.6 390.2,91.0 391.6,90.4 393.0,89.8 394.4,89.3 395.8,88.7 397.2,88.1 398.6,87.6 400.0,87.0 401.5,86.4 402.9,85.9 404.3,85.3 405.7,84.7 407.1,84.2 408.5,83.6 409.9,83.1 411.3,82.5 412.7,81.9 414.1,81.4 415.5,80.8 417.0,80.3 418.4,79.7 419.8,79.2 421.2,78.6 422.6,78.0 424.0,77.5 425.4,76.9 426.8,76.4 428.2,75.8 429.6,75.3 431.1,74.7 432.5,74.2 433.9,73.6 435.3,73.1 436.7,72.6 438.1,72.0 439.5,71.5 440.9,70.9 442.3,70.4 443.8,69.8 445.2,69.3 446.6,68.7 448.0,68.2 449.4,67.7 450.8,67.1 452.2,66.6 453.6,66.0 455.0,65.5 456.4,65.0 457.9,64.4 459.3,63.9 460.7,63.3 462.1,62.8 463.5,62.3 464.9,61.7 466.3,61.2 467.7,60.7 469.1,60.1 470.5,59.6 472.0,59.1 473.4,58.5 474.8,58.0 476.2,57.5 477.6,56.9 479.0,56.4 480.4,55.9 481.8,55.3 483.2,54.8 484.6,54.3 486.0,53.8 487.5,53.2 488.9,52.7 490.3,52.2 491.7,51.6 493.1,51.1 494.5,50.6 495.9,50.1 497.3,49.5 498.7,49.0 500.1,48.5 501.6,48.0 503.0,47.4 504.4,46.9 505.8,46.4 507.2,45.9 508.6,45.3 510.0,44.8 511.4,44.3 512.8,43.8 514.2,43.3 515.7,42.7 517.1,42.2 518.5,41.7 519.9,41.2 521.3,40.6 522.7,40.1 524.1,39.6 525.5,39.1 526.9,38.6 528.4,38.0 529.8,37.5 531.2,37.0 532.6,36.5 534.0,36.0 535.4,35.5 536.8,34.9 538.2,34.4 539.6,33.9 541.0,33.4 542.5,32.9 543.9,32.4 545.3,31.8 546.7,31.3 548.1,30.8 549.5,30.3 550.9,29.8 552.3,29.3 553.7,28.7 555.1,28.2 556.5,27.7 558.0,27.2 559.4,26.7 560.8,26.2 562.2,25.7 563.6,25.1 565.0,24.6 566.4,24.1 567.8,23.6 569.2,23.1 570.6,22.6 572.1,22.1 573.5,21.6 574.9,21.0 576.3,20.5 577.7,20.0 579.1,20.0 580.5,20.0 581.9,20.0 583.3,20.0 584.8,20.0 586.2,20.0 587.6,20.0 589.0,20.0 590.4,20.0 591.8,20.0 593.2,20.0 594.6,20.0 596.0,20.0 597.4,20.0 598.9,20.0 600.3,20.0 601.7,20.0 603.1,20.0 604.5,20.0 605.9,20.0 607.3,20.0 608.7,20.0 610.1,20.0 611.5,20.0 613.0,20.0 614.4,20.0 615.8,20.0 617.2,20.0 618.6,20.0 620.0,20.0" fill="none" stroke="#c0392b" stroke-width="2" stroke-dasharray="6 4"/>
<line x1="298.1" y1="20" x2="298.1" y2="356" stroke="#2e7d32" stroke-width="1.5" stroke-dasharray="3 3"/>
<line x1="395.8" y1="20" x2="395.8" y2="356" stroke="#2e7d32" stroke-width="1.5" stroke-dasharray="3 3"/>
<text x="346.9" y="36" text-anchor="middle" fill="#2e7d32">self-stable</text>
<text x="294.1" y="350" text-anchor="end" fill="#2e7d32">v_w 4.29</text>
<text x="399.8" y="350" fill="#2e7d32">v_c 6.02</text>
<text x="524.1" y="33.4" fill="#c0392b">Im weave</text>
<text x="473.4" y="248.5" fill="#1f5fa8">Re weave</text>
<text x="484.6" y="171.2" fill="#1f5fa8">capsize</text>
<text x="106.8" y="332.5" fill="#1f5fa8">castering</text>
<circle cx="112.4" cy="128.7" r="3.5" fill="none" stroke="#000" stroke-width="1.2"/>
<circle cx="112.4" cy="174.4" r="3.5" fill="none" stroke="#000" stroke-width="1.2"/>
<circle cx="168.8" cy="142.9" r="3.5" fill="none" stroke="#000" stroke-width="1.2"/>
<circle cx="168.8" cy="159.8" r="3.5" fill="none" stroke="#000" stroke-width="1.2"/>
<circle cx="225.2" cy="159.3" r="3.5" fill="none" stroke="#000" stroke-width="1.2"/>
<circle cx="225.2" cy="149.1" r="3.5" fill="none" stroke="#000" stroke-width="1.2"/>
<circle cx="281.6" cy="181.1" r="3.5" fill="none" stroke="#000" stroke-width="1.2"/>
<circle cx="281.6" cy="136.3" r="3.5" fill="none" stroke="#000" stroke-width="1.2"/>
<circle cx="338.0" cy="201.0" r="3.5" fill="none" stroke="#000" stroke-width="1.2"/>
<circle cx="338.0" cy="113.0" r="3.5" fill="none" stroke="#000" stroke-width="1.2"/>
<circle cx="394.4" cy="213.6" r="3.5" fill="none" stroke="#000" stroke-width="1.2"/>
<circle cx="394.4" cy="89.3" r="3.5" fill="none" stroke="#000" stroke-width="1.2"/>
<circle cx="450.8" cy="223.9" r="3.5" fill="none" stroke="#000" stroke-width="1.2"/>
<circle cx="450.8" cy="67.1" r="3.5" fill="none" stroke="#000" stroke-width="1.2"/>
<circle cx="507.2" cy="233.3" r="3.5" fill="none" stroke="#000" stroke-width="1.2"/>
<circle cx="507.2" cy="45.9" r="3.5" fill="none" stroke="#000" stroke-width="1.2"/>
<circle cx="563.6" cy="242.0" r="3.5" fill="none" stroke="#000" stroke-width="1.2"/>
<circle cx="563.6" cy="25.1" r="3.5" fill="none" stroke="#000" stroke-width="1.2"/>
<circle cx="620.0" cy="250.5" r="3.5" fill="none" stroke="#000" stroke-width="1.2"/>
<circle cx="620.0" cy="4.8" r="3.5" fill="none" stroke="#000" stroke-width="1.2"/>
<text x="616" y="334" text-anchor="end">circles: table 2 of Meijaard et al. 2007</text>
</svg>
@@ figures whipple
{
  "diagram": {"kind": "diagram", "model": "whipple"},
  "scene-lean": {"kind": "scene", "model": "whipple", "t": 2.0, "zoom": 7},
  "fig4": {
    "kind": "plot", "model": "whipple", "xlim": [0, 5],
    "rows": [
      {"ylabel": "rate [rad/s]", "series": [{"signal": "Sense/phid", "label": "lean rate"}, {"signal": "Sense/deltad", "label": "steer rate"}], "legend": true},
      {"ylabel": "v [m/s]", "series": [{"signal": "Sense/v", "label": "forward speed"}], "ylim": [4.58, 4.72], "hlines": [{"y": 4.6, "label": "4.60"}, {"y": 4.7, "label": "4.70"}], "legend": true}
    ]
  },
  "weave5": {
    "kind": "plot", "model": "whipple", "xlim": [0, 6],
    "settings": {"t_end": 6.0, "output": {"points": 1201}},
    "overrides": [{"target": "global:v", "value": 5.0}, {"target": "global:phid0", "value": 0.05}],
    "rows": [
      {"ylabel": "angle [rad]", "series": [{"signal": "Sense/phi", "label": "lean"}, {"signal": "Sense/delta", "label": "steer"}], "legend": true}
    ]
  },
  "weave3": {
    "kind": "plot", "model": "whipple", "xlim": [0, 3],
    "settings": {"t_end": 3.0, "output": {"points": 601}},
    "overrides": [{"target": "global:v", "value": 3.0}, {"target": "global:phid0", "value": 0.002}],
    "rows": [
      {"ylabel": "angle [rad]", "series": [{"signal": "Sense/phi", "label": "lean"}, {"signal": "Sense/delta", "label": "steer"}], "legend": true}
    ]
  },
  "capsize": {
    "kind": "plot", "model": "whipple", "xlim": [0, 12],
    "settings": {"t_end": 12.0, "output": {"points": 1201}},
    "overrides": [{"target": "global:v", "value": 8.0}, {"target": "global:phid0", "value": 0.05}],
    "rows": [
      {"ylabel": "lean [rad]", "series": [{"signal": "Sense/phi", "label": "lean at 8 m/s"}], "legend": true, "legend_loc": "upper left"}
    ]
  },
  "energy": {
    "kind": "plot", "model": "whipple", "xlim": [0, 5],
    "overrides": [{"target": "RearHub/br", "value": 0.0}, {"target": "RearHub/bt", "value": 0.0}, {"target": "Steer/br", "value": 0.0}, {"target": "Steer/bt", "value": 0.0}, {"target": "FrontHub/br", "value": 0.0}, {"target": "FrontHub/bt", "value": 0.0}],
    "rows": [
      {"ylabel": "tyre loss [J]", "series": [{"signal": "Energy/loss", "label": "dissipated in the tyres"}], "legend": true, "legend_loc": "upper left"},
      {"ylabel": "Ebal [J]", "series": [{"signal": "Energy/Ebal", "label": "stored + loss (constant to 0.07 mJ)"}], "legend": true}
    ]
  }
}
@@ page whipple overview - | Overview
# The hands-off bicycle in 3D

The benchmark bicycle as a nonlinear **3D bond graph**: rear frame with rider, fork, two wheels, three hinges and two rolling tyres. Nobody holds the handlebar. The run starts like the paper's figure 4: rolling straight at **4.6 m/s** when a sideways push gives it a lean rate of **0.5 rad/s**.

![The 3D view at 2 s, in the second weave swing: the bicycle leans 0.06 rad to the right and has steered 0.06 rad into the lean|800](@fig:scene-lean)

The bicycle leans to the right, the handlebar turns to the right on its own, the wheels run back under the rider and the bicycle comes upright after one and a half swings of the **weave** oscillation. At 4.6 m/s it is inside the self-stable band (4.29 to 6.02 m/s, see [the benchmark bicycle](project:benchmark)).

![Lean and steer rate and the forward speed (compare the paper's figure 4)|900](@fig:fig4)

The forward speed is not held: the bicycle coasts, and the energy of the sideways motion is traded with the forward motion (the speed rises to 4.69 m/s while the lean is largest and settles at 4.62 m/s). It stays between 4.60 and 4.70 m/s, the range of the paper's figure.

## Run it

Press **Run** (5 s, about 15 s of solving). The **3D View** replays the run; the orange marker on each rim shows the wheels turning. Default plots: lean and steer angle ([Sense](block:Sense) `phi`, `delta`), their rates, the [forward speed](signal:Sense/v), the path, the tyre normal forces and the energy book.

The dashboard has two sliders, both **global parameters**: the forward speed `v` and the push `phid0` (the lean rate at the start). Things to try:

- **3 m/s**: below the weave speed the oscillation grows and the bicycle falls (after about 2 s with the default push; the model does not stop at the floor, so stop reading once the lean passes 1 rad).
- **5 m/s**: the weave dies out faster.
- **8 m/s** with a run of 12 s (Simulation settings): the weave dies out in a second, then the bicycle slowly capsizes, leaning and turning ever more to the right.
- **phid0 = 0**: nothing happens. The upright bicycle is an equilibrium at every speed.

Pages: [model and bond graph](page:model), [validation](page:validation).
@@ page whipple model overview | Model and bond graph
# Model and bond graph

![The model canvas|1000](@fig:diagram)

Every body, joint and contact is a library block:

```
Ground (ContactSurface) --> TyreR, TyreF (RollingDisk, knife edge)
RearFrame (RigidBody3D) <-- PoseB (PoseIntegrator3D)                 the floating base
RearFrame.p == MountR == RearHub (Revolute3D) == LinkRW == RearWheel (RigidBody3D) == TyreR
RearFrame.p == MountS == Steer (Revolute3D)   == LinkH  == Fork (RigidBody3D)
Fork.p      == MountF == FrontHub (Revolute3D) == LinkFW == FrontWheel (RigidBody3D) == TyreF
FreeR, FreeS, FreeF (Se, zero torque) -> the three joint drives
```

- **Bodies.** [RearFrame](block:RearFrame), [Fork](block:Fork), [RearWheel](block:RearWheel), [FrontWheel](block:FrontWheel): `RigidBody3D` with their mass and principal inertias. The paper gives the frame and fork inertias with a product of inertia $I_{xz}$, so `design/build_model.py` turns each body frame into its principal axes.
- **Floating base.** Only the rear frame's pose is integrated ([PoseB](block:PoseB)). The other bodies compose their poses through the joints (`LocalPose3D` and `ComposePose3D`), so they add no pose states.
- **Joints.** [RearHub](block:RearHub), [Steer](block:Steer) and [FrontHub](block:FrontHub) are `Revolute3D`. Their joint frames are placed by `FixedTransform3DNeutral` mounts. The steer joint's axis points *down* the steer axis, tilted 18° back, so its angle is the paper's steer angle (positive to the right). The five held directions of each joint are stiff springs ($10^6$) with dampers. They start deflected by the static load (0.6 mm at the rear hub), so the run starts in equilibrium.
- **Tyres.** [TyreR](block:TyreR) and [TyreF](block:TyreF) are `RollingDisk` contacts with a zero crown radius, i.e. the paper's knife-edge wheels. The contact point travels around the rim; the normal force is a stiff Hertz spring and the friction a regularised Coulomb law, so the wheels roll without slipping up to a creep below 0.5 mm/s. The contact radius is the wheel radius plus the static tyre deflection (0.72 mm rear, 0.46 mm front), which puts the loaded wheel centres at the paper's heights.
- **No hands.** The steer drive is a zero torque ([FreeS](block:FreeS)); so are the hub drives (no pedalling, no brakes).

Two example blocks (in `library/`) only measure:

| block | role |
| --- | --- |
| [Sense](block:Sense) `BikeSense` | the paper's coordinates: lean `phi` and its rate from the rear frame's pose and angular velocity, steer `delta` from the steer joint, heading `psi` (integrated heading rate), forward speed `v` (rear wheel rate times rolling radius) and the rear hub position |
| [Energy](block:Energy) `BikeEnergy` | kinetic and potential energy of the four bodies, the tyre and joint springs, the tyre losses and the steer torque's work: `Ebal` stays constant |

Signs: the world frame has x forward, y to the left and z up. The paper's frame (y right, z down) is the world turned by π about x, so the paper's lean and steer angles keep their signs (positive to the right).
@@ page whipple validation overview | Validation
# Validation

## Against the paper's eigenvalues

The paper's table 2 lists the eigenvalues of the linearised bicycle at each whole speed. A run of this nonlinear model after a small push shows the same modes; a damped-oscillation fit of the steer (or lean) rate gives the weave's damping ratio $\zeta$ and natural frequency $\omega_n$:

| speed | push | table 2 weave pair | $\zeta$, $\omega_n$ (table 2) | $\zeta$, $\omega_n$ (3D bond graph) |
| --- | --- | --- | --- | --- |
| 3 m/s | 0.002 rad/s | 1.7068 ± 2.3158 i | −0.5933, 2.8768 | −0.5935, 2.8801 |
| 4 m/s | 0.01 rad/s | 0.4133 ± 3.0791 i | −0.1330, 3.1067 | −0.1353, 3.1045 |
| 5 m/s | 0.05 rad/s | −0.7753 ± 4.4649 i | 0.1711, 4.5317 | 0.1702, 4.5153 |
| 6 m/s | 0.05 rad/s | −1.5264 ± 5.8767 i | 0.2514, 6.0717 | 0.2508, 6.0596 |

A negative $\zeta$ is a growing oscillation. The fit itself is accurate to about 0.2 % (it gives 4.526 rad/s on the exact linear response at 5 m/s), so the bond graph agrees with the benchmark to the accuracy of the fit.

![At 5 m/s the weave dies out|900](@fig:weave5)

![At 3 m/s it grows: below the weave speed the bicycle falls|900](@fig:weave3)

Above the capsize speed the bicycle falls over slowly: at 8 m/s the capsize eigenvalue is +0.143/s. The lean of the bond graph at 6 s and 12 s is within 0.7 % of the linearised benchmark from the same start (0.3 % and 0.6 % low).

![At 8 m/s the weave dies out within a second, then the lean grows slowly (capsize)|900](@fig:capsize)

## Against the linear model

After a 0.05 rad/s push at 5 m/s, the lean and steer angles of this model and of model [linear](model:linear) differ by less than 8e-5 rad over 6 s, on a motion of 0.011 rad (0.7 %). The difference is the nonlinearity and the compliance of tyres and joints.

## Energy

The Whipple bicycle has no friction, so its energy is constant. [Energy](block:Energy) adds the kinetic energy $\tfrac12 V\cdot P$ and the potential energy of the four bodies, the tyre and joint springs and the energy dissipated in the tyres (`loss`). With the joint dampers off, `Ebal` stays constant to 0.07 mJ out of 1837 J:

![Energy book with the joint dampers off|900](@fig:energy)

Without their dampers the stiff joints keep a high-frequency vibration alive, and the tyres dissipate 2.8 J of it in 5 s. This is why the models keep the dampers on; they take 0.24 J in this run, which the book does not count.

## What is not the paper's model

- Tyres and joints are stiff springs, not rigid constraints. The static tyre deflection is under a millimetre, the side creep under 0.5 mm/s.
- The contact radius is 0.7 mm (rear) and 0.5 mm (front) larger than the wheel radius, so the wheels spin 0.2 % slower than in the paper for the same speed. This changes the gyroscopic terms by 0.2 %.
@@ figures linear
{
  "diagram": {"kind": "diagram", "model": "linear"},
  "response": {
    "kind": "plot", "model": "linear", "xlim": [0, 5],
    "rows": [
      {"ylabel": "angle [rad]", "series": [{"signal": "Lean/y", "label": "lean phi"}, {"signal": "Steer/y", "label": "steer delta"}], "legend": true},
      {"ylabel": "heading [rad]", "series": [{"signal": "Heading/y", "label": "heading psi"}], "legend": true}
    ]
  },
  "vw": {
    "kind": "plot", "model": "linear", "xlim": [0, 10],
    "settings": {"t_end": 10.0, "output": {"points": 2001}},
    "overrides": [{"target": "global:v", "value": 4.29238253634111}, {"target": "global:phid0", "value": 0.1}],
    "rows": [
      {"ylabel": "lean rate [rad/s]", "series": [{"signal": "LeanRate/y", "label": "at the weave speed 4.2924 m/s"}], "legend": true}
    ]
  }
}
@@ page linear overview - | Overview
# The linearised benchmark bicycle

The paper's equations of motion for small lean $\phi$ and steer $\delta$ about upright straight rolling at speed $v$:

$$M\ddot q + v\,C_1\dot q + (g K_0 + v^2 K_2)\,q = f, \qquad q = (\phi, \delta), \quad f = (T_\phi, T_\delta)$$

with the benchmark's matrices (the paper's eq. 6.1 to 6.4)

$$M = \begin{bmatrix} 80.817 & 2.319 \\ 2.319 & 0.298 \end{bmatrix},\quad C_1 = \begin{bmatrix} 0 & 33.866 \\ -0.850 & 1.685 \end{bmatrix},\quad K_0 = \begin{bmatrix} -80.95 & -2.600 \\ -2.600 & -0.803 \end{bmatrix},\quad K_2 = \begin{bmatrix} 0 & 76.597 \\ 0 & 2.654 \end{bmatrix}.$$

![The signal diagram|1000](@fig:diagram)

The diagram solves for the two accelerations, $\ddot q = M^{-1}(f - v C_1 \dot q - (g K_0 + v^2 K_2) q)$, and integrates twice ([LeanRate](block:LeanRate), [Lean](block:Lean), [SteerRate](block:SteerRate), [Steer](block:Steer)). Each gain is one entry of the matrices, written as an expression of the global `v`: for example [K_phi_delta](block:K_phi_delta) is the $\phi\delta$ entry of $-M^{-1}(g K_0 + v^2 K_2)$. The steer torque enters through [B_phi](block:B_phi) and [B_delta](block:B_delta) (the second column of $M^{-1}$); here it is zero ([SteerTorque](block:SteerTorque)). The heading follows from the rolling kinematics, $\dot\psi = (v\delta + c\dot\delta)\cos\lambda / w$ ([Heading](block:Heading)).

Why a signal diagram and not a bond graph: $C_1$ and $K_2$ are not symmetric. They come from the rolling constraints and are neither stored energy nor dissipation, so in a bond graph they would be modulated sources driven by the states, i.e. this same diagram. The physical bond graph is [whipple](model:whipple).

## Run it

Press **Run** (instant; the dashboard re-runs on every change). The start is the paper's figure 4: 4.6 m/s and a lean rate of 0.5 rad/s.

![Lean, steer and heading at 4.6 m/s|900](@fig:response)

Slide the **speed** and watch the self-stable band (4.29 to 6.02 m/s, [the benchmark bicycle](project:benchmark)): below it the weave grows, above it the lean drifts away slowly (capsize; lengthen the run to see it). At exactly the weave speed the weave neither grows nor decays:

![At the weave speed 4.2924 m/s the weave is undamped: 3.4350 rad/s, the paper's table 2|900](@fig:vw)

## Checks

- The lean and steer of this model equal the matrix exponential of the paper's matrices (computed in `design/design.py`) to 1e-8.
- At the weave speed of table 2 the fitted damping is zero (to 2e-5) at the table's frequency 3.4350 rad/s.
- At 5 m/s the fitted weave matches table 2 to 0.2 %, and the 3D bond graph matches this model (see [whipple validation](model:whipple/validation)).
@@ figures balance
{
  "diagram": {"kind": "diagram", "model": "balance"},
  "scene-turn": {"kind": "scene", "model": "balance", "t": 7.0, "zoom": 7},
  "response": {
    "kind": "plot", "model": "balance", "xlim": [0, 10],
    "rows": [
      {"ylabel": "lean [rad]", "series": [{"signal": "Sense/phi", "label": "lean"}, {"signal": "LeanRef/y", "label": "set-point", "style": "--"}], "legend": true, "legend_loc": "lower right"},
      {"ylabel": "steer [rad]", "series": [{"signal": "Sense/delta", "label": "steer"}], "legend": true, "legend_loc": "lower right"},
      {"ylabel": "torque [N m]", "series": [{"signal": "Ctrl/y", "label": "steer torque"}], "legend": true}
    ]
  },
  "path": {
    "kind": "plot", "model": "balance", "width": 560, "row_height": 5.0,
    "rows": [
      {"ylabel": "y [m]", "x": "Sense/x", "xlabel": "x [m]", "equal": true, "series": [{"signal": "Sense/y", "label": "rear hub"}]}
    ]
  }
}
@@ page balance overview - | Overview
# Balancing the bicycle at low speed

At **3 m/s** the benchmark bicycle is too slow to balance itself: the weave grows by a factor of e every 0.6 s. Here a **steer torque** keeps it up, as a rider's hands would, and a **lean set-point** turns it.

![The 3D view at 7 s: a steady right turn at 0.1 rad lean|800](@fig:scene-turn)

The plant is the 3D bond graph of [whipple](model:whipple) with an `MSe` on the steer joint ([SteerMotor](block:SteerMotor)). The run starts with a sideways push (lean rate 0.3 rad/s); at 2 s the lean set-point steps to 0.1 rad to the right ([LeanRef](block:LeanRef), global `lean_ref`).

![Lean, steer angle and steer torque|900](@fig:response)

The push is caught within a second. For the right turn, the controller first steers **left** (counter-steering): the wheels run out to the left, the bicycle falls to the right, and then the handlebar follows into the turn. In the steady turn the rider holds the handlebar with a small torque *against* the turn (−0.55 N m).

![Path of the rear hub: a right turn of 9 m radius|500](@fig:path)

## Run it

Press **Run** (10 s, about 15 s of solving). The dashboard sets the lean set-point (global `lean_ref`, negative for a left turn) and the push `phid0`.

Pages: [controller](page:controller).
@@ page balance controller overview | Controller
# Controller

![The model canvas: the 3D bicycle and the controller|1000](@fig:diagram)

A state feedback on the steer torque, designed by LQR on the [linear model](model:balance-linear) at 3 m/s (`design/design.py`):

$$T_\delta = -K x + N \phi_{ref}, \qquad x = (\phi, \delta, \dot\phi, \dot\delta)$$

| | value |
| --- | --- |
| weights | $Q = \mathrm{diag}(100, 10, 10, 1)$, $R = 1$ |
| gain $K$ | (−28.45, 18.70, −7.67, 1.97) |
| reference gain $N$ | −12.44 |
| closed-loop poles | −11.01, −2.59 ± 2.71 i, −2.85 |

The gains are the [L_phi](block:L_phi), [L_delta](block:L_delta), [L_phid](block:L_phid), [L_deltad](block:L_deltad) blocks (each $-K_i$) and [N_ref](block:N_ref); [Sense](block:Sense) provides the states. $N$ makes the steady turn at lean $\phi_{ref}$ the equilibrium of the linear closed loop: in a steady turn the lean equation gives $\delta = 1.196\,\phi$ and the steer equation the holding torque $T = -6.35\,\phi$ N m.

On the nonlinear bicycle the turn settles at 0.1016 rad lean and 0.1177 rad steer (linear design: 0.1 and 0.1196). The bicycle speeds up from 3.00 to 3.05 m/s while it leans (its centre of mass drops), and the controller has no integral action. The heading rate 0.3381 rad/s agrees with the rolling kinematics $v \tan\delta \cos\lambda / (w \cos\phi)$ at the measured speed, steer and lean to 0.03 %.

The gains are fixed for 3 m/s. At other speeds the loop still balances over a range (try `v` in the Model inspector), but the steady lean is no longer exactly the set-point.
@@ figures balance-linear
{
  "response": {
    "kind": "plot", "model": "balance-linear", "xlim": [0, 10],
    "rows": [
      {"ylabel": "lean [rad]", "series": [{"signal": "Lean/y", "label": "lean"}, {"signal": "LeanRef/y", "label": "set-point", "style": "--"}], "legend": true, "legend_loc": "lower right"},
      {"ylabel": "torque [N m]", "series": [{"signal": "Ctrl/y", "label": "steer torque"}], "legend": true}
    ]
  }
}
@@ page balance-linear overview - | Overview
# The balance controller on the linear model

The controller of [balance](model:balance) on the linearised benchmark ([linear](model:linear)) at 3 m/s: the model the controller was designed on. It runs in a fraction of a second.

![Lean and steer torque|900](@fig:response)

Here the turn settles exactly on the set-point: lean 0.1 rad, steer 0.1196 rad, heading rate 0.3346 rad/s and a holding torque of −0.635 N m, the steady turn computed in `design/design.py`. The 3D model of [balance](model:balance) follows this run to within 0.0016 rad of lean.
