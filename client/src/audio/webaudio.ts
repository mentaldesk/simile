import { SAMPLE_RATE } from '../net';
import type { AudioOutput, VoiceOutput } from './player';
import type { Mix } from './spatial';

const SMOOTHING_S = 0.05;

export class WebAudioOutput implements AudioOutput {
  private readonly context: BaseAudioContext;

  constructor(context: BaseAudioContext) {
    this.context = context;
  }

  get now(): number {
    return this.context.currentTime;
  }

  createVoice(): VoiceOutput {
    return new WebAudioVoice(this.context);
  }
}

class WebAudioVoice implements VoiceOutput {
  private readonly context: BaseAudioContext;
  private readonly gain: GainNode;
  private readonly panner: StereoPannerNode;
  private readonly sources = new Set<AudioBufferSourceNode>();

  constructor(context: BaseAudioContext) {
    this.context = context;
    this.gain = new GainNode(context, { gain: 0 });
    this.panner = new StereoPannerNode(context);
    this.gain.connect(this.panner).connect(context.destination);
  }

  play(samples: Float32Array<ArrayBuffer>, at: number): void {
    const buffer = new AudioBuffer({ length: samples.length, sampleRate: SAMPLE_RATE });
    buffer.copyToChannel(samples, 0);
    const source = new AudioBufferSourceNode(this.context, { buffer });
    source.onended = () => this.sources.delete(source);
    source.connect(this.gain);
    source.start(at);
    this.sources.add(source);
  }

  mix({ gain, pan }: Mix): void {
    const now = this.context.currentTime;
    this.gain.gain.setTargetAtTime(gain, now, SMOOTHING_S);
    this.panner.pan.setTargetAtTime(pan, now, SMOOTHING_S);
  }

  close(): void {
    this.sources.forEach((source) => source.stop());
    this.gain.disconnect();
    this.panner.disconnect();
  }
}

export function resumeOnFirstGesture(
  context: Pick<AudioContext, 'resume'>,
  target: EventTarget = window,
): void {
  const events = ['keydown', 'pointerdown'];
  const resume = () =>
    context.resume().then(
      () => events.forEach((event) => target.removeEventListener(event, resume)),
      () => {},
    );
  events.forEach((event) => target.addEventListener(event, resume));
}
