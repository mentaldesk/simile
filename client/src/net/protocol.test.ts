import { compile } from 'json-schema-to-typescript';
import { expect, it } from 'vitest';
import schema from '../../../server/simile/protocol/protocol.schema.json?raw';

const banner = `// Generated from server/simile/protocol/protocol.schema.json by protocol.test.ts.
// Don't edit it by hand: docs/protocol.md says how to regenerate it.`;

const generate = () =>
  compile(JSON.parse(schema), 'Message', {
    bannerComment: banner,
    additionalProperties: false,
    style: { singleQuote: true, printWidth: 100 },
  });

it('protocol.ts matches the server JSON Schema', async () => {
  await expect(await generate()).toMatchFileSnapshot(
    './protocol.ts',
    'Run `npx vitest run src/net/protocol.test.ts -u` in client/ and commit protocol.ts.',
  );
});

it('protocol.ts declares no numbered copies of a type', async () => {
  expect(await generate()).not.toMatch(/^export (interface|type) \w+\d\b/m);
});
