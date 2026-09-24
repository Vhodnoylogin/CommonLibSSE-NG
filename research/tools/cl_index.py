#!/usr/bin/env python3
"""Index CommonLib type definitions: name -> [(qualified, file:line, kind)], plus VR sizeof from the clang dump. """
import os, re, json
from gapcfg import CL, LAYOUT, WORK
CL = str(CL)
lay = json.load(open(LAYOUT / 'layouts-vr.json'))
idx = {}
pat = re.compile(r'^\s*(?:template\s*<[^>]*>\s*)?(class|struct|union|enum(?:\s+class|\s+struct)?)\s+(?:alignas\([^)]*\)\s*)?(?:__declspec\([^)]*\)\s*)?([A-Za-z_]\w*)\s*(?:final\s*)?(?::[^;{]*)?(?:\{|$)')
upat = re.compile(r'^\s*using\s+([A-Za-z_]\w*)\s*=')
for d in ('include',):
    for dp, _, fs in os.walk(os.path.join(CL, d)):
        for f in fs:
            if not f.endswith('.h'): continue
            p = os.path.join(dp, f); rel = os.path.relpath(p, CL)
            for i, line in enumerate(open(p, encoding='utf-8', errors='replace'), 1):
                code = line.split('//')[0]
                m = pat.match(code)
                if m and not code.rstrip().endswith(';'):
                    idx.setdefault(m.group(2), []).append([f'{rel}:{i}', m.group(1)])
                m = upat.match(code)
                if m: idx.setdefault(m.group(1), []).append([f'{rel}:{i}', 'using'])
sizes = {}
for q, r in lay.items():
    base = re.sub(r'<.*', '', q).split('::')[-1]
    if 'size' in r: sizes.setdefault(base, []).append([q, r['size']])
json.dump({'defs': idx, 'sizes': sizes}, open(WORK / 'cl-types.json', 'w'))
print(len(idx), 'names;', len(sizes), 'sized')
