// ESLint v10 flat config. Lints tests/ TypeScript only —
// dist/app.js is hand-managed and intentionally excluded.
import tsParser from '@typescript-eslint/parser';

export default [
  {
    ignores: ['node_modules/**', 'dist/**', 'scripts/**', 'tools/**', 'server/**', 'docs/**'],
  },
  {
    files: ['tests/**/*.ts', 'tests/**/*.mts'],
    languageOptions: {
      parser: tsParser,
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        process: 'readonly',
        console: 'readonly',
      },
    },
    rules: {
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      'no-undef': 'off', // TS handles this
      semi: ['error', 'always'],
    },
  },
];
