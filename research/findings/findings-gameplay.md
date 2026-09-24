# CommonLibSSE-NG 9.1.0 (a898f4698): ревью рукописных помощников над объектами игры

Область: тела функций в `src/RE` (Actor, TESObjectREFR, ExtraDataList, InventoryEntryData, InventoryChanges,
AIProcess, PlayerCharacter, TESDataHandler, TESForm, TESFile, TESNPC, TESFaction, Projectile, TES,
TESObjectCELL, TESContainer, BGS*/TESObject*, MagicTarget/ActiveEffect, UI) вместе с объявлениями в `include/RE`.
Мерка — `AGENTS.md` и `CLAUDE.md` клона. Клон только читался.

Как сверялись идентификаторы Address Library (находки G-2…G-6, G-12):
- `tests/REL/version-1-5-97-0.bin` (SE) и `tests/REL/versionlib-1-6-*.bin` (AE 353/629/1130/1170/1179) из самого
  клона разобраны скриптом по формату meh321. Сравнивались «подписи» соседей: разности адресов id-1→id→id+1 в SE
  и в AE. Одна и та же функция в SE и AE, как правило, даёт те же размеры соседей, а выпадающий из ряда сдвиг
  AE−SE виден сразу. Проверено 270 пар `RELOCATION_ID` в файлах области. Сдвиг выпадает из ряда только у пар,
  описанных ниже.
- VR: `database.csv`, `addrlib.csv` и `se_ae_offsets.csv` из `alandtse/skyrim_vr_address_library` (ветка main,
  скачаны 2026-09-24) и `tests/REL/version-1-4-15-0.csv` (v0.194.0) из клона.
- Уже исправлено или нет: `git log --oneline -5 -- <файл>`, `git log -S`, диффы всех 130 веток
  `origin/*` относительно `ng`. Ни одна из находок ниже не исправлена ни в `ng`, ни в какой-либо ветке.

---

### G-1. ActiveEffect::GetTargetActor и MagicTarget::GetTargetAsActor возвращают указатель внутрь Actor, а не на Actor
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено
- Где: `src/RE/A/ActiveEffect.cpp:30`, `src/RE/A/ActiveEffect.cpp:39`, `src/RE/M/MagicTarget.cpp:109`
- Код:
  ```cpp
  Actor* ActiveEffect::GetTargetActor() {
      if (target && target->MagicTargetIsActor()) {
          return reinterpret_cast<Actor*>(target);          // ActiveEffect.cpp:33
  ...
  Actor* MagicTarget::GetTargetAsActor() {
      if (MagicTargetIsActor()) {
          return reinterpret_cast<Actor*>(this);            // MagicTarget.cpp:112
  ```
- Суть и сценарий: `ActiveEffect::target` — это `MagicTarget*`, то есть указатель на подобъект `MagicTarget` внутри
  `Actor`. Этот подобъект лежит по смещению 0x98 (SE/VR/AE до 1.6.629) или 0xA0 (AE с 1.6.629):
  `include/RE/A/Actor.h:145` (`public MagicTarget, // 098, 0A0`) и
  `Actor.h:777` (`RUNTIME_CAST_ACCESSOR_VERSIONED(MagicTarget, AsMagicTarget, ..., 0x98, 0xA0)`).
  `reinterpret_cast` не вычитает это смещение, поэтому возвращается `Actor*`, который на 0x98/0xA0 байт правее
  начала объекта. Любое обращение к полям или виртуальным функциям через него читает чужую память. Пример: в хуке
  на `ActiveEffect` вызов `effect->GetTargetActor()->GetActorBase()` берёт «vtable» из поля `MagicTarget`, и
  игра падает. Ошибка задевает и саму библиотеку: `src/SKSE/RegistrationSetUnique.cpp:134` и `:176` берут
  `a_activeEffect->GetTargetActor()->GetFormID()`. Это чтение по адресу актёр+0x98+0x14, то есть мусор, поэтому
  регистрации `RegistrationSetUnique` для `ActiveEffect` либо отклоняются (formID 0), либо записываются под чужим
  ключом. Ошибку внёс коммит 197ff1691 (2022): тогда `static_cast` заменили на `reinterpret_cast`.
- Как проверено: чтение кода; смещения подобъекта взяты из `Actor.h:145,777`; `git log -S"reinterpret_cast<Actor*>(target)"`.
  Проверка в игре: сравнить `effect->GetTargetActor()` с `effect->target->GetTargetStatsObject()`. Разница составит
  0x98 или 0xA0.
- Предложение: получать актёра через движок, без арифметики с раскладкой:
  ```cpp
  auto* ref = target ? target->GetTargetStatsObject() : nullptr;
  return ref ? ref->As<Actor>() : nullptr;
  ```
  Второй вариант: вычесть смещение `AsMagicTarget()` с учётом версии (0x98/0xA0).

### G-2. InventoryEntryData::SetWorn: SE- и AE-id перепутаны местами
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено
- Где: `src/RE/I/InventoryEntryData.cpp:303`
- Код:
  ```cpp
  void InventoryEntryData::SetWorn(bool a_worn, bool a_left, bool a_deleteExtraList)
  {
      using func_t = decltype(&InventoryEntryData::SetWorn);
      static REL::Relocation<func_t> func{ RELOCATION_ID(16027, 15789) };
  ```
- Суть и сценарий: во всём файле AE-id = SE-id + 238 (15745→15983, 15757→15995, 15760→15998, 15782→16020,
  15786→16024, 15788→16026, 15797→16035). Здесь же стоит пара (16027, 15789), а 15789 + 238 = 16027, то есть
  числа просто переставлены. На AE id 15789 разрешается в 0x1401DA8E6. Адрес не выровнен на 16 байт и не может
  быть началом функции, поэтому `SetWorn` на AE почти наверняка падает. На SE id 16027 ведёт в 0x1401F1CB0: это
  вне модуля InventoryEntryData, и там вызывается чужая функция.
- Как проверено: разбор `version-1-5-97-0.bin` и `versionlib-1-6-353-0.bin` из клона. Подписи совпадают:
  SE 15788→15789→15790 даёт шаги 0x30 и 0x2A0, AE 16026→16027→16028 — те же 0x30 и 0x2A0.
  Значит SE 15789 и AE 16027 — одна и та же функция. Поиск по всему `src/include` пар с «SE-id > AE-id» для
  функций нашёл только эту пару и G-3.
- Предложение: `RELOCATION_ID(15789, 16027)`. Для VR: в `database.csv` нет строки 15789, а `addrlib.csv` даёт
  VR 0x1401E8AE0. По AGENTS.md сначала нужно влить этот id в VR address library, иначе VR упадёт на поиске id.

### G-3. Actor::RefreshEquippedActorValueCharge: AE-id взят от соседней UpdateWeaponAbility
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено (AE)
- Где: `src/RE/A/Actor.cpp:1235` (для сравнения `Actor.cpp:1503`)
- Код:
  ```cpp
  void Actor::RefreshEquippedActorValueCharge(const RE::TESForm* a_object, ...)
      static REL::Relocation<func_t> func{ RELOCATION_ID(38752, 37803) };
  ...
  void Actor::UpdateWeaponAbility(TESForm* a_weapon, ExtraDataList* a_extraData, bool a_leftHand)
      static REL::Relocation<func_t> func{ RELOCATION_ID(37803, 38752) };
  ```
- Суть и сценарий: у двух функций с одинаковой сигнатурой пары id зеркальны. SE 38752 — это функция по адресу
  0x140679000. Её AE-двойник — 39776: так в `se_ae_offsets.csv`, и подписи совпадают (SE 38751→38752→38753 даёт
  шаги 0x60 и 0x110, AE 39775→39776→39777 — те же 0x60 и 0x110). AE-id 37803 указывает на 0x1406279F0, в область
  `Character::*`, к этой функции отношения не имеет. Поэтому на AE вызов (добавлен в fdb747ba9 «Add some
  functions used in enchanting») исполняет чужую функцию с аргументами `(this, form, extraList, bool)`, и
  результат непредсказуем.
- Как проверено: разбор bin-файлов, `se_ae_offsets.csv`, `git show fdb747ba9`.
- Предложение: `RELOCATION_ID(38752, 39776)`. Для VR строка 38752 в `database.csv` есть (status 4).

### G-4. InventoryChanges: неверные AE-id у GetItemCount и SetUniqueID, два метода на одном адресе
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено (GetItemCount, SetUniqueID), вероятно (InitScripts/GenerateLeveledListChanges)
- Где: `src/RE/I/InventoryChanges.cpp:41`, `:134`, `:34`/`:176`
- Код:
  ```cpp
  static REL::Relocation<func_t> func{ RELOCATION_ID(15868, 16047) };   // GetItemCount, :41
  static REL::Relocation<func_t> func{ RELOCATION_ID(15909, 16149) };   // SendContainerChangedEvent, :120
  static REL::Relocation<func_t> func{ RELOCATION_ID(15907, 16149) };   // SetUniqueID, :134
  static REL::Relocation<func_t> func{ RELOCATION_ID(15829, 16068) };   // GenerateLeveledListChanges, :34
  static REL::Relocation<func_t> func{ RELOCATION_ID(15829, 16068) };   // InitScripts, :176
  ```
- Суть и сценарий:
  - `GetItemCount`: в модуле AE ≈ SE + 238…240. Для SE 15868 ожидается AE ≈ 16108, а стоит 16047 (сдвиг +179).
    Подписи: SE 15867→15868→15869 даёт шаги 0xB80 и 0x40; AE 16107→16108→16109 — те же 0xB80 и 0x40; у AE 16047
    шаги 0x40 и 0x20 (это 0x20-байтовая функция рядом с `GetWornMask`). На AE `GetItemCount` вызывает чужую
    функцию. Ошибка живёт с 61383c799 (2022).
  - `SetUniqueID`: AE 16149 совпадает с AE-id `SendContainerChangedEvent`, хотя SE-id у них разные (15907 и 15909).
    Подписи: SE 15906→15907 даёт шаг 0x2D0, AE 16146→16147 — тоже 0x2D0. Значит на AE `SetUniqueID` вызывает
    функцию SE 15909 с другой сигнатурой.
  - `GenerateLeveledListChanges` и `InitScripts` — два разных метода с одним адресом. Один из них назван неверно.
    `TESObjectREFR::ForceInitInventoryChanges` (`TESObjectREFR.cpp:1107`) вызывает `InitScripts`, и если по
    15829 на самом деле генерация уровневых предметов, то инициализация инвентаря повторно разворачивает LVLI.
    Какой из двух методов верен, без дизассемблера не определить.
- Как проверено: разбор bin-файлов (SE 1.5.97, AE 1.6.353); старый `include/RE/Offsets.h` (891eb5692^) уже
  содержал копипаст `SetUniqueID = SendContainerChangedEvent = TransferItemUID = 16149`.
- Предложение: `GetItemCount` → `RELOCATION_ID(15868, 16108)`, `SetUniqueID` → `RELOCATION_ID(15907, 16147)`.
  Для 15829 сверить с дизассемблером и удалить или переименовать дубликат. Попутно стоит проверить тип
  результата `GetItemCount` (`std::int16_t`): при счёте больше 32767 (например, золото) значение обрежется.

### G-5. InventoryChanges::RemoveAllItems: AE-id есть только с 1.6.1130, на AE 1.6.353…1.6.640 игра аварийно завершается
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено
- Где: `src/RE/I/InventoryChanges.cpp:113`
- Код:
  ```cpp
  void InventoryChanges::RemoveAllItems(TESObjectREFR* a_ref, TESObjectREFR* a_moveToRef, ...)
      static REL::Relocation<func_t> func{ RELOCATION_ID(15878, 441567) };
  ```
- Суть и сценарий: коммит 5cdde1d2c заменил 16118 на 441567. Id 441567 есть в `versionlib-1-6-1130/1170/1179`, но
  отсутствует в `versionlib-1-6-353` и `-629`. Там функция идёт под 16118: подписи SE 15877→15878 и AE-629
  16117→16118 совпадают (шаги 0x160 и 0x190), а в 1.6.1170 по адресу 16117+0x190 стоит уже 441567. На AE 1.6.640,
  самой популярной «даунгрейд»-версии, первый вызов `RemoveAllItems` приводит в `IDDB::id2offset` к
  `report_id_lookup_failure` (`src/REL/IDDB.cpp:29`), то есть к аварийному завершению.
- Как проверено: разбор всех `versionlib-1-6-*.bin` из `tests/REL`. Поиск по всему `src/include` AE-id, которых
  нет в 1.6.629, нашёл ещё `include/RE/B/BSScaleformExternalTexture.h:37` (443440) и
  `include/RE/B/BSWin32SystemUtility.h:45` (453511). Оба вне этой области, но ошибка та же.
- Предложение: применить уже принятый в проекте шаблон (`src/RE/S/Script.cpp:60`):
  `RELOCATION_ID(15878, AE_CHECK(SKSE::RUNTIME_SSE_1_6_1130, 16118, 441567))`.

### G-6. Помощники с id 0 на одном из рантаймов вызывают адрес 0 (IsInBleedout, IsEssentialDown и др.)
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено
- Где: `src/RE/A/Actor.cpp:1053` (IsInBleedout), `:1013` (IsEssentialDown), `:167` (CanFly), `:342` (FightsInWater),
  `:1120` (IsOnWaterTriangle), `src/RE/E/ExtraDataList.cpp:270` (GetObjectHealth) — AE-id 0;
  `src/RE/P/PlayerCharacter.cpp:125` (GetEquippedWeaponsDamage) — SE-id 0, а значит и VR
- Код:
  ```cpp
  bool Actor::IsInBleedout() const
  {
      using func_t = decltype(&Actor::IsInBleedout);
      static REL::Relocation<func_t> func{ RELOCATION_ID(48461, 0) };
      return func(this);
  }
  ```
- Суть и сценарий: `RelocationID::offset()` для id 0 возвращает 0, а `address()` тоже возвращает 0
  (`include/REL/ID.h:71-81`). `Relocation` получает `_impl = 0`, и вызов уходит на адрес 0: access violation без
  диагностики. Объявления в `Actor.h:531,555,639,644,655`, `ExtraDataList.h:206` и `PlayerCharacter.h:742` ничем
  не помечены, так что `actor->IsInBleedout()` в плагине с поддержкой AE падает на первом вызове. `IsInBleedout` и
  `IsEssentialDown` пришли в 31c570903 (2026-02), `GetEquippedWeaponsDamage` — в 9e292082d.
- Как проверено: чтение `REL/ID.h`; все id 0 в области найдены grep-ом. Кандидаты AE найдены по подписям соседей:
  SE 48458…48464 дают шаги 0x30, 0x30, 0x40, 0x20, 0x20, 0x10, AE 49449…49455 — те же 0x30, 0x30, 0x40, 0x20,
  0x20, 0x10. Отсюда кандидаты AE 49451 (IsEssentialDown) и 49452 (IsInBleedout). Это только предположение:
  по AGENTS.md его нужно подтвердить дизассемблером.
- Предложение: (1) подтвердить и проставить AE-id (для `IsInBleedout`/`IsEssentialDown` — кандидаты 49451/49452);
  (2) пока id нет — закрыть вызов проверкой, например
  `if (REL::Module::IsAE()) { SKSE::log::error(...); return false; }`, или реализовать через
  `AsActorState()->GetLifeState()`; (3) там, где id нет, исключить объявление из сборок без этого рантайма, как
  сделано для `GetWarmthRating` (`#if !defined(ENABLE_SKYRIM_VR)`).

### G-7. HasKeywordInArray и HasKeywordInList: при a_matchAll = true проверяется только первое ключевое слово
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `src/RE/T/TESObjectREFR.cpp:715`, `:729`; `src/RE/T/TESForm.cpp:78`, `:97`
- Код:
  ```cpp
  for (const auto& keyword : a_keywords) {
      hasKeyword = keyword && HasKeyword(keyword);
      if ((a_matchAll && !hasKeyword) || hasKeyword) {
          break;
      }
  }
  return hasKeyword;
  ```
- Суть и сценарий: при `a_matchAll == true` условие выхода истинно на первой же итерации при любом исходе:
  нашлось — выходим по `|| hasKeyword`, не нашлось — по `a_matchAll && !hasKeyword`. Функция возвращает
  `HasKeyword(a_keywords[0])`. Например, `HasKeywordInArray({ArmorHeavy, ArmorCuirass}, true)` на тяжёлых сапогах
  даст true. Так же ведёт себя `HasKeywordInList` через `ForEachForm`. Для пустого списка при matchAll
  возвращается false, хотя «все из пустого» — это true.
- Как проверено: чтение четырёх реализаций; `git log -S"(a_matchAll && !hasKeyword) || hasKeyword"`.
- Предложение:
  ```cpp
  if (a_matchAll) { return std::ranges::all_of(a_keywords, [&](auto* k){ return k && HasKeyword(k); }); }
  return std::ranges::any_of(a_keywords, [&](auto* k){ return k && HasKeyword(k); });
  ```
  Для списка — то же через `ForEachForm` с `kStop` при первом несовпадении.

### G-8. Actor::GetVendorFaction возвращает старое значение и при первом вызове даёт nullptr
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `src/RE/A/Actor.cpp:775`, `:784`
- Код:
  ```cpp
  auto* _vendorFaction = GetActorRuntimeData().vendorFaction;
  if (!_vendorFaction) {
      CalculateCurrentVendorFaction();
  }
  return _vendorFaction;
  ```
- Суть и сценарий: `CalculateCurrentVendorFaction` записывает результат в `runtimeData.vendorFaction`, а функция
  возвращает локальную копию, снятую до вычисления, то есть nullptr. Из-за этого `Actor::CanOfferServices()`
  (`Actor.cpp:184`) при первом вызове у торговца возвращает false. Ошибку внёс рефакторинг 95439daea (2022):
  прямое обращение к члену заменили локальной копией.
- Как проверено: чтение кода; `git show 95439daea -- src/RE/A/Actor.cpp`.
- Предложение: после вычисления заново прочитать поле: `return GetActorRuntimeData().vendorFaction;`.

### G-9. TES::ForEachCellInRange обходит одну ячейку; ForEachReference* не останавливаются по kStop
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `src/RE/T/TES.cpp:64`; `src/RE/T/TES.cpp:82-112`, `:114-162`
- Код:
  ```cpp
  if (worldPos.x < xPlus && (worldPos.x + 4096.0f) > xMinus && worldPos.y < yPlus && (worldPos.y + 4096.0f) > yMinus) {
      return a_callback(cell);                      // :64 — выход из всей функции
  }
  ...
  cell->ForEachReference([&](TESObjectREFR* a_ref) {
      return a_callback(a_ref);                     // kStop прерывает только текущую ячейку
  });
  ```
- Суть и сценарий: (1) `ForEachCellInRange` во внешнем мире возвращается после первой подходящей ячейки. Ячейка
  неба и остальные 8 ячеек сетки не посещаются. При радиусе 8192 вместо 3–9 ячеек callback получит одну.
  (2) `ForEachReference` и `ForEachReferenceInRange` игнорируют `kStop`: он прерывает обход одной ячейки, а цикл по
  сетке и ячейке неба продолжается. Типичный поиск «первой подходящей ссылки» с `return kStop` получает лишние
  вызовы и при сохранении результата «последний выигрывает» возвращает не то.
- Как проверено: чтение кода; `git log -S"return a_callback(cell);"` → d5f9c62ba.
- Предложение: в (1) заменить `return a_callback(cell);` на `a_callback(cell);`; в (2) завести флаг
  `bool stop = false;`, в лямбде выставлять его при `kStop` и после каждой ячейки выходить из циклов.

### G-10. TESObjectREFR::GetWorldLocation: у загруженной внешней ссылки space остаётся nullptr
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `src/RE/T/TESObjectREFR.cpp:665`
- Код:
  ```cpp
  if (parentCell) {
      if (parentCell->IsInteriorCell() || !parentCell->GetRuntimeData().worldSpace) {
          worldLocation.space = parentCell;
      }                                   // внешняя ячейка с миром: space не присваивается
  } else {
      ... worldLocation.space = xData->persistentCell->GetRuntimeData().worldSpace;
  ```
- Суть и сценарий: ветка без `parentCell` для внешней ячейки записывает мир, а ветка с загруженной внешней ячейкой
  оставляет `space = nullptr`. Скорее всего, при переносе декомпиляции потеряли присваивание в условии
  (`|| !(space = worldSpace)`). `BGSWorldLocation::GetDistance` сравнивает `space`. В итоге две ссылки в разных мирах
  (Тамриэль и Солстхейм) получают конечное расстояние, а загруженная и незагруженная ссылки одного мира —
  `NI_INFINITY`.
- Как проверено: чтение кода и `include/RE/B/BGSWorldLocation.h:12`; `git log -L` → 5503ba376.
- Предложение: `worldLocation.space = (parentCell->IsInteriorCell() || !ws) ? static_cast<TESForm*>(parentCell) : ws;`,
  где `ws = parentCell->GetRuntimeData().worldSpace`.

### G-11. Лёгкие плагины (ESL): LookupFormIDRaw, LookupFormID, TESFile::GetFormID и GetRawFormID считают formID неверно
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `src/RE/T/TESDataHandler.cpp:158-171`, `:136-139`; `include/RE/T/TESFile.h:74`; `src/RE/T/TESForm.cpp:159-167`
- Код:
  ```cpp
  bool isLight = rawIndex == 0xFE;
  if (isLight) { rawIndex = (a_rawFormID & 0x00FFF000) >> 12; }
  for (...) { ... if (index++ == rawIndex) {
          return (a_rawFormID & 0x00FFFFFF) | (master->compileIndex << 24); } }   // :169
  return 0;                                                                        // :172
  ...
  formID += a_localFormID;          // LookupFormID, путь SE/AE (:138) — без маски; путь VR (:134) маскирует 0xFFFFFF
  ```
- Суть и сценарий:
  1. `LookupFormIDRaw`, лёгкий мастер: биты 12–23 результата остаются равны *позиции* мастера среди лёгких
     мастеров файла, а должны содержать `master->smallFileCompileIndex`. Пусть у Foo.esp мастера Skyrim.esm и
     Bar.esl, а Bar.esl в игре имеет `smallFileCompileIndex = 5`. Тогда raw 0xFE000801 превращается в 0xFE000801
     вместо 0xFE005801, и `LookupFormRaw` находит форму чужого ESL или nullptr.
  2. Там же индекс «сам файл» (rawIndex == числу мастеров) не разрешается: возвращается 0. При этом
     `TESForm::GetRawFormID` (`TESForm.cpp:184-187`) как раз выдаёт такой индекс для собственных форм файла,
     поэтому пара `GetRawFormID` → `LookupFormRaw` не работает для обычных форм.
     Верная реализация уже есть в `TESFile::GetRuntimeFormID` (`src/RE/T/TESFile.cpp:111-125`).
  3. `LookupFormID` на SE/AE не маскирует входное значение (VR-путь маскирует `& 0xFFFFFF`). Значение с байтом
     мастера, например 0x01000D62 как в xEdit, на VR даёт верную форму, а на SE/AE — `0xFE… + 0x01000D62`, то есть
     переполнение в чужой индекс вплоть до диапазона 0xFF.
  4. `TESFile::GetFormID(formLower)` возвращает `compileIndex << 24 | lower24` и для ESL даёт 0xFE000xxx без
     `smallFileCompileIndex` (метод перенесён из CommonLibVR, где ESL нет).
  5. `GetRawFormID`, ветка VR, при установленном SkyrimVRESL считает все формы полными, хотя `LookupFormID` учитывает
     VRESL через `HasValidVRCompiledFileCollection`.
- Как проверено: разбор арифметики на примере выше; `git show a60c2ad76`; сравнение с `TESFile::GetRuntimeFormID`.
- Предложение: в `LookupFormIDRaw` для лёгкого мастера возвращать
  `0xFE000000 | (master->smallFileCompileIndex << 12) | (a_rawFormID & 0xFFF)`, а индекс «сам файл» разрешать в
  `file`. В `LookupFormID` маскировать `a_localFormID & (file->IsLight() ? 0xFFF : 0xFFFFFF)`. `TESFile::GetFormID`
  выразить через `GetPartialIndex()`/`IsLight()`.

### G-12. VR: помощники, у SE-id которых нет VR-адреса, аварийно завершают игру
- Вид: ошибка; Важность: средняя; Уверенность: вероятно (зависит от выпущенной версии VR CSV)
- Где: `src/RE/T/TESObjectREFR.cpp:79` (AddLockChange, 19110), `src/RE/E/ExtraDataList.cpp:310` (IsInventoryStackable, 11452),
  `src/RE/I/InventoryEntryData.cpp:151` (GetFavoriteExtraList, 15760), `:289` (NormalizeAndCountNonStackableExtraLists, 15797),
  `src/RE/I/InventoryChanges.cpp:64` (GetInventoryItemAt, 15866), `src/RE/T/TESContainer.cpp:87` (CollectUniqueInventoryObjects, 14390)
- Код:
  ```cpp
  InventoryEntryData* InventoryChanges::GetInventoryItemAt(std::int32_t a_index)
  {
      using func_t = decltype(&InventoryChanges::GetInventoryItemAt);
      static REL::Relocation<func_t> func{ RELOCATION_ID(15866, 16106) };
  ```
- Суть и сценарий: на VR `RELOCATION_ID` использует SE-id. Этих шести id нет ни в `database.csv` (main,
  2026-09-24), ни в `tests/REL/version-1-4-15-0.csv` (v0.194.0). Первый вызов на VR приводит к
  `report_id_lookup_failure` и аварийному завершению. Защиты `IsVR()` в функциях нет, объявления не помечены.
  Функции добавлены в августе–сентябре 2026 (9b1842bf2 «expose inventory refresh helpers», 0687032b3 «add SE IDs»).
  Это прямо нарушает правило AGENTS.md: «If a fix depends on a skyrim_vr_address_library id that has no VR
  mapping yet, say so explicitly and land that address-library PR first».
- Как проверено: сверка всех SE-id файлов области с обоими CSV; наличие guard проверено в окружающих 12 строках.
- Предложение: внести адреса в `skyrim_vr_address_library` (для 15866, 15760, 15797, 14390 VR-адрес есть в
  `sse_vr.csv`/`addrlib.csv` и требует проверки); до этого закрыть функции `if (REL::Module::IsVR())` с внятной
  ошибкой в логе или исключить их из VR-сборок.

### G-13. GetInventory и GetInventoryCount считают записи уровневых списков (TESLevItem) базового контейнера предметами
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `src/RE/T/TESObjectREFR.cpp:461-478`, `:484-492`
- Код:
  ```cpp
  container->ForEachContainerObject([&](ContainerObject& a_entry) {
      auto obj = a_entry.obj;
      if (obj && !ignore(obj) && a_filter(*obj)) {
          auto it = results.find(obj);
          if (it == results.end()) {
              results.emplace(obj, std::make_pair(a_entry.count, std::make_unique<InventoryEntryData>(obj, 0)));
  ```
- Суть и сценарий: `ContainerObject::obj` бывает `TESLevItem` (наследник `TESBoundObject`,
  `include/RE/T/TESLevItem.h:10`), и у NPC это обычное дело: `LItemBanditWeapon` и т.п. Фильтр по умолчанию
  (`DEFAULT_INVENTORY_FILTER`) пропускает всё. В результате `GetInventory()` возвращает LVLI-формы как предметы с
  положительным счётом рядом с уже развёрнутыми из них предметами, а `GetInventoryCount()` завышает итог. Кроме
  того, в карту попадают записи с суммарным счётом 0 и отрицательные, то есть предметы, которых уже нет. Обходы без
  проверки `count > 0` видят «пустые» предметы.
- Как проверено: чтение кода и иерархии `TESLevItem`. Проверка в игре: `GetInventory()` у бандита — среди ключей
  окажутся формы `FormType::LeveledItem`.
- Предложение: в проходе по базовому контейнеру пропускать `obj->Is(FormType::LeveledItem)`, а в
  `GetInventoryCount` суммировать только `count > 0`. Решение по нулевым записям задокументировать в объявлении.

### G-14. Actor::GetKiller возвращает nullptr именно для мёртвого актёра
- Вид: ошибка; Важность: средняя; Уверенность: вероятно
- Где: `src/RE/A/Actor.cpp:629`
- Код:
  ```cpp
  Actor* Actor::GetKiller() const
  {
      if (IsDead(false)) {
          return nullptr;
      }
      return GetActorRuntimeData().myKiller.get().get();
  }
  ```
- Суть и сценарий: смысл Papyrus `GetKiller` — «None, если актёр не мёртв». Здесь же выход с nullptr происходит,
  когда `IsDead(false)` истинно. Если `IsDead` при любом значении аргумента истинно для окончательно мёртвого
  актёра, функция никогда не вернёт убийцу: условие инвертировано (с первого коммита b4fa43573). Кроме того,
  возвращается сырой указатель из временного `NiPointer`, и ссылка на него освобождается до выхода из функции.
- Как проверено: чтение кода и истории. Точный смысл аргумента `IsDead(bool)` из клона не выводится. Проверка в
  игре: убить NPC (`kill` в консоли от игрока) и вызвать `GetKiller()`. Ожидается игрок, при текущем коде будет nullptr.
- Предложение: `if (!IsDead(false)) return nullptr;` после проверки в игре; возвращать `NiPointer<Actor>`.

### G-15. TESObjectREFR::MoveToNode передаёт мир самой ссылки, а не цели (MoveTo передаёт мир цели)
- Вид: ошибка; Важность: низкая; Уверенность: вероятно
- Где: `src/RE/T/TESObjectREFR.cpp:959` (сравнить с `:899`)
- Код:
  ```cpp
  MoveTo_Impl(handle, a_target->GetParentCell(), a_target->GetWorldspace(), a_target->GetPosition(), a_target->data.angle); // MoveTo, :899
  ...
  MoveTo_Impl(handle, a_target->GetParentCell(), GetWorldspace(), position, rotation);                                    // MoveToNode, :959
  ```
- Суть и сценарий: две обёртки над одной функцией движка передают разные миры: ячейку цели, но мир `this`.
  Перемещение объекта из интерьера (мир nullptr) к узлу цели во внешнем мире или между Тамриэлем и Солстхеймом
  передаёт движку несогласованную пару ячейка/мир. SKSE64 `ObjectReference.MoveToNode` берёт мир цели.
- Как проверено: сравнение вызовов внутри файла. Проверка в игре: `MoveToNode` предмета из интерьера к узлу NPC
  на улице.
- Предложение: `a_target->GetWorldspace()`, как в `MoveTo`.

### G-16. TESDataHandler::LookupForm<T> и LookupFormRaw<T> сравнивают тип точно и не находят наследников
- Вид: ошибка; Важность: низкая; Уверенность: подтверждено
- Где: `include/RE/T/TESDataHandler.h:225`, `:236`
- Код:
  ```cpp
  auto form = LookupForm(a_localFormID, a_modName);
  if (!form) { return 0; }
  return form->Is(T::FORMTYPE) ? static_cast<T*>(form) : 0;
  ```
- Суть и сценарий: `LookupForm<TESObjectREFR>(id, "Mod.esp")` для размещённого NPC (FormType `ActorCharacter`)
  возвращает nullptr. Для интерфейсных типов без собственного `FORMTYPE` (`TESBoundObject`, `MagicItem`) вызов либо
  не компилируется, либо не находит ничего. Соседний `TESForm::LookupByID<T>` (`TESForm.h:225-229`) использует
  `As<T>()`, так что поведение двух API расходится.
- Как проверено: чтение кода.
- Предложение: `return form ? form->As<T>() : nullptr;`.

### G-17. BGSDefaultObjectManager::SupportsSE: `!=` вместо `==`, VR-only объекты считаются поддержанными в SE
- Вид: ошибка; Важность: низкая; Уверенность: подтверждено
- Где: `src/RE/B/BGSDefaultObjectManager.cpp:82`
- Код:
  ```cpp
  bool BGSDefaultObjectManager::SupportsSE(DefaultObjectID a_object) noexcept
  {
      return (std::to_underlying(a_object) & 0x0000FFFF) || a_object != DefaultObjectID::kWerewolfSpell;
  }
  ```
- Суть и сценарий: у VR-only объектов SE-часть равна 0, например `kisJarlChair = MakeDefaultObjectID(0, 184)`
  (`BGSDefaultObjectManager.h:955`). Выражение даёт `0 || (kisJarlChair != kWerewolfSpell)`, то есть true, и так
  же отвечает `SupportsAE`. Исключение нужно ровно одно: `kWerewolfSpell` имеет индекс 0 в SE. `GetObject` сам
  защищён `MapIndex`, поэтому ошибка бьёт по коду, который решает по `SupportsSE/AE`.
- Как проверено: чтение кода и enum.
- Предложение: `... || a_object == DefaultObjectID::kWerewolfSpell;`.

### G-18. StringToFormType передаёт string_view::data() в _stricmp и читает за границей строки
- Вид: ошибка; Важность: низкая; Уверенность: подтверждено
- Где: `src/RE/F/FormTypes.cpp:292`
- Код:
  ```cpp
  for (auto& iter : FORM_ENUM_STRING::GetFormEnumString()) {
      if (_stricmp(iter.formString, a_formType.data()) == 0) {
  ```
- Суть и сценарий: `std::string_view` не обязан заканчиваться нулём. `StringToFormType("ARMOxyz"sv.substr(0, 4))`
  вернёт `None`, а представление без нуля в конце (срез буфера) приводит к чтению за пределами. Рядом
  `TESDataHandler::LookupModByName` делает правильно: сверяет размер и вызывает `_strnicmp`.
- Как проверено: чтение кода.
- Предложение: `a_formType.size() == std::strlen(iter.formString) && _strnicmp(iter.formString, a_formType.data(), a_formType.size()) == 0`.

### G-19. Утечки при правке списков: ExtraDataList::SetOwner и SetEncounterZone, TESNPC::AddPerk(s), TESContainer::RemoveObjectFromContainer
- Вид: ошибка; Важность: низкая; Уверенность: подтверждено
- Где: `src/RE/E/ExtraDataList.cpp:341`, `:408`; `src/RE/T/TESNPC.cpp:29`, `:44`; `src/RE/T/TESContainer.cpp:131`
- Код:
  ```cpp
  } else { Remove(xZone); }                                  // ExtraDataList.cpp:341, только отцепляет узел
  const auto newPerk = new PerkRankData(a_perk, a_rank);     // TESNPC.cpp:29
  copiedData.push_back(*newPerk);                            // копия; newPerk никто не удаляет
  copiedData.erase(copiedData.cbegin() + *index);            // TESContainer.cpp:131, ContainerObject* теряется
  ```
- Суть и сценарий: `ExtraDataList::Remove(T*)` (`ExtraDataList.h:191`) только вынимает узел из списка и не удаляет
  его, в отличие от `RemoveByType`. Поэтому каждый `SetOwner(nullptr)`/`SetEncounterZone(nullptr)` теряет объект
  extra-данных. `AddPerk`/`AddPerks` выделяют `PerkRankData` в куче только ради копирования. `RemoveObjectFromContainer`
  выбрасывает указатель на `ContainerObject` вместе с его `itemExtra`. По одной утечка мала, но эти функции
  вызываются массово при распределении (SPID/KID-подобные плагины на тысячах форм).
- Как проверено: чтение кода и шаблона `Remove`.
- Предложение: после `Remove(x)` вызывать `delete x;`; в `AddPerk(s)` использовать `copiedData.emplace_back(a_perk, a_rank)`;
  в `RemoveObjectFromContainer` удалять `ContainerObject` (вместе с `itemExtra`). Отдельно стоит задокументировать,
  что удаляется только запись с точно равным `a_count`.

### G-20. GetWornArmor, GetGoldAmount, CanPayCrimeGold и GetInventoryCount строят полную копию инвентаря на каждый вызов
- Вид: неоптимальное; Важность: средняя; Уверенность: подтверждено
- Где: `src/RE/A/Actor.cpp:809`, `:829`, `:572`; `src/RE/T/TESFaction.cpp:24`; `src/RE/T/TESObjectREFR.cpp:484`;
  `src/RE/I/InventoryChanges.cpp:47-53`
- Код:
  ```cpp
  const auto inv = GetInventory([](TESBoundObject& a_object) { return a_object.IsArmor(); }, a_noInit);
  for (const auto& [item, invData] : inv) {
      const auto& [count, entry] = invData;
      if (count > 0 && entry->IsWorn()) {
  ```
- Суть и сценарий: `GetInventory` для каждого элемента выделяет узел `std::map`, `InventoryEntryData`
  (`make_unique`) и копию `BSSimpleList` его extra-списков (`InventoryEntryData.cpp:19-26`), затем проходит
  базовый контейнер с `results.find` на каждый элемент. Всё это через `std::function` (ещё одно выделение). У NPC
  со 100 предметами один `GetWornArmor(slot)` стоит 200–300 выделений памяти, а такие вызовы часто делаются
  покадрово (видимость брони, слоты). `GetGoldAmount` строит карту ради одного объекта, а при
  неинициализированном `kGold` (вызов до kDataLoaded) разыменует nullptr: `inv.find(*gold)`, строка 585, где
  `GetObject<T>` возвращает `T**` или nullptr. Попутно: `GetWornArmor(kNone)` возвращает первую надетую броню,
  потому что `HasPartOf(kNone)` → `all(0)` = true. На VR `InventoryChanges::GetArmorInSlot` при `a_slot < 30`
  строит маску 0 и возвращает произвольную надетую броню, а при `a_slot > 61` сдвиг `1 << (a_slot - 30)` — UB.
- Как проверено: чтение кода; `REX::EnumSet::all` (`include/REX/REX/EnumSet.h:101-105`).
- Предложение: надетые предметы обходить через `InventoryChanges::VisitWornItems` (движок, без копий) или прямым
  проходом `entryList` с `IsWorn()`, без копирования; счёт одного объекта — см. G-21. В `GetGoldAmount` проверять
  `gold` на nullptr до `find`. На VR проверять `30 <= a_slot && a_slot <= 61`.

### G-21. Нет TESObjectREFR::GetItemCount(obj) без построения карты
- Вид: расширение; Важность: средняя; Уверенность: подтверждено
- Где: `include/RE/T/TESObjectREFR.h:405-409` (есть только `GetInventory*`), `include/RE/I/InventoryChanges.h:58,74`
- Код:
  ```cpp
  [[nodiscard]] InventoryItemMap  GetInventory(std::function<bool(TESBoundObject&)> a_filter, bool a_noInit = false);
  [[nodiscard]] InventoryCountMap GetInventoryCounts(std::function<bool(TESBoundObject&)> a_filter, bool a_noInit = false);
  std::int16_t                    GetItemCount(TESBoundObject* a_obj);          // InventoryChanges, AE-id неверен (G-4)
  ```
- Суть и сценарий: самая частая операция плагинов — «сколько у ссылки предмета X» (крафт, торговля, условия квестов,
  po3 Papyrus Extender, SkyUI-подобные меню). Сейчас пользователи пишут `GetInventoryCounts()[obj]`: полная карта ради
  одного числа, с ошибками G-13. Движковый `InventoryChanges::GetItemCount` на AE вызывает не ту функцию (G-4) и
  возвращает `int16`. Шаблон `InventoryChanges::GetCount(obj, filter)` (`InventoryChanges.h:74-96`) прибавляет
  базовый счёт даже тогда, когда фильтр отверг запись.
- Как проверено: grep по `include/RE` на `GetItemCount`: есть только у `PlayerCharacter` и `InventoryChanges`.
- Предложение: `std::int32_t TESObjectREFR::GetItemCount(const TESBoundObject* a_obj, bool a_noInit = true) const`:
  базовый счёт из `TESContainer::GetObjectCount` плюс `countDelta` найденной записи, без выделений. Поверх неё —
  `HasItem(obj)`.

### G-22. Нет обхода инвентаря и надетого лямбдой без копий и нет GetWornArmorInSlot через движок
- Вид: расширение; Важность: средняя; Уверенность: подтверждено
- Где: `include/RE/I/InventoryChanges.h:29-38` (`IItemChangeVisitor` — только класс с виртуальными методами), `:72`
- Код:
  ```cpp
  class IItemChangeVisitor {
      virtual ~IItemChangeVisitor() = default;                                  // 00
      virtual BSContainer::ForEachResult Visit(InventoryEntryData* a_entryData) = 0;   // 01
  ...
  void VisitWornItems(IItemChangeVisitor& visitor);
  ```
- Суть и сценарий: чтобы пройти надетые предметы без G-20, пользователю приходится объявлять класс-наследник
  `IItemChangeVisitor` с нужной раскладкой vtable. Поэтому большинство плагинов пишут свой проход `entryList` или
  берут `GetInventory`. Обход по слоту брони (`GetWornArmor`), левой и правой руке, «все надетые с ключевым
  словом» — типичная логика плагинов экипировки, трансмога и «иммерсивных» модов.
- Как проверено: чтение заголовков.
- Предложение: `template <class F> void ForEachWornItem(F&& f)`, обёртка над `VisitWornItems` с локальным
  наследником `IItemChangeVisitor`, и `ForEachInventoryEntry(F&&)` без копирования. Поверх них — `GetWornArmorInSlot`
  (замена `GetWornArmor`) и `GetWornItemsWithKeyword`.

### G-23. Нет поиска ближайшей ссылки или актёра по предикату
- Вид: расширение; Важность: низкая; Уверенность: подтверждено
- Где: `include/RE/T/TES.h:90-93`, `include/RE/P/ProcessLists.h:42-43`
- Код:
  ```cpp
  void ForEachReferenceInRange(TESObjectREFR* a_origin, float a_radius, std::function<BSContainer::ForEachResult(TESObjectREFR*)> a_callback);
  void ForAllActors(std::function<BSContainer::ForEachResult(Actor*)> a_callback);
  void ForEachHighActor(std::function<BSContainer::ForEachResult(Actor*)> a_callback);
  ```
- Суть и сценарий: «найти ближайший предмет, дверь или актёра с ключевым словом K в радиусе R» пишут почти все
  плагины взаимодействия (авто-лут, поиск стрел, «ближайший враг», телекинез в VR). Сейчас каждый обходит
  `TES::ForEachReferenceInRange` с G-9 (одна ячейка, нет раннего выхода) и сам считает квадрат расстояния.
- Как проверено: grep по `include/RE` на `Closest|Nearest|FindReferences`: есть только `FindNearestVertex` (навмеш).
- Предложение: после исправления G-9 добавить
  `NiPointer<TESObjectREFR> TES::FindClosestReference(const NiPoint3&, float a_radius, Pred&&)` и
  `ProcessLists::FindClosestActor(...)`, возвращающие `NiPointer` (не сырой указатель) и сравнивающие квадраты расстояний.

---

## Проверено и в порядке

- `ExtraDataList::RemoveByType` (`ExtraDataList.cpp:132-162`): после удаления среднего узла цикл корректно
  продолжает с `prev`; удаляемые узлы освобождаются через `delete` (у `BSExtraData` есть `TES_HEAP_REDEFINE_NEW`).
- `ExtraDataList::GetLock()`: смещение 0x10 до AE 1.6.629 и 0x18 после, `BaseExtraList::GetData/GetPresence`
  согласованы с ним. `HasType`, `GetByTypeImpl` и `GetLinkedRef` берут read-lock; `Remove` и `RemoveByType` — write-lock.
- `TESForm::LookupByID/LookupByEditorID` берут `allFormsMapLock`/`allFormsEditorIDMapLock`;
  `TESObjectCELL::ForEachReference` держит `spinLock` ячейки.
- `TESFile::GetRuntimeFormID` верно обрабатывает индекс «сам файл» и лёгкие мастера (на него стоит опереться в G-11).
  `TESFile::IsFormInMod` верна. `TESForm::GetLocalFormID` уже защищена от `GetFile(0) == nullptr`
  (ветка `fix/getlocalformid-null-file` фактически влита).
- `TESDataHandler::LookupModByName/LookupLoadedModByName/LookupLoadedLightModByName` сравнивают длину и вызывают
  `_strnicmp`. `GetLoadedMods/GetLoadedLightMods` корректно переключаются на коллекцию SkyrimVRESL.
- `InventoryEntryData`: копирующий и перемещающий конструкторы и присваивания корректно владеют `extraLists`.
  `GetSoulLevel`, `IsWorn`, `IsQuestObject` и `GetEnchantmentCharge` защищены от nullptr.
- `AIProcess`: все рукописные геттеры проверяют `high`/`middleHigh`. `Actor::GetAttackingWeapon`,
  `GetEquippedEntryData`, `GetHighProcess`, `GetMiddleHighProcess` и `GetCharController` проверяют `currentProcess`.
- `TESObjectREFR::GetHeadingAngle`: нормализация покрывает диапазон [-540, 180].
  `GetSubmergeLevel` и `GetWaterHeight` корректно сравнивают сентинел `-NI_INFINITY`.
- `TESNPC::CopyPerkRankArray`, `BGSKeywordForm::CopyKeywords`, `TESContainer::CopyObjectList` и
  `BGSIdleCollection::CopyIdles` выделяют и освобождают память игровой кучей (`RE::calloc`/`RE::free`).
  `BGSKeywordForm::AddKeywords` корректно отбрасывает дубликаты.
- `PlayerCharacter`: смещения AE 1.7.99 (`kAE1799ShiftBytes`) для `GetActorDoingPlayerCommand`, `GetGrabbedRef` и
  `IsGrabbing` согласованы между собой. Пары id `ActivatePickRef`/`ActivatePickRefVR` и
  `CheckPoisonWeapon`/`UsePoisonFromInventory` — осознанные дубликаты одной функции с одинаковой сигнатурой.
- `TESFaction`: `SetAlly`/`SetEnemy` верно отображают флаги на `FIGHT_REACTION` и сбрасывают кэш `ProcessLists`.
- Остальные 262 из 270 пар SE/AE-id в файлах области дают сдвиг AE−SE, согласованный с соседями по модулю.
  Расхождение в размерах соседей там объясняется изменением размеров функций в AE, а не перестановкой id.
- Виртуальные обёртки `RelocateVirtual` в `Actor.cpp`/`TESObjectREFR.cpp` — повторение раскладки движка. Они не
  оценивались: это вне области рукописной логики.
- Не включено по недостатку доказательств: AE-id `ExtraDataList::SetInventoryChanges` (11483, 11600) нарушает
  монотонность соседей (SE 11471→AE 11617), но подписи соседей не дают однозначного двойника. Порядок обхода
  `Actor::VisitFactions` (базовые фракции идут раньше `ExtraFactionChanges`, и снятые фракции с rank −1 видны с
  базовым рангом) требует проверки в игре.
