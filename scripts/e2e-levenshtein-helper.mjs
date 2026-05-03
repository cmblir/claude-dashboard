#!/usr/bin/env node
/**
 * QQ170 — locks in the QQ163 shared `_lcLevenshtein` helper. The
 * QQ161 / QQ162 typo suggesters depend on it returning correct edit
 * distances; a stray "optimisation" that breaks edge cases would
 * regress every typo hint silently.
 */
import { chromium } from 'playwright';

const PORT = process.env.PORT || '19500';
const URL  = `http://127.0.0.1:${PORT}/`;

function check(label, ok, detail) {
  const tag = ok ? '[32m✅[0m' : '[31m❌[0m';
  console.log(`${tag} ${label}${detail ? ' — ' + detail : ''}`);
  if (!ok) process.exitCode = 1;
}

const browser = await chromium.launch({ headless: process.env.HEADLESS !== '0' });
const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage();

await page.goto(URL, { waitUntil: 'networkidle' });
await page.evaluate(() => window.go && window.go('lazyclawChat'));
await page.waitForSelector('#lcChatInput', { timeout: 8000 });

const r = await page.evaluate(() => ({
  emptyEmpty:   window._lcLevenshtein('', ''),
  emptyString:  window._lcLevenshtein('', 'abc'),
  stringEmpty:  window._lcLevenshtein('abc', ''),
  same:         window._lcLevenshtein('abc', 'abc'),
  oneSubst:     window._lcLevenshtein('abc', 'abd'),
  oneInsert:    window._lcLevenshtein('vrsion', 'version'),
  oneDelete:    window._lcLevenshtein('version', 'vrsion'),
  textbook:     window._lcLevenshtein('kitten', 'sitting'),
  windowExposed: typeof window._lcLevenshtein,
}));

check('exposed on window as a function',  r.windowExposed === 'function');
check('lev("", "") === 0',                r.emptyEmpty === 0,  `${r.emptyEmpty}`);
check('lev("", "abc") === 3',             r.emptyString === 3, `${r.emptyString}`);
check('lev("abc", "") === 3',             r.stringEmpty === 3, `${r.stringEmpty}`);
check('lev("abc", "abc") === 0',          r.same === 0,        `${r.same}`);
check('lev("abc", "abd") === 1 (subst)',  r.oneSubst === 1,    `${r.oneSubst}`);
check('lev("vrsion", "version") === 1 (insert)',
  r.oneInsert === 1, `${r.oneInsert}`);
check('lev("version", "vrsion") === 1 (delete)',
  r.oneDelete === 1, `${r.oneDelete}`);
check('lev("kitten", "sitting") === 3 (textbook)',
  r.textbook === 3, `${r.textbook}`);

await browser.close();
console.log(process.exitCode ? '\nFAILED' : '\nOK');
