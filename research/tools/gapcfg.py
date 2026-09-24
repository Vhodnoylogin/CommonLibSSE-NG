"""Где лежат входы сверки CommonLib ↔ троица. 

Каждый путь можно задать переменной окружения; иначе берётся первый существующий из кандидатов
(облако: клоны рядом с корнем сессии и в local/src; ПК: папки модинга). Выходы (TSV/JSON) пишутся
в рабочую папку WORK (переменная GAPS_WORK, по умолчанию текущая)."""
import os
from pathlib import Path

try:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from paths import P  # журнал проекта: tools/paths.py
    _root, _local = Path(P.root), Path(P.local)
    _modding = Path(getattr(P, 'modding_root', _root.parent))
except Exception:
    # без журнала: корень чат-проекта — первый предок с папкой local/
    _here = [Path.cwd(), *Path.cwd().parents, *Path(__file__).resolve().parents]
    _root = next((d for d in _here if (d / 'local').is_dir()), Path.cwd())
    _local = _root / 'local'; _modding = _root.parent


def _pick(env, *cands):
    if os.environ.get(env):
        return Path(os.environ[env])
    for c in cands:
        if Path(c).exists():
            return Path(c)
    return Path(cands[0])


WORK = Path(os.environ.get('GAPS_WORK', Path.cwd()))
CL = _pick('COMMONLIB_SRC', _local / 'src' / 'commonlibsse-ng', _modding / 'CommonLibVR')
HIGGS = _pick('HIGGS_SRC', _root / 'higgs', _modding / 'HIGGS')
PLANCK = _pick('PLANCK_SRC', _root / 'activeragdoll', _modding / 'PLANCK')
VRAL = _pick('VR_ADDRLIB_SRC', _local / 'src' / 'vr-addrlib', _modding / 'skyrim_vr_address_library')
LAYOUT = _pick('GAPS_LAYOUT', WORK / 'layout')
ROOTS = {'HIGGS': str(HIGGS), 'PLANCK': str(PLANCK)}
