import { ServerConnection } from './connection';

export { SAMPLE_RATE, type AudioChunk } from './audio';
export type { ServerEvent, ServerEvents } from './connection';
export type * from './protocol';

/** Messages aren't replayed, so subscribe when your module loads, before the first one arrives. */
export const server = new ServerConnection();

if (import.meta.env.MODE !== 'test') {
  server.on('snapshot', (snapshot) => console.info('Snapshot from the sim server', snapshot));
  server.connect();
}
