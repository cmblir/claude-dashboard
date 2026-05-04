import { test, expect } from '@playwright/test';
import * as path from 'node:path';
import type { Server } from 'node:http';

import { startStaticServer } from '../src/lazyclaw/web/server.mjs';

let server: Server;
let baseUrl: string;

test.beforeAll(async () => {
  const root = path.resolve(process.cwd(), 'dist-lazyclaw');
  const r = await startStaticServer(root);
  server = r.server;
  baseUrl = r.url;
});

test.afterAll(async () => {
  await new Promise<void>(resolve => server.close(() => resolve()));
});

test.describe('Phase 3 — Chat UI', () => {
  test('user can send a message and receive a reply', async ({ page }) => {
    await page.goto(baseUrl + '/index.html');
    await page.fill('#input', 'hello');
    await page.click('#send');
    const lastBot = page.locator('.msg.bot').last();
    await expect(lastBot).toContainText('mock-reply: hello');
  });

  test('streaming displays incrementally', async ({ page }) => {
    await page.goto(baseUrl + '/index.html');
    await page.fill('#input', 'streamtest');
    // Sample text length over time and assert the bubble grew at least once
    // before reaching its final size.
    const samples: number[] = [];
    const sampler = setInterval(async () => {
      try {
        const t = await page.locator('.msg.bot').last().textContent();
        samples.push((t || '').length);
      } catch { /* ignore — element may not exist yet */ }
    }, 15);
    await page.click('#send');
    const lastBot = page.locator('.msg.bot').last();
    await expect(lastBot).toContainText('mock-reply: streamtest');
    clearInterval(sampler);
    const intermediate = samples.filter(n => n > 0 && n < 'mock-reply: streamtest'.length);
    expect(intermediate.length).toBeGreaterThan(0);
  });

  test('settings persist across reload', async ({ page }) => {
    await page.goto(baseUrl + '/index.html');
    await page.fill('#apiKey', 'sk-test-123');
    await page.fill('#model', 'claude-test-model');
    await page.click('#saveSettings');
    await page.reload();
    await expect(page.locator('#apiKey')).toHaveValue('sk-test-123');
    await expect(page.locator('#model')).toHaveValue('claude-test-model');
  });

  test('invalid API key shows an error', async ({ page }) => {
    await page.goto(baseUrl + '/index.html');
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.selectOption('#provider', 'anthropic');
    await page.fill('#apiKey', '');
    await page.click('#saveSettings');
    await page.fill('#input', 'hello');
    await page.click('#send');
    await expect(page.locator('#error')).toContainText('invalid api key');
  });
});
