/**
 * Sound made on the spot, so a game carries no audio files. Filtered noise and a few oscillators
 * follow the simulation: a browser only lets a page make sound after a click, so `start` must be
 * called from one.
 */

export interface JetSound {
  /** 0..1 engine power. */
  power: number;
  /** 0..1 afterburner. */
  burner: number;
  /** m/s through the air. */
  airspeed: number;
  /** 0..1 buffet near the stall or at high load. */
  buffet: number;
  /** 0 outside, 1 in the cockpit: muffles the engine and keeps the wind. */
  inside: number;
}

function noiseBuffer(context: AudioContext, seconds: number): AudioBuffer {
  const buffer = context.createBuffer(2, context.sampleRate * seconds, context.sampleRate);
  for (let channel = 0; channel < 2; channel += 1) {
    const data = buffer.getChannelData(channel);
    let brown = 0;
    for (let i = 0; i < data.length; i += 1) {
      brown = (brown + 0.02 * (Math.random() * 2 - 1)) / 1.02;
      data[i] = brown * 3.5;
    }
  }
  return buffer;
}

/** The sound card's side of a game: looping noise, filters, one-shot tones. A voice builds on it. */
export class Sound {
  protected context: AudioContext | null = null;
  protected master!: GainNode;
  private warningAt = 0;
  muted = false;

  /** Call from a click or a key press: a browser allows sound from nothing else. */
  start(): void {
    if (this.context) {
      void this.context.resume();
      return;
    }
    const context = new AudioContext();
    this.context = context;
    this.master = context.createGain();
    const limiter = context.createDynamicsCompressor();
    this.master.connect(limiter).connect(context.destination);
    this.master.gain.value = 0.7;
    this.noise = noiseBuffer(context, 4);
    this.build(context);
  }

  private noise!: AudioBuffer;

  /** Sets up the voice: the context exists from here on. */
  protected build(_context: AudioContext): void {}

  /** Looping brown noise, playing from now on. */
  protected loop(rate: number): AudioBufferSourceNode {
    const source = (this.context as AudioContext).createBufferSource();
    source.buffer = this.noise;
    source.loop = true;
    source.playbackRate.value = rate;
    source.start();
    return source;
  }

  /** A source through a filter and a gain into the master, silent until the gain is raised. */
  protected chain(source: AudioNode, type: BiquadFilterType, frequency: number): [BiquadFilterNode, GainNode] {
    const context = this.context as AudioContext;
    const filter = context.createBiquadFilter();
    filter.type = type;
    filter.frequency.value = frequency;
    const gain = context.createGain();
    gain.gain.value = 0;
    source.connect(filter).connect(gain).connect(this.master);
    return [filter, gain];
  }

  stop(): void {
    void this.context?.suspend();
  }

  /** Mutes or unmutes; call it each frame. */
  protected level(at: number): void {
    this.master.gain.setTargetAtTime(this.muted ? 0 : 0.7, at, 0.02);
  }

  protected tone(frequency: number, seconds: number, level: number, type: OscillatorType = "sine", delay = 0): void {
    const c = this.context;
    if (!c || this.muted) {
      return;
    }
    const oscillator = c.createOscillator();
    oscillator.type = type;
    oscillator.frequency.value = frequency;
    const gain = c.createGain();
    const at = c.currentTime + delay;
    gain.gain.setValueAtTime(0, at);
    gain.gain.linearRampToValueAtTime(level, at + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, at + seconds);
    oscillator.connect(gain).connect(this.master);
    oscillator.start(at);
    oscillator.stop(at + seconds);
  }

  /** Going through a gate: a rising chime, or a low note for a miss. */
  gate(hit: boolean): void {
    if (hit) {
      this.tone(784, 0.2, 0.2);
      this.tone(1175, 0.34, 0.2, "sine", 0.07);
    } else {
      this.tone(196, 0.3, 0.16, "triangle");
    }
  }

  /** The master warning: at most one beep every 0.6 s. */
  warning(): void {
    const c = this.context;
    if (!c || c.currentTime < this.warningAt) {
      return;
    }
    this.warningAt = c.currentTime + 0.6;
    this.tone(1250, 0.14, 0.09, "square");
  }

  crash(): void {
    const c = this.context;
    if (!c) {
      return;
    }
    const length = c.sampleRate * 2.4;
    const buffer = c.createBuffer(1, length, c.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < length; i += 1) {
      data[i] = (Math.random() * 2 - 1) * Math.exp((-5 * i) / length);
    }
    const source = c.createBufferSource();
    source.buffer = buffer;
    const filter = c.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.value = 500;
    source.connect(filter).connect(this.master);
    source.start();
  }
}

/** A jet: rumble and turbine whine, afterburner roar, wind, and a low shudder near the stall. */
export class JetVoice extends Sound {
  private rumbleGain!: GainNode;
  private rumbleFilter!: BiquadFilterNode;
  private whine!: OscillatorNode;
  private whineGain!: GainNode;
  private burnerGain!: GainNode;
  private windGain!: GainNode;
  private windFilter!: BiquadFilterNode;
  private buffetGain!: GainNode;

  protected override build(context: AudioContext): void {
    [this.rumbleFilter, this.rumbleGain] = this.chain(this.loop(1), "lowpass", 220);
    [, this.burnerGain] = this.chain(this.loop(0.62), "lowpass", 340);
    [this.windFilter, this.windGain] = this.chain(this.loop(1.7), "bandpass", 900);
    [, this.buffetGain] = this.chain(this.loop(0.3), "lowpass", 70);
    this.whine = context.createOscillator();
    this.whine.type = "sawtooth";
    [, this.whineGain] = this.chain(this.whine, "bandpass", 2400);
    this.whine.start();
  }

  update(sound: JetSound): void {
    const c = this.context;
    if (!c) {
      return;
    }
    const at = c.currentTime;
    const smooth = 0.08;
    const muffle = 1 - 0.65 * sound.inside;
    this.level(at);
    this.rumbleGain.gain.setTargetAtTime((0.14 + 0.62 * sound.power) * muffle, at, smooth);
    this.rumbleFilter.frequency.setTargetAtTime(150 + 420 * sound.power * muffle, at, smooth);
    this.whine.frequency.setTargetAtTime(420 + 2300 * sound.power, at, smooth);
    this.whineGain.gain.setTargetAtTime(0.012 + 0.032 * sound.power * muffle, at, smooth);
    this.burnerGain.gain.setTargetAtTime(1.15 * sound.burner * muffle, at, 0.16);
    const air = Math.min(sound.airspeed / 320, 1.3);
    this.windGain.gain.setTargetAtTime(air * air * (0.26 + 0.4 * sound.inside), at, smooth);
    this.windFilter.frequency.setTargetAtTime(420 + 1400 * air, at, smooth);
    this.buffetGain.gain.setTargetAtTime(sound.buffet * 2.2, at, 0.05);
  }
}
