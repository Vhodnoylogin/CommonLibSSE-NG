# Исследование CommonLibSSE-NG

Форк `alandtse/CommonLibSSE-NG` под исследование кода. Ветка `ng` не меняется; исследование лежит только в этой
папке. Объект — `ng` на коммите `a898f4698` (выпуск 9.1.0, 24.09.2026).

Два направления:

| что | файл |
|---|---|
| Общий рефакторинг: ошибки, неоптимальное, точки расширения — 134 находки, 15 высоких после независимой проверки | [library-audit.md](library-audit.md), подробности — [findings/](findings/), проверка — [verification-high.md](verification-high.md) |
| Что нужно добавить или исправить, чтобы на библиотеку можно было перевести VR-моды HIGGS и PLANCK (`adamhynek/higgs`, `adamhynek/activeragdoll`) | [trinity-improvements.md](trinity-improvements.md) |

## Как проверялось

- Каждая находка — после чтения кода: путь:строка, выдержка, сценарий, как проверено, предложение.
- Раскладки — не по комментариям смещений, а сборкой: весь `RE/Skyrim.h` собирается на Linux clang 18 с раскладкой
  записей MSVC (`--target=x86_64-pc-windows-msvc`) поверх libstdc++/mingw-w64 и трёх заглушек; `-fdump-record-layouts`
  даёт точные смещения каждого поля для выбранного рантайма ([tools/layout_stand.py](tools/layout_stand.py)).
  Все `static_assert` библиотеки на размеры в конфигурации VR проходят.
- Адреса VR — по `alandtse/skyrim_vr_address_library` (выпуск 0.270.0): «в выпуске» — строки `database.csv` со
  статусом ≥ 2, именно их `vr_address_tools.py generate` кладёт в `version-1-4-15-0.csv`.
- Ошибки контейнеров воспроизведены ASan на настоящих заголовках; id SE/AE — по `tests/REL/*.bin` самого клона.
- Все находки высокой важности пытался опровергнуть отдельный проверяющий, не автор находок.

## Инструменты (`tools/`)

Пути к исходникам задаются переменными `COMMONLIB_SRC`, `HIGGS_SRC`, `PLANCK_SRC`, `VR_ADDRLIB_SRC`; выходы пишутся в
текущую папку (`GAPS_WORK`).

    python3 tools/layout_stand.py [--runtime vr|se|ae]   # дамп раскладок → layout/layouts-<rt>.{txt,json}
    python3 tools/commonlib_addrs.py cl-addrs.json         # все адресные выражения библиотеки → VR-адрес
    python3 tools/trinity_addrs.py > trinity-addrs.tsv     # RelocAddr/RelocPtr HIGGS и PLANCK
    python3 tools/join_addrs.py && python3 tools/gaps_addr_table.py
    python3 tools/cl_index.py && python3 tools/trinity_structs.py && python3 tools/compare_layouts.py
    python3 tools/trinity_sdk_usage.py
    python3 tools/audit_summary.py . verdicts.tsv > сводка.md

`commonlib_addrs.py` + препроцессор VR-сборки — готовая CI-проверка «каждый id, попавший в VR-сборку, есть в выпуске
VR Address Library» (находка K-1).

Лицензия исследования — как у библиотеки (GPL-3.0-or-later с исключениями `EXCEPTIONS.md`).
