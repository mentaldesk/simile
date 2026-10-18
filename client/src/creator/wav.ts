/** P11 takes at most 10 MB and 60 s, and its checks want 5 to 25 s. */
export const MAX_RECORDING_SECONDS = 30;
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
export const UPLOAD_TYPES = ['.wav', '.mp3', '.m4a'];

export function encodeWav(
  chunks: readonly Float32Array[],
  sampleRate: number,
): Uint8Array<ArrayBuffer> {
  const samples = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const bytes = new Uint8Array(44 + samples * 2);
  const view = new DataView(bytes.buffer);
  const text = (offset: number, value: string) =>
    [...value].forEach((char, i) => view.setUint8(offset + i, char.charCodeAt(0)));
  text(0, 'RIFF');
  view.setUint32(4, 36 + samples * 2, true);
  text(8, 'WAVE');
  text(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  text(36, 'data');
  view.setUint32(40, samples * 2, true);
  let offset = 44;
  for (const chunk of chunks) {
    for (const sample of chunk) {
      const s = Math.max(-1, Math.min(1, sample));
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      offset += 2;
    }
  }
  return bytes;
}

export function uploadProblem(file: { name: string; size: number }): string | null {
  const name = file.name.toLowerCase();
  if (!UPLOAD_TYPES.some((type) => name.endsWith(type))) return 'Choose a WAV, MP3 or M4A file.';
  if (file.size > MAX_UPLOAD_BYTES) return 'That file is over 10 MB.';
  if (file.size === 0) return 'That file is empty.';
  return null;
}

/** Records the microphone as raw samples, since `MediaRecorder` only makes WebM or MP4. */
export class MicRecorder {
  seconds = 0;
  level = 0;
  onTick: () => void = () => {};
  onLimit: () => void = () => {};
  private readonly chunks: Float32Array[] = [];
  private readonly context: AudioContext;
  private readonly stream: MediaStream;
  private readonly processor: ScriptProcessorNode;

  private constructor(context: AudioContext, stream: MediaStream) {
    this.context = context;
    this.stream = stream;
    const source = context.createMediaStreamSource(stream);
    this.processor = context.createScriptProcessor(4096, 1, 1);
    const silent = context.createGain();
    silent.gain.value = 0;
    this.processor.onaudioprocess = ({ inputBuffer }) => {
      const samples = new Float32Array(inputBuffer.getChannelData(0));
      this.chunks.push(samples);
      this.seconds += samples.length / context.sampleRate;
      this.level = Math.sqrt(samples.reduce((total, s) => total + s * s, 0) / samples.length);
      this.onTick();
      if (this.seconds >= MAX_RECORDING_SECONDS) this.onLimit();
    };
    source.connect(this.processor);
    this.processor.connect(silent);
    silent.connect(context.destination);
  }

  static async start(): Promise<MicRecorder> {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
      },
    });
    const context = new AudioContext();
    await context.resume();
    return new MicRecorder(context, stream);
  }

  stop(): Uint8Array<ArrayBuffer> {
    this.processor.onaudioprocess = null;
    this.processor.disconnect();
    this.stream.getTracks().forEach((track) => track.stop());
    void this.context.close();
    return encodeWav(this.chunks, this.context.sampleRate);
  }
}
