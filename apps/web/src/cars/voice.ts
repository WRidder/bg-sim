/**
 * The cars are electric, so the note is a motor's: a clean whine that follows the rotor, with the
 * reduction gears singing an interval above it, and a growl under load. Around it the road: tyres
 * scrubbing, stones in the arches, the kerb's buzz, the wind.
 */

import { Sound } from "../engine/audio";

export interface CarSound {
  /** Rotor speed, rpm. */
  rpm: number;
  /** -1..1 of the motor's power: negative while it brakes the car. */
  load: number;
  /** Tyres past their grip, 0..1. */
  slip: number;
  /** Wheels on something loose, 0..1. */
  loose: number;
  /** Wheels on a kerb, 0..1. */
  kerb: number;
  /** m/s. */
  speed: number;
  /** 1 inside the car. */
  inside: number;
}

export class CarVoice extends Sound {
  private motor!: OscillatorNode;
  private motorTop!: OscillatorNode;
  private gears!: OscillatorNode;
  private motorGain!: GainNode;
  private motorTopGain!: GainNode;
  private gearGain!: GainNode;
  private motorFilter!: BiquadFilterNode;
  private growlGain!: GainNode;
  private growlFilter!: BiquadFilterNode;
  private squeal!: OscillatorNode;
  private squealGain!: GainNode;
  private scrubGain!: GainNode;
  private scrubFilter!: BiquadFilterNode;
  private looseGain!: GainNode;
  private kerbGain!: GainNode;
  private kerbBuzz!: OscillatorNode;
  private windGain!: GainNode;
  private windFilter!: BiquadFilterNode;
  private rollGain!: GainNode;

  protected override build(context: AudioContext): void {
    const oscillator = (type: OscillatorType): OscillatorNode => {
      const node = context.createOscillator();
      node.type = type;
      node.start();
      return node;
    };
    this.motor = oscillator("sawtooth");
    this.motorTop = oscillator("square");
    this.gears = oscillator("triangle");
    [this.motorFilter, this.motorGain] = this.chain(this.motor, "bandpass", 900);
    this.motorFilter.Q.value = 0.8;
    [, this.motorTopGain] = this.chain(this.motorTop, "bandpass", 2600);
    [, this.gearGain] = this.chain(this.gears, "highpass", 500);
    [this.growlFilter, this.growlGain] = this.chain(this.loop(0.9), "lowpass", 260);
    this.squeal = oscillator("sawtooth");
    const [squealFilter, squealGain] = this.chain(this.squeal, "bandpass", 1500);
    squealFilter.Q.value = 7;
    this.squealGain = squealGain;
    [this.scrubFilter, this.scrubGain] = this.chain(this.loop(2.2), "bandpass", 1300);
    this.scrubFilter.Q.value = 2.5;
    [, this.looseGain] = this.chain(this.loop(2.6), "highpass", 1100);
    this.kerbBuzz = oscillator("square");
    [, this.kerbGain] = this.chain(this.kerbBuzz, "lowpass", 300);
    [this.windFilter, this.windGain] = this.chain(this.loop(1.7), "bandpass", 700);
    [, this.rollGain] = this.chain(this.loop(0.5), "lowpass", 160);
  }

  update(s: CarSound): void {
    const c = this.context;
    if (!c) {
      return;
    }
    const at = c.currentTime;
    const smooth = 0.05;
    this.level(at);
    const hertz = Math.abs(s.rpm) / 60;
    const pitch = 40 + hertz * 0.42;
    const effort = Math.abs(s.load);
    const muffle = 1 - 0.45 * s.inside;
    this.motor.frequency.setTargetAtTime(pitch, at, smooth);
    this.motorTop.frequency.setTargetAtTime(pitch * 2.02, at, smooth);
    this.gears.frequency.setTargetAtTime(pitch * 3.5, at, smooth);
    this.motorFilter.frequency.setTargetAtTime(300 + pitch * 1.4 + 900 * effort, at, smooth);
    const moving = Math.min(1, hertz / 40);
    this.motorGain.gain.setTargetAtTime(moving * (0.05 + 0.12 * effort) * muffle, at, smooth);
    this.motorTopGain.gain.setTargetAtTime(moving * (0.006 + 0.028 * effort) * muffle, at, smooth);
    this.gearGain.gain.setTargetAtTime(moving * (0.012 + 0.03 * Math.max(0, -s.load) + 0.012 * effort), at, smooth);
    this.growlFilter.frequency.setTargetAtTime(180 + 200 * effort, at, smooth);
    this.growlGain.gain.setTargetAtTime(0.3 * effort * moving, at, 0.08);
    this.squeal.frequency.setTargetAtTime(760 + 340 * s.slip + 60 * Math.sin(at * 37), at, 0.02);
    this.squealGain.gain.setTargetAtTime(s.slip * s.slip * 0.1, at, 0.03);
    this.scrubGain.gain.setTargetAtTime(s.slip * 1.2, at, 0.03);
    this.looseGain.gain.setTargetAtTime(s.loose * Math.min(1, s.speed / 18) * 0.6, at, 0.05);
    this.kerbBuzz.frequency.setTargetAtTime(Math.max(30, s.speed * 2.4), at, 0.02);
    this.kerbGain.gain.setTargetAtTime(s.kerb * Math.min(1, s.speed / 14) * 0.16, at, 0.015);
    const air = Math.min(s.speed / 80, 1.2);
    this.windGain.gain.setTargetAtTime(air * air * (0.55 + 0.35 * s.inside), at, smooth);
    this.windFilter.frequency.setTargetAtTime(380 + 1100 * air, at, smooth);
    this.rollGain.gain.setTargetAtTime(Math.min(1, s.speed / 30) * 0.5, at, smooth);
  }

  /** A start light; the last one is higher and held. */
  lightBeep(go: boolean): void {
    this.tone(go ? 1320 : 660, go ? 0.5 : 0.16, 0.16, "square");
  }

  /** Over the line: two rising notes, or three on a best. */
  lap(best: boolean): void {
    this.tone(880, 0.18, 0.14);
    this.tone(1175, 0.3, 0.14, "sine", 0.09);
    if (best) {
      this.tone(1568, 0.5, 0.16, "sine", 0.2);
    }
  }

  /** A low thud: the lap no longer counts. */
  fault(): void {
    this.tone(180, 0.3, 0.2, "triangle");
  }

  thump(): void {
    this.tone(70, 0.24, 0.5, "sine");
  }
}
