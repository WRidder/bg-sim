/**
 * Canvas markers and colouring for diagnostics (plan 7.3).
 *
 * W1.1 owns `src/editor/`; W1.3 owns this directory. The canvas is therefore
 * decorated from the outside, without touching the editor components:
 *
 * * node cards get `data-diagnostic-*` attributes; `diagnostics.css` draws the
 *   red/amber outline and the count badge, and the `title` lists the messages;
 * * power edges get the domain the worker adopted (`domains`), falling back to
 *   W1.1's client-side analysis when the worker has no entry yet;
 * * edge diagnostics are HTML badges in a fixed overlay positioned from the
 *   edge's on-screen midpoint;
 * * the check's causal strokes and unit factors are summarised here so the
 *   canvas decorator and the tests share one reading of the worker maps, but
 *   they are drawn by the edge components themselves (`editor/edges/`), which
 *   is where their data-testid hooks live.
 *
 * All worker maps are read defensively: an absent `causality` or `unitFactors`
 * object never breaks a render.
 */

import type { DomainName } from "../contracts/catalog";
import type { Diagnostic } from "../contracts/diagnostic";
import type { Model } from "../contracts/model";
import type { CausalityStroke } from "../contracts/worker-rpc";
import { useDocumentStore } from "../state/documentStore";
import { createNodeResolver } from "./navigation";
import { useDiagnosticsStore } from "./store";
import "./diagnostics.css";

export const DIAGNOSTIC_SEVERITIES = ["error", "warning"] as const;
export type MarkerSeverity = (typeof DIAGNOSTIC_SEVERITIES)[number];

const DOMAIN_TOKENS: Record<DomainName, string> = {
  Electrical: "var(--domain-electrical)",
  Translation: "var(--domain-translation)",
  Rotation: "var(--domain-rotation)",
  Hydraulic: "var(--domain-hydraulic)",
  Generic: "var(--domain-generic)",
};

/** The CSS token of a domain (plan 7.3); unknown domains stay generic. */
export function domainToken(domain: DomainName): string {
  return DOMAIN_TOKENS[domain] ?? DOMAIN_TOKENS.Generic;
}

/** Generic bonds are dashed; every adopted domain is solid (plan 7.3). */
export function domainDash(domain: DomainName): string {
  return domain === "Generic" ? "4 3" : "none";
}

/** `0.001` -> `×0.001`; large and tiny factors stay readable. */
export function formatUnitFactor(factor: number): string {
  if (!Number.isFinite(factor)) {
    return "×?";
  }
  const magnitude = Math.abs(factor);
  if (magnitude !== 0 && (magnitude < 1e-4 || magnitude >= 1e6)) {
    return `×${factor.toExponential(3).replace(/\.?0+e/, "e")}`;
  }
  return `×${String(factor)}`;
}

export interface NodeMarker {
  nodeId: string;
  severity: MarkerSeverity;
  count: number;
  messages: string[];
}

export interface ConnectionMarker {
  connectionId: string;
  severity: MarkerSeverity;
  count: number;
  messages: string[];
}

export interface CanvasCheck {
  diagnostics: readonly Diagnostic[];
  domains: Readonly<Record<string, DomainName>>;
  unitFactors: Readonly<Record<string, number>>;
  causality: Readonly<Record<string, CausalityStroke>>;
}

function markerSeverity(severity: Diagnostic["severity"]): MarkerSeverity | null {
  if (severity === "error") {
    return "error";
  }
  if (severity === "warning") {
    return "warning";
  }
  return null;
}

/** Errors and warnings grouped by the editor node they point at. */
export function collectNodeMarkers(
  doc: Model | null,
  diagnostics: readonly Diagnostic[],
): Map<string, NodeMarker> {
  const markers = new Map<string, NodeMarker>();
  const resolveNode = createNodeResolver(doc);
  for (const diagnostic of diagnostics) {
    const severity = markerSeverity(diagnostic.severity);
    if (severity === null) {
      continue;
    }
    const nodeId = resolveNode(diagnostic);
    if (nodeId === null) {
      continue;
    }
    const existing = markers.get(nodeId);
    if (existing === undefined) {
      markers.set(nodeId, {
        nodeId,
        severity,
        count: 1,
        messages: [`${diagnostic.code}: ${diagnostic.message}`],
      });
      continue;
    }
    existing.count += 1;
    // An error always wins over a warning on the same element.
    if (severity === "error") {
      existing.severity = "error";
    }
    existing.messages.push(`${diagnostic.code}: ${diagnostic.message}`);
  }
  return markers;
}

/** Errors and warnings grouped by the connection they point at. */
export function collectConnectionMarkers(
  doc: Model | null,
  diagnostics: readonly Diagnostic[],
): Map<string, ConnectionMarker> {
  const connectionIds = new Set(
    doc === null ? [] : doc.diagram.connections.map((connection) => connection.id),
  );
  const markers = new Map<string, ConnectionMarker>();
  for (const diagnostic of diagnostics) {
    const severity = markerSeverity(diagnostic.severity);
    const connectionId = diagnostic.connection ?? null;
    if (severity === null || connectionId === null || !connectionIds.has(connectionId)) {
      continue;
    }
    const existing = markers.get(connectionId);
    if (existing === undefined) {
      markers.set(connectionId, {
        connectionId,
        severity,
        count: 1,
        messages: [`${diagnostic.code}: ${diagnostic.message}`],
      });
      continue;
    }
    existing.count += 1;
    if (severity === "error") {
      existing.severity = "error";
    }
    existing.messages.push(`${diagnostic.code}: ${diagnostic.message}`);
  }
  return markers;
}

function messagesAttribute(messages: readonly string[]): string {
  return messages.join(" · ");
}

function composedTitle(marker: NodeMarker): string {
  return `${marker.count} ${marker.count === 1 ? "diagnostic" : "diagnostics"}\n${marker.messages.join("\n")}`;
}

function applyNodeMarker(element: Element, marker: NodeMarker): void {
  const previous = element.getAttribute("data-diagnostic-title-text");
  const current = element.getAttribute("title");
  if (current !== null && current !== previous) {
    element.setAttribute("data-diagnostic-title-base", current);
  }
  const base = element.getAttribute("data-diagnostic-title-base") ?? "";
  const text = composedTitle(marker);
  element.setAttribute("data-diagnostic-severity", marker.severity);
  element.setAttribute("data-diagnostic-count", String(marker.count));
  element.setAttribute("data-diagnostic-messages", messagesAttribute(marker.messages));
  element.setAttribute("title", base.length > 0 ? `${base}\n\n${text}` : text);
  element.setAttribute("data-diagnostic-title-text", base.length > 0 ? `${base}\n\n${text}` : text);
}

function clearNodeMarker(element: Element): void {
  const hadMarker = element.hasAttribute("data-diagnostic-severity");
  element.removeAttribute("data-diagnostic-severity");
  element.removeAttribute("data-diagnostic-count");
  element.removeAttribute("data-diagnostic-messages");
  element.removeAttribute("data-diagnostic-title-text");
  const base = element.getAttribute("data-diagnostic-title-base");
  if (base !== null) {
    element.setAttribute("title", base);
    element.removeAttribute("data-diagnostic-title-base");
  } else if (hadMarker) {
    element.removeAttribute("title");
  }
}

/**
 * Put the worker's adopted domain on one edge. The edge's own `data-domain`
 * (W1.1's client analysis) is kept in `data-bgsim-base-domain` so clearing a
 * check result restores exactly what the editor had.
 */
export function applyEdgeDomain(edge: Element, domain: DomainName | null): DomainName {
  const kind = edge.getAttribute("data-kind");
  const current = (edge.getAttribute("data-domain") ?? "Generic") as DomainName;
  const client = edge.getAttribute("data-bgsim-client-domain") as DomainName | null;
  const applied = edge.getAttribute("data-bgsim-applied-domain");
  const storedBase = edge.getAttribute("data-bgsim-base-domain");

  if (client !== null) {
    // React owns this attribute and always renders the client-side analysis;
    // it cannot be confused by an earlier diagnostic application. (Without it,
    // a mutation can be observed after the decorator itself wrote the worker
    // domain, which made the base domain equal the applied one.)
    if (storedBase !== client) {
      edge.setAttribute("data-bgsim-base-domain", client);
    }
  } else if (storedBase === null || (applied !== null && current !== applied)) {
    edge.setAttribute("data-bgsim-base-domain", current);
  }
  const base: DomainName =
    client ??
    ((edge.getAttribute("data-bgsim-base-domain") ?? "Generic") as DomainName);
  // `domains` describes power connections; a signal keeps its type styling.
  const effective = kind === "signal" ? base : (domain ?? base);

  edge.setAttribute("data-domain", effective);
  edge.setAttribute("data-bgsim-applied-domain", effective);
  if (kind === "signal") {
    return effective;
  }

  const colour = domainToken(effective);
  const dash = domainDash(effective);
  for (const path of edge.querySelectorAll<SVGPathElement>(".react-flow__edge-path")) {
    path.style.setProperty("stroke", colour, "important");
    path.style.setProperty("stroke-dasharray", dash, "important");
  }
  for (const path of edge.querySelectorAll<SVGElement>(".editor-edge__half-arrow")) {
    path.setAttribute("stroke", colour);
  }
  for (const dot of edge.querySelectorAll<SVGElement>(".editor-edge__node-dot")) {
    dot.setAttribute("fill", colour);
  }
  return effective;
}

function applyEdgeMarker(element: Element, marker: ConnectionMarker): void {
  element.setAttribute("data-diagnostic-severity", marker.severity);
  element.setAttribute("data-diagnostic-count", String(marker.count));
  element.setAttribute("data-diagnostic-messages", messagesAttribute(marker.messages));
}

function clearEdgeMarker(element: Element): void {
  element.removeAttribute("data-diagnostic-severity");
  element.removeAttribute("data-diagnostic-count");
  element.removeAttribute("data-diagnostic-messages");
}

export interface UnitFactorBadge {
  connectionId: string;
  label: string;
}

export interface EdgeMarkerBadge {
  connectionId: string;
  severity: MarkerSeverity;
  count: number;
  messages: string[];
}

export interface CausalStrokeBadge {
  connectionId: string;
  strokeAt: "from" | "to";
}

export interface DecorationSummary {
  /** Node cards carrying a marker. */
  nodes: number;
  /** Edges carrying a marker. */
  edges: number;
  factors: UnitFactorBadge[];
  edgeMarkers: EdgeMarkerBadge[];
  causalStrokes: CausalStrokeBadge[];
}

function edgeId(element: Element): string | null {
  const testId = element.getAttribute("data-testid");
  if (testId === null || !testId.startsWith("edge-")) {
    return null;
  }
  return testId.slice("edge-".length);
}

function elementsByEdgeId(root: ParentNode): Map<string, Element> {
  const edges = new Map<string, Element>();
  for (const element of root.querySelectorAll<Element>('[data-testid^="edge-"]')) {
    const id = edgeId(element);
    if (id !== null) {
      edges.set(id, element);
    }
  }
  return edges;
}

/**
 * Apply one check result to a canvas subtree. Pure DOM: the unit test builds
 * the same markup xyflow produces and asserts the attributes and styles.
 */
export function decorateCanvas(
  root: ParentNode,
  doc: Model | null,
  check: CanvasCheck,
): DecorationSummary {
  // No document means no dependencies to colour or mark; treat it as empty so
  // a stale result can never leak onto the next model's canvas.
  const diagnostics = doc === null ? [] : check.diagnostics;
  const domains = doc === null ? {} : check.domains;
  const unitFactors = doc === null ? {} : check.unitFactors;
  const causality = doc === null ? {} : check.causality;
  const nodeMarkers = collectNodeMarkers(doc, diagnostics);
  const connectionMarkers = collectConnectionMarkers(doc, diagnostics);
  const edges = elementsByEdgeId(root);

  let nodeCount = 0;
  for (const element of root.querySelectorAll<Element>('[data-testid="diagram-node"]')) {
    const nodeId = element.getAttribute("data-node-id");
    const marker = nodeId === null ? undefined : nodeMarkers.get(nodeId);
    if (marker === undefined) {
      clearNodeMarker(element);
    } else {
      applyNodeMarker(element, marker);
      nodeCount += 1;
    }
  }

  let edgeCount = 0;
  for (const [id, element] of edges) {
    applyEdgeDomain(element, domains[id] ?? null);
    const marker = connectionMarkers.get(id);
    if (marker === undefined) {
      clearEdgeMarker(element);
    } else {
      applyEdgeMarker(element, marker);
      edgeCount += 1;
    }
  }

  const factors: UnitFactorBadge[] = [];
  for (const [connectionId, factor] of Object.entries(unitFactors)) {
    if (!edges.has(connectionId) || typeof factor !== "number" || !Number.isFinite(factor)) {
      continue;
    }
    // A factor of exactly 1 is not drawn: the signal is already in its unit.
    if (factor === 1) {
      continue;
    }
    factors.push({ connectionId, label: formatUnitFactor(factor) });
  }

  const edgeMarkers: EdgeMarkerBadge[] = [];
  for (const [connectionId, marker] of connectionMarkers) {
    if (!edges.has(connectionId)) {
      continue;
    }
    edgeMarkers.push({
      connectionId,
      severity: marker.severity,
      count: marker.count,
      messages: marker.messages,
    });
  }

  const causalStrokes: CausalStrokeBadge[] = [];
  for (const [connectionId, stroke] of Object.entries(causality)) {
    if (!edges.has(connectionId) || stroke === null || stroke === undefined) {
      continue;
    }
    const strokeAt = stroke.strokeAt;
    if (strokeAt !== "from" && strokeAt !== "to") {
      continue;
    }
    causalStrokes.push({ connectionId, strokeAt });
  }

  return {
    nodes: nodeCount,
    edges: edgeCount,
    factors,
    edgeMarkers,
    causalStrokes,
  };
}

// --------------------------------------------------------------------- panning

function cssEscape(value: string): string {
  if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
    return CSS.escape(value);
  }
  return value.replace(/[^A-Za-z0-9_-]/g, (character) => `\\${character}`);
}

function mouse(
  target: EventTarget,
  type: string,
  x: number,
  y: number,
  buttons: number,
): void {
  target.dispatchEvent(
    new MouseEvent(type, {
      bubbles: true,
      cancelable: true,
      view: window,
      clientX: x,
      clientY: y,
      button: 0,
      buttons,
    }),
  );
}

/** The screen position halfway along an edge's drawn path. */
export function edgeMidpoint(edge: Element): { x: number; y: number } | null {
  const path = edge.querySelector<SVGPathElement>(".react-flow__edge-path");
  if (path === null || typeof path.getTotalLength !== "function" || typeof path.getScreenCTM !== "function") {
    return null;
  }
  try {
    const length = path.getTotalLength();
    const point = path.getPointAtLength(length / 2);
    const matrix = path.getScreenCTM();
    if (matrix === null) {
      return null;
    }
    const screen = point.matrixTransform(matrix);
    return { x: screen.x, y: screen.y };
  } catch {
    return null;
  }
}

const OVERLAY_CLASS = "canvas-diagnostics__overlay";

function setText(element: HTMLElement, text: string): void {
  if (element.textContent !== text) {
    element.textContent = text;
  }
}

function setPosition(element: HTMLElement, x: number, y: number, visible: boolean): void {
  if (!visible) {
    if (element.style.display !== "none") {
      element.style.display = "none";
    }
    return;
  }
  if (element.style.display === "none") {
    element.style.display = "";
  }
  const left = `${Math.round(x)}px`;
  const top = `${Math.round(y)}px`;
  if (element.style.left !== left) {
    element.style.left = left;
  }
  if (element.style.top !== top) {
    element.style.top = top;
  }
}

/**
 * Watches the editor and the stores and keeps the decorations and the focus
 * pan in step. Mounted once by the diagnostics runtime in `BottomDock`.
 */
export class CanvasDiagnosticsController {
  private observer: MutationObserver | null = null;
  private resizeObserver: ResizeObserver | null = null;
  private observedCanvas: HTMLElement | null = null;
  private storeStops: (() => void)[] = [];
  private stopped = false;
  private frame: number | null = null;
  private frameIsTimeout = false;
  private overlay: HTMLDivElement | null = null;
  private edgeBadges = new Map<string, HTMLElement>();
  private pendingFocus: string | null = null;
  private lastFocusNonce: number;

  constructor() {
    this.lastFocusNonce = useDiagnosticsStore.getState().focus?.nonce ?? 0;
  }

  start(): () => void {
    this.observer = new MutationObserver(() => this.schedule());
    this.observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      // React re-renders rebuild inline edge styles and selection classes.
      attributeFilter: ["style", "class", "data-domain"],
    });
    this.storeStops = [
      useDocumentStore.subscribe(() => this.schedule()),
      useDiagnosticsStore.subscribe(() => {
        this.checkFocus();
        this.schedule();
      }),
    ];
    window.addEventListener("resize", this.onResize);
    this.schedule();
    return () => this.stop();
  }

  private readonly onResize = (): void => this.schedule();

  private schedule(): void {
    if (this.stopped || this.frame !== null) {
      return;
    }
    const run = (): void => {
      this.frame = null;
      this.sync();
    };
    this.frameIsTimeout = typeof window.requestAnimationFrame !== "function";
    this.frame = this.frameIsTimeout
      ? window.setTimeout(run, 16)
      : window.requestAnimationFrame(run);
  }

  private checkFocus(): void {
    const focus = useDiagnosticsStore.getState().focus;
    if (focus === null || focus.nonce === this.lastFocusNonce) {
      return;
    }
    this.lastFocusNonce = focus.nonce;
    this.pendingFocus = focus.nodeId;
  }

  private ensureOverlay(): HTMLDivElement {
    if (this.overlay !== null && document.body.contains(this.overlay)) {
      return this.overlay;
    }
    const overlay = document.createElement("div");
    overlay.className = OVERLAY_CLASS;
    overlay.setAttribute("data-testid", "canvas-diagnostics-overlay");
    document.body.appendChild(overlay);
    this.overlay = overlay;
    this.edgeBadges.clear();
    return overlay;
  }

  private hideOverlay(): void {
    if (this.overlay !== null) {
      this.overlay.remove();
    }
    this.overlay = null;
    this.edgeBadges.clear();
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    this.observedCanvas = null;
  }

  private sync(): void {
    if (this.stopped) {
      return;
    }
    const canvas = document.querySelector<HTMLElement>('[data-testid="canvas-surface"]');
    if (canvas === null) {
      this.hideOverlay();
      return;
    }
    this.observeCanvasSize(canvas);
    const doc = useDocumentStore.getState().doc;
    const state = useDiagnosticsStore.getState();
    const summary = decorateCanvas(canvas, doc, {
      diagnostics: state.diagnostics,
      domains: state.domains,
      unitFactors: state.unitFactors,
      causality: state.causality,
    });

    this.ensureOverlay();
    this.renderEdgeBadges(canvas, summary.edgeMarkers);

    if (this.pendingFocus !== null && this.focusNode(canvas, this.pendingFocus)) {
      this.pendingFocus = null;
    }
  }

  /** A splitter drag or a panel resize moves the canvas without DOM mutations. */
  private observeCanvasSize(canvas: HTMLElement): void {
    if (this.observedCanvas === canvas || typeof ResizeObserver === "undefined") {
      return;
    }
    this.resizeObserver?.disconnect();
    this.resizeObserver = new ResizeObserver(() => this.schedule());
    this.resizeObserver.observe(canvas);
    this.observedCanvas = canvas;
  }

  private renderEdgeBadges(canvas: HTMLElement, entries: EdgeMarkerBadge[]): void {
    this.renderBadges(
      canvas,
      entries,
      this.edgeBadges,
      "edge-diagnostic-",
      (entry) => `${entry.count}`,
      -12,
      (entry) => `${entry.messages.join("\n")}`,
      (entry) => entry.severity,
    );
  }

  private renderBadges<T extends { connectionId: string }>(
    canvas: HTMLElement,
    entries: T[],
    store: Map<string, HTMLElement>,
    testIdPrefix: string,
    label: (entry: T) => string,
    offsetY: number,
    title?: (entry: T) => string,
    tone?: (entry: T) => MarkerSeverity,
  ): void {
    const rect = canvas.getBoundingClientRect();
    const seen = new Set<string>();
    for (const entry of entries) {
      const edge = canvas.querySelector<Element>(
        `[data-testid="edge-${cssEscape(entry.connectionId)}"]`,
      );
      const point = edge === null ? null : edgeMidpoint(edge);
      if (point === null) {
        continue;
      }
      seen.add(entry.connectionId);
      let badge = store.get(entry.connectionId);
      if (badge === undefined) {
        badge = document.createElement("div");
        badge.className = "canvas-diagnostics__badge";
        badge.setAttribute("data-testid", `${testIdPrefix}${entry.connectionId}`);
        this.ensureOverlay().appendChild(badge);
        store.set(entry.connectionId, badge);
      }
      setText(badge, label(entry));
      if (title !== undefined) {
        const text = title(entry);
        if (badge.title !== text) {
          badge.title = text;
        }
      }
      const severity = tone === undefined ? null : tone(entry);
      badge.dataset.tone = severity ?? "factor";
      // `point` is in client coordinates, and the overlay is a fixed layer at
      // the viewport origin, so no canvas offset is subtracted here.
      const x = point.x;
      const y = point.y + offsetY;
      const visible =
        x >= rect.left && y >= rect.top && x <= rect.left + rect.width && y <= rect.top + rect.height;
      setPosition(badge, x, y, visible);
    }
    for (const [id, badge] of store) {
      if (!seen.has(id)) {
        badge.remove();
        store.delete(id);
      }
    }
  }

  private focusNode(canvas: HTMLElement, nodeId: string): boolean {
    const node = canvas.querySelector<HTMLElement>(
      `[data-testid="diagram-node"][data-node-id="${cssEscape(nodeId)}"]`,
    );
    if (node === null) {
      return false;
    }
    const canvasRect = canvas.getBoundingClientRect();
    const nodeRect = node.getBoundingClientRect();
    if (canvasRect.width <= 0 || canvasRect.height <= 0 || nodeRect.width <= 0) {
      return false;
    }
    const dx = canvasRect.left + canvasRect.width / 2 - (nodeRect.left + nodeRect.width / 2);
    const dy = canvasRect.top + canvasRect.height / 2 - (nodeRect.top + nodeRect.height / 2);
    if (Math.abs(dx) >= 1 || Math.abs(dy) >= 1) {
      if (!this.panByDrag(canvas, dx, dy)) {
        this.panByTransform(dx, dy);
      }
    }
    canvas.setAttribute("data-focused-node", nodeId);
    return true;
  }

  /**
   * Pan through d3-zoom's public interaction path so React Flow's viewport
   * store stays in sync. The renderer is the element the zoom behaviour is
   * attached to; starting there cannot start a node drag.
   */
  private panByDrag(canvas: HTMLElement, dx: number, dy: number): boolean {
    const renderer = canvas.querySelector<HTMLElement>(".react-flow__renderer");
    if (renderer === null) {
      return false;
    }
    const rect = canvas.getBoundingClientRect();
    const startX = rect.left + rect.width / 2;
    const startY = rect.top + rect.height / 2;
    mouse(renderer, "mousedown", startX, startY, 1);
    mouse(window, "mousemove", startX + dx, startY + dy, 1);
    mouse(window, "mouseup", startX + dx, startY + dy, 0);
    return true;
  }

  /** Last resort when d3 is not listening (the viewport is still observable). */
  private panByTransform(dx: number, dy: number): void {
    const viewport = document.querySelector<HTMLElement>(".react-flow__viewport");
    if (viewport === null) {
      return;
    }
    const match = /translate\(\s*([-\d.eE+]+)px\s*,\s*([-\d.eE+]+)px\s*\)\s*scale\(\s*([-\d.eE+]+)\s*\)/.exec(
      viewport.style.transform,
    );
    if (match === null) {
      return;
    }
    const x = Number(match[1]) + dx;
    const y = Number(match[2]) + dy;
    const zoom = Number(match[3]);
    viewport.style.transform = `translate(${x}px,${y}px) scale(${zoom})`;
  }

  private stop(): void {
    this.stopped = true;
    this.observer?.disconnect();
    this.observer = null;
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    this.observedCanvas = null;
    for (const unsubscribe of this.storeStops) {
      unsubscribe();
    }
    this.storeStops = [];
    window.removeEventListener("resize", this.onResize);
    if (this.frame !== null) {
      if (this.frameIsTimeout) {
        window.clearTimeout(this.frame);
      } else {
        window.cancelAnimationFrame(this.frame);
      }
      this.frame = null;
    }
    this.hideOverlay();
  }
}

/** Start decorating the canvas; returns the stop function for `useEffect`. */
export function startCanvasDiagnostics(): () => void {
  return new CanvasDiagnosticsController().start();
}
