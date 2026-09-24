#!/usr/bin/env python3
"""Release CSV = database.csv rows with status >= 2 (vr_address_tools generate, min confidence MANUAL). 
Index every address expression in CommonLib and resolve it to a SkyrimVR.exe 1.4.15 offset.
VariantID/VariantOffset carry the VR offset directly; RELOCATION_ID/RelocationID/ID carry an id that the
VR Address Library (database.csv = what the release CSV is generated from) maps to a VR address."""
import re, os, sys, csv, json
from gapcfg import CL, LAYOUT, WORK
CL = str(CL)
from gapcfg import VRAL
DB = str(VRAL)
BASE = 0x140000000
def num(s):
    s = s.strip().replace("'", '').rstrip('uUlL')
    return int(s, 16) if s.lower().startswith('0x') else int(s)
db = {}
with open(os.path.join(DB, 'database.csv'), encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        try: db[int(r['id'])] = (int(r['vr'], 16) - BASE, int(r['status'] or 0), r['name'])
        except (ValueError, TypeError): pass
al = {}
with open(os.path.join(DB, 'addrlib.csv'), encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        try: al[int(r['id'])] = int(r['vr'], 16) - BASE
        except (ValueError, TypeError): pass
N = r"(0x[0-9A-Fa-f']+|\d[\d']*)(?:[uU]?[lL]{0,2})"
pats = [
    ('VariantID', re.compile(r'REL::VariantID\s*[({]\s*' + N + r'\s*,\s*' + N + r'\s*,\s*' + N)),
    ('VariantOffset', re.compile(r'REL::VariantOffset\s*[({]\s*' + N + r'\s*,\s*' + N + r'\s*,\s*' + N)),
    ('RelocationID3', re.compile(r'REL::RelocationID\s*[({]\s*' + N + r'\s*,\s*' + N + r'\s*,\s*' + N)),
    ('RelocationID', re.compile(r'(?:RELOCATION_ID|REL::RelocationID)\s*\(\s*' + N + r'\s*,\s*' + N + r'\s*\)')),
    ('ID', re.compile(r'REL::ID\s*[({]\s*' + N + r'\s*[)}]')),
]
fn_re = re.compile(r'([A-Za-z_~][\w:~<>]*)\s*\([^;{}]*\)\s*(?:const)?\s*(?:noexcept)?\s*(?:override)?\s*(?:->\s*[\w:<>*&\s]+)?\{?\s*$')
kw = {'if', 'for', 'while', 'switch', 'return', 'sizeof', 'static_assert', 'decltype', 'alignas', 'func', 'defined'}
def context(lines, i, line):
    m = re.search(r'constexpr\s+REL::\w+\s+(\w+)\s*\(', line)
    if m: return m.group(1)
    for j in range(i, max(-1, i - 40), -1):
        m = fn_re.search(lines[j].split('//')[0])
        if m and m.group(1).split('::')[-1] not in kw: return m.group(1)
    return ''
out = []
for d in ('include', 'src'):
    for dp, _, fs in os.walk(os.path.join(CL, d)):
        for f in sorted(fs):
            if not f.endswith(('.h', '.cpp', '.inl')): continue
            p = os.path.join(dp, f); rel = os.path.relpath(p, CL)
            lines = open(p, encoding='utf-8', errors='replace').read().split('\n')
            for i, line in enumerate(lines):
                code = line.split('//')[0]
                if 'REL::' not in code and 'RELOCATION_ID' not in code: continue
                seen = set()
                for kind, pat in pats:
                    for m in pat.finditer(code):
                        if m.start() in seen: continue
                        seen.add(m.start())
                        g = [num(x) for x in m.groups()]
                        vr, how, idv, status, dbname = None, '', None, '', ''
                        if kind in ('VariantID', 'VariantOffset'):
                            vr, how = g[2], 'vr-offset'
                        else:
                            idv = g[2] if kind == 'RelocationID3' else g[0]
                            if idv in db:
                                vr, status, dbname = db[idv][0], db[idv][1], db[idv][2]
                                how = 'release' if status >= 2 else 'database.csv-status1'
                            elif idv in al: vr, how = al[idv], 'addrlib.csv-only'
                            else: how = 'no-vr-mapping'
                        out.append({'file': f'{rel}:{i+1}', 'kind': kind, 'args': [hex(x) if x > 0xFFFFF else x for x in g],
                                    'id': idv, 'vr': vr, 'how': how, 'status': status, 'dbname': dbname,
                                    'ctx': context(lines, i, line), 'code': line.strip()[:160]})
json.dump(out, open(sys.argv[1], 'w'), ensure_ascii=False)
from collections import Counter
print(len(out), 'expressions'); print(Counter((o['kind'], o['how']) for o in out))
