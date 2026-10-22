/**
 * The library browser and its typed drag payload (plan 7.2/3.2).
 */

import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog } from "../src/contracts/catalog";
import { resetCatalogStore, useCatalogStore } from "../src/library/catalogStore";
import { LibraryBrowser } from "../src/library/LibraryBrowser";
import {
  BLOCK_DRAG_MIME,
  parseDragPayload,
  payloadForBlock,
  readDragPayload,
  writeDragPayload,
} from "../src/library/dnd";

const catalog = catalogJson as unknown as Catalog;

function fakeDataTransfer() {
  const data = new Map<string, string>();
  return {
    data,
    transfer: {
      effectAllowed: "none",
      setData(format: string, value: string) {
        data.set(format, value);
      },
      getData(format: string) {
        return data.get(format) ?? "";
      },
    } as unknown as DataTransfer,
  };
}

beforeEach(() => {
  resetCatalogStore();
  useCatalogStore.getState().setCatalog(catalog);
});

describe("library browser", () => {
  it("renders the catalog groups plus the junction group", () => {
    const { container } = render(<LibraryBrowser />);
    const groups = [...container.querySelectorAll(".library-group")].map(
      (group) => group.getAttribute("data-testid"),
    );
    expect(groups).toEqual([
      "library-group-Bond graph",
      "library-group-Sources and sinks",
      "library-group-Continuous",
      "library-group-Electrical",
      "library-group-Translation",
      "library-group-Rotation",
      "library-group-Converters and sensors",
      "library-group-Junctions",
    ]);
  });

  it("lists all 36 catalog blocks and both junctions", () => {
    render(<LibraryBrowser />);
    expect(screen.getAllByTestId(/^library-item-/)).toHaveLength(38);
    expect(screen.getByTestId("library-count").textContent).toBe("38");
    expect(screen.getByTestId("library-item-DCMotor")).toBeTruthy();
    expect(screen.getByTestId("library-item-junction-0")).toBeTruthy();
    expect(screen.getByTestId("library-item-junction-1")).toBeTruthy();
  });

  it("filters by name while typing", () => {
    render(<LibraryBrowser />);
    const search = screen.getByTestId("library-search");
    fireEvent.change(search, { target: { value: "motor" } });
    expect(screen.getAllByTestId(/^library-item-/)).toHaveLength(1);
    expect(screen.getByTestId("library-item-DCMotor")).toBeTruthy();
    expect(screen.getByTestId("library-count").textContent).toBe("1");
  });

  it("searches descriptions and refs too, and shows an empty result", () => {
    render(<LibraryBrowser />);
    const search = screen.getByTestId("library-search");
    fireEvent.change(search, { target: { value: "converters/dcmotor" } });
    expect(screen.getByTestId("library-item-DCMotor")).toBeTruthy();

    fireEvent.change(search, { target: { value: "no-such-block" } });
    expect(screen.queryAllByTestId(/^library-item-/)).toHaveLength(0);
    expect(screen.getByTestId("library-empty").textContent).toContain("no-such-block");
  });

  it("shows the parameter and port summary in the details", () => {
    render(<LibraryBrowser />);
    const item = screen.getByTestId("library-item-DCMotor");
    fireEvent.click(within(item).getByRole("button"));
    expect(within(item).getByText(/Permanent-magnet DC motor/)).toBeTruthy();
    expect(within(item).getByText("2.0")).toBeTruthy();
    expect(within(item).getByText("k_t")).toBeTruthy();
    const portTexts = [...item.querySelectorAll(".library-item__ports li")].map(
      (line) => line.textContent ?? "",
    );
    expect(portTexts.some((text) => text.includes("shaft · power"))).toBe(true);
    expect(portTexts.some((text) => text.includes("housing · power"))).toBe(true);
  });

  it("renders bond-graph letters in a serif glyph and iconic blocks as SVG", () => {
    render(<LibraryBrowser />);
    const capacitor = screen.getByTestId("library-item-C");
    expect(capacitor.querySelector(".bond-letter")?.textContent).toBe("C");
    const motor = screen.getByTestId("library-item-DCMotor");
    expect(motor.querySelector("svg[data-icon='conv-dc-motor']")).toBeTruthy();
  });

  it("shows a loading state when no catalog is loaded", () => {
    resetCatalogStore();
    useCatalogStore.getState().setLoading();
    render(<LibraryBrowser />);
    expect(screen.getByTestId("library-loading").textContent).toContain("Loading the library");
  });
});

describe("drag payload", () => {
  it("round-trips a block ref through the typed MIME type", () => {
    const se = catalog.blocks.find((block) => block.name === "Se");
    if (se === undefined) {
      throw new Error("catalog has no Se block");
    }
    const { transfer, data } = fakeDataTransfer();
    writeDragPayload(transfer, payloadForBlock(se));
    expect(data.get(BLOCK_DRAG_MIME)).toContain("stdlib:");
    expect(data.get("text/plain")).toBe(se.ref);
    expect(readDragPayload(transfer)).toEqual({ kind: "block", ref: se.ref });
  });

  it("round-trips a junction", () => {
    const { transfer } = fakeDataTransfer();
    writeDragPayload(transfer, { kind: "junction", junction: "1" });
    expect(readDragPayload(transfer)).toEqual({ kind: "junction", junction: "1" });
  });

  it("ignores a malformed payload", () => {
    expect(parseDragPayload("not json")).toBeNull();
    expect(parseDragPayload('{"kind":"block"}')).toBeNull();
    expect(parseDragPayload('{"kind":"junction","junction":"2"}')).toBeNull();
    expect(parseDragPayload(null)).toBeNull();
    const { transfer } = fakeDataTransfer();
    expect(readDragPayload(transfer)).toBeNull();
  });
});
