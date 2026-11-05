/**
 * A flat-four and a two-blade propeller. Everything keys off the engine's speed: the exhaust fires
 * twice a revolution, and the propeller's blades pass twice a revolution, so one number drives the
 * whole note. Noise keyed by the exhaust gives the uneven chuff at idle.
 */

import { Sound } from "../engine/audio";

export interface PistonSound {
  rpm: number;
  /** 0..1 how hard the engine is working. */
  power: number;
  /** m/s through the air. */
  airspeed: number;
  /** m/s over the runway, when the wheels are on it; 0 otherwise. */
  rolling: number;
  /** 0..1 the stall warning. */
  stall: number;
  /** 0 outside, 1 in the cabin. */
  inside: number;
}

export class PistonVoice extends Sound {
  private exhaust!: OscillatorNode;
  private exhaustHalf!: OscillatorNode;
  private body!: BiquadFilterNode;
  private bodyGain!: GainNode;
  private chuff!: GainNode;
  private chuffKey!: GainNode;
  private chuffFilter!: BiquadFilterNode;
  private prop!: OscillatorNode;
  private propFilter!: BiquadFilterNode;
  private propGain!: GainNode;
  private windFilter!: BiquadFilterNode;
  private windGain!: GainNode;
  private tyreGain!: GainNode;
  private hornGain!: GainNode;
  private scrubGain!: GainNode;

  protected override build(context: AudioContext): void {
    this.exhaust = context.createOscillator();
    this.exhaust.type = "sawtooth";
    this.exhaustHalf = context.createOscillator();
    this.exhaustHalf.type = "square";
    const mix = context.createGain();
    mix.gain.value = 0.5;
    this.exhaust.connect(mix);
    this.exhaustHalf.connect(mix);
    [this.body, this.bodyGain] = this.chain(mix, "lowpass", 300);
    this.body.Q.value = 2;

    // Noise opened and shut by the exhaust note: a modulator on the gain itself.
    const noise = this.loop(1.3);
    this.chuffKey = context.createGain();
    this.chuffKey.gain.value = 0;
    this.chuffFilter = context.createBiquadFilter();
    this.chuffFilter.type = "bandpass";
    this.chuffFilter.frequency.value = 500;
    this.chuff = context.createGain();
    this.chuff.gain.value = 0;
    noise.connect(this.chuffFilter).connect(this.chuffKey).connect(this.chuff).connect(this.master);
    const key = context.createGain();
    key.gain.value = 0.9;
    this.exhaustHalf.connect(key).connect(this.chuffKey.gain);

    this.prop = context.createOscillator();
    this.prop.type = "sawtooth";
    [this.propFilter, this.propGain] = this.chain(this.prop, "bandpass", 420);
    this.propFilter.Q.value = 0.9;
    [this.windFilter, this.windGain] = this.chain(this.loop(1.7), "bandpass", 700);
    [, this.tyreGain] = this.chain(this.loop(0.34), "lowpass", 140);
    [, this.scrubGain] = this.chain(this.loop(2.4), "bandpass", 1500);
    const horn = context.createOscillator();
    horn.type = "triangle";
    horn.frequency.value = 1450;
    [, this.hornGain] = this.chain(horn, "bandpass", 1450);
    this.exhaust.start();
    this.exhaustHalf.start();
    this.prop.start();
    horn.start();
  }

  update(s: PistonSound): void {
    const c = this.context;
    if (!c) {
      return;
    }
    const at = c.currentTime;
    const smooth = 0.06;
    this.level(at);
    const turning = Math.max(s.rpm, 0);
    const firing = (turning / 60) * 2;
    const alive = Math.min(turning / 500, 1);
    const muffle = 1 - 0.45 * s.inside;
    this.exhaust.frequency.setTargetAtTime(Math.max(firing, 4), at, smooth);
    this.exhaustHalf.frequency.setTargetAtTime(Math.max(firing / 2, 2), at, smooth);
    this.body.frequency.setTargetAtTime(120 + 520 * s.power * muffle + firing * 1.5, at, smooth);
    this.bodyGain.gain.setTargetAtTime(alive * (0.1 + 0.2 * s.power) * muffle, at, smooth);
    this.chuff.gain.setTargetAtTime(alive * (0.35 + 0.9 * s.power) * muffle, at, smooth);
    this.chuffFilter.frequency.setTargetAtTime(280 + firing * 5, at, smooth);
    this.prop.frequency.setTargetAtTime(Math.max(firing * 2, 4), at, smooth);
    this.propFilter.frequency.setTargetAtTime(260 + firing * 4, at, smooth);
    this.propGain.gain.setTargetAtTime(alive * (0.02 + 0.07 * s.power) * (1 - 0.3 * s.inside), at, smooth);
    const air = Math.min(s.airspeed / 70, 1.4);
    this.windGain.gain.setTargetAtTime(air * air * (0.3 + 0.35 * s.inside), at, smooth);
    this.windFilter.frequency.setTargetAtTime(300 + 900 * air, at, smooth);
    this.tyreGain.gain.setTargetAtTime(Math.min(s.rolling / 30, 1) * 1.2, at, 0.04);
    this.hornGain.gain.setTargetAtTime(s.stall * 0.09, at, 0.03);
  }

  /** Rubber meeting the runway: louder the harder it was. */
  chirp(sink: number): void {
    const c = this.context;
    if (!c || this.muted) {
      return;
    }
    const at = c.currentTime;
    const level = 0.12 + Math.min(sink / 500, 1) * 0.5;
    this.scrubGain.gain.cancelScheduledValues(at);
    this.scrubGain.gain.setValueAtTime(level, at);
    this.scrubGain.gain.exponentialRampToValueAtTime(0.001, at + 0.3);
  }

  /** The flap motor. */
  flap(): void {
    this.tone(150, 0.5, 0.03, "sawtooth");
    this.tone(180, 0.5, 0.02, "square");
  }

  /** The engine stumbling to a stop. */
  cough(): void {
    for (const delay of [0, 0.22, 0.4, 0.7]) {
      this.tone(70 + delay * 40, 0.14, 0.24, "square", delay);
    }
  }

  /** The score going up on the result. */
  fanfare(): void {
    this.tone(523, 0.22, 0.14, "triangle");
    this.tone(659, 0.22, 0.14, "triangle", 0.12);
    this.tone(784, 0.4, 0.16, "triangle", 0.24);
  }
}
