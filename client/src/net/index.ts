import { ServerConnection } from './connection';

export { SAMPLE_RATE, type AudioChunk } from './audio';
export type { ServerEvent, ServerEvents } from './connection';
export type * from './protocol';

function serverUrl(): string {
  const url = new URL('/ws', window.location.href);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.href;
}

/** Messages aren't replayed, so subscribe when your module loads, before the first one arrives. */
export const server = new ServerConnection(serverUrl());

server.on('snapshot', (snapshot) => console.info('Snapshot from the sim server', snapshot));
server.connect();
