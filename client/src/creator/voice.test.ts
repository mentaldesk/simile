// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Capabilities, CreatorApi } from './api';
import { character } from './character.fixture';
import { Draft } from './draft';
import type { Job, SocketLike } from './jobs';
import { VoiceStep, type VoiceContext, transcriptProblem } from './voice';

const CAN_CHECK: Capabilities = {
  machine: { apple_silicon: true, voice_lab: true, voice_lab_mlx: true },
  kinds: {
    voice_design: { available: true, reason: null },
    voice_check: { available: true, reason: null },
  },
};
const TRANSCRIPT = 'Come in out of the rain, the kettle’s on and there’s a seat by the stove for you.';

function checked(overrides: Record<string, unknown> = {}): Job {
  return {
    id: '3f9c2a7d1b6e4c08',
    kind: 'voice_check',
    state: 'succeeded',
    progress: 1,
    message: 'Checked',
    error: null,
    result: {
      seconds: 8.1,
      heard: TRANSCRIPT,
      word_error_rate: 0,
      accent: 'scotland 81%',
      sample_accents: ['scotland 70%', 'scotland 64%', 'scotland 77%'],
      errors: [],
      problems: [],
      warnings: [],
      reference_line: TRANSCRIPT,
      clip: '/api/jobs/files/voice_check/3f9c2a7d1b6e4c08.wav',
      samples: [1, 2, 3].map((n) => `/api/jobs/files/voice_check/3f9c2a7d1b6e4c08_${n}.wav`),
      usable: true,
      ...overrides,
    },
    created: '2026-10-18T09:30:00Z',
    started: '2026-10-18T09:30:01Z',
    finished: '2026-10-18T09:30:40Z',
  };
}

function fakeApi() {
  const socket: SocketLike = { onmessage: null, onclose: null, close: () => {} };
  const voiced = character({
    voice: {
      ...character().voice,
      reference_line: TRANSCRIPT,
      reference_clip: 'clips/wren_abernethy.wav',
    },
  });
  return {
    characters: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    exportUrl: (id: string) => `/api/characters/${id}/export`,
    importFile: vi.fn(),
    generate: vi.fn(),
    reroll: vi.fn(),
    player: vi.fn(),
    savePlayer: vi.fn(),
    capabilities: vi.fn(),
    submit: vi.fn(),
    job: vi.fn(),
    cancel: vi.fn(),
    watch: vi.fn(() => socket),
    atlas: vi.fn(),
    voices: vi.fn(async () => []),
    record: vi.fn(async () => checked()),
    pick: vi.fn(async () => voiced),
    say: vi.fn(),
  } satisfies CreatorApi;
}

function step(
  api: CreatorApi,
  capabilities: Capabilities | null = CAN_CHECK,
  saved = character(),
) {
  const ctx: VoiceContext = {
    api,
    capabilities,
    draft: Draft.of(saved),
    readOnly: false,
    edit: vi.fn(),
    ensureSaved: vi.fn(async () => true),
    picked: vi.fn(async () => {}),
  };
  const voice = new VoiceStep(ctx);
  voice.render();
  document.body.append(voice.root);
  return { voice, ctx };
}

function buttonCalled(root: HTMLElement, text: string): HTMLButtonElement {
  const found = [...root.querySelectorAll('button')].find((b) => b.textContent === text);
  if (!found) throw new Error(`No ${text} button`);
  return found;
}

function transcriptBox(root: HTMLElement): HTMLTextAreaElement {
  const box = root.querySelector<HTMLTextAreaElement>('.creator-transcript textarea');
  if (!box) throw new Error('No transcript box');
  return box;
}

function choose(root: HTMLElement, file: File): void {
  const input = root.querySelector<HTMLInputElement>('.creator-ways input[type="file"]')!;
  Object.defineProperty(input, 'files', { value: [file], configurable: true });
  input.dispatchEvent(new Event('change'));
}

function type(box: HTMLTextAreaElement, text: string): void {
  box.value = text;
  box.dispatchEvent(new Event('input'));
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
const note = (root: HTMLElement) => root.querySelector('.creator-note')?.textContent;

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => 'blob:clip');
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  document.body.replaceChildren();
});

describe('uploading a clip', () => {
  it('is its own way, with what the clip says filled in from their line', () => {
    const { voice } = step(fakeApi());

    buttonCalled(voice.root, 'Upload a clip').click();

    expect(transcriptBox(voice.root).value).toBe(character().voice.reference_line);
    expect(buttonCalled(voice.root, 'Choose a clip…')).toBeTruthy();
  });

  it('sends the clip with its own transcript, and using it makes that their line', async () => {
    const api = fakeApi();
    const { voice, ctx } = step(api);
    buttonCalled(voice.root, 'Upload a clip').click();
    const file = new File(['RIFF'], 'from-elsewhere.m4a', { type: 'audio/mp4' });

    choose(voice.root, file);
    type(transcriptBox(voice.root), ` ${TRANSCRIPT}\n`);
    buttonCalled(voice.root, 'Check it').click();
    await settle();

    expect(ctx.ensureSaved).toHaveBeenCalled();
    expect(api.record).toHaveBeenCalledWith('wren_abernethy', file, ` ${TRANSCRIPT}\n`);
    const result = voice.root.querySelector('.creator-check')!;
    expect(result.textContent).toContain('It passed its checks.');
    expect(result.textContent).toContain(`Using it makes “${TRANSCRIPT}” their line.`);
    expect(result.querySelectorAll('audio')).toHaveLength(3);

    buttonCalled(voice.root, 'Use this voice').click();
    await settle();

    expect(api.pick).toHaveBeenCalledWith('wren_abernethy', { recording: '3f9c2a7d1b6e4c08' });
    expect(ctx.picked).toHaveBeenCalledWith(await api.pick.mock.results[0].value, undefined);
    expect(note(voice.root)).toBe('Voice saved.');
  });

  it.each([
    ['Come in out of the rain.', 'it has to be 12 to 25 words, not 6.'],
    [TRANSCRIPT.replace('.', '!'), 'so it can’t have a “!”.'],
    ['  ', 'Write exactly what the clip says first.'],
  ])('checks the transcript %j before uploading', async (transcript, problem) => {
    const api = fakeApi();
    const { voice, ctx } = step(api);
    buttonCalled(voice.root, 'Upload a clip').click();
    choose(voice.root, new File(['RIFF'], 'clip.wav', { type: 'audio/wav' }));

    type(transcriptBox(voice.root), transcript);

    expect(voice.root.querySelector('.creator-transcript .creator-warn')?.textContent).toContain(
      problem,
    );
    buttonCalled(voice.root, 'Check it').click();
    await settle();
    expect(note(voice.root)).toContain(problem);
    expect(ctx.ensureSaved).not.toHaveBeenCalled();
    expect(api.record).not.toHaveBeenCalled();

    type(transcriptBox(voice.root), TRANSCRIPT);
    expect(note(voice.root)).toBeUndefined();
    buttonCalled(voice.root, 'Check it').click();
    await settle();
    expect(api.record).toHaveBeenCalledWith('wren_abernethy', expect.any(File), TRANSCRIPT);
  });

  it('shows what a failed check found, without a way to use it', async () => {
    const api = fakeApi();
    api.record.mockResolvedValue(
      checked({ usable: false, problems: ['word error rate 58%', 'ending missing'] }),
    );
    const { voice } = step(api);
    buttonCalled(voice.root, 'Upload a clip').click();
    choose(voice.root, new File(['RIFF'], 'clip.wav', { type: 'audio/wav' }));

    buttonCalled(voice.root, 'Check it').click();
    await settle();

    const result = voice.root.querySelector('.creator-check')!;
    expect(result.textContent).toContain('It didn’t pass its checks.');
    expect(result.textContent).toContain('word error rate 58%; ending missing');
    expect([...voice.root.querySelectorAll('button')].map((b) => b.textContent)).not.toContain(
      'Use this voice',
    );
  });

  it('refuses a file that isn’t audio before it goes up', () => {
    const api = fakeApi();
    const { voice } = step(api);
    buttonCalled(voice.root, 'Upload a clip').click();

    choose(voice.root, new File(['x'], 'clip.webm', { type: 'audio/webm' }));

    expect(note(voice.root)).toBe('Choose a WAV, MP3 or M4A file.');
    expect(voice.root.querySelector('.creator-ways audio')).toBeNull();
  });

  it('opens on uploading when the voice designer can’t do the accent', () => {
    const { voice } = step(
      fakeApi(),
      CAN_CHECK,
      character({ voice: { ...character().voice, needs_recording: true } }),
    );

    expect(buttonCalled(voice.root, 'Upload a clip').getAttribute('aria-pressed')).toBe('true');
    expect(transcriptBox(voice.root)).toBeTruthy();
  });

  it('takes the limits from import_voices.py', () => {
    expect(transcriptProblem(TRANSCRIPT)).toBeNull();
    expect(transcriptProblem(Array(25).fill('word').join(' '))).toBeNull();
    expect(transcriptProblem(Array(26).fill('word').join(' '))).toContain('not 26.');
    expect(transcriptProblem(Array(11).fill('word').join(' '))).toContain('not 11.');
  });
});

describe('when clips can’t be checked here', () => {
  const without = (machine: Record<string, boolean>): Capabilities => ({
    machine,
    kinds: { voice_check: { available: false, reason: 'voice_check jobs need …' } },
  });

  it.each([
    [
      without({ apple_silicon: false }),
      'Checking a clip needs a Mac with Apple Silicon. Start the game with ./run.sh on one, with voice-lab set up as voice-lab/README.md says.',
    ],
    [
      without({ apple_silicon: true, voice_lab: true, voice_lab_mlx: false }),
      'Checking a clip needs voice-lab’s two virtualenvs. Set them up as voice-lab/README.md says, then start the game again with ./run.sh.',
    ],
    [
      null,
      'Checking a clip isn’t available: the server didn’t say what it can run. Start the game with ./run.sh',
    ],
  ])('says how to make it available', (capabilities, fix) => {
    const { voice } = step(fakeApi(), capabilities);

    buttonCalled(voice.root, 'Upload a clip').click();

    const hint = voice.root.querySelector('.creator-ways .creator-hint')?.textContent;
    expect(hint).toContain(fix);
    expect(hint).toContain('The library works anywhere.');
  });
});
