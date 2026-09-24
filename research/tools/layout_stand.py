#!/usr/bin/env python3
"""Стенд раскладок CommonLib без Windows: clang с раскладкой MSVC → точные смещения полей для VR/SE/AE.


Только Linux (облачная сессия). Один раз поставить:
    apt-get install -y --no-install-recommends clang mingw-w64-x86-64-dev g++-mingw-w64-x86-64-win32
Зависимости заголовков (git clone --depth 1 в DEPS): gabime/spdlog, microsoft/DirectXMath, microsoft/DirectXTK,
herumi/xbyak; openvr.h — из ValveSoftware/openvr/headers. В SimpleMath.h DirectXTK ветки master стоит
`operator<= >` (с пробелом) — стенд правит это в своей копии.

    python3 layout_stand.py [--runtime vr|se|ae] [--extra "RE::Имя" ...]

Пишет в LAYOUT: flags-<rt>.rsp, shim/, tu-<rt>.cpp, layouts-<rt>.txt, layouts-<rt>.json.
Заглушки: dxgi1_2.h (SimpleMath без windows.h), setjmp.h (конфликт mingw с intrin.h clang), prelude.h
(std::sinf и т.п., которых нет в libstdc++). Проверка стенда: все static_assert CL на размеры обязаны пройти —
иначе модель раскладки неверна и дамп не годится."""
import argparse, os, subprocess, sys, glob
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gapcfg import CL, LAYOUT

ap = argparse.ArgumentParser()
ap.add_argument('--runtime', default='vr', choices=['vr', 'se', 'ae'])
ap.add_argument('--deps', default=os.environ.get('LAYOUT_DEPS', str(Path(CL).parent / 'deps')))
ap.add_argument('--extra', nargs='*', default=[], help='классы, раскладку которых вычислить принудительно')
a = ap.parse_args()
L = Path(LAYOUT); L.mkdir(parents=True, exist_ok=True); shim = L / 'shim'; shim.mkdir(exist_ok=True)
D = Path(a.deps)
gcc = sorted(glob.glob('/usr/lib/gcc/x86_64-w64-mingw32/*-win32/include'))
clang_inc = sorted(glob.glob('/usr/lib/llvm-*/lib/clang/*/include'))
if not gcc or not clang_inc:
    sys.exit('нет mingw-w64 (win32) или clang: см. докстроку')
gcc, clang_inc = gcc[-1], clang_inc[-1]
(shim / 'dxgi1_2.h').write_text('#pragma once\n// keeps windows.h out; only what SimpleMath.h references\n'
    'enum DXGI_SCALING { DXGI_SCALING_STRETCH = 0, DXGI_SCALING_NONE = 1, DXGI_SCALING_ASPECT_RATIO_STRETCH = 2 };\n'
    'struct tagRECT { long left, top, right, bottom; };\ntypedef tagRECT RECT;\ntypedef unsigned int UINT;\n')
(shim / 'setjmp.h').write_text('#pragma once\ntypedef struct __attribute__((aligned(16))) { unsigned long long Part[2]; } _SETJMP_FLOAT128;\n'
    'typedef _SETJMP_FLOAT128 jmp_buf[16];\nextern "C" [[noreturn]] void __cdecl longjmp(jmp_buf, int);\n')
(shim / 'prelude.h').write_text('#pragma once\n#include <cfloat>\n#include <cmath>\n'
    'namespace std { using ::atan2f; using ::cosf; using ::fminf; using ::fmodf; using ::logf; using ::powf; using ::sinf; using ::sqrtf; }\n')
if not (shim / 'openvr.h').exists():
    src = D / 'openvr' / 'headers' / 'openvr.h'
    if src.exists(): (shim / 'openvr.h').write_text(src.read_text(encoding='utf-8', errors='replace'))
    else: sys.exit(f'нет openvr.h: положи его в {shim}')
sm = D / 'DirectXTK' / 'Inc' / 'SimpleMath.h'
if sm.exists():
    t = sm.read_text(encoding='utf-8', errors='replace')
    if 'operator<= >' in t: sm.write_text(t.replace('operator<= >', 'operator<=>'), encoding='utf-8')
rt = {'vr': 'ENABLE_SKYRIM_VR', 'se': 'ENABLE_SKYRIM_SE', 'ae': 'ENABLE_SKYRIM_AE'}[a.runtime]
atomics = subprocess.run(['clang', '-dM', '-E', '-x', 'c', '/dev/null'], capture_output=True, text=True).stdout
flags = ['--target=x86_64-pc-windows-msvc', '-std=c++23', '-fms-extensions', '-fms-compatibility',
         '-fdelayed-template-parsing', '-w', '-D__GNUC__=13', '-D__GNUC_MINOR__=2', '-D__GNUC_PATCHLEVEL__=0',
         '-U__SIZEOF_INT128__', '"-D__MINGW_IMPORT=extern __declspec(dllimport)"', '"-D_CRTIMP=__declspec(dllimport)"',
         '-D__MINGW32__=1', '-D__MINGW64__=1', '-D_WIN64', '-DWIN32_LEAN_AND_MEAN', '-DNOMINMAX', '-DWINVER=0x0601',
         '-D_WIN32_WINNT=0x0601', f'-D{rt}=1', '-DSPDLOG_COMPILED_LIB', '-D_INT128_DEFINED',
         '"-D__declspec(...)=__declspec(__VA_ARGS__)"', '-nostdinc++', '-nostdlibinc',
         f'-isystem {gcc}/c++', f'-isystem {gcc}/c++/x86_64-w64-mingw32', f'-isystem {gcc}/c++/backward',
         f'-isystem {shim}', f'-isystem {clang_inc}', '-isystem /usr/x86_64-w64-mingw32/include',
         f'-isystem {D}/spdlog/include', f'-isystem {D}/DirectXMath/Inc', f'-isystem {D}/DirectXTK/Inc',
         f'-isystem {D}/xbyak', f'-I{CL}/include', '-include', 'prelude.h', '-include', 'SKSE/Impl/PCH.h']
flags += [l.replace('#define ', '-D').replace(' ', '=', 1) for l in atomics.splitlines() if 'GCC_ATOMIC' in l or 'GCC_HAVE_SYNC' in l]
flags.append('-D__GCC_ATOMIC_CHAR8_T_LOCK_FREE=2')
rsp = L / f'flags-{a.runtime}.rsp'; rsp.write_text('\n'.join(flags) + '\n')
tu = L / f'tu-{a.runtime}.cpp'
tu.write_text('#include "RE/Skyrim.h"\n#include "SKSE/SKSE.h"\n' + ''.join(f'static_assert(sizeof({n}) > 0);\n' for n in a.extra))
out = L / f'layouts-{a.runtime}.txt'
r = subprocess.run(['clang++', f'@{rsp}', '-fsyntax-only', '-Xclang', '-fdump-record-layouts', str(tu)], capture_output=True, text=True)
out.write_text(r.stdout)
errs = [l for l in r.stderr.splitlines() if 'error' in l]
print(f'{len(errs)} ошибок компиляции' + (':\n' + '\n'.join(errs[:20]) if errs else ' — стенд годен'))
subprocess.run([sys.executable, str(Path(__file__).with_name('parse_layouts.py')), str(out), str(L / f'layouts-{a.runtime}.json')])
