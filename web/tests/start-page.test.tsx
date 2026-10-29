/**
 * The start page (W5.4): shown without `?project=`, with the example gallery,
 * recent projects and New project. Samples import through the create-from-example
 * flow; an example without a thumbnail gets the neutral placeholder card.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/app/App";
import { navigation } from "../src/app/openSession";
import { hasProjectRoute } from "../src/app/route";
import { exampleInfo, galleryExamples, titleFromName } from "../src/examples/gallery";
import { resetCatalogStore } from "../src/library/catalogStore";
import { resetDocumentStore } from "../src/state/documentStore";
import { resetSessionCache } from "../src/state/session";

interface Call {
  method: string;
  url: string;
  body: unknown;
}

const calls: Call[] = [];

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function installBackend(options: { examples: string[]; projects: unknown[] }): void {
  vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.pathname : input.url;
    const method = init?.method ?? "GET";
    const body = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
    calls.push({ method, url, body });
    if (url === "/api/examples") {
      return json({ examples: options.examples });
    }
    if (url === "/api/projects" && method === "GET") {
      return json({ projects: options.projects });
    }
    if (url === "/api/projects" && method === "POST") {
      const name = (body as { name: string }).name;
      return json(
        {
          name,
          path: `/projects/${name}`,
          language: "0.1.0",
          models: [{ name: "iconic", inProject: true }],
          modified: null,
          valid: true,
          error: null,
        },
        201,
      );
    }
    return json({}, 404);
  });
}

beforeEach(() => {
  calls.length = 0;
  window.history.replaceState(null, "", "/");
  resetDocumentStore();
  resetCatalogStore();
  resetSessionCache();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("route", () => {
  it("only a non-empty project parameter selects the editor", () => {
    expect(hasProjectRoute("")).toBe(false);
    expect(hasProjectRoute("?model=a")).toBe(false);
    expect(hasProjectRoute("?project=")).toBe(false);
    expect(hasProjectRoute("?project=demo")).toBe(true);
  });
});

describe("example gallery data", () => {
  it("does not make a card of a tooling directory", () => {
    expect(galleryExamples(["__pycache__", ".hidden", "dc-motor"])).toEqual(["dc-motor"]);
  });

  it("falls back to a readable title and description for an unknown example", () => {
    expect(titleFromName("reaction-wheel_2d")).toBe("Reaction wheel 2d");
    const info = exampleInfo("zz-brand-new-example");
    expect(info.title).toBe("Zz brand new example");
    expect(info.description.length).toBeGreaterThan(10);
    expect(info.thumbnail).toBeNull();
  });
});

describe("start page", () => {
  it("replaces the editor when no project is in the URL", async () => {
    installBackend({ examples: ["dc-motor"], projects: [] });
    render(<App />);

    expect(await screen.findByTestId("start-page")).toBeTruthy();
    expect(screen.queryByTestId("left-panel")).toBeNull();
    expect(screen.queryByTestId("bottom-dock")).toBeNull();
    // The top bar stays, so Open (Ctrl+O) works from the start page.
    expect(screen.getByTestId("open-project")).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByTestId("start-page").getAttribute("data-state")).toBe("ready"),
    );
  });

  it("shows the editor, not the start page, when a project is in the URL", () => {
    window.history.replaceState(null, "", "/?project=demo&model=Model1");
    vi.stubGlobal("fetch", () => new Promise(() => {}));
    render(<App />);
    expect(screen.queryByTestId("start-page")).toBeNull();
    expect(screen.getByTestId("left-panel")).toBeTruthy();
  });

  it("lists a card per example with a placeholder when there is no thumbnail", async () => {
    installBackend({ examples: ["zz-brand-new-example", "another-new-one"], projects: [] });
    render(<App />);

    const card = await screen.findByTestId("example-card-zz-brand-new-example");
    expect(within(card).getByRole("heading", { name: "Zz brand new example" })).toBeTruthy();
    expect(within(card).getByTestId("example-placeholder-zz-brand-new-example")).toBeTruthy();
    expect(within(card).queryByRole("img")).toBeNull();
    expect(screen.getByTestId("example-card-another-new-one")).toBeTruthy();
  });

  it("guides the user when there are no projects or no samples", async () => {
    installBackend({ examples: [], projects: [] });
    render(<App />);
    expect((await screen.findByTestId("recent-empty")).textContent).toMatch(/Create one/);
    expect(screen.getByTestId("gallery-empty").textContent).toMatch(/Create an empty project/);
  });

  it("lists the most recent projects first and opens one", async () => {
    installBackend({
      examples: [],
      projects: [
        { name: "old", path: "", language: "0.1.0", models: ["a"], modified: "2026-01-01T00:00:00Z", valid: true, error: null },
        { name: "fresh", path: "", language: "0.1.0", models: ["m1", "m2"], modified: "2026-09-01T00:00:00Z", valid: true, error: null },
      ],
    });
    const assign = vi.spyOn(navigation, "assign").mockImplementation(() => {});
    render(<App />);

    const list = await screen.findByTestId("recent-projects");
    const names = within(list)
      .getAllByRole("button")
      .map((button) => button.getAttribute("data-testid"));
    expect(names).toEqual(["recent-project-fresh", "recent-project-old"]);

    fireEvent.click(screen.getByTestId("recent-project-fresh"));
    await waitFor(() => expect(assign).toHaveBeenCalledTimes(1));
    const target = new URL(assign.mock.calls[0]?.[0] ?? "");
    expect(target.searchParams.get("project")).toBe("fresh");
    expect(target.searchParams.get("model")).toBe("m1");
  });

  it("imports a sample as a copy through the create-from-example flow", async () => {
    installBackend({
      examples: ["dc-motor"],
      projects: [{ name: "dc-motor", path: "", language: "0.1.0", models: ["iconic"], modified: null, valid: true, error: null }],
    });
    const assign = vi.spyOn(navigation, "assign").mockImplementation(() => {});
    render(<App />);

    fireEvent.click(await screen.findByTestId("example-open-dc-motor"));
    await waitFor(() => expect(assign).toHaveBeenCalledTimes(1));

    const post = calls.find((call) => call.method === "POST");
    // The existing project keeps its name; the copy gets the next free one.
    expect(post?.body).toEqual({ name: "dc-motor-2", example: "dc-motor" });
    const target = new URL(assign.mock.calls[0]?.[0] ?? "");
    expect(target.searchParams.get("project")).toBe("dc-motor-2");
    expect(target.searchParams.get("model")).toBe("iconic");
  });

  it("creates a new project from the name field and rejects an invalid name", async () => {
    installBackend({ examples: [], projects: [] });
    const assign = vi.spyOn(navigation, "assign").mockImplementation(() => {});
    render(<App />);

    const input = await screen.findByTestId("start-new-project-name");
    fireEvent.change(input, { target: { value: "bad name!" } });
    fireEvent.click(screen.getByTestId("start-create-project"));
    expect((await screen.findByTestId("start-page-error")).textContent).toMatch(/letters, digits/);
    expect(calls.some((call) => call.method === "POST")).toBe(false);

    fireEvent.change(input, { target: { value: "my-motor" } });
    fireEvent.click(screen.getByTestId("start-create-project"));
    await waitFor(() => expect(assign).toHaveBeenCalledTimes(1));
    expect(calls.find((call) => call.method === "POST")?.body).toEqual({ name: "my-motor" });
  });
});
