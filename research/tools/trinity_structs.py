#!/usr/bin/env python3
"""Engine structs the trinity describes by hand in include/RE/*.h, with their size asserts and the CommonLib match. """
import os, re, json, csv, sys
from gapcfg import ROOTS
cl = json.load(open('cl-types.json'))
rows = []
for mod, root in ROOTS.items():
    d = os.path.join(root, 'include', 'RE')
    for f in sorted(os.listdir(d)):
        if not f.endswith('.h'): continue
        p = os.path.join(d, f); lines = open(p, encoding='utf-8', errors='replace').read().split('\n')
        stack = []  # (name, depth)
        depth = 0
        asserts = {}
        for i, line in enumerate(lines, 1):
            code = line.split('//')[0]
            for m in re.finditer(r'static_assert\s*\(\s*sizeof\s*\(\s*([\w:]+)\s*\)\s*==\s*(0x[0-9A-Fa-f]+|\d+)', code):
                asserts.setdefault(m.group(1).split('::')[-1], []).append((int(m.group(2), 0), i))
            m = re.match(r'^\s*(?:template\s*<[^>]*>\s*)?(class|struct|union)\s+(?:alignas\([^)]*\)\s*)?([A-Za-z_]\w*)\s*(?::\s*([^{;]*))?\s*(\{|$)', code)
            if m and not code.rstrip().endswith(';'):
                parent = stack[-1][0] if stack else ''
                rows.append({'mod': mod, 'where': f'include/RE/{f}:{i}', 'name': m.group(2), 'parent': parent, 'bases': (m.group(3) or '').strip()})
                stack.append([m.group(2), depth, False])
            depth += code.count('{') - code.count('}')
            if stack and not stack[-1][2] and depth > stack[-1][1]:
                stack[-1][2] = True
            while stack and stack[-1][2] and depth <= stack[-1][1]:
                stack.pop()
        for r in rows:
            if r['mod'] == mod and r['where'].startswith(f'include/RE/{f}:') and r['name'] in asserts:
                r['assert'] = ', '.join(f'0x{s:X} (:{ln})' for s, ln in asserts[r['name']])
from gapcfg import LAYOUT
lay = json.load(open(LAYOUT / 'layouts-vr.json'))
ALIAS = {'AIProcessManager': 'ProcessLists', 'SoundData': 'BSSoundHandle', 'BSList': 'BSSimpleList', 'ActorProcessManager': 'AIProcess',
         'ContainerChanges': 'InventoryChanges', 'ActorProcess': 'AIProcess'}
def nested_match(parent, n):
    ks = [k for k in lay if k.endswith(f'::{parent}::{n}')]
    if ks: return [[k, 'VR 0x%X' % lay[k].get('size', 0)] for k in ks[:2]]
    pdefs = cl['defs'].get(parent, [])
    pfiles = {d[0].split(':')[0] for d in pdefs}
    return [[d[0], d[1]] for d in cl['defs'].get(n, []) if d[0].split(':')[0] in pfiles]
out = []
for r in rows:
    if r['parent']:
        nm = nested_match(r['parent'], r['name'])
        r['cl_def'] = '; '.join(' '.join(x) for x in nm)
        r['cl_vr_size'] = ''
        out.append(r); continue
    if r['name'] in ALIAS and not cl['defs'].get(r['name']):
        a = ALIAS[r['name']]
        r['cl_def'] = '; '.join(d[0] + f' (как {a})' for d in cl['defs'].get(a, [])[:2])
        r['cl_vr_size'] = '; '.join(f'{q}=0x{s:X}' for q, s in cl['sizes'].get(a, [])[:2])
        out.append(r); continue
    n = r['name']
    alt = n.split('__')[-1] if '__' in n else n
    defs = cl['defs'].get(n, []) or ([d + ['(как ' + n.replace('__', '::').rstrip(':') + ')'] for d in cl['defs'].get(alt, [])] if alt != n else [])
    sz = cl['sizes'].get(n, [])
    r['cl_def'] = '; '.join(' '.join([d[0]] + d[2:]) for d in defs[:3])
    r['cl_vr_size'] = '; '.join(f'{q}=0x{s:X}' for q, s in sz[:3])
    out.append(r)
w = csv.DictWriter(open('trinity-structs.tsv', 'w'), fieldnames=['mod', 'where', 'name', 'parent', 'bases', 'assert', 'cl_def', 'cl_vr_size'], delimiter='\t', lineterminator='\n')
w.writeheader(); w.writerows(out)
names = {}
for r in out: names.setdefault((r['parent'] + '::' if r['parent'] else '') + r['name'], set()).add(r['mod'])
has = {}
for r in out: has.setdefault((r['parent'] + '::' if r['parent'] else '') + r['name'], []).append(bool(r['cl_def']))
top = [r for r in out if not r['parent']]
print('struct defs', len(out), '(top-level', len(top), ') unique names', len(names),
      'both mods', sum(1 for v in names.values() if len(v) == 2))
print('unique names with CommonLib def', sum(1 for n in has if any(has[n])), 'without', sum(1 for n in has if not any(has[n])))
