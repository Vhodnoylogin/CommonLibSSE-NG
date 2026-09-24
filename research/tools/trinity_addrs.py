#!/usr/bin/env python3
"""Extract every RelocAddr/RelocPtr address from HIGGS and PLANCK sources -> TSV. 
Columns: mod, file:line, name, reloc kind, template arg, VR offset (hex), guess (func/data/site/vtbl)."""
import re, os, sys, csv
from gapcfg import ROOTS
pat = re.compile(r'(?:(\w+)\s*=\s*)?Reloc(Addr|Ptr)\s*<(.+?)>\s*(\w*)\s*\(\s*(0x[0-9A-Fa-f]+)\s*\)')
rows = []
for mod, root in ROOTS.items():
    for d in ('src', 'include'):
        for dp, _, fs in os.walk(os.path.join(root, d)):
            for f in fs:
                if not f.endswith(('.cpp', '.h')): continue
                p = os.path.join(dp, f)
                for i, line in enumerate(open(p, encoding='utf-8', errors='replace'), 1):
                    code = line.split('//')[0]
                    for m in pat.finditer(code):
                        lhs, kind, targ, name, hexv = m.groups()
                        name = name or lhs or ''
                        low = (name + ' ' + targ).lower()
                        if kind == 'Ptr': g = 'data'
                        elif 'vtbl' in low or 'vtable' in low: g = 'vtbl'
                        elif re.search(r'hookloc|loc$|_loc|hooklocation|callsite|jumploc', name.lower()): g = 'site'
                        elif re.search(r'hookedfunc|originalfunc', name.lower()): g = 'func(hooked)'
                        else: g = 'func'
                        rel = os.path.relpath(p, root).replace(os.sep, '/')
                        rows.append([mod, f'{rel}:{i}', name, 'Reloc' + kind, targ.strip(), '0x%X' % int(hexv, 16), g, line.split('//', 1)[1].strip() if '//' in line else ''])
w = csv.writer(sys.stdout, delimiter='\t', lineterminator='\n')
w.writerow(['mod', 'where', 'name', 'reloc', 'type', 'vr', 'guess', 'comment'])
w.writerows(rows)
