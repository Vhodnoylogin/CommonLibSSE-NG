# CommonLibSSE-NG 9.1.0 (a898f4698): связка с Papyrus и регистрации событий SKSE — находки

Область: `RE::BSScript` (NativeFunction/NativeLatentFunction, PackUnpack, TypeTraits, Variable, Array, reference_array, Object, ObjectTypeInfo, Stack/StackFrame, IVirtualMachine/Internal::VirtualMachine, FunctionArguments, IObjectHandlePolicy), `SKSE::RegistrationSet/SetUnique/Map/MapUnique`, `SKSE::Impl::VMArg` (RegistrationTraits.h).
Пути — от корня клона. Всё прочитано по коду ветки `ng`; сборкой и в игре не проверялось. Для сверки с эталоном использован исходник SKSE64 (github.com/ianpatt/skse64, `skse64/PapyrusEvents.h/.cpp`, `skse64/PapyrusVM.h`, ветка master).

Итого: 19 находок — ошибок 15, неоптимального 2, расширений 2.

---

## Ошибки

### P-1. RegistrationMap<std::string>: фильтр читается в reserve(), после загрузки все регистрации попадают под ключ ""
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено
- Где: `include/SKSE/RegistrationMap.h:440-446` (LoadFilter), запись — `include/SKSE/RegistrationMap.h:390-393` (SaveFilter), использование — `include/SKSE/RegistrationMap.h:467-479`
- Код:
  ```cpp
  std::size_t length = 0;
  if (!a_intfc->ReadRecordData(length)) {
  	return false;
  }
  a_filter.reserve(length);
  return a_intfc->ReadRecordData(a_filter.data(), static_cast<std::uint32_t>(length));
  ```
- Суть и сценарий: `reserve()` не меняет `size()`. Байты пишутся в буфер за пределами размера строки (формально UB), а сама строка `filter` (объявлена один раз `Filter filter{};` перед циклом) остаётся пустой. Затем `_regs[filter].insert(handle)` кладёт каждую загруженную регистрацию под ключ `""`. Сценарий: `SKSE::RegistrationMap<std::string, ...> regs("OnMyEvent")`, скрипт регистрируется на фильтр `"Foo"`, игрок сохраняется и загружается. После этого `SendEvent("Foo", ...)` не находит ключ, и события молча перестают приходить. Даже при `resize()` ключ был бы неверным: SaveFilter пишет `length()+1` байт вместе с `'\0'`, и строка получилась бы `"Foo\0"` ≠ `"Foo"`.
- Как проверено: прочитаны SaveFilter/LoadFilter/Load; `git log -5` по файлу (последняя правка 89eaa7524 этот участок не меняла); веток с исправлением нет (`git branch -r | grep -i regist`).
- Предложение (формат co-save не меняется):
  ```cpp
  if (a_intfc->ReadRecordData(length) != sizeof(length) || length == 0 || length > kMaxFilterLength) return false;
  a_filter.resize(length);
  if (a_intfc->ReadRecordData(a_filter.data(), static_cast<std::uint32_t>(length)) != length) return false;
  a_filter.pop_back();  // сохранённый '\0'
  return true;
  ```

### P-2. SendEvent в регистрациях: MakeFunctionArguments делает new на каждый handle, и объект никто не удаляет (утечка)
- Вид: ошибка; Важность: высокая; Уверенность: вероятно
- Где: `include/SKSE/RegistrationSet.h:89-96`, `include/SKSE/RegistrationSetUnique.h:94-100`, `include/SKSE/RegistrationMap.h:102-108`, `include/SKSE/RegistrationMapUnique.h:110-116`, те же `<void>`-версии (`RegistrationSet.h:145-148` и т.д.); фабрика — `include/RE/F/FunctionArguments.h:79-89`
- Код:
  ```cpp
  for (auto& handle : _handles) {
  	auto copy = std::make_tuple(a_args...);
  	std::apply([&](auto&&... a_copy) {
  		auto args = RE::MakeFunctionArguments(std::forward<Args>(a_copy)...);   // new FunctionArguments<...>
  		vm->SendEvent(handle, eventName, args);
  	}, copy);
  }
  ```
- Суть и сценарий: указатель из `new` передаётся в `IVirtualMachine::SendEvent` (слот 0x24) и больше нигде не освобождается. По двум признакам ВМ этими аргументами не владеет:
  1. Сама библиотека: `SkyrimVM::SendAndRelayEvent` (`src/RE/S/SkyrimVM.cpp:28-32`) передаёт один и тот же `a_args` сначала в `SendEvent`, потом в `RelayEvent`. Если бы ВМ удаляла аргументы, это было бы использование после освобождения.
  2. SKSE64 вызывает тот же слот 0x24 (`VMClassRegistry::QueueEvent`, `PapyrusVM.h:260`) с временным объектом на стеке. Объект создаётся один на все регистрации (`PapyrusEvents.cpp:52-75, 177-180`: `registry->QueueEvent(reg.handle, &eventName, this)`). Значит, ВМ копирует аргументы синхронно и объект не удаляет.

  Следствие: на каждое событие и каждый зарегистрированный handle в куче игры теряется `FunctionArguments<Args...>` вместе с содержимым. Если среди аргументов есть `std::string`, теряется и его буфер. Если есть `RE::BSFixedString`, счётчик ссылок записи пула строк не уменьшается, и строка не выгружается из пула. Для частых событий (анимация, ввод, OnUpdate-подобные) память растёт непрерывно. Попутно `make_tuple` копирует все аргументы заново для каждого handle.
- Как проверено: прочитаны FunctionArguments.h, все четыре SendEvent и SkyrimVM.cpp. Индекс слота в SKSE64 посчитан по порядку объявлений `VMClassRegistry`: QueueEvent = 0x24, в CommonLib `SendEvent // 24`. Нужна проверка: в Ghidra убедиться, что `BSScript::Internal::VirtualMachine::SendEvent` не вызывает слот 0 (удаляющий деструктор) у `a_args`; в игре — точка останова или лог в `~FunctionArguments` не срабатывает. Для `DispatchStaticCall/DispatchMethodCall*` владение нужно проверить отдельно.
- Предложение: один объект на стеке на всё событие, без копий под каждый handle:
  ```cpp
  RE::BSScript::FunctionArguments<void, Args...> args(Args(a_args)...);   // для <void>: RE::BSScript::ZeroFunctionArguments args;
  for (auto handle : handles) { vm->SendEvent(handle, eventName, &args); }
  ```
  Кроме того, задокументировать владение у `MakeFunctionArguments` или возвращать из неё `std::unique_ptr`.

### P-3. SendEvent обходит _handles/_regs без блокировки; PersistHandle вызывается вне блокировки
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено
- Где: `include/SKSE/RegistrationSet.h:84-97, 139-150`; `include/SKSE/RegistrationSetUnique.h:87-104, 147-160`; `include/SKSE/RegistrationMap.h:96-112, 154-166`; `include/SKSE/RegistrationMapUnique.h:101-122, 164-181`; вставка — `src/SKSE/RegistrationSet.cpp:221-227` (и аналоги: `RegistrationSetUnique.cpp:295-301`, `RegistrationMap.h:511-517`, `RegistrationMapUnique.h:619-625`)
- Код:
  ```cpp
  inline void SendEvent(Args... a_args) {            // RegistrationSet.h:84
  	RE::BSFixedString eventName(_eventName);
  	auto vm = RE::BSScript::Internal::VirtualMachine::GetSingleton();
  	for (auto& handle : _handles) {                 // без _lock
  // RegistrationSet.cpp:221
  _lock.lock(); auto result = _handles.insert(handle); _lock.unlock();
  if (result.second) { policy->PersistHandle(handle); }
  ```
- Суть и сценарий: все изменяющие методы берут `_lock` (recursive_mutex), а единственный читатель, SendEvent, его не берёт. Натив `RegisterForX`/`UnregisterForX` работает в потоке Papyrus: зарегистрирован с `callableFromTasklets = true`, как в SKSE64 (`kFunctionFlag_NoWait`). В это же время главный поток (обработчик события или задача QueueEvent) обходит `std::set`/`std::map`. Вставка перестраивает красно-чёрное дерево, удаление освобождает узел, на котором стоит итератор. Итог: пропуск или повтор handle, бесконечный цикл, крах. Обработчики `BSAnimationGraphEvent` к тому же вызываются из параллельных потоков обновления анимации. SKSE64 держит блокировку на всё время обхода (`PapyrusEvents.h:400-408`, ForEach). Вторая гонка: между `unlock()` и `PersistHandle()` другой поток успевает выполнить Unregister/Clear и ReleaseHandle. После этого Persist не имеет пары, и объект handle навсегда остаётся «persistent». В SKSE64 AddRef вызывается под блокировкой (`PapyrusEvents.h:340-344`).
- Как проверено: прочитаны все 8 SendEvent и 4 Register; `git log -5` — правок блокировок не было.
- Предложение: в SendEvent под `Locker` скопировать handles в `std::vector<RE::VMHandle>` и отправлять уже по копии, вне блокировки. Для *Unique — снимок `it->second`. `PersistHandle` вызывать под `_lock` сразу после успешной вставки.

### P-4. Load(): результаты ReadRecordData не проверяются, счётчики не инициализированы и не ограничены
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `src/SKSE/RegistrationSet.cpp:179-197`; `src/SKSE/RegistrationSetUnique.cpp:244-271`; `include/SKSE/RegistrationMap.h:457-485` (и `438-455`); `include/SKSE/RegistrationMapUnique.h:553-593` (`eventFilter.Load(a_intfc)` без проверки, строка 579)
- Код:
  ```cpp
  std::size_t numRegs;
  a_intfc->ReadRecordData(numRegs);          // возвращает число прочитанных байт — игнорируется
  ...
  for (std::size_t i = 0; i < numRegs; ++i) {
  	a_intfc->ReadRecordData(handle);
  	if (a_intfc->ResolveHandle(handle, handle)) {
  ```
- Суть и сценарий: запись может оказаться короче ожидаемой. Так бывает, если плагин сменил формат и не проверил версию, если co-save обрезан из-за краха во время сохранения или если передана запись другого типа. Тогда ReadRecordData возвращает 0, `numRegs` содержит мусор со стека, и цикл до 2^64 итераций «висит» при загрузке. При повреждённой длине строкового фильтра `reserve(length)` бросает `std::length_error`/`bad_alloc` сквозь C-колбэк SKSE, игра падает. После 89eaa7524 неудачное чтение фильтра больше не прерывает загрузку: чтение продолжается со сдвинутой позиции, и в карту попадают мусорные регистрации. Это прямо противоречит `AGENTS.md`, раздел «Security & input validation»: «malformed input must not crash or corrupt state». SKSE64 проверяет каждое чтение и возвращает false (`PapyrusEvents.h:437-470`).
- Как проверено: прочитаны все четыре Load; сигнатура `std::uint32_t ReadRecordData(T&)` — `include/SKSE/Interfaces.h:312-316`.
- Предложение: вспомогательная `template <class T> bool ReadExact(T& v) { return a_intfc->ReadRecordData(v) == sizeof(T); }`; при любой ошибке писать в лог и делать `return false`. Счётчики инициализировать нулём и ограничивать остатком длины записи (из `GetNextRecordInfo`) или константой.

### P-5. Load() не вызывает PersistHandle для загруженных handle, а Clear/Unregister/деструктор вызывают ReleaseHandle
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено (дисбаланс виден по коду; последствия в игре — вероятно)
- Где: `src/SKSE/RegistrationSet.cpp:188-194` (сравнить с `221-227` и `135-146`); то же в `src/SKSE/RegistrationSetUnique.cpp:262-267`, `include/SKSE/RegistrationMap.h:476-481`, `include/SKSE/RegistrationMapUnique.h:583-587`
- Код:
  ```cpp
  for (std::size_t i = 0; i < numRegs; ++i) {
  	a_intfc->ReadRecordData(handle);
  	if (a_intfc->ResolveHandle(handle, handle)) {
  		_handles.insert(handle);            // Persist нет
  	}
  }
  ```
- Суть и сценарий: остальной код класса держит инвариант «каждый handle в наборе persisted ровно один раз». Register и конструктор копирования вызывают Persist, Unregister/Clear/деструктор — Release. Load нарушает инвариант. После загрузки `UnregisterForX` или следующий Revert вызывают `ReleaseHandle(h)` без парного Persist. Счётчик persist в `SkyrimScript::HandlePolicy` один на handle и общий для SKSE, других плагинов и движка, поэтому уменьшается чужая ссылка. Созданная ссылка (0xFF), на которую зарегистрирован плагин, после загрузки не удерживается и может быть выгружена или удалена. Регистрация тогда тихо перестаёт работать. SKSE64 при загрузке делает `policy->AddRef(reg.handle)` (`PapyrusEvents.h:283-291` для карт, `458-466` для наборов).
- Как проверено: сравнение Register/Load/Clear во всех четырёх классах и с SKSE64. Нужна проверка в игре: счётчик persist у handle до и после «загрузка → Unregister».
- Предложение: во всех Load писать `if (set.insert(handle).second) { policy->PersistHandle(handle); }` (policy получать один раз до цикла).

### P-6. RegistrationMap<std::uint32_t>: любой фильтр типа uint32_t считается FormID и проходит ResolveFormID
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `include/SKSE/RegistrationMap.h:447-451`; `include/RE/B/BSCoreTypes.h:5`
- Код:
  ```cpp
  } else if constexpr (std::is_same_v<RE::FormID, Filter>) {   // RE::FormID == std::uint32_t
  	if (!a_intfc->ReadRecordData(a_filter)) {
  		return false;
  	}
  	return a_intfc->ResolveFormID(a_filter, a_filter);
  ```
- Суть и сценарий: `using FormID = std::uint32_t`, поэтому ветка срабатывает для любого фильтра `std::uint32_t`: хеша имени события, битовой маски, упакованного значения. Пример: фильтр `0x9A3C21F0` (CRC32 строки). При загрузке старший байт `0x9A` читается как индекс мода. Если такого индекса нет, ResolveFormID возвращает false, и регистрации отбрасываются. Если порядок модов изменился, фильтр переписывается в другое число и больше никогда не совпадёт. Коды клавиш (< 0x100) уцелевают только потому, что индекс 0 — Skyrim.esm.
- Как проверено: прочитан LoadFilter, найден тип FormID.
- Предложение: признак `template <class F> inline constexpr bool resolve_filter_as_formid_v = std::is_same_v<F, RE::FormID>;` с возможностью переопределить (или строгий тип `enum class FormIDFilter : RE::FormID`). Прежнее поведение оставить по умолчанию и описать ловушку в комментарии к `RegistrationMap`.

### P-7. Variable::operator=(const Variable&) после Cleanup() скалярного типа оставляет мусор в value.p, Assign() освобождает его как указатель
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `src/RE/V/Variable.cpp:48-55`, `322-349` (Cleanup), `351-361` (Assign)
- Код:
  ```cpp
  Cleanup();          // kInt/kFloat/kBool: break — value.p не обнуляется
  Assign(a_rhs);
  ...
  case Type::kObject: value.obj = a_rhs.value.obj; break;   // BSTSmartPointer::operator= → TryDetach(старый p)
  case Type::kString: value.str = a_rhs.value.str; break;   // BSFixedString::operator= → try_release(старый p)
  ```
- Суть и сценарий: у скаляров Cleanup ничего не делает, и в `value.p` остаётся число: `SetSInt(5)` → `p == 0x5`, `SetBool(true)` → `0x1`, `SetFloat(1.f)` → `0x3F800000`. Затем Assign присваивает членам union obj/str/arr. Присваивание `BSTSmartPointer`/`BSFixedString` сначала освобождает «старое» значение (`BSTSmartPointer.h:113-121`, `BSFixedString.h:60-68`), и это приводит к DecRef/`BSStringPool::release` по адресу 0x5 — access violation. Пример: `Variable a; a.SetSInt(5); Variable b; b.SetString("x"); a = b;` — крах. То же происходит при копирующем присваивании `std::vector<Variable>` и при `(*array)[i] = var`, если в элементе лежал ненулевой скаляр. Конструктор копирования не падает, потому что начинает с `value()` (p = nullptr).
- Как проверено: прочитаны Variable.cpp, BSTSmartPointer.h (TryDetach обнуляет только ненулевой _ptr), BSFixedString.h.
- Предложение: одна строка в конце `Variable::Cleanup()` — `value.p = nullptr;`. ChangeType и move-присваивание и так перезаписывают p, поведение для них не меняется.

### P-8. Array::empty() возвращает инвертированный результат
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `src/RE/A/Array.cpp:136-139`
- Код:
  ```cpp
  [[nodiscard]] bool Array::empty() const noexcept
  {
  	return size() > 0;
  }
  ```
- Суть и сценарий: `if (arr->empty()) return;` в нативе выходит именно тогда, когда массив НЕ пуст. `std::ranges::empty(*arr)` и любые алгоритмы, опирающиеся на `empty()`, тоже получают обратный ответ.
- Как проверено: `git log -L` — строка не менялась с первого появления файла (76f448572); веток с исправлением нет.
- Предложение: `return size() == 0;`

### P-9. reference_array::operator=(const Variable*) дописывает элементы без очистки, и do_wrap пишет за границу массива ВМ
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `include/RE/R/ReferenceArray.h:58-62`, `131-142` (do_unwrap), `121-129` (do_wrap)
- Код:
  ```cpp
  reference_array& operator=(const Variable* a_wrapped) { do_unwrap(a_wrapped); return *this; }
  ...
  if (_wrapped != arr) {
  	_wrapped = std::move(arr);
  	_unwrapped.reserve(_wrapped->size());
  	for (auto& elem : *_wrapped) { _unwrapped.push_back(elem.Unpack<value_type>()); }   // старые элементы не удалены
  ```
- Суть и сценарий: `reference_array<int> ra(varA);` (10 элементов), затем `ra = varB;` (3 элемента). В `_unwrapped` оказывается 13 элементов, а `_wrapped` указывает на B. Деструктор вызывает do_wrap, который пишет 13 Variable в `B->_data[0..12]`. `Array::operator[]` проверяет индекс только через assert, поэтому в релизе 10 элементов записываются за пределы выделенного движком блока — порча кучи. Изменения в A при этом теряются: перед переключением do_wrap не вызывается.
- Как проверено: прочитан ReferenceArray.h целиком; `git log -3` — только форматирование.
- Предложение: в `operator=(const Variable*)` сначала `do_wrap(); _unwrapped.clear(); _wrapped.reset();`, затем do_unwrap. В do_wrap ограничить длину `std::min<std::size_t>(_unwrapped.size(), _wrapped->size())`.

### P-10. reference_array::do_wrap записывает null-формы как нетипизированный None (исправление #337 сюда не распространено)
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `include/RE/R/ReferenceArray.h:121-129`; для сравнения — `include/RE/P/PackUnpackImpl.h:54-63` (e44731e04, #337)
- Код:
  ```cpp
  for (std::uint32_t i = 0; i < SIZE; ++i) {
  	(*_wrapped)[i].Pack(_unwrapped[i]);     // null → PackHandle → a_dst->SetNone()
  }
  ```
- Суть и сценарий: натив `void F(RE::StaticFunctionTag*, RE::reference_array<RE::Actor*> a)` вызывают с `Actor[]`, где есть None (например, свежий `new Actor[5]`). На выходе do_wrap переписывает все элементы, в том числе нетронутые. Null-элементы получают тип kNone вместо типа элемента массива. Именно этот симптом исправлял #337: «an untyped None here silently rejects later in-script reassignment». После вызова `arr[0] = someActor` в скрипте молча не срабатывает.
- Как проверено: сопоставлены PackHandle (`src/RE/P/PackUnpack.cpp:48-57`: сначала SetNone(), при `!a_src` — return) и ветка для форм в PackValue массива.
- Предложение: в do_wrap для `is_form_pointer_v<T>` писать `if (_unwrapped[i]) Pack(...); else (*_wrapped)[i] = Variable(_wrapped->type_info());`. Ещё лучше переписывать только изменённые элементы.

### P-11. Unique-регистрации: ключ — текущая цель алиаса; после смены или очистки алиаса отменить регистрацию нельзя
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `src/SKSE/RegistrationSetUnique.cpp:116-128, 158-170` (алиас), `333-351` (`Unregister(VMHandle)`), `323-330` (пустые множества); `include/SKSE/RegistrationMapUnique.h:329-342, 374-387, 415-426`
- Код:
  ```cpp
  bool RegistrationSetUniqueBase::Unregister(RE::BGSRefAlias* a_alias) {
  	const auto target = a_alias->GetActorReference();          // текущая цель, а не та, что была при Register
  	const auto formID = target ? target->GetFormID() : 0;
  	if (formID != 0) { return Unregister(a_alias, formID, RE::BGSRefAlias::VMTYPEID); }
  	return false;
  ```
- Суть и сценарий: скрипт ReferenceAlias вызывает `RegisterForX()`, пока алиас указывает на NPC A, и получает `_regs[A] = {h}`. Затем квест делает `ForceRefTo(B)` или `Clear()`, и скрипт вызывает `UnregisterForX()`. Поиск идёт в `_regs[B]` или вовсе не выполняется (цель null), поэтому возвращается false. Запись для A остаётся: скрипт продолжает получать события про A, handle остаётся persisted и навсегда сохраняется в co-save. Повторный Register после смены цели кладёт h и в `_regs[B]`. Очевидный путь очистки `RegistrationSetUniqueBase::Unregister(RE::VMHandle)` (например, из SetFormDeleteCallback) удаляет h только из первого найденного множества и сразу возвращается. `RegistrationMapUnique::UnregisterAll(VMHandle)` обходит все. Дополнительно:
  - алиас с не-актёром (сундук, дверь) зарегистрироваться не может (`GetActorReference()` == null), хотя перегрузка для `TESForm*` принимает любую ссылку;
  - опустевшие множества из карты не удаляются и до перезагрузки пишутся в co-save.
- Как проверено: прочитаны все Register/Unregister/UnregisterAll в двух Unique-классах; `BGSRefAlias.h:150-151`.
- Предложение: Unregister/UnregisterAll для алиаса вести по handle и обходить все цели, как `UnregisterAll(RE::VMHandle)`. В `SetUnique::Unregister(VMHandle)` убрать ранний return. Удалять пустые множества после erase. Для цели алиаса использовать `GetReference()`.

### P-12. QueueEvent хранит невладеющие аргументы: string_view/const char*, ActiveEffect*, цель a_target
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `include/SKSE/Impl/RegistrationTraits.h:43-73` (VMArg по умолчанию хранит T как есть), `108-111`; `include/SKSE/RegistrationSetUnique.h:106-116`, `include/SKSE/RegistrationMapUnique.h:124-134`; допуск типов — `include/RE/C/CommonTypeTraits.h:278-281`
- Код:
  ```cpp
  template <class T> struct is_string_convertible : std::is_convertible<T, std::string_view> {};  // string_view, const char* проходят
  ...
  task->AddTask([a_target, args, this]() mutable {        // RegistrationSetUnique.h:112 — сырой TESObjectREFR*
  	SendEvent_Tuple(a_target, std::move(args), ...);
  ```
- Суть и сценарий: QueueEvent откладывает отправку в задачу главного потока. Объекты-ссылки в аргументах защищены `NiPointer` (специализация VMArg для объектов), остальные типы — нет:
  - A) `RegistrationSet<std::string_view>` или `<const char*>` проходит `is_return_convertible`. В `regs.QueueEvent(localString)` VMArg сохраняет view. К моменту выполнения задачи строка уже уничтожена: ВМ получает мусор или падает.
  - B) `RegistrationSet<RE::ActiveEffect*>::QueueEvent(effect)`: эффект завершается и удаляется до задачи, после чего PackHandle → GetHandleForObject читает освобождённую память.
  - C) в *Unique-классах `a_target` хранится сырым указателем. Если ссылку удалили (снаряд, временная или удалённая созданная ссылка), `a_target->GetFormID()` обращается к освобождённой памяти.

  Попутно: VMArg для форм делает `static_cast` после `LookupByID` без проверки типа (`RegistrationTraits.h:108-111`), а переиспользованный динамический FormID даёт объект чужого типа. `<void>`-версии QueueEvent (`RegistrationSet.h:152-159` и аналоги) разыменовывают `task` без проверки на null, хотя вариадические проверяют.
- Как проверено: прослежены вывод типов `VMArg(T&&) -> VMArg<T>`, выбор специализаций и тип хранения.
- Предложение: специализация VMArg для строковых типов, которая хранит `std::string`. Для `ActiveEffect*` — static_assert или хранение VMHandle. `a_target` захватывать как FormID (или NiPointer). В VMArg для форм — `RE::TESForm::LookupByID<std::remove_pointer_t<value_type>>(_formID)`. В `<void>`-QueueEvent — `if (task)`.

### P-13. Variable::SetString(std::string_view) и PackValue игнорируют длину view; const char* == nullptr приводит к крашу
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `src/RE/V/Variable.cpp:309-313`; `include/RE/P/PackUnpack.h:89-99`; первопричина — `include/RE/B/BSFixedString.h:97-104` (и `50-56`)
- Код:
  ```cpp
  void Variable::SetString(std::string_view a_val) {
  	ChangeType(TypeInfo::RawType::kString);
  	value.str = a_val;                      // BSFixedString::operator=(const T&) → ctor(view.data())
  }
  ```
- Суть и сценарий: BSFixedString строится по `view.data()` как по C-строке, длина view теряется. Натив `std::string_view F(RE::StaticFunctionTag*, RE::BSFixedString s) { return std::string_view(s).substr(0, 3); }` возвращает в Papyrus всю строку, а не три символа. View на буфер без терминатора читается за его концом до ближайшего `'\0'`. `const char*` проходит `is_string_convertible`, и возврат nullptr из натива превращается в `std::string_view(nullptr)`, то есть в `strlen(nullptr)` и краш.
- Как проверено: прослежена цепочка PackValue → SetString → BSFixedString::operator=(const T&).
- Предложение: в `SetString(std::string_view)` строить строку через `std::string(a_val)`. Добавить перегрузки `SetString(const BSFixedString&)` и null-безопасную `SetString(const char*)`. Первопричину (конструктор и присваивание BSFixedString из string_view) исправлять отдельно — это вне этой области.

### P-14. Awaitable: потерянное пробуждение и гонка на pending/continuation
- Вид: ошибка; Важность: низкая; Уверенность: вероятно
- Где: `src/RE/I/IVirtualMachine.cpp:12-20, 34-56`
- Код:
  ```cpp
  void IVirtualMachine::Awaitable::CallbackFunctor::operator()(Variable a_result) {
  	pending = false; result = a_result;
  	if (continuation) { continuation.resume(); }       // continuation не сбрасывается
  }
  void IVirtualMachine::Awaitable::await_suspend(std::coroutine_handle<> a_handle) {
  	auto& continuation = ...; if (continuation) { continuation.destroy(); } continuation = a_handle; }
  ```
- Суть и сценарий: корутина в потоке T1 делает `co_await vm->ADispatchStaticCall(...)`. `await_ready()` видит `pending == true`. Между await_ready и присваиванием continuation в await_suspend поток ВМ T2 завершает вызов: operator() ставит `pending = false` и не находит continuation. После этого T1 сохраняет handle, и корутина больше не возобновится (утечка или зависание). `pending` и `continuation` — обычные поля без атомарности, это гонка данных. Копии Awaitable разделяют один callback: если дождаться двух копий, await_suspend уничтожит кадр первой корутины. Возможно при T1 ≠ T2: co_await внутри tasklet-натива или в потоке плагина.
- Как проверено: чтение кода; нужна проверка в игре (co_await из натива с `callableFromTasklets = true` под нагрузкой).
- Предложение: `std::atomic<int> state` (0 — ожидание, 1 — приостановлен, 2 — готово) и `bool await_suspend`: сохранить handle, затем `return state.exchange(1) != 2;`. В operator(): `if (state.exchange(2) == 1) std::exchange(continuation, {}).resume();`. `destroy()` убрать.

### P-15. TraceStack: у IVirtualMachine и VirtualMachine разные аргументы по умолчанию (kError и kInfo)
- Вид: ошибка; Важность: низкая; Уверенность: подтверждено
- Где: `include/RE/I/IVirtualMachine.h:67`; `include/RE/V/VirtualMachine.h:75`
- Код:
  ```cpp
  virtual void TraceStack(const char* a_str, VMStackID a_stackID, Severity a_severity = Severity::kError) = 0;   // IVirtualMachine
  void TraceStack(const char* a_str, VMStackID a_stackID, Severity a_severity = Severity::kInfo) override;        // Internal::VirtualMachine
  ```
- Суть и сценарий: аргумент по умолчанию выбирается по статическому типу указателя. В нативе с длинной сигнатурой `(RE::BSScript::IVirtualMachine* a_vm, VMStackID, ...)` вызов `a_vm->TraceStack("bad arg", id)` пишет ошибку. Тот же вызов через `Internal::VirtualMachine*` (GetSingleton() или натив с таким типом первого параметра) пишет Info, и сообщение теряется среди информационных.
- Как проверено: сравнение объявлений.
- Предложение: в VirtualMachine.h убрать аргумент по умолчанию или поставить kError, как в базе.

---

## Неоптимальное

### P-16. BSFixedString ↔ Variable идут через string_view и каждый раз заново ищутся в пуле строк
- Вид: неоптимальное; Важность: средняя; Уверенность: подтверждено
- Где: `include/RE/P/PackUnpack.h:198-207` (UnpackValue для строк), `89-99` (PackValue); `include/SKSE/RegistrationSet.h:86` (и `141`; в остальных трёх классах — аналогично); `include/RE/R/ReferenceArray.h:121-129`
- Код:
  ```cpp
  return T{ a_src->GetString() };                 // T = BSFixedString: BSFixedString(string_view) → ctor8 → поиск в пуле
  a_dst->SetString(std::forward<T>(a_src));        // BSFixedString → string_view → снова поиск в пуле
  RE::BSFixedString eventName(_eventName);         // на каждый SendEvent
  ```
- Суть и сценарий: `RE::BSFixedString` — самый частый строковый тип в нативах. Каждый такой параметр и возврат, а также каждый SendEvent (имя события хранится как std::string) выполняют полный поиск в BSStringPool: хеш строки без учёта регистра, блокировку корзины, сравнение. Хватило бы атомарного инкремента счётчика уже существующей записи `value.str`. `reference_array<BSFixedString>::do_wrap` заново упаковывает все элементы. Копии аргументов под каждый handle в SendEvent — см. P-2.
- Как проверено: прослежен выбор перегрузок PackValue/UnpackValue для BSFixedString.
- Предложение: невиртуальные методы `const BSFixedString& Variable::GetFixedString() const` и `SetString(const BSFixedString&)` (раскладка не меняется), отдельные перегрузки Pack/Unpack для BSFixedString. В регистрациях кешировать BSFixedString имени события лениво, при первом SendEvent под `_lock`.

### P-17. PackHandle/BindID: повторные поиски типа и handle, временные BSFixedString из GetName()
- Вид: неоптимальное; Важность: низкая; Уверенность: подтверждено
- Где: `src/RE/P/PackUnpack.cpp:48-81` (PackHandle), `27-46` (BindID)
- Код:
  ```cpp
  if (!vm || !vm->GetScriptObjectType(a_typeID, classPtr) || !classPtr) { return; }   // поиск типа на каждую упаковку
  auto handle = policy->GetHandleForObject(a_typeID, a_src);
  if (!vm->FindBoundObject(handle, classPtr->GetName(), objectPtr)) {
  	if (vm->CreateObject(classPtr->GetName(), objectPtr) && objectPtr) {     // const char* → временный BSFixedString
  		BindID(objectPtr, a_src, a_typeID);   // внутри: GetTypeIDForScriptObject(GetName()) и повторный GetHandleForObject
  ```
- Суть и сценарий: каждая форма в аргументах события и в возврате натива проходит GetScriptObjectType (хеш-поиск под typeInfoLock плюс счётчик ссылок). На пути создания объекта (формы без привязанного скрипта) добавляются два временных BSFixedString из `const char*`, хотя `classPtr->name` уже является BSFixedString. Ещё там обратный поиск typeID по имени класса, только что полученного по этому же typeID, и повторный GetHandleForObject.
- Как проверено: чтение PackUnpack.cpp; сигнатуры `CreateObject(const BSFixedString&, ...)` и `GetTypeIDForScriptObject(const BSFixedString&, ...)` — `include/RE/I/IVirtualMachine.h:78, 129`.
- Предложение: передавать `classPtr->name` напрямую. В BindID передавать уже вычисленные handle и classPtr. Сравнение id с a_typeID оставить только в assert.

---

## Расширения

### P-18. RegisterFunction: нельзя привязать лямбду или функтор, результат привязки теряется
- Вид: расширение; Важность: средняя; Уверенность: подтверждено
- Где: `include/RE/N/NativeFunction.h:65, 116, 120-121, 168-169, 173-180`; `include/RE/N/NativeLatentFunction.h:87-94`
- Код:
  ```cpp
  template <class F, class = void> class NativeFunction;               // первичный шаблон не определён
  template <class F>
  NativeFunction(std::string_view, std::string_view, F) -> NativeFunction<std::remove_pointer_t<F>>;
  ...
  BindNativeMethod(new RE::NativeFunction(a_fnName, a_className, a_callback));   // результат bool отброшен
  if (a_callableFromTasklets) { SetCallableFromTasklets(a_className.data(), a_fnName.data(), a_callableFromTasklets); }
  ```
- Суть и сценарий: `_stub` имеет тип `std::function<R(Cls, Args...)>` и мог бы хранить лямбду с захватом. Но CTAD выводит `NativeFunction<closure-type>`, а это неопределённый первичный шаблон, так что не компилируется даже лямбда без захвата (нужен `+[]`). Параметр конструктора `function_type` — тип функции, он сводится к указателю, и захват невозможен ни через какой путь. RegisterFunction возвращает void: при опечатке в имени класса натив молча не привязывается, а SetCallableFromTasklets всё равно вызывается. `string_view::data()` не гарантирует нуль-терминатора (например, substr у имени).
- Как проверено: разбор CTAD и специализаций (частичные специализации в CTAD не участвуют).
- Предложение: перегрузка `template <class Sig, class F> bool RegisterFunction(std::string_view, std::string_view, F&&, bool = false)` и конструктор `NativeFunction(..., std::function<Sig>)`; для лямбд без захвата — вывод Sig из `&F::operator()`. Возвращать и логировать результат BindNativeMethod. Имена для SetCallableFromTasklets передавать через `std::string(...).c_str()`. По желанию: возврат `std::expected<R, std::string>` → `TraceStack(kError)` и None.

### P-19. Нет типизированного вызова скриптовых функций из C++
- Вид: расширение; Важность: средняя; Уверенность: подтверждено
- Где: `include/RE/I/IVirtualMachine.h:109-111, 130-134`; `src/RE/I/IVirtualMachine.cpp:88-127`
- Код:
  ```cpp
  bool      DispatchMethodCall(VMHandle, const BSFixedString& a_className, const BSFixedString& a_fnName,
                               IFunctionArguments* a_args, BSTSmartPointer<IStackCallbackFunctor>& a_result);
  Awaitable ADispatchStaticCall(const BSFixedString& a_className, const BSFixedString& a_fnName, IFunctionArguments* a_args);
  Variable  await_resume() const;
  ```
- Суть и сценарий: чтобы вызвать `Game.GetPlayer()` или метод скрипта и получить `Actor*`, пользователь пишет свой класс-наследник IStackCallbackFunctor (готового лямбда-колбэка в библиотеке нет, единственная реализация — внутренняя `Awaitable::CallbackFunctor`), вручную распаковывает Variable и сам решает вопрос владения `IFunctionArguments*` (см. P-2). `ReturnLatentResult<V>` упаковывает значение по типу аргумента, а не по объявленному при регистрации R; ограничение описано в комментарии `NativeLatentFunction.h:77`.
- Как проверено: поиск наследников IStackCallbackFunctor (`grep -rln "public IStackCallbackFunctor"`) нашёл только IVirtualMachine.h.
- Предложение: `template <class R, class... Args, class F> bool DispatchStaticCall(const BSFixedString& cls, const BSFixedString& fn, F&& onResult, Args&&... args);`. Внутри — FunctionArguments на стеке и `LambdaCallback : IStackCallbackFunctor { void operator()(Variable v) override { f(v.Unpack<R>()); } }`, плюс `Awaitable::As<R>()` для корутин.

---

## Проверено и в порядке

- `NativeFunction::MarshallAndDispatch` (`NativeFunction.h:81-112`): распаковка базы и возврат false при None; передача vm/stackID для длинной сигнатуры; SetNone() для void. `Impl::MakeTupleImpl`: временные из forward_as_tuple живут до конца оператора return, поэтому висячих ссылок нет.
- NativeLatentFunction: тип результата колбэка — `underlying_type_t<LatentStatus>` (bool), `_retType` перезаписывается на latentR, флаг `_isLatent` выставлен.
- GetRawType для массивов: в REX::EnumSet `operator+` арифметический (`include/REX/REX/EnumSet.h:144-146`), поэтому `kInt + kNoneArray = kIntArray`, а `ObjectTypeInfo* + 1` задаёт признак массива объектов — верно.
- PackValue для массивов: CreateArray с типом элемента, `std::vector<bool>`, типизированный None для null-форм (#337) есть в ng. UnpackValue для массивов: None или пустой массив дают пустой контейнер.
- Variable: перемещающие конструктор и присваивание, Set* через ChangeType (Cleanup, затем p = nullptr), operator==/operator< сначала сравнивают типы. `TypeInfo::GetUnmangledRawType/IsObject/IsObjectArray` по битам согласованы с RawType.
- Object::Resolve и UnpackHandle: HandleIsType + IsHandleObjectAvailable + GetObjectForHandle, как UnpackHandle в SKSE64. Object::GetVariable верно прибавляет смещения переменных родительских классов.
- Баланс Persist/Release в конструкторах копирования и перемещения, в присваиваниях и деструкторах всех четырёх регистраций сходится (кроме Load, см. P-5). Формат Save согласован с Load во всех четырёх классах: count типа size_t, затем элементы; расхождение только у строкового фильтра, P-1.
- IVirtualMachine.cpp: индексы RelocateVirtual для VR (0x1B→0x1C, дальше +2) согласованы с New_1B/New_1D в заголовке.
- Раскладки: Stack 0xA0, StackFrame 0x40, NativeFunctionBase 0x50, VDescTable 0x10, хвост Internal::VirtualMachine 0x9320…0x9518 — арифметика смещений без противоречий.
- Ветки: `origin/fix/registration-set-unique-const-args` (VMArg для const-указателей) не влита и здесь не дублируется. `origin/fix/typed-none-array-elements` уже в ng (e44731e04).

Не включено, нужна сверка с бинарником: смещения `Object::GetProperty` по autoVarIndex без поправки на переменные родителей (абсолютный это индекс или относительный — не проверено); PackHandle берёт статический FORMTYPE, а не тип объекта — так же делает SKSE64; владение `IFunctionArguments*` в DispatchStaticCall/DispatchMethodCall*.
