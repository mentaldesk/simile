import Phaser from 'phaser';
import { server, type ClientMessage, type Entity, type LineMessage, type Position } from '../net';
import { npcAt } from '../world/hit';
import { mapOf } from '../world/map';
import { speakingSeconds } from './bubbles';
import './harness.css';
import { sideView } from './side-view';
import { CHAT_RANGE_TILES } from './tuning';
import { PLAYER_ID, trackedWorld } from './world-view';

const MAP = 'high_street';
const onStreet = (x: number): Position => ({ x, y: 15, map: MAP });

const entities: Entity[] = [
  { id: PLAYER_ID, kind: 'player', name: 'Player', position: onStreet(51) },
  { id: 'mei', kind: 'npc', name: 'Mei Lin', position: onStreet(53) },
  { id: 'viktor', kind: 'npc', name: 'Viktor Hale', position: onStreet(49) },
  { id: 'suki', kind: 'npc', name: 'Suki Tan', position: onStreet(56) },
  { id: 'tom', kind: 'npc', name: 'Tom Reed', position: onStreet(62) },
];

const conversation = [
  ['mei', 'Morning, Viktor! Same as always, or are you feeling brave today?'],
  ['viktor', "Same as always. Bravery is for people who haven't had their coffee."],
  ['mei', "Ha! Look, I tried a new pattern on the foam. It's meant to be the old footbridge."],
  ['viktor', "Hm. The arch is wrong, but it's a fine likeness. Well done."],
];

const asides: Record<string, string[]> = {
  suki: ['Has anyone seen my headphones?', 'The square is lovely when the fountain is on.'],
  tom: ['Can anyone hear me over here?', 'Nobody ever comes out this way.'],
};

let nextLineId = 1000;

function say(speaker: string, text: string, conversationId: string): number {
  const duration = speakingSeconds(text);
  const message: LineMessage = {
    type: 'line',
    line: {
      id: nextLineId++,
      conversation_id: conversationId,
      speaker,
      text,
      timestamp: new Date().toISOString(),
      duration,
    },
    voiced: false,
  };
  server.dispatch(JSON.stringify(message));
  return duration;
}

function talk(turn = 0): void {
  const [speaker, text] = conversation[turn % conversation.length];
  const seconds = say(speaker, text, 'harness_conversation');
  setTimeout(() => talk(turn + 1), (seconds + 0.8) * 1000);
}

function muse(speaker: string, everyMs: number, turn = 0): void {
  say(speaker, asides[speaker][turn % asides[speaker].length], `harness_${speaker}`);
  setTimeout(() => muse(speaker, everyMs, turn + 1), everyMs);
}

function movePlayer(position: Position): void {
  server.dispatch(JSON.stringify({ type: 'entity_moved', entity_id: PLAYER_ID, position }));
}

function step(dx: number, dy: number): void {
  const at = trackedWorld.positionOf(PLAYER_ID);
  if (at) movePlayer({ ...at, x: at.x + dx, y: at.y + dy });
}

class HarnessScene extends Phaser.Scene {
  private graphics!: Phaser.GameObjects.Graphics;
  private readonly names = new Map<string, Phaser.GameObjects.Text>();

  create(): void {
    this.scene.sendToBack();
    this.graphics = this.add.graphics();
    for (const { id, name } of entities) {
      const label = this.add.text(0, 0, name, { fontSize: '10px', color: '#f4ecd8' });
      this.names.set(id, label.setOrigin(0.5, 0));
    }
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [-1, 0],
      ArrowRight: [1, 0],
      ArrowUp: [0, -1],
      ArrowDown: [0, 1],
      a: [-1, 0],
      d: [1, 0],
      w: [0, -1],
      s: [0, 1],
    };
    window.addEventListener('keydown', ({ key }) => {
      if (Object.hasOwn(moves, key)) step(...moves[key]);
    });
    this.input.on('pointerdown', ({ x, y }: Phaser.Input.Pointer) => {
      const tile = trackedWorld.tileAt({ x, y });
      if (tile && !npcAt({ x, y }, trackedWorld)) movePlayer({ ...tile, map: MAP });
    });
  }

  update(): void {
    const g = this.graphics.clear();
    const player = trackedWorld.positionOf(PLAYER_ID);
    const centre = player && trackedWorld.feetOnScreen(player);
    if (!centre) return;
    const { scale, tilePx: tile } = trackedWorld;
    const range = CHAT_RANGE_TILES * tile;
    g.lineStyle(scale, 0x7fc8a9);
    if (sideView(mapOf(player))) g.strokeRect(centre.x - range, 0, 2 * range, this.cameras.main.height);
    else g.strokeCircle(centre.x, centre.y - tile / 2, range);
    for (const entity of trackedWorld.all()) {
      const feet = trackedWorld.feetOnScreen(entity.position)!;
      g.fillStyle(0x2f4a40).fillRect(feet.x - tile / 2, feet.y - tile, tile, tile);
      g.fillStyle(entity.kind === 'player' ? 0x7fc8a9 : 0xe8b04a);
      g.fillRect(feet.x - tile / 4, feet.y - 1.5 * tile, tile / 2, 1.5 * tile);
      this.names.get(entity.id)?.setPosition(feet.x, feet.y + 2 * scale).setScale(scale);
    }
  }
}

function showPanel(root: HTMLElement): (message: ClientMessage) => void {
  const panel = root.appendChild(document.createElement('section'));
  panel.className = 'dialogue-harness';
  panel.innerHTML = `<b>Dialogue harness</b>
    <p>Arrows, WASD or click to move. T or Enter talks to the ringed NPC: click one or press Tab to pick
    another within ${CHAT_RANGE_TILES} tiles.</p>
    <ol></ol>`;
  const sent = panel.querySelector('ol')!;
  return (message) => {
    console.info('Harness: sent', message);
    if (message.type !== 'player_say') return;
    const item = sent.appendChild(document.createElement('li'));
    item.textContent = `player_say → ${message.target}: ${message.text}`;
  };
}

export function startHarness(scene: Phaser.Scene, root: HTMLElement): void {
  server.close();
  const record = showPanel(root);
  server.send = (message) => {
    record(message);
    return true;
  };
  server.dispatch(
    JSON.stringify({
      type: 'snapshot',
      time: new Date().toISOString(),
      map_id: MAP,
      entities,
      conversations: [],
    }),
  );
  scene.scene.add('dialogue-harness', HarnessScene, true);
  talk();
  setTimeout(() => muse('suki', 7000), 2500);
  muse('tom', 5000);
}
