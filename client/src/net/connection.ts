import { decodeAudioChunk, type AudioChunk } from './audio';
import type { ClientMessage, ServerMessage } from './protocol';

export type ServerEvents = { [M in ServerMessage as M['type']]: M } & { audio_chunk: AudioChunk };
export type ServerEvent = keyof ServerEvents;
type Handler<E extends ServerEvent> = (event: ServerEvents[E]) => void;

export type Socket = Pick<
  WebSocket,
  'binaryType' | 'readyState' | 'onopen' | 'onmessage' | 'onclose' | 'send' | 'close'
>;

const OPEN = 1;
const FIRST_RETRY_MS = 250;
const MAX_RETRY_MS = 5000;

function sameOriginUrl(): string {
  const url = new URL('/ws', window.location.href);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.href;
}

/** The WebSocket to the sim server. It reconnects by itself; each connection starts with a snapshot. */
export class ServerConnection {
  private readonly url?: string;
  private readonly createSocket: (url: string) => Socket;
  private readonly handlers = new Map<ServerEvent, Set<Handler<never>>>();
  private socket?: Socket;
  private retryMs = FIRST_RETRY_MS;
  private retry?: ReturnType<typeof setTimeout>;
  private stopped = false;

  /** Without a URL, it connects to `/ws` on the page's own origin. */
  constructor(url?: string, createSocket: (url: string) => Socket = (url) => new WebSocket(url)) {
    this.url = url;
    this.createSocket = createSocket;
  }

  on<E extends ServerEvent>(event: E, handler: Handler<E>): () => void {
    const handlers = this.handlers.get(event) ?? new Set();
    this.handlers.set(event, handlers);
    handlers.add(handler);
    return () => handlers.delete(handler);
  }

  /** Returns false, dropping the message, while disconnected. */
  send(message: ClientMessage): boolean {
    if (this.socket?.readyState !== OPEN) return false;
    this.socket.send(JSON.stringify(message));
    return true;
  }

  connect(): void {
    this.stopped = false;
    const socket = this.createSocket(this.url ?? sameOriginUrl());
    socket.binaryType = 'arraybuffer';
    socket.onopen = () => {
      this.retryMs = FIRST_RETRY_MS;
    };
    socket.onmessage = ({ data }) => this.dispatch(data);
    socket.onclose = () => {
      if (this.stopped) return;
      this.retry = setTimeout(() => this.connect(), this.retryMs);
      this.retryMs = Math.min(this.retryMs * 2, MAX_RETRY_MS);
    };
    this.socket = socket;
  }

  close(): void {
    this.stopped = true;
    clearTimeout(this.retry);
    this.socket?.close();
  }

  /** Handles a frame as if the server had sent it: a JSON message, or an audio chunk. */
  dispatch(data: string | ArrayBuffer): void {
    if (data instanceof ArrayBuffer) {
      this.emit('audio_chunk', decodeAudioChunk(data));
    } else if (typeof data === 'string') {
      const message = JSON.parse(data) as ServerMessage;
      this.emit(message.type, message);
    }
  }

  private emit<E extends ServerEvent>(event: E, payload: ServerEvents[E]): void {
    for (const handler of this.handlers.get(event) ?? []) {
      try {
        (handler as Handler<E>)(payload);
      } catch (error) {
        console.error(`A ${event} handler failed`, error);
      }
    }
  }
}
