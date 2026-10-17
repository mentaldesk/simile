import { server, type Conversation, type Line } from '../net';
import { SpeechBubbles, speakingSeconds } from './bubbles';
import { DialogueLog, type LogEntry } from './log';
import { EARSHOT_TILES } from './tuning';
import { distanceFromPlayer, PLAYER_ID, worldView, type WorldView } from './world-view';

type Server = Pick<typeof server, 'on' | 'send'>;

const CUT = /[,;—–-]$/;

function joined(clause: string, rest: string): string {
  return /\S(?:[—–]|--)$/.test(clause) ? clause + rest : `${clause} ${rest}`;
}

export class Dialogue {
  readonly bubbles = new SpeechBubbles();
  readonly log = new DialogueLog();
  private readonly names = new Map<string, string>();
  private readonly talks = new Map<string, readonly string[]>();
  private readonly invitations = new Set<(npcId: string) => void>();
  private readonly latest = new Map<string, { speaker: string; text: string }>();
  private readonly held = new Map<string, LogEntry>();
  private readonly server: Server;
  private readonly view: () => WorldView;

  constructor(server: Server, view: () => WorldView) {
    this.server = server;
    this.view = view;
  }

  listen(): () => void {
    const unsubscribes = [
      this.server.on('snapshot', ({ entities, conversations }) => {
        this.release();
        this.latest.clear();
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
    const conversation = line.conversation_id;
    const before = this.latest.get(conversation);
    const held = this.held.get(conversation);
    this.latest.delete(conversation);
    this.held.delete(conversation);
    const partner = this.withPlayer(conversation);
    const distance = distanceFromPlayer(this.view(), line.speaker);
    const near = distance !== undefined && distance <= EARSHOT_TILES;
    const heard = line.speaker !== PLAYER_ID && (partner || near); // say() showed the player's
    const continues = partner && before?.speaker === line.speaker && CUT.test(before.text);
    if (held && !continues) this.logged(held);
    if (!heard) return false;
    const text = continues ? joined(before.text, line.text) : line.text;
    this.latest.set(conversation, { speaker: line.speaker, text });
    this.bubbles.show(line.speaker, text, line.duration, partner);
    const entry = {
      speaker: line.speaker,
      name: this.nameOf(line.speaker),
      text: held && continues ? joined(held.text, line.text) : line.text,
      to: partner ? this.nameOf(PLAYER_ID) : null,
    };
    if (partner && CUT.test(text)) this.held.set(conversation, entry);
    else this.logged(entry);
    return true;
  }

  say(text: string, target: string): boolean {
    const said = text.trim();
    if (!said || !this.server.send({ type: 'player_say', text: said, target })) return false;
    this.bubbles.show(PLAYER_ID, said, speakingSeconds(said));
    this.bubbles.think(target);
    for (const [id, participants] of this.talks) {
      if (participants.includes(PLAYER_ID)) this.latest.delete(id);
    }
    this.logged({
      speaker: PLAYER_ID,
      name: this.nameOf(PLAYER_ID),
      text: said,
      to: this.nameOf(target),
    });
    return true;
  }

  private logged(entry: LogEntry): void {
    this.release();
    this.log.add(entry);
  }

  private release(conversationId?: string): void {
    for (const [id, entry] of this.held) {
      if (conversationId !== undefined && id !== conversationId) continue;
      this.held.delete(id);
      this.log.add(entry);
    }
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
    this.release(conversationId);
    this.latest.delete(conversationId);
    if (!participants.includes(PLAYER_ID)) return;
    for (const id of participants) if (id !== PLAYER_ID) this.bubbles.stopThinking(id);
  }
}

export const dialogue = new Dialogue(server, worldView);
dialogue.listen();
