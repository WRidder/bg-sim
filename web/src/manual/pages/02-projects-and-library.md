# Projects and the library

## Projects and models

A **project** is a folder with one or more **models**, the project's own block library, CSV data, 3D scenes and docs. One model is open at a time.

- **Start page** (shown when no project is open): create a project under **New project**, reopen one of the **Recent projects**, or import an example from the **Example gallery**.
- **Open dialog** (`Ctrl+O`, or click the project name in the top bar): pick a project on the left and a model on the right. Use **New project** and **New model** to create them.
- **Examples** are read-only templates. **Open sample** (or a sample in the Open dialog) imports an editable copy into your projects; the example itself never changes.
- **Back to the start page:** click **BG-Sim** at the top left. If something is not saved yet, BG-Sim asks whether to save first.

### Saving

- The model **saves automatically** about half a second after each edit. The canvas toolbar shows **Saved**, **Unsaved changes**, **Saving…** or **Save failed**; the **Save now** button saves at once.
- Code of the project library saves automatically too.
- **Docs pages do not autosave**: press `Ctrl+S` or click **Save** in the Docs tab.

## The block library

The **Library** panel at the top left lists every block you can use.

- **Search** (`/` focuses it) matches names, ports, groups and descriptions.
- **List view** shows names with a summary; click a row for its parameters and ports. **Grid view** shows icons; click a tile for the block help.
- Blocks are grouped in **categories**, collapsed by default: Bond graph, Sources and sinks, Continuous, Discrete and logic, Electrical, Translation, Rotation, Hydraulic, Thermal, Converters and sensors, Drives, Planar and Spatial mechanics, Contact, 2D and 3D multibond, Junctions, and **Project** for blocks in the project's own library.
- The last category, **Shapes**, holds the background shapes: rectangle, rounded rectangle, ellipse, line and arrow. They are drawing only and ignored by simulation (see [Building models](page:building-models)). Search for "shape" or a shape name to find them.
- The **cog** (Library settings) switches between list and grid, shows or hides categories, and has **Show all**, **Expand all** and **Collapse all**.
- **Drag** a block onto the canvas to add it. A dragged shape lands with its top-left corner (a line: its start) at the drop point. A click on a shape (or `Enter`) adds it in the middle of the canvas.
- The help button of a block (or `F1` on a selected block) explains its ports and parameters.

### Your own blocks

To change a standard block, select it and click **Copy to project library** in the inspector (or in the read-only Code tab). The copy goes to `library/<Name>.jl` in the project, appears in the **Project** category and can be edited in the [Code tab](page:code-and-docs).
