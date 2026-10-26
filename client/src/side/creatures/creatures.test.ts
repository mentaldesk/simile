import { describe, expect, it } from 'vitest';
import { server, type Creature, type CreatureState } from '../../net';
import { Creatures, DOWN_SECONDS, sideCreatures, Tracked } from './creatures';
import { creatureFigures, frameOf, goingDown, placedOf, poseOf } from './figures';

const rat: Creature = {
  id: 'rat_1',
  kind: 'rat',
  position: { x: 30, y: 15, map: 'sewers' },
  facing: 'east',
  state: 'idle',
};

const at = (creature: Creature, x: number, y = creature.position.y, more: Partial<Creature> = {}): Creature => ({
  ...creature,
  position: { ...creature.position, x, y },
  ...more,
});

function run(target: Creatures | Tracked, seconds: number, step = 1 / 60): void {
  for (let t = 0; t < seconds - 1e-9; t += step) target.update(step);
}

describe('the creatures', () => {
  it('adds one from a delta message, and draws it at its figure’s anchor', () => {
    server.dispatch(JSON.stringify({ type: 'creature_moved', creature: rat }));

    const tracked = sideCreatures.all.get('rat_1')!;
    expect(tracked.at).toEqual({ x: 30, y: 15 });
    const figure = creatureFigures.rat!;
    const frame = frameOf(figure, tracked);
    expect(frame).toBe('stand');
    const [, , w, h] = figure.frames.stand.frame;
    const [ax, ay] = figure.frames.stand.anchor;
    expect(placedOf(figure, frame, 'east')).toEqual({ originX: ax / w, originY: ay / h, flip: false });
    server.dispatch(JSON.stringify({ type: 'creature_gone', creature_id: 'rat_1' }));
    run(sideCreatures, DOWN_SECONDS);
    expect(sideCreatures.all.has('rat_1')).toBe(false);
  });

  it('tweens to each position over the time since the last, and snaps to a jump', () => {
    const all = new Creatures();
    all.move(rat);
    run(all, 1);
    all.move(at(rat, 30.4, 15, { state: 'moving' }));
    const tracked = all.all.get('rat_1')!;
    run(all, 0.1);
    expect(tracked.at.x).toBeCloseTo(30.2);
    run(all, 0.1);
    expect(tracked.at.x).toBeCloseTo(30.4);
    expect(tracked.travelled).toBeCloseTo(0.4 * 1.1);

    all.move(at(rat, 30.6, 15, { state: 'moving' }));
    run(all, 0.1);
    expect(tracked.at.x).toBeCloseTo(30.5);

    all.move(at(rat, 40));
    expect(tracked.at.x).toBe(40);
    all.move({ ...rat, position: { x: 41, y: 15, map: 'metro' } });
    expect(tracked.at.x).toBe(41);
  });

  it('tweens a fall and a fast dog’s strides rather than snapping them', () => {
    const all = new Creatures();
    const dog: Creature = { ...rat, id: 'dog_1', kind: 'dog', state: 'chasing' };
    all.move(dog);
    const tracked = all.all.get('dog_1')!;
    for (const x of [32.6, 35.2, 37.8]) {
      all.move(at(dog, x));
      run(all, 0.1);
      expect(tracked.at.x).toBeCloseTo(x - 1.3);
      run(all, 0.1);
    }
    all.move(at(dog, 37.8, 16.6));
    run(all, 0.1);
    expect(tracked.at.y).toBeCloseTo(15.8);
  });

  it('keeps the rest of a snapshot, drops what it leaves out, and replaces one that came back', () => {
    const all = new Creatures();
    all.reset([rat, { ...rat, id: 'rat_2' }]);
    all.reset([at(rat, 31)]);
    expect([...all.all.keys()]).toEqual(['rat_1']);

    all.gone('rat_1');
    run(all, DOWN_SECONDS / 2);
    all.move(at(rat, 30));
    expect(all.all.get('rat_1')!.down).toBeUndefined();
    expect(all.all.get('rat_1')!.at.x).toBe(30);
  });
});

describe('their figures', () => {
  const kinds = ['rat', 'bot', 'dog', 'bat'] as const;

  it('play each state’s pose by the protocol’s table', () => {
    const poses = (state: CreatureState) => kinds.map((kind) => poseOf(creatureFigures[kind]!, state));
    expect(poses('idle')).toEqual(['stand', 'stand', 'stand', 'fly']);
    expect(poses('moving')).toEqual(['walk', 'walk', 'run', 'fly']);
    expect(poses('chasing')).toEqual(poses('moving'));
    expect(poses('fleeing')).toEqual(poses('moving'));
    expect(poses('attacking')).toEqual(['attack', 'attack', 'attack', 'attack']);
    expect(poses('hurt')).toEqual(poses('idle'));
    expect(poseOf(creatureFigures.bat!, 'roosting')).toBe('roost');
    expect(creatureFigures.bat!.frames.roost.hangs).toBe(true);
  });

  it('step a walk with the distance covered and a flight with time', () => {
    const dog = new Tracked({ ...rat, kind: 'dog', state: 'chasing' });
    const figure = creatureFigures.dog!;
    const seen = new Set<string>();
    for (let i = 0; i < 20; i++) {
      dog.travelled = i * 0.2;
      seen.add(frameOf(figure, dog));
    }
    expect(seen).toEqual(new Set(['run', 'run_pass']));
    dog.travelled = 0;
    expect(frameOf(figure, dog)).toBe('run');

    const bat = new Tracked({ ...rat, kind: 'bat', state: 'idle' });
    const flown = new Set<string>();
    for (let i = 0; i < 20; i++) {
      run(bat, 0.05);
      flown.add(frameOf(creatureFigures.bat!, bat));
    }
    expect(flown).toEqual(new Set(['up', 'glide', 'down']));
  });

  it('mirror about the anchor to face west', () => {
    const figure = creatureFigures.dog!;
    const [, , w] = figure.frames.run.frame;
    const [ax] = figure.frames.run.anchor;
    const west = placedOf(figure, 'run', 'west');
    expect(west.flip).toBe(true);
    expect(west.originX).toBeCloseTo((w - ax) / w);
  });

  it('keel over away from the way they face and fade as they go down, a bat dropping', () => {
    const rat = creatureFigures.rat!;
    expect(goingDown(rat, 'east', 0)).toEqual({ angle: -0, alpha: 1, drop: 0 });
    const gone = goingDown(rat, 'east', DOWN_SECONDS);
    expect(gone.angle).toBe(-90);
    expect(gone.alpha).toBe(0);
    expect(goingDown(rat, 'west', DOWN_SECONDS).angle).toBe(90);
    expect(goingDown(creatureFigures.bat!, 'east', DOWN_SECONDS).drop).toBeGreaterThan(gone.drop);
  });
});
