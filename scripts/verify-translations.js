#!/usr/bin/env node
/**
 * 번역 누락 검증 스크립트 — 0 건이면 통과, 1건 이상이면 exit 1.
 *
 * 4 단계 검증:
 *   1. 키 일치 검증  : ko/en/zh 세 파일의 키 집합 완전 일치
 *   2. 사용처 검증   : dist/index.html 의 모든 t('...') 호출 한국어 인자가 사전에 존재
 *   3. 원본 대조 검증 : translation-audit.json 의 모든 text 가 사전에 존재
 *   4. 정적 DOM 검증 : dist/index.html 의 HTML 텍스트 노드 · placeholder · title · alt · aria-label
 *                    속성값이 en/zh 사전에 존재 (runtime _translateDOM 가 소비하는 범위)
 *
 * 사용:
 *   node scripts/verify-translations.js
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const DIST = path.join(ROOT, 'dist');
const LOCALES = path.join(DIST, 'locales');
const HTML = path.join(DIST, 'index.html');
const AUDIT = path.join(ROOT, 'translation-audit.json');

const KO_RE = /[\uAC00-\uD7A3]/;

function loadLocale(lang) {
  const fp = path.join(LOCALES, `${lang}.json`);
  if (!fs.existsSync(fp)) {
    throw new Error(`locale file missing: ${fp}`);
  }
  return JSON.parse(fs.readFileSync(fp, 'utf-8'));
}

function loadHtml() {
  return fs.readFileSync(HTML, 'utf-8');
}

function extractTCalls(source) {
  const out = new Set();
  const re = /\bt\(\s*(['"`])((?:\\.|(?!\1).)*?)\1\s*\)/g;
  let m;
  while ((m = re.exec(source)) !== null) {
    const raw = m[2];
    if (KO_RE.test(raw)) out.add(raw.replace(/\\'/g, "'").replace(/\\"/g, '"'));
  }
  return out;
}

function extractDomKoreanPhrases(html) {
  // HTML 텍스트 노드 + placeholder/title/alt/aria-label 속성값에서 한국어 phrase 추출.
  // runtime _translateDOM 은 전체 일치 · 긴 키 부분 일치(5글자+) 두 경로를 쓴다.
  // 여기서는 "한국어 텍스트 한 덩어리 (줄바꿈 · 태그 바깥)" 단위로 추출.
  const out = new Set();
  const cleaned = html
    .replace(/<style[\s\S]*?<\/style>/g, '')
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/<script[\s\S]*?<\/script>/g, ''); // 스크립트 안 텍스트는 t() 경로로 별도 검증

  // 텍스트 노드 (> ... <)
  const textRe = />([^<>]*)</g;
  let m;
  while ((m = textRe.exec(cleaned)) !== null) {
    const raw = m[1];
    if (!KO_RE.test(raw)) continue;
    for (const line of raw.split('\n')) {
      const t = line.trim();
      if (t && KO_RE.test(t)) out.add(t);
    }
  }
  // 속성
  const attrs = ['placeholder', 'title', 'alt', 'aria-label'];
  for (const a of attrs) {
    const reDouble = new RegExp(`${a}\\s*=\\s*"([^"]*)"`, 'gi');
    const reSingle = new RegExp(`${a}\\s*=\\s*'([^']*)'`, 'gi');
    for (const re of [reDouble, reSingle]) {
      let mm;
      while ((mm = re.exec(cleaned)) !== null) {
        const v = mm[1];
        if (KO_RE.test(v)) out.add(v.trim());
      }
    }
  }
  return out;
}

function section(title) {
  console.log('\n─── ' + title + ' ───');
}

function main() {
  let failed = 0;

  section('1) 키 일치 검증');
  const ko = loadLocale('ko');
  const en = loadLocale('en');
  const zh = loadLocale('zh');
  const koKeys = new Set(Object.keys(ko));
  const enKeys = new Set(Object.keys(en));
  const zhKeys = new Set(Object.keys(zh));

  const onlyKo = [...koKeys].filter((k) => !enKeys.has(k) || !zhKeys.has(k));
  const onlyEn = [...enKeys].filter((k) => !koKeys.has(k) || !zhKeys.has(k));
  const onlyZh = [...zhKeys].filter((k) => !koKeys.has(k) || !enKeys.has(k));
  console.log(`ko: ${koKeys.size}, en: ${enKeys.size}, zh: ${zhKeys.size}`);
  if (onlyKo.length || onlyEn.length || onlyZh.length) {
    console.error(`  ✗ 키 불일치: ko-only=${onlyKo.length}, en-only=${onlyEn.length}, zh-only=${onlyZh.length}`);
    if (onlyKo.length) console.error('    ko-only sample:', onlyKo.slice(0, 5));
    if (onlyEn.length) console.error('    en-only sample:', onlyEn.slice(0, 5));
    if (onlyZh.length) console.error('    zh-only sample:', onlyZh.slice(0, 5));
    failed++;
  } else {
    console.log('  ✓ 3개 파일의 키 집합 일치');
  }

  const html = loadHtml();

  section(`2) 사용처 검증 (t('...') 호출)`);
  const tCalls = extractTCalls(html);
  const missingT_en = [...tCalls].filter((k) => !(k in en));
  const missingT_zh = [...tCalls].filter((k) => !(k in zh));
  console.log(`t() 호출 한국어 인자: ${tCalls.size}`);
  if (missingT_en.length || missingT_zh.length) {
    console.error(`  ✗ t() 인자 번역 누락: en=${missingT_en.length}, zh=${missingT_zh.length}`);
    if (missingT_en.length) console.error('    en 누락 sample:', missingT_en.slice(0, 5));
    if (missingT_zh.length) console.error('    zh 누락 sample:', missingT_zh.slice(0, 5));
    failed++;
  } else {
    console.log(`  ✓ 모든 t() 인자가 ko/en/zh 에 존재`);
  }

  section('3) 원본 대조 검증 (translation-audit.json)');
  if (!fs.existsSync(AUDIT)) {
    console.error('  ✗ translation-audit.json 없음 — `python3 tools/extract_ko_strings.py` 실행');
    failed++;
  } else {
    const audit = JSON.parse(fs.readFileSync(AUDIT, 'utf-8'));
    const items = audit.items.map((i) => i.text);
    const missAudit_en = items.filter((k) => !(k in en));
    const missAudit_zh = items.filter((k) => !(k in zh));
    console.log(`audit items: ${items.length}`);
    if (missAudit_en.length || missAudit_zh.length) {
      console.error(
        `  ✗ audit 항목 번역 누락: en=${missAudit_en.length}, zh=${missAudit_zh.length}`
      );
      if (missAudit_en.length) console.error('    en 누락 sample:', missAudit_en.slice(0, 5));
      if (missAudit_zh.length) console.error('    zh 누락 sample:', missAudit_zh.slice(0, 5));
      failed++;
    } else {
      console.log(`  ✓ audit 항목 모두 번역됨`);
    }
  }

  section('4) 정적 DOM 한국어 phrase 검증');
  const domPhrases = extractDomKoreanPhrases(html);
  // 정확히 일치하지 않더라도 runtime 은 "긴 키 부분 치환" 으로 커버.
  // 따라서 '완전 일치' 또는 '사전 키 중 하나가 phrase 의 substring' 인 것까지 허용.
  const keyList = Object.keys(en)
    .filter((k) => KO_RE.test(k))
    .sort((a, b) => b.length - a.length);
  function hasCoverage(phrase, dict) {
    if (phrase in dict) return true;
    // 긴 키(5글자+) 로 부분 치환 가능한지 확인
    for (const k of keyList) {
      if (k.length >= 5 && phrase.includes(k)) return true;
    }
    return false;
  }
  const uncovered_en = [];
  const uncovered_zh = [];
  for (const p of domPhrases) {
    if (!hasCoverage(p, en)) uncovered_en.push(p);
    if (!hasCoverage(p, zh)) uncovered_zh.push(p);
  }
  console.log(`static DOM phrases: ${domPhrases.size}`);
  if (uncovered_en.length || uncovered_zh.length) {
    console.error(
      `  ✗ 정적 phrase 커버리지 누락: en=${uncovered_en.length}, zh=${uncovered_zh.length}`
    );
    if (uncovered_en.length) console.error('    en 누락 sample:', uncovered_en.slice(0, 5));
    if (uncovered_zh.length) console.error('    zh 누락 sample:', uncovered_zh.slice(0, 5));
    failed++;
  } else {
    console.log(`  ✓ 모든 정적 DOM phrase 가 번역 커버됨`);
  }

  section('요약');
  if (failed > 0) {
    console.error(`✗ 실패한 검증: ${failed} 건`);
    process.exit(1);
  }
  console.log('✓ 모든 검증 통과');
}

main();
