# Разбор CommonLibSSE-NG: ошибки, неоптимальное, точки расширения

Объект: `alandtse/CommonLibSSE-NG`, ветка `ng`, коммит `a898f4698` (выпуск 9.1.0, 24.09.2026). Разбор
24.09.2026. Направление «общий рефакторинг»; то, что нужно VR-модам HIGGS и PLANCK, — в `trinity-improvements.md`.

## Как делалось

- Семь тематических разборов, каждый своим агентом: контейнеры и память (C), Papyrus и регистрации (P), помощники над
  объектами игры (G), математика, граф сцены и Scaleform (M), REX, сборка и CI (X), VR и Havok (V), сквозное —
  адреса VR, заголовки, трамплин (K). Файлы — `findings/findings-*.md`: у каждой находки путь:строка, выдержка,
  сценарий, как проверено, предложение.
- Проверка не только чтением. Весь `RE/Skyrim.h` собран clang 18 с раскладкой MSVC в конфигурации «только VR»
  (`tools/layout_stand.py`), ошибки C воспроизведены ASan на настоящих заголовках, id Address Library
  сверены по `tests/REL/*.bin` клона и по `alandtse/skyrim_vr_address_library` (выпуск 0.270.0).
- Независимая проверка: все находки с важностью «высокая» пытался опровергнуть отдельный агент, не автор
  (`verification-high.md`); пять перепроверил главный агент. Опровергнутых нет; у 4 уточнения, у 11 важность
  снижена до средней (редкий API, утечка без порчи памяти, громкая ошибка на configure).
- Дубликаты: V-11 и K-1 — одна находка (76 функций без VR-адреса), найдена двумя разборами независимо.

## Главное: 15 ошибок высокой важности после проверки

| ID | что ломается | последствие |
|---|---|---|
| K-1 | 76 обёрток зовут SE-id, которого нет в выпуске VR Address Library, без проверки рантайма | VR-плагин, вызвавший любую, закрывает игру на первом вызове |
| V-1 | `IMenu::GetVRRuntimeData()` в VR берёт смещение 0 вместо 0x30 | `IMenu::Unk_09` пишет в vptr; `~WorldSpaceMenu` освобождает мусор |
| V-2 | `hkpWorld::RemoveEntity` объявлен как `void(hkpEntity*)`, а движок возвращает `hkBool` через скрытый указатель | сущность попадает на место буфера результата; HIGGS/PLANCK годами зовут правильно |
| V-3 | `PlayerCharacter::GetInfoRuntimeData()` в VR указывает в середину VR-блока (0x8E4 вместо 0xFE0) | `skills`, `firstPerson3D` читаются из матрицы; копирование NiPointer роняет игру |
| M-2 | `NiCamera::WorldPtToScreenPt3` в VR берёт матрицу со смещения 0 | проекция мира на экран в VR — мусор (маркеры, прицелы HUD) |
| M-1 | `NiFastATan2` теряет знак при \|y\| ≤ \|x\| (регрессия 2021) | `ToEulerAnglesXYZ`, `GetHeadingAngle`, `MoveToNode` — зеркальные углы до 45° |
| G-1 | `ActiveEffect::GetTargetActor`/`MagicTarget::GetTargetAsActor` через `reinterpret_cast` | указатель на Actor сдвинут на 0x98/0xA0; ломает и `RegistrationSetUnique` для эффектов |
| G-2 | `InventoryEntryData::SetWorn`: SE- и AE-id переставлены | на SE и VR вызывается чужая функция, на AE — невыровненный адрес |
| G-3 | `Actor::RefreshEquippedActorValueCharge`: AE-id соседней функции | на AE исполняется чужой код |
| G-4 | `InventoryChanges::GetItemCount`/`SetUniqueID`: неверные AE-id | на AE счёт предметов и идентификаторы берутся из чужих функций |
| G-5 | `InventoryChanges::RemoveAllItems`: AE-id только с 1.6.1130 | AE 1.6.353…1.6.640 (включая популярную 1.6.640) — аварийное завершение |
| G-6 | семь помощников с id 0 на одном из рантаймов (`IsInBleedout`, `IsEssentialDown`, …) | вызов адреса 0 без диагностики в Release |
| C-5 | `GString::size()` с флаговым битом; самоприсваивание — use-after-free | `size()` ≈ 2⁶³, `empty()` лжёт; порча кучи |
| P-1 | `RegistrationMap<std::string>` читает фильтр в `reserve()` | после загрузки сохранения все регистрации с фильтром молча перестают работать |
| P-3 | `SendEvent` регистраций обходит набор без блокировки | гонка с Register/Unregister из потоков Papyrus и анимации |

## Все находки

Всего находок: 134.

| вид | высокая | средняя | низкая |
|---|---|---|---|
| ошибка | 15 | 63 | 24 |
| неоптимальное | 0 | 5 | 8 |
| расширение | 2 | 12 | 5 |

| ID | находка | вид | важность | уверенность | проверка | файл |
|---|---|---|---|---|---|---|
| C-5 | `GString`: `size()` возвращает поле вместе с флаговым битом (≈2⁶³); самоприсваивание и присваивание из своего буфера — use-after-free | ошибка | высокая | подтверждено | подтверждено | [containers](findings/findings-containers.md) |
| G-1 | ActiveEffect::GetTargetActor и MagicTarget::GetTargetAsActor возвращают указатель внутрь Actor, а не на Actor | ошибка | высокая | подтверждено | подтверждено (главный агент) | [gameplay](findings/findings-gameplay.md) |
| G-2 | InventoryEntryData::SetWorn: SE- и AE-id перепутаны местами | ошибка | высокая | подтверждено | подтверждено (главный агент) | [gameplay](findings/findings-gameplay.md) |
| G-3 | Actor::RefreshEquippedActorValueCharge: AE-id взят от соседней UpdateWeaponAbility | ошибка | высокая | подтверждено | подтверждено | [gameplay](findings/findings-gameplay.md) |
| G-4 | InventoryChanges: неверные AE-id у GetItemCount и SetUniqueID, два метода на одном адресе | ошибка | высокая | подтверждено | подтверждено с поправкой | [gameplay](findings/findings-gameplay.md) |
| G-5 | InventoryChanges::RemoveAllItems: AE-id есть только с 1.6.1130, на AE 1.6.353…1.6.640 игра аварийно завершается | ошибка | высокая | подтверждено | подтверждено | [gameplay](findings/findings-gameplay.md) |
| G-6 | Помощники с id 0 на одном из рантаймов вызывают адрес 0 (IsInBleedout, IsEssentialDown и др.) | ошибка | высокая | подтверждено | подтверждено с поправкой | [gameplay](findings/findings-gameplay.md) |
| K-1 | 76 функций в VR-сборке зовут id, которого нет в выпуске VR Address Library, и не проверяют рантайм | ошибка | высокая | подтверждено | подтверждено | [core](findings/findings-core.md) |
| M-1 | `NiFastATan2` возвращает atan2 с обратным знаком при \|y\| ≤ \|x\| (регрессия 2021 г.) | ошибка | высокая | подтверждено | подтверждено (главный агент) | [math-scene](findings/findings-math-scene.md) |
| M-2 | `NiCamera::WorldPtToScreenPt3(point, …)` в VR берёт матрицу со смещения 0 объекта | ошибка | высокая | подтверждено | подтверждено | [math-scene](findings/findings-math-scene.md) |
| P-1 | RegistrationMap<std::string>: фильтр читается в reserve(), после загрузки все регистрации попадают под ключ "" | ошибка | высокая | подтверждено | подтверждено (главный агент) | [papyrus](findings/findings-papyrus.md) |
| P-3 | SendEvent обходит _handles/_regs без блокировки; PersistHandle вызывается вне блокировки | ошибка | высокая | подтверждено | подтверждено с поправкой | [papyrus](findings/findings-papyrus.md) |
| V-1 | IMenu::GetVRRuntimeData() смотрит на смещение 0 вместо 0x30, и IMenu::Unk_09 затирает vptr | ошибка | высокая | подтверждено | подтверждено | [vr-havok](findings/findings-vr-havok.md) |
| V-2 | hkpWorld::RemoveEntity: движок возвращает hkBool через скрытый указатель, а CommonLib передаёт сущность не в том регистре | ошибка | высокая | подтверждено | подтверждено | [vr-havok](findings/findings-vr-havok.md) |
| V-3 | PlayerCharacter::GetInfoRuntimeData() в VR возвращает this+0x8E4 — середину VR-блока, а не INFO (0xFE0) | ошибка | высокая | подтверждено | подтверждено | [vr-havok](findings/findings-vr-havok.md) |
| C-1 | `BSTSmallArray`: двойное освобождение в деструкторе, падение при перемещении, мусорный указатель после `shrink_to_fit` | ошибка | средняя (была высокая) | подтверждено | подтверждено | [containers](findings/findings-containers.md) |
| C-10 | `BSTScatterTable::erase(it)` возвращает `entry + 1` — при удалении в цикле пропускается элемент, переехавший в текущий слот | ошибка | средняя | подтверждено |  | [containers](findings/findings-containers.md) |
| C-11 | Итераторы `BSTScatterTable`: `it++` не двигает итератор, `const_iterator` даёт изменяемую ссылку (и ключ `BSTSet`), присваивание в пустой итератор падает на assert | ошибка | средняя | подтверждено |  | [containers](findings/findings-containers.md) |
| C-12 | `BSSimpleList`: `pop_front()` не опустошает список из одного элемента, `insert_at(0, …)` теряет узел, константный обход, `erase_after` и `resize` не компилируются | ошибка | средняя | подтверждено |  | [containers](findings/findings-containers.md) |
| C-13 | `BSString`: `== string_view` сравнивает префикс, из `string_view` получается строка без терминатора, перемещающее присваивание теряет старый буфер | ошибка | средняя | подтверждено |  | [containers](findings/findings-containers.md) |
| C-14 | `BSFixedString(string_view)` / `operator=(string_view)` передают движку только `view.data()` — подстроки становятся длиннее | ошибка | средняя | подтверждено |  | [containers](findings/findings-containers.md) |
| C-15 | `NiTMapBase`: `end()` и `++` читают `_data[_capacity]`; `erase()` и константный обход не компилируются; присваивание итераторов без `return` | ошибка | средняя | подтверждено |  | [containers](findings/findings-containers.md) |
| C-16 | `NiTNewInterface::Allocate` не конструирует элементы, а `Deallocate` вызывает для них деструкторы | ошибка | средняя | подтверждено |  | [containers](findings/findings-containers.md) |
| C-2 | `BSTScatterTable`: `value_union` безусловно конструирует и разрушает значение — двойной деструктор на каждом живом элементе | ошибка | средняя (была высокая) | подтверждено | подтверждено | [containers](findings/findings-containers.md) |
| C-3 | `BSTList::clear()` читает `node->next` после освобождения узла; `erase()` не разрушает элемент; `erase(begin())` не компилируется | ошибка | средняя (была высокая) | подтверждено | подтверждено | [containers](findings/findings-containers.md) |
| C-4 | `GArrayBase::RemoveMultipleAt`: знак «+» вместо «−» в длине сдвига — выход за буфер на 2·num элементов | ошибка | средняя (была высокая) | подтверждено | подтверждено | [containers](findings/findings-containers.md) |
| C-6 | Неявное поверхностное копирование `NiTArray`/`NiTLargeArray`/`SimpleArray` — `auto children = node->GetChildren();` освобождает детей узла | ошибка | средняя (была высокая) | подтверждено | подтверждено | [containers](findings/findings-containers.md) |
| C-7 | `BSTSmartPointer`/`NiPointer`/`GPtr`: присваивание сначала отпускает старый объект, потом читает источник — use-after-free на `p = p->next`; `BSTAutoPointer` копируется | ошибка | средняя | подтверждено |  | [containers](findings/findings-containers.md) |
| C-8 | `BSTArray::push_back(a[i])` / `insert(pos, a[i])`: ссылка на собственный элемент протухает при росте или сдвиге | ошибка | средняя | подтверждено |  | [containers](findings/findings-containers.md) |
| C-9 | `BSTArray::operator=(BSTArray&&)` переносит только указатель и ёмкость — состояние аллокатора теряется (`BSScrapArray`, `BSTSmallArray`) | ошибка | средняя | подтверждено |  | [containers](findings/findings-containers.md) |
| G-10 | TESObjectREFR::GetWorldLocation: у загруженной внешней ссылки space остаётся nullptr | ошибка | средняя | подтверждено |  | [gameplay](findings/findings-gameplay.md) |
| G-11 | Лёгкие плагины (ESL): LookupFormIDRaw, LookupFormID, TESFile::GetFormID и GetRawFormID считают formID неверно | ошибка | средняя | подтверждено |  | [gameplay](findings/findings-gameplay.md) |
| G-12 | VR: помощники, у SE-id которых нет VR-адреса, аварийно завершают игру | ошибка | средняя | вероятно |  | [gameplay](findings/findings-gameplay.md) |
| G-13 | GetInventory и GetInventoryCount считают записи уровневых списков (TESLevItem) базового контейнера предметами | ошибка | средняя | подтверждено |  | [gameplay](findings/findings-gameplay.md) |
| G-14 | Actor::GetKiller возвращает nullptr именно для мёртвого актёра | ошибка | средняя | вероятно |  | [gameplay](findings/findings-gameplay.md) |
| G-7 | HasKeywordInArray и HasKeywordInList: при a_matchAll = true проверяется только первое ключевое слово | ошибка | средняя | подтверждено |  | [gameplay](findings/findings-gameplay.md) |
| G-8 | Actor::GetVendorFaction возвращает старое значение и при первом вызове даёт nullptr | ошибка | средняя | подтверждено |  | [gameplay](findings/findings-gameplay.md) |
| G-9 | TES::ForEachCellInRange обходит одну ячейку; ForEachReference* не останавливаются по kStop | ошибка | средняя | подтверждено |  | [gameplay](findings/findings-gameplay.md) |
| K-2 | `RE/S/State.h` тянет `windows.h` в каждый плагин и вносит `DirectX::SimpleMath` в глобальное пространство имён | ошибка | средняя | подтверждено на clang + заголовках mingw-w64 |  | [core](findings/findings-core.md) |
| M-10 | `BSVisit::Traverse*`: после колбэка обход продолжает по сырому указателю — UAF при отсоединении узла | ошибка | средняя | подтверждено |  | [math-scene](findings/findings-math-scene.md) |
| M-11 | `GFxWStringBuffer`: запись по nullptr, копия без терминатора, `back()` за границей | ошибка | средняя | подтверждено |  | [math-scene](findings/findings-math-scene.md) |
| M-12 | `BSLightingShaderProperty::CopyMembers` выделяет `emissiveColor` из кучи CRT плагина | ошибка | средняя | вероятно |  | [math-scene](findings/findings-math-scene.md) |
| M-3 | `GFxValue::operator=(GFxValue&&)` не освобождает прежнее управляемое значение | ошибка | средняя (была высокая) | подтверждено | подтверждено с поправкой | [math-scene](findings/findings-math-scene.md) |
| M-4 | `NiObjectNET::AddExtraData(key, extra)`: оба условия инвертированы, метод никогда не работает | ошибка | средняя | подтверждено |  | [math-scene](findings/findings-math-scene.md) |
| M-5 | `GFxValue::DisplayInfo`: `SetYRotation` ставит флаг `kRotation`, конструкторы не ставят флагов | ошибка | средняя | подтверждено |  | [math-scene](findings/findings-math-scene.md) |
| M-6 | `GFxValue(std::string_view)` / `SetString(std::string_view)` отбрасывают длину и копят висячие указатели | ошибка | средняя | подтверждено |  | [math-scene](findings/findings-math-scene.md) |
| M-7 | `NiQuaternion::SetEulerAnglesXYZ` расходится с `NiMatrix3::SetEulerAnglesXYZ` по оси Y | ошибка | средняя | вероятно |  | [math-scene](findings/findings-math-scene.md) |
| M-8 | `Color(const NiColor&)` делит 255 на компоненту; `NiColor::ToHex` без ведущих нулей | ошибка | средняя | подтверждено |  | [math-scene](findings/findings-math-scene.md) |
| M-9 | `NiAVObject::GetMass` читает `hkpRigidBody::motion` у фантомов — выход за объект | ошибка | средняя | подтверждено |  | [math-scene](findings/findings-math-scene.md) |
| P-10 | reference_array::do_wrap записывает null-формы как нетипизированный None (исправление #337 сюда не распространено) | ошибка | средняя | подтверждено |  | [papyrus](findings/findings-papyrus.md) |
| P-11 | Unique-регистрации: ключ — текущая цель алиаса; после смены или очистки алиаса отменить регистрацию нельзя | ошибка | средняя | подтверждено |  | [papyrus](findings/findings-papyrus.md) |
| P-12 | QueueEvent хранит невладеющие аргументы: string_view/const char*, ActiveEffect*, цель a_target | ошибка | средняя | подтверждено |  | [papyrus](findings/findings-papyrus.md) |
| P-13 | Variable::SetString(std::string_view) и PackValue игнорируют длину view; const char* == nullptr приводит к крашу | ошибка | средняя | подтверждено |  | [papyrus](findings/findings-papyrus.md) |
| P-2 | SendEvent в регистрациях: MakeFunctionArguments делает new на каждый handle, и объект никто не удаляет (утечка) | ошибка | средняя (была высокая) | вероятно | подтверждено | [papyrus](findings/findings-papyrus.md) |
| P-4 | Load(): результаты ReadRecordData не проверяются, счётчики не инициализированы и не ограничены | ошибка | средняя | подтверждено |  | [papyrus](findings/findings-papyrus.md) |
| P-5 | Load() не вызывает PersistHandle для загруженных handle, а Clear/Unregister/деструктор вызывают ReleaseHandle | ошибка | средняя | подтверждено |  | [papyrus](findings/findings-papyrus.md) |
| P-6 | RegistrationMap<std::uint32_t>: любой фильтр типа uint32_t считается FormID и проходит ResolveFormID | ошибка | средняя | подтверждено |  | [papyrus](findings/findings-papyrus.md) |
| P-7 | Variable::operator=(const Variable&) после Cleanup() скалярного типа оставляет мусор в value.p, Assign() освобождает его как указатель | ошибка | средняя | подтверждено |  | [papyrus](findings/findings-papyrus.md) |
| P-8 | Array::empty() возвращает инвертированный результат | ошибка | средняя | подтверждено | подтверждено (главный агент) | [papyrus](findings/findings-papyrus.md) |
| P-9 | reference_array::operator=(const Variable*) дописывает элементы без очистки, и do_wrap пишет за границу массива ВМ | ошибка | средняя | подтверждено |  | [papyrus](findings/findings-papyrus.md) |
| V-4 | Projectile::HandleHits: аргумент слота SE 0xBE / VR 0xBF — hkpAllCdPointCollector*, а не hkpCollidable* | ошибка | средняя | подтверждено для VR практикой HIGGS |  | [vr-havok](findings/findings-vr-havok.md) |
| V-5 | PlayerCharacter::VRPlayerHandData — это VRMeleeData HIGGS/PLANCK: поле 0x10 — NiPointer<bhkWorld>, а блок 0xA0–0xAC противоречит практике | ошибка | средняя | подтверждено |  | [vr-havok](findings/findings-vr-havok.md) |
| V-6 | WorldSpaceMenu в сборке SE+AE+VR: menuNode по 0x30, а в игре — по 0x48 (это же видно через HUDMenu/MapMenu::AsWorldSpaceMenu) | ошибка | средняя | подтверждено |  | [vr-havok](findings/findings-vr-havok.md) |
| V-7 | CrosshairPickData в сборке SE+AE+VR использует VR-раскладку и для SE/AE | ошибка | средняя | подтверждено |  | [vr-havok](findings/findings-vr-havok.md) |
| V-8 | PlayerControls без VR-раскладки: в VR после togglePOVHandler идут ещё три обработчика | ошибка | средняя | вероятно |  | [vr-havok](findings/findings-vr-havok.md) |
| X-1 | TOML: значение вложенной секции читается из чужой таблицы | ошибка | средняя (была высокая) | подтверждено | подтверждено | [rex-build](findings/findings-rex-build.md) |
| X-13 | Публичный `/wd4996` глушит у всех потребителей собственные `[[deprecated]]` CommonLib, включая режим аудита | ошибка | средняя | подтверждено |  | [rex-build](findings/findings-rex-build.md) |
| X-14 | `add_commonlibsse_plugin`: нет при сборке из исходников, `EXCLUDE_FROM_ALL` ломает конфигурацию, в пути поиска мусорный каталог | ошибка | средняя | подтверждено |  | [rex-build](findings/findings-rex-build.md) |
| X-15 | xmake: проверка prebuilt запрещает `rex_json`/`rex_toml`, хотя бандл собран с ними | ошибка | средняя | подтверждено |  | [rex-build](findings/findings-rex-build.md) |
| X-17 | Цепочка поставки CI: сторонние actions на перезаписываемых тегах в заданиях с правом записи, версии инструментов не зафиксированы, бандл скачивается потребителями автоматически | ошибка | средняя | подтверждено |  | [rex-build](findings/findings-rex-build.md) |
| X-2 | `Save()` пишет только в базовый файл: при наличии пользовательского файла изменение теряется после перезапуска | ошибка | средняя (была высокая) | подтверждено | подтверждено | [rex-build](findings/findings-rex-build.md) |
| X-3 | Пакет, установленный через `cmake --install`, непригоден для `find_package(CommonLibSSE)` | ошибка | средняя (была высокая) | подтверждено | подтверждено | [rex-build](findings/findings-rex-build.md) |
| X-4 | Повреждённый базовый файл: JSON `Save` роняет процесс, TOML молча сбрасывает все настройки и затирает файл; запись не атомарна | ошибка | средняя (была высокая) | подтверждено | подтверждено | [rex-build](findings/findings-rex-build.md) |
| X-5 | JSON: одно значение неверного типа обрывает загрузку всех следующих настроек | ошибка | средняя | подтверждено |  | [rex-build](findings/findings-rex-build.md) |
| X-6 | INI: U32 ≥ 2^31 и hex-значения читаются как 2147483647; нет проверки диапазона; дробные сохраняются с 6 знаками | ошибка | средняя | подтверждено |  | [rex-build](findings/findings-rex-build.md) |
| X-7 | `SettingStore::Init` хранит `string_view`: use-after-free; пути принимаются только в ANSI | ошибка | средняя | подтверждено |  | [rex-build](findings/findings-rex-build.md) |
| X-8 | `src/REX/REX.cpp` не компилируется clang/clang-cl при любом `REX_OPTION_*`, и CI этого не ловит | ошибка | средняя | подтверждено |  | [rex-build](findings/findings-rex-build.md) |
| X-9 | `ComPtr`/`IUnknown`: `As`, `CopyTo<U>`, `QueryInterface<T>` и преобразующие присваивания не компилируются; перемещение не обнуляет источник | ошибка | средняя | подтверждено |  | [rex-build](findings/findings-rex-build.md) |
| C-17 | Перемещающий конструктор `BSTScatterTable` не компилируется — `BSTHashMap`/`BSTSet` нельзя перемещать | ошибка | низкая | подтверждено |  | [containers](findings/findings-containers.md) |
| C-18 | `BSTEventSource::AddEventSink/PrependEventSink<SinkEvent>` бесконечно рекурсирует при несовпадении типа события | ошибка | низкая | подтверждено |  | [containers](findings/findings-containers.md) |
| C-19 | `GString::BernsteinHashFunctionCIS`: знаковое сравнение переводит в «нижний регистр» и цифры/пробелы — хеш расходится с движковым | ошибка | низкая | вероятно |  | [containers](findings/findings-containers.md) |
| C-20 | Макрос `GMEMALIGN(a_sz, a_al)` берёт размер из переменной `a_count` вызывающего кода | ошибка | низкая | подтверждено |  | [containers](findings/findings-containers.md) |
| C-21 | Комментарии смещений и маска противоречат полям: `MemoryManager::alignmentForPools`, `BSStringPool::Entry::_crc`, `BucketTable::kLockIndexMask` | ошибка | низкая | подтверждено |  | [containers](findings/findings-containers.md) |
| G-15 | TESObjectREFR::MoveToNode передаёт мир самой ссылки, а не цели (MoveTo передаёт мир цели) | ошибка | низкая | вероятно |  | [gameplay](findings/findings-gameplay.md) |
| G-16 | TESDataHandler::LookupForm<T> и LookupFormRaw<T> сравнивают тип точно и не находят наследников | ошибка | низкая | подтверждено |  | [gameplay](findings/findings-gameplay.md) |
| G-17 | BGSDefaultObjectManager::SupportsSE: `!=` вместо `==`, VR-only объекты считаются поддержанными в SE | ошибка | низкая | подтверждено |  | [gameplay](findings/findings-gameplay.md) |
| G-18 | StringToFormType передаёт string_view::data() в _stricmp и читает за границей строки | ошибка | низкая | подтверждено |  | [gameplay](findings/findings-gameplay.md) |
| G-19 | Утечки при правке списков: ExtraDataList::SetOwner и SetEncounterZone, TESNPC::AddPerk(s), TESContainer::RemoveObjectFromContainer | ошибка | низкая | подтверждено |  | [gameplay](findings/findings-gameplay.md) |
| K-5 | `Trampoline::write_branch`: проверка «вызов уже заменён NOP-ами» мертва | ошибка | низкая | подтверждено |  | [core](findings/findings-core.md) |
| K-7 | `InitTrampoline` не создаёт трамплин, если SKSE не отдал интерфейс трамплина | ошибка | низкая | подтверждено |  | [core](findings/findings-core.md) |
| K-8 | `PlayerCharacter::ActivatePickRef()` без аргумента вызывает в VR функцию с аргументом устройства | ошибка | низкая | подтверждено |  | [core](findings/findings-core.md) |
| M-13 | `fixed_range_to_radians`: множитель 2π/6553.6 вместо 1/1000 для `BSInvMarker` | ошибка | низкая | вероятно |  | [math-scene](findings/findings-math-scene.md) |
| M-14 | `NiMatrix3::Inverse` объявлен, но нигде не определён | ошибка | низкая | подтверждено |  | [math-scene](findings/findings-math-scene.md) |
| P-14 | Awaitable: потерянное пробуждение и гонка на pending/continuation | ошибка | низкая | вероятно |  | [papyrus](findings/findings-papyrus.md) |
| P-15 | TraceStack: у IVirtualMachine и VirtualMachine разные аргументы по умолчанию (kError и kInfo) | ошибка | низкая | подтверждено |  | [papyrus](findings/findings-papyrus.md) |
| V-9 | NiAVObject (EXCLUSIVE_SKYRIM_VR): пропущен float unk118, хвостовые поля сдвинуты на 4 байта | ошибка | низкая | подтверждено |  | [vr-havok](findings/findings-vr-havok.md) |
| X-10 | Enum/EnumSet: `Enum::operator=(Enum<E,U2>)` без `return`, `EnumSet::operator~` не компилируется | ошибка | низкая | подтверждено |  | [rex-build](findings/findings-rex-build.md) |
| X-11 | `REX_W32_IMPORT` отбрасывает типы параметров; мелкие расхождения W32 с SDK | ошибка | низкая | подтверждено |  | [rex-build](findings/findings-rex-build.md) |
| X-12 | `COMMONLIB_ENABLE_IPO` ничего не делает: IPO не включается никогда | ошибка | низкая | подтверждено |  | [rex-build](findings/findings-rex-build.md) |
| X-16 | `prebuilt.yml`: производное от `workflow_dispatch` значение подставляется в `run:` шаблоном `${{ }}` | ошибка | низкая | подтверждено |  | [rex-build](findings/findings-rex-build.md) |
| X-18 | `ENABLE_COMMONLIBSSE_TESTING` задан только тестовому exe: у inline `report_and_error` два разных тела (нарушение ODR) | ошибка | низкая | вероятно |  | [rex-build](findings/findings-rex-build.md) |
| X-19 | `scripts/build-all-presets.cmd --clang` прячет текст ошибок компиляции | ошибка | низкая | подтверждено |  | [rex-build](findings/findings-rex-build.md) |
| G-20 | GetWornArmor, GetGoldAmount, CanPayCrimeGold и GetInventoryCount строят полную копию инвентаря на каждый вызов | неоптимальное | средняя | подтверждено |  | [gameplay](findings/findings-gameplay.md) |
| K-6 | `write_call<6>`/`write_branch<6>` возвращают адрес ячейки указателя, а `<5>` — саму функцию | неоптимальное | средняя | подтверждено |  | [core](findings/findings-core.md) |
| P-16 | BSFixedString ↔ Variable идут через string_view и каждый раз заново ищутся в пуле строк | неоптимальное | средняя | подтверждено |  | [papyrus](findings/findings-papyrus.md) |
| V-11 | Нет проверки, что SE-id обёрток есть в VR-адресной библиотеке, а тестовая копия CSV отстала на 76 выпусков | неоптимальное | средняя | подтверждено |  | [vr-havok](findings/findings-vr-havok.md) |
| X-20 | Зависимости: vcpkg ставит всё всегда, CMake не ищет зависимости REX/xbyak, xmake и CMake расходятся в версиях и флагах | неоптимальное | средняя | подтверждено |  | [rex-build](findings/findings-rex-build.md) |
| C-22 | `BSTArray`: `resize(n)` удваивает ёмкость, копирующее присваивание всегда перевыделяет, рост считается во `float` | неоптимальное | низкая | подтверждено |  | [containers](findings/findings-containers.md) |
| C-23 | `BSString()` по умолчанию всегда выделяет память в куче движка | неоптимальное | низкая | подтверждено |  | [containers](findings/findings-containers.md) |
| K-3 | Пять одинаковых копий инструкций для агентов, из них две — настоящие файлы | неоптимальное | низкая | подтверждено |  | [core](findings/findings-core.md) |
| M-15 | `BSVisit`: `std::function` передаётся по значению и копируется на каждом уровне рекурсии | неоптимальное | низкая | подтверждено |  | [math-scene](findings/findings-math-scene.md) |
| P-17 | PackHandle/BindID: повторные поиски типа и handle, временные BSFixedString из GetName() | неоптимальное | низкая | подтверждено |  | [papyrus](findings/findings-papyrus.md) |
| V-10 | hkpWorldObject::SetProperty (SE 60628) — не та функция, которой HIGGS ставит свойство (SE 60630) | неоптимальное | низкая | вероятно |  | [vr-havok](findings/findings-vr-havok.md) |
| V-12 | bhkRigidBodyT наследует bhkRigidBody приватно | неоптимальное | низкая | подтверждено |  | [vr-havok](findings/findings-vr-havok.md) |
| X-21 | CI гоняет лишнее: полная матрица на любом PR, каждый тест в ctest выполняется дважды | неоптимальное | низкая | подтверждено |  | [rex-build](findings/findings-rex-build.md) |
| V-14 | Havok/bhk-функции с VR-адресами, проверенными HIGGS/PLANCK, в CommonLib без обёрток | расширение | высокая | подтверждено для VR-адресов практикой |  | [vr-havok](findings/findings-vr-havok.md) |
| V-15 | hkpRigidBody/hkpEntity/hkpWorldObject: нет inline-аксессоров Havok SDK, которые плагины используют чаще всего | расширение | высокая | подтверждено |  | [vr-havok](findings/findings-vr-havok.md) |
| C-24 | `BSTHashMap`: нет `operator[]`, `try_emplace`, `insert_or_assign`, `count`, `at` и поиска без построения ключа | расширение | средняя | подтверждено |  | [containers](findings/findings-containers.md) |
| C-25 | Совместимость со стандартной библиотекой: `BSTList` — не range, итераторы `GArray` — не `input_iterator`, у `BSTTuple` нет `<=>`, у умных указателей нет `std::hash` | расширение | средняя | подтверждено |  | [containers](findings/findings-containers.md) |
| G-21 | Нет TESObjectREFR::GetItemCount(obj) без построения карты | расширение | средняя | подтверждено |  | [gameplay](findings/findings-gameplay.md) |
| G-22 | Нет обхода инвентаря и надетого лямбдой без копий и нет GetWornArmorInSlot через движок | расширение | средняя | подтверждено |  | [gameplay](findings/findings-gameplay.md) |
| K-4 | Раскладки VR можно проверять в CI без Windows: clang с раскладкой MSVC | расширение | средняя | подтверждено |  | [core](findings/findings-core.md) |
| M-16 | Нет математики, которую VR- и физические плагины пишут сами | расширение | средняя | подтверждено |  | [math-scene](findings/findings-math-scene.md) |
| P-18 | RegisterFunction: нельзя привязать лямбду или функтор, результат привязки теряется | расширение | средняя | подтверждено |  | [papyrus](findings/findings-papyrus.md) |
| P-19 | Нет типизированного вызова скриптовых функций из C++ | расширение | средняя | подтверждено |  | [papyrus](findings/findings-papyrus.md) |
| V-13 | PlayerCharacter (VR): 0x6BC/0x6C8 — позиция и скорость последнего удара (практика PLANCK) | расширение | средняя | подтверждено для записи практикой PLANCK |  | [vr-havok](findings/findings-vr-havok.md) |
| V-16 | VR-only функции и VR-настройки без SE-id, нужные VR-плагинам | расширение | средняя | подтверждено практикой |  | [vr-havok](findings/findings-vr-havok.md) |
| V-17 | Рэгдолл и поведение (PLANCK): структуры портированы, функций нет | расширение | средняя | подтверждено для VR-адресов практикой PLANCK |  | [vr-havok](findings/findings-vr-havok.md) |
| X-22 | Нет тестов на REX и на установленный пакет | расширение | средняя | подтверждено |  | [rex-build](findings/findings-rex-build.md) |
| C-26 | `BSSpinLock`/`BSReadWriteLock` не удовлетворяют BasicLockable/SharedLockable — `std::scoped_lock`/`std::shared_lock` неприменимы | расширение | низкая | подтверждено |  | [containers](findings/findings-containers.md) |
| C-27 | Форматирование: нет `std::formatter` для `BSFixedString`/`BSString`/`GString`; в `fmt::formatter<BSFixedString>` исключение создаётся, но не бросается | расширение | низкая | подтверждено |  | [containers](findings/findings-containers.md) |
| G-23 | Нет поиска ближайшей ссылки или актёра по предикату | расширение | низкая | подтверждено |  | [gameplay](findings/findings-gameplay.md) |
| M-17 | Граф сцены: нет шаблонного visitor, поиска по пути и доступа к полям `NiRect` | расширение | низкая | подтверждено |  | [math-scene](findings/findings-math-scene.md) |
| X-23 | Цель для юнит-тестов плагинов и минимальный пример плагина | расширение | низкая | подтверждено |  | [rex-build](findings/findings-rex-build.md) |

## Что стоит предложить автору первым (если владелец разрешит issue и запросы)

Автор принимает вклады и работает с агентами (`AGENTS.md`, `CLAUDE.md` в корне; 208 коммитов с соавтором Claude).
Правила запроса по их `AGENTS.md`: Conventional Commits, сборка всех пресетов, адреса — только проверенные по бинарнику,
id без VR-адреса — сначала запрос в `skyrim_vr_address_library`.

1. **Однострочные исправления с тестом**: M-1 (`if (offset)`), P-8 (`size() == 0`), G-2 и G-3 (id), K-5 (`uint8_t`),
   M-4 (условия `AddExtraData`), G-7 (`HasKeywordInArray`), G-17 (`==`), X-10, C-4 (знак), M-5 (флаг).
2. **VR-раскладки со сверкой по HIGGS/PLANCK и SKSE VR**: V-1, V-3, V-9, M-2, V-5 (поля `VRPlayerHandData`).
3. **Инструменты для CI**: проверка id против выпуска VR Address Library (K-1/V-11; скрипт готов —
   `tools/commonlib_addrs.py`) и стенд раскладок без Windows (K-4).
4. **Требуют Ghidra/игры до запроса**: V-2 (ABI RemoveEntity на AE), M-7 (знак кватерниона), G-4 (id 15829),
   V-8 (`PlayerControls` в VR), G-14 (`GetKiller`).
