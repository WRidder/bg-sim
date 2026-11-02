/**
 * Project docs (`<project>/docs/`): the second wiki of the Docs tab (a Project section above
 * This model), `project:` and `model:` links, the project page's Docs tab (every page of the
 * project in one tree with a reading pane) and the URLs that deep-link into both.
 */

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/app/App";
import { ModelPicker } from "../src/app/ModelPicker";
import { navigation } from "../src/app/openSession";
import { modelDocsUrl, projectTabUrl, projectUrl, readScreenTab } from "../src/app/route";
import * as api from "../src/docs/docsApi";
import { DocsTab, resetDocsUrlPage } from "../src/docs/DocsTab";
import { assetUrl, planPaste } from "../src/docs/docsImages";
import {
  resetDocsStore,
  useDocsStore,
  useDocsViewStore,
  useProjectDocsStore,
} from "../src/docs/docsStore";
import { hasUnsavedDocs } from "../src/docs/leaveGuard";
import { MarkdownView, type LinkActions } from "../src/docs/MarkdownView";
import type { Docs, DocsPage } from "../src/docs/pageTree";
import { resetCatalogStore } from "../src/library/catalogStore";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";
import { resetSessionCache } from "../src/state/session";

function page(id: string, children: DocsPage[] = []): DocsPage {
  return { id, title: id.toUpperCase(), file: `pages/${id}.md`, children };
}

function tree(...pages: DocsPage[]): Docs {
  return { format: "bgsim.docs", version: 1, pages };
}

const EMPTY = tree();

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// --------------------------------------------------------------------------- Docs tab

describe("Docs tab with project docs", () => {
  let projectDocs: Docs;
  let assign: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    window.history.replaceState(null, "", "/?project=demo&model=m");
    resetDocsStore();
    resetDocsUrlPage();
    resetDocumentStore();
    projectDocs = tree(page("rig", [page("safety")]));
    const texts: Record<string, string> = {
      "m/a": "Model page. See [the rig](project:rig), [ghost](project:ghost) and [other](model:Other/intro).",
      ":project/rig": "Rig page. Back to [the model](model:m/a); [nope](block:Motor).",
      ":project/safety": "Safety.",
    };
    vi.spyOn(api, "fetchManifest").mockImplementation(async (_p, model) =>
      structuredClone(model === null ? projectDocs : tree(page("a"))),
    );
    vi.spyOn(api, "listAssets").mockResolvedValue({ assets: [], unused: 0 });
    vi.spyOn(api, "fetchPage").mockImplementation(async (_p, model, id) => texts[`${model ?? ":project"}/${id}`] ?? "");
    vi.spyOn(api, "saveManifest").mockImplementation(async (_p, _m, docs) => docs);
    vi.spyOn(api, "savePage").mockResolvedValue();
    vi.spyOn(api, "fetchDocsIndex").mockImplementation(async () => ({
      project: structuredClone(projectDocs),
      models: [
        { name: "m", inProject: true, docs: tree(page("a")), error: null },
        { name: "Other", inProject: true, docs: tree(page("intro")), error: null },
      ],
    }));
    assign = vi.spyOn(navigation, "assign").mockImplementation(() => {});
    useDocumentStore.setState({ project: "demo", modelName: "m", doc: createEmptyModel("m") });
  });

  async function renderTab(): Promise<void> {
    render(<DocsTab onShowDiagram={() => undefined} />);
    await screen.findByText("Model page.", { exact: false });
  }

  it("shows a Project section above This model and starts on the model's first page", async () => {
    await renderTab();
    const project = screen.getByTestId("docs-section-project");
    const model = screen.getByTestId("docs-section-model");
    expect(project.compareDocumentPosition(model) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(project).getByRole("tree", { name: "Project pages" })).toBeTruthy();
    expect(within(model).getByRole("tree", { name: "Pages of this model" })).toBeTruthy();
    expect(screen.getByTestId("docs-tree-item-a").getAttribute("aria-selected")).toBe("true");
    expect(screen.getByTestId("project-docs-tree-item-rig").getAttribute("aria-selected")).toBe("false");
    expect(screen.getByTestId("docs-tab").dataset.wiki).toBe("model");
    expect(screen.getByTestId("docs-crumbs").textContent).toBe("Project docs / m / A");
    expect(screen.queryByTestId("docs-add-project")).toBeNull();
  });

  it("opens project pages from the tree, the breadcrumb and project: links", async () => {
    await renderTab();
    fireEvent.click(screen.getByText("the rig"));
    await screen.findByText("Rig page.", { exact: false });
    expect(screen.getByTestId("docs-tab").dataset.wiki).toBe("project");
    expect(screen.getByTestId("project-docs-tree-item-rig").getAttribute("aria-selected")).toBe("true");
    expect(screen.getByTestId("docs-tree-item-a").getAttribute("aria-selected")).toBe("false");
    expect(screen.getByTestId("docs-crumbs").textContent).toBe("Project docs / RIG");

    // model:<this model>/<id> comes back to the model's own page.
    fireEvent.click(screen.getByText("the model"));
    await screen.findByText("Model page.", { exact: false });
    expect(screen.getByTestId("docs-tab").dataset.wiki).toBe("model");

    fireEvent.click(screen.getByTestId("project-docs-tree-item-safety"));
    await screen.findByText("Safety.");
    fireEvent.click(screen.getByTestId("docs-tree-item-a"));
    await screen.findByText("Model page.", { exact: false });
    fireEvent.click(screen.getByTestId("docs-crumbs-project"));
    await screen.findByText("Rig page.", { exact: false });
  });

  it("marks broken links with the reason and keeps block links out of the project docs", async () => {
    await renderTab();
    const ghost = screen.getByText("ghost").closest("[data-testid='docs-broken-link']");
    expect(ghost?.getAttribute("title")).toContain('no page "ghost" in the project docs');
    await act(async () => {
      await useDocsViewStore.getState().setWiki("project");
      await useProjectDocsStore.getState().select("rig");
    });
    await screen.findByText("Rig page.", { exact: false });
    const block = screen.getByText("nope").closest("[data-testid='docs-broken-link']");
    expect(block?.getAttribute("title")).toContain("Block links work in a model's docs only");
  });

  it("opens another model's docs page through the editor URL", async () => {
    await renderTab();
    fireEvent.click(screen.getByText("other"));
    await waitFor(() => expect(assign).toHaveBeenCalled());
    const url = new URL(String(assign.mock.calls[0]?.[0]));
    expect(url.searchParams.get("model")).toBe("Other");
    expect(url.searchParams.get("tab")).toBe("docs");
    expect(url.searchParams.get("page")).toBe("intro");
  });

  it("edits both wikis: new pages go to the section they are made in", async () => {
    await renderTab();
    fireEvent.click(screen.getByTestId("project-docs-new-page"));
    await waitFor(() => expect(api.saveManifest).toHaveBeenCalled());
    const [projectArg, modelArg, saved] = vi.mocked(api.saveManifest).mock.calls[0]!;
    expect([projectArg, modelArg]).toEqual(["demo", null]);
    expect(saved.pages.map((p) => p.id)).toEqual(["rig", "new-page"]);
    expect(screen.getByTestId("docs-tab").dataset.wiki).toBe("project");

    fireEvent.click(screen.getByTestId("docs-new-page"));
    await waitFor(() => expect(api.saveManifest).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.saveManifest).mock.calls[1]?.[1]).toBe("m");
    expect(screen.getByTestId("docs-tab").dataset.wiki).toBe("model");

    useProjectDocsStore.getState().setDraft("rig", "changed");
    expect(hasUnsavedDocs()).toBe(true);
  });

  it("collapses the Project section and remembers it", async () => {
    await renderTab();
    const toggle = screen.getByTestId("docs-section-project-toggle");
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(toggle);
    expect(screen.queryByTestId("project-docs-tree")).toBeNull();
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(localStorage.getItem("bgsim.docs.projectOpen")).toBe("false");
    fireEvent.click(toggle);
    expect(screen.getByTestId("project-docs-tree")).toBeTruthy();
  });

  it("opens the page the URL names (tab=docs&page=project:<id>)", async () => {
    window.history.replaceState(null, "", "/?project=demo&model=m&tab=docs&page=project:safety");
    render(<DocsTab onShowDiagram={() => undefined} />);
    await screen.findByText("Safety.");
    expect(screen.getByTestId("docs-tab").dataset.wiki).toBe("project");
  });

  it("without project docs shows only the model section and an Add project docs link", async () => {
    projectDocs = EMPTY;
    await renderTab();
    expect(screen.queryByTestId("docs-section-project")).toBeNull();
    expect(screen.queryByTestId("docs-section-model")).toBeNull();
    expect(screen.getByRole("tree", { name: "Pages" })).toBeTruthy();
    expect(screen.getByTestId("docs-crumbs").textContent).toBe("A");
    // The broken project: link says why.
    const rig = screen.getByText("the rig").closest("[data-testid='docs-broken-link']");
    expect(rig?.getAttribute("title")).toContain("no project docs yet");

    fireEvent.click(screen.getByTestId("docs-add-project"));
    await screen.findByTestId("docs-section-project");
    const [, model, saved] = vi.mocked(api.saveManifest).mock.calls[0]!;
    expect(model).toBeNull();
    expect(saved.pages.map((p) => p.title)).toEqual(["Overview"]);
    expect(screen.getByTestId("docs-tab").dataset.wiki).toBe("project");
  });

  it("starts on the project docs when the model has none of its own", async () => {
    vi.mocked(api.fetchManifest).mockImplementation(async (_p, model) =>
      structuredClone(model === null ? projectDocs : EMPTY),
    );
    render(<DocsTab onShowDiagram={() => undefined} />);
    await screen.findByText("Rig page.", { exact: false });
    expect(screen.getByTestId("docs-create-first")).toBeTruthy();
  });
});

describe("project docs plumbing", () => {
  it("the project docs store loads and saves through the project-docs API", async () => {
    resetDocsStore();
    const fetchManifest = vi.spyOn(api, "fetchManifest").mockResolvedValue(tree(page("rig")));
    vi.spyOn(api, "listAssets").mockResolvedValue({ assets: [], unused: 0 });
    vi.spyOn(api, "fetchPage").mockResolvedValue("text");
    const savePage = vi.spyOn(api, "savePage").mockResolvedValue();
    await useProjectDocsStore.getState().load("demo", "ignored");
    expect(fetchManifest).toHaveBeenCalledWith("demo", null);
    expect(useProjectDocsStore.getState().model).toBeNull();
    expect(useProjectDocsStore.getState().selected).toBe("rig");
    useProjectDocsStore.getState().setDraft("rig", "new");
    expect(await useProjectDocsStore.getState().saveAll()).toBe(true);
    expect(savePage).toHaveBeenCalledWith("demo", null, "rig", "new");
    // The model store is a separate wiki.
    expect(useDocsStore.getState().project).toBeNull();
  });

  it("names the project docs folder in asset and API URLs", () => {
    expect(assetUrl("demo", null, "0123456789ab.png")).toBe("/api/projects/demo/project-docs/assets/0123456789ab.png");
    expect(assetUrl("demo", "m", "0123456789ab.png")).toBe("/api/projects/demo/docs/m/assets/0123456789ab.png");
    expect(api.docsPath("a b", null)).toBe("/api/projects/a%20b/project-docs");
  });

  it("copies images when Markdown moves between the project docs and a model's docs", () => {
    const text = "![](assets/0123456789ab.png)";
    const custom = JSON.stringify({ project: "demo", model: null, text });
    expect(planPaste({ files: [], text, custom, remembered: null, target: { project: "demo", model: "m" } })).toEqual({
      kind: "copy-assets",
      from: { project: "demo", model: null },
      files: ["0123456789ab.png"],
    });
    expect(planPaste({ files: [], text, custom, remembered: null, target: { project: "demo", model: null } }).kind).toBe(
      "default",
    );
  });

  it("renders project images from the project docs and follows project: links", () => {
    const actions: LinkActions = {
      openPage: vi.fn(),
      openProjectPage: vi.fn(),
      openModelPage: vi.fn(),
      showBlock: vi.fn(),
      plotSignal: vi.fn(),
      notify: vi.fn(),
    };
    const { container } = render(
      <MarkdownView
        text="![x](assets/0123456789ab.png) [r](project:rig) [m](model:Plant)"
        project="demo"
        model={null}
        links={{
          pageIds: new Set(),
          model: null,
          signalIds: null,
          wiki: "project",
          projectPageIds: new Set(["rig"]),
          modelPages: new Map([["Plant", ["overview"]]]),
        }}
        actions={actions}
      />,
    );
    expect(container.querySelector("img")?.getAttribute("src")).toBe("/api/projects/demo/project-docs/assets/0123456789ab.png");
    fireEvent.click(screen.getByText("r"));
    expect(actions.openProjectPage).toHaveBeenCalledWith("rig");
    fireEvent.click(screen.getByText("m"));
    expect(actions.openModelPage).toHaveBeenCalledWith("Plant", "overview");
  });

  it("builds and reads the deep-link URLs", () => {
    const here = "http://localhost:5173/?project=a&model=b&theme=dark&tab=x&page=y";
    expect(modelDocsUrl("p", "m", "project:rig", here)).toBe(
      "http://localhost:5173/?project=p&model=m&theme=dark&tab=docs&page=project%3Arig",
    );
    expect(projectTabUrl("p", "docs", "model:m/a", here)).toBe(
      "http://localhost:5173/?project=p&theme=dark&tab=docs&page=model%3Am%2Fa",
    );
    expect(projectUrl("p", here)).toBe("http://localhost:5173/?project=p&theme=dark");
    expect(readScreenTab("?project=p&tab=docs&page=project%3Arig")).toEqual({ tab: "docs", page: "project:rig" });
    expect(readScreenTab("?project=p")).toEqual({ tab: null, page: null });
  });
});

describe("editor deep link", () => {
  it("tab=docs opens the editor on its Docs tab and still opens the model", async () => {
    window.history.replaceState(null, "", "/?project=demo&model=Model1&tab=docs&page=project:rig");
    resetDocumentStore();
    resetCatalogStore();
    resetSessionCache();
    resetDocsStore();
    const urls: string[] = [];
    vi.stubGlobal("fetch", (input: RequestInfo | URL) => {
      urls.push(typeof input === "string" ? input : input instanceof URL ? input.pathname : input.url);
      return new Promise<Response>(() => {});
    });
    render(<App />);
    const editor = screen.getByRole("tablist", { name: "Editor" });
    expect(within(editor).getByRole("tab", { name: "Docs" }).getAttribute("aria-selected")).toBe("true");
    // The session starts without the Diagram tab ever being shown.
    await waitFor(() => expect(urls.some((url) => url.startsWith("/api/projects/demo"))).toBe(true));
  });
});

// --------------------------------------------------------------------------- project page

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

const CARDS = [
  { name: "iconic", modified: null, inProject: true, description: "A motor.", thumbnail: null, nodes: 0, preview: { nodes: [], links: [] }, error: null },
  { name: "bondgraph", modified: null, inProject: true, description: null, thumbnail: null, nodes: 0, preview: { nodes: [], links: [] }, error: null },
];

const INDEX = {
  project: tree(page("rig", [page("safety")])),
  models: [
    { name: "iconic", inProject: true, docs: tree(page("intro")), error: null },
    { name: "bondgraph", inProject: true, docs: tree(), error: null },
  ],
};

const PAGES: Record<string, string> = {
  "/api/projects/motor/project-docs/pages/rig": "Shared rig notes. See [the motor](model:iconic) and [safety](page:safety); [gone](model:bondgraph).",
  "/api/projects/motor/project-docs/pages/safety": "Safety first.",
  "/api/projects/motor/docs/iconic/pages/intro": "Iconic intro. Back to [the rig](project:rig); [b](block:Motor).",
};

describe("project page tabs", () => {
  let assign: ReturnType<typeof vi.spyOn>;
  let urls: string[];

  beforeEach(() => {
    window.history.replaceState(null, "", "/?project=motor");
    localStorage.clear();
    resetDocsStore();
    resetDocumentStore();
    urls = [];
    vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.pathname : input.url;
      urls.push(url);
      if (url === "/api/projects/motor/models") {
        return json({ name: "motor", models: CARDS });
      }
      if (url === "/api/projects/motor/docs-index") {
        return json(INDEX);
      }
      const text = PAGES[url];
      if (text !== undefined) {
        return new Response(text, { status: 200, headers: { "content-type": "text/markdown" } });
      }
      return new Promise<Response>(() => {});
    });
    assign = vi.spyOn(navigation, "assign").mockImplementation(() => {});
  });

  it("opens on Models and loads no docs until the Docs tab is chosen", async () => {
    render(<ModelPicker project="motor" />);
    await screen.findByText("A motor.");
    const tabs = screen.getByRole("tablist", { name: "Project" });
    expect(within(tabs).getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Models", "Docs"]);
    expect(screen.getByRole("tab", { name: "Models" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByTestId("picker-panel-models")).toBeTruthy();
    expect(urls.some((url) => url.includes("docs"))).toBe(false);
  });

  it("shows every page of the project in one tree and reads the selected one", async () => {
    render(<ModelPicker project="motor" />);
    await screen.findByText("A motor.");
    fireEvent.click(screen.getByRole("tab", { name: "Docs" }));
    await screen.findByText("Shared rig notes.", { exact: false });
    expect(window.location.search).toBe("?project=motor&tab=docs");

    const tree = screen.getByTestId("project-docs-tree");
    const groups = within(tree).getAllByRole("heading").map((heading) => heading.textContent);
    expect(groups).toEqual(["Project", "iconic", "bondgraph · no docs"]);
    expect(screen.getByTestId("project-docs-group-bondgraph").dataset.empty).toBe("true");
    expect(screen.getByTestId("project-docs-page-:project-rig").getAttribute("aria-current")).toBe("page");

    // Links navigate within the view; the URL follows.
    fireEvent.click(screen.getByText("safety"));
    await screen.findByText("Safety first.");
    expect(readScreenTab().page).toBe("project:safety");
    fireEvent.click(screen.getByTestId("project-docs-page-:project-rig"));
    await screen.findByText("Shared rig notes.", { exact: false });
    const gone = screen.getByText("gone").closest("[data-testid='docs-broken-link']");
    expect(gone?.getAttribute("title")).toContain("has no docs yet");
    fireEvent.click(screen.getByText("the motor"));
    await screen.findByText("Iconic intro.", { exact: false });
    expect(readScreenTab()).toEqual({ tab: "docs", page: "model:iconic/intro" });
    expect(screen.getByTestId("project-docs-crumbs").textContent).toBe("iconic / INTRO");
    // Block links need the model open.
    const block = screen.getByText("b").closest("[data-testid='docs-broken-link']");
    expect(block?.getAttribute("title")).toContain("Open the model");
  });

  it("edits a model page in the model's Docs tab and a project page in the first model's", async () => {
    window.history.replaceState(null, "", "/?project=motor&tab=docs&page=model:iconic/intro");
    render(<ModelPicker project="motor" />);
    await screen.findByText("Iconic intro.", { exact: false });
    const edit = new URL((screen.getByTestId("project-docs-edit") as HTMLAnchorElement).href);
    expect([edit.searchParams.get("model"), edit.searchParams.get("tab"), edit.searchParams.get("page")]).toEqual([
      "iconic",
      "docs",
      "intro",
    ]);
    fireEvent.click(screen.getByTestId("project-docs-edit"));
    expect(assign).toHaveBeenCalledWith(edit.toString());
    expect(new URL((screen.getByTestId("project-docs-open-model") as HTMLAnchorElement).href).searchParams.get("tab")).toBeNull();

    fireEvent.click(screen.getByText("the rig"));
    await screen.findByText("Shared rig notes.", { exact: false });
    const projectEdit = new URL((screen.getByTestId("project-docs-edit") as HTMLAnchorElement).href);
    expect(projectEdit.searchParams.get("model")).toBe("iconic");
    expect(projectEdit.searchParams.get("page")).toBe("project:rig");
    expect(screen.queryByTestId("project-docs-open-model")).toBeNull();
  });

  it("remembers the Docs tab per project", async () => {
    const first = render(<ModelPicker project="motor" />);
    await screen.findByText("A motor.");
    fireEvent.click(screen.getByRole("tab", { name: "Docs" }));
    await screen.findByText("Shared rig notes.", { exact: false });
    first.unmount();
    window.history.replaceState(null, "", "/?project=motor");
    render(<ModelPicker project="motor" />);
    expect(screen.getByRole("tab", { name: "Docs" }).getAttribute("aria-selected")).toBe("true");
    await screen.findByText("Shared rig notes.", { exact: false });
  });
});
