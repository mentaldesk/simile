import {
  SAMPLE_RATE,
  server,
  type ConversationStartedMessage,
  type LineMessage,
  type Position,
} from '../../net';
import { PLAYER_ID } from '../../ui/world-view';
import type { VoicePlayer } from '../player';
import { setPositionProvider } from '../positions';
import { overheardMix, partnerMix } from '../spatial';
import { checkGapless, type GaplessCheck } from './check';
import { arrivalGaps, audioFrames, toInt16 } from './stream';

const wavs = import.meta.glob<string>('../../../../voice-lab/voices/*.wav', {
  query: '?url',
  import: 'default',
  eager: true,
});

type Source = { id: string; name: string; url: string; position: Position; partner: boolean };

const STEP = 0.5;
const MOVES: Record<string, [number, number]> = {
  ArrowLeft: [-STEP, 0],
  ArrowRight: [STEP, 0],
  ArrowUp: [0, -STEP],
  ArrowDown: [0, STEP],
};

const sleep = (seconds: number) => new Promise((resolve) => setTimeout(resolve, seconds * 1000));
const fixed = (value: number) => value.toFixed(2).padStart(5);

export function startHarness(context: AudioContext, player: VoicePlayer): void {
  const sources: Source[] = Object.entries(wavs).map(([path, url], i) => ({
    id: `harness_${i + 1}`,
    name: path.slice(path.lastIndexOf('/') + 1),
    url,
    position: { x: 6 + 6 * i, y: 10 },
    partner: i === 0,
  }));
  const conversationOf = (source: Source) =>
    source.partner ? 'audio-harness-partner' : 'audio-harness';
  const startTalking = (partner: Source) => {
    const started: ConversationStartedMessage = {
      type: 'conversation_started',
      conversation: {
        id: conversationOf(partner),
        participants: [PLAYER_ID, partner.id],
        started: new Date().toISOString(),
        ended: null,
        lines: [],
      },
    };
    server.dispatch(JSON.stringify(started));
  };
  const listener: Position = { x: 10, y: 10 };
  setPositionProvider({
    positionOf: (id) => sources.find((source) => source.id === id)?.position,
    listenerPosition: () => listener,
  });

  const decoded = new Map<Source, Promise<Int16Array>>();
  const load = (source: Source) => {
    const samples =
      decoded.get(source) ??
      fetch(source.url)
        .then((response) => response.arrayBuffer())
        .then((wav) => new OfflineAudioContext(1, 1, SAMPLE_RATE).decodeAudioData(wav))
        .then((audio) => toInt16(audio.getChannelData(0)));
    decoded.set(source, samples);
    return samples;
  };

  let nextLineId = 0xf000_0000;
  let streaming = 0;
  const stream = async (source: Source) => {
    await context.resume();
    const samples = await load(source);
    if (source.partner) startTalking(source);
    const id = nextLineId++;
    const line: LineMessage = {
      type: 'line',
      line: {
        id,
        conversation_id: conversationOf(source),
        speaker: source.id,
        text: source.name,
        timestamp: new Date().toISOString(),
        duration: samples.length / SAMPLE_RATE,
      },
      voiced: true,
    };
    server.dispatch(JSON.stringify(line));
    const frames = audioFrames(id, samples);
    const gaps = arrivalGaps(frames.length);
    streaming++;
    for (const [i, frame] of frames.entries()) {
      server.dispatch(frame);
      await sleep(gaps[i]);
    }
    streaming--;
  };

  let checks: string[] = ['press C'];
  const describe = (source: Source, { seconds, worstError, underruns }: GaplessCheck) =>
    `${source.name}: ${seconds.toFixed(2)} s rendered, worst error ${worstError.toExponential(1)}, ` +
    `${underruns} late chunks: ${worstError < 1e-3 && underruns === 0 ? 'gapless' : 'GAPS'}`;
  const check = async () => {
    checks = ['rendering…'];
    checks = await Promise.all(
      sources.map(async (source) => describe(source, await checkGapless(await load(source)))),
    );
  };

  const panel = document.body.appendChild(document.createElement('pre'));
  panel.id = 'audio-harness';
  Object.assign(panel.style, {
    position: 'fixed',
    top: '8px',
    left: '8px',
    margin: '0',
    padding: '8px',
    background: 'rgba(0, 0, 0, 0.8)',
    color: '#eee',
    font: '12px/1.4 monospace',
    pointerEvents: 'none',
  });
  const render = () => {
    panel.textContent = [
      'Audio harness (dev only)',
      `audio ${context.state}${context.state === 'running' ? '' : ': press a key'}`,
      `listener at (${fixed(listener.x)}, ${fixed(listener.y)}): arrow keys move it`,
      ...sources.map((source, i) => {
        const mixOf = source.partner ? partnerMix : overheardMix;
        const { gain, pan } = mixOf(listener, source.position);
        const { x, y } = source.position;
        const who = source.partner ? 'partner' : 'overheard';
        const mix = `gain ${fixed(gain)}, pan ${fixed(pan)}`;
        return `${i + 1} ${source.name} (${who}) at (${x}, ${y}): ${mix}`;
      }),
      `1-${sources.length} stream that voice, space streams them all at once, C checks gapless`,
      `lines streaming ${streaming}, late chunks ${player.underruns}`,
      ...checks.map((line) => `check: ${line}`),
    ].join('\n');
  };

  window.addEventListener('keydown', (event) => {
    const move = MOVES[event.key];
    if (move) {
      listener.x += move[0];
      listener.y += move[1];
    } else if (event.key === ' ') {
      sources.forEach((source) => void stream(source));
    } else if (event.key.toLowerCase() === 'c') {
      void check();
    } else {
      const source = sources[Number(event.key) - 1];
      if (source) void stream(source);
    }
  });
  setInterval(render, 100);
  render();
}
