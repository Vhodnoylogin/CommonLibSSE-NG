# CommonLibSSE-NG 9.1.0 глазами VR-плагинов: сверка с HIGGS и PLANCK

Объект: `alandtse/CommonLibSSE-NG`, ветка `ng`, коммит `a898f4698` (9.1.0).
Сторона практики: `adamhynek/higgs` (HIGGS) и `adamhynek/activeragdoll` (PLANCK); пути ниже — от корней их репозиториев. Оба плагина только для VR 1.4.15 и используют сырые VR-смещения `RelocAddr<>(0x…)`. Поля `PlayerCharacter`/`Actor`/`BSOpenVR` у них берутся из заголовков SKSE VR 2.00.12 (`skse64/GameReferences.h`, `GameInput.h`, `NiObjects.h`, `PluginAPI.h` дистрибутива SKSE VR).

## Источники и методика

- **Смещения CommonLib взяты из дампа clang** (`-fdump-record-layouts`, раскладка MSVC):
  - только VR: `layouts-vr.txt` стенда `layout_stand.py` (ENABLE_SKYRIM_VR=1);
  - SE+AE+VR («all», SKYRIM_CROSS_VR): те же флаги стенда плюс `-DENABLE_SKYRIM_SE=1 -DENABLE_SKYRIM_AE=1`. Единственная ошибка компиляции — `ImageSpaceManager.h:517` (`-Winvalid-constexpr`), на раскладки она не влияет.
  - В дампе смещения десятичные, ниже переведены в hex.
- **Адреса VR.** CSV есть локально в двух видах:
  1. `tests/REL/version-1-4-15-0.csv` в клоне CommonLib — релиз VR Address Library **v0.194.0**, 13 502 id.
  2. Свежий клон `alandtse/skyrim_vr_address_library` @ `9907085` (релиз **0.270.0**, 2026-09-24). Из него использованы `database.csv` (источник релизных CSV, 18 544 id) и `addrlib.csv` (аналитическое сопоставление SE→VR, 139 817 строк).
  - Для адресов HIGGS/PLANCK, которых нет в `database.csv`, SE-id предсказывался **по дельтам**. Брался ближайший VR-адрес с известным SE-id, и тот же сдвиг применялся в SE-библиотеке 1.5.97 (`tests/REL/version-1-5-97-0.bin`, расшифрована по алгоритму `IDDB::unpack_file`). Все предсказания, которые есть в `addrlib.csv`, с ним совпали: 60552/60554/60556/60558, 60629/60630, 42826/42828/42836, 68836, 76247/76258/76268.
- Проверка исправлений: `git log --oneline -5 -- <файл>` и просмотр файла на всех 131 удалённых ветках (`git show <ветка>:<файл>`).

---

### V-1. IMenu::GetVRRuntimeData() смотрит на смещение 0 вместо 0x30, и IMenu::Unk_09 затирает vptr
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено (код + дамп clang)
- Где: `include/RE/I/IMenu.h:121-145` (VR_RUNTIME_DATA и аксессор), `include/RE/I/IMenu.h:84-87,156-160`; `src/RE/I/IMenu.cpp:97-103`; `src/RE/W/WorldSpaceMenu.cpp:19-21, 81-91`
- Код:
  ```cpp
  // IMenu.h:130-135
  // Returns nullptr on SE/AE; uses absolute VR offset so it works in cross-VR builds too.
  [[nodiscard]] inline VR_RUNTIME_DATA* GetVRRuntimeData() noexcept {
      if SKYRIM_REL_VR_CONSTEXPR (REL::Module::IsVR()) {
          return &REL::RelocateMember<VR_RUNTIME_DATA>(this, 0x0, 0x0);
  // IMenu.cpp:98-101
  void IMenu::Unk_09(UI_MENU_Unk09 a_unk) {
      if (auto* vrData = GetVRRuntimeData()) { vrData->unk30 = a_unk; }
  ```
- Суть и сценарий: в VR `RelocateMember<T>(this, 0, 0)` даёт `this + 0`.
  - Дамп clang (VR), `IMenu`: `FxDelegateHandler` 0x00–0x0F (vptr и счётчик ссылок), `unk30` @0x30, `unk34` @0x34, `menuName` @0x38, sizeof 0x40.
  - `VR_RUNTIME_DATA` = {unk30 +0, unk34 +4, menuName +8}. Должно быть `this+0x30+{0,4,8}`, а реально `this+0x00+{0,4,8}`: сдвиг на −0x30.
  - `Unk_09` — виртуальный слот 09 во всех сборках с ENABLE_SKYRIM_VR (IMenu.h:84-87).
  - Меню плагина, унаследованное от `RE::IMenu` без своего `Unk_09`, в VR при вызове движком `vtbl[9]` пишет `kNone` (0) в младшие 4 байта vptr. Следующий виртуальный вызов уходит в мусор, игра падает.
  - Деструктор `WorldSpaceMenu` вызывает `~BSFixedString()` на `this+8`, где лежит счётчик ссылок. `MessageMatchesMenu` сравнивает имя меню с тем же мусором.
- Как проверено:
  - код и дамп `layouts-vr.txt` (IMenu);
  - состояние (0x0, 0x0) держится с `5e5417e35` (2024-07-27, «add GetVRRuntimeData for IMenu»); `18d6c1011` (2026-07-31, «safe VR/AE runtime-data accessors») сохранил ноль;
  - во всех ветках, где есть файл, стоит `(this, 0x0, 0x0)`.
- Предложение:
  - `RelocateMember<VR_RUNTIME_DATA>(this, 0x30, 0x30)` внутри IsVR-ветки;
  - под EXCLUSIVE_SKYRIM_VR добавить `static_assert(offsetof(IMenu, unk30) == 0x30)`;
  - тест в `tests/REL/RuntimeDataAccessors.test.cpp`: `(char*)&m->GetVRRuntimeData()->menuName - (char*)m == 0x38`.

### V-2. hkpWorld::RemoveEntity: движок возвращает hkBool через скрытый указатель, а CommonLib передаёт сущность не в том регистре
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено (практика HIGGS и PLANCK + статус 4 в VR-библиотеке)
- Где:
  - CommonLib `include/RE/H/hkpWorld.h:91-96`;
  - HIGGS `include/RE/offsets.h:110`, `src/hand.cpp:621-622, 800-801`, `src/RE/offsets.cpp:83`;
  - PLANCK `include/RE/offsets.h:150`, `src/RE/offsets.cpp:110`;
  - VR-библиотека `database.csv:1608`.
- Код:
  ```cpp
  // CommonLib hkpWorld.h:91-95
  inline void RemoveEntity(hkpEntity* a_entity) {
      using func_t = decltype(&hkpWorld::RemoveEntity);
      static REL::Relocation<func_t> func{ RELOCATION_ID(60493, 61305) };
      return func(this, a_entity);
  // PLANCK offsets.h:150 / HIGGS hand.cpp:621-622
  typedef hkBool(*_hkpWorld_RemoveEntity)(hkpWorld *world, hkBool *ret, hkpEntity *entity);
  hkBool ret; hkpWorld_RemoveEntity(world->world, &ret, handBody->hkBody);
  // database.csv:1608
  60493,0x140a76450,0x140ab0e50,4,void hkpWorld::RemoveEntity(hkpEntity* a_entity)
  ```
- Суть и сценарий:
  - В Havok 2010.2 функция объявлена как `hkBool hkpWorld::removeEntity(hkpEntity*)`.
  - MSVC x64 для нестатического метода, возвращающего класс, передаёт буфер результата скрытым вторым аргументом (RDX), а сущность уходит в R8.
  - HIGGS и PLANCK вызывают VR 0xAB0E50 именно так — (world, &ret, entity) — и это годами работает. Если бы сущность была в RDX, их вызов удалял бы адрес стековой переменной.
  - CommonLib объявляет `void`, поэтому `REL::invoke` зовёт функцию как свободную: RCX=this, RDX=a_entity, R8=мусор.
  - Движок запишет hkBool в первый байт сущности (младший байт vptr `hkpEntity`) и попытается удалить объект по мусорному R8.
  - SE-id 60493 → VR 0xAB0E50 (database.csv, статус 4 = побайтно идентично SE) совпадает с адресом HIGGS и PLANCK. Значит, то же соглашение действует в SE, а по общей реализации Havok, вероятно, и в AE.
- Как проверено:
  - код обеих сторон и database.csv;
  - предсказание по дельтам (якоря 60502 @0xAB2180 и 60504 @0xAB2780) дало тот же id;
  - во всех 93 ветках с этим файлом осталось `inline void RemoveEntity(hkpEntity* a_entity)`, включая `origin/feat/hkpworld-removeentity` — исходную ветку этой функции.
- Предложение:
  - явная сигнатура со скрытым буфером: `using func_t = std::uint8_t*(*)(hkpWorld*, std::uint8_t*, hkpEntity*); std::uint8_t r{}; func(this, &r, a_entity); return r != 0;` (возвращать `bool`);
  - Ghidra по SE 0x140A76450: читается ли сущность из R8;
  - проверка в игре (e2e).

### V-3. PlayerCharacter::GetInfoRuntimeData() в VR возвращает this+0x8E4 — середину VR-блока, а не INFO (0xFE0)
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено (дамп clang + STATIC_ASSERT в SKSE VR)
- Где: `include/RE/P/PlayerCharacter.h:1097` (против `:1101`); SKSE VR `GameReferences.h:707,709,749-750`
- Код:
  ```cpp
  // PlayerCharacter.h:1097, 1101
  RUNTIME_MEMBER_ACCESSOR_VERSIONED(INFO_RUNTIME_DATA, GetInfoRuntimeData, SKSE::RUNTIME_SSE_1_6_629, 0x8E4, 0x8E4, REL::VersionShift(0x8EC, …));
  VR_ONLY_POINTER_ACCESSOR(VR_INFO_RUNTIME_DATA, GetVRInfoRuntimeData, 0xFE0);
  // SKSE VR GameReferences.h:749-750
  STATIC_ASSERT(offsetof(PlayerCharacter, firstPersonSkeleton) == 0xFF0);
  STATIC_ASSERT(offsetof(PlayerCharacter, skills) == 0x10B0);
  ```
- Суть и сценарий: VR-смещение аксессора равно SE-смещению (0x8E4).
  - Дамп clang (VR PlayerCharacter): 0x8E4 — `firstPersonLagMaxDownAngle`, 0x8EC–0x90F — `NiMatrix3 viewStateIdentity1`, 0x9A8 — `unk9A8[16]`.
  - В `INFO_RUNTIME_DATA` (pack 4, sizeof 0x13C): `firstPerson3D` +0x0C, `lastRiddenMount` +0x30, `skills` +0xCC.
  - `GetInfoRuntimeData().firstPerson3D` → 0x8E4+0x0C = **0x8F0**, внутри матрицы. Float читается как NiPointer, при копировании растёт «счётчик» по мусорному адресу, игра падает.
  - `.skills` → 0x8E4+0xCC = **0x9B0**, мусор.
  - В VR на самом деле `skills` @0x10B0 и `firstPerson3D` @0xFF0 (дамп: VR_INFO с 0xFE0; SKSE VR STATIC_ASSERT).
  - Макрос RUNTIME_DATA_ACCESSOR_EX при VR=0 хотя бы срабатывает assert-ом. Здесь VR-смещение ненулевое, поэтому нет ни assert, ни nullptr — данные молча читаются не оттуда.
- Как проверено:
  - дамп;
  - `git log -L1097,1097`: VR=0x8E4 держится с `1fc569596` (2026-01-21) и не тронут ни в `b105ce17a` (исправление VR-раскладки, 2026-09-01), ни в `15c399d7f`;
  - на всех ветках VR=0x8E4;
  - в самой библиотеке вызовов нет — это ловушка для потребителей;
  - `scripts/check-vr-runtime-data.ps1` ищет только пары GetRuntimeData/GetVRRuntimeData и этот аксессор не ловит.
- Предложение: сделать `GetInfoRuntimeData()` доступным только на SE/AE (nullptr или assert в VR). Добавить полевые аксессоры по образцу `RUNTIME_DATA_FIELD_ACCESSOR`: `GetSkills()`, `GetFirstPerson3D()`, `GetLastRiddenMount()` выбирают INFO или VR_INFO.

### V-4. Projectile::HandleHits: аргумент слота SE 0xBE / VR 0xBF — hkpAllCdPointCollector*, а не hkpCollidable*
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено для VR практикой HIGGS (для SE вероятно: та же функция)
- Где:
  - CommonLib `include/RE/P/Projectile.h:230`, `src/RE/P/Projectile.cpp:152-155`, `include/RE/C/ConeProjectile.h:44`, `include/RE/Offsets_VTABLE.h:2775, 2788`;
  - HIGGS `src/hooks.cpp:104-105, 108-116, 176-183, 1457-1461`.
- Код:
  ```cpp
  // CommonLib Projectile.h:230
  SKYRIM_REL_VR_VIRTUAL bool HandleHits(hkpCollidable* a_collidable);   // Projectile.cpp: RelocateVirtual(0xBE, 0xBF)
  // HIGGS hooks.cpp:104-105, 108, 115
  static RelocPtr<_Projectile_UpdateImpactFromCollector> MissileProjectile_UpdateImpactFromCollector_vtbl(0x16FE4F0);
  static RelocPtr<_Projectile_UpdateImpactFromCollector> ArrowProjectile_UpdateImpactFromCollector_vtbl(0x16F99A0);
  bool Projectile_UpdateImpactFromCollector_Hook(Projectile *_this, hkpAllCdPointCollector *collector, …)
      for (hkpRootCdPoint &point : collector->getHits()) { … point.m_rootCollidableB = …; }
  ```
- Суть и сценарий:
  - База VR-таблицы `VTABLE_MissileProjectile` = 0x16FDEF8, `VTABLE_ArrowProjectile` = 0x16F93A8 (Offsets_VTABLE.h).
  - Слоты HIGGS: (0x16FE4F0 − 0x16FDEF8)/8 = **0xBF** и (0x16F99A0 − 0x16F93A8)/8 = **0xBF** — ровно тот слот, который CommonLib отдаёт `HandleHits` в VR.
  - HIGGS в этом хуке обходит `collector->getHits()` и переписывает `m_rootCollidableB`. На этом построен его «блок снарядов оружием», работающий в игре.
  - В `hkpCollidable` (0x70 байт) массива попаданий нет, так что при типе из CommonLib хук HIGGS падал бы.
  - Для потребителей CommonLib переопределение или хук `HandleHits` получает неверно типизированный аргумент.
- Как проверено: код обеих сторон, VTABLE-базы CommonLib. Сигнатура не менялась с `0af8b16a2` (2022); на всех ветках `HandleHits(hkpCollidable*)`.
- Предложение: `virtual bool HandleHits(hkpAllCdPointCollector* a_collector)` (у HIGGS имя `UpdateImpactFromCollector`); поправить переопределение в `ConeProjectile`.

### V-5. PlayerCharacter::VRPlayerHandData — это VRMeleeData HIGGS/PLANCK: поле 0x10 — NiPointer<bhkWorld>, а блок 0xA0–0xAC противоречит практике
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено (0x10, 0xC0) / вероятно (0xA0–0xAC)
- Где:
  - CommonLib `include/RE/P/PlayerCharacter.h:373-400, 939`;
  - HIGGS `include/RE/misc.h:56-94`, `include/utils.h:62`, `src/hand.cpp:828-853`;
  - PLANCK `include/RE/misc.h:88-153`, `include/utils.h:87`, `src/utils.cpp:1112-1124`, `src/main.cpp:1145-1162`.
- Код:
  ```cpp
  // HIGGS utils.h:62
  inline VRMeleeData * GetVRMeleeData(bool isLeft) { return (VRMeleeData *)((UInt64)*g_thePlayer + 0x710 + (isLeft ? sizeof(VRMeleeData) : 0)); };
  // HIGGS hand.cpp:851-853
  if (NiPointer<bhkWorld> world = meleeData->world) { BSWriteLocker lock(&world->worldLock); CreateWeaponCollision(world); }
  // CommonLib PlayerCharacter.h:379, 390-391
  NiPointer<NiAVObject> unk10;               // 10 - NiPointer (likely controller scene node)
  NiPoint3              cachedHandPosition;  // A0
  std::uint32_t         padAC;               // AC
  // PLANCK utils.cpp:1123
  PlayRumble(!isLeft, meleeData->impactConfirmRumbleIntensity, meleeData->impactConfirmRumbleDuration);
  ```
- Суть и сценарий: это одна и та же память: `player+0x710+(isLeft?0xD0:0)` = `hands[isLeft]` (дамп: `hands` @0x710, sizeof(VRPlayerHandData) = 0xD0; у HIGGS и PLANCK static_assert 0xD0). Сравнение по дампу:

  | смещ. | CommonLib (дамп clang) | HIGGS/PLANCK | статус |
  |---|---|---|---|
  | 0x10 | `NiPointer<NiAVObject> unk10` | `NiPointer<bhkWorld> world` | **расхождение**; HIGGS берёт `world->worldLock` (+0xC598) и создаёт в мире тела, а у NiAVObject в VR всего 0x138 байт |
  | 0x18 | `unk18` «hand collision-proxy node» | `collisionNode` | совпадает (5 мест в src) |
  | 0x28–0x70 | deviceIndex, ringSampleIndex, lastSampledHandPosition, 3 кольцевых BSTArray | те же по типам | совпадает |
  | 0x88 | `BSTArray<NiPoint3> historyD` «unconfirmed» | `tArray<Actor*> sweepActors` | не используется в src — не проверено |
  | 0xA0–0xAC | `NiPoint3 cachedHandPosition` + `padAC` | `unkA0`, `linearVelocityThreshold` @0xA4 (static_assert), `impactConfirmRumbleIntensity` @0xA8, `…Duration` @0xAC | **конфликт**; PLANCK передаёт 0xA8/0xAC в PlayRumble (VR 0xC59440) |
  | 0xBC | `uint16 collisionFilterBit14Desired` | `bool enableCollision` | смысл совпадает (бит 14 фильтра) |
  | 0xC0 | `uint64 unkC0` | `SwingDirection swingDirection` + `float cooldown` @0xC4 | PLANCK пишет направление (main.cpp:1155-1162), и направление удара применяется |

  Если прав CommonLib, PLANCK подавал бы в вибрацию z-координату руки и нулевую длительность; HIGGS и PLANCK описывают здесь именно параметры вибрации. Индексация по практике: `hands[0]` — правая рука, `hands[1]` — левая.
- Как проверено: код обеих сторон, дамп. `cachedHandPosition` @0xA0 появилось в `b105ce17a` (2026-09-01). На всех 113 ветках с файлом стоит `NiPointer<NiAVObject> unk10`.
- Предложение:
  - `unk10` → `NiPointer<bhkWorld> world`;
  - `unkC0` → `SwingDirection swingDirection; float cooldown;`;
  - задокументировать индексы рук и добавить `GetVRHandData(bool a_left)`;
  - по 0xA0–0xAC — Ghidra: VR 0x6E5220 (`UpdateVRMeleeCollision`), читаются ли +0xA8/+0xAC перед вызовом 0xC59440. До проверки пометить конфликт в комментарии.

### V-6. WorldSpaceMenu в сборке SE+AE+VR: menuNode по 0x30, а в игре — по 0x48 (это же видно через HUDMenu/MapMenu::AsWorldSpaceMenu)
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено (дампы clang VR-only и all)
- Где: `include/RE/W/WorldSpaceMenu.h:27-33, 72-79`; `include/RE/I/IMenu.h:156-160`; `include/RE/H/HUDMenu.h:70-76`; `include/RE/M/MapMenu.h:159-164`; `src/RE/W/WorldSpaceMenu.cpp:9-16`
- Код:
  ```cpp
  class WorldSpaceMenu :
  #ifndef SKYRIM_CROSS_VR
      public IMenu, public BSTEventSink<HudModeChangeEvent>  // 40
  #else
      public IMenu  // 00
  #endif
  …   RE::NiPointer<RE::NiNode> menuNode;  // 48
  STATIC_ASSERT_SIZE(IMenu, 0x30, 0x30, 0x40, 0x30);   // IMenu.h:160 — в all 0x30
  ```
- Суть и сценарий:
  - Дамп all: `menuNode` @**0x30**, `registerForHudModeChangeEvent` @0x38, sizeof 0x40.
  - Дамп VR (он же раскладка движка): `IMenu` 0x40 + `BSTEventSink` @0x40, `menuNode` @**0x48**, sizeof 0x58.
  - Ошибка: 0x48 − 0x30 = 0x18.
  - В all-сборке на VR `hud->AsWorldSpaceMenu()->menuNode` читает `IMenu::unk30/unk34` (UI_MENU_Unk09 + байт) как `NiNode*`.
  - Деструктор `WorldSpaceMenu` (cpp:12-16) обращается к `parent` мусорного указателя.
  - Это станет важно, если HIGGS или PLANCK перейдут на одну DLL для SE и VR.
- Как проверено: два дампа; 125 веток с тем же `#else public IMenu`.
- Предложение: в SKYRIM_CROSS_VR не объявлять поля напрямую, а дать аксессор `GetMenuNode()` через `RelocateMember(this, 0, 0x48)` (VR-only, nullptr вне VR). Размер для all не фиксировать как 0x40.

### V-7. CrosshairPickData в сборке SE+AE+VR использует VR-раскладку и для SE/AE
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено (код + дамп all)
- Где: `include/RE/C/CrosshairPickData.h:36-52, 55-86`
- Код:
  ```cpp
  #if defined(EXCLUSIVE_SKYRIM_FLAT)
      ObjectRefHandle target;  // 04   ObjectRefHandle targetActor; // 08 …  bhkRigidBody* targetCollider; // 20
  #else
      ObjectRefHandle target[VR_DEVICE::kTotal];  // 04   … targetActor[3]; // 10 … targetCollider[3]; // 50
  #endif
  STATIC_ASSERT_SIZE(CrosshairPickData, 0x38, 0x38, 0x88, 0x88);
  ```
- Суть и сценарий:
  - `#else` покрывает и EXCLUSIVE_SKYRIM_VR, и SKYRIM_CROSS_VR, а размер для all закреплён как 0x88.
  - Правильно работает только `GetActiveTarget()`: вне VR он берёт `target[0]` @0x04, что совпадает с SE.
  - Прямые поля в all-сборке на SE/AE (SE → all):

    | поле | SE | all |
    |---|---|---|
    | `targetActor` | 0x08 | 0x10 |
    | `grabPickRef` | 0x0C | 0x1C |
    | `collisionPoint` | 0x10 | 0x28 |
    | `targetCollider` | 0x20 | 0x50 |
    | `pickCollider` | 0x28 | 0x78 — за пределами 0x38-байтного SE-объекта |

  - Сама VR-раскладка верна (см. «Проверено и в порядке»).
- Как проверено: дамп all; `git log` (последнее изменение — `98f5f3058` «GetActiveTarget»).
- Предложение: в CROSS — две структуры за аксессорами (`GetTargetCollider(VR_DEVICE)`, `GetPickCollider()`, `GetTargetActor(VR_DEVICE)`), как в других классах с runtime data.

### V-8. PlayerControls без VR-раскладки: в VR после togglePOVHandler идут ещё три обработчика
- Вид: ошибка; Важность: средняя; Уверенность: вероятно (SKSE VR + наличие RTTI TeleportHandler; для подтверждения нужен Ghidra VR-конструктора 0x72B900)
- Где: CommonLib `include/RE/P/PlayerControls.h:42, 68-89`, `src/RE/P/PlayerControls.cpp:8-11, 19-24`, `include/RE/T/TeleportHandler.h`; SKSE VR `GameInput.h:461-492`
- Код:
  ```cpp
  // CommonLib PlayerControls.h:80-89
  TogglePOVHandler* togglePOVHandler;  // 1D0
  bool notifyingHandlers;              // 1D8
  bool blockPlayerInput;               // 1D9
  static_assert(sizeof(PlayerControls) == 0x1E0);
  // SKSE VR GameInput.h:476-482, 492
  kInputHandler_Teleport, kInputHandler_VrSwim, kInputHandler_DragonRiding, kInputHandler_Num
  PlayerInputHandler* inputHandlers[kInputHandler_Num];	// 170
  STATIC_ASSERT(offsetof(PlayerControls, inputHandlers) == 0x170);
  ```
- Суть и сценарий:
  - В дампе VR у CommonLib та же раскладка, что во flat: `notifyingHandlers` @0x1D8, `blockPlayerInput` @0x1D9, sizeof 0x1E0.
  - В SKSE VR 16 обработчиков с 0x170: 0x170 + 16·8 = 0x1F0. Индексы 13/14/15 (Teleport, VrSwim, DragonRiding) — 0x1D8/0x1E0/0x1E8.
  - Значит, в VR `blockPlayerInput = true` пишет во второй байт указателя `teleportHandler`, и следующий ввод телепорта роняет игру.
  - `PlayerControls()` вызывает VR-конструктор (RELOCATION_ID(41257) → VR 0x72B900 = SKSE VR ctor), который инициализирует больше 0x1E0 байт.
  - Сам `TeleportHandler` в CommonLib есть, а места для него в `PlayerControls` нет.
- Как проверено: дамп; SKSE VR; ветки `vr`, `dev`, `feat/playercontrols-register-handler` — везде 0x1E0.
- Предложение:
  - VR-блок: `teleportHandler` @0x1D8, `vrSwimHandler` @0x1E0, `dragonRidingHandler` @0x1E8;
  - смещения `notifyingHandlers`/`blockPlayerInput` в VR снять в Ghidra (ожидаемо 0x1F0/0x1F1);
  - `STATIC_ASSERT_SIZE(PlayerControls, 0x1E0, 0x1E0, <VR>)` и аксессоры через `RelocateMember`.

### V-9. NiAVObject (EXCLUSIVE_SKYRIM_VR): пропущен float unk118, хвостовые поля сдвинуты на 4 байта
- Вид: ошибка; Важность: низкая; Уверенность: подтверждено (дамп + SKSE VR)
- Где: `include/RE/N/NiAVObject.h:158-160, 184-199`; SKSE VR `NiObjects.h:213-219`
- Код:
  ```cpp
  // CommonLib (VR)                                  // SKSE VR NiObjects.h:215-217
  TESObjectREFR* userData;   // 110                  float  unk118;     // 118
  std::uint32_t  unk11C;     // 11C  (дамп: 0x118)   UInt32 unk11C;     // 11C
  std::uint8_t   unk120[8];  // 120  (дамп: 0x11C)   UInt8  unk120[8];  // 120 - bitfield
  RUNTIME_DATA_ACCESSOR_EX(std::uint8_t, GetFlags02, 0x109, 0x121)
  ```
- Суть и сценарий:
  - После `userData` (0x110, 8 байт) у CommonLib сразу идёт `unk11C`, поэтому в дампе VR `unk11C` @0x118 и `unk120` @0x11C.
  - `unk128` встаёт на 0x128 за счёт выравнивания; sizeof 0x138 совпадает.
  - Аксессор `GetFlags02` (VR 0x121 = SKSE `unk120[1]`) верен, а член `unk120[1]` в VR-сборке лежит по 0x11D.
  - Пострадает только код, который напрямую трогает unk-поля или флаги через `unk120`.
- Как проверено: дамп; последнее изменение файла — `0fee48ad2`; на всех 127 ветках то же.
- Предложение: добавить `float unk118; // 118` и `static_assert(offsetof(NiAVObject, unk120) == 0x120)` под EXCLUSIVE_SKYRIM_VR.

### V-10. hkpWorldObject::SetProperty (SE 60628) — не та функция, которой HIGGS ставит свойство (SE 60630)
- Вид: неоптимальное; Важность: низкая; Уверенность: вероятно (нужен Ghidra SE 0x140A7F0E0 / 0x140A7F240)
- Где: CommonLib `src/RE/H/hkpWorldObject.cpp:57-62`; HIGGS `src/RE/offsets.cpp:147-150`, `src/physics.cpp:362-381`; VR-библиотека `database.csv:1613`, `addrlib.csv`
- Код:
  ```cpp
  // CommonLib
  static REL::Relocation<func_t> func{ RELOCATION_ID(60628, 61479) };    // SetProperty → VR 0xAB9AE0
  // HIGGS offsets.cpp:148-149
  RelocAddr<_hkpWorldObject_removeProperty> hkpWorldObject_removePropertyImpl(0xAB9B80);
  RelocAddr<_hkpWorldObject_setProperty> hkpWorldObject_setProperty(0xAB9C40);
  ```
- Суть и сценарий:
  - SE: 60628 @0xA7F0E0, 60629 @0xA7F180 (+0xA0), 60630 @0xA7F240 (+0xC0). VR: 0xAB9AE0 → 0xAB9B80 (+0xA0) → 0xAB9C40 (+0xC0).
  - Дельты совпадают побайтно, `addrlib.csv` даёт ту же пару: `removeProperty` HIGGS = 60629, `setProperty` HIGGS = 60630. CommonLib `SetProperty` = 60628, то есть другая функция.
  - HIGGS вызывает 60630 только после `!hasProperty` (physics.cpp:364-367), то есть для добавления.
  - Семантику 60628 никто не подтвердил: название в database.csv взято из CommonLib, а в `1.5.97_comments.csv` функция значится как `hkpWorldObject::sub_140A7F0E0`.
  - При порядке исходника Havok (addProperty → removeProperty → editProperty) одна из двух трактовок неверна. Если 60628 = addProperty, повторный `SetProperty` плодит дубликаты ключа.
- Как проверено: адреса и дельты; `git log` файла — только синхронизации.
- Предложение:
  - проверить обе функции в Ghidra, переименовать (AddProperty/EditProperty) и добавить недостающую;
  - внести 60629→0xAB9B80, 60630→0xAB9C40, 75975→0xDF8BD0 (HasProperty, Bethesda) в database.csv VR-библиотеки.

### V-11. Нет проверки, что SE-id обёрток есть в VR-адресной библиотеке, а тестовая копия CSV отстала на 76 выпусков
- Вид: неоптимальное; Важность: средняя; Уверенность: подтверждено
- Где: `include/REL/ID.h:40-53` (для VR `RELOCATION_ID(se, ae)` берёт `_vrID = a_seID`), `src/REL/IDDB.cpp:29-37, 175-177` (`report_and_fail`), `tests/REL/version-1-4-15-0.csv` (строка 2: `13502,0.194.0`), `tests/REL/Relocation.test.cpp:346`
- Код:
  ```cpp
  #ifdef ENABLE_SKYRIM_VR
      _vrID = a_seID;          // ID.h:50-52
  #endif
  if (it == _id2offset.end() || it->id != a_id) { report_id_lookup_failure(a_id); }   // IDDB.cpp:175-177
  ```
- Суть и сценарий: если SE-id нет в VR-CSV, первый же вызов обёртки на VR аварийно завершает игру. Прогон по всем 1 383 вызовам `RELOCATION_ID`/`REL::ID`/`REL::RelocationID` (VariantID не в счёт):
  - против тестовой копии v0.194.0 — 506 без VR-соответствия;
  - против текущего `database.csv` 0.270.0 — 77 вызовов (76 id), для 57 из них в `addrlib.csv` есть кандидат.

  Из оставшихся для VR-физики и взаимодействия значимы:
  - `hkpResponseModifier::SetInvMassScalingForContact` (61388; кандидат 0xAE3140);
  - `NiPick` ctor/dtor/PickObjects (70361–70363);
  - `InventoryChanges::GetInventoryItemAt` (15866);
  - `ExtraDataList::IsInventoryStackable` (11452);
  - `TESObjectREFR::AddLockChange` (19110);
  - `BSAudioManager::ReleaseAllSounds` (66472);
  - `BSTempNodeManager::UpdateTempNodeTimers` (74387).

  Показательно: три обёртки, которые HIGGS/PLANCK обходят сырыми адресами — `hkpWorld::LinearCast` (60554), `hkpWorld::RemoveEntity` (60493), `HitData::Ctor` (42826). В 0.194.0 их не было, в 0.270.0 они появились, и их VR-адреса 0xAB5EC0/0xAB0E50/0x76D000 совпали с HIGGS/PLANCK.
- Как проверено: скрипт по регулярному выражению над include/ и src/ и сопоставление с обоими CSV. Самостоятельной проверки id в CI нет: в `scripts/` только `check-vr-runtime-data.ps1` (он о раскладках) и `generate_offsets.py`.
- Предложение:
  - CI-шаг «все id из RELOCATION_ID/REL::ID есть в database.csv VR-библиотеки или стоят за IsVR()»;
  - обновить `tests/REL/version-1-4-15-0.csv`;
  - список 76 id отдать PR-ом в `skyrim_vr_address_library`.

### V-12. bhkRigidBodyT наследует bhkRigidBody приватно
- Вид: неоптимальное; Важность: низкая; Уверенность: подтверждено (код)
- Где: `include/RE/B/bhkRigidBodyT.h:9`; HIGGS `src/utils.cpp:254, 304`, `src/hooks.cpp:628-680` (14 строк), PLANCK `src/utils.cpp` (1 строка)
- Код:
  ```cpp
  class bhkRigidBodyT : bhkRigidBody   // по умолчанию private
  // HIGGS utils.cpp:254
  if (bhkRigidBodyT *rigidBodyT = DYNAMIC_CAST(rigidBody, bhkRigidBody, bhkRigidBodyT)) {
  ```
- Суть и сценарий:
  - `bhkRigidBodyT*` не приводится к `bhkRigidBody*`, а члены базы (`GetRigidBody()`, `referencedObject`, `unk28`) снаружи недоступны. HIGGS же после приведения работает с объектом и как с базой.
  - Раскладка при этом верна: дамп — `rotation` @0x40, `translation` @0x50, sizeof 0x60, как у HIGGS (`havok.h:191-199`).
  - VR-таблица 0x182BA80 совпадает с HIGGS hooks.cpp:650.
- Как проверено: код; файл с `cd83eb52b` не менялся.
- Предложение: `class bhkRigidBodyT : public bhkRigidBody`.

### V-13. PlayerCharacter (VR): 0x6BC/0x6C8 — позиция и скорость последнего удара (практика PLANCK)
- Вид: расширение; Важность: средняя; Уверенность: подтверждено для записи практикой PLANCK (что движок это читает — по комментарию PLANCK)
- Где: CommonLib `include/RE/P/PlayerCharacter.h:927-928`; PLANCK `src/main.cpp:1603-1609, 1698-1703`
- Код:
  ```cpp
  // CommonLib :927-928 (дамп: unk6B0 @0x6B0 [4×8], unk6D0 @0x6D0)
  std::uint64_t unk6B0[0x4]; /* … +0x0C/+0x18 unverified … */
  std::uint32_t unk6D0;      /* 6D0 */
  // PLANCK main.cpp:1604-1608
  // Hit position / velocity need to be set before Character::HitTarget() which at some point will read from them (during the HitData population)
  NiPoint3 *playerLastHitPosition = (NiPoint3 *)((UInt64)player + 0x6BC);
  NiPoint3 *playerLastHitVelocity = (NiPoint3 *)((UInt64)player + 0x6C8);
  ```
- Суть и сценарий: 0x6BC = 0x6B0 + 0x0C и 0x6C8 = 0x6B0 + 0x18 — ровно слоты, помеченные «unverified». `NiPoint3` @0x6BC занимает 0x6BC–0x6C7, @0x6C8 — 0x6C8–0x6D3. Значит, `unk6D0` — это `velocity.z`, а не отдельное поле.
- Предложение: разложить `unk6B0[4]` + `unk6D0` на `… ; NiPoint3 lastMeleeHitPosition /*6BC*/; NiPoint3 lastMeleeHitVelocity /*6C8*/;`. Добавить static_assert на 0x6BC/0x6C8/0x6D4 и пометку «проверено записью PLANCK перед HitTarget».

### V-14. Havok/bhk-функции с VR-адресами, проверенными HIGGS/PLANCK, в CommonLib без обёрток
- Вид: расширение; Важность: высокая; Уверенность: подтверждено для VR-адресов практикой; SE-id — по `addrlib.csv` и совпадению дельт (перед вкладом сверить в SE-бинаре)
- Где: HIGGS `src/RE/offsets.cpp:76-151`, `include/RE/offsets.h:88-315`; PLANCK `src/RE/offsets.cpp`; CommonLib `include/RE/H/hkpWorld.h`, `hkpRigidBody.h`, `hkpEntity.h`, `include/RE/B/bhkRigidBody.h`, `src/RE/B/bhkRigidBody.cpp`
- Код:
  ```cpp
  // HIGGS offsets.cpp (выборка)
  RelocAddr<_bhkRigidBody_setActivated> bhkRigidBody_setActivated(0xE085D0);     // SE 76258
  RelocAddr<_bhkRigidBody_setMotionType> bhkRigidBody_setMotionType(0xE08040);   // SE 76247
  RelocAddr<_hkpWorld_CastRay> hkpWorld_CastRay(0x00AB5B20);                     // SE 60552 (collector)
  RelocAddr<_hkpWorld_AddEntity> hkpWorld_AddEntity(0xAB0CB0);                   // SE 60492
  ```
- Суть:
  - Из 420 уникальных адресов HIGGS+PLANCK 80 через VR-библиотеку попадают на обёртки CommonLib, расхождений 0.
  - Остальные 340 без обёрток:
    - функций 287: у 22 id есть в `database.csv`, у 256 — только в `addrlib.csv`, у 9 SE-id нет;
    - глобальных переменных 53: 3 в `database.csv`, 50 нет (в основном INI-настройки).
  - Портированные из PLANCK заголовки (`hkConstraintCinfo`, `hkBallAndSocketConstraintCinfo`, `bhkGroupConstraint`, `bhkRigidBodyCinfo`, `hkbRagdollDriver`, …) функций не содержат: `grep -c RELOCATION_ID` даёт 0 в 12 файлах.
  - Самые нужные (строк в src HIGGS+PLANCK):

    | функция | SE-id | строк |
    |---|---|---|
    | `bhkRigidBody::SetActivated` | 76258 | 14 |
    | `bhkRigidBody::SetMotionType` | 76247 | 9 |
    | `hkpConstraintInstance::isEnabled` | 60721 | 6 |
    | `bhkRigidBody` ctor | 19457 (есть в db) | 4 |
    | `bhkWorldObject::UpdateCollisionFilter` | 75968 | 4 |
    | `bhkGroupConstraint` ctor | 77866 | 3 |
    | `hkpKeyFrameUtility::applyHardKeyFrame` | 61579 | 3 |
    | `hkpWorld::UpdateCollisionFilterOnEntity` | 60509 | 3 |

    Полный список — в таблице вкладов.
  - Сигнатуры брать из HIGGS `offsets.h`, учитывая скрытые возвраты (`hkBool`, `hkpPropertyValue`, см. V-2).
- Предложение:
  - обёртки `RELOCATION_ID(se, ae)` (AE-id подобрать по SE→AE);
  - VR-адреса отдать PR-ом в `database.csv` со ссылкой на практику HIGGS/PLANCK;
  - для hkpWorld — перегрузка `CastRay(const hkpWorldRayCastInput&, hkpRayHitCollector&)` (60552).

### V-15. hkpRigidBody/hkpEntity/hkpWorldObject: нет inline-аксессоров Havok SDK, которые плагины используют чаще всего
- Вид: расширение; Важность: высокая; Уверенность: подтверждено (подсчёт; смещения сверены)
- Где: CommonLib `include/RE/H/hkpRigidBody.h` (28 строк, 3 метода: ApplyLinearImpulse/SetLinearVelocity/SetAngularVelocity); `include/RE/H/hkpTypedBroadPhaseHandle.h:17-21`, `hkSweptTransform.h:11-15`, `hkpMotion.h:67-80`
- Код:
  ```cpp
  void ApplyLinearImpulse(const hkVector4& a_impulse);
  void SetLinearVelocity(const hkVector4& a_newVel);
  void SetAngularVelocity(const hkVector4& a_newVel);   // всё, что есть у hkpRigidBody
  ```
- Суть:
  - Вызовы в src HIGGS+PLANCK: `getCollidable` 25, `getTransform` 19, `getMassInv` 17, `getPosition` 16, `getWorld` 14, `getQualityType` 10, `getCollisionFilterInfo` 8, `getLinearVelocity` 7, `getMotionState` 4, `getCenterOfMassInWorld` 4, `getRotation` 3.
  - Обращения к полям: `m_collidable` 73, `m_userData` 55, `m_motionState` 32, `m_motion` 30.
  - Всё это inline в SDK 2010.2 и адресов не требует.
  - Нужные смещения в CommonLib уже есть и сверены по дампу: `motion` @0x150, `collidable` @0x20, `userData` @0x18, `broadPhaseHandle.objectQualityType` +6, `.collisionFilterInfo` +8, `sweptTransform.centerOfMass1` +0x10, `inertiaAndMassInv` @motion+0xD0.
- Предложение: `GetTransform()`, `GetPosition()`, `GetRotation()`, `GetMassInv()`, `GetLinearVelocity()`, `GetAngularVelocity()`, `GetCenterOfMassInWorld()`, `GetQualityType()`, `Get/SetCollisionFilterInfo()`, `GetWorld()` + static_assert смещений.

### V-16. VR-only функции и VR-настройки без SE-id, нужные VR-плагинам
- Вид: расширение; Важность: средняя; Уверенность: подтверждено практикой (адреса VR 1.4.15)
- Где:
  - HIGGS `src/RE/offsets.cpp:46-60, 197, 200, 202, 223, 225`, `src/main.cpp:122-190, 710`;
  - PLANCK `src/RE/offsets.cpp:64-65, 348-349`, `src/main.cpp:7978`;
  - CommonLib — образцы VR-only обёрток через `REL::Offset` в `src/RE/B/BSOpenVR.cpp:8-58`, `src/RE/W/WorldSpaceMenu.cpp`.
- Код:
  ```cpp
  typedef void(*_PlayRumble)(UInt32 isRight, float rumbleIntensity, float rumbleDuration);   // VR 0xC59440
  typedef void (*_UpdateClavicleToTransformHand)(NiAVObject *clavicle, NiAVObject *hand, NiTransform *desiredHandWorldTransform, NiTransform *additionalLocalTransform);  // 0xC4C5A0
  typedef NiAVObject * (*_PlayerCharacter_GetOffsetNodeForWeaponIndex)(PlayerCharacter *_this, UInt32 isLeft, UInt32 weaponIndex); // 0x6AF100
  ```
- Суть:
  - Ни в `database.csv`, ни в `addrlib.csv` нет:
    - `PlayRumble` (7 строк);
    - `UpdateClavicleToTransformHand` (7);
    - `PlayerCharacter::GetOffsetNodeForWeaponIndex` (2);
    - `VRMeleeData::ComputeAngularVelocities` (0x6B45C0);
    - `PlayerControls::IsTriggerHeldOffHand` (0x72D770).
  - Для `UpdateVRMeleeCollision` (0x6E5220), `PlayerControls::IsTriggerHeldMainHand` (0x72D740) и `RefreshActivateButtonArt` (0x53EFE0) в `addrlib.csv` есть SE-«кандидаты» (51478/95206/67389). Но это VR-only функции, и автоматическому сопоставлению здесь доверять нельзя.
  - VR-настройки: `fMagicHand{Translate,Rotate}{X,Y,Z}/Scale` (0x1EAEA58…0x1EAEAE8), `fActivateRolloverWand*` (0x1EAACF0…0x1EAAD80), `fMeleeLinearVelocityThreshold` 0x1EAE500, `fShieldLinearVelocityThreshold` 0x1EAE5A8.
  - OpenVR: позы плагины берут через колбэк `WaitGetPoses` интерфейса VRTools, а `BSOpenVR` в CommonLib уже даёт `vrSystem`, `TriggerHapticPulse`, `GetHandTransform`.
- Предложение: VR-only обёртки через `REL::VariantID(0, 0, off)` или `REL::Offset` под `ENABLE_SKYRIM_VR` с IsVR()-проверкой. Настройки брать через `INISettingCollection` по имени (адреса не нужны).

### V-17. Рэгдолл и поведение (PLANCK): структуры портированы, функций нет
- Вид: расширение; Важность: средняя; Уверенность: подтверждено для VR-адресов практикой PLANCK; SE-id — `addrlib.csv`
- Где: PLANCK `src/RE/offsets.cpp` (hkbRagdollDriver_*, hkaRagdollRigidBodyController_*, BSAnimationGraphManager_*), `include/RE/havok_behavior.h`; CommonLib `include/RE/H/hkbRagdollDriver.h`, `include/RE/B/BSIRagdollDriver.h:15-29`, `include/RE/B/BShkbAnimationGraph.h`
- Код:
  ```cpp
  // CommonLib BSIRagdollDriver.h:17-19 — виртуальные функции есть, а обёрток уровня менеджера/драйвера нет
  virtual bool HasRagdoll() = 0;             // 01
  virtual bool AddRagdollToWorld() = 0;      // 02
  virtual bool RemoveRagdollFromWorld() = 0; // 03
  ```
- Суть: PLANCK вызывает или перехватывает (VR-адрес → SE-id из addrlib):

  | функция | VR | SE-id |
  |---|---|---|
  | `hkbRagdollDriver::driveToPose` | 0xA25B60 | 57723 |
  | `hkbRagdollDriver::postPhysics` | 0xA27730 | 57725 |
  | `hkbRagdollDriver::mapHighResPoseLocalToLowResPoseWorld` | 0xA280C0 | 57735 |
  | `hkbRagdollDriver::getRagdoll` | 0xA25860 | 57718 |
  | `hkbRagdollDriver::reset` | 0xA279C0 | 57726 |
  | `hkaRagdollRigidBodyController` ctor/dtor/driveToPose/reinitialize | 0xB4CBC0/0xB4CEE0/0xB4CFF0/0xB4D220 | 63178/63179/63180/63181 |
  | `hkaSkeletonMapper::mapPose` | 0xB48AB0 | 63152 |
  | `hkbBehaviorGraph::generate` | 0xA2BD80 | 57772 |
  | `BShkbAnimationGraph::PreGenerate/Generate` | 0xB2A190/0xB2A9E0 | 62642/62644 |
  | `BSAnimationGraphManager` AddRagdollToWorld/RemoveRagdollFromWorld/SetWorld/ResetRagdoll/HasRagdoll | 0x5D1B50/0x61A1E0/0x502670/0x6973D0/0x20B320 | 36023/37074/32189/39052/16163 |

  Упоминаний типов в src PLANCK: `hkbRagdollDriver` 46, `BSAnimationGraphManager` 23, `BShkbAnimationGraph` 20. Раскладки CommonLib для этих классов совпадают с PLANCK (см. ниже).
- Предложение: обёртки с SE-id из addrlib после сверки. Bethesda-обёртки `BSAnimationGraphManager::*` сверять особо — это не байт-идентичный код Havok.

---

## Приоритетный список вкладов для троицы

Счёт — строки в `src/*.cpp` HIGGS+PLANCK (без `src/RE/offsets.cpp`), по имени сущности.

| # | Что внести в CommonLib | Откуда взять описание | Использований (HIGGS+PLANCK) |
|---|---|---|---|
| 1 | Inline-аксессоры `hkpRigidBody`/`hkpEntity`/`hkpWorldObject` (V-15) | Havok SDK 2010.2 + смещения CommonLib (дамп) | ≈116 вызовов + ≈190 обращений к полям |
| 2 | Счётчик кадров `gFrameCounter` (SE-id 525008, VR 0x3186C5C, в database.csv) | HIGGS/PLANCK `offsets.cpp` (`g_currentFrameCounter`) | 54 |
| 3 | `GetNiObjectFromHavokCollidable` (76160, VR 0xE01FE0, в database.csv) рядом с `TESHavokUtilities::FindCollidableRef` | HIGGS `offsets.h:320` (`GetNodeFromCollidable`) | 26 |
| 4 | `bhkRigidBody`: SetActivated (76258), SetMotionType (76247), MoveToPositionAndRotation (76268), ctor (19457), Add/RemoveConstraintToArray (76265/76264), GetMaxAngularVelocity (76335); `bhkRigidBodyCinfo` ctor (76222); `bhkWorldObject::UpdateCollisionFilter` (75968); `public`-наследование `bhkRigidBodyT` (V-12) | HIGGS `offsets.h:146-227`, `havok.h:170-199, 247-261` | ≈37; bhkRigidBodyT 15 |
| 5 | Поля `VRPlayerHandData` (world, swingDirection, cooldown, вибрация) + `GetVRHandData(bool)` (V-5) | HIGGS `misc.h:56-94`, PLANCK `misc.h:88-153` | VRMeleeData 13 + GetVRMeleeData 11 |
| 6 | `bhkCharacterController`: имена слотов 09 SetCollisionFilterInfo / 0B Integrate / 0C FireMoveFinishEvent / 0E MoveToWorld, `CollisionEvent`; `HitData::PopulateFromPhysicalHit` (42836), `HitData` dtor (42828) | HIGGS `havok.h:295-396`, `offsets.h:489-499`; PLANCK `havok_behavior.h:488-592` | bhkCharacterController 23, CollisionEvent 8, HitData_* 5 |
| 7 | Ограничения: `hkConstraintCinfo::setConstraintData` (77111), `hkpBallAndSocketConstraintData` ctor/setInBodySpace/setInWorldSpace (60775/60776/60777), `hkpRagdollConstraintData` ctor/setInBodySpace (60745/60748), `hkpConstraintInstance` ctor/setEnabled/isEnabled/setPriority (60705/60720/60721/60716), `bhkGroupConstraint` ctor (77866), `bhkRagdollConstraint` ctor (77367), `hkMalleableConstraintCinfo` setWrappedConstraintData/setStrength (77091/77092), `hkpPositionConstraintMotor` ctor (61172), `bhkWorld::AddConstraint/RemoveConstraint` (76007/76015) | HIGGS `offsets.h:244-290`, `havok.h:154-158, 263-293`; PLANCK `offsets.cpp` | ≈30 (bhkGroupConstraint 7, isEnabled 6, hkConstraintCinfo 5, BallAndSocket 3, прочие по 1–2) |
| 8 | Рэгдолл и поведение (V-17) | PLANCK `offsets.cpp`, `havok_behavior.h` | hkbRagdollDriver 46, BSAnimationGraphManager 23, BShkbAnimationGraph 20 |
| 9 | `hkpWorld`: AddEntity (60492), CastRay(collector) (60552), GetClosestPoints (60556), GetPenetrations (60558), add/remove ContactListener (60543/…), WorldPostSimulationListener (60538/60539), IslandActivationListener (60535/60536), addEntityListener (60532), UpdateCollisionFilterOnEntity (60509), findWorldExtension (60549), reintegrateAndRecollideEntities (60513), getCurrentTime (60572); исправить RemoveEntity (V-2) | HIGGS `offsets.h:89-135` | ≈20 |
| 10 | VR-only: PlayRumble, UpdateClavicleToTransformHand, GetOffsetNodeForWeaponIndex, UpdateAndGetAttackData (addrlib: 40232, сверить), IsTriggerHeld*, UpdateVRMeleeCollision, RefreshActivateButtonArt, VR-настройки (V-16) | HIGGS/PLANCK `offsets.h/.cpp` | ≈28 |
| 11 | `PlayerControls` VR-раскладка (V-8) и `blockPlayerInput` для VR | SKSE VR `GameInput.h:438-492` + Ghidra | 6 (SendAction/IsTriggerHeld в PLANCK) |
| 12 | `MovementControllerNPC`: имена `movementType` (0x1C0), `isPlannerDirectControl` (0x1C7), `isHighProcess` (0x1C9), `movementPlannerDirectControl` и других интерфейсов | PLANCK `misc.h:456-505` | 9 + GetMovementController 5 |
| 13 | `bhkCollisionFilter::CompareFilterInfos` (VR 0xDD6A80, SE-id не найден); `layerDebugColors[64]` @0x5E0 вместо `unk5E0[256]` | HIGGS `offsets.h:198`, PLANCK `havok.h:74` | bhkCollisionFilter 9 |
| 14 | PlayerCharacter VR 0x6BC/0x6C8 (V-13) | PLANCK `main.cpp:1603-1609` | 4 |
| 15 | `hkpKeyFrameUtility` applyHardKeyFrame/Asynchronously/applySoftKeyFrame (61579/61580/61578) | HIGGS `offsets.h:185-190` | 3 |
| 16 | `NiObject::Clone(NiCloningProcess&)` (68836) + `NiCloningProcess` | HIGGS `misc.h:21-54`, PLANCK `misc.h:53-86` | 2 |
| 17 | `hkpCharacterProxy` add/removeCharacterProxyListener (61729/…) | HIGGS `offsets.h:313`, PLANCK | 2 |

SE-id с пометкой addrlib нужно подтвердить в SE-бинаре и отдать парой «id → VR-адрес (из HIGGS/PLANCK)» в `database.csv`.

## Проверено и в порядке

- **Адреса.**
  - 80 уникальных адресов HIGGS/PLANCK, которые через текущую VR-библиотеку ложатся на SE-id обёрток CommonLib, совпали без единого расхождения. Среди них:
    - `bhkWorld::GetWorldScale(Inverse)` (231896/230692), `CrosshairPickData::GetSingleton` (515446), `ProcessLists` (514167), `bhkCollisionFilter` (514415);
    - `hkpEntity::Add/RemoveContactListener/Activate` (60094/60095/60096), `hkReferencedObject` (56606/56607), `bhkCollisionObject::GetRigidBody` (12784), `hkpWorldObject::RemoveProperty` (75976);
    - `TESObjectCELL::GetbhkWorld` (18536), `TESHavokUtilities::FindCollidableRef` (25466);
    - `PlayerCharacter::ActivatePickRef/StartGrabObject` (39471/39475);
    - `NiAVObject::Update` (68900), `NiAVObject::SetMotionType` (76033), `UpdateRigidConstraints` (76271);
    - `HitData::Populate` (42832), `BSSoundHandle::*`, `Actor::*` (36252…37864), `AIProcess::*`, `TES`, `BGSImpactManager` и другие.
  - `hkpWorld::LinearCast` 60554 → 0xAB5EC0, `RemoveEntity` 60493 → 0xAB0E50, `HitData::Ctor` 42826 → 0x76D000: есть в 0.270.0 и совпадают с HIGGS/PLANCK (сигнатура RemoveEntity — V-2).
- **VTABLE (VariantID, VR-смещение).** `PlayerCharacter` 0x16E2230, `hkCharControllerShape` 0x1838E78, `TESActionData` 0x15BF5D8, `bhkRigidBodyT` 0x182BA80, `hkConstraintCinfo` 0x161D218, `hkBallAndSocketConstraintCinfo` 0x18249C8 — равны значениям PLANCK/HIGGS. Синглтон `BSOpenVR` — `REL::Offset(0x2FEB9B0)` = SKSE VR `g_openVR`; `hapticPulseScale` 0x17E6E50.
- **Слоты виртуальных функций в VR.**
  - `Actor::Update` — 0xAF (`RelocateVirtual(0x0AD, 0x0AF)`; HIGGS: 0x16E27A8 = 0x16E2230 + 0xAF·8).
  - `Projectile`: слот 0xBF (номер совпадает, тип аргумента — V-4).
  - `hkpShapePhantom::SetPositionAndLinearCast` — 0x0F (HIGGS: 0x17B6890 − 0x17B6818 = 0x78 = 0x0F·8).
  - `BSVRInterface::TriggerHapticPulse(bool right, float)` — 0x0E (HIGGS haptics.cpp:12; в SKSE VR тоже 0x0E).
  - Слоты `bhkRefObject` 25–26, `bhkSerializable` 27–31, `bhkRigidBody` 33–3C совпадают с HIGGS/PLANCK.
- **Узлы PlayerCharacter (VR).**
  - Все 26 узлов, которые используют HIGGS/PLANCK (`unk3F0[kNode_*]`, `unk538[kBowNode_*]`), проверены по индексу SKSE VR (0x3F0 + 8·i, 0x5B8 + 8·i) против дампа `VR_NODE_DATA`.
  - Совпали: PlayerWorldNode 0x3F0, RoomNode 0x418, SpellOrigin 0x468, Left/RightWandNode 0x490/0x4F8, *ValveIndexControllerNode 0x4A0/0x508, *Weapon/Crossbow/Melee/Staff/ShieldOffsetNode, Secondary/PrimaryMagicAimNode 0x4E8/0x540, HmdNode 0x570, NPC L/R Hnd/Clv 0x590–0x5A8, BowRotationNode 0x5D0.
  - sizeof(PlayerCharacter) VR = 0x12D8, как в SKSE VR.
- **Havok/bhk (дамп VR против HIGGS/PLANCK).**
  - `bhkWorld.worldLock` 0xC598, sizeof 0xC600; `ahkpWorld.userData` 0x430.
  - `bhkCollisionFilter`: nextSystemGroup 0x4C, layerBitfields 0x1D0, имена слоёв 0x3E0/0x6E0, sizeof 0x7E0.
  - `bhkRigidBody` 0x40 (массив ограничений @0x28); `bhkRigidBodyT` 0x60.
  - `bhkNiCollisionObject`: flags 0x18, body 0x20. `bhkBlendCollisionObject`: blendStrength 0x28, motionType 0x30, world 0x38, sizeof 0x48. `bhkShape.materialID` 0x20.
  - `bhkCharacterController` 0x330, все используемые поля: outVelocity 0x90, initialVelocity 0xA0, context 0x1E0, flags 0x218, calculatePitchTimer 0x22C, fallStartHeight 0x240, fallTime 0x244, pitchAngle 0x24C, rollAngle 0x250.
  - `bhkCharProxyController.proxy` / `bhkCharRigidBodyController.charRigidBody` 0x340.
  - `hkpEntity.motion` 0x150 (PLANCK: `(hkpRigidBody*)(motion − 0x150)`); `hkpWorldObject`: world 0x10, userData 0x18, collidable 0x20, properties 0xB8.
  - `MiddleHighProcessData.charController` 0x250 (HIGGS `middleProcess->unk250`).
- **Поведение (дамп против PLANCK).**
  - `BShkbAnimationGraph`: character 0xC0, holder 0x210, generatorOutputs 0x220, world 0x238, doFootIK 0x249, sizeof 0x250.
  - `BSAnimationGraphManager`: graphs 0x40, updateLock 0x98.
  - `hkbRagdollDriver`: character 0x80, sizeof 0xD0. `hkbCharacter`: behaviorGraph 0x58, sizeof 0xA0. `hkbContext.world` 0x38. `hkbNode` 0x48. `hkbCharacterData` 0xB0. `hkbFootIkDriver.disableFootIk` 0x4A.
  - `hkbTransitionEffect.eventMode` 0x49, `hkbBlendingTransitionEffect.fromGenerator` 0x60, `BSCyclicBlendTransitionGenerator.state` 0xA8, `BSLookAtModifier` 0xE0, `BGSFootIkRaycastInterfaceDB.raycastData` 0x40.
  - `MovementControllerNPC`: actor 0x1B8, sizeof 0x1D0.
  - `hkbCharacterSetup`: поля до 0x40, которые использует PLANCK, совпадают. Дальше описание CommonLib (unscaledAnimationSkeleton 0x48, mirroredSkeleton 0x50, characterPropertyIdMap 0x58, sizeof 0x68) полнее PLANCK, а PLANCK эти поля не читает.
- **Прочее VR.**
  - `BSFlattenedBoneTree` VR: numBones 0x150, boneEntries 0x158, sizeof 0x190 = PLANCK.
  - `NiAVObject` VR: flags 0x10C, userData 0x110, sizeof 0x138; хвост — V-9.
  - `BSOpenVR`: vrSystem 0x208, controllerNodes 0x388, hmdDeviceType 0x398, eyeToHeadTransform 0x39C, sizeof 0x408 — как в SKSE VR.
  - `CrosshairPickData` VR: target[3] 0x04, targetActor[3] 0x10, grabPickRef[3] 0x1C, targetCollider[3] 0x50, pickCollider 0x78, sizeof 0x88. Точно ложится на HIGGS: `leftHandle1..3`/`rightHandle1..3`, `rigidBodies[2]` @0x50, `sphere` @0x78; `g_pickSphere` 0x3000958 = экземпляр 0x30008E0 + 0x78.
  - `Actor`: VR-смещения равны SE (boolBits 0xE0, voiceTimer 0x108, movementController 0x148, combatController 0x158, race 0x1F0, boolFlags 0x1FC, unk274). Аксессор `RelocateMemberIfNewer` для VR 1.4.15 выбирает SE-вариант — верно.
  - `HitData`: используемые поля (hitPosition, aggressor, totalDamage 0x50, flags 0x80) совпадают, sizeof 0x90.
