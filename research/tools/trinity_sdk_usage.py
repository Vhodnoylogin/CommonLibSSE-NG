#!/usr/bin/env python3
"""Havok SDK surface the trinity (HIGGS, PLANCK) relies on, from sources only (the SDK headers are not public). 
Outputs sdk-includes.tsv, sdk-methods.tsv (lowerCamel member calls not defined in trinity and not std),
sdk-fields.tsv (m_* member accesses), sdk-types.tsv (hk*/hkp*/hka* identifiers not defined by the trinity)."""
import os, re, csv, collections
from gapcfg import ROOTS
STD = set('''end push_back find clear size count c_str erase insert begin empty data type contains str pop_back push_front
reset assign put open close init val stack rbegin heap get wasUsed time_since_epoch emplace emplace_back front back at
lock unlock try_lock load store exchange fetch_add length substr compare replace append rfind find_first_of swap resize
reserve capacity max_size shrink_to_fit rend cbegin cend emplace_hint lower_bound upper_bound equal_range key_comp value_comp
count_if seekg tellg read write getline good fail eof flush first second what join detach joinable notify_one notify_all wait
wait_for wait_until release operator splice remove remove_if unique merge sort reverse pop_front emplace_front has_value value
value_or'''.split())
files = []
for mod, root in ROOTS.items():
    for d in ('src', 'include'):
        for dp, _, fs in os.walk(os.path.join(root, d)):
            for f in fs:
                if f.endswith(('.cpp', '.h')): files.append((mod, root, os.path.join(dp, f)))
src = {p: open(p, encoding='utf-8', errors='replace').read().split('\n') for _, _, p in files}
# names the trinity itself defines (functions/methods/fields/types) — excluded from "SDK" lists
defined = set()
for _, _, p in files:
    for line in src[p]:
        code = line.split('//')[0]
        for m in re.finditer(r'\b([A-Za-z_]\w*)\s*\([^;{}]*\)\s*(?:const)?\s*(?:override)?\s*[{;]', code):
            if not re.search(r'(->|\.)\s*' + re.escape(m.group(1)) + r'\s*\($', code[:m.end(1)] + '('): defined.add(m.group(1))
        for m in re.finditer(r'\b(?:struct|class|enum(?:\s+class)?|typedef\s+[\w:<>\s\*]+?|using)\s+([A-Za-z_]\w*)', code): defined.add(m.group(1))
inc, meth, fld, typ = [], collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list)
for mod, root, p in files:
    rel = os.path.relpath(p, root)
    for i, line in enumerate(src[p], 1):
        code = line.split('//')[0]
        m = re.search(r'#include\s*[<"]((?:Physics|Common|Animation|Behavior)[^>"]*)[>"]', code)
        if m: inc.append([mod, f'{rel}:{i}', m.group(1)])
        for m in re.finditer(r'(?:->|\.)\s*([a-z][A-Za-z0-9_]*)\s*\(', code):
            n = m.group(1)
            if n not in STD and not n.startswith('m_'): meth[n].append(f'{mod} {rel}:{i}')
        for m in re.finditer(r'(?:->|\.)\s*(m_[A-Za-z0-9_]+)', code):
            fld[m.group(1)].append(f'{mod} {rel}:{i}')
        for m in re.finditer(r'\b(hk[a-zA-Z0-9_]*|bhk[A-Z][A-Za-z0-9_]*|ahk[A-Za-z0-9_]+)\b', code):
            typ[m.group(1)].append(f'{mod} {rel}:{i}')
def dump(name, d, excl_defined):
    with open(name, 'w') as f:
        w = csv.writer(f, delimiter='\t', lineterminator='\n'); w.writerow(['name', 'uses', 'higgs', 'planck', 'first'])
        for k, v in sorted(d.items(), key=lambda kv: -len(kv[1])):
            if excl_defined and k in defined: continue
            w.writerow([k, len(v), sum(x.startswith('HIGGS') for x in v), sum(x.startswith('PLANCK') for x in v), '; '.join(v[:3])])
with open('sdk-includes.tsv', 'w') as f:
    w = csv.writer(f, delimiter='\t', lineterminator='\n'); w.writerow(['mod', 'where', 'header']); w.writerows(inc)
dump('sdk-methods.tsv', meth, True); dump('sdk-fields.tsv', fld, False); dump('sdk-types.tsv', typ, True)
print('includes', len(inc), 'unique', len({r[2] for r in inc}))
for n in ('sdk-methods.tsv', 'sdk-fields.tsv', 'sdk-types.tsv'): print(n, sum(1 for _ in open(n)) - 1)
