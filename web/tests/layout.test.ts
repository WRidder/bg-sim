/**
 * Splitter persistence (plan 7.2): layouts live in localStorage under
 * `bgsim.layout.<key>`, every access is wrapped in try/catch, and a junk value
 * falls back to the default layout.
 */

import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { readPanelSizes, usePersistedPanelSizes, writePanelSizes } from "../src/state/layout";

beforeEach(() => {
  localStorage.clear();
});

describe("panel layout persistence", () => {
  it("round-trips a layout through localStorage", () => {
    writePanelSizes("test", { library: 30, center: 70 });

    expect(localStorage.getItem("bgsim.layout.test")).toBe('{"library":30,"center":70}');
    expect(readPanelSizes("test")).toEqual({ library: 30, center: 70 });
  });

  it("returns null for missing, malformed or empty layouts", () => {
    expect(readPanelSizes("missing")).toBeNull();

    localStorage.setItem("bgsim.layout.test", "not json");
    expect(readPanelSizes("test")).toBeNull();

    localStorage.setItem("bgsim.layout.test", JSON.stringify(["50", "50"]));
    expect(readPanelSizes("test")).toBeNull();

    localStorage.setItem("bgsim.layout.test", JSON.stringify({ library: "wide" }));
    expect(readPanelSizes("test")).toBeNull();

    localStorage.setItem("bgsim.layout.test", JSON.stringify({ library: -3 }));
    expect(readPanelSizes("test")).toBeNull();

    localStorage.setItem("bgsim.layout.test", JSON.stringify({}));
    expect(readPanelSizes("test")).toBeNull();
  });

  it("never throws when storage is unavailable", () => {
    const denied = {
      getItem: () => {
        throw new Error("storage denied");
      },
      setItem: () => {
        throw new Error("storage denied");
      },
    };

    expect(readPanelSizes("test", denied)).toBeNull();
    expect(() => writePanelSizes("test", { a: 50, b: 50 }, denied)).not.toThrow();
  });

  it("reads a stored layout once and writes every change", () => {
    localStorage.setItem("bgsim.layout.hook", JSON.stringify({ a: 40, b: 60 }));

    const { result } = renderHook(() => usePersistedPanelSizes("hook", { a: 50, b: 50 }));
    expect(result.current.defaultLayout).toEqual({ a: 40, b: 60 });

    act(() => result.current.onLayoutChanged({ a: 25, b: 75 }));
    expect(readPanelSizes("hook")).toEqual({ a: 25, b: 75 });
  });

  it("falls back to the default layout when nothing is stored", () => {
    const { result } = renderHook(() => usePersistedPanelSizes("hook", { a: 50, b: 50 }));
    expect(result.current.defaultLayout).toEqual({ a: 50, b: 50 });
  });
});
