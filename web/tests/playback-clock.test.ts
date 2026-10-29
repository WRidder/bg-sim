import { describe, expect, it } from "vitest";
import { liveHead, PlaybackClock } from "../src/viewer/playbackClock";

describe("PlaybackClock", () => {
  it("advances with wall time times the speed", () => {
    const c = new PlaybackClock(1, 5);
    expect(c.time(0)).toBe(1);
    c.play(1000);
    expect(c.time(1500)).toBeCloseTo(1.5);
    c.setSpeed(2, 1500);
    expect(c.time(2000)).toBeCloseTo(2.5);
    c.setSpeed(0.1, 2000);
    expect(c.time(3000)).toBeCloseTo(2.6);
  });
  it("re-anchors on seek and keeps playing from there", () => {
    const c = new PlaybackClock(0, 10);
    c.play(0);
    c.seek(7, 2000);
    expect(c.time(2000)).toBe(7);
    expect(c.time(3000)).toBeCloseTo(8);
    expect(c.playing(3000)).toBe(true);
  });
  it("pauses at the current time", () => {
    const c = new PlaybackClock(0, 10);
    c.play(0);
    c.pause(2500);
    expect(c.time(9000)).toBeCloseTo(2.5);
    expect(c.playing(9000)).toBe(false);
  });
  it("stops at the end and plays again from the start", () => {
    const c = new PlaybackClock(0, 2);
    c.play(0);
    expect(c.playing(1999)).toBe(true);
    expect(c.playing(2500)).toBe(false);
    expect(c.time(2500)).toBe(2);
    c.play(3000);
    expect(c.time(3000)).toBe(0);
    expect(c.playing(3500)).toBe(true);
  });
  it("wraps when looping", () => {
    const c = new PlaybackClock(1, 3);
    c.setLoop(true, 0);
    c.play(0);
    expect(c.time(2500)).toBeCloseTo(1.5);
    expect(c.playing(99999)).toBe(true);
    c.pause(2500);
    expect(c.time(5000)).toBeCloseTo(1.5);
  });
  it("clamps a seek and ignores a bad speed", () => {
    const c = new PlaybackClock(0, 2);
    c.seek(99, 0);
    expect(c.time(0)).toBe(2);
    c.seek(-5, 0);
    expect(c.time(0)).toBe(0);
    c.setSpeed(0, 0);
    c.setSpeed(Number.NaN, 0);
    expect(c.speed).toBe(1);
  });
  it("keeps the head inside a new range and notifies subscribers", () => {
    const c = new PlaybackClock(0, 10);
    let calls = 0;
    const off = c.subscribe(() => {
      calls++;
    });
    c.seek(8, 0);
    c.setRange(0, 4, 0);
    expect(c.time(0)).toBe(4);
    expect(calls).toBe(2);
    off();
    c.seek(1, 0);
    expect(calls).toBe(2);
  });
});

describe("liveHead", () => {
  it("is 1.5 sample intervals behind the newest sample, never ahead of it", () => {
    expect(liveHead({ t0: 0, t1: 10 }, 0.2)).toBeCloseTo(9.7);
    expect(liveHead({ t0: 0, t1: 10 }, null)).toBe(10);
  });
  it("holds the first sample while the data is shorter than the delay", () => {
    expect(liveHead({ t0: 0, t1: 0.1 }, 0.5)).toBe(0);
  });
  it("has no head without data", () => {
    expect(liveHead(null, 0.1)).toBeNull();
  });
});
