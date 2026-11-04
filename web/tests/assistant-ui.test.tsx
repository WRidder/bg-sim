/**
 * The assistant's chat: the transcript as a fold over events, questions, figures, Markdown with
 * math and diagrams, and the selection the assistant is shown. The real backend flow is the
 * Playwright spec and backend/tests/test_assistant_runners.py.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatChart } from "../src/assistant/ChatChart";
import { ChatMarkdown } from "../src/assistant/ChatMarkdown";
import { extentOf, formatNumber, sortOrder, thin, ticks } from "../src/assistant/chartModel";
import { normalizeChatMath } from "../src/assistant/chatMath";
import { CodeCard } from "../src/assistant/CodeCard";
import { FigureCard } from "../src/assistant/FigureCard";
import { ProposalReview } from "../src/assistant/ProposalReview";
import { QuestionCard } from "../src/assistant/QuestionCard";
import {
  diagramSelection,
  publishCodeSelection,
  selectionKey,
  selectionLabel,
  trackDocSelection,
  useAssistantSelectionStore,
} from "../src/assistant/selectionStore";
import { applyEvent, EMPTY_TRANSCRIPT, type Transcript } from "../src/assistant/transcript";
import type { AssistantEnvelope, AssistantProposal, AssistantQuestionSet } from "../src/contracts/assistant";
import type { Model } from "../src/contracts/model";

const mermaidRender = vi.hoisted(() => vi.fn());

vi.mock("mermaid", () => ({
  default: { initialize: vi.fn(), render: mermaidRender },
}));

const EMPTY_PROPOSAL: AssistantProposal = { changed: false, valid: true, checked: true, issues: [], files: [] };

function fold(events: readonly object[]): Transcript {
  return events.reduce<Transcript>(
    (state, event, seq) => applyEvent(state, { seq, t: 0, ...event } as AssistantEnvelope),
    EMPTY_TRANSCRIPT,
  );
}

describe("the transcript", () => {
  it("is rebuilt from the events alone", () => {
    const state = fold([
      { type: "run_start", profile: "p", runner: "claude-cli" },
      { type: "user", text: "hello" },
      { type: "tool_call", name: "get_model", args: {}, isError: false, summary: "" },
      { type: "tool_call", name: "add_block", args: {}, isError: true, summary: "refused" },
      { type: "text", text: "done" },
      { type: "run_end", status: "ok", proposal: { ...EMPTY_PROPOSAL, changed: true } },
    ]);
    expect(state.items.map((item) => item.kind)).toEqual(["user", "tools", "assistant"]);
    const tools = state.items[1]!;
    expect(tools.kind === "tools" && tools.calls).toHaveLength(2);
    expect(state.running).toBe(false);
    expect(state.proposal?.changed).toBe(true);
    expect(state.nextSeq).toBe(6);
  });

  it("ignores an event it has seen, so a reconnect can replay", () => {
    const state = fold([{ type: "text", text: "once" }]);
    expect(applyEvent(state, { seq: 0, t: 0, type: "text", text: "once" })).toBe(state);
  });

  it("closes a question when the next message arrives", () => {
    const question = { id: "q", questions: [{ id: "a", prompt: "?", kind: "text" }] };
    const open = fold([{ type: "question", question }]);
    expect(open.items[0]).toMatchObject({ kind: "question", answered: false });
    const closed = applyEvent(open, { seq: 1, t: 0, type: "user", text: "My answers:" });
    expect(closed.items[0]).toMatchObject({ kind: "question", answered: true });
  });

  it("says why a run ended early, but not that one ended well", () => {
    const end = { type: "run_end", proposal: EMPTY_PROPOSAL };
    expect(fold([{ ...end, status: "ok" }]).items).toEqual([]);
    expect(fold([{ ...end, status: "error", message: "no login" }]).items[0]).toMatchObject({
      tone: "error",
      text: "The run failed: no login",
    });
    expect(fold([{ ...end, status: "cancelled" }]).items[0]).toMatchObject({ tone: "info", text: "Stopped." });
  });

  it("remembers the project a home-screen chat created", () => {
    const state = fold([{ type: "project_created", project: "pendulum" }]);
    expect(state.createdProject).toBe("pendulum");
    expect(state.items[0]).toMatchObject({ kind: "project", project: "pendulum" });
  });

  it("keeps a debug run apart from a plain one", () => {
    const state = fold([
      { type: "simulation", runId: "r1", model: "m", draft: false },
      { type: "simulation", runId: "r2", model: "m", draft: false, debug: true },
    ]);
    expect(state.items.map((item) => (item.kind === "simulation" ? item.debug : null))).toEqual([false, true]);
  });
});

describe("chat math", () => {
  it("turns the bracket forms into dollars", () => {
    expect(normalizeChatMath(String.raw`so \(a+b\) is`)).toBe("so $a+b$ is");
    expect(normalizeChatMath(String.raw`\[ x^2 \]`)).toBe("\n$$\nx^2\n$$\n");
  });

  it("leaves code and dollar math alone", () => {
    const fenced = "```julia\nx = \"\\(a)\"\n```";
    expect(normalizeChatMath(fenced)).toBe(fenced);
    expect(normalizeChatMath("`\\(a\\)`")).toBe("`\\(a\\)`");
    expect(normalizeChatMath(String.raw`$$a \\[2pt] b$$`)).toBe(String.raw`$$a \\[2pt] b$$`);
  });
});

describe("a chat message", () => {
  beforeEach(() => {
    mermaidRender.mockReset();
  });

  it("typesets math", () => {
    const { container } = render(<ChatMarkdown text={String.raw`The constant is \(\tau = L/R\).`} />);
    expect(container.querySelector(".katex")).not.toBeNull();
  });

  it("draws a mermaid fence", async () => {
    mermaidRender.mockResolvedValue({ svg: "<svg><title>drawn</title></svg>" });
    render(<ChatMarkdown text={"```mermaid\ngraph LR\n  A --> B\n```"} />);
    expect(await screen.findByTestId("mermaid-diagram")).toBeTruthy();
    expect(mermaidRender.mock.calls[0]?.[1]).toBe("graph LR\n  A --> B");
  });

  it("shows the source and the reason when a diagram does not parse", async () => {
    mermaidRender.mockImplementation(async () => {
      throw new Error("Parse error on line 2");
    });
    render(<ChatMarkdown text={"```mermaid\ngraph LR\n  A --\n```"} />);
    const box = await screen.findByTestId("mermaid-error");
    expect(box.textContent).toContain("Parse error on line 2");
    expect(box.textContent).toContain("A --");
  });

  it("leaves other fences as code", () => {
    const { container } = render(<ChatMarkdown text={"```julia\nx = 1\n```"} />);
    expect(container.querySelector("pre code")?.textContent).toContain("x = 1");
    expect(mermaidRender).not.toHaveBeenCalled();
  });
});

const QUESTIONS: AssistantQuestionSet = {
  id: "q1",
  title: "Scope",
  questions: [
    {
      id: "friction",
      prompt: "Model friction?",
      kind: "single",
      options: [
        { value: "none", label: "No friction" },
        { value: "viscous", label: "Viscous", description: "Adds a damper" },
      ],
    },
    {
      id: "plots",
      prompt: "Which plots?",
      kind: "multiple",
      allowOther: true,
      options: [
        { value: "speed", label: "Speed" },
        { value: "power", label: "Power" },
      ],
    },
    { id: "note", prompt: "Anything else?", kind: "text", optional: true },
  ],
};

describe("a question card", () => {
  it("offers radio buttons and checkboxes and sends what was chosen", () => {
    const onAnswer = vi.fn();
    render(<QuestionCard question={QUESTIONS} answered={false} busy={false} onAnswer={onAnswer} />);
    expect(screen.getByRole<HTMLInputElement>("radio", { name: /Viscous/ }).type).toBe("radio");
    const send = screen.getByTestId<HTMLButtonElement>("question-send");
    expect(send.disabled).toBe(true);

    fireEvent.click(screen.getByRole("radio", { name: /No friction/ }));
    fireEvent.click(screen.getByRole("radio", { name: /Viscous/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Speed" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Power" }));
    expect(send.disabled).toBe(false);
    fireEvent.click(send);

    expect(onAnswer).toHaveBeenCalledWith([
      { questionId: "friction", values: ["viscous"], other: null },
      { questionId: "plots", values: ["speed", "power"], other: null },
      { questionId: "note", values: [], other: null },
    ]);
  });

  it("takes a free-text answer where one is allowed", () => {
    const onAnswer = vi.fn();
    render(<QuestionCard question={QUESTIONS} answered={false} busy={false} onAnswer={onAnswer} />);
    fireEvent.click(screen.getByRole("radio", { name: /No friction/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Other" }));
    fireEvent.change(screen.getByRole("textbox", { name: /Other answer/ }), { target: { value: "torque" } });
    fireEvent.click(screen.getByTestId("question-send"));
    expect(onAnswer.mock.calls[0]?.[0][1]).toEqual({ questionId: "plots", values: [], other: "torque" });
  });

  it("only records the question once it was answered", () => {
    render(<QuestionCard question={QUESTIONS} answered busy={false} onAnswer={vi.fn()} />);
    expect(screen.queryByTestId("question-send")).toBeNull();
    expect(screen.getByRole("radio", { name: /No friction/ }).matches(":disabled")).toBe(true);
  });
});

describe("chart arithmetic", () => {
  it("picks round ticks", () => {
    expect(ticks({ min: 0, max: 1 })).toEqual([0, 0.2, 0.4, 0.6, 0.8, 1]);
    expect(ticks({ min: -3, max: 7 })).toEqual([-2, 0, 2, 4, 6]);
  });

  it("widens a flat extent and ignores what is not finite", () => {
    expect(extentOf([[2, 2, null]])).toEqual({ min: 1.8, max: 2.2 });
    expect(extentOf([[null, Number.NaN]])).toBeNull();
  });

  it("sorts an x that wraps around, as fftfreq does", () => {
    const order = sortOrder([0, 1, -2, -1]);
    expect(order.map((i) => [0, 1, -2, -1][i])).toEqual([-2, -1, 0, 1]);
  });

  it("keeps a narrow peak when it thins", () => {
    const y = new Array<number>(100000).fill(0);
    y[54321] = 9;
    const keep = thin(y.length, [y], 200);
    expect(keep.length).toBeLessThanOrEqual(204);
    expect(keep).toContain(54321);
  });

  it("formats numbers for reading", () => {
    expect(formatNumber(null)).toBe("–");
    expect(formatNumber(true)).toBe("true");
    expect(formatNumber(1200)).toBe("1200");
    expect(formatNumber(0.12345678)).toBe("0.1235");
    expect(formatNumber(2.5e-7)).toBe("2.50e-7");
  });
});

describe("a figure", () => {
  it("draws a chart with a legend", () => {
    const { container } = render(
      <ChatChart xLabel="Hz" style="line" x={[0, 1, 2]} series={[{ name: "amp", y: [1, null, 3] }]} />,
    );
    expect(screen.getByRole("img", { name: /line chart of amp against Hz/ })).toBeTruthy();
    expect(container.querySelector("path")?.getAttribute("d")).toMatch(/^M.*M/); // the gap stays a gap
    expect(container.querySelector(".assistant-chart__legend")?.textContent).toContain("amp");
  });

  it("draws bars and points", () => {
    const series = [{ name: "a", y: [1, 2] }];
    const { container, rerender } = render(<ChatChart xLabel="x" style="bar" x={[0, 1]} series={series} />);
    expect(container.querySelectorAll("rect")).toHaveLength(2);
    rerender(<ChatChart xLabel="x" style="points" x={[0, 1]} series={series} />);
    expect(container.querySelectorAll("circle")).toHaveLength(2);
  });

  it("says when there is nothing to draw", () => {
    render(<ChatChart xLabel="x" style="line" x={[0]} series={[{ name: "a", y: [null] }]} />);
    expect(screen.getByText(/Nothing to draw/)).toBeTruthy();
  });

  it("shows a table of a cell", () => {
    render(
      <FigureCard
        figure={{
          id: "f",
          kind: "table",
          title: "Peaks",
          columns: ["f", "amp"],
          rows: [
            [12.5, null],
            [25, 0.5],
          ],
          truncated: true,
        }}
      />,
    );
    expect(screen.getByText("Peaks")).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "amp" })).toBeTruthy();
    expect(screen.getAllByRole("row")).toHaveLength(3);
    expect(screen.getByText(/first rows/)).toBeTruthy();
  });

  it("shows a matrix with its range", () => {
    render(
      <FigureCard
        figure={{ id: "f", kind: "image", title: "", rows: [[0, 1], [2, 3]], min: 0, max: 3 }}
      />,
    );
    expect(screen.getByRole("img", { name: "2 by 2 matrix, from 0 to 3" })).toBeTruthy();
  });

  it("draws a level of a model's diagram", () => {
    const { container } = render(
      <FigureCard
        figure={{
          id: "f",
          kind: "diagram",
          title: "Motor",
          model: "motor",
          path: [],
          nodes: [
            { id: "a", name: "Se1", kind: "block", label: "Se", x: 0, y: 0 },
            { id: "b", name: "J1", kind: "junction", label: "1", x: 200, y: 0 },
          ],
          edges: [{ from: "a", to: "b", kind: "bond" }],
        }}
      />,
    );
    expect(container.querySelectorAll("line")).toHaveLength(1);
    expect(container.querySelector("circle")).not.toBeNull();
    expect(screen.getByRole("img", { name: /Diagram of motor: Se1, J1/ })).toBeTruthy();
  });

  it("shows a code cell and its error", () => {
    render(
      <CodeCard
        cell={{
          seq: 1,
          t: 0,
          type: "code",
          id: "c",
          title: "Spectrum",
          code: "fft(x)",
          runId: "r1",
          ok: false,
          output: ["partial"],
          error: "E004 x is not defined",
        }}
      />,
    );
    expect(screen.getByRole("alert").textContent).toContain("x is not defined");
    expect(screen.getByText("partial")).toBeTruthy();
    expect(screen.getByText("run r1")).toBeTruthy();
  });
});

describe("the proposal", () => {
  const proposal: AssistantProposal = {
    changed: true,
    valid: true,
    checked: false,
    issues: [{ file: "model:motor", severity: "warning", code: "W201", message: "unused" }],
    files: [
      {
        kind: "model",
        name: "motor",
        change: "changed",
        rows: [{ op: "changed", what: "Motor.R", before: "1", after: "2" }],
      },
    ],
  };

  function review(next: AssistantProposal, running = false) {
    const onApply = vi.fn();
    render(
      <ProposalReview
        proposal={next}
        running={running}
        applying={false}
        autoApply={false}
        onApply={onApply}
        onDiscard={vi.fn()}
        onAutoApply={vi.fn()}
      />,
    );
    return { onApply, apply: screen.getByTestId<HTMLButtonElement>("assistant-apply") };
  }

  it("lists the changes and warns of an unchecked draft", () => {
    const { apply, onApply } = review(proposal);
    expect(screen.getByText(/1 → 2/)).toBeTruthy();
    expect(screen.getByText(/W201 unused/)).toBeTruthy();
    expect(screen.getByText(/Not checked/)).toBeTruthy();
    fireEvent.click(apply);
    expect(onApply).toHaveBeenCalled();
  });

  it("cannot apply an invalid draft, or during a run", () => {
    expect(review({ ...proposal, valid: false }).apply.disabled).toBe(true);
  });

  it("waits for the run to end", () => {
    expect(review(proposal, true).apply.disabled).toBe(true);
  });
});

function modelWithSubsystem(): Model {
  return {
    diagram: {
      nodes: [
        { id: "n1", name: "Motor", block: { ref: "stdlib:converters/DCMotor" }, at: { x: 0, y: 0 } },
        {
          id: "n2",
          name: "Drive",
          at: { x: 0, y: 0 },
          block: {
            subsystem: {
              diagram: {
                nodes: [
                  { id: "n3", name: "Gain", block: { ref: "stdlib:continuous/Gain" }, at: { x: 0, y: 0 } },
                  { id: "n4", name: "Sum", block: { ref: "stdlib:continuous/Sum" }, at: { x: 0, y: 0 } },
                ],
                connections: [
                  { id: "c1", kind: "signal", from: { node: "n3", port: "out" }, to: { node: "n4", port: "a" } },
                ],
              },
            },
          },
        },
      ],
      connections: [],
    },
  } as unknown as Model;
}

describe("the selection", () => {
  beforeEach(() => {
    useAssistantSelectionStore.setState({ code: null, doc: null, dismissed: new Set() });
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("names canvas elements as the assistant knows them, at their level", () => {
    const item = diagramSelection(modelWithSubsystem(), "motor", ["n2"], { nodes: ["n3"], connections: ["c1"] });
    expect(item).toEqual({
      kind: "diagram",
      model: "motor",
      path: ["Drive"],
      nodes: ["Gain"],
      connections: ["Gain.out -> Sum.a"],
    });
    expect(selectionLabel(item!)).toBe("Gain, 1 connection");
  });

  it("has nothing to send without a selection", () => {
    expect(diagramSelection(modelWithSubsystem(), "motor", [], { nodes: [], connections: [] })).toBeNull();
    expect(diagramSelection(null, null, [], { nodes: ["n1"], connections: [] })).toBeNull();
  });

  it("publishes selected code, and clears it when the selection collapses", () => {
    publishCodeSelection("project:Motor", "tau = k * i", 3, 4);
    const code = useAssistantSelectionStore.getState().code;
    expect(code).toEqual({ kind: "code", source: "project:Motor", text: "tau = k * i", fromLine: 3, toLine: 4 });
    expect(selectionLabel(code!)).toBe("Motor, lines 3-4");
    publishCodeSelection("project:Motor", "", 3, 3);
    expect(useAssistantSelectionStore.getState().code).toBeNull();
  });

  it("forgets a removed chip when the selection goes", () => {
    publishCodeSelection("b", "x", 1, 1);
    const state = useAssistantSelectionStore.getState();
    state.dismiss([selectionKey(state.code!)]);
    expect(useAssistantSelectionStore.getState().dismissed.size).toBe(1);
    publishCodeSelection("b", "", 1, 1);
    expect(useAssistantSelectionStore.getState().dismissed.size).toBe(0);
  });

  it("keeps a docs selection while the user clicks into the chat", () => {
    document.body.innerHTML = `<div data-assistant-doc-page="overview" data-assistant-doc-model="motor"><p id="t">The time constant</p></div><textarea id="c"></textarea>`;
    const stop = trackDocSelection();
    const text = document.getElementById("t")!.firstChild!;

    document.getSelection()!.setBaseAndExtent(text, 4, text, 17);
    document.dispatchEvent(new Event("selectionchange"));
    expect(useAssistantSelectionStore.getState().doc).toEqual({
      kind: "doc",
      model: "motor",
      page: "overview",
      text: "time constant",
    });

    const chat = document.getElementById("c")!;
    document.getSelection()!.collapse(chat, 0);
    document.dispatchEvent(new Event("selectionchange"));
    expect(useAssistantSelectionStore.getState().doc?.text).toBe("time constant");

    document.getSelection()!.collapse(text, 2);
    document.dispatchEvent(new Event("selectionchange"));
    expect(useAssistantSelectionStore.getState().doc).toBeNull();
    stop();
  });
});

describe("a figure of a run", () => {
  it("fetches the signals and draws them", async () => {
    const fetchRunData = vi.spyOn(await import("../src/plot/runApi"), "fetchRunData");
    fetchRunData.mockResolvedValue({
      nSignals: 1,
      nPoints: 2,
      time: Float64Array.of(0, 1),
      values: [Float64Array.of(0, 2)],
    });
    render(
      <FigureCard figure={{ id: "f", kind: "plot", title: "Sine", runId: "r1", signals: ["Load/w"] }} />,
    );
    await waitFor(() => expect(screen.getByRole("img", { name: /line chart of Load\/w/ })).toBeTruthy());
    expect(fetchRunData.mock.calls[0]?.slice(0, 3)).toEqual(["r1", ["Load/w"], null]);
    fetchRunData.mockRestore();
  });

  it("says so when the run is gone", async () => {
    const fetchRunData = vi.spyOn(await import("../src/plot/runApi"), "fetchRunData");
    fetchRunData.mockRejectedValue(new Error("no such run"));
    render(<FigureCard figure={{ id: "f", kind: "plot", title: "", runId: "r9", signals: ["a"] }} />);
    expect(await screen.findByText(/no such run/)).toBeTruthy();
    fetchRunData.mockRestore();
  });
});
