// Real-time recording helpers for the 30 fps intro video: CDP screencast with a virtual clock,
// a visible mouse cursor overlay and smooth, paced mouse/keyboard actions.
import { mkdirSync, writeFileSync, copyFileSync } from "node:fs";
import path from "node:path";
import { sleep } from "./lib.mjs";

const CURSOR_JS = `(() => {
  if (window.__curInstalled) return; window.__curInstalled = true;
  const mk = () => {
    const d = document.createElement("div");
    d.id = "__cur";
    d.style.cssText = "position:fixed;left:0;top:0;width:28px;height:28px;z-index:2147483647;pointer-events:none;display:none;will-change:transform;";
    d.innerHTML = '<svg width="28" height="28" viewBox="0 0 24 24"><path d="M3 2l7.5 19 2.6-7.6L21 10.8z" fill="#ffffff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    const r = document.createElement("div");
    r.id = "__curring";
    r.style.cssText = "position:fixed;left:0;top:0;width:34px;height:34px;margin:-17px 0 0 -17px;border:3px solid #f5a524;border-radius:50%;z-index:2147483646;pointer-events:none;opacity:0;";
    (document.body || document.documentElement).append(r, d);
    window.addEventListener("mousemove", (e) => { d.style.display = "block"; d.style.transform = "translate(" + e.clientX + "px," + e.clientY + "px)"; r.style.left = e.clientX + "px"; r.style.top = e.clientY + "px"; }, true);
    window.addEventListener("mousedown", (e) => { r.style.transition = "none"; r.style.opacity = "1"; r.style.transform = "scale(.5)"; requestAnimationFrame(() => { r.style.transition = "opacity .45s, transform .45s"; r.style.opacity = "0"; r.style.transform = "scale(1.5)"; }); }, true);
  };
  if (document.body) mk(); else document.addEventListener("DOMContentLoaded", mk);
})();`;

export async function installCursor(context) {
  await context.addInitScript(CURSOR_JS);
}

export class Recorder {
  constructor(page, dir, name) {
    this.page = page; this.dir = path.join(dir, name); this.name = name;
    mkdirSync(this.dir, { recursive: true });
    this.frames = []; this.marks = []; this.paused = false; this.pausedTotal = 0; this.skew = 0; this.pauseAt = 0; this.n = 0;
  }
  vt(ms = Date.now()) { return ms - this.pausedTotal + this.skew; }
  _write(buf, vt) {
    const f = path.join(this.dir, String(this.n++).padStart(6, "0") + ".jpg");
    writeFileSync(f, buf);
    this.frames.push({ vt, file: f });
  }
  async start() {
    this.cdp = await this.page.context().newCDPSession(this.page);
    this.cdp.on("Page.screencastFrame", async (ev) => {
      const ts = (ev.metadata?.timestamp ?? Date.now() / 1000) * 1000;
      this.cdp.send("Page.screencastFrameAck", { sessionId: ev.sessionId }).catch(() => {});
      if (this.paused || this.stopped) return;
      this._write(Buffer.from(ev.data, "base64"), this.vt(ts));
    });
    await this.cdp.send("Page.startScreencast", { format: "jpeg", quality: 92, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 });
    await this.snapshotFrame();
  }
  async snapshotFrame() {
    const r = await this.cdp.send("Page.captureScreenshot", { format: "jpeg", quality: 92 });
    this._write(Buffer.from(r.data, "base64"), this.vt());
  }
  pause() { if (this.paused) return; this.paused = true; this.pauseAt = Date.now(); }
  async resume() {
    if (!this.paused) return;
    this.pausedTotal += Date.now() - this.pauseAt; this.paused = false;
    await sleep(150);
    await this.snapshotFrame();
  }
  mark(name) { this.marks.push({ name, vt: this.vt() }); }
  /** Insert a still image (e.g. a pop-out window) for `sec` seconds of video. */
  injectStill(file, sec) {
    const f = path.join(this.dir, String(this.n++).padStart(6, "0") + ".jpg");
    copyFileSync(file, f);
    this.frames.push({ vt: this.vt(), file: f });
    this.skew += sec * 1000;
  }
  async stop() {
    this.stopped = true;
    const end = this.vt();
    await this.cdp.send("Page.stopScreencast").catch(() => {});
    const out = { name: this.name, frames: this.frames, marks: this.marks, end, dir: this.dir };
    writeFileSync(path.join(this.dir, "timeline.json"), JSON.stringify(out));
    return out;
  }
}

// ---- paced actions -------------------------------------------------------------------------------------
const pos = new WeakMap();
const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);
export async function glide(page, x, y, ms = 500) {
  const from = pos.get(page) ?? { x: 960, y: 700 };
  const n = Math.max(4, Math.round(ms / 16));
  for (let i = 1; i <= n; i++) {
    const e = ease(i / n);
    await page.mouse.move(from.x + (x - from.x) * e, from.y + (y - from.y) * e);
    await sleep(16);
  }
  pos.set(page, { x, y });
}
async function center(loc, dx = 0, dy = 0) {
  await loc.scrollIntoViewIfNeeded().catch(() => {});
  const b = await loc.boundingBox();
  if (!b) throw new Error("no box for " + loc);
  return { x: b.x + b.width / 2 + dx, y: b.y + b.height / 2 + dy, b };
}
export async function hover(page, loc, o = {}) { const c = await center(loc, o.dx, o.dy); await glide(page, c.x, c.y, o.ms ?? 600); await sleep(o.pause ?? 250); }
export async function click(page, loc, o = {}) {
  const c = await center(loc, o.dx, o.dy);
  await glide(page, c.x, c.y, o.ms ?? 600);
  await sleep(180);
  await page.mouse.down(o.right ? { button: "right" } : undefined);
  await sleep(70);
  await page.mouse.up(o.right ? { button: "right" } : undefined);
  await sleep(o.pause ?? 450);
}
export async function dblclick(page, loc, o = {}) {
  const c = await center(loc, o.dx, o.dy);
  await glide(page, c.x, c.y, o.ms ?? 600);
  await sleep(180);
  await page.mouse.dblclick(c.x, c.y);
  await sleep(o.pause ?? 500);
}
export async function typeInto(page, loc, text, o = {}) {
  await click(page, loc, { pause: 200 });
  await page.keyboard.press("Control+A");
  await sleep(150);
  await page.keyboard.type(text, { delay: o.delay ?? 90 });
  await sleep(250);
  if (o.enter !== false) await page.keyboard.press("Enter");
  await sleep(o.pause ?? 700);
}
export async function drag(page, from, to, o = {}) {
  await glide(page, from.x, from.y, o.ms ?? 500);
  await sleep(150);
  await page.mouse.down();
  await glide(page, to.x, to.y, o.dragMs ?? 700);
  await page.mouse.up();
  await sleep(o.pause ?? 500);
}
export async function key(page, k, pause = 500) { await page.keyboard.press(k); await sleep(pause); }
/** Smooth wheel scrolling at a point. */
export async function wheel(page, x, y, total, o = {}) {
  await glide(page, x, y, 400);
  const steps = o.steps ?? 20;
  for (let i = 0; i < steps; i++) { await page.mouse.wheel(0, total / steps); await sleep(o.dt ?? 30); }
  await sleep(o.pause ?? 400);
}
/** Slide an <input type=range> smoothly between two values. */
export async function slide(page, loc, from, to, ms = 1500) {
  const n = Math.round(ms / 33);
  for (let i = 0; i <= n; i++) {
    const v = from + ((to - from) * i) / n;
    await loc.fill(String(Number(v.toFixed(3))));
    await sleep(25);
  }
}
