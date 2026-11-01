/**
 * Opening a project shows its model picker (`?project=` without a model): a card
 * per model with a thumbnail and a short description. Inside a model, the top
 * bar's model menu lists the project's models (not other projects); another
 * project is reached through the start page.
 */

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/app/App";
import { LeaveProjectDialog } from "../src/app/LeaveProjectDialog";
import { registerUnsavedWork, useLeaveProjectStore } from "../src/app/leaveProject";
import { modifiedDate, previewLayout, shortDescription, withoutPlanReferences } from "../src/app/modelCards";
import { navigation } from "../src/app/openSession";
import { modelUrl, projectUrl, readAppRoute } from "../src/app/route";
import { TopBar } from "../src/app/TopBar";
import { resetCatalogStore } from "../src/library/catalogStore";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";
import { resetSessionCache } from "../src/state/session";

const CARDS = [
  {
    name: "iconic",
    modified: "2026-10-01T10:00:00Z",
    inProject: true,
    description:
      "Plan 9.1 (X2.5): a permanent-magnet DC motor driven by a 12 V step. The second sentence explains more. A third one is too much for a card because the card is short.",
    thumbnail: "1078c8343b4c.png",
    nodes: 7,
    preview: { nodes: [[0, 0, "b"], [100, 0, "j"]], links: [[0, 1, "b"]] },
    error: null,
  },
  {
    name: "bondgraph",
    modified: null,
    inProject: true,
    description: null,
    thumbnail: null,
    nodes: 2,
    preview: { nodes: [[0, 0, "b"], [200, 100, "s"]], links: [[0, 1, "s"]] },
    error: null,
  },
  {
    name: "empty",
    modified: null,
    inProject: false,
    description: "",
    thumbnail: null,
    nodes: 0,
    preview: { nodes: [], links: [] },
    error: null,
  },
];

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function installBackend(cards: unknown[] | null = CARDS): string[] {
  const urls: string[] = [];
  vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.pathname : input.url;
    urls.push(`${init?.method ?? "GET"} ${url}`);
    if (url === "/api/projects/motor/models") {
      return cards === null ? json({ detail: "unknown project" }, 404) : json({ name: "motor", models: cards });
    }
    return new Promise<Response>(() => {});
  });
  return urls;
}

let assign: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  window.history.replaceState(null, "", "/");
  resetDocumentStore();
  resetCatalogStore();
  resetSessionCache();
  useLeaveProjectStore.getState().close();
  assign = vi.spyOn(navigation, "assign").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("routes", () => {
  it("tells the start page, the model picker and the editor apart", () => {
    expect(readAppRoute("")).toEqual({ kind: "start" });
    expect(readAppRoute("?model=a")).toEqual({ kind: "start" });
    expect(readAppRoute("?project=p")).toEqual({ kind: "picker", project: "p" });
    expect(readAppRoute("?project=p&model=")).toEqual({ kind: "picker", project: "p" });
    expect(readAppRoute("?project=p&model=m")).toEqual({ kind: "editor", project: "p", model: "m" });
  });

  it("builds the picker and editor URLs from the current one", () => {
    const here = "http://localhost:5173/?project=a&model=b&theme=dark";
    expect(projectUrl("x y", here)).toBe("http://localhost:5173/?project=x+y&theme=dark");
    expect(modelUrl("p", "m", here)).toBe("http://localhost:5173/?project=p&model=m&theme=dark");
  });
});

describe("short descriptions", () => {
  it("drops plan bookkeeping", () => {
    expect(withoutPlanReferences("Plan 9.1 (X2.5): the M2 variant.")).toBe("The M2 variant.");
    expect(withoutPlanReferences("X5.8: the aerial manipulator.")).toBe("The aerial manipulator.");
    expect(withoutPlanReferences("Plan 9.6b industrial-servo (X2.6). The PMSM plant.")).toBe("The PMSM plant.");
    expect(withoutPlanReferences("The walking skeleton of bg-sim (plan 9.1, milestone M1): a motor.")).toBe(
      "The walking skeleton of bg-sim: a motor.",
    );
    // A first sentence without bookkeeping stays.
    expect(withoutPlanReferences("The same motor, as a bond graph (plan 9.1). The chain is:")).toBe(
      "The same motor, as a bond graph. The chain is:",
    );
    expect(withoutPlanReferences("A ball on a spring. It bounces.")).toBe("A ball on a spring. It bounces.");
  });

  it("keeps whole sentences up to the limit, cuts a long first one at a word", () => {
    expect(shortDescription("One. Two. Three.", 10)).toBe("One. Two.");
    expect(shortDescription("The same motor. The chain is:")).toBe("The same motor.");
    expect(shortDescription("The same motor. The chain is")).toBe("The same motor.");
    expect(shortDescription("Only an intro:")).toBe("Only an intro…");
    const long = shortDescription(`A ${"very ".repeat(60)}long sentence.`, 50) ?? "";
    expect(long.endsWith("…")).toBe(true);
    expect(long.length).toBeLessThanOrEqual(51);
    expect(shortDescription(null)).toBeNull();
    expect(shortDescription("   ")).toBeNull();
  });

  it("fits the miniature in an 8:5 view box and skips an empty diagram", () => {
    expect(previewLayout({ nodes: [], links: [] })).toBeNull();
    const layout = previewLayout({ nodes: [[0, 0, "b"], [800, 100, "b"]], links: [] });
    const [, , width, height] = (layout?.viewBox ?? "").split(" ").map(Number);
    expect((width ?? 0) / (height ?? 1)).toBeCloseTo(8 / 5, 2);
    expect(modifiedDate("not a date")).toBe("");
  });
});

describe("model picker page", () => {
  it("opens on a project without a model: a card per model with a description", async () => {
    window.history.replaceState(null, "", "/?project=motor");
    installBackend();
    render(<App />);

    const picker = await screen.findByTestId("model-picker");
    await waitFor(() => expect(picker.getAttribute("data-state")).toBe("ready"));
    expect(screen.queryByTestId("start-page")).toBeNull();
    expect(screen.queryByTestId("left-panel")).toBeNull();
    expect(screen.getByRole("heading", { level: 1, name: "motor" })).toBeTruthy();

    const iconic = screen.getByTestId("model-card-iconic");
    expect(iconic.tagName).toBe("A");
    expect(iconic.getAttribute("href")).toContain("model=iconic");
    expect(within(iconic).getByRole("heading", { name: "iconic" })).toBeTruthy();
    expect(iconic.textContent).toContain(
      "A permanent-magnet DC motor driven by a 12 V step. The second sentence explains more.",
    );
    expect(iconic.textContent).not.toContain("Plan 9.1");
    expect(iconic.textContent).toContain("7 blocks");
    expect(within(iconic).getByTestId("model-thumbnail-iconic").getAttribute("src")).toBe(
      "/api/projects/motor/docs/iconic/assets/1078c8343b4c.png",
    );
    // No docs image: a miniature of the diagram; an empty model: the placeholder.
    const bondgraph = screen.getByTestId("model-card-bondgraph");
    expect(within(bondgraph).getByTestId("model-miniature-bondgraph").querySelectorAll("rect")).toHaveLength(2);
    expect(bondgraph.textContent).toContain("No description yet.");
    const empty = screen.getByTestId("model-card-empty");
    expect(within(empty).getByTestId("model-placeholder-empty")).toBeTruthy();
    expect(empty.textContent).toContain("not in the project list");
  });

  it("opens the clicked model, but leaves a Ctrl+click to the browser", async () => {
    window.history.replaceState(null, "", "/?project=motor");
    installBackend();
    render(<App />);

    const card = await screen.findByTestId("model-card-bondgraph");
    fireEvent.click(card, { ctrlKey: true });
    expect(assign).not.toHaveBeenCalled();
    fireEvent.click(card);
    await waitFor(() => expect(assign).toHaveBeenCalledTimes(1));
    const target = new URL(String(assign.mock.calls[0]?.[0]));
    expect(target.searchParams.get("project")).toBe("motor");
    expect(target.searchParams.get("model")).toBe("bondgraph");
  });

  it("starts a new model and refuses a name the project already has", async () => {
    window.history.replaceState(null, "", "/?project=motor");
    installBackend();
    render(<App />);

    const input = await screen.findByTestId("picker-new-model-name");
    fireEvent.change(input, { target: { value: "Iconic" } });
    fireEvent.click(screen.getByTestId("picker-create-model"));
    expect((await screen.findByTestId("picker-error")).textContent).toMatch(/already has a model/);
    expect(assign).not.toHaveBeenCalled();

    fireEvent.change(input, { target: { value: "Model2" } });
    fireEvent.click(screen.getByTestId("picker-create-model"));
    await waitFor(() => expect(assign).toHaveBeenCalledTimes(1));
    expect(new URL(String(assign.mock.calls[0]?.[0])).searchParams.get("model")).toBe("Model2");
  });

  it("goes back to all projects, and says so when the project does not exist", async () => {
    window.history.replaceState(null, "", "/?project=motor");
    installBackend(null);
    render(<App />);

    expect((await screen.findByTestId("picker-missing")).textContent).toContain("no project named");
    fireEvent.click(screen.getByTestId("picker-back"));
    expect(assign).toHaveBeenCalledWith("http://localhost:3000/");
    // The top bar shows the project as a breadcrumb, not the Open dialog button.
    expect(screen.getByTestId("project-crumb").textContent).toBe("motor");
    expect(screen.queryByTestId("open-project")).toBeNull();
  });
});

describe("model menu in the top bar", () => {
  function openEditor(): void {
    window.history.replaceState(null, "", "/?project=motor&model=iconic");
    useDocumentStore.getState().openDocument("motor", "iconic", createEmptyModel("iconic"));
  }

  function renderTopBar() {
    return render(
      <TopBar theme="dark" onToggleTheme={() => {}} route={{ kind: "editor", project: "motor", model: "iconic" }} />,
    );
  }

  it("lists this project's models, marks the open one and closes on Escape", async () => {
    openEditor();
    const urls = installBackend();
    renderTopBar();

    const button = screen.getByTestId("open-project");
    expect(button.textContent).toContain("iconic");
    button.focus();
    fireEvent.click(button);
    const menu = await screen.findByTestId("model-menu");
    await waitFor(() => expect(menu.getAttribute("data-state")).toBe("ready"));
    // Only the open project's models: no project list.
    expect(urls).toContain("GET /api/projects/motor/models");
    expect(urls.some((url) => url === "GET /api/projects")).toBe(false);
    expect(within(menu).queryByTestId("open-project-list")).toBeNull();

    const current = within(menu).getByTestId("model-option-iconic");
    expect(current.getAttribute("aria-current")).toBe("page");
    expect(document.activeElement).toBe(current);
    expect(within(menu).getByTestId("model-option-bondgraph").getAttribute("aria-current")).toBeNull();

    // Arrow keys move between the cards.
    fireEvent.keyDown(current, { key: "ArrowRight" });
    expect(document.activeElement).toBe(within(menu).getByTestId("model-option-bondgraph"));

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByTestId("model-menu")).toBeNull();
    expect(document.activeElement).toBe(button);
  });

  it("Ctrl+O opens the model menu inside a project", async () => {
    openEditor();
    installBackend();
    renderTopBar();
    fireEvent.keyDown(window, { key: "o", ctrlKey: true });
    expect(await screen.findByTestId("model-menu")).toBeTruthy();
    expect(screen.queryByTestId("open-dialog")).toBeNull();
  });

  it("switches to another model when everything is saved", async () => {
    openEditor();
    installBackend();
    renderTopBar();
    fireEvent.click(screen.getByTestId("open-project"));
    fireEvent.click(await screen.findByTestId("model-option-bondgraph"));
    await waitFor(() => expect(assign).toHaveBeenCalledTimes(1));
    expect(new URL(String(assign.mock.calls[0]?.[0])).searchParams.get("model")).toBe("bondgraph");
  });

  it("asks first when other work is unsaved, then switches on Save and leave", async () => {
    openEditor();
    installBackend();
    const save = vi.fn(async () => true);
    const unregister = registerUnsavedWork("code-tab", () => ({ label: "the library block “Foo”", save }));
    renderTopBar();

    fireEvent.click(screen.getByTestId("open-project"));
    fireEvent.click(await screen.findByTestId("model-option-bondgraph"));
    const dialog = await screen.findByTestId("leave-project-dialog");
    expect(within(dialog).getByRole("heading").textContent).toBe("Open another model?");
    expect(dialog.textContent).toContain("Foo");
    expect(screen.queryByTestId("model-menu")).toBeNull();
    expect(assign).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("leave-project-save"));
    await waitFor(() => expect(assign).toHaveBeenCalledTimes(1));
    expect(save).toHaveBeenCalledTimes(1);
    expect(new URL(String(assign.mock.calls[0]?.[0])).searchParams.get("model")).toBe("bondgraph");
    unregister();
  });

  it("the project name opens the model picker; another project goes through the start page", async () => {
    openEditor();
    installBackend();
    render(
      <>
        <TopBar theme="dark" onToggleTheme={() => {}} route={{ kind: "editor", project: "motor", model: "iconic" }} />
        <LeaveProjectDialog />
      </>,
    );

    fireEvent.click(screen.getByTestId("project-crumb"));
    await waitFor(() => expect(assign).toHaveBeenCalledTimes(1));
    const picker = new URL(String(assign.mock.calls[0]?.[0]));
    expect(picker.searchParams.get("project")).toBe("motor");
    expect(picker.searchParams.has("model")).toBe(false);

    fireEvent.click(screen.getByTestId("open-project"));
    await screen.findByTestId("model-option-iconic");
    act(() => {
      fireEvent.click(screen.getByTestId("model-menu-home"));
    });
    expect(assign).toHaveBeenCalledTimes(2);
    const home = new URL(String(assign.mock.calls[1]?.[0]));
    expect(home.searchParams.has("project")).toBe(false);
  });
});
