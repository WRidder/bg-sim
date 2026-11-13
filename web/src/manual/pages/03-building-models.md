# Building models

Models are drawn on the canvas of the **Diagram** tab.

## Blocks

- **Add:** drag a block from the [library](page:projects-and-library) onto the canvas.
- **Select:** click a block, or drag on empty canvas for a selection box.
- **Edit:** the inspector on the right shows the selected block: name, parameters (with units, defaults and limits), constants, start values and ports. Press `Enter` to apply a value, `Esc` to undo the typing. Values can be expressions and can use [global parameters](page:parameters).
- **Arrange:** `R` rotates, `F` flips, `Del` deletes, `Ctrl+C` / `Ctrl+X` / `Ctrl+V` copy, cut and paste (see **Copy and paste** below). Right-click a block for the same actions, and for **Show source**, which opens the block's source in the Code tab.
- **Undo:** `Ctrl+Z`, redo `Ctrl+Y`.
- **Navigate:** the mouse wheel zooms. Pan with the middle mouse button, `Space`+drag or the arrow keys. **Fit view** in the canvas toolbar fits the whole diagram.
- **Find a block:** click it in the **Model tree** (left panel). The Diagram tab opens on the diagram that holds the block, also inside a subsystem, and the block is selected and centred. A `block:` link in the [docs](page:code-and-docs) does the same.

## Ports and connections

| Port glyph | Kind | Connects to |
| --- | --- | --- |
| filled square | power port | one other power port of the same domain (a **bond**) |
| filled triangle | signal output | any number of signal inputs |
| hollow triangle | signal input | exactly one signal output |

- **Connect:** drag from one port to another. Compatible ports are highlighted; an invalid target shows why it is refused. `Ctrl`+drag starts from the port of a block nearest to the pointer.
- **Release on empty canvas** to get a filterable list of compatible blocks; the one you pick is added and connected.
- **Bond direction:** a bond has a direction, shown by its half arrow. It matters, and most ports fix it for you: see **Bond direction and port orientation** below. Right-click a bond and choose **Reverse bond direction** to flip it where that is allowed.
- **Routing:** right-click a connection for **Add routing vertex** and **Clear routing vertices**.
- **Crossing kinds:** a signal cannot drive a power port directly. Use a modulated source (`MSe`, `MSf`) or a sensor. Different physical domains connect through a converter (`TF`, `GY`, a DC motor, …). **Thermal** ports carry temperature and heat flow, not power, so they never connect to another domain; losses reach them through `RS` or a heated component (see [Thermal domain](page:thermal-domain)).
- **Junctions:** the **Junctions** category has the 0-junction (equal efforts, flows sum to zero) and the 1-junction (equal flows, efforts sum to zero).

Units are checked: ports with the same dimension but a different unit connect with a conversion factor shown on the wire; different dimensions are refused.

## Bond direction and port orientation

A bond has a direction, and the direction is part of the model. The half arrow points the way positive power flows. Port variables count positive into the block, so a bond from X to Y gives Y the bond's flow and X its negative. On a 1-junction, a port at the head of the arrow sees the junction's flow, a port at the tail sees minus that flow, and its effort enters the junction's sum with the opposite sign. Drawing one bond the wrong way round therefore reverses the sign of that element's flow and effort.

To keep you from drawing it wrong, power ports declare an **orientation**, the direction their equations assume:

- `in`: the bond ends at the port (the arrow points into the block).
- `out`: the bond starts at the port.
- `through`: a pass-through two-port such as a mount or a `TF`. Of its two bonds, one arrives and the other leaves, and it does not matter which.

The port tooltip and the **Ports** list of the block inspector show the orientation. A port that shows "orientation not declared" cannot be bonded: its block has not said which way it works (see [Code and Docs tabs](page:code-and-docs) to declare it).

**The editor orients bonds for you.** A new bond takes its direction from the two ports, whichever end you start dragging from. Two `in` ports, or two `out` ports, cannot be bonded directly: the editor says "put a junction in between", because a junction takes one bond from each. Pasting and duplicating keep the stored direction of a bond.

**When Reverse bond direction is disabled.** A bond at an `in` or `out` port, or at one port of a pass-through pair whose other bond already takes the role, cannot be reversed. The menu item is greyed out, and its tooltip (and the bond inspector) names the port and the direction it needs, for example "the port `C1.p` is declared `in`: a bond must end there". Put a junction in between if you need the other direction.

**Bonds between junctions are free.** A bond between two junctions is never checked. Reversing a bond between two junctions of the same kind (1 and 1, or 0 and 0) only changes its own arrow. Reversing a bond between a 0-junction and a 1-junction changes the model: it reverses the reference direction of everything behind that bond, so the signs of relative flows and displacements, and the results that show them, change.

### The convention

| Element | Orientation | How to bond it |
| --- | --- | --- |
| Storage, dissipation, detectors and sensors (`C`, `I`, `R`, `MR`, `De`, `Df`, the sensors, Coriolis, planar and spatial forms) | `in` | junction to element |
| Bond-graph sources (`Se`, `Sf`, `MSe`, `MSf`, gravity, external wrench, planar and spatial forms) | `out` | source to junction. `Sf` and `MSf` impose their value on the junction they point at |
| Transformers, gyrators, mounts (`TF`, `GY`, `MTF`, `MGY`, `FixedTransform*`, `JointTransform*`), `PowerSensor` | `through` | one bond in, one bond out, either way round |
| Contacts (`ContactPoint`, `RollingDisk`, `Tyre`, `MovingPlaneContact`, ...) | `in` | body to contact, or body to mount side `b` and mount side `a` to the contact |
| Joints (`Revolute3D`, `Free3D`, ...) | `parent` `in`, `child` `out`, `drive` `in` | parent body to `parent`, `child` to the child body, source or junction to `drive` |
| Iconic components (electrical, rotation, translation, hydraulic, thermal, drives, motion, converters) | `in` | junction to port. The port then behaves exactly as if it were wired to that junction |

Two element ports are never bonded to each other directly. Two iconic ports are joined by a wire, or by a junction with a bond into each. A dissipator or a sensor on a joint drive goes through a junction too: `drive <- 1 -> R`.

### Bodies and mounts

A body is a 1-junction whose flow is the body's true twist. The library `RigidBody2D` and `RigidBody3D` have such a junction on their port `p`, and a body you build from a 1-junction, an `I`, a Coriolis element and gravity behaves the same. Every block attached to the body therefore sees the body's twist at its port. Attach each one by the convention above:

- a source: `Source -> Body`, or `Source -> Mount.a` and `Mount.b -> Body`;
- a contact: `Body -> Contact`, or `Body -> Mount.b` and `Mount.a -> Contact`;
- a joint: `ParentBody -> Joint.parent` and `Joint.child -> ChildBody`.

A mount keeps its side `b` on the body side. Do not turn it round (side `a` toward the body): the model then needs the inverse of the mount's transform, which is badly conditioned and can fail at some rotations.

### E114: a bond against a declared orientation

The model check reports [E114](page:diagnostics) for each bond that breaks a declared orientation. The message names the bond, the port and the orientation it declares. The hint says what to do:

- **Reverse the bond.** The bond starts at an `in` port or ends at an `out` port. Right-click it and choose **Reverse bond direction**. Reversing a bond on a 1-junction changes the sign of that port's flow and effort, so when you fix an older model look at the element: a linear `C`, `I` or `R` is not affected, a source needs its value negated, and a start value of a storage element changes sign.
- **Put a junction in between.** The bond joins two `in` ports or two `out` ports. Add a 1-junction (or a 0-junction) and bond each port to it in the direction the port wants.
- **Turn one bond of a pair.** Both bonds of a `through` pair arrive, or both leave. Reverse the one whose other end is free.
- **Declare the orientation.** The bond reaches a port that declares no orientation. For a block of your own, add `@orientation` to it (see [Code and Docs tabs](page:code-and-docs)).

## Legend and grid

The canvas toolbar has **Show legend** (domain colours and port glyphs, bottom left), **Show grid** and **Snap to grid**. Causal strokes on bonds appear after the model has been checked.

| Domain | Colour | Port letter | Effort | Flow |
| --- | --- | --- | --- | --- |
| Electrical | blue | E | voltage [V] | current [A] |
| Translation | green | T | force [N] | velocity [m/s] |
| Rotation | violet | R | torque [N·m] | angular velocity [rad/s] |
| Hydraulic | cyan | H | pressure [Pa] | volume flow [m³/s] |
| Thermal | rose | Th | temperature [K] | heat flow [W] |
| Generic | grey | G | adopted from the bond | adopted from the bond |
| Mechanics (2D and 3D multibond) | brown | P, S | wrench | twist |

Colour is never the only cue: hover a port to see its domain letter.

A Generic port takes the domain of the bonds around it. A Generic two-port such as `PowerSensor` passes a domain through: a bond graph island that has only Generic ports takes the domain of the island on the other side of the sensor. When the two sides already have different domains, the block reports E102.

## Subsystems

- **Create:** select blocks and click **⧉ Subsystem** in the canvas toolbar. The selected blocks and the connections between them move into the subsystem.
- **Enter:** double-click the subsystem, on the canvas or in the Model tree (a single click in the tree only centres it). **Leave:** `Esc`, **↑ Up**, or a crumb in the path bar above the canvas.
- **Port terminals:** inside a subsystem, each port of the subsystem is a terminal. To add a port, drag an internal port onto the dashed **+ input**, **+ output** or **+ power** terminal, or right-click a port of an internal block and choose **Expose as subsystem port**. Right-click a terminal to **Rename port…**, **Delete port** or **Show outside connection**.
- A subsystem can be exported on its own as an FMU (see [Export](page:export)).
- **Reuse:** a subsystem that the model needs several times can be made a library subsystem with **Make reusable…** in the inspector. The node then is an instance, more instances come from the **Project** category, and an edit inside any instance changes them all (see [Projects and the library](page:projects-and-library)).

## Sticky notes

- Press `N` to add a note at the pointer, or right-click the empty canvas and choose **Add note (N)**.
- Double-click a note to edit it. The text is Markdown with math and links (`page:`, `block:`, `signal:`), as in the [Docs tab](page:code-and-docs).
- Right-click a note to change its colour or delete it.

## Shapes

Background shapes group and annotate parts of a diagram. They are drawn behind blocks.

- **Add:** right-click the empty canvas and choose **Add rectangle**, **Add rounded rectangle**, **Add ellipse**, **Add line** or **Add arrow**.
- **From the library:** open the **Shapes** category at the bottom of the library. Drag a shape onto the canvas to place it at the drop point, or click it (or press `Enter`) to add it in the middle of the canvas. The new shape is selected, and one **Undo** removes it.
- **Style:** select a shape to set fill, line width, line style, opacity and a label in the inspector.
- **Label position:** under the label, pick one of nine places on the 3×3 grid: a corner, the middle of an edge, or the centre. Lines and arrows always centre their label.
- **Order:** right-click a shape for **Bring to front**, **Bring forward**, **Send backward** and **Send to back**.
- **Lock:** **Lock** in the shape's menu (or **Locked** in the inspector) prevents moving, resizing and deleting it. **Unlock** to change it again.
- **Duplicate** copies the shape.

## Copy and paste

Select blocks, sticky notes and shapes, press `Ctrl+C` (or `Ctrl+X` to cut), and press `Ctrl+V` where they should go. Right-click a block for **Copy**, and right-click the empty canvas for **Paste**.

- **What is copied:** the selected blocks with everything inside a subsystem, the connections between selected blocks, and the selected notes and shapes. A connection to a block that is not selected stays behind.
- **Where it lands:** at the mouse pointer when it is over the canvas, otherwise in the middle of the visible canvas. The pasted elements keep their layout. Pasted back into the diagram they came from with the pointer outside the canvas, they appear slightly offset, and pasting again offsets them further.
- **Names and undo:** pasted blocks get a free name in the target diagram (`Gain` becomes `Gain2`). The pasted elements are selected, and one **Undo** removes the whole paste, including any global parameters it added.
- **Inside a subsystem:** the paste goes into the diagram that is open, at any subsystem level.

### Between models, windows and projects

The copy goes to the system clipboard, so you can paste it into another model, another browser window or tab, or another project on the same bg-sim server. Copying text in a field, in the code editor or in the docs works as usual: the canvas only handles `Ctrl+C` and `Ctrl+V` when no text field has the focus.

When the target is another model or project, the paste brings along what the copied elements need:

| Copied elements use | Is brought along as |
| --- | --- |
| a project library block (`project:<Name>`), also inside a subsystem or used by another library block | `library/<Name>.jl` in the target project |
| a global parameter in a value or start value | a global parameter of the target model, with every global it depends on |
| a CSV file of a CsvSource block | the same file in the target project's `data/` folder |
| the reduced-model file (`.modal.json`) of a ModalBody3D block | the same file in the target project's `data/` folder (copy the mode-shape GLB into `meshes/` yourself) |
| an image in a sticky note's Markdown | the image in the target model's docs |

A subsystem image is part of the block, so it always comes along.

**Conflicts:** if the target already has a library block, global parameter or data file with the same name but different content, one dialog lists them. Choose for each:

- **Use this project's / this model's …** (the default): the paste uses the target's definition and changes nothing in it.
- **Import as `<Name2>`:** the copy is added under a free name, and the pasted blocks and values are changed to use it.
- **Convert the pasted blocks to inline** (library blocks only): the pasted blocks carry the block's code themselves.

**Cancel** pastes nothing. Library blocks and data files are written to the project before the elements are pasted. **Undo** removes the pasted elements and globals but not those files.

After the paste, a notice at the bottom of the canvas lists what was added, which of the target's definitions were kept, and what was not carried along:

- 3D bindings, plot probes, dashboard cards and saved plots that refer to the copied blocks,
- docs pages, and their links to the copied blocks, which stay with the source model.
