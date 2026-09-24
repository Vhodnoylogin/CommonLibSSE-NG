#!/usr/bin/env python3
"""Compare trinity hand-written structs (offset comments + offsetof/sizeof asserts) against CommonLib VR layouts 
(clang dump). For every trinity field with a known offset: which CommonLib member starts there, or which one covers it."""
import re, json, csv, os
from gapcfg import LAYOUT
lay = json.load(open(LAYOUT / 'layouts-vr.json'))
rows = list(csv.DictReader(open('trinity-structs.tsv'), delimiter='\t'))
from gapcfg import ROOTS as ROOT
ALIAS = {'AIProcessManager': 'ProcessLists', 'SoundData': 'BSSoundHandle', 'BSList': 'BSSimpleList'}
def cl_layout(name, parent):
    q = f'RE::{parent}::{name}' if parent else f'RE::{ALIAS.get(name, name)}'
    if q in lay: return q, lay[q]
    for k in lay:
        if k.endswith('::' + (f'{parent}::{name}' if parent else name)) and '<' not in k: return k, lay[k]
    return None, None
def body(mod, where):
    f, ln = where.rsplit(':', 1); p = os.path.join(ROOT[mod], f)
    lines = open(p, encoding='utf-8', errors='replace').read().split('\n')
    i = int(ln) - 1; depth = 0; started = False; out = []
    for j in range(i, len(lines)):
        code = lines[j]
        c = code.split('//')[0]
        if started and depth == 1: out.append((j + 1, code))
        depth += c.count('{') - c.count('}')
        if '{' in c: started = True
        if started and depth <= 0: return out, lines[j + 1:j + 40]
    return out, []
res = []
for r in rows:
    if r['parent'] and not r['cl_def']: continue
    q, L = cl_layout(r['name'], r['parent'])
    fields, after = body(r['mod'], r['where'])
    tf = []
    for ln, code in fields:
        m = re.match(r'^\s*([^/;(){}]+?)\s+\**\s*([A-Za-z_]\w*)\s*(\[[^\]]*\])?\s*;\s*//\s*([0-9A-Fa-f]{1,4})\b', code)
        if m and not code.strip().startswith(('virtual', 'static', 'using', 'typedef', 'enum')):
            tf.append({'line': ln, 'type': m.group(1).strip(), 'name': m.group(2), 'off': int(m.group(4), 16)})
    for code in after:
        for m in re.finditer(r'offsetof\s*\(\s*' + re.escape(r['name']) + r'\s*,\s*([\w.]+)\s*\)\s*==\s*(0x[0-9A-Fa-f]+|\d+)', code):
            if not any(t['name'] == m.group(1) for t in tf): tf.append({'line': 0, 'type': '?', 'name': m.group(1), 'off': int(m.group(2), 0)})
    item = {'mod': r['mod'], 'where': r['where'], 'name': (r['parent'] + '::' if r['parent'] else '') + r['name'],
            'assert': r.get('assert', ''), 'cl': q or '', 'cl_size': L.get('size') if L else None, 'fields': []}
    for t in tf:
        hit = cov = ''
        if L:
            starts = [x for x in L['lines'] if x[0] == t['off']]
            leaf = [x for x in starts if not re.match(r'^(class|struct|union) ', x[2]) and 'vftable pointer' not in x[2] and '(base)' not in x[2] and '(primary base)' not in x[2]]
            if leaf: hit = leaf[-1][2]
            elif starts: hit = starts[-1][2]
            else:
                prev = [x for x in L['lines'] if x[0] < t['off']]
                cov = prev[-1][2] + f' @0x{prev[-1][0]:X}' if prev else ''
            if L.get('size') is not None and t['off'] >= L['size']: cov = f'за концом CommonLib (sizeof 0x{L["size"]:X})'
        item['fields'].append({**t, 'cl_at': hit, 'cl_cover': cov})
    res.append(item)
json.dump(res, open('layout-compare.json', 'w'), ensure_ascii=False, indent=0)
tot = sum(len(i['fields']) for i in res); at = sum(1 for i in res for f in i['fields'] if f['cl_at'])
print(len(res), 'structs compared;', tot, 'trinity fields with offsets;', at, 'have a CommonLib member at the same offset')
bad = [(i['name'], i['assert'], i['cl_size']) for i in res if i['assert'] and i['cl_size'] is not None]
for n, a, s in bad:
    sz = int(a.split()[0], 16)
    if sz != s: print('SIZE MISMATCH', n, 'trinity', a, 'CommonLib VR 0x%X' % s)
