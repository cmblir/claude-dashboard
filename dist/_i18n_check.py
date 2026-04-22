#!/usr/bin/env python3
"""Find ALL missing i18n keys and output just the missing ones."""
import re, json

# Read HTML
with open('/Users/o/claude-dashboard/dist/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

print(f"HTML file size: {len(html)} chars, {len(html.splitlines())} lines")

# Extract ALL t('...') keys
t_keys = set(re.findall(r"t\('([^']+)'\)", html))
# Extract data-i18n="..." keys
di_keys = set(re.findall(r'data-i18n="([^"]+)"', html))
# Extract data-i18n-placeholder="..." keys
dip_keys = set(re.findall(r'data-i18n-placeholder="([^"]+)"', html))

all_raw = t_keys | di_keys | dip_keys
print(f"Raw keys: t()={len(t_keys)} data-i18n={len(di_keys)} placeholder={len(dip_keys)} total_unique={len(all_raw)}")

# Apply user's filter: exclude fake matches
# - starts with $, #, ., {
# - 2 chars or less
# - contains (
filtered = set()
for k in all_raw:
    if k[0] in ('$', '#', '.', '{'):
        continue
    if len(k) <= 2:
        continue
    if '(' in k:
        continue
    filtered.add(k)

print(f"After filter: {len(filtered)} keys")
print()

# Load locales and find missing
for lang in ['ko', 'en', 'zh']:
    path = f'/Users/o/claude-dashboard/dist/locales/{lang}.json'
    with open(path, 'r', encoding='utf-8') as f:
        locale = json.load(f)

    missing = sorted([k for k in filtered if k not in locale])
    print(f"{lang}.json: {len(locale)} keys, {len(filtered)-len(missing)} present, {len(missing)} MISSING")
    for m in missing:
        print(f"  MISS: {repr(m)}")

print()
print("=== ALL filtered keys (sorted) ===")
for k in sorted(filtered):
    print(f"  {repr(k)}")
