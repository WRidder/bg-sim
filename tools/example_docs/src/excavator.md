@@ figures @project
{
  "scene": {"kind": "scene", "model": "excavator-dig-cycle", "t": 5.5, "zoom": 2},
  "circuit": {"kind": "svg", "svg": "circuit"},
  "linkage": {"kind": "svg", "svg": "linkage"},
  "energy": {
    "kind": "plot", "model": "excavator-dig-cycle", "xlim": [0, 16.5],
    "rows": [
      {"ylabel": "engine energy [MJ]", "series": [{"signal": "Ein/y", "label": "load sensing (dig-cycle)", "scale": 1e-6}], "legend": true, "legend_loc": "upper left"},
      {"ylabel": "pump pressure [bar]", "series": [{"signal": "Vpump/p", "label": "pump line", "scale": 1e-5}, {"signal": "Vls/p", "label": "LS line", "scale": 1e-5, "style": "--"}], "legend": true, "legend_loc": "upper right"}
    ]
  },
  "nolsenergy": {
    "kind": "plot", "model": "excavator-no-ls", "xlim": [0, 16.5],
    "rows": [
      {"ylabel": "engine energy [MJ]", "series": [{"signal": "Ein/y", "label": "constant pressure (no-ls)", "scale": 1e-6}], "legend": true, "legend_loc": "upper left"},
      {"ylabel": "pump pressure [bar]", "series": [{"signal": "Vpump/p", "label": "pump line", "scale": 1e-5}], "legend": true, "legend_loc": "lower right"}
    ]
  }
}
@@ svg @project circuit
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 860 430" font-family="sans-serif" font-size="12">
<rect width="860" height="430" fill="#ffffff"/>
<rect x="20" y="170" width="90" height="60" rx="6" fill="#dddddd" stroke="#333"/>
<text x="65" y="195" text-anchor="middle" fill="#222">engine</text>
<text x="65" y="212" text-anchor="middle" fill="#222" font-size="11">1800 rpm</text>
<line x1="110" y1="200" x2="150" y2="200" stroke="#333" stroke-width="4"/>
<circle cx="185" cy="200" r="34" fill="#fde9b0" stroke="#333" stroke-width="2"/>
<text x="185" y="196" text-anchor="middle" fill="#222">LS pump</text>
<text x="185" y="212" text-anchor="middle" fill="#222" font-size="11">220 cm³/rev</text>
<text x="185" y="258" text-anchor="middle" fill="#555" font-size="11">margin 25 bar, cut-off 320 bar,</text>
<text x="185" y="272" text-anchor="middle" fill="#555" font-size="11">power limit 100 kW</text>
<line x1="219" y1="200" x2="300" y2="200" stroke="#d62728" stroke-width="3"/>
<line x1="260" y1="200" x2="260" y2="320" stroke="#d62728" stroke-width="2"/>
<rect x="240" y="320" width="40" height="26" fill="#ffffff" stroke="#d62728"/>
<text x="260" y="337" text-anchor="middle" fill="#d62728" font-size="11">relief</text>
<text x="290" y="337" fill="#d62728" font-size="11">343 bar</text>
<line x1="300" y1="80" x2="300" y2="320" stroke="#d62728" stroke-width="3"/>
<text x="306" y="74" fill="#d62728" font-size="11">pump line (Vpump)</text>
<g>
<line x1="300" y1="110" x2="360" y2="110" stroke="#d62728" stroke-width="2"/>
<rect x="360" y="95" width="80" height="30" fill="#fde0dc" stroke="#333"/>
<text x="400" y="114" text-anchor="middle" fill="#222" font-size="11">compensator</text>
<line x1="440" y1="110" x2="480" y2="110" stroke="#ff7f0e" stroke-width="2"/>
<rect x="480" y="90" width="90" height="40" fill="#e8f1fa" stroke="#333"/>
<text x="525" y="108" text-anchor="middle" fill="#222" font-size="11">4/3 spool</text>
<text x="525" y="122" text-anchor="middle" fill="#222" font-size="11">+ LS edge</text>
<line x1="570" y1="102" x2="660" y2="102" stroke="#333" stroke-width="2"/>
<line x1="570" y1="118" x2="660" y2="118" stroke="#333" stroke-width="2"/>
<rect x="660" y="92" width="150" height="36" fill="#fde9b0" stroke="#333"/>
<text x="735" y="114" text-anchor="middle" fill="#222">boom cylinders (2×)</text>
</g>
<g>
<line x1="300" y1="200" x2="360" y2="200" stroke="#d62728" stroke-width="2"/>
<rect x="360" y="185" width="80" height="30" fill="#fde0dc" stroke="#333"/>
<text x="400" y="204" text-anchor="middle" fill="#222" font-size="11">compensator</text>
<line x1="440" y1="200" x2="480" y2="200" stroke="#ff7f0e" stroke-width="2"/>
<rect x="480" y="180" width="90" height="40" fill="#e8f1fa" stroke="#333"/>
<text x="525" y="198" text-anchor="middle" fill="#222" font-size="11">4/3 spool</text>
<text x="525" y="212" text-anchor="middle" fill="#222" font-size="11">+ LS edge</text>
<line x1="570" y1="192" x2="660" y2="192" stroke="#333" stroke-width="2"/>
<line x1="570" y1="208" x2="660" y2="208" stroke="#333" stroke-width="2"/>
<rect x="660" y="182" width="150" height="36" fill="#fde9b0" stroke="#333"/>
<text x="735" y="204" text-anchor="middle" fill="#222">arm cylinder</text>
</g>
<g>
<line x1="300" y1="290" x2="360" y2="290" stroke="#d62728" stroke-width="2"/>
<rect x="360" y="275" width="80" height="30" fill="#fde0dc" stroke="#333"/>
<text x="400" y="294" text-anchor="middle" fill="#222" font-size="11">compensator</text>
<line x1="440" y1="290" x2="480" y2="290" stroke="#ff7f0e" stroke-width="2"/>
<rect x="480" y="270" width="90" height="40" fill="#e8f1fa" stroke="#333"/>
<text x="525" y="288" text-anchor="middle" fill="#222" font-size="11">4/3 spool</text>
<text x="525" y="302" text-anchor="middle" fill="#222" font-size="11">+ LS edge</text>
<line x1="570" y1="282" x2="660" y2="282" stroke="#333" stroke-width="2"/>
<line x1="570" y1="298" x2="660" y2="298" stroke="#333" stroke-width="2"/>
<rect x="660" y="272" width="150" height="36" fill="#fde9b0" stroke="#333"/>
<text x="735" y="294" text-anchor="middle" fill="#222">bucket cylinder</text>
</g>
<line x1="525" y1="130" x2="525" y2="150" stroke="#2ca02c" stroke-width="2" stroke-dasharray="5 3"/>
<line x1="525" y1="220" x2="525" y2="240" stroke="#2ca02c" stroke-width="2" stroke-dasharray="5 3"/>
<line x1="525" y1="310" x2="525" y2="370" stroke="#2ca02c" stroke-width="2" stroke-dasharray="5 3"/>
<polygon points="519,150 531,150 525,160" fill="#2ca02c"/>
<polygon points="519,240 531,240 525,250" fill="#2ca02c"/>
<polygon points="519,360 531,360 525,370" fill="#2ca02c"/>
<line x1="590" y1="155" x2="590" y2="370" stroke="#2ca02c" stroke-width="2" stroke-dasharray="5 3"/>
<line x1="525" y1="160" x2="590" y2="160" stroke="#2ca02c" stroke-width="2" stroke-dasharray="5 3"/>
<line x1="525" y1="250" x2="590" y2="250" stroke="#2ca02c" stroke-width="2" stroke-dasharray="5 3"/>
<line x1="185" y1="370" x2="590" y2="370" stroke="#2ca02c" stroke-width="2" stroke-dasharray="5 3"/>
<line x1="185" y1="370" x2="185" y2="234" stroke="#2ca02c" stroke-width="2" stroke-dasharray="5 3"/>
<text x="600" y="345" fill="#2ca02c" font-size="11">shuttle (check) valves: the highest</text>
<text x="600" y="359" fill="#2ca02c" font-size="11">load pressure reaches the LS line (Vls)</text>
<text x="200" y="388" fill="#2ca02c" font-size="11">LS line to the pump regulator; bleed orifice to tank</text>
<text x="20" y="30" fill="#222" font-size="14">Load-sensing system: the pump keeps its outlet 25 bar above the highest load;</text>
<text x="20" y="48" fill="#222" font-size="14">each compensator holds 10 bar across its spool, so the flow follows the joystick.</text>
<text x="660" y="160" fill="#555" font-size="11">make-up checks from tank</text>
<text x="660" y="174" fill="#555" font-size="11">on every cylinder port</text>
</svg>
@@ svg @project linkage
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 860 380" font-family="sans-serif" font-size="12">
<rect width="860" height="380" fill="#ffffff"/>
<line x1="40" y1="330" x2="820" y2="330" stroke="#8c6d46" stroke-width="3"/>
<text x="760" y="350" fill="#8c6d46" font-size="11">soil surface</text>
<line x1="120" y1="230" x2="470" y2="110" stroke="#f0b400" stroke-width="16" stroke-linecap="round"/>
<text x="250" y="140" fill="#222">boom 5.70 m</text>
<line x1="470" y1="110" x2="640" y2="290" stroke="#f0b400" stroke-width="12" stroke-linecap="round"/>
<text x="580" y="170" fill="#222">arm 2.90 m</text>
<line x1="640" y1="290" x2="700" y2="345" stroke="#c98d00" stroke-width="10" stroke-linecap="round"/>
<text x="712" y="330" fill="#222">bucket 1.50 m</text>
<circle cx="120" cy="230" r="7" fill="#fff" stroke="#333" stroke-width="2"/>
<text x="92" y="222" text-anchor="end" fill="#222">O (boom foot)</text>
<circle cx="470" cy="110" r="6" fill="#fff" stroke="#333" stroke-width="2"/>
<text x="470" y="96" text-anchor="middle" fill="#222">C</text>
<circle cx="640" cy="290" r="6" fill="#fff" stroke="#333" stroke-width="2"/>
<text x="624" y="304" text-anchor="end" fill="#222">Q</text>
<line x1="126" y1="282" x2="280" y2="190" stroke="#555" stroke-width="9"/>
<line x1="280" y1="190" x2="300" y2="178" stroke="#bbb" stroke-width="5"/>
<circle cx="126" cy="282" r="5" fill="#333"/>
<text x="136" y="300" fill="#222">A1</text>
<text x="300" y="214" fill="#222">B1 · boom cylinders</text>
<line x1="420" y1="90" x2="300" y2="70" stroke="#555" stroke-width="9"/>
<line x1="420" y1="90" x2="460" y2="97" stroke="#bbb" stroke-width="5"/>
<text x="290" y="60" fill="#222">A2 · arm cylinder · B2 (arm tail)</text>
<line x1="490" y1="140" x2="590" y2="245" stroke="#555" stroke-width="7"/>
<text x="470" y="250" fill="#222">A3 · bucket cylinder</text>
<line x1="590" y1="245" x2="620" y2="262" stroke="#333" stroke-width="4"/>
<line x1="590" y1="245" x2="655" y2="270" stroke="#333" stroke-width="4"/>
<circle cx="620" cy="262" r="4" fill="#fff" stroke="#333"/>
<circle cx="590" cy="245" r="4" fill="#333"/>
<circle cx="655" cy="270" r="4" fill="#fff" stroke="#333"/>
<text x="664" y="262" fill="#222">J (rocker / H-link pin)</text>
<text x="664" y="282" fill="#222">R (rocker on the arm), P (H-link on the bucket)</text>
<text x="40" y="30" fill="#222" font-size="14">Each cylinder length is a result: CylinderMount2D computes L, dL/dq and the rod extension</text>
<text x="40" y="48" fill="#222" font-size="14">from the pin positions; BucketLinkage2D solves the rocker-H-link four-bar (ratio k = dφ/dq3).</text>
</svg>
@@ page @project machine - | The excavator front
# The front of a 20-t hydraulic excavator

This project models the **front of a 20-t class crawler excavator**: the boom (5.70 m), the arm (2.90 m) and the
bucket (1.50 m, 0.93 m³ heaped). The mechanism is planar, with the **real cylinder linkage**: the two boom cylinders
from the upper structure to the boom, the arm cylinder from the boom to the arm tail, and the bucket cylinder
through the rocker and H-link **four-bar** to the bucket. The cylinders are driven by a **load-sensing (LS)
hydraulic system**: a variable pump at constant engine speed with an LS regulator, pressure cut-off and power
limiter, three pre-compensated proportional valve sections, a shuttle network, a main relief and the tank. The
bucket teeth cut **soil** with the fundamental earthmoving equation and fill the bucket.

![The dig cycle in 3D at 5.5 s: the bucket curls out of the cut, full|700](@fig:scene)

| model | what it shows |
| --- | --- |
| [excavator-kinematics](model:excavator-kinematics) | the linkage alone: prescribed cylinder lengths, the bucket tip from forward kinematics |
| [excavator-lift](model:excavator-lift) | holding 1.5 t, the hydraulic ringing of the boom, then a boom lift through the LS system |
| [excavator-dig-cycle](model:excavator-dig-cycle) | a scripted 16.5 s dig cycle: penetrate, drag, curl, lift, dump, return |
| [excavator-no-ls](model:excavator-no-ls) | the same cycle on a constant-pressure supply (no load sensing), for the energy comparison |

All four share one design: `design/design.py` computes the parameters and the independent references (forward
kinematics, static forces, hydraulic modes, earthmoving factors) in Python, and `design/build_model.py` writes
the models, the 3D scene and `expected.json`. The details: [mechanics](page:mechanics),
[hydraulics](page:hydraulics), [soil](page:soil), and [checks and limits](page:checks).

**Energy.** The LS system costs **0.57 MJ** at the engine shaft for the dig cycle; the same cycle on a
constant-pressure supply (281 bar) costs **1.52 MJ**, 2.7 times as much.

![Engine energy and pump pressure in the dig cycle (load sensing)|900](@fig:energy)

![The same cycle on a constant-pressure supply|900](@fig:nolsenergy)
@@ page @project mechanics machine | Mechanics and linkage
# Mechanics

The three links are `RigidBody2D` bodies on `Revolute2DLimit` joints (planar multibond bond graph, as in
robot-arm-2d). The joint angles are relative: q1 the boom against the horizontal, q2 the arm against the boom
line, q3 the bucket against the arm line. The joint limits are the **cylinder end stops**: the angles at which
each cylinder is fully retracted or extended (boom −40° to 62°, arm −158° to −52°, bucket −125° to 45°).

![The linkage and the pins|860](@fig:linkage)

**Masses.** The total of boom, arm and bucket, **3606 kg**, is the front mass of the 20-t excavator in Jin et al.
(2024). The split (boom 1650 kg, arm 1000 kg, bucket 956 kg with its linkage), the centres of mass and the
inertias (slender links) are ours. The lift model adds a 1.5 t payload to the bucket (0.93 m³ of loose soil).

**Cylinder linkage.** Each cylinder is a `HydraulicCylinder` (chambers with compressibility, `beta` = 1.2 GPa
for oil with hoses) whose rod drives a translational 1-junction with a `Friction` element (Coulomb plus viscous)
to the barrel. A `RackAndPinion` with radius 1 turns the rod motion into a rotation, and a modulated transformer
(`MTF`) with the moment arm r = dL/dq of the custom block `CylinderMount2D` couples it to the joint. So the
cylinder force does exactly the virtual work of the real linkage, and the cylinder length is a **kinematic
result** of the pin positions, not a state of its own. For the bucket, the arm-side `BucketLinkage2D` block solves
the rocker / H-link four-bar (circle intersection) and gives the ratio k = dφ/dq3 between the rocker angle and the
bucket angle: the bucket cylinder works on the rocker through r, and the rocker on the bucket through k.

| cylinder | bore / rod [mm] | count | stroke [m] | source |
| --- | --- | --- | --- | --- |
| boom | 120 / 85 | 2 | 1.30 | Jin et al. (2024): 11310 / 5635 mm² per cylinder |
| arm | 140 / 100 | 1 | 1.31 | typical 20-t size (assumed) |
| bucket | 120 / 85 | 1 | 1.09 | typical 20-t size (assumed) |

The strokes and the closed lengths follow from the pin layout and the joint ranges (`design.py`). The end stops
of the joints (stiffness 2·10⁷ N·m/rad) act as the cylinder end stops.
@@ page @project hydraulics machine | Load-sensing hydraulics
# Hydraulics

![The load-sensing circuit|860](@fig:circuit)

**Pump.** `LoadSensingPump` (stdlib, `converters`) is a variable-displacement pump of 220 cm³/rev at a constant
1800 rpm (396 l/min at full stroke). Its static regulator sets the displacement so that the outlet stays
`dp_ls` = 25 bar above the LS port (linear over a 2 bar regulation range), with a pressure cut-off at 320 bar and
a torque limiter at 530 N·m (100 kW of ideal pump power at 1800 rpm; the shaft power adds the friction loss
and peaks at 116 kW in the dig cycle). Volumetric and mechanical efficiencies 0.95 / 0.92. The
form follows the pressure-compensated pump of Simscape Fluids, with the LS pressure added to the set point.

**Sections.** Each of the three valve sections is a pre-compensator (`PressureCompensatedFlowControl`, 10 bar
across the spool) in front of a 4/3 spool (`DirectionalValve43`), whose opening follows the joystick through a
first-order spool lag (80 ms). The flow therefore depends on the joystick and not on the load: the boom passes
300 l/min at full stick, the arm 280, the bucket 200. A small **LS edge** on each spool (a second `DirectionalValve43`)
connects the LS gallery to the pressurised cylinder port. **Shuttle network:** a `CheckValve` from each gallery
to the common LS line picks the highest load pressure; a bleed orifice drains the line to tank when the sections
close. Make-up check valves on every cylinder port prevent cavitation.

**Volumes.** Every valve sits between two volumes (pump line, the volume between compensator and spool, the
cylinder chambers, the LS line), so the hydraulic connection sets have no algebraic loops.

**Relief.** A main `PressureReliefValve` at 343 bar. The LS pump never needs it: the cut-off destrokes the pump
first.

**No load sensing.** [excavator-no-ls](model:excavator-no-ls) ties the pump's LS port to the tank and sets the
margin to 280 bar, so the pump holds a constant 281 bar, and the sections throttle the difference to the load.
@@ page @project soil machine | Soil and bucket fill
# Soil

`SoilCutting2D` (custom) is a nonlinear resistive element on the bucket's planar bond. It uses the **fundamental
earthmoving equation** (Reece 1964, in McKyes' form) for a tool of width w at the cutting depth d:

$$F = w\,(\gamma d^2 N_\gamma + c\,d\,N_c) + \rho\,w\,d\,|v|^2,$$

against the tooth velocity v. The factors N_γ = 1.436 and N_c = 1.998 come from `design.py`: the flat-ground form
(Wagner 2025, eq. 15) for a 45° rake angle, an internal friction angle of 30° and a soil-tool friction of 20°,
minimised over the failure angle. The soil is a loam: unit weight 18 kN/m³, cohesion 15 kPa (the dashboard
slider goes to 60 kPa, stiff clay), density 1835 kg/m³.

**Fill.** The bucket takes the swept volume w·d·|v| times the swell factor 1.25 until it is full (0.93 m³
heaped) and spills once its mouth faces down. The soil in the bucket adds its weight at the centre of the
bucket (its inertia is not modelled). The depth is a smooth positive part of the penetration, so the force is
continuous and there are no events.

**Ground contact.** The cutting force grows with d², so the bucket cannot sink far: in the dig cycle the teeth
reach 0.43 m. The ground itself is flat at 1.95 m below the boom foot.
@@ page @project checks machine | Checks and limits
# Checks and limits

`uv run examples/run_checks.py --only excavator` runs every model and checks `expected.json` (50 checks):

| check | bond graph | reference (design.py) |
| --- | --- | --- |
| bucket tip at 6.5 s / 12.5 s (kinematics) | (7.38335, 2.77970) / (2.97815, −1.87711) m | scipy FK from the cylinder lengths, agreement < 4·10⁻⁷ m |
| static boom cylinder force, 1.5 t payload | 274.4 kN | 275.2 kN (moment balance) |
| static arm / bucket cylinder force | 10.6 / 81.0 kN | 10.4 / 81.1 kN (within the Coulomb band) |
| boom hydraulic mode | 2.483 Hz (FFT) | 2.489 Hz (3-DOF eig); 1-DOF formula 2.596 Hz |
| LS margin stand-by / in the lift / in the dig cycle | 27.0 / 26.2 / 22.6–27.0 bar | 25 bar + 2 bar regulation |
| boom section flow, joystick 0.5 | 145 l/min | 150 l/min |
| relief flow in the dig cycle | < 2·10⁻⁹ m³/s | closed |
| bucket fill after the curl / after the dump | 0.75 / 0.004 | > 0.6 / < 0.05 |
| engine energy of the cycle, LS / constant pressure | 0.57 / 1.52 MJ | < 0.7 / > 1.2 MJ |
| port-power ledger | closes (Tellegen) | |

Every model also checks for no causality warnings (no derivative causality, no algebraic loop), no solver
failure and the 3D bindings.

**Solver.** FBDF, reltol = abstol = 10⁻⁶ for the hydraulic models (10⁻⁸ / 10⁻⁹ for the kinematics), 100 output
points per second. Run times on a desktop PC (warm / first run including compilation): kinematics 1.6 / 15 s,
lift 4.8 / 9 s, dig cycle 4.5 / 30 s, no-LS about 23 s first run.

**Simplifications.**

- The cylinder drives its joint through a virtual-work transformer (MTF with r = dL/dq): the joint torque and the
  motion are exact, the pin reaction forces are not modelled.
- The rocker and the H-link are massless; the soil in the bucket has weight but no inertia.
- In the lift model the payload is folded into the bucket body.
- The boom lowers on its meter-out edge: the speed depends on the load (no regeneration, no load-holding valve).
- The shuttle network is a set of check valves into one LS line with a bleed; the pump regulator is static
  (no regulator dynamics).
- The pump's friction torque grows with the pressure even at zero stroke (stdlib pump law): this is why the
  constant-pressure supply idles at about 25 kW.
- The swing is fixed and the ground is flat. In the kinematics model the tip passes below the soil surface (no
  soil there).
- "Cylinder work / engine energy" is the net cylinder work (lifting minus lowering) over the engine shaft energy.
@@ figures excavator-kinematics
{
  "diagram": {"kind": "diagram", "model": "excavator-kinematics"},
  "run": {
    "kind": "plot", "model": "excavator-kinematics", "xlim": [0, 13],
    "rows": [
      {"ylabel": "cylinder length [m]", "series": [{"signal": "BoomMount/L", "label": "boom"}, {"signal": "BoomSetL/y", "label": "boom set", "style": "--"}, {"signal": "ArmMount/L", "label": "arm"}, {"signal": "ArmSetL/y", "label": "arm set", "style": "--"}, {"signal": "BucketMount/L", "label": "bucket"}, {"signal": "BucketSetL/y", "label": "bucket set", "style": "--"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "joint angle [deg]", "series": [{"signal": "Joint1/qout", "label": "q1 boom", "scale": 57.29577951308232}, {"signal": "Joint2/qout", "label": "q2 arm", "scale": 57.29577951308232}, {"signal": "Joint3/qout", "label": "q3 bucket", "scale": 57.29577951308232}], "legend": true, "legend_loc": "right"},
      {"ylabel": "moment arm [m], k", "series": [{"signal": "BoomMount/r", "label": "boom r"}, {"signal": "ArmMount/r", "label": "arm r"}, {"signal": "BucketMount/r", "label": "bucket r"}, {"signal": "Linkage/k", "label": "four-bar k"}], "legend": true, "legend_loc": "right"}
    ]
  },
  "tip": {
    "kind": "plot", "model": "excavator-kinematics", "width": 700,
    "rows": [{"ylabel": "tip y [m]", "x": "PoseTip/g[2]", "xlabel": "tip x [m]", "equal": true, "series": [{"signal": "PoseTip/g[3]", "label": "bucket tip"}]}], "row_height": 4.5
  }
}
@@ page excavator-kinematics overview - | What you're looking at
# Kinematics: cylinder lengths in, bucket tip out

**Scenario.** The hydraulics are replaced by a stiff servo on each cylinder: a [BoomServo](block:BoomServo)
spring-damper pulls the rod towards a set length ([BoomSetL](block:BoomSetL), the integral of the rate table
[BoomRate](block:BoomRate)). The set lengths move from 1 to 4 s, hold until 7 s, move again from 7 to 10 s and
hold until 13 s. Gravity is off in this model (g0 = 0), so the servos only carry the inertia of the front and the
holds are exact.

![The model canvas|900](@fig:diagram)

**What it checks.** At the holds (6.5 s and 12.5 s) the bucket tip, the joint angles, the pin-to-pin lengths,
the moment arm of the bucket cylinder and the four-bar ratio [Linkage/k](signal:Linkage/k) are compared with
`design.py`, which finds the joint angle of each set length by root finding on the geometry of `exc_geom.py`
(scipy `brentq`, the bucket through the four-bar). The tip agrees to better than 4·10⁻⁷ m: (7.3834, 2.7797) m at
6.5 s and (2.9781, −1.8771) m at 12.5 s.

![Cylinder lengths and set lengths, joint angles, moment arms and four-bar ratio|900](@fig:run)

![Bucket tip path|600](@fig:tip)

**Blocks.** [BoomMount](block:BoomMount), [ArmMount](block:ArmMount) and [BucketMount](block:BucketMount)
(`CylinderMount2D`) compute each cylinder length L, the moment arm r = dL/dq and the rod extension from the pin
poses; [Linkage](block:Linkage) (`BucketLinkage2D`) solves the four-bar. The pose chain
(`JointPose2D` / `LocalPose2D` / `ComposePose2D`) gives the world poses of the pins and of the tip
([PoseTip](block:PoseTip)).

**Dashboard.** The tip path, the cylinder lengths, the four-bar ratio and its transmission angle
[Linkage/mu](signal:Linkage/mu). The slider sets the servo stiffness.

**Try:** lower the servo stiffness to 10⁷ N/m: the servos follow the set lengths more loosely, and at the 6.5 s hold the tip
is still about 12 mm from the FK reference (the check then fails).
@@ figures excavator-lift
{
  "diagram": {"kind": "diagram", "model": "excavator-lift"},
  "scene": {"kind": "scene", "model": "excavator-lift", "t": 6.0, "zoom": 1},
  "run": {
    "kind": "plot", "model": "excavator-lift", "xlim": [0, 9],
    "rows": [
      {"ylabel": "boom pressure [bar]", "series": [{"signal": "BoomCyl/pA", "label": "cap side", "scale": 1e-5}, {"signal": "BoomCyl/pB", "label": "rod side", "scale": 1e-5}], "legend": true, "legend_loc": "right"},
      {"ylabel": "boom rod [m]", "series": [{"signal": "BoomCyl/x", "label": "extension"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "pressure [bar]", "series": [{"signal": "Vpump/p", "label": "pump", "scale": 1e-5}, {"signal": "Vls/p", "label": "LS line", "scale": 1e-5}, {"signal": "Pump/margin", "label": "margin", "scale": 1e-5}], "legend": true, "legend_loc": "right"},
      {"ylabel": "flow [l/min]", "series": [{"signal": "BoomComp/Q", "label": "boom section", "scale": 60000}, {"signal": "Pump/Q", "label": "pump", "scale": 60000, "style": "--"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "power [kW]", "series": [{"signal": "Pump/P_in", "label": "engine shaft", "scale": 0.001}, {"signal": "Pump/P_out", "label": "pump hydraulic", "scale": 0.001}, {"signal": "Pcyl/y", "label": "cylinders", "scale": 0.001}], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page excavator-lift overview - | What you're looking at
# Holding and lifting 1.5 t

**Scenario.** The front holds 1.5 t of soil in the bucket at q = (10°, −95°, −95°). At t = 0 the boom cap
pressure starts 15 % below the static value, so the boom drops a little and **rings at its hydraulic natural
frequency** while all valves are closed. From **3 to 6 s** the boom joystick ([LiftStick](block:LiftStick)) is at
0.5 and the boom lifts at about 0.1 m/s of rod speed. When the spool closes at 6 s, the moving front is stopped by the oil
trapped in both chambers: the boom rings again, now with the rod side pressurised as well, and only lightly damped
(the cylinder friction and the valve leakage are the only losses).

![The model canvas: supply and LS line (left), the three valve sections and cylinders, the linkage|900](@fig:diagram)

![Boom pressures, rod extension, pump and LS pressures, flows and power|900](@fig:run)

**Expected outcome** (checked by `expected.json`):

| quantity | bond graph | design.py |
| --- | --- | --- |
| boom cylinder force at 2.9 s | 274.4 kN | 275.2 kN (moment balance) |
| arm / bucket cylinder force | 10.6 / 81.0 kN | 10.4 / 81.1 kN |
| ringing of the boom pressure (FFT) | 2.483 Hz | 2.489 Hz: eig(M⁻¹K) of the 3-DOF front |
| LS margin stand-by / during the lift | 27.0 / 26.2 bar | 25 bar + 2 bar regulation range |
| boom section flow at joystick 0.5 | 145 l/min | 150 l/min (−3 %: compensator saturation) |

The single-DOF estimate of the boom frequency, with the boom-joint inertia and the chamber stiffness
β(A²/V_A + A_r²/V_B), gives 2.60 Hz; the coupled 3-DOF mode at 2.49 Hz is what the bond graph shows. The
cylinder forces agree within the Coulomb band of the cylinder friction.

![The front at 6 s, the end of the lift|600](@fig:scene)

**Blocks.** [Pump](block:Pump) (`LoadSensingPump`), [Vpump](block:Vpump) and [Vls](block:Vls) the pump and LS
lines, [BoomComp](block:BoomComp) and [BoomValve](block:BoomValve) the boom section,
[BoomCyl](block:BoomCyl) the boom cylinders, [BoomForce](block:BoomForce) the force pA·Ap − pB·Ar. [Ein](block:Ein),
[Ecyl](block:Ecyl) and [Eff](block:Eff) integrate the engine and the cylinder energy.

**Try:** raise the payload slider to 2.5 t: the boom cap pressure during the lift rises to about 170 bar, and the
section flow stays within 5 % (the compensator). Lower the bulk modulus to 0.6 GPa: the chamber stiffness halves,
and the ringing drops by √2, to about 1.8 Hz. Set the LS margin to 15 bar: the boom section gets only about
100 l/min instead of 145, because the margin no longer covers the 10 bar compensator plus the spool drop.
@@ figures excavator-dig-cycle
{
  "diagram": {"kind": "diagram", "model": "excavator-dig-cycle"},
  "scene": {"kind": "scene", "model": "excavator-dig-cycle", "t": 9.0, "zoom": 2},
  "tip": {
    "kind": "plot", "model": "excavator-dig-cycle", "width": 700,
    "rows": [{"ylabel": "tip y [m]", "x": "PoseTip/g[2]", "xlabel": "tip x [m]", "equal": true, "series": [{"signal": "PoseTip/g[3]", "label": "bucket tip"}]}], "row_height": 4.5
  },
  "run": {
    "kind": "plot", "model": "excavator-dig-cycle", "xlim": [0, 16.5],
    "rows": [
      {"ylabel": "joystick", "series": [{"signal": "BoomSpool/y", "label": "boom"}, {"signal": "ArmSpool/y", "label": "arm"}, {"signal": "BucketSpool/y", "label": "bucket"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "soil", "series": [{"signal": "Soil/Fcut", "label": "cutting force [10 kN]", "scale": 1e-4}, {"signal": "Soil/depth", "label": "depth [m]"}, {"signal": "Soil/fillr", "label": "fill"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "pressure [bar]", "series": [{"signal": "Vpump/p", "label": "pump", "scale": 1e-5}, {"signal": "BoomCyl/pA", "label": "boom cap", "scale": 1e-5}, {"signal": "ArmCyl/pA", "label": "arm cap", "scale": 1e-5}, {"signal": "BucketCyl/pA", "label": "bucket cap", "scale": 1e-5}], "legend": true, "legend_loc": "right"},
      {"ylabel": "LS margin [bar]", "series": [{"signal": "Pump/margin", "label": "pump − LS line", "scale": 1e-5}], "hlines": [{"y": 25, "label": "setting 25 bar"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "power [kW]", "series": [{"signal": "Pump/P_in", "label": "engine shaft", "scale": 0.001}, {"signal": "Pcyl/y", "label": "cylinders", "scale": 0.001}], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page excavator-dig-cycle overview - | What you're looking at
# A dig cycle

**Scenario.** A scripted operator ([BoomStick](block:BoomStick), [ArmStick](block:ArmStick),
[BucketStick](block:BucketStick), linear ramps of 0.25 s) runs one cycle in 16.5 s. The spool commands
(positive extends the cylinder):

| phase | time [s] | boom | arm | bucket |
| --- | --- | --- | --- | --- |
| penetrate | 0.5 – 2.0 | −0.15 | 0 | 0.25 |
| drag | 2.0 – 5.0 | −0.03 | 0.5 | 0.22 |
| curl | 5.0 – 6.5 | 0.13 | 0.33 | 0.38 |
| lift | 6.5 – 9.5 | 0.9 | −0.06 | 0 |
| arm out | 9.5 – 11.0 | 0.15 | −0.65 | 0 |
| dump | 11.0 – 12.8 | 0 | 0 | −0.85 |
| return | 12.8 – 15.3 | −0.17 | 0.02 | 0.38 |

The global `u_scale` scales all three sticks ([BoomCmd](block:BoomCmd) and the others).

![The bucket tip path: into the soil, drag, curl, up and out, back to the start|600](@fig:tip)

![Joysticks, soil, pressures, LS margin and power|900](@fig:run)

**Expected outcome** (checked by `expected.json`):

| quantity | bond graph | check |
| --- | --- | --- |
| LS margin | 22.6 – 27.0 bar | 20 – 32 bar |
| main relief flow | < 2·10⁻⁹ m³/s | closed |
| bucket fill after the curl / after the dump | 0.75 / 0.004 | > 0.6 / < 0.05 |
| deepest cut, peak cutting force | 0.43 m, 22.2 kN | < 0.6 m |
| engine energy / cylinder work ratio | 0.57 MJ / 0.27 | < 0.7 MJ |
| port-power ledger | closes | |

The margin dips below its setting when a load pressure steps up and the LS line follows through its shuttle: the
largest dip (22.6 bar) is at 9.7 s, when the arm swings out with the full bucket and the boom cap pressure peaks at
290 bar. The margin never runs out, so every section gets its flow.

![The front at 9 s: lifting the full bucket|600](@fig:scene)

![The model canvas|900](@fig:diagram)

**Blocks.** [Soil](block:Soil) (`SoilCutting2D`) at the bucket body; the three sections with their
compensators ([BoomComp](block:BoomComp), [ArmComp](block:ArmComp), [BucketComp](block:BucketComp)), spools
([BoomValve](block:BoomValve)…), LS edges ([BoomLSEdge](block:BoomLSEdge)…) and shuttles
([BoomShuttle](block:BoomShuttle)…); the supply with [Pump](block:Pump), [Relief](block:Relief) and
[Bleed](block:Bleed).

**Try:** set the soil cohesion to 50 kPa (stiff clay): the peak cutting force doubles to 44 kN, the cut stays
shallower (0.33 m) and the bucket fills only to 0.64. Raise the joystick scale to 1.2: the operator digs deeper
(0.52 m), the bucket fills to 0.83 and the cycle costs 0.72 MJ. Compare the engine energy with [excavator-no-ls](model:excavator-no-ls).
@@ figures excavator-no-ls
{
  "run": {
    "kind": "plot", "model": "excavator-no-ls", "xlim": [0, 16.5],
    "rows": [
      {"ylabel": "pressure [bar]", "series": [{"signal": "Vpump/p", "label": "pump", "scale": 1e-5}, {"signal": "BoomCyl/pA", "label": "boom cap", "scale": 1e-5}, {"signal": "ArmCyl/pA", "label": "arm cap", "scale": 1e-5}, {"signal": "BucketCyl/pA", "label": "bucket cap", "scale": 1e-5}], "legend": true, "legend_loc": "right"},
      {"ylabel": "power [kW]", "series": [{"signal": "Pump/P_in", "label": "engine shaft", "scale": 0.001}, {"signal": "Pcyl/y", "label": "cylinders", "scale": 0.001}], "legend": true, "legend_loc": "right"},
      {"ylabel": "energy [MJ]", "series": [{"signal": "Ein/y", "label": "engine", "scale": 1e-6}, {"signal": "Ecyl/y", "label": "cylinders (net)", "scale": 1e-6}], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page excavator-no-ls overview - | What you're looking at
# The same cycle without load sensing

**Scenario.** The dig cycle of [excavator-dig-cycle](model:excavator-dig-cycle), with the same operator and the
same soil, on a **constant-pressure supply**: the pump's LS port sees the tank and the margin is set to 280 bar,
so [Pump](block:Pump) holds about 281 bar in the pump line whatever the load. There is no LS line and no shuttle
network; the compensators and spools throttle the difference between 281 bar and the load pressure.

![Pressures, power and energy|900](@fig:run)

**Expected outcome:**

| quantity | no-LS | LS (dig-cycle) |
| --- | --- | --- |
| pump pressure | ≥ 201 bar (281 bar between moves) | 25 bar above the highest load |
| engine power at stand-by | 24.9 kW | 1.6 kW |
| engine energy for the cycle | 1.52 MJ | 0.57 MJ |
| cylinder work / engine energy | 0.10 | 0.27 |

The motion is almost the same, because the compensated sections deliver the same flow; only the energy changes.
The stand-by power is high because the pump friction torque grows with the pressure even at zero stroke.

**Try:** lower the constant pressure (the global `dp_ls`) to 200 bar: the cycle still runs (the bucket fills to
0.72), and the engine energy drops to 1.15 MJ, still twice that of load sensing, because the pump pressure has to
cover the highest load of the cycle all the time.
