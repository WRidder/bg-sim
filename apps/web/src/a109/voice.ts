/**
 * The helicopter's sound. The rotor is noise chopped at the blade-passing rate by one shared
 * oscillator, so the thump stays locked to the rotor's speed whatever the frame rate does. Over it
 * sit the turbines' whine, the tail rotor's buzz and the wind.
 */

import { Sound } from "../engine/audio";

export interface HeliSound {
  /** Rotor speed, 1 at 100 %. */
  rotor: number;
  /** 0..1 engine power. */
  power: number;
  /** m/s through the air. */
  airspeed: number;
  /** 0..1 how hard the blades are working: the slap. */
  load: number;
  /** 0 outside, 1 in the cockpit. */
  inside: number;
}

/** Four blades at 385 rpm. */
const BLADE_RATE = 25.67;
const TAIL_RATE = 69.3;

export class HeliVoice extends Sound {
  private chop!: OscillatorNode;
  private tail!: OscillatorNode;
  private turbine!: OscillatorNode;
  private turbine2!: OscillatorNode;
  private gearbox!: OscillatorNode;
  private thumpGain!: GainNode;
  private thumpFilter!: BiquadFilterNode;
  private slapGain!: GainNode;
  private slapDepth!: GainNode;
  private thumpDepth!: GainNode;
  private tailGain!: GainNode;
  private turbineGain!: GainNode;
  private gearboxGain!: GainNode;
  private windGain!: GainNode;
  private windFilter!: BiquadFilterNode;

  protected override build(context: AudioContext): void {
    // A narrow pulse: a blade going by is a thump with a silence after it, not a sine.
    const harmonics = 14;
    const real = new Float32Array(harmonics);
    const imaginary = new Float32Array(harmonics);
    for (let i = 1; i < harmonics; i += 1) {
      real[i] = Math.exp(-i * 0.22);
    }
    this.chop = context.createOscillator();
    this.chop.setPeriodicWave(context.createPeriodicWave(real, imaginary));
    this.chop.frequency.value = BLADE_RATE;
    this.chop.start();

    const chopped = (rate: number, type: BiquadFilterType, frequency: number): [BiquadFilterNode, GainNode, GainNode] => {
      const [filter, gain] = this.chain(this.loop(rate), type, frequency);
      const shaped = context.createGain();
      filter.disconnect();
      filter.connect(shaped).connect(gain);
      const depth = context.createGain();
      this.chop.connect(depth).connect(shaped.gain);
      return [filter, gain, depth];
    };
    [this.thumpFilter, this.thumpGain, this.thumpDepth] = chopped(0.5, "lowpass", 260);
    let filter: BiquadFilterNode;
    [filter, this.slapGain, this.slapDepth] = chopped(1.4, "bandpass", 1050);
    filter.Q.value = 0.8;

    this.tail = context.createOscillator();
    this.tail.type = "sawtooth";
    this.tail.frequency.value = TAIL_RATE;
    this.tail.start();
    [, this.tailGain] = this.chain(this.tail, "bandpass", 640);

    this.turbine = context.createOscillator();
    this.turbine.type = "sawtooth";
    this.turbine2 = context.createOscillator();
    this.turbine2.type = "triangle";
    [, this.turbineGain] = this.chain(this.turbine, "bandpass", 2900);
    this.turbine2.connect(this.turbineGain);
    this.turbine.start();
    this.turbine2.start();

    this.gearbox = context.createOscillator();
    this.gearbox.frequency.value = 1540;
    [, this.gearboxGain] = this.chain(this.gearbox, "lowpass", 3000);
    this.gearbox.start();

    [this.windFilter, this.windGain] = this.chain(this.loop(1.6), "bandpass", 900);
  }

  update(sound: HeliSound): void {
    const c = this.context;
    if (!c) {
      return;
    }
    const at = c.currentTime;
    const smooth = 0.06;
    const muffle = 1 - 0.55 * sound.inside;
    this.level(at);
    this.chop.frequency.setTargetAtTime(BLADE_RATE * sound.rotor, at, smooth);
    this.tail.frequency.setTargetAtTime(TAIL_RATE * sound.rotor, at, smooth);
    this.thumpDepth.gain.setTargetAtTime(0.5 + 0.4 * sound.load, at, smooth);
    this.thumpGain.gain.setTargetAtTime((1.1 + 1.3 * sound.load) * muffle * Math.min(sound.rotor, 1), at, smooth);
    this.thumpFilter.frequency.setTargetAtTime(170 + 200 * sound.load, at, smooth);
    this.slapDepth.gain.setTargetAtTime(0.9, at, smooth);
    this.slapGain.gain.setTargetAtTime(sound.load * sound.load * 0.8 * muffle, at, smooth);
    this.tailGain.gain.setTargetAtTime(0.02 * muffle, at, smooth);
    this.turbine.frequency.setTargetAtTime(2500 + 900 * sound.power, at, smooth);
    this.turbine2.frequency.setTargetAtTime(1720 + 620 * sound.power, at, smooth);
    this.turbineGain.gain.setTargetAtTime((0.012 + 0.02 * sound.power) * (1 - 0.3 * sound.inside), at, smooth);
    this.gearboxGain.gain.setTargetAtTime(0.008 * sound.inside, at, smooth);
    const air = Math.min(sound.airspeed / 90, 1.2);
    this.windGain.gain.setTargetAtTime(air * air * (0.5 + 0.5 * sound.inside), at, smooth);
    this.windFilter.frequency.setTargetAtTime(500 + 900 * air, at, smooth);
  }

  /** Tyres meeting a deck: heavier the faster it came down. */
  touch(sink: number): void {
    this.tone(90, 0.16, Math.min(0.3 + sink * 0.25, 0.6), "triangle");
    if (sink > 1) {
      this.tone(55, 0.3, 0.4, "square");
    }
  }

  /** A landing that counted: a chime that rises with the grade. */
  landed(score: number): void {
    const notes = score >= 90 ? [660, 880, 1320] : score >= 55 ? [660, 880] : [440];
    notes.forEach((frequency, i) => this.tone(frequency, 0.34, 0.16, "sine", i * 0.11));
  }
}
