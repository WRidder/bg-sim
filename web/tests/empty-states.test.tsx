/**
 * Empty states say what to do next (plan 7.8), and the shell exposes landmarks.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import { App } from "../src/app/App";
import type { Catalog } from "../src/contracts/catalog";
import { ModelTree } from "../src/editor/ModelTree";
import { resetCatalogStore, useCatalogStore } from "../src/library/catalogStore";
import { LibraryBrowser } from "../src/library/LibraryBrowser";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";
import { resetSessionCache } from "../src/state/session";

const catalog = catalogJson as unknown as Catalog;

beforeEach(() => {
  resetDocumentStore();
  resetCatalogStore();
  resetSessionCache();
  useCatalogStore.getState().setCatalog(catalog);
});

describe("empty states", () => {
  it("tells the user how to recover from a library search without a match", () => {
    render(<LibraryBrowser />);
    fireEvent.change(screen.getByTestId("library-search"), { target: { value: "zzzz-none" } });
    const message = screen.getByTestId("library-empty").textContent ?? "";
    expect(message).toContain("No block matches");
    expect(message).toMatch(/Clear the search/);
  });

  it("tells the user to drag a block when the diagram is empty", () => {
    useDocumentStore
      .getState()
      .openDocument("demo", "Model1", createEmptyModel("Model1", catalog.language), { persisted: false });
    render(<ModelTree />);
    expect(screen.getByText(/Drag a block from the library/)).toBeTruthy();
  });
});

describe("landmarks", () => {
  it("has a banner, one main landmark and a skip link to it", () => {
    window.history.replaceState(null, "", "/?project=demo&model=Model1");
    vi.stubGlobal("fetch", () => new Promise(() => {}));
    render(<App />);
    expect(screen.getAllByRole("banner")).toHaveLength(1);
    const main = screen.getAllByRole("main");
    expect(main).toHaveLength(1);
    const skip = screen.getByRole("link", { name: "Skip to the main content" });
    expect(skip.getAttribute("href")).toBe(`#${main[0]?.id}`);
    vi.unstubAllGlobals();
  });
});
