import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { bubbleAlpha, distanceAlpha, fadeAlpha, SpeechBubbles, speakingSeconds } from './bubbles';
import {
  BUBBLE_FADE_SECONDS,
  EARSHOT_TILES,
  FAINTEST_ALPHA,
  FULL_ALPHA_TILES,
  MIN_BUBBLE_SECONDS,
  SECONDS_PER_WORD,
  THINKING_SECONDS,
} from './tuning';

describe('SpeechBubbles', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('shows a line for its duration, then fades it out', () => {
    const bubbles = new SpeechBubbles();
    bubbles.show('mei', 'Morning, Viktor!', 4.4);

    vi.advanceTimersByTime(4400);
    const [bubble] = bubbles.current();
    expect(bubble).toMatchObject({ speaker: 'mei', text: 'Morning, Viktor!' });
    expect(fadeAlpha(bubble, Date.now())).toBe(1);

    vi.advanceTimersByTime((BUBBLE_FADE_SECONDS * 1000) / 2);
    expect(fadeAlpha(bubble, Date.now())).toBeCloseTo(0.5);

    vi.advanceTimersByTime((BUBBLE_FADE_SECONDS * 1000) / 2);
    expect(bubbles.current()).toEqual([]);
  });

  it('keeps short lines up long enough to read', () => {
    const bubbles = new SpeechBubbles();
    bubbles.show('viktor', 'Hm.', 0.4);

    vi.advanceTimersByTime(MIN_BUBBLE_SECONDS * 1000);
    expect(fadeAlpha(bubbles.current()[0], Date.now())).toBe(1);

    vi.advanceTimersByTime(BUBBLE_FADE_SECONDS * 1000);
    expect(bubbles.current()).toEqual([]);
  });

  it("replaces a speaker's bubble when they say something new, and restarts its time", () => {
    const bubbles = new SpeechBubbles();
    bubbles.show('mei', 'First', 3);
    bubbles.show('viktor', 'Reply', 3);
    vi.advanceTimersByTime(2500);
    bubbles.show('mei', 'Second', 3);

    vi.advanceTimersByTime(1000 + BUBBLE_FADE_SECONDS * 1000);
    expect(bubbles.current().map(({ speaker, text }) => [speaker, text])).toEqual([
      ['mei', 'Second'],
    ]);
  });
});

describe('thinking', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('shows an ellipsis until the speaker says something or stops', () => {
    const bubbles = new SpeechBubbles();
    bubbles.think('mei');
    expect(bubbles.current()).toMatchObject([{ speaker: 'mei', text: '…', thinking: true }]);

    vi.advanceTimersByTime(1000);
    bubbles.show('mei', 'Hello!', 2);
    bubbles.stopThinking('mei');
    expect(bubbles.current()).toMatchObject([{ speaker: 'mei', text: 'Hello!' }]);

    bubbles.think('mei');
    bubbles.stopThinking('mei');
    expect(bubbles.current()).toEqual([]);
  });

  it('gives up after a while', () => {
    const bubbles = new SpeechBubbles();
    bubbles.think('mei');

    vi.advanceTimersByTime((THINKING_SECONDS + BUBBLE_FADE_SECONDS) * 1000);
    expect(bubbles.current()).toEqual([]);
  });
});

describe('distanceAlpha', () => {
  it('is opaque up close and fades to the faintest at the edge of earshot', () => {
    expect(distanceAlpha(0)).toBe(1);
    expect(distanceAlpha(FULL_ALPHA_TILES)).toBe(1);
    expect(distanceAlpha((FULL_ALPHA_TILES + EARSHOT_TILES) / 2)).toBeCloseTo(
      (1 + FAINTEST_ALPHA) / 2,
    );
    expect(distanceAlpha(EARSHOT_TILES)).toBeCloseTo(FAINTEST_ALPHA);
  });

  it('fades the further away the speaker is', () => {
    const alphas = [3.5, 4, 5, 6, 7.5].map(distanceAlpha);
    expect(alphas).toEqual([...alphas].sort((a, b) => b - a));
    expect(new Set(alphas).size).toBe(alphas.length);
  });

  it('hides a speaker out of earshot', () => {
    expect(distanceAlpha(EARSHOT_TILES + 0.1)).toBe(0);
  });
});

it('combines fading with time and with distance', () => {
  const bubble = { speaker: 'mei', text: 'Hi', shownAt: 0, seconds: 2 };
  const halfFaded = 2000 + (BUBBLE_FADE_SECONDS * 1000) / 2;
  expect(bubbleAlpha(bubble, EARSHOT_TILES, halfFaded)).toBeCloseTo(FAINTEST_ALPHA / 2);
});

it('estimates how long the player takes to say something', () => {
  expect(speakingSeconds("  Hi Mei, how's your morning going? ")).toBeCloseTo(6 * SECONDS_PER_WORD);
});
