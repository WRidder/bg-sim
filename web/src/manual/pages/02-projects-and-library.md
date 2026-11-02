# Projects and the library

## Projects and models

A **project** is a folder with one or more **models**, the project's own block library, CSV data, 3D scenes and docs. One model is open at a time.

- **Start page** (shown when no project is open): create a project under **New project**, reopen one of the **Recent projects**, or import an example from the **Example gallery**.
- **Project overview:** opening a project (a recent project, an imported sample, or **Open project overview** in the Open dialog) first shows its models as cards, like the example gallery. Each card has a picture, the model name, a short description, the number of blocks and the date of the last change. Click a card (or focus it with `Tab` and press `Enter`) to open that model. `Ctrl+click` opens it in a new browser tab. **Create model** starts a new, empty model in the project. **← All projects** goes back to the start page.
  - The picture is the first image of the model's [Docs](page:code-and-docs) overview page. Without one, the card shows a miniature of the diagram: boxes for blocks, dots for junctions, dashed lines for signals.
  - The description is the model's comment (`$comment` in the model file) or, without one, the first paragraph of its Docs overview page.
  - The overview has two tabs. **Models** (the default) shows the cards. **Docs** shows all documentation of the project in one tree: the project docs first, then each model with its pages (a model without docs is greyed, "no docs"). Click a page to read it next to the tree. Links in the page (`page:`, `project:`, `model:`) open other pages in the same view.
  - Pages are edited in a model's [Docs tab](page:code-and-docs). **Edit** opens the model on its Docs tab at that page. For a project page, it opens the first model of the project, with the page selected in the **Project** section. **Open model** opens the model on its diagram.
  - The open tab and page are part of the address (`?project=<name>&tab=docs&page=project:<id>`), so you can bookmark a page or share its link. The overview also reopens on the tab you used last in that project.
- **Open dialog** (`Ctrl+O` on the start page, or click **No project** in the top bar): pick a project on the left and a model on the right. Use **New project** and **New model** to create them.
- **Examples** are read-only templates. **Open sample** (or a sample in the Open dialog) imports an editable copy into your projects and shows its project overview; the example itself never changes.

### Switching models and projects

In a project, the top bar reads **BG-Sim ▸ project ▸ model ▾**:

- **model ▾** (or `Ctrl+O`) opens the model menu: the models of this project as small cards, with the open model marked **Open**. Click a card to switch to that model. Use the arrow keys to move between cards, `Enter` to open one and `Esc` to close the menu.
- **project** (the project name) opens the project overview with all models of the project.
- **BG-Sim** goes back to the start page. To open **another project**, go back to the start page and pick it there. The model menu only lists the models of the open project.

The model saves itself before BG-Sim switches. If other work is not saved yet (a project-library block in the Code tab, or Docs pages), BG-Sim asks first: **Save and leave**, **Leave without saving** or **Cancel**.

### Saving

- The model **saves automatically** about half a second after each edit. The canvas toolbar shows **Saved**, **Unsaved changes**, **Saving…** or **Save failed**; the **Save now** button saves at once.
- Code of the project library saves automatically too.
- **Docs pages do not autosave**: press `Ctrl+S` or click **Save** in the Docs tab.

## The block library

The **Library** panel at the top left lists every block you can use.

- **Search** (`/` focuses it) matches names, ports, groups and descriptions.
- **List view** shows names with a summary; click a row for its parameters and ports. **Grid view** shows icons only.
- Right-click a block in either view for **Show source** (the block's source in the Code tab) and **Info** (the block help). A junction offers **Info**.
- Blocks are grouped in **categories**, collapsed by default: Bond graph, Sources and sinks, Continuous, Discrete and logic, Electrical, Translation, Rotation, Hydraulic, Thermal, Converters and sensors, Drives, Planar and Spatial mechanics, Contact, 2D and 3D multibond, Junctions, and **Project** for blocks in the project's own library.
- The last category, **Shapes**, holds the background shapes: rectangle, rounded rectangle, ellipse, line and arrow. They are drawing only and ignored by simulation (see [Building models](page:building-models)). Search for "shape" or a shape name to find them.
- The **cog** (Library settings) switches between list and grid, shows or hides categories, and has **Show all**, **Expand all** and **Collapse all**.
- **Drag** a block onto the canvas to add it. A dragged shape lands with its top-left corner (a line: its start) at the drop point. A click on a shape (or `Enter`) adds it in the middle of the canvas.
- The help button of a block (or `F1` on a selected block) explains its ports and parameters.

### Your own blocks

Blocks in the project library live in `library/<Name>.jl` in the project. They appear in the **Project** category, can be dragged onto any model of the project like a standard block, and are edited in the [Code tab](page:code-and-docs). There are three ways to make one:

- **Change a standard block:** select it and click **Copy to project library** in the inspector (or in the read-only Code tab). The instance then uses the copy.
- **Keep an inline code block:** select an inline Equation or Discrete code block and click **Save to project library** in the inspector (or in the Code tab). Choose a name. The block on the diagram then uses the library block and keeps its name, position and values. Inline blocks with exactly the same code can be switched over in the same step, and one **Undo** turns them all back into inline blocks.
- **Start a new one:** click **+ Library block** in the Code tab and pick *Equation block* or *Discrete block* and a name.

A block name is a Julia identifier (letters, digits and `_`, not starting with a digit) that no other project block uses. Case does not count, because the name is also the file name. The `@block <Name>` line of the code is set to the chosen name. After saving, the **Project** category opens and the new block is highlighted for a moment.
