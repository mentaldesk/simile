import {
  BUBBLE_FADE_SECONDS,
  EARSHOT_TILES,
  FAINTEST_ALPHA,
  FULL_ALPHA_TILES,
  MIN_BUBBLE_SECONDS,
  SECONDS_PER_WORD,
  THINKING_SECONDS,
} from './tuning';

export type Bubble = {
  speaker: string;
  text: string;
  shownAt: number;
  seconds: number;
  thinking?: boolean;
  partner?: boolean;
  /** The infrared eye saw the speaker flush: the line is a lie. */
  flushed?: boolean;
};

export function speakingSeconds(text: string): number {
  return text.split(/\s+/).filter(Boolean).length * SECONDS_PER_WORD;
}

export function fadeAlpha(bubble: Bubble, now: number): number {
  const sinceEnd = (now - bubble.shownAt) / 1000 - bubble.seconds;
  return Math.min(1, Math.max(0, 1 - sinceEnd / BUBBLE_FADE_SECONDS));
}

export function distanceAlpha(distance: number): number {
  if (distance > EARSHOT_TILES) return 0;
  if (distance <= FULL_ALPHA_TILES) return 1;
  const far = (distance - FULL_ALPHA_TILES) / (EARSHOT_TILES - FULL_ALPHA_TILES);
  return 1 - far * (1 - FAINTEST_ALPHA);
}

export function bubbleAlpha(bubble: Bubble, distance: number, now: number): number {
  return fadeAlpha(bubble, now) * (bubble.partner ? 1 : distanceAlpha(distance));
}

export class SpeechBubbles {
  private readonly bySpeaker = new Map<string, Bubble>();

  show(speaker: string, text: string, duration: number, partner = false, now = Date.now(), flushed = false): void {
    const seconds = Math.max(duration, MIN_BUBBLE_SECONDS);
    this.bySpeaker.set(speaker, { speaker, text, shownAt: now, seconds, partner, flushed });
  }

  think(speaker: string, now = Date.now()): void {
    const seconds = THINKING_SECONDS;
    const bubble = { speaker, text: '…', shownAt: now, seconds, thinking: true, partner: true };
    this.bySpeaker.set(speaker, bubble);
  }

  stopThinking(speaker: string): void {
    if (this.bySpeaker.get(speaker)?.thinking) this.bySpeaker.delete(speaker);
  }

  current(now = Date.now()): Bubble[] {
    for (const [speaker, bubble] of this.bySpeaker) {
      if (fadeAlpha(bubble, now) === 0) this.bySpeaker.delete(speaker);
    }
    return [...this.bySpeaker.values()];
  }
}
