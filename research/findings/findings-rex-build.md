# CommonLibSSE-NG 9.1.0 (a898f4698): слой REX, сборка, упаковка, CI и тесты — находки

Область: (А) `include/REX/**`, `src/REX/**` — Singleton, Enum/EnumSet, Setting и бэкенды INI/JSON/TOML, W32/* (KERNEL32, USER32, ADVAPI32, BCRYPT, DBGHELP, D3D/D3D11/DXGI, DINPUT, XINPUT, COM/COMPTR, NT, SHELL32, VERSION), PS4/SCEPAD; (Б) `CMakeLists.txt`, `cmake/**`, `CMakePresets.json`, `xmake.lua`, `vcpkg*.json`, `.github/workflows/*.yml`, `scripts/**`, `tests/**`, `test_consumer*/**`, `test_package/**`, `examples/linux-cross-compile/**`.
Пути — от корня клона. Клон только читался (`git status` чист).

Чем проверялось, кроме чтения кода:
- стенд в scratchpad: настоящий `src/REX/REX.cpp` + заголовки REX, собранные g++ 13.3 с toml11 v4.4.0, nlohmann/json v3.12.0 и SimpleIni v4.25 (версии из `vcpkg.json`). В копии REX.cpp исправлен только нестандартный синтаксис `SettingLoad<T>(` → `SettingLoad(` (см. X-8), логика не тронута;
- clang 18.1.3 (`-fms-extensions -fdeclspec`, для X-8 ещё и `--target=x86_64-pc-windows-msvc -fms-compatibility`) — проверки компиляции Enum/EnumSet/ComPtr;
- CMake 3.28 — модели для IPO, install/find_package и `add_commonlibsse_plugin`.
MSVC и игра в этой среде недоступны. Что сверено только по правилам языка или документации SDK, так и помечено.

Итого: 23 находки — ошибок 19, неоптимального 2, расширений 2.

---

## Ошибки

### X-1. TOML: значение вложенной секции читается из чужой таблицы
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено
- Где: `src/REX/REX.cpp:227-251` (`recurse_table`), вызов — `src/REX/REX.cpp:285-293`
- Код:
  ```cpp
  if (a_result && a_result->is_table()) {
  	for (auto& value : a_result->as_table()) { if (value.first == a_section) return std::addressof(value.second); }
  	if (a_create) { ... }
  } else if (a_value.is_table()) {      // уровень не найден -> снова поиск от корня
  	for (auto& value : a_value.as_table()) { if (value.first == a_section) return std::addressof(value.second); }
  	...
  }
  return a_result;                       // не найдено -> возвращается родитель, а не nullptr
  ```
- Суть и сценарий: для секции из двух и более уровней, например `"Display.HUD"`, возможны две ошибки.
  1. Если `[Display]` есть, а `[Display.HUD]` нет, функция возвращает `[Display]`, и ключ читается из родительской таблицы.
  2. Если первого уровня нет, следующее имя ищется в корне, и берётся таблица `[HUD]` верхнего уровня.

  Чужое значение молча заменяет значение по умолчанию, а в пользовательском файле ещё и перекрывает базовый. Пример: в base.toml есть только `[Display] Scale = 2.0`; `TOML::F32<>{"Display.HUD", "Scale", 1.0f}` получает 2.0 вместо 1.0. Для секции `"Game.Menu"` при файле `[Menu] Scale = 3.0` получается 3.0.
- Как проверено: на стенде с toml11 v4.4.0 вывод `Display.HUD.Scale (expected default 1.0) = 2` и `Game.Menu.Scale (expected default 1.0) = 3`. `git log -5 -- src/REX/REX.cpp`: последняя правка e1d1b0c7e этот участок не исправляла. Веток с исправлением в `origin/*` нет.
- Предложение: обходить всегда от корня и возвращать `nullptr`, если уровня нет или он не таблица: `toml::value* cur = &root; for (auto& s : sec) { if (!cur->is_table()) return nullptr; auto& t = cur->as_table(); auto it = t.find(s); if (it == t.end()) { if (!create) return nullptr; it = t.emplace(s, toml::table{}).first; } cur = &it->second; } return cur;`. Добавить тест на вложенные секции (X-22).

### X-2. `Save()` пишет только в базовый файл: при наличии пользовательского файла изменение теряется после перезапуска
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено
- Где: `src/REX/REX.cpp:100-112` (INI), `:202-216` (JSON), `:359-373` (TOML); семантика загрузки — `include/REX/REX/INI.h:40-48` (так же в JSON.h/TOML.h)
- Код:
  ```cpp
  void SettingStore::Save()
  {
  	CSimpleIniA file; ...
  	file.LoadFile(m_fileBase.data());
  	for (auto& setting : m_settings) { setting->Save(&file); }
  	file.SaveFile(m_fileBase.data());
  }
  ```
- Суть и сценарий: `Load` читает базовый файл, затем пользовательский, и значения пользовательского файла перекрывают базовые. `Save` пишет текущие значения только в базовый файл. Пользовательский файл остаётся прежним и при следующем `Load` снова перекрывает сохранённое. Сценарий: в base `iVal = 10`, в user `iVal = 20`. `Load` даёт 20; плагин из MCM делает `SetValue(30)` и `Save()`. На диске base = 30, user = 20. После перезапуска значение снова 20, изменение потеряно. Заодно пользовательские значения затирают поставляемые с модом умолчания в базовом файле.
- Как проверено: на стенде с SimpleIni 4.25 — `INI after re-Load (expected 30) = 20`, содержимое файлов после `Save`: base = 30, user = 20. JSON и TOML устроены так же: пишут в `m_fileBase` без условий.
- Предложение: если задан `m_fileUser`, сохранять в него, причём только значения, отличные от `m_valueDefault`; базовый файл не трогать. Либо явный параметр `Save(Target)`.

### X-3. Пакет, установленный через `cmake --install`, непригоден для `find_package(CommonLibSSE)`
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено
- Где: `cmake/config.cmake.in:1-5`, `CMakeLists.txt:307-336` (install), `:237-245` и `:276-290` (openvr, DirectXTK)
- Код:
  ```cmake
  include("${CMAKE_CURRENT_LIST_DIR}/@PROJECT_NAME@-targets.cmake")
  include("${CMAKE_CURRENT_LIST_DIR}/@PROJECT_NAME@.cmake")   # этот файл не устанавливается
  include(CMakeFindDependencyMacro)
  find_dependency(spdlog CONFIG)                              # directxtk не ищется
  ```
- Суть и сценарий: путь, описанный в README (`README.md:79`, `:114`: `find_package(CommonLibSSE REQUIRED)`), ломается в трёх местах.
  1. `cmake/CommonLibSSE.cmake` не устанавливается, поэтому конфиг падает с «include could not find requested file».
  2. Цель ссылается на `Microsoft::DirectXTK` (PUBLIC), а `find_dependency` вызывается только для spdlog. Итог: «link interface … contains Microsoft::DirectXTK but the target was not found».
  3. Устанавливаются только `include/{RE,REL,REX,SKSE}`, а `INSTALL_INTERFACE` — только `include`. При этом `RE/B/BSVRInterface.h:9` и `RE/B/BSTrackedControllerDevice.h:7` при `ENABLE_SKYRIM_VR` (он включён по умолчанию) делают `#include "openvr.h"`. Вдобавок `openvr_api.lib` экспортируется абсолютным путём в дерево исходников.

  `test_package/CMakeLists.txt` идёт именно этим путём, но в CI не запускается: после 05775a8bf («remove Conan») он не используется.
- Как проверено: модель на CMake 3.28 с настоящим `config.cmake.in` и теми же install-правилами (заглушки spdlog/directxtk). Воспроизведены обе ошибки configure (п. 1 и 2). П. 3 — по install-правилам и include-ам. Порт vcpkg лежит вне репозитория и может сам это латать — не проверялось.
- Предложение: `install(FILES cmake/CommonLibSSE.cmake …)`; `find_dependency(spdlog)` и `find_dependency(directxtk)` до подключения targets; устанавливать `extern/openvr/headers` и `openvr_api.lib`, путь давать через `$<INSTALL_INTERFACE:…>`. Нужен CI-джоб «install + сборка test_package» (X-22).

### X-4. Повреждённый базовый файл: JSON `Save` роняет процесс, TOML молча сбрасывает все настройки и затирает файл; запись не атомарна
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено
- Где: `src/REX/REX.cpp:202-216` (JSON Save), `:344-357` и `:359-373` (TOML Load/Save), `:106-111` (INI Save)
- Код:
  ```cpp
  nlohmann::json output{};
  if (std::filesystem::exists(m_fileBase)) {
  	std::ifstream file{ m_fileBase.data() };
  	output = nlohmann::json::parse(file);          // без try: parse_error уходит из Save()
  }
  ...
  std::ofstream file{ m_fileBase.data(), std::ios::trunc };
  file << std::setw(4) << output;                  // запись поверх, результат не проверяется
  ```
- Суть и сценарий:
  - JSON: исключение `nlohmann::parse_error` выходит из `SettingStore::Save()` в код плагина. `Save` обычно вызывают из обработчика меню или сообщения SKSE без `try`, поэтому дело кончается `std::terminate` и вылетом игры. Типичная причина — лишняя запятая в конце объекта после ручной правки.
  - TOML: при ошибке разбора `Load` ничего не пишет в лог, и все настройки остаются по умолчанию. Затем `Save` начинает с пустого документа и перезаписывает файл: комментарии, чужие ключи и секции исчезают.
  - Все три бэкенда пишут прямо в целевой файл (`ofstream(trunc)` или `SaveFile`, который открывает файл на запись) без временного файла и не проверяют результат. Сбой посреди записи оставляет обрезанный файл. Для JSON это замкнутый круг: после этого `Save` падает при каждом вызове.
- Как проверено: на стенде JSON дал `Save threw out of SettingStore::Save: [json.exception.parse_error.101] …`. Для TOML файл `# comments / [General] a=5 other="keep me" / [Extra] x=1 / broken =` после `Load` дал `a=1`, а после `Save` в нём осталось только `[General]\na = 1`.
- Предложение: в `Save` при ошибке разбора базового файла не перезаписывать его (или писать `.new`) и логировать; обернуть работу в `try`/`catch`; писать во временный файл рядом и затем `ReplaceFileW`/`MoveFileExW(MOVEFILE_REPLACE_EXISTING)`, проверяя ошибки; в TOML `Load` логировать `result.unwrap_err()`.

### X-5. JSON: одно значение неверного типа обрывает загрузку всех следующих настроек
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `src/REX/REX.cpp:179-186` (так же `:190-198`), `:130-135`
- Код:
  ```cpp
  try {
  	auto result = nlohmann::json::parse(file);
  	for (auto setting : m_settings) { setting->Load(&result, true); }   // value<T>() бросает type_error.302
  } catch (const std::exception& e) {
  	SKSE::log::error("{}", e.what());
  }
  ```
- Суть и сценарий: `json.value<T>()` бросает исключение, если ключ есть, но у значения другой тип (`"5"` вместо `5`, `1.5` для I32). Один `try` охватывает весь цикл, поэтому первая же ошибка прерывает загрузку, и все настройки, зарегистрированные после неё, сохраняют базовые значения, хотя в файле они корректны. В лог попадает только текст исключения, без имени ключа и файла. Сценарий: user.json `{"a": "five", "b": 42}` даёт `b = 2`.
- Как проверено: на стенде — `JSON b from user file (expected 42) = 2`.
- Предложение: `try`/`catch` вокруг каждого `setting->Load`, в логе — путь ключа и файл; проверять диапазон (сейчас `U8 = 300` молча превращается в 44).

### X-6. INI: U32 ≥ 2^31 и hex-значения читаются как 2147483647; нет проверки диапазона; дробные сохраняются с 6 знаками
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено (по коду REX.cpp и SimpleIni 4.25; LLP64 — документированное свойство Win64)
- Где: `src/REX/REX.cpp:15`, `:30-31`, `:58-61`
- Код:
  ```cpp
  constexpr bool is_long_integral_v = std::_Is_any_of_v<..., std::uint32_t, ...>;
  a_value = static_cast<T>(file->GetLongValue(a_section.data(), a_key.data(), a_valueDefault));
  // SimpleIni 4.25, GetLongValue:  nValue = strtol(&szValue[2], &pszSuffix, 16);  /  strtol(szValue, &pszSuffix, 10);
  // SimpleIni 4.25, SetDoubleValue: sprintf_s(szInput, "%f", a_nValue);
  ```
- Суть и сценарий: все целые, включая `std::uint32_t`, читаются через `long`, а `long` на Windows 32-битный. При переполнении `strtol` возвращает `LONG_MAX`. `uColor = 0xFF00FF00` (ARGB) превращается в `0x7FFFFFFF`, `4294967295` — в `2147483647`. Запись через `SetLongValue(long)` превращает 3000000000 в `-1294967296`: такое значение читается обратно, но для человека файл непонятен. Диапазон U8/I8/U16/I16 не проверяется: `static_cast<std::uint8_t>(300)` даёт 44. `SetDoubleValue` пишет с форматом `"%f"`, поэтому `F32 = 1e-7` сохраняется как `0.000000`.
- Как проверено: код REX.cpp и исходник SimpleIni v4.25 (`GetLongValue`, `SetLongValue`, `SetDoubleValue`). Воспроизвести на Linux нельзя: там `long` 64-битный.
- Предложение: целые читать через `GetValue` + `std::from_chars` (основание 10 или 16 по префиксу) с проверкой диапазона `T` и логом при ошибке; писать через `std::format("{}")`; для float/double использовать `std::format("{}")`, который даёт кратчайшее точное представление.

### X-7. `SettingStore::Init` хранит `string_view`: use-after-free; пути принимаются только в ANSI
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `include/REX/REX/Setting.h:55-59`, `:67-68`; ключи — `include/REX/REX/INI.h:56-57`, `JSON.h:54`, `TOML.h:73`
- Код:
  ```cpp
  virtual void Init(const char* a_fileBase, const char* a_fileUser) override
  {
  	m_fileBase = a_fileBase;          // std::string_view, владения нет
  	m_fileUser = a_fileUser;
  }
  ```
- Суть и сценарий:
  - Если путь собран во время выполнения (`std::string`, `std::format`, `path::string()`) внутри функции настройки, то после выхода из неё `Load`/`Save` читают освобождённую память.
  - `nullptr` вместо «пользовательского файла нет» — это UB (`string_view(nullptr)`).
  - Пути принимаются только как `const char*` и на MSVC интерпретируются в ANSI-кодовой странице (`std::filesystem::exists(string_view)`, `fopen` в SimpleIni, `std::ifstream(const char*)`). Путь с символами вне CP_ACP открыть невозможно, например `Documents\My Games\…` пользователя с кириллическим именем на английской Windows.
  - Секции и ключи тоже `string_view`, и их `.data()` передаётся как C-строка. Если `string_view` не заканчивается нулём, чтение уйдёт за границу.
- Как проверено: ASan на стенде (`Configure()` с локальными `std::string`) — `heap-use-after-free … in REX::JSON::SettingStore::Load() … REX.cpp:177`.
- Предложение: хранить `std::filesystem::path` (с владением) и принимать `path`/`wstring_view`; секции и ключи хранить как `std::string`.

### X-8. `src/REX/REX.cpp` не компилируется clang/clang-cl при любом `REX_OPTION_*`, и CI этого не ловит
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `src/REX/REX.cpp:18`, `:49`, `:124`, `:150`, `:269`, `:310`; также `:15`
- Код:
  ```cpp
  template <class T>
  void SettingLoad<T>(         // частичная специализация шаблона функции — запрещена
  	void* a_data, sec_t a_section, key_t a_key, T& a_value, T& a_valueDefault)
  ```
- Суть и сценарий: определение шаблона функции с явными аргументами в деклараторе — это частичная специализация функции, которую стандарт запрещает. MSVC такое пропускает, clang — нет. Пресеты clang-cl и linux-clangcl штатные (AGENTS.md советует `--clang` для быстрой итерации), но `REX_OPTION_*` в CI включаются только в `prebuilt.yml`, где собирает MSVC. Пользователь clang-cl с `-DREX_OPTION_INI=ON` получит ошибки компиляции. Попутно `std::_Is_any_of_v` в строке 15 — внутренняя деталь MSVC STL.
- Как проверено: clang 18.1.3, в том числе с `--target=x86_64-pc-windows-msvc -fms-compatibility -fms-extensions`, выдаёт «function template partial specialization is not allowed»; g++ 13 выдаёт ту же ошибку на настоящем REX.cpp. `grep REX_OPTION .github/workflows` — только `prebuilt.yml:87`, `:255`, `:262`.
- Предложение: `void SettingLoad(` без `<T>` (явные инстанциации ниже остаются); вместо `_Is_any_of_v` — `std::disjunction_v<std::is_same<…>…>`; добавить в матрицу сборку clang-cl с `REX_OPTION_*=ON` (X-22).

### X-9. `ComPtr`/`IUnknown`: `As`, `CopyTo<U>`, `QueryInterface<T>` и преобразующие присваивания не компилируются; перемещение не обнуляет источник
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено (clang 18); для MSVC — по тем же правилам языка
- Где: `include/REX/W32/COMPTR.h:61-79`, `:143-147`, `:167-171`; `include/REX/W32/COM.h:14-18`
- Код:
  ```cpp
  return _ptr->QueryInterface(__uuidof(U), reinterpret_cast<void**>(a_ptr->ReleaseAndGetAddressOf()));   // As
  return QueryInterface(*reinterpret_cast<const IID*>(&__uuidof(T)), static_cast<void**>(a_object));   // IUnknown
  template <class U> ComPtr& operator=(const ComPtr<U>& a_other) noexcept { ComPtr(a_other).Swap(*this); ... }
  ComPtr& operator=(ComPtr&& a_other) noexcept { ComPtr(static_cast<ComPtr&&>(a_other)).Swap(*this); ... }
  ```
- Суть и сценарий:
  1. `As<U>` и `CopyTo<U>` передают `__uuidof(U)` типа `const _GUID` туда, где ожидается `const REX::W32::IID&`. Преобразования между ними нет (в самом COM.h для этого сделан `reinterpret_cast`).
  2. `IUnknown::QueryInterface<T>(T**)` делает `static_cast<void**>(T**)`, а такое приведение запрещено.
  3. `operator=(const ComPtr<U>&)` и `operator=(ComPtr<U>&&)` строят `ComPtr<T>` из `ComPtr<U>`, но преобразующих конструкторов нет.
  4. Перемещающего конструктора нет, поэтому «перемещение» — это копия с `AddRef`, и источник, в отличие от WRL, не обнуляется.

  Шаблоны инстанцируются только при вызове, а в репозитории `ComPtr` не используется ни разу, поэтому CI молчит. Первый же плагин с WRL-идиомой `swapChain.As(&swapChain1)` не соберётся.
- Как проверено: clang 18 с `-fms-extensions -fdeclspec` на тестовых `IFoo`/`IBar` — 6 ошибок: «cannot convert … 'const _GUID' to 'const IID'», «static_cast from 'IBar **' to 'void **' is not allowed», «no matching conversion … from 'ComPtr<IBar>' to 'ComPtr<IFoo>'». `grep -rn ComPtr include src tests` — использований нет. `git log -- COMPTR.h` — единственный коммит cd61f6620.
- Предложение: `*reinterpret_cast<const IID*>(&__uuidof(U))`; в `QueryInterface<T>` использовать `reinterpret_cast<void**>`; добавить `ComPtr(ComPtr&&) noexcept`, обнуляющий источник, и `template <class U> requires std::convertible_to<U*, T*>` для конструкторов из `const ComPtr<U>&` и `ComPtr<U>&&`; `explicit operator bool`; тест с фиктивным `IUnknown`-счётчиком.

### X-10. Enum/EnumSet: `Enum::operator=(Enum<E,U2>)` без `return`, `EnumSet::operator~` не компилируется
- Вид: ошибка; Важность: низкая; Уверенность: подтверждено
- Где: `include/REX/REX/Enum.h:35-39`, `include/REX/REX/EnumSet.h:172`
- Код:
  ```cpp
  template <class U2>
  constexpr Enum& operator=(Enum<E, U2> a_rhs) noexcept { _impl = static_cast<U>(a_rhs.get()); }       // нет return
  friend constexpr EnumSet& operator~(EnumSet& a_lhs) noexcept { return a_lhs = ~a_lhs.underlying(); }  // int -> EnumSet
  ```
- Суть и сценарий: у первого оператора выход из не-void функции без `return` — UB; в constexpr-контексте это ошибка, у MSVC C4716 по умолчанию тоже ошибка. Второй оператор присваивает `int` в `EnumSet`, а подходящего `operator=` нет, поэтому `~flags` не компилируется. Если бы компилировался, по своей сигнатуре менял бы сам операнд (`auto m = ~flags;` портило бы `flags`) и не работал бы для `const`. `EnumSet` — база `stl::enumeration` (`include/SKSE/Impl/PCH.h:267`), которой пользуются около 250 заголовков RE.
- Как проверено: clang 18 выдаёт `EnumSet.h:172:79: error: no viable overloaded '='`, `Enum.h:39: warning: non-void function does not return a value`, а в constexpr — «must be initialized by a constant expression». `git log -- EnumSet.h`: последний 90949fb94 («Fix EnumSet») эти строки не затрагивал.
- Предложение: `return *this;`; `friend constexpr EnumSet operator~(EnumSet a) noexcept { return static_cast<E>(static_cast<U>(~a.underlying())); }`; `static_assert`-тесты на все операторы (X-22).

### X-11. `REX_W32_IMPORT` отбрасывает типы параметров; мелкие расхождения W32 с SDK
- Вид: ошибка; Важность: низкая; Уверенность: подтверждено (механизм и расхождения); с HKEY вероятно безвредно
- Где: `include/REX/W32/BASE.h:36-38`; `include/REX/W32/DINPUT.h:462`; `include/REX/W32/ADVAPI32.h:7-9`; `src/REX/W32.cpp:293`, `:313-316`, `:321`, `:327-328`, `:36`, `:362-363`
- Код:
  ```cpp
  #define REX_W32_IMPORT(a_ret, a_name, ...)                                            \
  	extern "C" __declspec(dllimport) a_ret __stdcall W32_IMPL_##a_name(...) noexcept; \
  	__pragma(comment(linker, "/alternatename:__imp_W32_IMPL_" #a_name "=__imp_" #a_name))
  virtual HRESULT CreateEffect(const GUID&, const DIEFFECT*, IDirectInputEffect*, IUnknown*) noexcept = 0;   // в SDK: LPDIRECTINPUTEFFECT*
  ```
- Суть и сценарий:
  - `__VA_ARGS__` в теле макроса не используется, поэтому каждый импорт объявлен как `a_ret f(...)`. Компилятор не проверяет в обёртках ни число, ни типы аргументов, а к `...` применяются стандартные продвижения: `float` стал бы `double`, и вызываемая функция прочитала бы мусор. Сейчас ни один импорт не принимает `float`, и все обёртки передают аргументы в правильном порядке (проверены все), так что пока это риск, а не сбой. Что типы действительно игнорируются, видно по строкам 36 и 362-363: неквалифицированные `BCRYPT_HASH_HANDLE*` и `MEMORY_BASIC_INFORMATION*` в глобальной области компилируются.
  - В `IDirectInputDevice8A::CreateEffect` третий параметр объявлен как `IDirectInputEffect*`, а должен быть `**`: `&effect` не компилируется, а хук неверно типизирует выходной параметр.
  - `HKEY_*` равны `0x80000000`, тогда как в SDK `(HKEY)(ULONG_PTR)(LONG)0x80000000` на x64 равен `0xFFFFFFFF80000000`. Используется это в `REL/Module.h:144`; реестр, судя по `HandleToUlong` в реализациях, принимает оба варианта.
  - 8 обёрток (`CreateFileA`, `GetComputerNameA/W`, `GetCurrentDirectoryA/W`, `GetFileSizeEx`, `GetPrivateProfileIntA/W`) определены в W32.cpp, но ни в одном заголовке не объявлены, поэтому недоступны.
  - Нет `D3D11_SDK_VERSION` (= 7), без которого `D3D11CreateDevice` не вызвать без магического числа.
- Как проверено: чтение; grep по заголовкам на каждое имя; сверка с d3d11.h/dinput.h/winreg.h по памяти SDK.
- Предложение: `W32_IMPL_##a_name(__VA_ARGS__)`, предварительно квалифицировав строки 36 и 362-363 через `REX::W32::`; исправить `CreateEffect`; объявить 8 функций; добавить `D3D11_SDK_VERSION`; `HKEY_*` задавать как `reinterpret_cast<HKEY>(static_cast<std::intptr_t>(static_cast<std::int32_t>(0x80000000)))`.

### X-12. `COMMONLIB_ENABLE_IPO` ничего не делает: IPO не включается никогда
- Вид: ошибка; Важность: низкая; Уверенность: подтверждено
- Где: `CMakeLists.txt:146-153`; флаг в CI — `.github/workflows/main_ci.yml:160`, `:285`
- Код:
  ```cmake
  if(COMMONLIB_ENABLE_IPO)
  	check_ipo_supported(RESULT USE_IPO OUTPUT IPO_OUTPUT)
  	if(USE_IPO)
  		set(CMAKE_INTERPROCEDURAL_OPTIMIZATION "$<$<CONFIG:RELEASE>:ON>")
  	endif()
  endif()
  ```
- Суть и сценарий: свойство `INTERPROCEDURAL_OPTIMIZATION` не вычисляет генераторные выражения: CMake проверяет строку `"$<$<CONFIG:RELEASE>:ON>"` как логическое значение, и она ложна. Комментарий «the real prebuilt/release builds keep it on» неверен; `-DCOMMONLIB_ENABLE_IPO=OFF` в main_ci ничего не меняет, а `check_ipo_supported` зря тратит время конфигурации.
- Как проверено: CMake 3.28, модель: цель с тем же `set(...)` компилируется без `-flto`, а соседняя с `INTERPROCEDURAL_OPTIMIZATION ON` — с `-flto=auto`. Строку ввёл 7133c5e98.
- Предложение: если LTO нужен — `set(CMAKE_INTERPROCEDURAL_OPTIMIZATION_RELEASE ON)`. Но для публикуемого prebuilt-бандла `/GL` включать нельзя: LTCG-объекты требуют ту же сборку cl (C1047), lld-link их не читает, а `cmake/Prebuilt.cmake:31-55` сверяет лишь major.minor и пропускает clang-cl. Честнее удалить опцию или разрешить её только для непубликуемых сборок.

### X-13. Публичный `/wd4996` глушит у всех потребителей собственные `[[deprecated]]` CommonLib, включая режим аудита
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `CMakeLists.txt:197-234` (строка 227, `PUBLIC`), prebuilt — `CMakeLists.txt:90-98` (строка 96, `INTERFACE`)
- Код:
  ```cmake
  target_compile_options("${PROJECT_NAME}" PUBLIC
  	...
  	/wd4996 # 'deprecated function': required due to Microsoft STL itself using its own deprecated functions
  ```
- Суть и сценарий: MSVC сообщает о `[[deprecated]]` именно предупреждением C4996, а clang-cl сопоставляет `/wd4996` с `-Wno-deprecated-declarations`. Опция публичная и доходит до всех потребителей CMake. Поэтому не видны пометки `SKSE/API.h:76`, `:78` (устаревшие `Init(…, bool)`/`AllocTrampoline`), а режим `REL_AUDIT_UNVERIFIED_PATCHES` (`REL/Relocation.h:204-207`, `:311-314`), который целиком держится на этом предупреждении, у потребителей CMake не работает вовсе. В xmake `/wd`-флаги не публичные, и там предупреждения видны.
- Как проверено: чтение; `git blame` — строку добавил 55b4b0bebd.
- Предложение: подавления сделать PRIVATE (для компиляции самой библиотеки); потребителям отдавать только то, что порождают заголовки CommonLib, лучше через `/external:anglebrackets /external:W0`; для STL — точечные `_SILENCE_*_DEPRECATION_WARNING`.

### X-14. `add_commonlibsse_plugin`: нет при сборке из исходников, `EXCLUDE_FROM_ALL` ломает конфигурацию, в пути поиска мусорный каталог
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `CMakeLists.txt:113`; `cmake/CommonLibSSE.cmake:179`, `:189`
- Код:
  ```cmake
  include(cmake/CommonLibSSE.cmake)  # add_commonlibsse_plugin() helper for consumers   (только в prebuilt-ветке, до return())
  target_include_directories("${TARGET}" PUBLIC CommonLibSSE_INCLUDE_DIRS)            # без ${}
  add_library("${TARGET}" SHARED $<$<BOOL:${ADD_COMMONLIBSSE_PLUGIN_EXCLUDE_FROM_ALL}>:EXCLUDE_FROM_ALL>
  ```
- Суть и сценарий:
  1. В ветке сборки из исходников помощник не подключается. Потребитель через `add_subdirectory` получает функцию в CI (на тэге подтягивается prebuilt), а локально или при любом откате на исходники (не тэг, dirty, другой MSVC, офлайн) — «Unknown CMake command add_commonlibsse_plugin». Поэтому `test_consumer_live/CMakeLists.txt:31` подключает файл вручную; `tests/prebuilt-consumer-cmake/CMakeLists.txt:11-13` этого не делает и сломается при откате.
  2. Ключевые слова `add_library` разбираются на этапе configure, поэтому генераторное выражение превращается в имя исходного файла `EXCLUDE_FROM_ALL`.
  3. Без `${}` добавляется каталог `<src>/CommonLibSSE_INCLUDE_DIRS`; для экспортируемой цели это ошибка относительного пути.
- Как проверено: CMake 3.28 с настоящим `CommonLibSSE.cmake`: `INCLUDE_DIRECTORIES = …/CommonLibSSE_INCLUDE_DIRS`; с `EXCLUDE_FROM_ALL` — «Cannot find source file: EXCLUDE_FROM_ALL», «No SOURCES given to target: foo». Последняя правка файла — fd60ebdfe, эти строки она не меняла.
- Предложение: `include(cmake/CommonLibSSE.cmake)` и в ветке исходников; `if(ADD_COMMONLIBSSE_PLUGIN_EXCLUDE_FROM_ALL) set(_efa EXCLUDE_FROM_ALL) endif()` → `add_library(${TARGET} SHARED ${_efa} …)`; строку 179 удалить.

### X-15. xmake: проверка prebuilt запрещает `rex_json`/`rex_toml`, хотя бандл собран с ними
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `xmake.lua:207-227`; `.github/workflows/prebuilt.yml:87`; `PREBUILT.md:34`, `:45-47`, `:90-91`; `tests/prebuilt-consumer/xmake.lua:19-20`
- Код:
  ```lua
  local required = {
      skyrim_se = true, skyrim_ae = true, skyrim_vr = true,
      rex_json = false, rex_toml = false, skse_patch_safety = true,
  }
  -- "rex_json/toml are baked off, so the lib lacks those symbols and they must stay off."
  ```
- Суть и сценарий: бандл собирается с `--rex_json=y --rex_toml=y`, и PREBUILT.md обещает «a consumer may enable any combination». Но `on_config` выдаёт `raise("prebuilt commonlibsse-ng.lib requires rex_json=n …")`. Плагин с JSON- или TOML-настройками падает на configure ровно тогда, когда включается автозагрузка, то есть в CI на тэге; локально, из исходников, он собирается. Проверка появилась в 32e182628, когда JSON и TOML действительно не пеклись, а в 66f257a44 («superset») её не обновили. Самотест включает только `rex_ini`/`skse_xbyak`, поэтому CI расхождения не видит.
- Как проверено: чтение трёх файлов; `git log -S"rex_json = false" -- xmake.lua`.
- Предложение: убрать `rex_json`/`rex_toml` из `required`; в `tests/prebuilt-consumer/xmake.lua` включить оба.

### X-16. `prebuilt.yml`: производное от `workflow_dispatch` значение подставляется в `run:` шаблоном `${{ }}`
- Вид: ошибка; Важность: низкая; Уверенность: подтверждено
- Где: `.github/workflows/prebuilt.yml:94-99`, `:114`, `:146`; `:269-272`, `:293`, `:330`
- Код:
  ```yaml
  ATTACH_TAG: ${{ inputs.attach_tag }} # via env, not template interpolation (injection-safe)
  run: |
    $stage = if ($tag) { "commonlibsse-ng-prebuilt-$tag-all-msvc" } ...
    "bundle=$stage.7z" | Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8
  # шаг публикации:
    gh release upload "$env:ATTACH_TAG" "${{ steps.bundle.outputs.bundle }}" "${{ steps.bundle.outputs.sha }}" --clobber
  ```
- Суть и сценарий: сам `attach_tag` передаётся через `env:`, но выведенные из него `bundle`/`sha` затем текстом вставляются в pwsh-скрипт внутри двойных кавычек. Значение `attach_tag` вида `$(…)` — допустимое имя каталога: на шаге сборки оно остаётся литералом, а на шаге публикации исполняется как подвыражение PowerShell при наличии `GH_TOKEN` с `contents: write`. Это прямое нарушение правила AGENTS.md о передаче таких значений через `env:`. Запустить `workflow_dispatch` может только тот, у кого есть право записи, поэтому практический риск низкий.
- Как проверено: чтение всех 5 workflows. В остальных местах в `run:` через `${{ }}` подставляются только `github.workspace` и `matrix.*`, которые извне не управляются.
- Предложение: `env: BUNDLE: ${{ steps.bundle.outputs.bundle }}` → `"$env:BUNDLE"`; дополнительно проверять `attach_tag` по `^v\d+\.\d+\.\d+$`.

### X-17. Цепочка поставки CI: сторонние actions на перезаписываемых тегах в заданиях с правом записи, версии инструментов не зафиксированы, бандл скачивается потребителями автоматически
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено (конфигурация); сама атака — модель угроз
- Где: `.github/workflows/prebuilt.yml:64-65`, `:75-79`, `:151-152`, `:174`, `:189`, `:247`, `:258`; `release.yml:9-12`, `:53`, `:57-65`; `maintenance.yml:9-11`, `:45`; `main_ci.yml:26-27` и `test-consumer.yml:16-18` (нет `permissions`); `cmake/Prebuilt.cmake:149-158`; `xmake.lua:137-147`
- Код:
  ```yaml
  permissions:
    contents: write # only used when attach_tag is set      (prebuilt.yml, в том числе на pull_request)
  - uses: xmake-io/github-action-setup-xmake@v1
    with: { xmake-version: latest }
  - uses: cycjimmy/semantic-release-action@v5            (release.yml, persist-credentials: true)
    with: { extra_plugins: "@google/semantic-release-replace-plugin\n@semantic-release/changelog\n@semantic-release/git" }
  ```
- Суть и сценарий: сторонние действия (`TheMrMilchmann/setup-msvc-dev@v4.0.0`, `lukka/run-vcpkg@v11`, `lukka/run-cmake@v10`, `nick-fields/retry@v3`, `xmake-io/github-action-setup-xmake@v1`, `cycjimmy/semantic-release-action@v5`, `stefanzweifel/git-auto-commit-action@v7`) закреплены тегами, а не SHA, а теги можно перезаписать. Выполняются они в заданиях с `contents: write`. Версии xmake (`latest`, `xmake repo --update`) и npm-плагинов semantic-release не зафиксированы. Джобы `build-and-test-vcpkg` и `test-consumer` получают права по умолчанию для репозитория.

  Риск усиливает автозагрузка: бандл релиза скачивается в CI потребителей и линкуется в их DLL, а `.sha256` берётся из того же релиза. Такая проверка защищает от порчи при скачивании, но не от подмены. Компрометация любого действия в release/prebuilt даёт подменённую библиотеку во всех плагинах, собираемых на тэге.
- Как проверено: чтение workflows, `Prebuilt.cmake`, `xmake.lua`. Действий на `@main` нет. Загрузки в `build-linux-cross-compile` (llvm.sh, xwin, llvm-mingw) закреплены хэшами — это правильно.
- Предложение: закрепить действия по SHA (и включить Dependabot для actions); на уровне workflow — `permissions: contents: read`, а `write` оставить только отдельному джобу публикации при `attach_tag`; зафиксировать версии xmake и npm-плагинов; подписывать бандл через `actions/attest-build-provenance`, а в `Prebuilt.cmake` и `xmake.lua` проверять происхождение (или хотя бы ключ подписи), а не sha256 из того же релиза.

### X-18. `ENABLE_COMMONLIBSSE_TESTING` задан только тестовому exe: у inline `report_and_error` два разных тела (нарушение ODR)
- Вид: ошибка; Важность: низкая; Уверенность: вероятно (нарушение ODR — факт; проявится ли оно, зависит от линкера)
- Где: `CMakeLists.txt:363-367`; `include/SKSE/Impl/PCH.h:538`, `:590-596`; `src/REL/IDDB.cpp:29-37`; `tests/REL/Relocation.test.cpp:390`, `:438`; `xmake.lua:64-68`, `:269`
- Код:
  ```cpp
  if (a_fail) {
  #ifdef ENABLE_COMMONLIBSSE_TESTING
  	throw std::runtime_error(...);
  #else
  	REX::W32::MessageBoxW(nullptr, body.c_str(), ...);
  	REX::W32::TerminateProcess(REX::W32::GetCurrentProcess(), EXIT_FAILURE);
  #endif
  ```
- Суть и сценарий: в CMake библиотека собирается без макроса (`report_and_error` вызывает MessageBox и TerminateProcess), а тесты — с макросом (`throw`). Получается одна inline-функция с двумя телами. `REQUIRE_THROWS(REL::IDDB::get().id2offset(0xFFFFFFFF))` проверяет код библиотеки (`IDDB.cpp` → `report_and_fail`) и проходит лишь потому, что линкер сейчас оставляет копию COMDAT из объектника теста. После инлайнинга в библиотеке или с ICF/LTCG тест превратится в `TerminateProcess`, и раннер будет молча убит. В xmake опция `tests` публичная, и макрос получает и сама библиотека, то есть две системы сборки тестируют разные бинарники.
- Как проверено: чтение. В `Module.h`/`IDDB.h` под макросом только статические функции, раскладка классов не меняется.
- Предложение: в тестовой конфигурации задавать макрос PUBLIC самой библиотеке (или собирать отдельную цель, см. X-23); либо вынести `report_and_error` из inline в .cpp с переключаемым обработчиком.

### X-19. `scripts/build-all-presets.cmd --clang` прячет текст ошибок компиляции
- Вид: ошибка; Важность: низкая; Уверенность: подтверждено (по формату диагностики clang-cl)
- Где: `scripts/build-all-presets.cmd:112`
- Код:
  ```bat
  type "%TEMP%\build_%%P.log" | findstr /C:"error C" /C:"error LNK" /C:"FAILED"
  ```
- Суть и сценарий: фильтр рассчитан на формат MSVC (`error C2065`). clang-cl пишет `file(12,5): error: …`, где подстроки `error C` нет, поэтому остаются только строки Ninja `FAILED: <obj>`. AGENTS.md и CLAUDE.md советуют именно `--clang` для быстрой итерации — в этом режиме причина ошибки не видна.
- Как проверено: чтение скрипта.
- Предложение: добавить `/C:": error:" /C:"lld-link: error"` или выводить хвост лога.

---

## Неоптимальное

### X-20. Зависимости: vcpkg ставит всё всегда, CMake не ищет зависимости REX/xbyak, xmake и CMake расходятся в версиях и флагах
- Вид: неоптимальное; Важность: средняя; Уверенность: подтверждено
- Где: `vcpkg.json:11-64`; `CMakeLists.txt:3-6`, `:37-39`, `:247-252`, `:276-290`; `xmake.lua:70-92`, `:293-342`; `CMakePresets.json` (`compiler-msvc`)
- Код:
  ```cmake
  find_package(spdlog CONFIG REQUIRED)
  find_path(RAPIDCSV_INCLUDE_DIRS "rapidcsv.h")
  find_package(directxtk CONFIG REQUIRED)      # simpleini / nlohmann_json / toml11 / xbyak не ищутся вовсе
  target_include_directories("${PROJECT_NAME}" PRIVATE ${spdlog_INCLUDE_DIRS} ${RAPIDCSV_INCLUDE_DIRS})
  ```
- Суть и сценарий:
  - a) simpleini, nlohmann-json, toml11 и xbyak — безусловные зависимости (из features есть только `tests`). Их ставят каждый потребитель порта и каждый из 20+ джобов CI, даже когда `REX_OPTION_*` и `SKSE_SUPPORT_XBYAK` выключены.
  - b) При `REX_OPTION_*=ON` CMake не вызывает `find_package` и не линкует парсеры. `<SimpleIni.h>`, `<nlohmann/json.hpp>` и `<toml.hpp>` находятся лишь потому, что `find_path(rapidcsv.h)` и spdlog добавляют в пути поиска общий каталог vcpkg `installed/<triplet>/include`. Вне vcpkg (системные пакеты, FetchContent) опции не соберутся. xmake делает это правильно: `add_requires`/`add_packages` при включённой опции.
  - c) Версии расходятся: в xmake directxmath 2024.02, directxtk 24.2.0, xbyak v7.06 и spdlog с std_format; в vcpkg directxmath ≥ 2025-04-03, directxtk ≥ 2025-10-27, xbyak ≥ 7.28 и fmt.
  - d) Флаги расходятся: в xmake `/Zc:enumTypes`, `/Zc:templateScope`, `/fp:contract`, `/fp:except-`, `/we4715`, `/W4`. У CMake-цели нет ни одного из них; `/W4 /WX` есть только в пресетах и до потребителей `add_subdirectory` не доходят.

  В результате два prebuilt-бандла одного тэга собраны разными версиями зависимостей и с разной семантикой. `/fp:contract` разрешает FMA и меняет результаты вычислений. `/Zc:enumTypes` меняет `underlying_type` перечислений без фиксированного типа со значениями больше `INT_MAX` (например, `DXGI_FORMAT` из-за `DXGI_FORMAT_FORCE_UINT`); размер при этом не меняется.
- Как проверено: чтение перечисленных файлов.
- Предложение: vcpkg features `rex-ini`/`rex-json`/`rex-toml`/`xbyak`; в CMake `if(REX_OPTION_*) find_package(… CONFIG REQUIRED)` + `target_link_libraries(PRIVATE …)`; единый источник версий и флагов (например, `cmake/flags.cmake`, который читает и xmake) или хотя бы проверка расхождений в CI.

### X-21. CI гоняет лишнее: полная матрица на любом PR, каждый тест в ctest выполняется дважды
- Вид: неоптимальное; Важность: низкая; Уверенность: подтверждено (п. 1–2), вероятно (п. 3)
- Где: `.github/workflows/main_ci.yml:15-16`, `:28-42`; `CMakeLists.txt:405-406`
- Код:
  ```cmake
  catch_discover_tests("${PROJECT_NAME}Tests")
  add_test(NAME "${PROJECT_NAME}Tests" COMMAND "${PROJECT_NAME}Tests")
  ```
- Суть и сценарий:
  1. У `push` есть фильтр путей, а у `pull_request` нет. PR, меняющий только README или CHANGELOG, запускает 20 Windows-сборок и ещё около 20 минут `test-consumer`.
  2. `catch_discover_tests` регистрирует каждый `TEST_CASE`, а `add_test` — весь exe ещё раз, поэтому `ctest --preset all` (рекомендован в CLAUDE.md) выполняет каждый тест дважды.
  3. 508 файлов .cpp собираются без unity build. На 20 джобах `CMAKE_UNITY_BUILD` с батчами по 8–16 файлов вероятно заметно сократил бы время, но нужно проверить коллизии имён в анонимных пространствах (не проверял).
- Как проверено: чтение; подсчёт по `cmake/sourcelist.cmake`.
- Предложение: `paths`/`paths-ignore` для `pull_request`; удалить `add_test`; попробовать unity build на одном джобе.

---

## Расширения

### X-22. Нет тестов на REX и на установленный пакет
- Вид: расширение; Важность: средняя; Уверенность: подтверждено
- Где: `cmake/testlist.cmake:1-14`; `test_package/CMakeLists.txt`; `.github/workflows/main_ci.yml:153-161`
- Код:
  ```cmake
  set(TESTS tests/Main.cpp tests/RE/... tests/REL/... tests/SKSE/...)   # ни одного tests/REX/*
  ```
- Суть и сценарий: нет ни одного теста на Setting (INI/JSON/TOML), Enum/EnumSet, ComPtr и раскладки W32-структур. `REX_OPTION_*` не включаются ни в одной конфигурации main_ci. install/find_package не проверяется: test_package заброшен после удаления Conan. X-1…X-10, X-3 и X-14 ловятся короткими тестами.
- Предложение:
  - `tests/REX/Settings.test.cpp` на временном каталоге: round-trip, вложенные секции TOML, неверный тип в JSON, повреждённый базовый файл, пользовательский файл + `Save` → `Load`;
  - `tests/REX/EnumSet.test.cpp` со `static_assert` всех операторов;
  - `tests/REX/ComPtr.test.cpp` с фиктивным `IUnknown` и счётчиком ссылок;
  - `static_assert(sizeof/offsetof)` для D3D11/DXGI/DINPUT-структур по числам из SDK;
  - в матрицу — по одной конфигурации MSVC и clang-cl с `-DREX_OPTION_INI=ON -DREX_OPTION_JSON=ON -DREX_OPTION_TOML=ON`;
  - джоб «`cmake --install` + сборка `test_package`».

### X-23. Цель для юнит-тестов плагинов и минимальный пример плагина
- Вид: расширение; Важность: низкая; Уверенность: подтверждено (отсутствие)
- Где: `include/REL/Module.h:95-190` (`inject`/`mock`/`reset`), `include/REL/IDDB.h:92-133` (`inject`); `examples/` (есть только `linux-cross-compile`)
- Код:
  ```cpp
  #ifdef ENABLE_COMMONLIBSSE_TESTING
  	static bool mock(REL::Version a_version, Runtime a_runtime = Runtime::Unknown, std::wstring_view a_filename = L"SkyrimSE.exe"sv, ...)
  ```
- Суть и сценарий: `REL::Module::mock` и `IDDB::inject` — готовые помощники, чтобы тестировать плагин без игры. Но они доступны только под макросом, который должен быть согласованно задан и библиотеке (см. X-18), а потребитель без пересборки CommonLib этого сделать не может. В `examples/` нет ни одного минимального плагина, хотя README и PREBUILT ссылаются на `add_commonlibsse_plugin` и `REX::INI`.
- Предложение: цель `CommonLibSSE::Testing` — та же библиотека, собранная с `ENABLE_COMMONLIBSSE_TESTING=1` PUBLIC, с описанием для Catch2-тестов плагинов; `examples/minimal-plugin` (CMake + xmake) с PCH, `add_commonlibsse_plugin` и настройкой REX (INI/TOML). Этот пример заодно станет самотестом для X-3, X-14 и X-15.

---

## Проверено и в порядке

- Константы W32 совпадают с SDK:
  - KERNEL32: `MEM_*`, `PAGE_*`, `SECTION_*`, `FILE_MAP_*`, `GENERIC_*`, флаги создания процесса, `LCMAP_*`, `IMAGE_*`;
  - BCRYPT: алгоритмы и свойства;
  - DBGHELP: `UNDNAME_*`;
  - SHELL32: `FOLDERID_Documents/Pictures/ProgramData`, `KF_FLAG_*`;
  - USER32: `GWLP_*`, `WM_*`, `VK_*`;
  - XINPUT: пороги, кнопки, структуры;
  - DINPUT: `DIK_*`;
  - D3D: `D3D_FEATURE_LEVEL`, `D3D_DRIVER_TYPE`;
  - D3D11: `BIND`, `CPU_ACCESS`, `RESOURCE_MISC`, `CREATE_DEVICE`, `MAP`, `COMPARISON`, `BLEND`, `COLOR_WRITE`;
  - D3DCOMPILER: `D3DCOMPILE_*`, `D3D_BLOB_PART`;
  - DXGI: `DXGI_FORMAT` (не хватает только `A4B4G4R4_UNORM` = 191), `SWAP_EFFECT`, `SWAP_CHAIN_FLAG`, `COLOR_SPACE`.
- Раскладки структур:
  - общие: `FILETIME`, `GUID`, `RECT`, `CRITICAL_SECTION` (0x28), `SECURITY_ATTRIBUTES` (0x18), `MEMORY_BASIC_INFORMATION` (0x30), `STARTUPINFOA/W` (0x68), `SYSTEM_INFO` (0x30), `WIN32_FIND_DATAA/W` (0x140/0x250), PE-заголовки;
  - NT: `NT_TIB`, `TEB` (PEB по смещению 0x60), `PEB`, `PEB_LDR_DATA`, `RTL_USER_PROCESS_PARAMETERS`; `NtCurrentTeb` читает `gs:[0x30]`;
  - DXGI/D3D11: `DXGI_*_DESC`, `DXGI_FRAME_STATISTICS`, `D3D11_TEXTURE2D/BUFFER/SAMPLER/RASTERIZER/BLEND/DEPTH_STENCIL/INPUT_ELEMENT/SHADER_RESOURCE_VIEW_DESC`, `D3D11_MAPPED_SUBRESOURCE`, `D3D11_VIEWPORT`;
  - DINPUT: `DIDEVICEOBJECTDATA`, `DIACTIONFORMATA`, `DIDATAFORMAT` и остальные структуры.
- Порядок методов в vtable и IID: `IDXGIObject` … `IDXGIFactory1`, `IDXGISwapChain`, `IDXGIOutput`, `ID3D11DeviceChild`, `ID3D11Device` (40 методов), `ID3D11DeviceContext` (108), `ID3D11ClassInstance`/`ClassLinkage`, `IDirectInput8A`, `IDirectInputDevice8A` (кроме X-11), `IDirectInputEffect`.
- Обёртки W32.cpp:
  - `BOOL` (int32) ↔ `bool` в обе стороны;
  - `INVALID_HANDLE_VALUE` = −1;
  - x64 — одно соглашение о вызове;
  - порядок аргументов во всех ~90 обёртках;
  - ни один импорт не принимает `float` — важно для X-11;
  - `/alternatename` поддерживается и link.exe, и lld-link.
- `REX::Singleton`: статик в функции даёт потокобезопасную инициализацию; `/Zc:threadSafeInit-` нигде не задан. Регистрация `TSetting` из глобальных конструкторов идёт через этот статик, и порядок разрушения корректен.
- `EnumSet`: `set`/`reset`/`any`/`all`/`none`, сравнения, побитовые операторы при беззнаковом и знаковом `U` — кроме `operator~` (X-10).
- `cmake/Prebuilt.cmake`: проверка CRT (`/MD`), конфигурации Release, полноты бандла, SHA256 при скачивании (как защита от порчи), откат на исходники, маркер `.failed`. Вопросы только в X-12, X-14 и X-17.
- Workflows:
  - `${{ }}` в `run:` — кроме X-16, подставляются только `github.workspace` и `matrix.*`;
  - кэши vcpkg для PR из форков — только restore;
  - код PR в `prebuilt.yml` checkout-ится с `persist-credentials: false`;
  - `maintenance.yml` не запускается на PR из форков;
  - внешние загрузки в `build-linux-cross-compile` и в overlay-порте directxtk закреплены хэшами.
- `cmake/sourcelist.cmake` синхронен с деревом: 508 .cpp и 2105 .h, расхождений нет. rapidcsv используется только под `ENABLE_SKYRIM_VR`, и CMake с xmake здесь согласованы. `HAS_SKYRIM_MULTI_TARGETING` вычисляется одинаково в обеих системах сборки.
- Среди `origin/*` исправлений для перечисленных находок нет. `fix/d3d11-rex-w32-alignment` касается RE-заголовков, `fix/prebuilt-*` — закрепления раннера и toolset, `feat/ci-speedups` — старая версия IPO-опции.
