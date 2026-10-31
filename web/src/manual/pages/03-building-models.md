# Building models

Models are drawn on the canvas of the **Diagram** tab.

## Blocks

- **Add:** drag a block from the [library](page:projects-and-library) onto the canvas.
- **Select:** click a block, or drag on empty canvas for a selection box.
- **Edit:** the inspector on the right shows the selected block: name, parameters (with units, defaults and limits), constants, start values and ports. Press `Enter` to apply a value, `Esc` to undo the typing. Values can be expressions and can use [global parameters](page:parameters).
- **Arrange:** `R` rotates, `F` flips, `Del` deletes, `Ctrl+C` / `Ctrl+V` copy and paste. Right-click a block for the same actions.
- **Undo:** `Ctrl+Z`, redo `Ctrl+Y`.
- **Navigate:** the mouse wheel zooms. Pan with the middle mouse button, `Space`+drag or the arrow keys. **Fit view** in the canvas toolbar fits the whole diagram.

## Ports and connections

| Port glyph | Kind | Connects to |
| --- | --- | --- |
| filled square | power port | one other power port of the same domain (a **bond**) |
| filled triangle | signal output | any number of signal inputs |
| hollow triangle | signal input | exactly one signal output |

- **Connect:** drag from one port to another. Compatible ports are highlighted; an invalid target shows why it is refused. `Ctrl`+drag starts from the port of a block nearest to the pointer.
- **Release on empty canvas** to get a filterable list of compatible blocks; the one you pick is added and connected.
- **Bond direction:** the half arrow on a bond shows the positive power direction. Right-click a bond and choose **Reverse bond direction** to flip it.
- **Routing:** right-click a connection for **Add routing vertex** and **Clear routing vertices**.
- **Crossing kinds:** a signal cannot drive a power port directly. Use a modulated source (`MSe`, `MSf`) or a sensor. Different physical domains connect through a converter (`TF`, `GY`, a DC motor, …).
- **Junctions:** the **Junctions** category has the 0-junction (equal efforts, flows sum to zero) and the 1-junction (equal flows, efforts sum to zero).

Units are checked: ports with the same dimension but a different unit connect with a conversion factor shown on the wire; different dimensions are refused.

## Legend and grid

The canvas toolbar has **Show legend** (domain colours and port glyphs, bottom left), **Show grid** and **Snap to grid**. Causal strokes on bonds appear after the model has been checked.

## Subsystems

- **Create:** select blocks and click **⧉ Subsystem** in the canvas toolbar. The selected blocks and the connections between them move into the subsystem.
- **Enter:** double-click the subsystem. **Leave:** `Esc`, **↑ Up**, or a crumb in the path bar above the canvas.
- **Port terminals:** inside a subsystem, each port of the subsystem is a terminal. To add a port, drag an internal port onto the dashed **+ input**, **+ output** or **+ power** terminal, or right-click a port of an internal block and choose **Expose as subsystem port**. Right-click a terminal to **Rename port…**, **Delete port** or **Show outside connection**.
- A subsystem can be exported on its own as an FMU (see [Export](page:export)).

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
