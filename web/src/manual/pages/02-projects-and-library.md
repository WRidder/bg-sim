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

Blocks in the project library live in `library/<Name>.jl` in the project. They appear in the **Project** category, can be dragged onto any model of the project like a standard block, and are edited in the [Code tab](page:code-and-docs). There are four ways to make one:

- **Change a standard block:** select it and click **Copy to project library** in the inspector (or in the read-only Code tab). The instance then uses the copy.
- **Keep an inline code block:** select an inline Equation or Discrete code block and click **Save to project library** in the inspector (or in the Code tab). Choose a name. The block on the diagram then uses the library block and keeps its name, position and values. Inline blocks with exactly the same code can be switched over in the same step, and one **Undo** turns them all back into inline blocks.
- **Write a subsystem as code:** select a subsystem and click **Export as code block…** in the inspector. See *A subsystem as a code block* below.
- **Start a new one:** click **+ Library block** in the Code tab and pick *Equation block* or *Discrete block* and a name.

A block name is a Julia identifier (letters, digits and `_`, not starting with a digit) that no other project block uses. Case does not count, because the name is also the file name. The `@block <Name>` line of the code is set to the chosen name. After saving, the **Project** category opens and the new block is highlighted for a moment.

### Library subsystems: one drawing, many instances

Use this when a model needs the same subsystem several times, such as the ten actuators of a robot. A **library subsystem** is a subsystem you draw once and place many times. Every placed copy is an **instance**. All instances share one diagram: open any instance, change something, and every instance changes.

To make one:

1. Draw and test the subsystem as usual.
2. Select it and click **Make reusable…** in the inspector.
3. Enter a name, for example `Actuator`, and click **Add to library**.

The subsystem is now in the **Project** category of the library, and the node on the diagram is its first instance. Drag more instances from the **Project** category, or copy an instance.

How to recognise an instance:

- **On the diagram:** the card has a link badge with the name of the library subsystem. A number in the badge counts the values this instance sets itself.
- **In the inspector:** the section **Library subsystem** names the library subsystem and the number of instances in the model.
- **Inside:** the path bar shows the instance and its library subsystem, `Act1 (Actuator)`, and a banner says that changes apply to all instances.

Editing:

- **Open an instance** by double-clicking it. You edit the shared diagram, at that instance: probes, plots and values on the diagram show the instance you came in through, and its signals keep their own names (`Act3/rotor/w`).
- **Everything you change inside changes every instance:** blocks, connections, layout, notes, shapes and parameter values. One **Undo** takes the change back everywhere.
- **Give each instance its own value:** open an instance, select a block and click **pin** next to a parameter or a start value. A pinned value belongs to the instance it is typed in. A value that is not pinned is the same in every instance.

The values of one instance:

- Select the instance. The **Library subsystem** section lists every pinned value with the library's value next to it.
- A value this instance sets itself is marked **this instance**. The line above the list counts them.
- The reset arrow of a value returns it to the library's value. **Reset all** does that for every value.
- An instance that sets no value of its own follows the library: change the value inside any instance that has not changed it, and they all follow.

What asks first:

- **Deleting a port** of a library subsystem, or of a subsystem inside it. Every instance loses the port and the connections on it; the dialog lists those connections. A subsystem around another instance that passes the port on loses that port too.
- **Renaming a port** of a library subsystem. The message under the name field says how many instances change; press Enter again to rename. Connections in this model follow the new name.
- **Unpinning a value** that some instances have changed. They return to the library's value.
- **Detach…** in the inspector turns one instance into an ordinary subsystem that no longer follows the library.
- **Remove from library…** (right-click the subsystem in the **Project** category) turns every instance into an ordinary subsystem.

What to know:

- **The file is** `library/<Name>.bgsub.json` in the project. It is written when the model is saved.
- **Other models of the project** that use the library subsystem get the change the next time they are opened. A port that was deleted or renamed leaves their connection to it unconnected, which the model check reports.
- **One model at a time:** edit a library subsystem in one browser tab. A second tab that has the project open does not see the change until it is reloaded, and saving there writes its older copy back.
- **A pin follows its block:** renaming a block inside keeps its pinned values. Deleting the block removes the pin.
- **The library file is deleted** only by **Remove from library…**, when the model is next saved.
- **A library subsystem can hold instances of another one** (a `Leg` with five `Actuator` instances). It cannot hold an instance of itself.
- **Values in an instance of an instance:** the pinned values of an `Actuator` inside `Leg` are part of `Leg`, so they are the same in every `Leg`.
- **Constants** (the structural settings of a block) cannot be pinned.

### A subsystem as a code block

**Export as code block…** in the inspector writes a subsystem as text instead: a block `library/<Name>.jl` with `@components` and `@connections`, and replaces the node by an instance of that block. Use it when you want the subsystem as code. To keep drawing it, use **Make reusable…** instead.

1. Select the subsystem and click **Export as code block…**.
2. Enter a block name. A name that a standard library block already has is refused.
3. Tick the **parameters each instance can set**. A ticked parameter becomes a parameter of the block. A plain number becomes the block's default; an expression stays on the instance and the block keeps the default of the block inside. A value that uses a [global parameter](page:parameters) is always ticked: a code block cannot see the model's globals, so the expression moves to the instance.
4. Click **Save to library**.

BG-Sim checks the new block, writes the file and checks the model with the instance in place of the subsystem. Only when the model has no new error is the subsystem replaced. The instance keeps its name, position, connections and signal names. Two kinds of name do change, and plots and dashboard cards follow them: a ticked parameter (`Actuator1/rotor/J` becomes `Actuator1/J`) and the effort and flow of a bond between two junctions. One **Undo** brings the drawn subsystem back; the library file stays.

- **The drawing is not kept:** its layout, notes, shapes and probes are gone, and the block is edited in the Code tab.
- **Everything inside becomes a library block:** a subsystem inside is saved as a block of its own (`<Name>_<Inner>`), and an inline code block inside is saved too. The dialog lists them.
- **Start values stay with the instance,** as `<block>/<variable>`.
- **What is refused,** with the reason in the dialog: a subsystem inside an instance of a library subsystem (detach the instance first), a port and a block inside with the same name, a name that block code reserves (such as `t`, `Ts` or `end`), a block with a data file (`CsvSource`, `ModalBody3D`), a constant set to a global parameter, a constant that is a one-column matrix, and a standard block whose name a project block also uses.
- **An instance of a library subsystem inside** is written as a code block of its own, so it no longer follows the library.

