import { defineConfig } from '@playwright/test';

// Verification scaffold for Ralph loop acceptance criteria.
// The repo's primary E2E suite is the 121 `scripts/e2e-*.mjs` files
// (driven directly via the playwright library). The specs in `tests/`
// are thin wrappers that exercise those same scripts under the
// `@playwright/test` runner so `npx playwright test` exits 0.

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: 'list',
  timeout: 60_000,
  expect: { timeout: 5_000 },
  use: {
    baseURL: process.env.BASE_URL || 'http://127.0.0.1:8080',
    headless: true,
  },
});
