import { server, type Line } from '../net';
import { SpeechBubbles, speakingSeconds } from './bubbles';
import { DialogueLog } from './log';
import { CHAT_RANGE_TILES, EARSHOT_TILES } from './tuning';
import { distanceFromPlayer, PLAYER_ID, worldView, type WorldView } from './world-view';

type Server = Pick<typeof server, 'on' | 'send'>;

export function chatTarget(view: WorldView): string | undefined {
  let nearest: string | undefined;
  let nearestDistance = Infinity;
  for (const id of view.npcIds()) {
    const distance = distanceFromPlayer(view, id);
    if (distance === undefined || distance > CHAT_RANGE_TILES) continue;
    if (distance < nearestDistance) {
      nearest = id;
      nearestDistance = distance;
    }
  }
  return nearest;
}

export class Dialogue {
  readonly bubbles = new SpeechBubbles();
  readonly log = new DialogueLog();
  private readonly names = new Map<string, string>();
  private readonly server: Server;
  private readonly view: () => WorldView;

  constructor(server: Server, view: () => WorldView) {
    this.server = server;
    this.view = view;
  }

  listen(): () => void {
    const unsubscribes = [
      this.server.on('snapshot', ({ entities }) => {
        this.names.clear();
        for (const { id, name } of entities) this.names.set(id, name);
      }),
      this.server.on('line', ({ line }) => this.hear(line)),
    ];
    return () => unsubscribes.forEach((unsubscribe) => unsubscribe());
  }

  nameOf(entityId: string): string {
    return entityId === PLAYER_ID ? 'You' : (this.names.get(entityId) ?? entityId);
  }

  hear(line: Line): boolean {
    if (line.speaker === PLAYER_ID) return false; // say() showed it already
    const distance = distanceFromPlayer(this.view(), line.speaker);
    if (distance === undefined || distance > EARSHOT_TILES) return false;
    this.bubbles.show(line.speaker, line.text, line.duration);
    this.log.add({
      speaker: line.speaker,
      name: this.nameOf(line.speaker),
      text: line.text,
      to: null,
    });
    return true;
  }

  say(text: string, target: string): boolean {
    const said = text.trim();
    if (!said || !this.server.send({ type: 'player_say', text: said, target })) return false;
    this.bubbles.show(PLAYER_ID, said, speakingSeconds(said));
    this.log.add({
      speaker: PLAYER_ID,
      name: this.nameOf(PLAYER_ID),
      text: said,
      to: this.nameOf(target),
    });
    return true;
  }
}

export const dialogue = new Dialogue(server, worldView);
dialogue.listen();
