import {
  BUBBLE_FADE_SECONDS,
  EARSHOT_TILES,
  FAINTEST_ALPHA,
  FULL_ALPHA_TILES,
  MIN_BUBBLE_SECONDS,
  SECONDS_PER_WORD,
} from './tuning';

export type Bubble = { speaker: string; text: string; shownAt: number; seconds: number };

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
  return fadeAlpha(bubble, now) * distanceAlpha(distance);
}

export class SpeechBubbles {
  private readonly bySpeaker = new Map<string, Bubble>();

  show(speaker: string, text: string, duration: number, now = Date.now()): void {
    const seconds = Math.max(duration, MIN_BUBBLE_SECONDS);
    this.bySpeaker.set(speaker, { speaker, text, shownAt: now, seconds });
  }

  current(now = Date.now()): Bubble[] {
    for (const [speaker, bubble] of this.bySpeaker) {
      if (fadeAlpha(bubble, now) === 0) this.bySpeaker.delete(speaker);
    }
    return [...this.bySpeaker.values()];
  }
}
