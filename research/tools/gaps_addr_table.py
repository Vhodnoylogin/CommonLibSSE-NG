#!/usr/bin/env python3
"""Таблица разрывов по адресам троицы (строка на уникальный VR-адрес) из joined-addrs.json. 

Колонки как в gaps.md: символ | кто пользуется | есть ли в CommonLib | верен ли для VR | что дописать и куда | цена.
«Кто пользуется»: место определения и число строк src/ (без RE/offsets.*), где встречается имя."""
import json, os, re, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gapcfg import ROOTS, WORK
res = json.load(open(WORK / 'joined-addrs.json'))
src = {}
for mod, root in ROOTS.items():
    txt = []
    for dp, _, fs in os.walk(os.path.join(root, 'src')):
        for f in fs:
            if f.endswith('.cpp') and not f.startswith('offsets'):
                txt.append(open(os.path.join(dp, f), encoding='utf-8', errors='replace').read())
    src[mod] = '\n'.join(txt)
def uses(mod, name):
    return len(re.findall(r'\b' + re.escape(name) + r'\b', src[mod])) if name else 0
by = collections.OrderedDict()
for r in res:
    by.setdefault(r['vr'], []).append(r)
rows = []
for vr, rs in sorted(by.items(), key=lambda kv: int(kv[0], 16)):
    r0 = rs[0]
    names = sorted({r['name'] for r in rs if r['name']})
    who = '; '.join(f"{r['mod']} `{r['where']}` ({uses(r['mod'], r['name'])})" for r in rs)
    g = r0['guess'].split('(')[0]
    alib = r0['alib']
    if r0['cl']:
        cl = r0['cl'].replace(' (', ' `CL ').replace(')', '`')
        ok = 'тот же VR-адрес'
        todo = 'ничего: взять из CL'
        cost = '0'
    elif r0['vtslot']:
        cl = f"`{r0['vtslot']}`"
        ok = 'таблица есть в CL; слот не описан' if g == 'vtbl' else 'слот таблицы CL'
        todo = 'назвать слот виртуальной функцией в классе (или write_vfunc по индексу)'
        cost = '1–3 строки'
    else:
        cl = 'нет' + (f"; CL обёртывает id функции: {r0['id_in_cl']}" if r0.get('id_in_cl') else '')
        ok = '—'
        if alib.startswith('id') and 'выпуск' in alib and 'не в выпуске' not in alib:
            todo = 'обёртка `RELOCATION_ID(' + alib.split()[1] + ', AE)`'; cost = '3–6 строк; риск низкий'
        elif alib.startswith('id'):
            todo = f"внести VR-адрес id {alib.split()[1]} в skyrim_vr_address_library (статус ≥ 2), затем обёртка"; cost = 'PR в VR AL + 3–6 строк; риск средний (сопоставление автоматическое)'
        elif alib.startswith('внутри') and g == 'site':
            todo = f"точка внутри функции: `REL::Relocation(RELOCATION_ID({alib.split()[2]}, AE), OFFSET)` c VR-смещением {alib.split()[3]}"; cost = '2–4 строки; смещение для SE/AE своё — сверить'
        elif alib.startswith('внутри'):
            todo = f"своего id нет (ближайший id {alib.split()[2]} {alib.split()[3]}): `REL::VariantID(0, 0, {vr})` или id после проверки"; cost = '1–3 строки; только VR'
        else:
            todo = f"`REL::VariantID(0, 0, {vr})` — только VR"; cost = '1–3 строки; только VR'
    if r0.get('plausible'):
        alib += '; ' + r0['plausible']
        if 'ложный' in r0['plausible'] and not r0['cl']:
            todo = f"`REL::VariantID(0, 0, {vr})` (id из addrlib.csv не годится) " + ('— сайт вызова' if g == 'site' else '')
            cost = '1–3 строки; только VR'
    rows.append(f"| `{' / '.join(names)}` {vr} ({g}) | {who} | {cl} | {ok}; VR AL: {alib} | {todo} | {cost} |")
out = WORK / 'gaps-addresses.md'
out.write_text('| символ (VR-адрес, вид) | кто пользуется (определение, строк в src) | есть ли в CommonLib | верен ли для VR | что дописать и куда | цена |\n|---|---|---|---|---|---|\n' + '\n'.join(rows) + '\n', encoding='utf-8')
print(len(rows), 'строк →', out)
