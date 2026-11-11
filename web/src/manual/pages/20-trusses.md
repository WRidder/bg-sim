# Trusses and member failure

A truss is a frame of straight bars joined by pins. The bars carry only an axial force, tension or compression, and they can fail: a bar breaks when the tension passes its strength, and a strut gives way when the compression passes its buckling load. The **Planar** category has the blocks for both ways of building one: bar by bar, or the whole truss in one block.

## Blocks

| Block | Ports and signals | Use |
| --- | --- | --- |
| `PinNode2D` | port `p`; output `g` (pose) | a joint of the truss: a point mass, free, pinned or on a roller |
| `Bar2D` | ports `a`, `b`; inputs `ga`, `gb` | one bar between two pin nodes |
| `Truss2D` | inputs `Fx`, `Fy`; outputs `x`, `y`, `xd`, `yd` | a whole truss from its node coordinates and connectivity |
| `MovingLoad2D` | input `x`; outputs `Fx`, `Fy` | a point load travelling along the deck of a `Truss2D` |
| `DeckContact2D` | port `p` (to a body); deck signals in, node forces out | wheels of a vehicle rolling on the deck of a `Truss2D` |

`PointMass2D` and `AxialBar2D` are the cores of `PinNode2D` and `Bar2D`. Use the composite blocks in models.

## Bar by bar: `PinNode2D` and `Bar2D`

The port of a `PinNode2D` is its 1-junction, and so are the ends of a `Bar2D`. Bond the bars to the nodes, as many as you need. These are bonds between two junctions, which are not checked, so either direction works. Wire each node's `g` to the bar inputs `ga` (end `a`) and `gb` (end `b`), so the bar knows where its ends are.

`PinNode2D` has the constant `support`: `free`, `pinned` (x and y fixed) or `roller` (y fixed, x free). The parameter `m` is the node mass. A bar's own mass is not in the bar: add half of `rho A L` of every bar to the mass of each of its nodes. The output `R` is the reaction of the support.

To push or pull a node, bond an `ExternalWrenchPlanar` **to** the node (from the wrench to the node). Its inputs are the force on the node.

## The whole truss: `Truss2D`

`Truss2D` holds `nn` nodes and `nb` bars in one block. The structure is given by constants, so it fixes the array sizes:

| Constant | Meaning |
| --- | --- |
| `nn`, `nb` | number of nodes and bars |
| `conn` | an `nb` × 2 matrix: bar k runs from node `conn[k, 1]` to node `conn[k, 2]` |
| `fix` | an `nn` × 2 matrix: `fix[i, 1]` and `fix[i, 2]` are 1 when the x or y motion of node i is fixed. `[1 1]` is pinned, `[0 1]` a roller, `[0 0]` free |

| Parameter | Unit | Meaning |
| --- | --- | --- |
| `xy` | m | an `nn` × 2 matrix of the node positions, row i = (x, y) |
| `A`, `I` | m², m⁴ | area and second moment of area of each bar (vectors of length `nb`) |
| `mn` | kg | extra mass at each node, for example the deck |
| `E`, `rho`, `fy` | Pa, kg/m³, Pa | Young's modulus, density and tensile strength |
| `K` | 1 | effective length factor of the buckling load (1 for pinned ends) |
| `beta` | s | stiffness-proportional damping of the bars |
| `g0` | m/s² | gravity along world −y |

Each node carries its `mn` plus half the mass of every bar that meets it. The inputs `Fx` and `Fy` are external forces on the nodes. The outputs give the node positions `x`, `y` and velocities `xd`, `yd`, and per bar the force `N`, the utilisation `util`, the flag `failed`, the length `L`, the strength `Ft` and the buckling load `Pcr`. They also give the support reactions `Rx`, `Ry`, the number of failed bars `nfail`, and the energies `Ek`, `Ee`, `Eg`, `Edis`, `Elost` and `Wext`.

Write matrices with rows separated by `;`, for example `[1 2; 2 3; 1 3]`.

## Bar force and failure

Both `Bar2D` and `Truss2D` use the same bar. The length comes from the current node positions, so large rotations are exact. The rest length is the distance between the nodes at the start: a truss starts unstressed in its drawn shape.

- **Force:** `N = E A / L0 (L − L0) + E A beta / L0 · dL/dt`, positive in tension.
- **Tension failure:** the bar breaks when `N > Ft = fy A`.
- **Buckling:** a strut fails when `−N > Pcr = π² E I / (K L0)²` (Euler).
- **After failure** the bar carries no force for the rest of the run. Compression failure is treated the same way: the post-buckling load of a real strut is not modelled.
- **Utilisation:** `util = N / Ft` in tension and `N / Pcr` in compression. It reaches +1 or −1 when the bar fails.
- **Energy:** the strain energy a bar held when it failed is booked in `Elost`. `Ebal = Ek + Ee + Eg + Edis + Elost − Wext` stays constant during the run, through every failure, which checks the integration.

Failure is an event: the solver stops on the exact instant the force crosses the limit. Set `event_limit` in the run settings high enough for a run in which many bars fail.

To scale the strength of every bar with one [global parameter](page:parameters) `strength`, set `fy` to `3.55e8*strength` and `K` to `1/sqrt(strength)`. The tensile strength and every buckling load then scale with `strength`, and the stiffness does not change. To weaken one strut only, write its entry of `I` as an expression, for example `1.5e-5*slender`.

## Loads on the deck

Put the deck nodes first in `Truss2D`, numbered from left to right: nodes 1 to `nd` form the road surface.

- `MovingLoad2D` (constants `nn`, `nd`) applies a load `P` that starts at `s0` and moves at `v`. Two neighbouring deck nodes share the load by linear shape functions. Wire the truss's `x` to its input and its `Fx`, `Fy` to the truss.
- `DeckContact2D` (constants `nn`, `nd`, `nw`) puts `nw` wheels of a planar body on the deck. The wheels sit at (`rx`, `ry`) in the body frame with radius `r`. Each tyre is a spring `k` with damping `c`, and the damping grows with the deflection. A wheel is carried by one deck panel at a time, the one it presses into most, and it rolls over a deck node on the node itself, so the tyre force has no jumps where the deck bends. The input `Fd` is a drive force along the deck, shared by the wheels in contact. The block's port `p` is `in`: bond the body to it (`Body -> DeckContact2D.p`), feed it the body pose `g` and the truss outputs `x`, `y`, `xd`, `yd`, and wire its `Fx`, `Fy` to the truss.

## In the 3D view

Draw each bar as a cylinder or box in the scene and bind it with a **segment** binding (see [Running and plotting](page:running-and-plotting)). Use the bar's end-node positions, `Truss/x[a]`, `Truss/y[a]`, `Truss/x[b]`, `Truss/y[b]`, and the flag `Truss/failed[k]` as **broken**. Add a **color** binding on `Truss/util[k]` with the `coolwarm` colormap and the range −1 to 1. Bars under compression then turn blue, bars under tension red, and the full colour is the failure load. The 3D view draws positions at true scale. In the scene file, put every bar between its two nodes of the undeformed truss, so the bridge shows before the first run.

## Example

**bridge** has two bridges, each with a lorry on compliant tyres.

- A 30 m Warren truss. It shows the member forces against the method of joints, the first bending frequency against an eigenvalue analysis, a strut that buckles at the Euler load, and an undersized diagonal that snaps when the lorry crosses too fast or too heavy (`bridge-failure`). The truss is statically determinate, so one failed bar brings it down.
- `bridge-pier`: a 2 × 24 m continuous truss on a steel column in the river, with X-braced panels next to the pier. It is statically indeterminate, so its reference numbers come from the stiffness method. A too slender diagonal next to the pier buckles under an overloaded lorry, its X-partner takes over the load, and the bridge stays up. With weaker members the bars next to it fail, the pier column buckles, and the bridge collapses.

In the lorry models the roller bearing sits on a seat of finite length: the project block `RollerSeat` carries the roller node, which is free in the truss (`fix` [0 0]). The seat pushes the node up but never pulls, the node rolls freely along it, and when it has rolled 0.3 m to either edge an event releases it for good: that end of the truss falls. In `bridge-failure` the folding truss pulls the roller off its seat. In the 3D view the seat turns red when the roller has rolled off.

The dashboards of `bridge-crossing`, `bridge-failure` and `bridge-pier` have sliders for the member strength (the global `strength` scales `fy` and, through `K`, every buckling load), the lorry's mass and its speed. `bridge-pier` also has a slider for the slender diagonal. A gauge shows the peak utilisation of the run. Indicators show when a member has failed, when the roller has rolled off its seat and when the bridge has collapsed. Move a slider until a member fails, then move it back to see where the bridge holds again.
