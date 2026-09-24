#!/usr/bin/env python3
"""Сводная таблица находок разбора CommonLib из файлов findings-*.md. 

    python3 audit_summary.py <папка с findings-*.md> [verdicts.tsv] > сводка.md
verdicts.tsv (необязательно): ID<TAB>вердикт независимой проверки."""
import re, glob, os, sys, collections
d = sys.argv[1]
ver = {}
if len(sys.argv) > 2 and os.path.exists(sys.argv[2]):
    for l in open(sys.argv[2], encoding='utf-8'):
        if '\t' in l: k, v = l.rstrip('\n').split('\t', 1); ver[k] = v
AREA = {'containers': 'контейнеры, память, строки', 'papyrus': 'Papyrus и регистрации SKSE', 'gameplay': 'помощники над объектами игры',
        'math-scene': 'математика, граф сцены, Scaleform', 'rex-build': 'REX, сборка, CI', 'vr-havok': 'VR и Havok', 'core': 'адреса VR, заголовки'}
rows = []
for f in sorted(glob.glob(os.path.join(d, 'findings-*.md'))):
    key = os.path.basename(f)[9:-3]
    t = open(f, encoding='utf-8').read().split('\n')
    for i, l in enumerate(t):
        m = re.match(r'^### ([A-Z]+-\d+)\.\s+(.*)$', l)
        if not m: continue
        meta = next((x for x in t[i + 1:i + 4] if 'Вид:' in x), '')
        g = lambda k: (re.search(k + r':\s*([^;\n]+)', meta) or [None, '?'])[1].strip()
        conf = g('Уверенность').split('(')[0].strip().rstrip(';')
        imp = g('Важность'); v = ver.get(m.group(1), '')
        mm = re.search(r'важность → (\w+)', v)
        if mm: imp = f'{mm.group(1)} (была {imp})'
        rows.append((m.group(1), m.group(2).replace('|', '\\|'), g('Вид'), imp, conf, key))
order = {'высокая': 0, 'средняя': 1, 'низкая': 2}
kinds = {'ошибка': 0, 'неоптимальное': 1, 'расширение': 2}
sev = lambda r: r[3].split()[0]
rows.sort(key=lambda r: (kinds.get(r[2], 9), order.get(sev(r), 9), r[0]))
c = collections.Counter((r[2], sev(r)) for r in rows)
print(f'Всего находок: {len(rows)}.\n')
print('| вид | высокая | средняя | низкая |\n|---|---|---|---|')
for k in ('ошибка', 'неоптимальное', 'расширение'):
    print(f'| {k} | ' + ' | '.join(str(c[(k, s)]) for s in ('высокая', 'средняя', 'низкая')) + ' |')
print('\n| ID | находка | вид | важность | уверенность | проверка | файл |\n|---|---|---|---|---|---|---|')
for r in rows:
    vv = re.sub('; важность → [^;]+', '', ver.get(r[0], ''))
    print(f'| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {vv} | [{r[5]}](findings/findings-{r[5]}.md) |')
