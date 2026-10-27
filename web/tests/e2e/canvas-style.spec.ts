import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * The diagram visual language follow-up:
 *
 * 1. a bond-graph element is its letter, not a card, and its port faces the
 *    bond that leaves it;
 * 2. the instance name hangs outside the letter (and moves off a port side);
 * 3. holding Ctrl and dragging an element starts a connection from its nearest
 *    source port, while Ctrl+click still selects;
 * 4. the toolbar toggles the grid and snapping, and a snapped drop lands on the
 *    20 px grid.
 */

let project = "";

test.beforeEach(async ({ page }) => {
  project = `w-canvas-style-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
  }
});

async function openModel(page: Page): Promise<void> {
  await page.goto(`/?project=${encodeURIComponent(project)}&model=CanvasStyle`);
  await expect(page.getByTestId("library-item-Se")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("canvas-surface")).toBeVisible();
}

async function dropBlock(page: Page, name: string, x: number, y: number): Promise<void> {
  const item = page.getByTestId(`library-item-${name}`).first();
  await item.scrollIntoViewIfNeeded();
  await item.dragTo(page.getByTestId("canvas-surface"), { targetPosition: { x, y } });
}

function node(page: Page, name: string) {
  return page.locator(`[data-testid="diagram-node"][data-node-name="${name}"]`);
}

async function connectPorts(
  page: Page,
  from: Locator,
  fromPort: string,
  to: Locator,
  toPort: string,
): Promise<void> {
  const handle = from.locator(`[data-port="${fromPort}"]`).first();
  const target = to.locator(`[data-port="${toPort}"]`).first();
  const fromBox = await handle.boundingBox();
  const toBox = await target.boundingBox();
  if (fromBox === null || toBox === null) {
    throw new Error("a port is not visible");
  }
  await page.mouse.move(fromBox.x + fromBox.width / 2, fromBox.y + fromBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(fromBox.x + fromBox.width / 2 + 12, fromBox.y + fromBox.height / 2 + 8, {
    steps: 3,
  });
  await page.mouse.move(toBox.x + toBox.width / 2, toBox.y + toBox.height / 2, { steps: 12 });
  await page.mouse.up();
}

test("a bond-graph element is its letter with the port on the bond side", async ({ page }) => {
  await openModel(page);
  await dropBlock(page, "Se", 80, 200);
  await dropBlock(page, "I", 420, 200);

  const source = node(page, "Se");
  const inertia = node(page, "I");
  await expect(source).toHaveAttribute("data-node-bond", "true");
  await expect(source.locator(".block-node")).toHaveCount(0);
  await expect(source.locator(".bond-node__glyph")).toHaveText("Se");
  await expect(source.locator('[data-testid^="node-label-"]')).toHaveText("Se");

  await connectPorts(page, source, "p", inertia, "p");
  await expect(page.locator('[data-testid^="edge-"]')).toHaveCount(1);

  // Bond-graph letters use the bond as the port marker; no square port glyph.
  await expect(source.locator(".port-glyph--power")).toBeHidden();

  const sourceId = await source.getAttribute("data-node-id");
  const targetId = await inertia.getAttribute("data-node-id");
  await expect(page.getByTestId(`port-${sourceId}-p`)).toHaveAttribute("data-side", "right");
  await expect(page.getByTestId(`port-${targetId}-p`)).toHaveAttribute("data-side", "left");
  // The label avoids the port side (right) and stays below the letter.
  await expect(source).toHaveAttribute("data-label-side", "bottom");
});

test("Ctrl-drag connects from the nearest source port and Ctrl+click still selects", async ({
  page,
}) => {
  await openModel(page);
  await dropBlock(page, "Se", 80, 200);
  await dropBlock(page, "Resistor", 420, 200);

  const source = node(page, "Se");
  const resistor = node(page, "Resistor");
  const sourceBox = await source.boundingBox();
  const portBox = await resistor.locator('[data-port="p"]').first().boundingBox();
  if (sourceBox === null || portBox === null) {
    throw new Error("source or target is not visible");
  }

  await page.keyboard.down("Control");
  await expect(page.locator(".react-flow.is-quick-connect")).toHaveCount(1);
  await page.mouse.move(sourceBox.x + sourceBox.width / 2, sourceBox.y + sourceBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(sourceBox.x + sourceBox.width / 2 + 20, sourceBox.y + 40, { steps: 4 });
  await expect(page.getByTestId("quick-connect-line")).toBeVisible();
  await page.mouse.move(portBox.x + portBox.width / 2, portBox.y + portBox.height / 2, {
    steps: 12,
  });
  await page.mouse.up();
  await page.keyboard.up("Control");

  await expect(page.locator('[data-testid^="edge-"]')).toHaveCount(1);
  await expect(page.locator('[data-testid^="edge-"]').first()).toHaveAttribute(
    "data-kind",
    "bond",
  );

  // A plain Ctrl+click is still additive selection, not a connection.
  await page.locator(".react-flow__pane").click({ position: { x: 700, y: 100 } });
  await page.keyboard.down("Control");
  await expect(page.locator(".react-flow.is-quick-connect")).toHaveCount(1);
  await source.click();
  await resistor.click();
  await page.keyboard.up("Control");
  await expect(source).toHaveClass(/is-selected/);
  await expect(resistor).toHaveClass(/is-selected/);
  await expect(page.locator('[data-testid^="edge-"]')).toHaveCount(1);
});

test("Ctrl-drag onto a block body picks the first compatible input and draws its arrow", async ({
  page,
}) => {
  await openModel(page);
  // Source on the right, target on the left: the input lands on the target's
  // right edge, so its arrow must point left (into the block).
  await dropBlock(page, "Step", 460, 220);
  await dropBlock(page, "Gain", 90, 220);

  const source = node(page, "Step");
  const gain = node(page, "Gain");
  const sourceBox = await source.boundingBox();
  const gainBox = await gain.boundingBox();
  if (sourceBox === null || gainBox === null) {
    throw new Error("source or target is not visible");
  }

  await page.keyboard.down("Control");
  await page.mouse.move(sourceBox.x + sourceBox.width / 2, sourceBox.y + sourceBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(sourceBox.x + sourceBox.width / 2 - 20, sourceBox.y + 20, {
    steps: 4,
  });
  await expect(page.getByTestId("quick-connect-line")).toBeVisible();
  // Deliberately the block body, not a port.
  await page.mouse.move(gainBox.x + gainBox.width / 2, gainBox.y + gainBox.height / 2, {
    steps: 12,
  });
  await page.mouse.up();
  await page.keyboard.up("Control");

  await expect(page.locator('[data-testid^="edge-"]')).toHaveCount(1);
  await expect(page.locator('[data-testid^="edge-"]').first()).toHaveAttribute(
    "data-kind",
    "signal",
  );
  const stored = JSON.parse(
    (await page.getByTestId("document-json").textContent()) ?? "null",
  ) as {
    diagram: {
      connections: { to: { node: string; port?: string } }[];
      nodes: { id: string; name: string }[];
    };
  };
  const gainId = stored.diagram.nodes.find((entry) => entry.name === "Gain")?.id;
  expect(stored.diagram.connections[0]?.to).toEqual({ node: gainId, port: "u" });

  const input = gain.locator('[data-port="u"]').first();
  await expect(input).toHaveAttribute("data-direction", "input");
  await expect(input).toHaveAttribute("data-glyph", "dot");
  await expect(input.locator(".port-glyph--in")).toBeVisible();
  await expect(input.locator(".port-glyph--signal")).toHaveCount(0);

  const output = source.locator('[data-port="y"]').first();
  await expect(output).toHaveAttribute("data-glyph", "arrow");
  await expect(output).toHaveAttribute("data-arrow-rotation", "180");
  const glyph = output.locator(".port-glyph--signal");
  await expect
    .poll(async () => glyph.evaluate((element) => getComputedStyle(element).transform))
    .toContain("matrix(-1");
  // The output arrow sits outside the block, with its base on the border and
  // its tip at the start of the outgoing line.
  const glyphBox = await glyph.boundingBox();
  const sourceBoxAfter = await source.boundingBox();
  expect(glyphBox).not.toBeNull();
  expect(sourceBoxAfter).not.toBeNull();
  if (glyphBox !== null && sourceBoxAfter !== null) {
    expect(glyphBox.x).toBeLessThan(sourceBoxAfter.x);
    expect(
      Math.abs(glyphBox.x + glyphBox.width - sourceBoxAfter.x),
    ).toBeLessThanOrEqual(1.5);
  }
});

test("a selected connection can be routed with draggable vertices", async ({ page }) => {
  await openModel(page);
  await dropBlock(page, "Se", 80, 200);
  await dropBlock(page, "I", 480, 280);
  const source = node(page, "Se");
  const inertia = node(page, "I");
  await connectPorts(page, source, "p", inertia, "p");

  const edge = page.locator('[data-testid^="edge-"]').first();
  await expect(edge).toHaveCount(1);
  const edgeId = (await edge.getAttribute("data-testid"))?.replace("edge-", "") ?? "";
  const pointOnEdge = async (fraction: number): Promise<{ x: number; y: number }> =>
    edge
      .locator(".react-flow__edge-path")
      .first()
      .evaluate((element, at) => {
        const path = element as SVGPathElement;
        const local = path.getPointAtLength(path.getTotalLength() * at);
        const matrix = path.getScreenCTM();
        if (matrix === null) {
          throw new Error("the connection has no screen transform");
        }
        return {
          x: matrix.a * local.x + matrix.c * local.y + matrix.e,
          y: matrix.b * local.x + matrix.d * local.y + matrix.f,
        };
      }, fraction);
  const openEdgeMenu = async (
    fraction: number,
  ): Promise<{ x: number; y: number }> => {
    const point = await pointOnEdge(fraction);
    await page.mouse.click(point.x, point.y, { button: "right" });
    await expect(page.getByTestId("canvas-menu")).toBeVisible();
    return point;
  };
  const route = async (): Promise<{ x: number; y: number }[]> => {
    const stored = JSON.parse(
      (await page.getByTestId("document-json").textContent()) ?? "null",
    ) as { diagram: { connections: { route?: { x: number; y: number }[] }[] } };
    return stored.diagram.connections[0]?.route ?? [];
  };
  const near = (
    point: { x: number; y: number },
    target: { x: number; y: number },
  ): number => Math.hypot(point.x - target.x, point.y - target.y);
  const isRouteGrid = (point: { x: number; y: number }): boolean =>
    point.x % 10 === 0 && point.y % 10 === 0;

  const firstClick = await openEdgeMenu(0.3);
  await page.getByTestId("add-vertex").click();
  const vertex = page.getByTestId(`connection-vertex-${edgeId}-0`);
  await expect(vertex).toBeVisible();
  await expect.poll(async () => (await route()).length).toBe(1);
  const firstPoint = (await route())[0];
  expect(firstPoint).toBeDefined();
  if (firstPoint === undefined) {
    throw new Error("the first vertex is missing");
  }
  expect(isRouteGrid(firstPoint), JSON.stringify(firstPoint)).toBe(true);
  const firstBox = await vertex.boundingBox();
  if (firstBox === null) {
    throw new Error("the first vertex is not visible");
  }
  // The new vertex lands at the click, snapped by at most half a cell.
  expect(
    near(
      { x: firstBox.x + firstBox.width / 2, y: firstBox.y + firstBox.height / 2 },
      firstClick,
    ),
  ).toBeLessThan(25);

  // A second right-click on a connection that already routes adds a vertex
  // near that click, not at the midpoint of the longest remaining segment.
  const secondClick = await openEdgeMenu(0.7);
  await page.getByTestId("add-vertex").click();
  await expect.poll(async () => (await route()).length).toBe(2);
  const secondPoint = (await route())[1];
  expect(secondPoint).toBeDefined();
  if (secondPoint === undefined) {
    throw new Error("the second vertex is missing");
  }
  expect(isRouteGrid(secondPoint), JSON.stringify(secondPoint)).toBe(true);
  const secondBox = await page.getByTestId(`connection-vertex-${edgeId}-1`).boundingBox();
  if (secondBox === null) {
    throw new Error("the second vertex is not visible");
  }
  expect(
    near(
      { x: secondBox.x + secondBox.width / 2, y: secondBox.y + secondBox.height / 2 },
      secondClick,
    ),
  ).toBeLessThan(25);

  await openEdgeMenu(0.5);
  await page.getByTestId("clear-vertices").click();
  await expect.poll(async () => (await route()).length).toBe(0);
  await page.keyboard.press("Control+z");
  await expect.poll(async () => (await route()).length).toBe(2);

  const vertexBox = await vertex.boundingBox();
  if (vertexBox === null) {
    throw new Error("the routing vertex is not visible");
  }
  const before = (await route())[0];
  const edgePath = edge.locator(".react-flow__edge-path").first();
  const pathBefore = await edgePath.getAttribute("d");
  await page.mouse.move(
    vertexBox.x + vertexBox.width / 2,
    vertexBox.y + vertexBox.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    vertexBox.x + vertexBox.width / 2 + 60,
    vertexBox.y + vertexBox.height / 2 + 40,
    { steps: 6 },
  );
  // The routed line follows the handle before the mouse is released.
  await expect.poll(async () => edgePath.getAttribute("d")).not.toBe(pathBefore);
  const live = (await route())[0];
  expect(live).not.toEqual(before);
  await page.mouse.up();
  await expect
    .poll(async () => {
      const after = (await route())[0];
      return after === undefined || before === undefined
        ? 0
        : Math.hypot(after.x - before.x, after.y - before.y);
    })
    .toBeGreaterThan(20);
  const dragged = (await route())[0];
  expect(dragged).toBeDefined();
  expect(isRouteGrid(dragged ?? { x: 0, y: 0 })).toBe(true);

  // The live updates are one coalesced drag gesture, not dozens of undo steps.
  await page.keyboard.press("Control+z");
  await expect.poll(async () => (await route())[0]).toEqual(before);
  await page.keyboard.press("Control+Shift+z");
  await expect.poll(async () => (await route())[0]).toEqual(dragged);

  await vertex.dblclick();
  await expect.poll(async () => (await route()).length).toBe(1);
  await page.keyboard.press("Control+z");
  await expect.poll(async () => (await route()).length).toBe(2);
});

test("routing vertices use the half grid when snapping is on and are free when off", async ({
  page,
}) => {
  await openModel(page);
  await dropBlock(page, "Gain", 200, 160);
  await dropBlock(page, "Gain", 200, 460);
  const source = node(page, "Gain");
  const target = node(page, "Gain2");
  await connectPorts(page, source, "y", target, "u");

  const edge = page.locator('[data-testid^="edge-"]').first();
  await expect(edge).toHaveCount(1);
  const edgeId = (await edge.getAttribute("data-testid"))?.replace("edge-", "") ?? "";
  const pointOnEdge = async (fraction: number): Promise<{ x: number; y: number }> =>
    edge
      .locator(".react-flow__edge-path")
      .first()
      .evaluate((element, at) => {
        const path = element as SVGPathElement;
        const local = path.getPointAtLength(path.getTotalLength() * at);
        const matrix = path.getScreenCTM();
        if (matrix === null) {
          throw new Error("the connection has no screen transform");
        }
        return {
          x: matrix.a * local.x + matrix.c * local.y + matrix.e,
          y: matrix.b * local.x + matrix.d * local.y + matrix.f,
        };
      }, fraction);
  const route = async (): Promise<{ x: number; y: number }[]> => {
    const stored = JSON.parse(
      (await page.getByTestId("document-json").textContent()) ?? "null",
    ) as { diagram: { connections: { route?: { x: number; y: number }[] }[] } };
    return stored.diagram.connections[0]?.route ?? [];
  };
  const vertex = page.getByTestId(`connection-vertex-${edgeId}-0`);
  const dragVertex = async (dx: number, dy: number): Promise<void> => {
    const box = await vertex.boundingBox();
    if (box === null) {
      throw new Error("the routing vertex is not visible");
    }
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(
      box.x + box.width / 2 + dx,
      box.y + box.height / 2 + dy,
      { steps: 4 },
    );
    await page.mouse.up();
  };

  // The vertical edge is at the block centre, an odd multiple of 10. Adding a
  // vertex there proves the route grid is not the 20 px node grid.
  const click = await pointOnEdge(0.5);
  await page.mouse.click(click.x, click.y, { button: "right" });
  await expect(page.getByTestId("canvas-menu")).toBeVisible();
  await page.getByTestId("add-vertex").click();
  await expect.poll(async () => (await route()).length).toBe(1);
  const centred = (await route())[0];
  expect(centred).toBeDefined();
  if (centred === undefined) {
    throw new Error("the vertex is missing");
  }
  expect(centred.x % 20).toBe(10);
  expect(centred.y % 10).toBe(0);

  // Snap off: the vertex follows the pointer freely.
  await page.getByTestId("toggle-snap").click();
  await dragVertex(7, 13);
  const free = (await route())[0];
  expect(free).toBeDefined();
  if (free === undefined) {
    throw new Error("the free vertex is missing");
  }
  expect(free.x % 10 === 0 && free.y % 10 === 0).toBe(false);

  // Snap on: the same drag lands back on the 10 px route grid.
  await page.getByTestId("toggle-snap").click();
  await dragVertex(7, 13);
  const snapped = (await route())[0];
  expect(snapped).toBeDefined();
  if (snapped === undefined) {
    throw new Error("the snapped vertex is missing");
  }
  expect(snapped.x % 10).toBe(0);
  expect(snapped.y % 10).toBe(0);
});

test("a dragged vertex shows a right-angle symbol when its corner is square", async ({
  page,
}) => {
  await openModel(page);
  await dropBlock(page, "Gain", 200, 160);
  await dropBlock(page, "Gain", 200, 460);
  const source = node(page, "Gain");
  const target = node(page, "Gain2");
  await connectPorts(page, source, "y", target, "u");

  const edge = page.locator('[data-testid^="edge-"]').first();
  await expect(edge).toHaveCount(1);
  const edgeId = (await edge.getAttribute("data-testid"))?.replace("edge-", "") ?? "";
  const pointOnEdge = async (fraction: number): Promise<{ x: number; y: number }> =>
    edge
      .locator(".react-flow__edge-path")
      .first()
      .evaluate((element, at) => {
        const path = element as SVGPathElement;
        const local = path.getPointAtLength(path.getTotalLength() * at);
        const matrix = path.getScreenCTM();
        if (matrix === null) {
          throw new Error("the connection has no screen transform");
        }
        return {
          x: matrix.a * local.x + matrix.c * local.y + matrix.e,
          y: matrix.b * local.x + matrix.d * local.y + matrix.f,
        };
      }, fraction);
  const route = async (): Promise<{ x: number; y: number }[]> => {
    const stored = JSON.parse(
      (await page.getByTestId("document-json").textContent()) ?? "null",
    ) as { diagram: { connections: { route?: { x: number; y: number }[] }[] } };
    return stored.diagram.connections[0]?.route ?? [];
  };
  const centre = (box: { x: number; y: number; width: number; height: number }) => ({
    x: box.x + box.width / 2,
    y: box.y + box.height / 2,
  });
  const drag = async (
    from: { x: number; y: number },
    to: { x: number; y: number },
  ): Promise<void> => {
    await page.mouse.move(from.x, from.y);
    await page.mouse.down();
    await page.mouse.move(to.x, to.y, { steps: 4 });
    await page.mouse.up();
  };
  const addVertex = async (fraction: number): Promise<void> => {
    const click = await pointOnEdge(fraction);
    await page.mouse.click(click.x, click.y, { button: "right" });
    await expect(page.getByTestId("canvas-menu")).toBeVisible();
    await page.getByTestId("add-vertex").click();
  };

  // Two vertices on the vertical connection; the lower one steps aside so the
  // upper one can become the corner of the route.
  await addVertex(0.4);
  await expect.poll(async () => (await route()).length).toBe(1);
  await addVertex(0.7);
  await expect.poll(async () => (await route()).length).toBe(2);
  const lower = page.getByTestId(`connection-vertex-${edgeId}-1`);
  const lowerBox = await lower.boundingBox();
  if (lowerBox === null) {
    throw new Error("the lower vertex is not visible");
  }
  await drag(centre(lowerBox), { x: centre(lowerBox).x + 100, y: centre(lowerBox).y });

  const marker = page.getByTestId(`connection-right-angle-${edgeId}`);
  await expect(marker).toHaveCount(0);

  // Drag the upper vertex down to the lower one's row: the segment from the
  // port is vertical and the segment to the other vertex is horizontal, so a
  // right-angle symbol appears in the corner until the pointer is released.
  const upper = page.getByTestId(`connection-vertex-${edgeId}-0`);
  const upperBox = await upper.boundingBox();
  const lowerNow = await lower.boundingBox();
  if (upperBox === null || lowerNow === null) {
    throw new Error("a routing vertex is not visible");
  }
  const start = centre(upperBox);
  await page.mouse.move(start.x, start.y);
  await page.mouse.down();
  await page.mouse.move(start.x, centre(lowerNow).y, { steps: 4 });
  await expect(marker).toHaveCount(1);
  const corner = (await route())[0];
  const peer = (await route())[1];
  expect(corner?.y).toBe(peer?.y);
  await page.mouse.up();
  await expect(marker).toHaveCount(0);
});

test("centred ports share the block and connection centre line", async ({ page }) => {
  await openModel(page);
  await dropBlock(page, "Gain", 200, 160);
  await dropBlock(page, "Gain", 200, 460);
  const source = node(page, "Gain");
  const target = node(page, "Gain2");
  await connectPorts(page, source, "y", target, "u");

  const body = await source.boundingBox();
  const output = await source.locator('[data-port="y"] .port-glyph').boundingBox();
  const input = await target.locator('[data-port="u"] .port-glyph').boundingBox();
  const edgePath = await page
    .locator('[data-testid^="edge-"] .react-flow__edge-path')
    .first()
    .boundingBox();
  if (body === null || output === null || input === null || edgePath === null) {
    throw new Error("a block, a port glyph or the connection is not visible");
  }
  const bodyCentre = body.x + body.width / 2;
  // Input dots and output arrows must sit on the vertical through the block,
  // even though the output arrow is shifted outward below the border.
  expect(Math.abs(output.x + output.width / 2 - bodyCentre)).toBeLessThanOrEqual(0.6);
  expect(Math.abs(input.x + input.width / 2 - bodyCentre)).toBeLessThanOrEqual(0.6);
  expect(Math.abs(edgePath.x + edgePath.width / 2 - bodyCentre)).toBeLessThanOrEqual(0.6);
});

test("probe blocks and plot windows tap a connection without entering the circuit", async ({
  page,
}) => {
  await openModel(page);
  await dropBlock(page, "Gain", 180, 180);
  await dropBlock(page, "Gain", 440, 180);
  const source = node(page, "Gain");
  const target = node(page, "Gain2");
  await connectPorts(page, source, "y", target, "u");

  const edge = page.locator('[data-testid^="edge-"]').first();
  await expect(edge).toHaveCount(1);
  const edgeId = (await edge.getAttribute("data-testid"))?.replace("edge-", "") ?? "";
  await edge.dispatchEvent("contextmenu", {
    bubbles: true,
    button: 2,
    clientX: 700,
    clientY: 400,
  });
  await expect(page.getByTestId("canvas-menu")).toBeVisible();
  await page.getByTestId("new-probe-block").click();

  const probe = page.getByTestId("probe-node");
  await expect(probe).toHaveCount(1);
  await expect(page.getByTestId("probe-inspector")).toBeVisible();
  const lead = page.locator('[data-testid^="probe-lead-"]').first();
  await expect(lead).toHaveCount(1);
  await expect(page.locator('[data-testid^="probe-signal-"]').first()).toBeVisible();
  const stored = JSON.parse(
    (await page.getByTestId("document-json").textContent()) ?? "null",
  ) as {
    diagram: {
      probes?: { id: string; kind: string; links: { connection: string }[] }[];
      connections: { id: string }[];
    };
  };
  expect(stored.diagram.probes).toHaveLength(1);
  expect(stored.diagram.probes?.[0]?.kind).toBe("block");
  expect(stored.diagram.probes?.[0]?.links[0]?.connection).toBe(edgeId);
  // A probe is not a circuit connection: the diagram still has exactly one.
  expect(stored.diagram.connections).toHaveLength(1);

  // A 3x3 probe opens its dedicated panel as soon as it has a lead; none
  // configured means one plot with all checked signals.
  await expect(page.locator('[data-testid^="probe-window-"]')).toHaveCount(1);
  await page.getByTestId("probe-toggle-open").click();
  await expect(page.locator('[data-testid^="probe-window-"]')).toHaveCount(0);
  await page.getByTestId("probe-toggle-open").click();
  await expect(page.locator('[data-testid^="probe-window-"]')).toHaveCount(1);
  await page.getByTestId("probe-add-panel").click();
  const withPanel = JSON.parse(
    (await page.getByTestId("document-json").textContent()) ?? "null",
  ) as { diagram: { probes?: { panels?: { signals: string[] }[] }[] } };
  expect(withPanel.diagram.probes?.[0]?.panels).toHaveLength(1);

  // The same connection can feed a second, independent floating plot window.
  await edge.dispatchEvent("contextmenu", {
    bubbles: true,
    button: 2,
    clientX: 720,
    clientY: 420,
  });
  await expect(page.getByTestId("canvas-menu")).toBeVisible();
  await page.getByTestId("new-probe-window").click();
  await expect(page.locator('[data-testid^="probe-window-"]')).toHaveCount(2);
  const after = JSON.parse(
    (await page.getByTestId("document-json").textContent()) ?? "null",
  ) as { diagram: { probes?: { kind: string; links: unknown[] }[] } };
  expect(after.diagram.probes).toHaveLength(2);
  expect(after.diagram.probes?.map((entry) => entry.kind)).toEqual(["block", "window"]);
  expect(after.diagram.probes?.[1]?.links).toHaveLength(1);

  // Probes are editor data, but they round-trip through the saved model.
  await page.getByTestId("save-now").click();
  await expect(page.getByTestId("save-status")).toHaveAttribute("data-state", "saved");
  await page.reload();
  await expect(page.getByTestId("library-item-Se")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("probe-node")).toHaveCount(1);
  await expect(page.locator('[data-testid^="probe-window-"]')).toHaveCount(2);
});

test("the toolbar toggles the grid and snapping", async ({ page }) => {
  await openModel(page);
  const grid = page.getByTestId("toggle-grid");
  await expect(grid).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".react-flow__background")).toHaveCount(1);
  await grid.click();
  await expect(grid).toHaveAttribute("aria-pressed", "false");
  await expect(page.locator(".react-flow__background")).toHaveCount(0);
  await grid.click();
  await expect(page.locator(".react-flow__background")).toHaveCount(1);

  const snap = page.getByTestId("toggle-snap");
  await expect(snap).toHaveAttribute("aria-pressed", "true");
  await snap.click();
  await expect(snap).toHaveAttribute("aria-pressed", "false");
  await snap.click();
  await expect(snap).toHaveAttribute("aria-pressed", "true");

  await dropBlock(page, "Se", 137, 213);
  const stored = JSON.parse((await page.getByTestId("document-json").textContent()) ?? "null") as {
    diagram: { nodes: { position: { x: number; y: number } }[] };
  };
  expect(stored.diagram.nodes).toHaveLength(1);
  const position = stored.diagram.nodes[0]?.position;
  expect(position?.x).toBe(Math.round((position?.x ?? 0) / 20) * 20);
  expect(position?.y).toBe(Math.round((position?.y ?? 0) / 20) * 20);
  expect(position?.x).not.toBe(0);
  expect(position?.y).not.toBe(0);
});
