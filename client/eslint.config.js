import js from '@eslint/js';
import { defineConfig, globalIgnores } from 'eslint/config';
import tseslint from 'typescript-eslint';

export default defineConfig(
  globalIgnores(['dist']),
  js.configs.recommended,
  tseslint.configs.recommended,
  {
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['@anthropic-ai/*'],
              message:
                'Never use the Claude API. LLM calls go through the server, over local Claude Code.',
            },
          ],
        },
      ],
    },
  },
);
