# Running and plotting

## Run a simulation

Click **Run** in the top bar, or press `Ctrl+Enter`. **Stop** ends a run early.

Next to the buttons are the run settings. They are saved with the model. Press `Enter` to apply a value and `Esc` to undo it; an invalid value is marked and not applied.

| Field | Meaning |
| --- | --- |
| **t_end** | end time in seconds |
| **solver** | `auto`, `Rodas5P`, `Rodas5`, `Rosenbrock23`, `Tsit5` or `Vern7` |
| **tol** | relative tolerance |

- The status next to the settings shows the progress (`t / t_end`), then `done in …`, `cancelled` or `failed: …`.
- The **worker status** pill at the right shows whether the simulation worker is starting, warming up, ready or has crashed. Hover it for details. The first run after a start takes longer while the worker warms up.

## The bottom dock

The panel below the editor has the tabs **Plots**, **Auto Plot**, **3D View**, **Diagnostics**, **Debug**, **Signals** and **Log**.

## Plot signals

Every signal of a run is recorded, so you can plot any signal after the run, without adding sinks. There are several ways to add one:

- **From the canvas:** right-click a bond and choose **Plot effort**, **Plot flow** or **Plot power**, or right-click a block and choose **Plot all outputs**.
- **From the Signals tab:** search by name, path or unit. Double-click a signal or click its **+** to add it, or drag it onto a plot panel. **Add to** picks the target panel; **Plot all** adds every listed signal.
- **From the inspector:** right-click a signal in the block's signal list.

Signals go to the **Active** panel, which you choose in the plot toolbar.

### Work with plots

- **+ Panel** adds a panel. Type in a panel's title to rename it. A panel has at most two y axes; signals with a third unit go to a new panel.
- Drag horizontally to zoom in on a time range, use the mouse wheel to zoom at the pointer, and double-click (or **Reset zoom**) to show the whole run. The cursor and its values are shared by all panels.
- During a run the plots update live and follow the latest time. Zooming pauses the following; **Follow live** resumes it.
- **Pin run** keeps the current run. Start another run to compare: the pinned run shows as dashed lines.
- **CSV** downloads the plotted signals. The download runs as a [background task](page:background-tasks).
- **Detach** opens the plots in a separate browser window.

## Auto Plot

While the **Auto Plot** tab is open, it plots every recorded signal of the selected block, subsystem or connection. Choose a **Layout**: all signals in one panel, one signal per panel, or grouped by unit.

## 3D view

Models with a 3D scene show it in the **3D View** tab. The scene follows the run through bindings between scene objects and signals.

- Drag to orbit, right-drag to pan, scroll to zoom.
- The toolbar has **Isometric**, **Top**, **Front** and **Side** views, an **Orthographic projection** toggle, **Fit the scene in the view**, **Full screen** (with the playback bar; `Esc` exits) and **Detach** (a separate window).
- The playback bar replays the run: **Play**/**Pause** (`Space` when the 3D view has focus), **Rewind to start**, **Speed** (0.1× to 4×), **Loop** and a time slider.
- **Bindings** opens the bindings table. Each row binds a scene object's property (position, pose, scale, colour, visibility, deformation, mode shapes or segment) to a signal, with a gain and an offset. **Add binding** adds a row.

### Bars between two points (segment bindings)

A **segment** binding draws a box or cylinder as a bar between two moving points, for example a truss member between its two nodes. The visual is placed midway between the points, turned along the line between them and stretched to their distance. Its cross-section keeps its size.

1. In **Bindings**, pick the property **segment** and a box or cylinder as target.
2. Pick the **end points**: `planar` takes four signals (u and v of end A, then of end B), `spatial` takes six (x, y, z of A, then of B). The positions are in m, in the world frame of the scene.
3. For planar points, set the **plane**: `xz` (the default) puts (u, v) at world (u, depth, v), so the model's y axis points up. `xy` and `yz` are the other planes. **depth** is the third coordinate, for example the y of one of two parallel trusses.
4. **axis** is the visual's direction that runs from A to B. By default it is a cylinder's own axis (+z) and a box's +x. A cylinder can only stretch along its own axis.
5. **broken** (optional) is a signal that marks a failed bar when it is above 0.5. A broken bar is drawn **snapped** (two short stubs that hang from the end points, with a gap between them) or **hidden**.

**Gain** and **offset** apply to every coordinate, not to the depth. The binding table reports a sphere, a mesh or a cylinder stretched across its axis as E301, a count other than 4 or 6 as E304, and a coordinate that is not a length as E303.

### Elastic beams (deformation bindings)

A box or cylinder in the scene can bend and twist with the run. A flexible beam block gives its rigid motion as a pose (bind it to the link, as for a rigid body) and its elastic motion as modal coordinates: `eta_y[i]` and `eta_z[i]` for bending (in m) and `eta_t[i]` for torsion (in rad). A **deformation** binding draws them on a visual.

1. In **Bindings**, pick the property **deformation** and a box or cylinder as target. Spheres cannot bend; a mesh bends through a **mode-shapes** binding instead (below).
2. Pick the **family**: `bending-y` (deflection along the beam's y axis), `bending-z` (along its z axis) or `torsion` (twist about the beam axis).
3. Pick the **basis**, which must match the block: `clamped-free` (a cantilever, fixed at end A) or `free-free` (both ends free). Torsion also offers `linear` (see below).
4. Set the **beam axis**: the direction in the shape from end A to end B. End A is the face on the other side. A cylinder runs along its own z axis, so it takes `+z` or `-z`. In the table you can also set the beam's **y** axis (default `+y`) and its length **L** (empty means the shape's length).
5. Pick one signal per mode, in mode order (up to three: **+ mode**, **− mode**). **Gain** multiplies every coordinate, for example 0.001 for coordinates in mm.

Add one binding per family. A beam can bend in y and z and twist at the same time, and all bindings of one visual must give the same beam axis. While torsion is bound, the beam shows dark longitudinal stripes: a dark band on each side of a box, four lines on a cylinder. They wind around the beam as it twists, so the twist is visible. For a bending binding, **strain** colours the beam by the bending strain of its outer fibres along its length, with a colormap and range (for example 0 to 0.001). The strain colours always come from the true deformation.

#### A lumped torsion spring: the linear basis

A shaft modelled as one spring between two inertias (a `TorsionSpring`, or a C on a 1-junction in a bond graph) has no modes, only its twist: the angle of the load end minus the angle of the drive end. Its twist is linear along the shaft. To draw such a shaft:

- put the shaft's cylinder in the link of the drive-side inertia (or bind a joint to that inertia's angle), so the shaft turns with it;
- add a deformation binding with family `torsion`, basis **`linear`** and **one** signal, the twist in rad. The section at distance s from end A turns by s/L of it, so end B sits exactly at the load's angle;
- if the model's twist is the drive-side minus the load-side angle (as `phi` of `TorsionSpring` is, a minus b), set the gain to −1.

A chain of lumped springs (several C's with small inertias between them) is one cylinder per segment, each on the link of its upstream inertia with its own spring's twist. The `drivetrain`, `drivetrain-kalman` and `drivetrain-position` examples draw their shafts this way. The linear basis is torsion only, with exactly one signal; a bending family or a second signal on it is E301 or E304.

#### Exaggeration

Real deflections are usually too small to see. Whenever a model has deformation or mode-shapes bindings, the top-left corner of the view shows **Deformation** with an exaggeration factor of ×1 (true scale), ×10, ×100 or ×1000. Every factor above ×1 is marked **exaggerated**, so a screenshot cannot pass off the drawing as real motion. The factor you pick is saved per model in this browser, not in the model, and the detached window and full screen use it too.

A model can name the factor its view opens with: `"exaggeration": 10` in its `scene` (next to `file`; 1, 10, 100 or 1000). It applies while this browser has no choice of its own for the model; picking the model's own factor again drops the stored choice. On a round shaft a twist only shows as the stripes winding round it, by radius × angle, so even 0.1 rad on a thin rod needs ×10: `drivetrain` and `drivetrain-position` open at ×10, and `drivetrain-kalman`, whose shaft segments twist by a few mrad, at ×1000. A torsion exaggeration only winds the stripes and never distorts the shaft, so a large factor is harmless. Only the deformation is exaggerated: joints and poses always move by their true values, so with an exaggerated twist the stripes at the end of a shaft run ahead of the marker of the disc it meets.

The binding table reports a sphere or mesh, a cylinder bent across its own axis, two bindings of one family, beam axes that differ, or the linear basis on a bending family as E301. It reports a wrong number of modes (or more than one signal on the linear basis) as E304, and a unit that is not m for bending or rad for torsion as E303.

### Flexible bodies from a mesh (mode-shapes bindings)

A part reduced from a finite element mesh (see [Flexible bodies](page:flexible-bodies)) is drawn from the GLB file the reduction tool writes. That GLB holds the part's surface and one morph target per elastic mode: the shape of the mode for one unit of its modal coordinate. Store it in the project's `meshes/` folder and reference it as a mesh visual in the scene, for example `<mesh><uri>bracket.glb</uri></mesh>`. The flexible body block records its frame as `pose` and its modal coordinates as `eta[1]` to `eta[n]` (in m).

1. Bind the block's `pose` to the link that holds the mesh, as for a rigid body.
2. In **Bindings**, pick the property **mode-shapes** and the mesh as target. Only mesh visuals are offered.
3. Fill the signals: **Fill eta[1..n] from…** lists the blocks that record `eta[i]` and fills `eta[1]` to `eta[n]` in mode order in one step, up to the number of mode shapes in the mesh. You can also pick them one by one (**+ mode**, **− mode**). The table shows how many mode shapes the mesh has.
4. **Gain** multiplies every coordinate, for example 0.001 for coordinates in mm. A mode-shapes binding has no offset.

The view moves every vertex by the sum of the mode shapes, each times its coordinate, the gain and the **Deformation** exaggeration factor of the view (×1 is true scale; a model can open at a larger factor with `"exaggeration"` in its `scene`, see above). A mesh can take one mode-shapes binding. The binding table reports a target that is no mesh, a mesh without morph targets, or a second mode-shapes binding of one mesh as E301. It reports more signals than the mesh has mode shapes (or more than 64) as E304, and a coordinate whose unit is not m as E303.
