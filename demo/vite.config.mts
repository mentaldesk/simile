// The client's config with its proxy pointed at $SIMILE_PORT, so the demo can run beside make dev.
import client from '../client/vite.config.ts';

const server = `http://127.0.0.1:${process.env.SIMILE_PORT ?? '8000'}`;

export default {
  ...client,
  server: {
    ...client.server,
    proxy: {
      '/api': server,
      '/ws': { target: server, ws: true },
    },
  },
};
