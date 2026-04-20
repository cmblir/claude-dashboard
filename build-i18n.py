#!/usr/bin/env python3
"""Generate fully translated index-en.html and index-zh.html.
Translates ALL Korean text everywhere — HTML content AND JS string literals."""
import re

SRC = "dist/index.html"
with open(SRC, "r") as f:
    html = f.read()

# Extract dicts
en_match = re.search(r"I18N\.en = \{(.*?)\};", html, re.DOTALL)
zh_block = re.search(r"const zhMap = \{(.*?)\};", html, re.DOTALL)

def parse_dict(block_text):
    d = {}
    for m in re.finditer(r"'([^'\\]*(?:\\.[^'\\]*)*)'\s*:\s*'([^'\\]*(?:\\.[^'\\]*)*)'", block_text):
        key = m.group(1).replace("\\'", "'")
        val = m.group(2).replace("\\'", "'")
        if any('\uAC00' <= c <= '\uD7A3' for c in key):
            d[key] = val
    return d

en_dict = parse_dict(en_match.group(1)) if en_match else {}
zh_dict = parse_dict(zh_block.group(1)) if zh_block else {}
print(f"EN: {len(en_dict)} keys, ZH: {len(zh_dict)} keys")

def build_translated(html_src, trans_dict):
    """Translate ALL Korean text — in HTML and JS alike."""
    # Sort keys longest-first to prevent short keys from corrupting longer words
    keys = sorted(trans_dict.keys(), key=len, reverse=True)

    # Split into style, script, html segments
    parts = re.split(r'(<style[\s\S]*?</style>|<script[\s\S]*?</script>)', html_src)

    result = []
    for part in parts:
        if part.startswith('<style'):
            result.append(part)  # Don't touch CSS
        elif part.startswith('<script'):
            # JS: translate all Korean, but escape single quotes in replacements
            inner_match = re.match(r'(<script[^>]*>)(.*?)(</script>)', part, re.DOTALL)
            if not inner_match:
                result.append(part)
                continue
            open_tag, js, close_tag = inner_match.groups()

            for k in keys:
                if k not in js:
                    continue
                v = trans_dict[k]
                # Replace ' with unicode right quote to avoid breaking JS strings
                safe_v = v.replace("'", "\u2019")
                # Use Korean-boundary-aware replacement to prevent short keys
                # from corrupting longer words (e.g. '전' matching inside '전체')
                pattern = re.escape(k)
                js = re.sub(
                    r'(?<![가-힣])' + pattern + r'(?![가-힣])',
                    safe_v, js
                )

            result.append(open_tag + js + close_tag)
        else:
            # HTML: translate with Korean-boundary-aware replacement
            translated = part
            for k in keys:
                if k in translated:
                    pattern = re.escape(k)
                    translated = re.sub(
                        r'(?<![가-힣])' + pattern + r'(?![가-힣])',
                        trans_dict[k], translated
                    )
            result.append(translated)

    return ''.join(result)

en_html = build_translated(html, en_dict)
# Post-process: update html lang, _curLang default
en_html = en_html.replace('<html lang="ko">', '<html lang="en">')
en_html = en_html.replace("let _curLang = 'ko'", "let _curLang = 'en'")
with open("dist/index-en.html", "w") as f:
    f.write(en_html)

zh_html = build_translated(html, zh_dict)
zh_html = zh_html.replace('<html lang="ko">', '<html lang="zh">')
zh_html = zh_html.replace("let _curLang = 'ko'", "let _curLang = 'zh'")
with open("dist/index-zh.html", "w") as f:
    f.write(zh_html)

# Validate JS
import subprocess
for lang, path in [("EN", "dist/index-en.html"), ("ZH", "dist/index-zh.html")]:
    with open(path) as f:
        h = f.read()
    m = re.search(r'<script>(.*?)</script>', h, re.DOTALL)
    if m:
        r = subprocess.run(['node', '-e', f'new Function(`{m.group(1)[:100]}`)'],
                          capture_output=True, text=True, timeout=5)
    # Full validation
    r2 = subprocess.run(['node', '-e',
        f"const fs=require('fs');const h=fs.readFileSync('{path}','utf8');"
        f"const m=h.match(/<script>([\\s\\S]*)<\\/script>/);try{{new Function(m[1]);console.log('{lang} OK')}}catch(e){{console.log('{lang} ERR:',e.message)}}"],
        capture_output=True, text=True, timeout=10)
    print(r2.stdout.strip())

# Count remaining Korean in translated files
ko_re = re.compile(r'[\uAC00-\uD7A3]')
for lang, path in [("EN", "dist/index-en.html"), ("ZH", "dist/index-zh.html")]:
    with open(path) as f:
        content = f.read()
    # Count Korean chars outside I18N dict definitions
    # Remove I18N dict sections for counting
    clean = re.sub(r'I18N\.en = \{.*?\};', '', content, flags=re.DOTALL)
    clean = re.sub(r'const zhMap = \{.*?\};', '', clean, flags=re.DOTALL)
    clean = re.sub(r'_NAV_KEYWORDS = \{.*?\};', '', clean, flags=re.DOTALL)
    ko_chars = len(ko_re.findall(clean))
    print(f"{lang}: {ko_chars} Korean chars remaining (outside dicts)")
