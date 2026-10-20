import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Position } from '../net';
import { bubbleAlpha, distanceAlpha, fadeAlpha, SpeechBubbles, speakingSeconds } from './bubbles';
import { loadStreets } from './street.fixture';
import {
  BUBBLE_FADE_SECONDS,
  EARSHOT_TILES,
  FAINTEST_ALPHA,
  FULL_ALPHA_TILES,
  MIN_BUBBLE_SECONDS,
  SECONDS_PER_WORD,
  THINKING_SECONDS,
} from './tuning';
import { distanceFromPlayer, PLAYER_ID, type WorldView } from './world-view';

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
    const alphas = [2.2, 2.5, 3, 3.5, 4].map(distanceAlpha);
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

it('keeps the player’s partner opaque however far away they are', () => {
  const bubbles = new SpeechBubbles();
  bubbles.show('mei', 'Over here!', 2, true, 0);
  bubbles.think('tom', 0);

  const alphas = bubbles.current(0).map((bubble) => bubbleAlpha(bubble, EARSHOT_TILES + 2, 0));
  expect(alphas).toEqual([1, 1]);
});

it('estimates how long the player takes to say something', () => {
  expect(speakingSeconds("  Hi Mei, how's your morning going? ")).toBeCloseTo(6 * SECONDS_PER_WORD);
});

describe('on a side-view map', () => {
  let unload: () => void;
  beforeEach(() => (unload = loadStreets()));
  afterEach(() => unload());

  const lane = (x: number, y = 15): Position => ({ x, y, map: 'lychee_lane' });

  function viewOf(positions: Record<string, Position>): WorldView {
    return {
      positionOf: (id) => positions[id],
      npcIds: () => Object.keys(positions).filter((id) => id !== PLAYER_ID),
      bubbleAnchor: () => ({ x: 0, y: 0 }),
      spriteOf: () => undefined,
    };
  }

  it('fades a speaker by how far along the street they are, however high they stand', () => {
    const view = viewOf({ [PLAYER_ID]: lane(43), mei: lane(48, 12), tom: lane(49, 12) });

    expect(distanceAlpha(distanceFromPlayer(view, 'mei')!)).toBeCloseTo(FAINTEST_ALPHA);
    expect(distanceAlpha(distanceFromPlayer(view, 'tom')!)).toBe(0);
  });

  it('shows a speaker on the ladder straight above the player in full', () => {
    const view = viewOf({ [PLAYER_ID]: lane(45), mei: lane(45, 12) });

    expect(distanceAlpha(distanceFromPlayer(view, 'mei')!)).toBe(1);
  });

  it('shows nobody inside a building to the player outside it, or on another floor', () => {
    const view = viewOf({
      [PLAYER_ID]: { x: 30, y: 15, map: 'high_street' },
      mei: { x: 5, y: 2, map: 'coffee_shop_floor_0' },
    });
    const upstairs = viewOf({
      [PLAYER_ID]: { x: 5, y: 2, map: 'coffee_shop_floor_1' },
      mei: { x: 5, y: 2, map: 'coffee_shop_floor_0' },
    });

    expect(distanceFromPlayer(view, 'mei')).toBeUndefined();
    expect(distanceFromPlayer(upstairs, 'mei')).toBeUndefined();
  });
});
