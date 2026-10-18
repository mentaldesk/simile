import { ApiError, type Capabilities, type CreatorApi, type Kind, type LibraryVoice } from './api';
import type { Character, CharacterVoice } from './character';
import { button, h, labelled, message, select, textArea } from './dom';
import type { Draft } from './draft';
import { type Job, JobWatch, describe, finished } from './jobs';
import { MicRecorder, UPLOAD_TYPES, uploadProblem } from './wav';

export type VoiceContext = {
  api: CreatorApi;
  capabilities: Capabilities | null;
  draft: Draft;
  readOnly: boolean;
  edit: (voice: CharacterVoice) => void;
  ensureSaved: () => Promise<boolean>;
  picked: (character: Character, description?: string) => Promise<void>;
};

type Way = 'design' | 'upload' | 'record' | 'library';

type Candidate = {
  n: number;
  clip: string;
  clone: string;
  accent: string;
  clone_accent: string;
  heard: string;
  problems: string[];
  warnings: string[];
};
type Designed = { description: string; reference_line: string; candidates: Candidate[] };
type Checked = {
  heard: string | null;
  accent: string | null;
  seconds: number | null;
  errors: string[];
  problems: string[];
  warnings: string[];
  reference_line: string;
  clip: string | null;
  samples: string[];
  usable: boolean;
};

const MIN_WORDS = 12;
const MAX_WORDS = 25;
const TRY_LENGTH = 300;
const SET_UP = 'with voice-lab set up as voice-lab/README.md says';

const wordCount = (line: string) => line.split(/\s+/).filter(Boolean).length;

/** `import_voices.py`'s limits on a clip's transcript, which becomes the reference line. */
export function transcriptProblem(line: string): string | null {
  const words = wordCount(line);
  if (!words) return 'Write exactly what the clip says first.';
  if (words < MIN_WORDS || words > MAX_WORDS)
    return `What the clip says becomes their line, so it has to be ${MIN_WORDS} to ${MAX_WORDS} words, not ${words}.`;
  if (line.includes('!'))
    return 'What the clip says becomes their line, which stays calm, so it can’t have a “!”.';
  return null;
}

class Take {
  clip: { blob: Blob; url: string; name: string } | null = null;
  check: { job: Job; watch: JobWatch } | null = null;
  checked: Checked | null = null;

  keep(blob: Blob, name: string): void {
    this.dispose();
    this.clip = { blob, url: URL.createObjectURL(blob), name };
  }

  get checking(): boolean {
    return !!this.check && !finished(this.check.job);
  }

  dispose(): void {
    this.check?.watch.stop();
    if (this.clip) URL.revokeObjectURL(this.clip.url);
    this.clip = null;
    this.check = null;
    this.checked = null;
  }
}

export class VoiceStep {
  readonly root = h('div', { className: 'creator-voice' });
  private readonly ways = h('div', { className: 'creator-ways' });
  private readonly tryBox = h('div', { className: 'creator-try' });
  private way: Way = 'design';
  private busy = false;
  private note = '';
  private design: { job: Job; watch: JobWatch } | null = null;
  private designed: Designed | null = null;
  private recorder: MicRecorder | null = null;
  private readonly recorded = new Take();
  private readonly uploaded = new Take();
  private transcript: string | null = null;
  private voices: LibraryVoice[] | null = null;
  private gender = '';
  private tryUnavailable: string | null = null;
  /** What the saved clip says, which saving a new line doesn't change. */
  private clipLine: string | null;
  private readonly ctx: VoiceContext;

  constructor(ctx: VoiceContext) {
    this.ctx = ctx;
    this.gender = ctx.draft.work.gender ?? '';
    if (ctx.draft.work.voice?.needs_recording) this.way = 'upload';
    const saved = ctx.draft.saved?.voice;
    this.clipLine = saved?.reference_clip ? saved.reference_line : null;
  }

  render(): void {
    const voice = this.ctx.draft.work.voice;
    const disabled = this.ctx.readOnly;
    if (!voice) {
      this.root.replaceChildren(
        h(
          'p',
          { className: 'creator-hint' },
          'Written with the character. Anything you write here is kept.',
        ),
        this.fields(blankVoice(), disabled),
      );
      return;
    }
    this.root.replaceChildren(
      this.fields(voice, disabled),
      this.current(),
      this.ctx.readOnly ? '' : this.ways,
      this.tryBox,
    );
    this.drawWays();
    this.drawTry();
  }

  dispose(): void {
    this.design?.watch.stop();
    this.recorder?.stop();
    this.recorded.dispose();
    this.uploaded.dispose();
  }

  private fields(voice: CharacterVoice, disabled: boolean): HTMLElement {
    const count = h('small', {});
    const counted = (line: string) => {
      const words = wordCount(line);
      const problem = line.includes('!') ? ', and no “!”' : '';
      const needs = `${MIN_WORDS} to ${MAX_WORDS} words${problem}, said calmly`;
      count.textContent = words
        ? `${words} words. A clip needs ${needs}.`
        : `What the clip says: ${needs}.`;
      count.classList.toggle(
        'creator-warn',
        !!words && (words < MIN_WORDS || words > MAX_WORDS || !!problem),
      );
    };
    counted(voice.reference_line);
    const edit = (patch: Partial<CharacterVoice>) =>
      this.ctx.edit({ ...(this.ctx.draft.work.voice ?? blankVoice()), ...patch });
    return h(
      'div',
      { className: 'creator-grid' },
      labelled(
        'What it sounds like',
        textArea(voice.description, (description) => edit({ description }), { rows: 3, disabled }),
        'Accent first, then age, pitch, pace and manner, for the voice designer.',
      ),
      labelled(
        'Their line',
        textArea(
          voice.reference_line,
          (reference_line) => {
            counted(reference_line);
            edit({ reference_line });
          },
          { rows: 2, disabled },
        ),
        count,
      ),
      voice.needs_recording
        ? h(
            'p',
            { className: 'creator-hint creator-wide' },
            'The voice designer can’t do this accent, so upload or record a clip of it, or pick a voice from the library.',
          )
        : null,
    );
  }

  private current(): HTMLElement {
    const saved = this.ctx.draft.saved;
    const line = this.ctx.draft.work.voice?.reference_line;
    if (!saved?.voice.reference_clip) return h('p', { className: 'creator-hint' }, 'No voice yet.');
    const mismatch = this.clipLine !== null && line !== this.clipLine;
    return h(
      'p',
      { className: mismatch ? 'creator-hint creator-warn' : 'creator-hint' },
      mismatch
        ? `The voice clip says “${this.clipLine}”. Their line has changed, so give them a voice again.`
        : 'They have a voice. Try it below.',
    );
  }

  private drawWays(): void {
    const kinds = this.ctx.capabilities?.kinds ?? {};
    const tab = (way: Way, label: string) =>
      button(
        label,
        () => {
          this.way = way;
          this.drawWays();
        },
        { 'aria-pressed': String(this.way === way) },
      );
    const panels: Record<Way, () => HTMLElement> = {
      design: () => this.designPanel(kinds.voice_design),
      upload: () => this.uploadPanel(kinds.voice_check),
      record: () => this.recordPanel(kinds.voice_check),
      library: () => this.libraryPanel(),
    };
    this.ways.replaceChildren(
      h(
        'div',
        { className: 'creator-tabs', role: 'group' },
        tab('design', 'Design'),
        tab('upload', 'Upload a clip'),
        tab('record', 'Record'),
        tab('library', 'Library'),
      ),
      panels[this.way](),
      this.note ? h('p', { className: 'creator-note' }, this.note) : '',
    );
  }

  private unavailable(kind: Kind | undefined, what: string): HTMLElement | null {
    if (kind?.available) return null;
    return h(
      'p',
      { className: 'creator-hint' },
      `${unavailableNote(what, kind, this.ctx.capabilities)} The library works anywhere.`,
    );
  }

  private designPanel(kind: Kind | undefined): HTMLElement {
    const missing = this.unavailable(kind, 'Designing a voice');
    if (missing) return missing;
    const running =
      this.design && !['succeeded', 'failed', 'cancelled'].includes(this.design.job.state);
    const start = button(
      this.designed ? 'Design again' : 'Design voices',
      () => void this.startDesign(),
      { disabled: this.busy || running, className: 'creator-primary' },
    );
    const parts: (HTMLElement | string)[] = [
      h(
        'p',
        { className: 'creator-hint' },
        'Makes four voices from the description saying their line, then the game’s clone of each. Edit the description and design again until one fits.',
      ),
      h(
        'div',
        { className: 'creator-actions' },
        start,
        running ? button('Cancel', () => void this.ctx.api.cancel(this.design!.job.id)) : '',
      ),
    ];
    if (this.design) parts.push(jobLine(this.design.job));
    if (this.designed) {
      parts.push(
        h(
          'ol',
          { className: 'creator-candidates' },
          this.designed.candidates.map((c) =>
            h(
              'li',
              {},
              h('b', {}, `Voice ${c.n}`),
              h(
                'div',
                { className: 'creator-clips' },
                clip('Designed', c.clip),
                clip('In the game', c.clone),
              ),
              h('small', {}, `Heard as ${c.accent}; cloned, ${c.clone_accent}`),
              [...c.problems, ...c.warnings].length
                ? h(
                    'small',
                    { className: 'creator-warn' },
                    [...c.problems, ...c.warnings].join('; '),
                  )
                : '',
              button(
                'Use this voice',
                () =>
                  void this.pick(
                    { design: this.design!.job.id, candidate: c.n },
                    this.designed!.description,
                  ),
                { disabled: this.busy },
              ),
            ),
          ),
        ),
      );
    }
    return h('div', {}, parts);
  }

  private async startDesign(): Promise<void> {
    const voice = this.ctx.draft.work.voice;
    if (!voice?.description.trim() || !voice.reference_line.trim()) {
      this.say('Write what the voice sounds like and their line first.');
      return;
    }
    this.design?.watch.stop();
    this.designed = null;
    this.say('');
    try {
      const job = await this.ctx.api.submit('voice_design', {
        description: voice.description,
        reference_line: voice.reference_line,
      });
      const watch = this.follow(job, (current) => {
        if (this.design) this.design.job = current;
      });
      this.design = { job, watch };
      this.drawWays();
      const done = await watch.done;
      if (done.state === 'succeeded') this.designed = done.result as Designed;
    } catch (error) {
      this.say(`Couldn’t design voices: ${message(error)}`);
    }
    this.drawWays();
  }

  private uploadPanel(kind: Kind | undefined): HTMLElement {
    const missing = this.unavailable(kind, 'Checking a clip');
    if (missing) return missing;
    const take = this.uploaded;
    const said = () => this.transcript ?? this.ctx.draft.work.voice?.reference_line ?? '';
    const chooser = h('input', {
      type: 'file',
      accept: UPLOAD_TYPES.join(','),
      hidden: true,
      onchange: (event) => this.chooseFile(event.target as HTMLInputElement),
    });
    const count = h('small', {});
    const counted = (line: string) => {
      const problem = transcriptProblem(line);
      count.textContent = problem ?? `${wordCount(line)} words.`;
      count.classList.toggle('creator-warn', !!problem);
    };
    counted(said());
    const transcript = labelled(
      'What the clip says',
      textArea(
        said(),
        (line) => {
          this.transcript = line;
          counted(line);
          this.say('');
          this.ways.querySelector('.creator-note')?.remove();
        },
        { rows: 2 },
      ),
      count,
    );
    transcript.classList.add('creator-transcript');
    const parts: (HTMLElement | string)[] = [
      h(
        'p',
        { className: 'creator-hint' },
        'A clip of the voice you want, made anywhere: a WAV, MP3 or M4A file with 5 to 25 seconds of calm speech. Write exactly what it says below. It’s checked against the clip before you can use it, and becomes their line when you do.',
      ),
      h(
        'div',
        { className: 'creator-actions' },
        button(take.clip ? 'Choose another clip…' : 'Choose a clip…', () => chooser.click(), {
          disabled: this.busy || take.checking,
        }),
        chooser,
        take.clip ? h('small', {}, take.clip.name) : '',
      ),
      transcript,
    ];
    if (take.clip) {
      parts.push(
        h(
          'div',
          { className: 'creator-actions' },
          h('audio', { controls: true, src: take.clip.url }),
          button('Check it', () => void this.startCheck(take, said()), {
            disabled: this.busy || take.checking,
            className: 'creator-primary',
          }),
        ),
      );
    }
    parts.push(...this.checkParts(take));
    return h('div', {}, parts);
  }

  private recordPanel(kind: Kind | undefined): HTMLElement {
    const missing = this.unavailable(kind, 'Checking a recording');
    if (missing) return missing;
    const take = this.recorded;
    const line = this.ctx.draft.work.voice?.reference_line ?? '';
    const parts: (HTMLElement | string)[] = [
      h(
        'p',
        { className: 'creator-hint' },
        'Read their line in the voice you want, calmly, in 5 to 25 seconds. It’s checked for what it says and how long it is before you can use it.',
      ),
      h('blockquote', {}, `“${line}”`),
    ];
    if (this.recorder) {
      const timer = h('span', { className: 'creator-timer' }, '0.0 s');
      const meter = h('meter', { min: 0, max: 0.3, value: 0 });
      this.recorder.onTick = () => {
        timer.textContent = `${this.recorder?.seconds.toFixed(1) ?? 0} s`;
        meter.value = this.recorder?.level ?? 0;
      };
      this.recorder.onLimit = () => this.stopRecording();
      parts.push(
        h(
          'div',
          { className: 'creator-actions' },
          button('Stop', () => this.stopRecording(), { className: 'creator-primary' }),
          timer,
          meter,
        ),
      );
    } else {
      parts.push(
        h(
          'div',
          { className: 'creator-actions' },
          button('Record', () => void this.startRecording(), {
            disabled: this.busy || take.checking,
          }),
        ),
      );
    }
    if (take.clip && !this.recorder) {
      parts.push(
        h(
          'div',
          { className: 'creator-actions' },
          h('audio', { controls: true, src: take.clip.url }),
          button('Check it', () => void this.startCheck(take, line), {
            disabled: this.busy || take.checking,
            className: 'creator-primary',
          }),
        ),
        h('small', {}, take.clip.name),
      );
    }
    parts.push(...this.checkParts(take));
    return h('div', {}, parts);
  }

  private checkParts(take: Take): HTMLElement[] {
    if (!take.check) return [];
    const job = take.check.job;
    return [jobLine(job), ...(take.checked ? [this.checkResult(job.id, take.checked)] : [])];
  }

  private checkResult(job: string, result: Checked): HTMLElement {
    const issues = [...result.errors, ...result.problems];
    const line = this.ctx.draft.work.voice?.reference_line;
    return h(
      'div',
      { className: 'creator-check' },
      h('p', {}, result.usable ? 'It passed its checks.' : 'It didn’t pass its checks.'),
      result.heard
        ? h('small', {}, `Heard: “${result.heard}”${result.accent ? `, as ${result.accent}` : ''}`)
        : '',
      issues.length ? h('small', { className: 'creator-warn' }, issues.join('; ')) : '',
      result.warnings.length ? h('small', {}, result.warnings.join('; ')) : '',
      result.samples.length
        ? h(
            'div',
            { className: 'creator-clips' },
            h('small', {}, 'The game’s clone of it, saying other lines:'),
            result.samples.map((src) => clip('', src)),
          )
        : '',
      result.usable && result.reference_line !== line
        ? h('small', {}, `Using it makes “${result.reference_line}” their line.`)
        : '',
      result.usable
        ? button('Use this voice', () => void this.pick({ recording: job }), {
            disabled: this.busy,
            className: 'creator-primary',
          })
        : '',
    );
  }

  private async startRecording(): Promise<void> {
    this.say('');
    try {
      this.recorder = await MicRecorder.start();
    } catch (error) {
      this.say(`Couldn’t use the microphone: ${message(error)}`);
    }
    this.drawWays();
  }

  private stopRecording(): void {
    const recorder = this.recorder;
    if (!recorder) return;
    this.recorder = null;
    const wav = recorder.stop();
    this.recorded.keep(
      new Blob([wav], { type: 'audio/wav' }),
      `Recording, ${recorder.seconds.toFixed(1)} s`,
    );
    this.say('');
    this.drawWays();
  }

  private chooseFile(input: HTMLInputElement): void {
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    const problem = uploadProblem(file);
    if (problem) {
      this.say(problem);
    } else {
      this.uploaded.keep(file, file.name);
      this.say('');
    }
    this.drawWays();
  }

  private async startCheck(take: Take, transcript: string): Promise<void> {
    if (!take.clip) return;
    const problem = transcriptProblem(transcript);
    if (problem) {
      this.say(problem);
      this.drawWays();
      return;
    }
    this.busy = true;
    this.say('');
    this.drawWays();
    try {
      if (!(await this.ctx.ensureSaved())) return;
      const job = await this.ctx.api.record(this.ctx.draft.work.id!, take.clip.blob, transcript);
      const watch = this.follow(job, (current) => {
        if (take.check?.watch === watch) take.check.job = current;
      });
      take.check = { job, watch };
      take.checked = null;
      this.busy = false;
      this.drawWays();
      const done = await watch.done;
      if (take.check?.watch === watch && done.state === 'succeeded')
        take.checked = done.result as Checked;
    } catch (error) {
      this.say(`Couldn’t check the clip: ${message(error)}`);
    } finally {
      this.busy = false;
      this.drawWays();
    }
  }

  private libraryPanel(): HTMLElement {
    if (!this.voices) {
      void this.loadVoices();
      return h('p', { className: 'creator-hint' }, 'Loading the voice library…');
    }
    const shown = this.voices.filter((v) => !this.gender || v.gender === this.gender);
    const genders = [
      ['', 'Any'],
      ['woman', 'Women'],
      ['man', 'Men'],
      ['nonbinary', 'Nonbinary'],
    ] as const;
    return h(
      'div',
      {},
      h(
        'p',
        { className: 'creator-hint' },
        'The residents’ voices. Using one copies its clip, with the line it says.',
      ),
      labelled(
        'Show',
        select(this.gender, genders, (gender) => {
          this.gender = gender;
          this.drawWays();
        }),
      ),
      shown.length
        ? h(
            'ul',
            { className: 'creator-library-voices' },
            shown.map((v) =>
              h(
                'li',
                {},
                h('b', {}, `${v.accent}, ${v.age} ${v.gender}`),
                clip('', v.clip),
                h('small', {}, `“${v.reference_line}”`),
                button('Use this voice', () => void this.pick({ library: v.id }), {
                  disabled: this.busy,
                }),
              ),
            ),
          )
        : h('p', { className: 'creator-hint' }, 'No voices match.'),
    );
  }

  private async loadVoices(): Promise<void> {
    try {
      this.voices = await this.ctx.api.voices();
    } catch (error) {
      this.voices = [];
      this.say(`Couldn’t load the voice library: ${message(error)}`);
    }
    if (this.way === 'library') this.drawWays();
  }

  private async pick(
    choice: Parameters<CreatorApi['pick']>[1],
    description?: string,
  ): Promise<void> {
    this.busy = true;
    this.say('Saving the voice…');
    this.drawWays();
    try {
      if (!(await this.ctx.ensureSaved())) {
        this.say('');
        return;
      }
      const character = await this.ctx.api.pick(this.ctx.draft.work.id!, choice);
      this.clipLine = character.voice.reference_line;
      this.transcript = null;
      await this.ctx.picked(character, description);
      this.tryUnavailable = null;
      this.say('Voice saved.');
    } catch (error) {
      this.say(`Couldn’t use that voice: ${message(error)}`);
    } finally {
      this.busy = false;
      this.render();
    }
  }

  private drawTry(): void {
    const saved = this.ctx.draft.saved;
    if (!saved?.voice.reference_clip) {
      this.tryBox.replaceChildren();
      return;
    }
    if (this.tryUnavailable) {
      this.tryBox.replaceChildren(
        h('b', {}, 'Try it'),
        h('p', { className: 'creator-hint' }, this.tryUnavailable),
      );
      return;
    }
    const input = h('input', {
      type: 'text',
      maxLength: TRY_LENGTH,
      placeholder: 'Type a line for them to say',
      'aria-label': 'A line to say',
    });
    const status = h('small', {});
    const say = button('Say it', async () => {
      const line = input.value.trim() || saved.voice.reference_line;
      say.disabled = true;
      status.textContent = 'Speaking…';
      try {
        const audio = await this.ctx.api.say(saved.id, line);
        const url = URL.createObjectURL(audio);
        const player = new Audio(url);
        player.onended = () => URL.revokeObjectURL(url);
        await player.play();
        status.textContent = '';
      } catch (error) {
        if (error instanceof ApiError && error.status === 503) {
          this.tryUnavailable = `${error.message}.`;
          this.drawTry();
          return;
        }
        status.textContent = message(error);
      }
      say.disabled = false;
    });
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') say.click();
    });
    this.tryBox.replaceChildren(
      h('b', {}, 'Try it'),
      h('div', { className: 'creator-actions' }, input, say),
      status,
    );
  }

  private follow(job: Job, onChange: (job: Job) => void): JobWatch {
    const watch = new JobWatch(job, {
      connect: (id) => this.ctx.api.watch(id),
      poll: (id) => this.ctx.api.job(id),
    });
    watch.onChange = (current) => {
      onChange(current);
      this.drawWays();
    };
    return watch;
  }

  private say(note: string): void {
    this.note = note;
  }
}

function unavailableNote(
  what: string,
  kind: Kind | undefined,
  capabilities: Capabilities | null,
): string {
  const machine = capabilities?.machine;
  if (!machine)
    return `${what} isn’t available: the server didn’t say what it can run. Start the game with ./run.sh on a Mac with Apple Silicon, ${SET_UP}.`;
  if (!machine.apple_silicon)
    return `${what} needs a Mac with Apple Silicon. Start the game with ./run.sh on one, ${SET_UP}.`;
  if (!machine.voice_lab || !machine.voice_lab_mlx)
    return `${what} needs voice-lab’s two virtualenvs. Set them up as voice-lab/README.md says, then start the game again with ./run.sh.`;
  return `${what} isn’t available here: ${kind?.reason ?? 'this server doesn’t have it'}.`;
}

function blankVoice(): CharacterVoice {
  return { description: '', reference_line: '', reference_clip: null, needs_recording: false };
}

function clip(label: string, src: string): HTMLElement {
  return h(
    'div',
    { className: 'creator-clip' },
    label ? h('small', {}, label) : '',
    h('audio', { controls: true, preload: 'none', src }),
  );
}

function jobLine(job: Job): HTMLElement {
  const running = job.state === 'queued' || job.state === 'running';
  return h(
    'div',
    { className: job.state === 'failed' ? 'creator-job creator-warn' : 'creator-job' },
    running ? h('progress', { max: 1, value: job.progress }) : '',
    h('small', {}, describe(job)),
  );
}
