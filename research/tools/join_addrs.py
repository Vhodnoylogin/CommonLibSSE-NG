#!/usr/bin/env python3
"""Join trinity VR offsets with CommonLib expressions and the VR Address Library. 
For each trinity address: exact CommonLib match(es); else vtable slot of a CommonLib VTABLE_*;
else address-library id (database.csv / addrlib.csv) with nearest preceding function start for call sites."""
import json, csv, sys, bisect, os
from gapcfg import VRAL
BASE = 0x140000000
cl = json.load(open('cl-addrs.json'))
by_vr = {}
for o in cl:
    if o['vr']: by_vr.setdefault(o['vr'], []).append(o)
import re as _re
def _vtname(o):
    m = _re.search(r'\b(VTABLE_\w+)', o['code'])
    return m.group(1) if m and o['file'].startswith('include/RE/Offsets_VTABLE.h') else ''
_seen_line = {}
vt = []
for o in cl:
    n = _vtname(o)
    if not n: continue
    k = _seen_line.get(o['file'], 0); _seen_line[o['file']] = k + 1   # порядок VariantID в строке = индекс в std::array
    if o['vr']: vt.append((o['vr'], f'{n}[{k}]'))
vt.sort()
vt_starts = [v for v, _ in vt]
db, al = {}, {}
with open(VRAL / 'database.csv', encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        try: db.setdefault(int(r['vr'], 16) - BASE, (int(r['id']), int(r['status'] or 0), r['name']))
        except (ValueError, TypeError): pass
with open(VRAL / 'addrlib.csv', encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        try: al.setdefault(int(r['vr'], 16) - BASE, int(r['id']))
        except (ValueError, TypeError): pass
db_sorted = sorted(db); al_sorted = sorted(al)
id_sse, id_vr, rel_by_sse = {}, {}, []
with open(VRAL / 'database.csv', encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        try:
            i, se, v, st = int(r['id']), int(r['sse'], 16), int(r['vr'], 16), int(r['status'] or 0)
        except (ValueError, TypeError):
            continue
        if st >= 2: rel_by_sse.append((se, v - se))
with open(VRAL / 'addrlib.csv', encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        try: id_sse[int(r['id'])] = int(r['sse'], 16); id_vr[int(r['id'])] = int(r['vr'], 16)
        except (ValueError, TypeError): pass
rel_by_sse.sort(); rel_se = [x[0] for x in rel_by_sse]
def plausible(i):
    # сдвиг VR-SE у id должен лежать в пределах сдвигов трёх соседей из выпуска с каждой стороны
    if i not in id_sse: return None
    se = id_sse[i]; d = id_vr[i] - se
    k = bisect.bisect_left(rel_se, se); nb = [x[1] for x in rel_by_sse[max(0, k - 3):k + 3]]
    if not nb: return None
    lo, hi = min(nb), max(nb)
    off = 0 if lo - 0x100 <= d <= hi + 0x100 else min(abs(d - lo), abs(d - hi))
    return 'ok' if off == 0 else ('disputed' if off < 0x1000 else 'false')
cl_ids = {o['id'] for o in cl if o['id'] is not None}
def prev(sorted_keys, x, lim=0x4000):
    i = bisect.bisect_right(sorted_keys, x) - 1
    return sorted_keys[i] if i >= 0 and x - sorted_keys[i] <= lim else None
rows = list(csv.DictReader(open('trinity-addrs.tsv'), delimiter='\t'))
res = []
for r in rows:
    vr = int(r['vr'], 16)
    out = dict(r)
    hits = by_vr.get(vr, [])
    out['cl'] = '; '.join(sorted({f"{h['ctx'] or h['kind']} ({h['file']})" for h in hits}))[:400]
    out['cl_n'] = len(hits)
    slot = ''
    if not hits:
        i = bisect.bisect_right(vt_starts, vr) - 1
        if i >= 0 and 0 < vr - vt[i][0] < 0x1000 and (vr - vt[i][0]) % 8 == 0:
            slot = f"{vt[i][1]}, слот {(vr - vt[i][0]) // 8} (0x{(vr - vt[i][0]) // 8:X})"
    out['vtslot'] = slot
    if vr in db:
        i, st, nm = db[vr]; out['alib'] = f"id {i} ({'выпуск' if st >= 2 else 'database.csv, status 1, не в выпуске'})"; out['alib_id'] = i; out['alib_rel'] = st >= 2
    elif vr in al:
        out['alib'] = f"id {al[vr]} (только addrlib.csv)"; out['alib_id'] = al[vr]
    else:
        p1, p2 = prev(db_sorted, vr), prev(al_sorted, vr)
        # ближайшее начало функции из обеих баз: addrlib.csv шире выпуска
        if p1 is not None and (p2 is None or p1 >= p2):
            i, st, nm = db[p1]; out['alib'] = f"внутри id {i} +0x{vr - p1:X} ({'выпуск' if st >= 2 else 'status 1, не в выпуске'})"; out['alib_id'] = i; out['alib_rel'] = st >= 2
        elif p2 is not None:
            i = al[p2]; rel = i in {v[0] for v in db.values() if v[1] >= 2}
            out['alib'] = f"внутри id {i} +0x{vr - p2:X} ({'выпуск' if rel else 'только addrlib.csv'})"; out['alib_id'] = i; out['alib_rel'] = rel
        else:
            out['alib'] = 'нет в базе'; out['alib_id'] = None
    pl = plausible(out['alib_id']) if out.get('alib_id') is not None and not out.get('alib_rel') else None
    out['plausible'] = {None: '', 'ok': 'сдвиг правдоподобен', 'disputed': 'сдвиг спорный (отличие от соседей из выпуска < 0x1000) — проверить сопоставление addrlib.csv',
                        'false': 'сдвиг ложный (вероятно VR-only код)'}[pl]
    out['id_in_cl'] = 'да' if out.get('alib_id') in cl_ids else ''
    if out['id_in_cl']:
        out['id_in_cl'] = '; '.join(sorted({f"{o['ctx']} ({o['file']})" for o in cl if o['id'] == out['alib_id']}))[:300]
    res.append(out)
json.dump(res, open('joined-addrs.json', 'w'), ensure_ascii=False)
from collections import Counter
def cat(o):
    if o['cl_n']: return 'в CommonLib тот же адрес'
    if o['vtslot']: return 'слот таблицы CommonLib'
    if o['alib'].startswith('id') and o.get('alib_rel'): return 'id в выпуске VR AL, в CommonLib нет'
    if o['alib'].startswith('id'): return 'id есть, но не в выпуске VR AL'
    if o['alib'].startswith('внутри') and o.get('alib_rel'): return 'внутри функции с id в выпуске'
    if o['alib'].startswith('внутри'): return 'внутри функции с id не в выпуске'
    return 'нет в базе'
for mod in ('HIGGS', 'PLANCK'):
    c = Counter((o['guess'].split('(')[0], cat(o)) for o in res if o['mod'] == mod)
    print('==', mod)
    for k, v in sorted(c.items()): print(f'  {k[0]:5} {k[1]:48} {v}')
