# CommonLibSSE-NG 9.1.0 (`ng`, a898f4698): находки по ядру, адресам VR и заголовкам

Область: сквозные вещи, которые не попали в тематические разборы: адреса функций в VR-сборке, заголовки,
которые тянет `RE/Skyrim.h`, документы для агентов. Проверялось не только чтением: весь `RE/Skyrim.h` +
`SKSE/SKSE.h` собран clang 18 с раскладкой MSVC (`--target=x86_64-pc-windows-msvc`) в конфигурации «только VR»
(`ENABLE_SKYRIM_VR=1`), все `static_assert` библиотеки прошли. Сборочный стенд:
`tools/layout_stand.py` (флаги clang, заглушки, дамп).

Итого: 8 находок — 5 ошибок, 2 неоптимальных, 1 расширение.

---

### K-1. 76 функций в VR-сборке зовут id, которого нет в выпуске VR Address Library, и не проверяют рантайм
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено (что код попадает в VR-сборку и id нет в выпуске); поведение в игре — по коду `REL/IDDB.cpp`
- Где: полный список — `k2-vr-unmapped-ids.md` рядом с этим файлом. Примеры:
  `src/RE/I/InventoryChanges.cpp:64` (`GetInventoryItemAt`, SE 15866), `src/RE/E/ExtraDataList.cpp:28`
  (`~BaseExtraList`, 11572), `src/RE/N/NiPick.cpp:24-38` (`NiPick`), `src/RE/R/Renderer.cpp:124-159`,
  `src/RE/B/BGSTerrainManager.cpp:7-89` (13 функций), `src/RE/P/PlayerCharacter.cpp:125`
  (`GetEquippedWeaponsDamage`, SE-id 0), `src/RE/B/BarterMenu.cpp:14` (SE-id 0).
- Код:
  ```cpp
  InventoryEntryData* InventoryChanges::GetInventoryItemAt(std::int32_t a_index)
  {
      using func_t = decltype(&InventoryChanges::GetInventoryItemAt);
      static REL::Relocation<func_t> func{ RELOCATION_ID(15866, 16106) };
  ```
- Суть и сценарий: в VR `RELOCATION_ID(se, ae)` берёт SE-id (`include/REL/ID.h:40-52`), а `IDDB::id2offset`
  при отсутствии id вызывает `report_id_lookup_failure` → `report_and_fail` (MessageBox + завершение процесса,
  `src/REL/IDDB.cpp:29-37`, `:175-177`). В выпуск VR Address Library попадают только строки `database.csv` со
  статусом ≥ 2 (`vr_address_tools.py generate`, `min_confidence = MANUAL`, `vr_address_tools.py:1031`).
  Из 1385 выражений `RELOCATION_ID`/`REL::ID` библиотеки 80 указывают на id вне выпуска: 57 есть только в
  `addrlib.csv` (автоматическое сопоставление, в выпуск не входит), 23 не имеют VR-соответствия вовсе. 77 из 80
  компилируются в VR-сборку (проверено препроцессором clang в конфигурации «только VR»), и только одно
  (`InventoryChanges::GetArmorInSlot`) защищено проверкой `IsVR()`. Итого 76 публичных функций: VR-плагин, вызвавший
  любую, завершает игру на первом вызове; три функции с SE-id 0 вызывают адрес 0. Это прямо противоречит правилу
  `AGENTS.md` («land that address-library PR first … aborts the game at load»). Шесть из них независимо нашёл разбор
  помощников (G-12 в `findings-gameplay.md`).
- Как проверено: скрипт `tools/commonlib_addrs.py` (все адресные выражения CL → VR через
  `skyrim_vr_address_library` 9907085, выпуск 0.270.0), затем `clang++ -E` каждого файла в конфигурации «только VR» и
  поиск `IsVR()` в 14 строках перед вызовом.
- Предложение: (1) CI-проверка: для конфигурации VR каждое `RELOCATION_ID`/`REL::ID`, попавшее в сборку, должно быть в
  выпуске VR Address Library или стоять под `IsVR()`/`#if !defined(ENABLE_SKYRIM_VR)` — скрипт уже есть, его надо
  только поставить в `main_ci.yml`; (2) для 57 id из `addrlib.csv` — запрос в `skyrim_vr_address_library` с проверкой
  в Ghidra; (3) остальные закрыть `#if !defined(ENABLE_SKYRIM_VR)`, как уже сделано у 3 функций.

### K-2. `RE/S/State.h` тянет `windows.h` в каждый плагин и вносит `DirectX::SimpleMath` в глобальное пространство имён
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено на clang + заголовках mingw-w64; для MSVC с Windows SDK — вероятно (та же цепочка `dxgi1_2.h` → `rpc.h`/`windows.h`)
- Где: `include/RE/S/State.h:9-10`; входит в `include/RE/Skyrim.h:1809` и `include/RE/R/RendererShadowState.h:11`
- Код:
  ```cpp
  #include <SimpleMath.h>
  using namespace DirectX::SimpleMath;
  ```
- Суть и сценарий: библиотека намеренно не включает `windows.h` — для этого весь `REX/W32`. Но `SimpleMath.h` на
  Windows подключает `<dxgi1_2.h>`, а тот — `rpc.h` и `windows.h`. После `#include "RE/Skyrim.h"` в плагине
  определены макросы Win32 `GetObject`, `PlaySound`, `SendMessage`, `CreateEvent`, `GetMessage` и др. Проверка:
  `dom->GetObject<RE::SpellItem>(RE::DEFAULT_OBJECT::kWerewolfSpell)` после `RE/Skyrim.h` даёт
  «no member named 'GetObjectA' in 'RE::BGSDefaultObjectManager'». Без `NOMINMAX` в MSVC добавятся макросы
  `min`/`max`. Внутри библиотеки ошибка не видна: `.cpp`, вызывающие `GetObject<>` (`src/RE/T/TutorialMenu.cpp:26`,
  `src/RE/A/Actor.cpp:584`), `State.h` не подключают. Второе: `using namespace` в заголовке переносит в глобальное
  пространство `Vector2/3/4`, `Matrix`, `Quaternion`, `Color`, `Plane`, `Ray`, `Rectangle`, `Viewport` во всех плагинах
  (`Rectangle` к тому же совпадает с функцией GDI из того же `windows.h`).
- Как проверено: сборка `tu-win.cpp` на стенде: с настоящим `dxgi1_2.h` (mingw) — ошибка выше, с заглушкой без
  `windows.h` — собирается. `grep -rn '#undef' include` — обходов нет. Строку ввёл bb1c57585 (2023-07-24).
- Предложение: в `State.h` подключать `<DirectXMath.h>` (без `windows.h`), SimpleMath перенести в `.cpp`; убрать
  `using namespace` из заголовка (писать `DirectX::SimpleMath::Matrix`); тест-потребитель, вызывающий `GetObject<>`
  после `RE/Skyrim.h` без `NOMINMAX`/`NOGDI`.

### K-3. Пять одинаковых копий инструкций для агентов, из них две — настоящие файлы
- Вид: неоптимальное; Важность: низкая; Уверенность: подтверждено
- Где: `CLAUDE.md`, `.claude/CLAUDE.md` (обычные файлы, blob `a761f5af`), `COPILOT.md`, `.cursorrules`, `.factory/AGENTS.md`
  (символьные ссылки, режим 120000); `AGENTS.md` — отдельный документ
- Суть и сценарий: пять путей с одинаковым содержимым (549 строк, md5 `98c65109…`). Два из них — самостоятельные копии и
  разойдутся при первой правке одной из них. Символьные ссылки при клоне на Windows без `core.symlinks=true` становятся
  файлами с текстом пути, и Copilot/Cursor получают строку `CLAUDE.md` вместо инструкции.
- Как проверено: `git ls-files -s`, `md5sum`.
- Предложение: один источник (`AGENTS.md` + `CLAUDE.md`), остальные — короткие файлы «см. AGENTS.md» или генерация в
  `maintenance.yml`.

### K-4. Раскладки VR можно проверять в CI без Windows: clang с раскладкой MSVC
- Вид: расширение; Важность: средняя; Уверенность: подтверждено (стенд работает)
- Где: стенд `tools/layout_stand.py`; дамп — `layouts-vr.txt` (8910 записей)
- Суть и сценарий: весь `RE/Skyrim.h` собирается на Linux clang 18 с `--target=x86_64-pc-windows-msvc`
  (раскладка записей MSVC) поверх libstdc++/mingw-w64 и трёх заглушек (`dxgi1_2.h`, `setjmp.h`, `prelude.h`); все
  `static_assert` на размеры, действующие в конфигурации VR, проходят. `-fdump-record-layouts` выдаёт точные смещения каждого поля в VR — то, что
  сейчас восстанавливается по комментариям `// 0x18`. Сверка с независимыми описаниями HIGGS и PLANCK: 43 из 43
  `static_assert` на размер совпали. Это готовая основа для CI-джоба «раскладки VR/SE/AE по комментариям и
  `static_assert`» и для машинной сверки комментариев смещений с фактом.
- Предложение: вынести стенд в `scripts/layout-dump` и джоб CI; проверять, что комментарий `// XX` у поля совпадает с
  фактическим смещением в каждом рантайме.

### K-5. `Trampoline::write_branch`: проверка «вызов уже заменён NOP-ами» мертва
- Вид: ошибка; Важность: низкая; Уверенность: подтверждено
- Где: `include/SKSE/Trampoline.h:144-147`
- Код:
  ```cpp
  const auto isNop = *reinterpret_cast<std::int8_t*>(a_src) == 0x90;
  const auto func = isNop ? 0 : nextOp + *disp;
  ```
- Суть и сценарий: `std::int8_t` со значением байта 0x90 равен −112, а литерал `0x90` — `int` 144, поэтому
  сравнение всегда ложно. Функция, добавленная коммитом 2056f5957 («return null when patching call that was replaced
  with nop slide», 2024-11-10), не работает: если другой плагин уже заменил вызов NOP-ами, `write_call<5>` вернёт
  «прежнюю цель» `nextOp + 0x90909090` — мусорный адрес, и вызов «оригинала» из перехвата уйдёт в никуда.
- Как проверено: чтение; правила продвижения целых. Нашёл разбор перехватов для троицы (``).
- Предложение: `*reinterpret_cast<const std::uint8_t*>(a_src) == 0x90`; тест с NOP-площадкой.

### K-6. `write_call<6>`/`write_branch<6>` возвращают адрес ячейки указателя, а `<5>` — саму функцию
- Вид: неоптимальное; Важность: средняя; Уверенность: подтверждено
- Где: `include/SKSE/Trampoline.h:141-158`; тест `tests/SKSE/Trampoline.test.cpp:32` возврат не проверяет
- Суть и сценарий: для `E8 rel32` значение `nextOp + disp` — цель вызова, а для `FF 15 [rip+disp32]` — адрес
  ячейки, где цель лежит. Одинаковая сигнатура с разным смыслом: `_orig = trampoline.write_call<6>(a, hook);
  _orig(...)` исполняет данные. Сейчас это держится на знании пользователей (`*(uintptr_t*)ret`) и нигде не описано.
- Предложение: не меняя смысла старой функции (правило AGENTS.md о минимальной правке), добавить
  `write_call_resolved<6>` или документировать возврат; тест, что вызов возвращённого значения для `<5>` и
  разыменованного для `<6>` попадает в прежнюю цель.

### K-7. `InitTrampoline` не создаёт трамплин, если SKSE не отдал интерфейс трамплина
- Вид: ошибка; Важность: низкая; Уверенность: подтверждено (по коду)
- Где: `src/SKSE/API.cpp:136-148`
- Код:
  ```cpp
  if (const auto intfc = GetTrampolineInterface()) {
      if (const auto mem = intfc->AllocateFromBranchPool(info.trampolineSize)) trampoline.set_trampoline(mem, info.trampolineSize);
      else trampoline.create(info.trampolineSize);
  }                                   // интерфейса нет -> трамплин пуст
  ```
- Суть и сценарий: при `SKSE::Init(..., {.trampoline = true})` и отсутствии `kTrampoline` (старый SKSE, чужой загрузчик)
  трамплин остаётся пустым, а первый `write_call` падает в `report_and_fail` («Failed to handle allocation request»,
  `src/SKSE/Trampoline.cpp:161-165`). SKSE VR 2.00.12 интерфейс даёт (`PluginAPI.h`: `kInterface_Trampoline`), так что
  на текущих рантаймах это запас прочности, а не авария. HIGGS такой случай обрабатывает сам (`src/main.cpp:105-114`).
- Предложение: `else trampoline.create(info.trampolineSize);` и для ветки без интерфейса.

### K-8. `PlayerCharacter::ActivatePickRef()` без аргумента вызывает в VR функцию с аргументом устройства
- Вид: ошибка; Важность: низкая; Уверенность: подтверждено (сигнатура VR — по имени в VR Address Library, статус 3)
- Где: `src/RE/P/PlayerCharacter.cpp:33-38` (против `:40-45` `ActivatePickRefVR(VR_DEVICE)`); `skyrim_vr_address_library/database.csv:1014`
- Суть и сценарий: обе обёртки зовут один id 39471. В VR у функции есть второй аргумент
  `VRControls::VRDevice a_device` (0x1406CBCE0, «ActivatePickRef_1406A9F90 (PlayerCharacter* a_this, VRControls::VRDevice a_device)»).
  `ActivatePickRef()` на VR передаёт в EDX то, что там осталось; при значении вне 0–2 движок индексирует массивы
  `CrosshairPickData` за границей. Защиты `IsVR()` нет.
- Предложение: в `ActivatePickRef()` на VR вызывать `ActivatePickRefVR(VR_DEVICE::kRightController)` или
  запретить вызов (`assert`/лог).
