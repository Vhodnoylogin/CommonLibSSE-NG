#!/usr/bin/env python3
"""Parse clang -fdump-record-layouts output into JSON: {record: {size, align, lines:[[off, depth, text]]}}. 
Offsets in the dump are decimal; bitfields look like '8:0-3'. Only RE::/REL::/SKSE:: records are kept."""
import json, re, sys
src, dst = sys.argv[1], sys.argv[2]
recs, cur = {}, None
line_re = re.compile(r'^\s*(\d+)(?::(\d+)-(\d+))? \| (\s*)(.*)$')
for raw in open(src, encoding='utf-8', errors='replace'):
    raw = raw.rstrip('\n')
    if raw.startswith('*** Dumping AST Record Layout'):
        cur = None; continue
    m = line_re.match(raw)
    if m:
        off, b0, b1, ind, text = m.groups()
        depth = len(ind) // 2
        if cur is None:
            name = re.sub(r'^(class|struct|union) ', '', text)
            name = re.sub(r' \(empty\)$', '', name)
            cur = {'name': name, 'lines': []}
            recs.setdefault(name, cur)
            continue
        cur['lines'].append([int(off), depth, text] + ([int(b0), int(b1)] if b0 else []))
        continue
    m = re.search(r'\[sizeof=(\d+), align=(\d+)', raw)
    if m and cur is not None:
        cur['size'], cur['align'] = int(m.group(1)), int(m.group(2))
keep = {k: v for k, v in recs.items() if re.match(r'^(RE|REL|SKSE|REX)::', k)}
json.dump(keep, open(dst, 'w'), ensure_ascii=False)
print(len(recs), 'records,', len(keep), 'kept')
