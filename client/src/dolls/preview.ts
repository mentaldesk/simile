// A dev page drawing the dolls with the real rig: /src/dolls/preview.html?show=lineup|poses|walk|run|climb|flat
import Phaser from 'phaser';
import type { Facing } from '../net/protocol';
import { dolls, flatDoll } from './assets';
import type { DollManifest } from './manifest';
import { addAtlas, PaperDoll } from './paper-doll';
import type { DollPose, PoseOptions } from './rig';

type Cell = {
  id: string;
  pose: DollPose;
  facing: Facing;
  phase?: number;
  options?: PoseOptions;
  /** Cycles a second, or turning from a walk to a run and back with `shift`. */
  pace?: number | 'shift';
};

/** The side scene's cadence: `PLAYER_SPEED` over `WALK_CYCLE_M`, and twice that over `RUN_CYCLE_M`. */
const WALK_HZ = 1.8;
const RUN_HZ = 2.4;
/** Walking, then Shift held, then let go, as the side scene blends. */
const SHIFT_MS = { walk: 1500, blend: 250, run: 1500 };

const params = new URLSearchParams(location.search);
const show = params.get('show') ?? 'lineup';
const named = params.get('who')?.split(',');
const who = named?.[0] ?? 'player';
const height = Number(params.get('height') ?? 245);
const flat = params.has('flat');
const fixed = params.has('phase') ? Number(params.get('phase')) : undefined;
const frames = Number(params.get('frames') ?? 8);
const cellWidth = height * 0.62;
const cellHeight = height * 1.35;
const FACINGS: Facing[] = ['east', 'south', 'north', 'west'];
const POSES: DollPose[] = [
  'standing',
  'walking',
  'sitting',
  'reading',
  'working',
  'looking',
  'climbing',
  'riding',
  'jumping',
];

function cells(ids: string[]): Cell[][] {
  const ladder = { on: 'ladder' } as const;
  const stairs = { on: 'stairs' } as const;
  const phases = Array.from({ length: frames }, (_, i) => i / frames);
  switch (show) {
    case 'poses':
      return POSES.map((pose) => FACINGS.map((facing) => ({ id: who, pose, facing })));
    case 'walk':
      return ids.map((id) =>
        phases.map((phase) => ({ id, pose: 'walking', facing: 'east', phase })),
      );
    case 'run':
      return ids.map((id) => [
        { id, pose: 'walking', facing: 'east', pace: WALK_HZ },
        { id, pose: 'walking', facing: 'east', pace: RUN_HZ, options: { run: 1 } },
        { id, pose: 'walking', facing: 'south', pace: RUN_HZ, options: { run: 1 } },
        { id, pose: 'walking', facing: 'north', pace: RUN_HZ, options: { run: 1 } },
        { id, pose: 'walking', facing: 'east', pace: 'shift' },
      ]);
    case 'climb':
      return [
        phases.map((phase) => ({
          id: who,
          pose: 'climbing',
          facing: 'north',
          phase,
          options: ladder,
        })),
        phases.map((phase) => ({
          id: who,
          pose: 'climbing',
          facing: 'east',
          phase,
          options: stairs,
        })),
      ];
    case 'views':
      return (params.get('facings')?.split(',') ?? ['east', 'south', 'north']).map((facing) =>
        ids.map((id) => ({
          id,
          pose: (params.get('pose') ?? 'standing') as DollPose,
          facing: facing as Facing,
        })),
      );
    case 'flat':
      return [
        (['east', 'south', 'north'] as Facing[]).map((facing) => ({
          id: 'flat',
          pose: 'standing',
          facing,
        })),
        (['walking', 'sitting', 'reading'] as DollPose[]).map((pose) => ({
          id: 'flat',
          pose,
          facing: 'east',
          phase: 0.3,
        })),
      ];
    default: {
      const rows: Cell[][] = [];
      for (let i = 0; i < ids.length; i += 4) {
        rows.push(
          ids.slice(i, i + 4).flatMap((id) =>
            (['east', 'south', 'north'] as Facing[]).map((facing) => ({
              id,
              pose: 'standing' as DollPose,
              facing,
            })),
          ),
        );
      }
      return rows;
    }
  }
}

async function chosen(): Promise<Record<string, DollManifest>> {
  if (show !== 'flat') return dolls;
  const appearance = JSON.parse(atob(params.get('appearance') ?? ''));
  return {
    flat: await flatDoll(appearance, params.get('character') ?? undefined),
  };
}

/** How far a walk has turned into a run `ms` into a cycle of walking, holding Shift and letting go. */
function shifted(ms: number): number {
  const { walk, blend, run } = SHIFT_MS;
  const t = ms % (2 * (walk + blend) + run);
  if (t < walk) return 0;
  if (t < walk + blend) return (t - walk) / blend;
  if (t < walk + blend + run) return 1;
  return Math.max(0, 1 - (t - walk - blend - run) / blend);
}

class Preview extends Phaser.Scene {
  private readonly posed: [PaperDoll, Cell, { phase: number }][] = [];
  private readonly found: Record<string, DollManifest>;
  private readonly rows: Cell[][];

  constructor(found: Record<string, DollManifest>, rows: Cell[][]) {
    super('preview');
    this.found = found;
    this.rows = rows;
  }

  async create(): Promise<void> {
    const ids = [...new Set(this.rows.flat().map((cell) => cell.id))];
    await Promise.all(
      ids.flatMap((id) => {
        const doll = this.found[id];
        const loads = [addAtlas(this, `${id}-flat`, doll.flat, doll)];
        if (doll.painted && !flat) loads.push(addAtlas(this, `${id}-painted`, doll.painted, doll));
        return loads;
      }),
    );
    const ground = this.add.graphics().lineStyle(1, 0xc9bca4);
    this.rows.forEach((row, r) => {
      const y = (r + 1) * cellHeight - height * 0.12;
      ground.lineBetween(0, y, row.length * cellWidth, y);
      row.forEach((cell, c) => {
        const doll = this.found[cell.id];
        const key = doll.painted && !flat ? `${cell.id}-painted` : `${cell.id}-flat`;
        const paper = new PaperDoll(this, (c + 0.5) * cellWidth, y, doll, key, height);
        this.add.existing(paper);
        paper.setPose(cell.pose, cell.facing, cell.phase ?? fixed ?? 0, cell.options);
        this.posed.push([paper, cell, { phase: 0 }]);
      });
    });
    (window as unknown as { dollsReady: boolean }).dollsReady = true;
  }

  update(time: number, delta: number): void {
    if (fixed !== undefined) return;
    for (const [paper, cell, at] of this.posed) {
      if (cell.phase !== undefined) continue;
      if (cell.pace === undefined) {
        paper.setPose(cell.pose, cell.facing, time / 1000, cell.options);
        continue;
      }
      const run = cell.pace === 'shift' ? shifted(time) : (cell.options?.run ?? 0);
      const hz = cell.pace === 'shift' ? WALK_HZ + (RUN_HZ - WALK_HZ) * run : cell.pace;
      at.phase += (hz * delta) / 1000;
      paper.setPose(cell.pose, cell.facing, at.phase, { ...cell.options, run });
    }
  }
}

chosen().then((found) => {
  const rows = cells(named ?? Object.keys(found).sort());
  new Phaser.Game({
    type: Phaser.WEBGL,
    parent: 'game',
    width: Math.max(...rows.map((row) => row.length)) * cellWidth,
    height: rows.length * cellHeight,
    backgroundColor: '#efe8da',
    antialias: true,
    scene: new Preview(found, rows),
  });
});
