import { compile } from 'json-schema-to-typescript';
import { expect, it } from 'vitest';
import schema from '../../../server/simile/schema/json/Character.json?raw';

const banner = `// Generated from server/simile/schema/json/Character.json by character.test.ts.
// Don't edit it by hand: run \`npx vitest run src/creator/character.test.ts -u\` in client/.`;

it('character.ts matches the server JSON Schema', async () => {
  const generated = await compile(JSON.parse(schema), 'Character', {
    bannerComment: banner,
    additionalProperties: false,
    style: { singleQuote: true, printWidth: 100 },
  });

  await expect(generated).toMatchFileSnapshot(
    './character.ts',
    'Run `npx vitest run src/creator/character.test.ts -u` in client/ and commit character.ts.',
  );
});
