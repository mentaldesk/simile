import { server, type Conversation, type Line } from '../net';
import { SpeechBubbles, speakingSeconds } from './bubbles';
import { DialogueLog } from './log';
import { CHAT_RANGE_TILES, EARSHOT_TILES } from './tuning';
import { distanceFromPlayer, PLAYER_ID, worldView, type WorldView } from './world-view';

type Server = Pick<typeof server, 'on' | 'send'>;

type Talks = Pick<Dialogue, 'partner' | 'busy'>;

/** The NPC the player is talking with until the server ends it, else the nearest free one. */
export function chatTarget(view: WorldView, talks?: Talks): string | undefined {
  const partner = talks?.partner();
  if (partner !== undefined) return partner;
  let nearest: string | undefined;
  let nearestDistance = Infinity;
  for (const id of view.npcIds()) {
    if (talks?.busy(id)) continue;
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
  private readonly talks = new Map<string, readonly string[]>();
  private readonly invitations = new Set<(npcId: string) => void>();
  private readonly server: Server;
  private readonly view: () => WorldView;

  constructor(server: Server, view: () => WorldView) {
    this.server = server;
    this.view = view;
  }

  listen(): () => void {
    const unsubscribes = [
      this.server.on('snapshot', ({ entities, conversations }) => {
        this.names.clear();
        for (const { id, name } of entities) this.names.set(id, name);
        this.talks.clear();
        for (const { id, participants } of conversations) this.talks.set(id, participants);
      }),
      this.server.on('conversation_started', ({ conversation }) => this.started(conversation)),
      this.server.on('conversation_ended', ({ conversation_id }) => this.ended(conversation_id)),
      this.server.on('line', ({ line }) => this.hear(line)),
    ];
    return () => unsubscribes.forEach((unsubscribe) => unsubscribe());
  }

  partner(): string | undefined {
    for (const participants of this.talks.values()) {
      if (participants.includes(PLAYER_ID)) return participants.find((id) => id !== PLAYER_ID);
    }
    return undefined;
  }

  busy(npcId: string): boolean {
    return [...this.talks.values()].some(
      (participants) => participants.includes(npcId) && !participants.includes(PLAYER_ID),
    );
  }

  onInvitation(listener: (npcId: string) => void): () => void {
    this.invitations.add(listener);
    return () => this.invitations.delete(listener);
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
      to: this.withPlayer(line.conversation_id) ? this.nameOf(PLAYER_ID) : null,
    });
    return true;
  }

  say(text: string, target: string): boolean {
    const said = text.trim();
    if (!said || !this.server.send({ type: 'player_say', text: said, target })) return false;
    this.bubbles.show(PLAYER_ID, said, speakingSeconds(said));
    this.bubbles.think(target);
    this.log.add({
      speaker: PLAYER_ID,
      name: this.nameOf(PLAYER_ID),
      text: said,
      to: this.nameOf(target),
    });
    return true;
  }

  private withPlayer(conversationId: string): boolean {
    return this.talks.get(conversationId)?.includes(PLAYER_ID) ?? false;
  }

  private started({ id, participants }: Conversation): void {
    this.talks.set(id, participants);
    const [opener] = participants;
    if (opener === PLAYER_ID || !participants.includes(PLAYER_ID)) return;
    for (const listener of this.invitations) listener(opener);
  }

  private ended(conversationId: string): void {
    const participants = this.talks.get(conversationId) ?? [];
    this.talks.delete(conversationId);
    if (!participants.includes(PLAYER_ID)) return;
    for (const id of participants) if (id !== PLAYER_ID) this.bubbles.stopThinking(id);
  }
}

export const dialogue = new Dialogue(server, worldView);
dialogue.listen();
