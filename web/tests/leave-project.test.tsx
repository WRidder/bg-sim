/**
 * The brand in the top bar goes back to the library (the start page); unsaved
 * work asks first with Save and leave / Leave without saving / Cancel.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LeaveProjectDialog } from "../src/app/LeaveProjectDialog";
import {
  libraryUrl,
  registerUnsavedWork,
  requestLeaveProject,
  unsavedWork,
  useLeaveProjectStore,
} from "../src/app/leaveProject";
import { navigation } from "../src/app/openSession";
import { isLeaveConfirmed } from "../src/docs/leaveGuard";
import { createEmptyModel } from "../src/state/modelFactory";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";

function openClean(): void {
  useDocumentStore.getState().openDocument("demo", "M", createEmptyModel("M"));
}

describe("leaving the project for the library", () => {
  let assign: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    resetDocumentStore();
    useLeaveProjectStore.getState().close();
    assign = vi.spyOn(navigation, "assign").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("drops project and model from the URL and keeps the rest", () => {
    expect(libraryUrl("http://localhost:5173/?project=p&model=m&theme=dark")).toBe(
      "http://localhost:5173/?theme=dark",
    );
    expect(libraryUrl("http://localhost:5173/?project=p&model=m")).toBe("http://localhost:5173/");
  });

  it("leaves straight away when everything is saved", () => {
    openClean();
    expect(unsavedWork()).toEqual([]);
    requestLeaveProject();
    expect(assign).toHaveBeenCalledTimes(1);
    expect(useLeaveProjectStore.getState().pending).toBeNull();
  });

  it("asks first when the model has an unsaved revision", () => {
    useDocumentStore
      .getState()
      .openDocument("demo", "M", createEmptyModel("M"), { persisted: false });
    requestLeaveProject();
    expect(assign).not.toHaveBeenCalled();
    expect(useLeaveProjectStore.getState().pending).toEqual(["the model “M”"]);
  });

  it("lists registered work until it unregisters", () => {
    openClean();
    const unregister = registerUnsavedWork("code-tab", () => ({
      label: "the library block “Foo”",
      save: async () => true,
    }));
    expect(unsavedWork().map((item) => item.label)).toEqual(["the library block “Foo”"]);
    unregister();
    expect(unsavedWork()).toEqual([]);
  });

  it("Save and leave saves every item, then leaves", async () => {
    openClean();
    const save = vi.fn(async () => true);
    const unregister = registerUnsavedWork("code-tab", () => ({ label: "block", save }));
    render(<LeaveProjectDialog />);
    requestLeaveProject();
    fireEvent.click(await screen.findByTestId("leave-project-save"));
    await waitFor(() => expect(assign).toHaveBeenCalledTimes(1));
    expect(save).toHaveBeenCalledTimes(1);
    unregister();
  });

  it("stays with an error when a save fails", async () => {
    openClean();
    const unregister = registerUnsavedWork("code-tab", () => ({
      label: "the library block “Foo”",
      save: async () => false,
    }));
    render(<LeaveProjectDialog />);
    requestLeaveProject();
    fireEvent.click(await screen.findByTestId("leave-project-save"));
    expect((await screen.findByTestId("leave-project-error")).textContent).toContain("Foo");
    expect(assign).not.toHaveBeenCalled();
    unregister();
  });

  it("Leave without saving leaves and silences the Docs unload prompt; Cancel stays", async () => {
    openClean();
    const unregister = registerUnsavedWork("code-tab", () => ({ label: "block", save: async () => true }));
    render(<LeaveProjectDialog />);
    requestLeaveProject();
    fireEvent.click(await screen.findByTestId("leave-project-cancel"));
    expect(screen.queryByTestId("leave-project-dialog")).toBeNull();
    expect(assign).not.toHaveBeenCalled();

    requestLeaveProject();
    fireEvent.click(await screen.findByTestId("leave-project-discard"));
    expect(assign).toHaveBeenCalledTimes(1);
    expect(isLeaveConfirmed()).toBe(true);
    unregister();
  });
});
