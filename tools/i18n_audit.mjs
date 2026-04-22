/**
 * Playwright i18n 검수 — 모든 탭을 순회하면서 미번역 텍스트를 찾습니다.
 *
 * 실행: npx playwright test tools/i18n_audit.mjs --headed
 * 또는: node tools/i18n_audit.mjs
 */
import { chromium } from 'playwright';

const BASE = 'http://127.0.0.1:8080';
const LANGS = ['ko', 'en', 'zh'];

// 영어 페이지에서 한글이 보이면 미번역
const KO_RE = /[\uAC00-\uD7A3]/;
// 중국어 페이지에서 한글이 보이면 미번역
const ZH_RE = /[\uAC00-\uD7A3]/;

// 한국어 UI에서 영어 단어가 섞이는 건 정상 (기술 용어)
const TECH_TERMS = /^(Claude|CLI|API|JSON|MCP|DAG|SSE|Webhook|Cron|Ollama|Gemini|GPT|OpenAI|Codex|Anthropic|OAuth|UUID|JSONL|SQLite|HTTP|POST|GET|PUT|DELETE|URL|USD|ARIA|DOM|CSS|HTML|SVG|Ctrl|Shift|Tab|Esc|Delete|Enter|Space|README|CLAUDE|Modelfile|GGUF|FROM|SYSTEM|PARAMETER|LLM|RAG|BAAI|Nomic|BGE|token|model|provider|embed|chat|code|vision|reasoning|node|edge|workflow|template|export|import|clone|diff|merge|delay|retry|loop|start|output|subagent|session|aggregate|branch|transform|variable|subworkflow|embedding|error_handler)$/i;

async function auditTab(page, tabId, lang) {
  const issues = [];

  // 탭 이동
  await page.goto(`${BASE}/#/${tabId}`, { waitUntil: 'networkidle', timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(1500); // 렌더 대기

  // data-i18n 속성이 있는 요소의 텍스트 확인
  const i18nEls = await page.$$eval('[data-i18n]', els =>
    els.map(el => ({
      key: el.getAttribute('data-i18n'),
      text: el.textContent.trim().substring(0, 100),
      tag: el.tagName,
    }))
  );

  for (const el of i18nEls) {
    if (lang !== 'ko' && KO_RE.test(el.text)) {
      issues.push({
        type: 'data-i18n-untranslated',
        key: el.key,
        text: el.text,
        tab: tabId,
        lang,
      });
    }
  }

  // 페이지 전체 텍스트에서 한글 잔존 체크 (en/zh 모드)
  if (lang !== 'ko') {
    const bodyText = await page.$eval('body', el => el.innerText);
    const lines = bodyText.split('\n').filter(l => l.trim());
    for (const line of lines) {
      if (KO_RE.test(line)) {
        // 기술 용어만으로 구성된 줄은 제외
        const cleaned = line.replace(/[^가-힣]/g, '');
        if (cleaned.length >= 2) { // 한글 2자 이상
          issues.push({
            type: 'body-korean-text',
            text: line.trim().substring(0, 120),
            tab: tabId,
            lang,
          });
        }
      }
    }
  }

  return issues;
}

async function main() {
  const browser = await chromium.launch({ headless: true });

  // 검수할 주요 탭
  const tabs = [
    'overview', 'aiProviders', 'workflows', 'agents', 'skills', 'commands',
    'hooks', 'permissions', 'mcp', 'plugins', 'settings', 'claudemd',
    'sessions', 'usage', 'metrics', 'memory', 'tasks', 'system',
  ];

  for (const lang of ['en', 'zh']) {
    console.log(`\n${'='.repeat(60)}`);
    console.log(`LANGUAGE: ${lang}`);
    console.log('='.repeat(60));

    const context = await browser.newContext({ locale: lang === 'zh' ? 'zh-CN' : 'en-US' });
    const page = await context.newPage();

    // 언어 설정 — localStorage
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 15000 }).catch(() => {});
    await page.evaluate((l) => { localStorage.setItem('lang', l); }, lang);
    await page.reload({ waitUntil: 'networkidle', timeout: 10000 }).catch(() => {});
    await page.waitForTimeout(2000);

    let totalIssues = 0;

    for (const tab of tabs) {
      const issues = await auditTab(page, tab, lang);
      if (issues.length > 0) {
        totalIssues += issues.length;
        console.log(`\n  [${tab}] ${issues.length} issues:`);
        // 중복 제거
        const seen = new Set();
        for (const i of issues) {
          const key = `${i.type}:${i.text.substring(0, 50)}`;
          if (seen.has(key)) continue;
          seen.add(key);
          console.log(`    ${i.type}: "${i.text.substring(0, 80)}"`);
        }
      }
    }

    console.log(`\n  TOTAL: ${totalIssues} issues for ${lang}`);
    await context.close();
  }

  await browser.close();
}

main().catch(console.error);
