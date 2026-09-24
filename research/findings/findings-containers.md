# CommonLibSSE-NG 9.1.0 (`ng`, a898f4698): контейнеры, память, строки, умные указатели, события, синхронизация

Область: `BSTArray` (с `BSTSmallArray`, `BSScrapArray`, `BSStaticArray`, `BSTSmallSharedArray`), `BSTHashMap`/`BSTScatterTable`/`BSTSet`, `BSTList`, `BSSimpleList`, `BSTTuple`, `BSTSmartPointer`, `BSTSingleton`, `BSFixedString` + `BSStringPool`, `BSString`, `MemoryManager` (+`SimpleArray`, `TES_HEAP_REDEFINE_NEW`), `ScrapHeap`, `BSAtomic` (`BSSpinLock`, `BSReadWriteLock`, guard'ы), `BSTEvent`, `BSTFreeList`, `BSTMessageQueue`, `BSTCaseInsensitiveStringMap`, `NiSmartPointer`/`NiRefObject`, `NiTArray`, `NiTListBase`/`NiTList`, `NiTMapBase`/`NiTMap`/`NiTPointerMap`/`NiTStringMap`, `NiTCollection`, `GArray*`, `GString`, `GMemory`, `GRefCount*`/`GPtr`, `CRC`. Заголовки в `include/RE/**`, реализации в `src/RE/**`.

Как проверялось. Каждая находка опирается на прочитанный код. По каждому файлу смотрел `git log --oneline -5` и `git blame`, по удалённым веткам — `git branch -r` (131 ветка) и `git diff ng <ветка>` для `dev`, `master`, `vr`, `sync/po3-upstream-2026-09-07`, `sync/powerof3-dev-2026-09-07`. Ни в одной ветке исправлений этих находок нет. Правила проекта взяты из `AGENTS.md`/`CLAUDE.md`. Клон не менялся.

Стенд. Настоящие заголовки клона собирались на Linux g++ 13.3 (`-fsanitize=address,undefined`) и clang 18 (`-fsyntax-only`). Подменялись три вещи: заглушка `RE/M/MemoryManager.h` (движковая куча заменена на `std::malloc/std::free`, поэтому ASan видит двойное освобождение и use-after-free), минимальный аналог `SKSE/Impl/PCH.h` (`stl::atomic_ref`, `scope_exit`, `report_and_fail`, `_stricmp` и т. п.) и заглушка `REL::Relocation` для `GString.cpp`. Там, где это возможно, компилировались и настоящие `.cpp`: `src/RE/B/BSTArray.cpp`, `src/RE/G/GString.cpp`. Оговорка: в ABI Itanium `BSTArrayBase` ложится в хвостовой отступ аллокатора, поэтому `static_assert` на размеры с раскладкой MSVC (например `BSTEventSource`) на Linux не выполняются. В двух тестах, где мешали только они, их пришлось отключить. На логику находок это не влияет. Стенд лежал в scratchpad сессии и после неё не сохранится; команды воспроизведения приведены в самих находках.

Итог: 27 находок — 21 ошибка, 2 неоптимальных места, 4 расширения. Пересечение с `findings-math-scene.md`: там `GString` (копирование и присваивание) отмечен как «в порядке». Находка C-5 это опровергает: `size()`, самоприсваивание и присваивание из собственного буфера сломаны.

---

### C-1. `BSTSmallArray`: двойное освобождение в деструкторе, падение при перемещении, мусорный указатель после `shrink_to_fit`
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено
- Где: `include/RE/B/BSTArray.h:226-233` (`set_allocator_traits`), `:261-272` (`copy(&&)`), `:276-285` (`release`); вызывающий код `:668-688` (`change_capacity`)
- Код:
  ```cpp
  constexpr void set_allocator_traits(void* a_data, std::uint32_t a_capacity, std::size_t a_typeSize) noexcept
  {   _capacity = a_capacity;
      if (a_capacity * a_typeSize > N) { _local = 0; _data.heap = a_data; }   // обратно в _local = 1 не сбрасывает никогда
  }
  inline void release()
  {   if (!local()) { free(_data.heap); }
      std::memset(data(), 0, capacity());   // data() всё ещё heap -> запись в освобождённое
      _capacity = N;                        // N — байты (sizeof(T)*count), _capacity — элементы
  ```
- Суть и сценарий: после ухода на кучу флаг `_local` остаётся 0 навсегда. Отсюда три поломки.
  1. Деструктор. `~BSTArray` → `change_capacity(0)` освобождает кучу и вызывает `set_allocator_traits(nullptr, 0)`, при этом `_local` остаётся 0, а `_data.heap` висит. Следом `~BSTSmallArrayHeapAllocator` → `release()` → повторный `free(_data.heap)`. Хватает `RE::BSTSmallArray<int, 2> a; a.push_back(1);` — даже первая вставка идёт на кучу, потому что `DF_CAP = 4` больше двух. Выход из области видимости даёт двойное освобождение в куче `MemoryManager`.
  2. Сжатие с кучи обратно на локальный буфер (`resize(2); shrink_to_fit()` для `BSTSmallArray<int,4>`). `allocate()` возвращает `_data.local`, то есть union, где лежит указатель кучи. `memcpy` затирает этот указатель данными элементов, а `_local` остаётся 0. `data()` возвращает «указатель» из байтов элементов, и чтение `a[0]` падает.
  3. Перемещающий конструктор (`BSTArray(BSTArray&&) = default` → `copy(&&)`) делает `memmove(data(), a_rhs.data(), capacity())`. Если источник на куче, у приёмника `data()` = `_data.heap` = nullptr, и запись идёт по нулевому адресу. К тому же копируется `capacity()` байт вместо `capacity()*sizeof(T)`, а источник получает `_capacity = N` в байтах, то есть ёмкость больше физического буфера.
- Как проверено: ASan. `BSTSmallArray<int,2>` + `push_back(1)` → «attempting double-free», стек `release()` ← `~BSTSmallArrayHeapAllocator` (`BSTArray.h:279`), первое освобождение из `BSTArray::deallocate` (`:659`). Перемещение → SEGV по адресу 0 в `copy(&&)` (`:267`). `shrink_to_fit` → SEGV при чтении `a[0]`. Последняя правка файла — fd13f0628 (#361, `BSTSmallSharedArray::empty`), этого кода она не касалась.
- Предложение: в `set_allocator_traits` при `a_capacity * a_typeSize <= N` ставить `_local = 1` (и не принимать указатель на `_data.local` от `allocate()`, пока старые данные лежат в том же union). Хранить ёмкость в элементах: передавать в аллокатор число элементов отдельным параметром шаблона или делить на `sizeof(T)`. В `release()` сначала сбрасывать `_local`, потом делать `memset`. `copy(&&)` должен забирать `_data.heap`, а не копировать байты. Добавить Catch2-тест `tests/RE/B/BSTArray.test.cpp` (`[unit]`, с подменой кучи).

### C-2. `BSTScatterTable`: `value_union` безусловно конструирует и разрушает значение — двойной деструктор на каждом живом элементе
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено
- Где: `include/RE/B/BSTHashMap.h:133-143`; срабатывает через `free_resources()` (`:525`) и `reserve()` (`:416`)
- Код:
  ```cpp
  union value_union
  {
      value_union() : value() {}                 // значение конструируется даже в пустом слоте
      ~value_union() { value.~value_type(); }    // и разрушается всегда
      value_type value;
      std::byte  buffer[sizeof(value_type)]{ static_cast<std::byte>(0) };
  };
  ```
- Суть и сценарий: `entry_type` сам ведёт время жизни значения: `emplace` конструирует его через `construct_at`, `destroy()` разрушает через `destroy_at`. Но деструктор union разрушает `value` ещё раз. При уничтожении карты каждый живой элемент получает два деструктора: `destroy()` из `~entry_type`, затем `~value_union`. При каждом росте таблицы (`reserve` → `destroy_n(oldEntries)`) то же происходит с каждым перенесённым элементом: после `steal()` он уже разрушен. Кроме того, `emplace` конструирует новое значение поверх живого значения по умолчанию, не разрушив его, а типы без конструктора по умолчанию в `BSTHashMap` вообще не допускаются. Для типов с «идемпотентным» деструктором (`BSFixedString`, `BSTSmartPointer`, `NiPointer` обнуляют указатель) это формальное UB. Для `std::string`, `std::vector`, `std::shared_ptr`, `std::function` в значении — настоящее двойное освобождение.
- Как проверено: ASan. `BSTHashMap<int, std::string>` с 20 длинными строками → «attempting double-free» в `~value_union` (`BSTHashMap.h:138`) из `free_resources` (`:525`). Счётчик: у карты из 20 элементов (32 слота) при уничтожении 52 деструктора и 0 конструкторов (32 от union + 20 от `destroy()`).
- Предложение: убрать конструктор и деструктор у union: `value_union() noexcept {}` и `~value_union() {}` (члену `buffer` инициализатор не нужен). Время жизни оставить только `emplace`/`destroy`. Сразу снимается и требование конструируемости по умолчанию.

### C-3. `BSTList::clear()` читает `node->next` после освобождения узла; `erase()` не разрушает элемент; `erase(begin())` не компилируется
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено
- Где: `include/RE/B/BSTList.h:250-253` (`clear`), `:265-277` (`erase`), `:65-69` (перемещающий конструктор `const_iterator`), `:33-36` (`free`)
- Код:
  ```cpp
  for (auto node = _sentinel->next; node != _sentinel; node = node->next) {   // node->next после free
      std::destroy_at(node);
      allocator_type{}.deallocate(node);
  }
  ...
  constexpr const_iterator(const const_iterator&& a_rhs) noexcept : _cur(a_rhs._cur) { a_rhs._cur = nullptr; }
  ```
- Суть и сценарий: шаг цикла читает `next`, лежащий по смещению 0 уже освобождённого узла. В куче движка первые 8 байт свободного блока обычно занимает ссылка свободного списка. Обход уходит в структуры аллокатора и начинает освобождать чужие блоки. `BSAudioManager::audioCache` (`include/RE/B/BSAudioManager.h:70`) — `BSTList<BSGameSound*>`, так что плагин, вызвавший `audioCache.clear()`, портит кучу. `erase()` отдаёт узел аллокатору без `destroy_at`: для `BSTList<BSFixedString>` или `BSTList<BSTSmartPointer<…>>` течёт счётчик ссылок. `l.erase(l.begin())` не компилируется, потому что `iterator` → `const_iterator` проходит через конструктор `const const_iterator&&`, который присваивает константному объекту. Для `BSTList<T>` с `T` из пространства `std` или глобального неквалифицированный `free(a_node)` неоднозначен (ADL находит `std::free`/`::free`).
- Как проверено: ASan, `BSTList<int>` с двумя элементами, `clear()` → «heap-use-after-free READ of size 8» в `BSTList.h:250`. `BSTList<RE::Owning>` (тип со `std::string` внутри), `erase(cbegin())` → LeakSanitizer, 65 байт. clang: `erase(begin())` → «cannot assign to variable 'a_rhs' with const-qualified type» (`:68`). g++: `BSTList<std::string>` → «call of overloaded 'free(...)' is ambiguous» (`:35`).
- Предложение: `for (auto node = _sentinel->next; node != _sentinel;) { auto next = node->next; std::destroy_at(node); deallocate(node); node = next; }`. В `erase` добавить `std::destroy_at(node)`. Перемещающий конструктор `const_iterator` удалить (итератор — один указатель, хватит копирования). Писать `RE::free(a_node)`.

### C-4. `GArrayBase::RemoveMultipleAt`: знак «+» вместо «−» в длине сдвига — выход за буфер на 2·num элементов
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено
- Где: `include/RE/G/GArrayBase.h:401-405`
- Код:
  ```cpp
  AllocatorType::DestructArray(data.data + a_index, a_num);
  AllocatorType::CopyArrayForward(
      data.data + a_index,
      data.data + a_index + a_num,
      data.size + a_num - a_index);   // должно быть data.size - a_num - a_index
  data.size -= a_num;
  ```
- Суть и сценарий: для size=10, index=2, num=3 сдвигать надо 5 элементов, код сдвигает 11. `memmove` читает `[5, 16)` и пишет в `[2, 13)`, то есть за `size` и почти всегда за ёмкость. У Scaleform в оригинале `Data.Size - num - index`; соседний `RemoveAt` (`:417-421`) считает верно. Страдают все `GArray`/`GArrayLH` движка (`GFxPlaceObjectBase::filterList`, `GFxMovieDataDef::assets`, `GImageBase::colorMap` и т. д.), если плагин удаляет из них диапазон.
- Как проверено: ASan, `GArray<int>` из 10 элементов, `RemoveMultipleAt(2, 3)` → «heap-buffer-overflow READ of size 44» в `GConstructorMov::CopyArrayForward` (`GConstructorMov.h:64`) ← `GArrayBase.h:402`.
- Предложение: `data.size - a_num - a_index`.

### C-5. `GString`: `size()` возвращает поле вместе с флаговым битом (≈2⁶³); самоприсваивание и присваивание из своего буфера — use-after-free
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено
- Где: `src/RE/G/GString.cpp:215` (`size`), `:42-49` (`SetFull`), `:92-104` (`operator=(const GString&)`), `:124-143` (`operator=(std::string_view)`); `include/RE/G/GString.h:131` (сравнение с `string_view`), `:15`/`:24` (хеш-функторы), `:87` (конструктор без определения)
- Код:
  ```cpp
  return desc->IsFull() ? desc->capacity : std::strlen(desc->data);   // capacity с kFullFlag = 1ull << 63
  ...
  GString& GString::operator=(const GString& a_rhs)
  {   auto desc = get_desc();
      if (desc) { desc->Release(); }          // при refCount==1 освобождает — и если a_rhs это *this ...
      desc = a_rhs.get_desc(); set_desc(desc);
      if (desc) { desc->AddRef(); }           // ... AddRef по освобождённой памяти
  ```
- Суть и сценарий:
  1. `operator=(std::string_view)` всегда вызывает `SetFull(true)`, то есть ставит старший бит `capacity`, а `size()` возвращает `capacity` без маски (`GetCapacity()` с маской в классе есть, но не используется). `RE::GString s; s = "abc";` → `s.size() == 0x8000000000000003`. `GString()` → `empty() == false`, `size() == 0x8000000000000000`. `std::string_view(s)`, `back()`, `HashFunctor`/`NoCaseHashFunctor` и `FxDelegate::CallbackHashFunctor` (`src/RE/F/FxDelegate.cpp:14`) читают до 2⁶³ байт. Строки движка ломаются так же, если движок выставил этот бит (у Scaleform это «длина в символах = длине в байтах», ставится после вычисления длины).
  2. `s = s` при единственной ссылке: `Release()` освобождает блок, затем `AddRef()` пишет в освобождённую память.
  3. `s = s.c_str() + 1` (и любой `string_view` на свой буфер): старый блок освобождается до `memcpy` из него.
  4. `operator==(GString, string_view)` сравнивает через `strcmp(a_lhs.data(), a_rhs.data())`, без учёта длины: для подстроки результат неверный, для пустого `string_view{}` (data=nullptr) — падение. В `BSString` такое сравнение исправлял e282ba56f, `GString` тот коммит не тронул.
  5. `GString(const std::string_view&)` объявлен (`GString.h:87`), но нигде не определён (LNK2019 при использовании).
- Как проверено: собран настоящий `src/RE/G/GString.cpp` с заглушкой `REL::Relocation`. Вывод: `default-constructed: empty()=0 size()=0x8000000000000000`, `after s = "abc": size()=0x8000000000000003`. ASan: `s = s` → heap-use-after-free в атомарном инкременте, `s = s.c_str()+1` → heap-use-after-free в `memcpy` (`GString.cpp:137`). `GString("abcdef") == string_view("abcdefXYZ",6)` → 0. `grep -rn "GString::GString" src` — определены только 4 конструктора.
- Предложение: `size()` → `desc ? desc->GetCapacity() : 0`. В присваиваниях сначала взять и `AddRef` новый блок (или скопировать данные), потом `Release` старый. Сравнение с `string_view` делать через `std::string_view(*this) == a_rhs`. Определить конструктор из `string_view` (или убрать объявление).

### C-6. Неявное поверхностное копирование `NiTArray`/`NiTLargeArray`/`SimpleArray` — `auto children = node->GetChildren();` освобождает детей узла
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено
- Где: `include/RE/N/NiTArray.h:20-35` и `:172-187` (копирование не запрещено, деструктор освобождает `_data`), `include/RE/M/MemoryManager.h:314-322` (`SimpleArray`); путь к ошибке: `include/RE/N/NiNode.h:59` (`GetChildren()` возвращает ссылку)
- Код:
  ```cpp
  NiTArray(std::uint32_t a_maxSize = 0, std::uint32_t a_growBy = 1) : ...
  virtual ~NiTArray()  // 00
  {
      allocator_type::Deallocate(_data);   // копия и оригинал владеют одним _data
  }
  ```
- Суть и сценарий: у классов есть пользовательский деструктор, освобождающий буфер, а конструктор и оператор копирования генерируются неявно и копируют только указатель. Типичная ошибка в плагине — `auto children = node->GetChildren();` без `&`. Она компилируется молча. Копия при уничтожении вызывает `NiTNewInterface::Deallocate`: разрушает все `NiPointer` детей (DecRef → удаление узлов) и освобождает буфер массива, который остаётся у `NiNode`. Дальше рендер обходит освобождённую память. То же с `SimpleArray<T>` в `TESLeveledList::entries`, `NiSkinPartition::partitions`, `BGSEntryPointPerkEntry::conditions`, `VDescTable::entries` и т. д.
- Как проверено: ASan. `NiTPrimitiveArray<int> a(4); { auto b = a; }` → «attempting double-free» в `NiTMallocInterface::Deallocate`. `SimpleArray<std::string> a(2); { auto b = a; }` → heap-use-after-free в `SimpleArray::size()` (код `MemoryManager.h:297-428` дословно).
- Предложение: в `NiTArray`, `NiTLargeArray`, `SimpleArray` (и `NiTMapBase`, `BSSemaphoreBase` по тому же принципу) объявить `X(const X&) = delete; X& operator=(const X&) = delete;` — это классы движка, глубокая копия им не нужна. Ошибка тогда проявится при компиляции.

### C-7. `BSTSmartPointer`/`NiPointer`/`GPtr`: присваивание сначала отпускает старый объект, потом читает источник — use-after-free на `p = p->next`; `BSTAutoPointer` копируется
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `include/RE/B/BSTSmartPointer.h:113-121`, `:140-148` (и шаблонные `:124-137`, `:151-164`, `reset(Y*)` `:171-185`); `include/RE/N/NiSmartPointer.h:78-86`, `:105-113`; `include/RE/G/GPtr.h:83-91`, `:110-118`; `BSTAutoPointer`: `BSTSmartPointer.h:21-32`, `:65-70`, `:278-279`
- Код:
  ```cpp
  inline BSTSmartPointer& operator=(const BSTSmartPointer& a_rhs)
  {
      if (this != std::addressof(a_rhs)) {
          TryDetach();          // может удалить объект, внутри которого лежит a_rhs
          _ptr = a_rhs._ptr;    // чтение освобождённой памяти
          TryAttach();
  ```
- Суть и сценарий: обход связной структуры одним указателем — `BSTSmartPointer<Node> p = head; p = p->next;`, `NiPointer<NiAVObject> cur = clonedRoot; cur = cur->GetChildren()[0];` на отсоединённом поддереве. Если `p` держит последнюю ссылку, `TryDetach()` удаляет объект, а вместе с ним и член `next` / массив детей, и следующая строка читает освобождённую память. Перемещающая версия ещё и пишет в неё (`a_rhs._ptr = nullptr`). `BSTAutoPointer` (`BSTSmartPointerAutoPtr`: `Acquire` — пустышка, `Release` — `delete`) имеет обычный конструктор копирования, и `BSTAutoPointer<X> b = a;` даёт двойной `delete`. Он лежит в `BSScript::Stack::MemoryPageData` (`include/RE/S/Stack.h:58`) внутри `BSTSmallArray`, копирование которого глубокое.
- Как проверено: ASan. `head = head->next` → heap-use-after-free в `BSTSmartPointer::operator=` (`BSTSmartPointer.h:117`). `cur = std::move(cur->child)` для `NiPointer` → heap-use-after-free (`NiSmartPointer.h:109`). `BSTAutoPointer<int> b = a;` → «attempting double-free» в `BSTSmartPointerAutoPtr::Release` (`:30`).
- Предложение: copy-and-swap — `BSTSmartPointer(a_rhs).swap(*this)` (сначала захват, потом отпускание). В `reset(Y*)` так же: сначала `Acquire(a_ptr)`, затем отпустить старый. Для `RefManager = BSTSmartPointerAutoPtr` удалить копирование (`requires` на конструкторе копирования или частичная специализация).

### C-8. `BSTArray::push_back(a[i])` / `insert(pos, a[i])`: ссылка на собственный элемент протухает при росте или сдвиге
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `include/RE/B/BSTArray.h:569-579` (`emplace_back`), `:601-617` (`emplace`)
- Код:
  ```cpp
  if (size() == capacity()) {
      grow_capacity();                  // старый буфер освобождён, a_args может ссылаться в него
  }
  set_size(size() + 1);
  auto& elem = back();
  std::construct_at(std::addressof(elem), std::forward<Args>(a_args)...);
  ...
  std::memcpy(newData + headPartToCopy + 1, cend() - tailPartToCopy, tailBytesToCopy);   // newData == data(): области перекрываются
  ```
- Суть и сценарий: `arr.push_back(arr[0])` на заполненном массиве копирует из освобождённого буфера. `std::vector` гарантирует, что такой вызов работает. `arr.insert(arr.begin(), arr[1])` без перераспределения сначала сдвигает хвост, а потом конструирует из ссылки, которая теперь указывает на соседний элемент, и вставляет не то значение. Сам сдвиг сделан `memcpy` с перекрытием, это UB (нужен `memmove`).
- Как проверено: ASan. `push_back(a[0])` при size==capacity==4 → heap-use-after-free в `emplace_back` (`BSTArray.h:578`). `insert(begin(), a[1])` для [1,2,3] при ёмкости 8 → «memcpy-param-overlap» (`:614`). Без ASan (`-O2`) результат `front=1` вместо 2.
- Предложение: в `emplace_back` при нехватке места сначала выделить новый буфер и сконструировать элемент в нём, потом переносить старые (как в `std::vector::_Emplace_reallocate`). В `emplace` сначала сделать `value_type tmp(args...)`, потом `memmove` и перенос `tmp`.

### C-9. `BSTArray::operator=(BSTArray&&)` переносит только указатель и ёмкость — состояние аллокатора теряется (`BSScrapArray`, `BSTSmallArray`)
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `include/RE/B/BSTArray.h:473-489`; `src/RE/B/BSTArray.cpp:28-35`
- Код:
  ```cpp
  release();
  const auto newCapacity = a_rhs.capacity();
  const auto newData = a_rhs.data();
  set_allocator_traits(newData, newCapacity);   // _allocator (ScrapHeap*) и _local не переносятся
  a_rhs.set_allocator_traits(0, 0);
  ```
- Суть и сценарий: у `BSScrapArrayAllocator` есть поле `_allocator` (куча потока), которое заполняется лениво при первом `allocate`. `BSScrapArray<int> a, b; b.push_back(1); a = std::move(b);` → у `a` блок из scrap-кучи, а `_allocator == nullptr`. В деструкторе `deallocate` попадает в `else { assert(false); }`: в Debug это abort, в Release утечка. Если `a` раньше выделяла память на другом потоке, блок уходит в чужую scrap-кучу. Для `BSTSmallArray` локальный буфер источника «переезжает» указателем на чужой объект, а у источника остаётся `_local == 0` и старый `_data.heap`, поэтому его деструктор освобождает уже отданный блок (ASan: double-free). Перемещающий конструктор (`= default`) аллокатор переносит, так что конструктор и присваивание ведут себя по-разному.
- Как проверено: ASan/LSan. `a = std::move(b)` для `BSScrapArray<int>` → «Assertion `false' failed» (`BSTArray.cpp:33`), с `-DNDEBUG` → LeakSanitizer, 16 байт. `BSTSmallArray<int,2>` → «attempting double-free».
- Предложение: реализовать как `release(); static_cast<Allocator&>(*this) = std::move(static_cast<Allocator&>(a_rhs)); BSTArrayBase::operator=(std::move(a_rhs));`. У аллокаторов перемещающее присваивание уже есть (для `BSTSmallArrayHeapAllocator` — после исправления C-1). Пометить `noexcept`.

### C-10. `BSTScatterTable::erase(it)` возвращает `entry + 1` — при удалении в цикле пропускается элемент, переехавший в текущий слот
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `include/RE/B/BSTHashMap.h:451-456`
- Код:
  ```cpp
  } else {  // move next into current
      *entry = std::move(*entry->next);
  }
  ++Parent::_free;
  return make_iterator<iterator>(entry + 1);
  ```
- Суть и сценарий: если у удаляемого элемента есть продолжение цепочки, следующий элемент переносится в текущий слот, а итератор уходит на `entry + 1`. Если бывший слот следующего элемента лежал дальше по массиву (а `get_free_entry` ищет свободные слоты вперёд от `_good`), перенесённый элемент не попадёт в обход. Идиома `for (it = m.begin(); it != m.end();) it = pred(*it) ? m.erase(it) : std::next(it);` оставляет в карте элементы, подходящие под условие.
- Как проверено: ASan-стенд. Ключи 0 и 12 оба попадают в слот 0 таблицы на 8 слотов (`BSCRC32<int>(k) & 7 == 0`). Цикл «удалить всё» оставляет `size() == 1`.
- Предложение: в ветке переноса возвращать `make_iterator<iterator>(entry)`, если индекс бывшего слота `next` больше индекса `entry`, иначе `entry + 1`. Ещё лучше поменять схему удаления, чтобы узлы не переезжали.

### C-11. Итераторы `BSTScatterTable`: `it++` не двигает итератор, `const_iterator` даёт изменяемую ссылку (и ключ `BSTSet`), присваивание в пустой итератор падает на assert
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `include/RE/B/BSTHashMap.h:201-206`, `:151-154`, `:171-179`
- Код:
  ```cpp
  using value_type = std::remove_const_t<U>;
  using reference = value_type&;          // для iterator_base<const T> это T&
  ...
  iterator_base operator++(int) noexcept
  {
      iterator_base result = *this;
      ++result;                           // двигается копия, *this остаётся на месте
      return result;
  ```
- Суть и сценарий: `for (auto it = m.begin(); it != m.end(); it++)` зацикливается. `m.erase(it++)` удаляет элемент, а `it` продолжает указывать на удалённый слот. `for (auto& [k, v] : constMap) v = 1;` компилируется и меняет константную карту. У `BSTSet<K>` `*it = other` меняет ключ на месте и ломает хеширование (у `std::unordered_set` итераторы константные). `BSTHashMap<…>::iterator it; it = m.find(k);` в Debug срабатывает `assert(_last == a_rhs._last)`. `static_assert(std::forward_iterator<…>)` (`:772`) проверяет только синтаксис и ничего из этого не ловит.
- Как проверено: стенд. После `auto ret = it++` → `it moved: NO; ret==old: NO`. Код `for (auto& e : cm) e.second = 42;` для `const BSTHashMap&` компилируется clang без ошибок, `decltype(*cm.begin())` — `BSTTuple<const int,int>&`. Присваивание в пустой итератор → «Assertion `_last == a_rhs._last' failed» (`:175`).
- Предложение: `iterator_base operator++(int) noexcept { auto tmp = *this; seek(); return tmp; }`. `using value_type = std::remove_const_t<U>; using reference = U&; using pointer = U*;`. Для `BSTSetTraits` сделать `iterator = const_iterator`. В `operator=` разрешать `_last == nullptr` у левой стороны.

### C-12. `BSSimpleList`: `pop_front()` не опустошает список из одного элемента, `insert_at(0, …)` теряет узел, константный обход, `erase_after` и `resize` не компилируются
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `include/RE/B/BSSimpleList.h:434-445` (`pop_front`), `:526-534` (`insert_at_impl`), `:301` (`begin() const`), `:402-411` и `:493-505` (`erase_after`), `:551-574` (`resize_impl`)
- Код:
  ```cpp
  std::destroy_at(std::addressof(_listHead.item));
  auto node = _listHead.next;
  if (node) { ... }                 // при node == nullptr item не пересоздаётся: для T* значение остаётся
  ...
  [[nodiscard]] inline const_iterator begin() const { return empty() ? end() : const_iterator(get_head()); }   // const Node* -> Node*
  ...
  erase_after_impl(node, node->next);   // удаляет узлы строго между node и node->next, то есть ни одного
  ```
- Суть и сценарий:
  - `pop_front()` на единственном элементе разрушает `item`, но не конструирует пустой. Для `BSSimpleList<TESForm*>` значение указателя остаётся, `empty()` = false, и `while (!l.empty()) l.pop_front();` зацикливается. `clear()` делает это правильно (`:326-329`).
  - `insert_at(0, v)` переносит значение из нового узла в голову, но сам узел не удаляет (утечка). При `a_count == 1` возвращается итератор на этот оторванный узел.
  - `begin() const`/`cbegin()` не компилируются (`const Node*` → `Node*`), так что константный `for` по спискам движка (52 заголовка используют `BSSimpleList`) невозможен. Из этого следует, что `erase_after(const_iterator)` вызвать нельзя: `iterator` в `const_iterator` не преобразуется. Если бы вызов собрался, `erase_after_impl(node, node->next)` ничего бы не удалил. `resize()` не компилируется по той же причине. Даже с исправленными типами он на пустом списке при `count > 1` разыменовал бы nullptr (`insert_after(end(), …)`), а при `count == 1` ничего бы не вставил.
- Как проверено: стенд. `pop_front` → `empty()=0 size()=1`. `insert_at(0, &x)` → LeakSanitizer (16 байт, `BSSimpleList.h:387`) и «returned iterator points into list: no». clang: `cbegin()` → «no matching conversion … from 'const Node *' to 'const_iterator'» (`:301`), `resize(3)` → «no matching member function for call to 'insert_after'/'erase_after'» (`:567`, `:570`), `erase_after(l.begin())` → нет подходящей перегрузки.
- Предложение: в `pop_front` при `!node` делать `construct_at(&_listHead.item)`. В `insert_at_impl` после переноса `delete head` (а для `a_count > 1` связывать `head->next`). `iterator_base<U>` хранить `std::conditional_t<std::is_const_v<U>, const Node*, Node*>` и добавить преобразование `iterator` → `const_iterator`. `erase_after(pos)` → `erase_after_impl(node, node->next ? node->next->next : nullptr)`. В `resize_impl` отдельно разобрать пустой список.

### C-13. `BSString`: `== string_view` сравнивает префикс, из `string_view` получается строка без терминатора, перемещающее присваивание теряет старый буфер
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `include/RE/B/BSString.h:212` (`==`), `:124-127` и `:167-171` (из `string_view`), `:232-258` (`set_cstr`), `:144-159` (перемещение), `:108-117` (перемещение для `FixedLengthMemoryManagementPol`)
- Код:
  ```cpp
  operator==(const BSStringT& a_lhs, const std::basic_string_view<value_type>& a_rhs) { return strnicmp(a_lhs.c_str(), a_rhs.data(), a_rhs.size()) == 0; }
  ...
  if (len == 0) { len = static_cast<std::uint16_t>(traits_type::length(a_str)); }   // пустой view трактуется как C-строка
  ++len;
  traits_type::copy(newData, a_str, len);   // копирует size()+1 символов из view, «терминатор» — чужой байт
  ```
- Суть и сценарий: `BSString("HelloWorld") == "Hello"sv` → true (сравнение по длине правой части, без проверки длин). `BSString(sv.substr(0, 5))` для "HelloWorld" копирует 6 байт "HelloW" без `\0`: `size()` = 5, а `c_str()` не завершён, и `strlen` или движок читают за буфер. `BSString(std::string_view("abc", 0))` даёт "abc", `BSString(std::string_view{})` вызывает `strlen(nullptr)`. `a = std::move(b)` перезаписывает `_data`, не освободив старый буфер. А `a` всегда что-то держит, потому что конструктор по умолчанию аллоцирует (см. C-23). Длина молча обрезается до `uint16_t`. У `BSStaticStringT` перемещение копирует `_data`, указывающий во встроенный `_buffer` источника, и после смерти источника указатель висит. В 9.1.0 классом никто не пользуется.
- Как проверено: стенд с ASan/LSan. `== "Hello"sv` → 1. `substr(0,5)` → «heap-buffer-overflow READ» в `strlen`. `string_view("abc",0)` → `"abc" size=3`. `a = std::move(b)` → LeakSanitizer, 6 байт. Сравнения правили 41cfab243 и e282ba56f, проверку длины они не добавили.
- Предложение: `==` → `a_lhs.size() == a_rhs.size() && strnicmp(…, a_rhs.size()) == 0`. `set_cstr(ptr, len)` с явным `bool a_hasLen`, копировать `len` символов и дописывать `\0`. В перемещающем присваивании `deallocate(_data)` до переноса. Для фиксированной политики перемещение = копирование через `set_cstr`.

### C-14. `BSFixedString(string_view)` / `operator=(string_view)` передают движку только `view.data()` — подстроки становятся длиннее
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено (по коду: у движковой функции `ctor8/ctor16` один параметр-указатель)
- Где: `include/RE/B/BSFixedString.h:50-56`, `:97-105`
- Код:
  ```cpp
  inline BSFixedString(const T& a_string)
  {
      const auto view = static_cast<std::basic_string_view<value_type>>(a_string);
      if (!view.empty()) {
          ctor(view.data());     // размер view теряется; ctor8(const char*) читает до '\0'
      }
  }
  ```
- Суть и сценарий: `std::string_view path = "meshes\\armor\\x.nif"; RE::BSFixedString s(path.substr(0, 6));` интернирует всю строку до `\0`, а не "meshes". Если за view нет нуля (буфер файла, `std::array<char>`), движок читает за его конец. Сравнение `s == view` потом даёт false, поиск по пулу возвращает не ту строку. Перегрузка стоит для любого `T`, приводимого к `string_view`, поэтому под неё попадает любой `string_view`, пришедший из разбора INI/JSON.
- Как проверено: чтение кода, сигнатуры `ctor8(const char*)`/`ctor16(const wchar_t*)` (`:191-203`). `git log -5` — последняя правка 0d87671cf, поведение не менялось.
- Предложение: если `view.data()[view.size()] != 0` проверить нельзя, всегда копировать во временный `std::basic_string<value_type>(view)` (или в стековый буфер для коротких строк) и отдавать `c_str()`. То же в `operator=`.

### C-15. `NiTMapBase`: `end()` и `++` читают `_data[_capacity]`; `erase()` и константный обход не компилируются; присваивание итераторов без `return`
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `include/RE/N/NiTMapBase.h:73` и `:161-164` (чтение за границей), `:318` (`item->key`), `:233-236`/`:248-256`/`:339-343` (const), `:92-108` (присваивание)
- Код:
  ```cpp
  _iter = _proxy->_data[_idx];                 // _idx == _capacity для end()
  while (!_iter && _idx < _proxy->_capacity) { ++_idx; _iter = _proxy->_data[_idx]; }
  ...
  if (key_eq(a_key, item->key)) {              // в NiTMapItem полей key нет: next/first/second
  ...
  iterator_base& operator=(const iterator_base& a_rhs) { assert(_proxy == a_rhs._proxy); _iter = a_rhs._iter; _idx = a_rhs._idx; }   // нет return
  ```
- Суть и сценарий: каждый `end()` и последний шаг `++` читают 8 байт за массивом корзин. Обычно там мусор, который потом не используется. Если массив кончается на границе страницы — access violation. `erase(key)` не компилируется: 6ce588df9 «Fix NiTMapBase::insert_or_assign» заменил `item->key` на `item->first` только в `insert_or_assign`. `begin() const`/`end() const`/`find() const` передают `const NiTMapBase*` в конструктор, который принимает неконстантный указатель, поэтому `for (auto& e : constMap)` не компилируется. `it = other;` выходит из не-void функции без `return`. Это UB, а clang (сборки `linux-clangcl`) ставит в конец такой функции `ud2`/unreachable. Кроме того, у собственных виртуальных функций базы (`hash_function`, `key_eq`, `assign_value`, `clear_value`) нет определений, так что плагин не может собрать свой наследник `NiTMap` (ошибки линковки).
- Как проверено: ASan на наследнике `NiTMapBase<Alloc,uint32_t,int>`, `for (auto& e : m)` → «heap-buffer-overflow READ of size 8 … 0 bytes after 32-byte region» в `iterator_base(NiTMapBase*, uint32_t)` (`:73`) ← `end()` (`:245`). clang: `erase` → «no member named 'key'» (`:318`), const → «no matching constructor for initialization of 'const_iterator'» (`:235`, `:250`), `it = m.begin()` → «-Wreturn-type» (`:108`). g++: без определений базовых виртуальных функций — «undefined reference to NiTMapBase<…>::hash_function».
- Предложение: читать `_data[_idx]` только при `_idx < _capacity`. `item->first`. `iterator_base` хранить `const NiTMapBase*` для константной версии. Добавить `return *this;`. Базовые виртуальные функции определить (`a_key % _capacity`, `==`, присваивание) или сделать чисто виртуальными.

### C-16. `NiTNewInterface::Allocate` не конструирует элементы, а `Deallocate` вызывает для них деструкторы
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `include/RE/N/NiTCollection.h:351-369`
- Код:
  ```cpp
  auto mem = malloc(sizeof(std::size_t) + sizeof(T) * a_numElements);   // память не инициализирована
  auto head = static_cast<std::size_t*>(mem);
  *head = a_numElements;
  mem = head + 1;
  return static_cast<T*>(mem);
  ...
  for (std::size_t i = 0; i < *head; ++i) { a_array[i].~T(); }
  ```
- Суть и сценарий: у Gamebryo это пара `new T[n]` / `delete[]`, где элементы конструируются. Здесь `NiTObjectArray<NiPointer<NiAVObject>> arr(4);` (так объявлены дети `NiNode`) получает четыре `NiPointer` с мусором, и при уничтожении или перезаписи каждый делает `DecRefCount()` по мусорному адресу. Кроме того, `malloc` может вернуть nullptr, а `*head` пишется без проверки.
- Как проверено: ASan. `NiTObjectArray<Obj> a(3)` с меткой в конструкторе → три деструктора на неинициализированной памяти (`magic=0xbebebebe` — заливка ASan).
- Предложение: после выделения `std::uninitialized_value_construct_n(static_cast<T*>(mem), a_numElements)`. Проверять `mem` на nullptr (`report_and_fail`).

### C-17. Перемещающий конструктор `BSTScatterTable` не компилируется — `BSTHashMap`/`BSTSet` нельзя перемещать
- Вид: ошибка; Важность: низкая; Уверенность: подтверждено
- Где: `include/RE/B/BSTHashMap.h:256-266`
- Код:
  ```cpp
  BSTScatterTable(BSTScatterTable&& a_rhs) noexcept requires(...) :
      Parent::_capacity(std::exchange(a_rhs._capacity, 0)),   // член базы в списке инициализации производного
      Parent::_free(std::exchange(a_rhs._free, 0)),
      Parent::_good(std::exchange(a_rhs._good, 0)),
  ```
- Суть и сценарий: по [class.base.init]/2 инициализировать член базового класса в списке инициализации производного нельзя. Конструктор объявлен `noexcept` и проходит ограничение для `BSTScatterTableHeapAllocator`, поэтому выбирается при `BSTHashMap b(std::move(a))`, при возврате карты по значению без NRVO и при росте `std::vector<BSTHashMap<…>>`, после чего сборка падает.
- Как проверено: g++ — «'…::_capacity' … which is not a type», clang — «typename specifier refers to non-type member '_capacity'» (`:259-261`).
- Предложение: инициализировать `Parent(std::move(a_rhs))` (с `noexcept`-перемещением у `BSTScatterTable*Parent`, обнуляющим источник) или присваивать поля в теле конструктора.

### C-18. `BSTEventSource::AddEventSink/PrependEventSink<SinkEvent>` бесконечно рекурсирует при несовпадении типа события
- Вид: ошибка; Важность: низкая; Уверенность: подтверждено
- Где: `include/RE/B/BSTEvent.h:58-62`, `:100-104`
- Код:
  ```cpp
  template <class SinkEvent>
  inline void AddEventSink(BSTEventSink<SinkEvent>* a_sink)
  {
      AddEventSink(a_sink);   // при SinkEvent != Event нешаблонная перегрузка не подходит — вызывается сама себя
  }
  ```
- Суть и сценарий: при `SinkEvent == Event` выигрывает нешаблонная перегрузка, и шаблон не нужен. При `SinkEvent != Event` (синк не того события, частая опечатка при нескольких `BSTEventSink<…>`) код компилируется без предупреждений и при регистрации падает на переполнении стека, а не на ошибке типа при сборке.
- Как проверено: g++ с ASan. `BSTEventSource<EvA>::AddEventSink(SinkB*)` → «stack-overflow», стек из `AddEventSink<EvB>` (`BSTEvent.h:61`). clang `-Winfinite-recursion` предупреждения не даёт.
- Предложение: удалить обе шаблонные перегрузки или заменить их на `static_assert(std::is_same_v<SinkEvent, Event>, "sink event type mismatch")`.

### C-19. `GString::BernsteinHashFunctionCIS`: знаковое сравнение переводит в «нижний регистр» и цифры/пробелы — хеш расходится с движковым
- Вид: ошибка; Важность: низкая; Уверенность: вероятно (нужна сверка с машинным кодом движка)
- Где: `src/RE/G/GString.cpp:251-256`
- Код:
  ```cpp
  for (hash = a_seed; a_size; hash = byte ^ 33 * hash) {
      byte = *(dataIn + a_size-- - 1);
      if (byte - 65 <= 25) {   // uint8_t -> int: для byte < 'A' разность отрицательна, условие истинно
          byte += 32;
      }
  }
  ```
- Суть и сценарий: должны превращаться только 'A'..'Z'. Здесь же `+32` получает любой байт 0..64: '0' → 'P', ' ' → '@'. Так обычно выглядит расшифровка беззнакового `cmp …, 19h; ja`, записанная со знаковой арифметикой. `GStringHash<…>` (`GFxSpriteDef::frameLabels`, `GFxMovieDataDef::frameLabels`, `GASStringManager`) хранит в элементах кешированный хеш. Поиск на стороне библиотеки по метке с цифрой или пробелом («frame 1») тогда не совпадёт с хешем, который посчитал движок.
- Как проверено: чтение кода, вычисление значений вручную. Внутри библиотеки хеш самосогласован, расхождение с движком не проверено.
- Проверка: дизассемблировать `GString::BernsteinHashFunctionCIS` в SE/AE/VR (путь вставки в `GStringHash`) или в игре сравнить кешированный хеш элемента `frameLabels` для метки с цифрой с результатом библиотечной функции. Исправление: `if (static_cast<std::uint8_t>(byte - 'A') <= 25)`.

### C-20. Макрос `GMEMALIGN(a_sz, a_al)` берёт размер из переменной `a_count` вызывающего кода
- Вид: ошибка; Важность: низкая; Уверенность: подтверждено
- Где: `include/RE/G/GMemory.h:34`
- Код:
  ```cpp
  #define GMEMALIGN(a_sz, a_al) RE::GMemory::Alloc((a_count), (a_al))
  ```
- Суть и сценарий: параметр `a_sz` не используется. В функции, где есть переменная `a_count` (обычное имя в этом коде), `GMEMALIGN(a_size, 16)` молча выделит `a_count` байт, после чего запись размера `a_size` выйдет за буфер. Там, где `a_count` нет, будет ошибка компиляции.
- Как проверено: clang `-fsyntax-only`. `f(size_t a_size) { GMEMALIGN(a_size,16); }` → «use of undeclared identifier 'a_count'», вариант с параметром `a_count` компилируется. В библиотеке макрос не используется.
- Предложение: `RE::GMemory::Alloc((a_sz), (a_al))`.

### C-21. Комментарии смещений и маска противоречат полям: `MemoryManager::alignmentForPools`, `BSStringPool::Entry::_crc`, `BucketTable::kLockIndexMask`
- Вид: ошибка; Важность: низкая; Уверенность: подтверждено (арифметика)
- Где: `include/RE/M/MemoryManager.h:88-89`, `include/RE/B/BSStringPool.h:88-89`, `:104-112`
- Код:
  ```cpp
  std::uint32_t mallocBytes{ 0 };        // 450
  std::uint32_t alignmentForPools{ 4 };  // 450   <- 0x454
  std::uint16_t          _flags;  // 08
  volatile std::uint16_t _crc;    // 08           <- 0x0A
  kLockIndexMask = 0x7F   ...   mutable BSSpinLock locks[0x10000 / 0x800];  // 32 элемента, "index using hash & kLockIndexMask"
  ```
- Суть и сценарий: `sysAllocBytes` 0x44C + 4 = 0x450 (`mallocBytes`), + 4 = 0x454 (`alignmentForPools`), + 4 = 0x458 (`mainThreadMemoryProblemPassSignal`, комментарий верный). `_left` 8 байт, `_flags` 2 байта на 0x08, значит `_crc` на 0x0A. `static_assert` размеров выполняются, ошибочны только комментарии. Для `BucketTable` маска 0x7F даёт индексы 0..127, а массив `locks` — 32 элемента (0x10000/0x800). Если следовать комментарию «index using hash & kLockIndexMask», три четверти индексов выходят за массив.
- Как проверено: сложение смещений по полям; `sizeof(BucketTable) == 0x80108` сходится при 32 замках (0x80000 + 32·8 = 0x80100).
- Предложение: исправить комментарии на `454` и `0A`. Для `BucketTable` сверить формулу индекса замка с движком (вероятно `(hash & 0xFFFF) >> 11`) и заменить маску на эту формулу.

### C-22. `BSTArray`: `resize(n)` удваивает ёмкость, копирующее присваивание всегда перевыделяет, рост считается во `float`
- Вид: неоптимальное; Важность: низкая; Уверенность: подтверждено
- Где: `include/RE/B/BSTArray.h:693-695` (`change_size`), `:454-471` (`operator=(const&)`), `:717-722` (`next_capacity`)
- Код:
  ```cpp
  if (a_newSize > capacity()) {
      grow_capacity(a_newSize);   // change_capacity(next_capacity(a_newSize)) == 2 * a_newSize
  }
  ...
  cap = cap > 0 ? static_cast<size_type>(std::ceil(static_cast<float>(cap) * GROWTH_FACTOR)) : DF_CAP;
  ```
- Суть и сценарий: `resize(100)` из пустого массива даёт `capacity() == 200`. `FunctionArguments::operator()` (`include/RE/F/FunctionArguments.h:65`) так раздувает каждый `BSScrapArray<Variable>` вызова Papyrus. Копирующее присваивание делает `clear(); change_capacity(rhs.capacity())` и выделяет память даже при достаточной своей ёмкости. `float` точен только до 2²⁴, а при `cap ≥ 2³¹` преобразование `4.29e9f` → `uint32_t` — UB.
- Как проверено: стенд — `resize(100): size=100 capacity=200`.
- Предложение: в `change_size` растить до `max(a_newSize, next_capacity())`. В `operator=` перевыделять только при `capacity() < rhs.size()`. Рост считать целочисленно: `cap + cap / 2` или `cap * 2` с проверкой переполнения.

### C-23. `BSString()` по умолчанию всегда выделяет память в куче движка
- Вид: неоптимальное; Важность: низкая; Уверенность: подтверждено
- Где: `include/RE/B/BSString.h:97-100`, `:204`, `:239-253`
- Код:
  ```cpp
  BSStringT() { clear(); }
  void clear() { set_cstr(EMPTY); }
  // set_cstr: _data(nullptr) != EMPTY, len = 0 -> ++len = 1 > _capacity(0) -> allocate(1)
  ```
- Суть и сценарий: каждый временный или член-`BSString` при создании вызывает `MemoryManager::Allocate` на один байт, хотя `data()` и так возвращает `EMPTY` при `_data == nullptr`. Отсюда и утечка из C-13 при перемещающем присваивании.
- Как проверено: трассировка `set_cstr` по коду; утечка из-за этой аллокации видна в C-13 (LSan).
- Предложение: `BSStringT() = default;`. В `clear()` при `_data` ставить `_data[0] = 0; _size = 0;`, без повторной записи через `set_cstr`.

### C-24. `BSTHashMap`: нет `operator[]`, `try_emplace`, `insert_or_assign`, `count`, `at` и поиска без построения ключа
- Вид: расширение; Важность: средняя; Уверенность: подтверждено
- Где: `include/RE/B/BSTHashMap.h:322-355` (весь публичный API вставки и поиска)
- Код:
  ```cpp
  template <class... Args>
  std::pair<iterator, bool> emplace(Args&&... a_args)
  {
      return insert(value_type(std::forward<Args>(a_args)...));   // значение строится до проверки ключа
  }
  [[nodiscard]] iterator find(const key_type& a_key) { return do_find<iterator>(a_key); }
  ```
- Суть и сценарий: пользователю приходится писать `if (auto it = m.find(k); it != m.end()) it->second = v; else m.emplace(k, v);`. Для `BSTHashMap<BSFixedString, …>` поиск по `std::string_view` требует построить `BSFixedString`, то есть обратиться к пулу строк движка (захват и отпускание ссылки, блокировка корзины). `emplace` конструирует значение даже при существующем ключе. `grep "operator\[\]\|try_emplace\|insert_or_assign\|count(" BSTHashMap.h` — пусто. У `NiTMapBase` `insert_or_assign` есть.
- Предложение: добавить `try_emplace`, `insert_or_assign`, `operator[]` (при конструируемом по умолчанию `mapped_type`), `count`, `at`; гетерогенный `find(const K&)` при `Hash::is_transparent`/`KeyEq::is_transparent`. Для `BSFixedString` дать прозрачный хешер, который ищет запись пула без вставки.

### C-25. Совместимость со стандартной библиотекой: `BSTList` — не range, итераторы `GArray` — не `input_iterator`, у `BSTTuple` нет `<=>`, у умных указателей нет `std::hash`
- Вид: расширение; Важность: средняя; Уверенность: подтверждено
- Где: `include/RE/B/BSTList.h:48-54` (у итераторов нет `difference_type`/`reference`), `include/RE/G/GArrayBase.h:18-24` (нет ни одного typedef), `include/RE/B/BSSimpleList.h:170-171` (нет `iterator` → `const_iterator`), `include/RE/B/BSTTuple.h:306-319` (только `==` и `<`), `include/RE/B/BSTSmartPointer.h:239-273`, `include/RE/N/NiSmartPointer.h:201-235`, `include/RE/G/GPtr.h:213-247`
- Код:
  ```cpp
  struct const_iterator
  {
      using value_type = T;
      using const_pointer = const T*;
      using iterator_category = std::bidirectional_iterator_tag;   // difference_type, reference нет
  ```
- Суть и сценарий: результаты проверки концептами — `std::input_iterator<BSTList<int>::iterator> = 0`, `std::ranges::range<BSTList<int>> = 0`, `std::input_iterator<GArray<int>::iterator> = 0`, `std::totally_ordered<BSTTuple<int,int>> = 0` (`std::ranges::sort` по массиву пар не собирается), `std::hash<BSTSmartPointer<N>>` отключён, `std::equality_comparable<BSTAutoPointer<int>> = 0` (сравнения и конвертирующие конструкторы есть только для `RefManager` по умолчанию). Нет `BSCRC32_<BSTSmartPointer<T>>`, хотя для `NiPointer` он есть, поэтому `BSTHashMap<BSTSmartPointer<X>, …>` не собирается. Перемещающее присваивание `BSTArray` и умных указателей не `noexcept` (`std::is_nothrow_move_assignable_v = 0`). Положительные результаты: `contiguous_range<BSTArray>`, `forward_range<BSTHashMap>`, `forward_range<BSSimpleList>` — 1.
- Предложение: добавить недостающие typedef (`difference_type = std::ptrdiff_t`, `reference`, `pointer`) и `value_type` у `GArrayBase::iterator`. `BSTTuple`: `friend auto operator<=>(const BSTTuple&, const BSTTuple&) = default;` (или ручной с `std::tie`). Для трёх умных указателей — `operator<=>`, сравнение с `T*`, `std::hash`, `BSCRC32_` и шаблон `template <class T, template <class> class R>` у сравнений. Пометить `noexcept` перемещающие присваивания.

### C-26. `BSSpinLock`/`BSReadWriteLock` не удовлетворяют BasicLockable/SharedLockable — `std::scoped_lock`/`std::shared_lock` неприменимы
- Вид: расширение; Важность: низкая; Уверенность: подтверждено
- Где: `include/RE/B/BSAtomic.h:96-137`
- Код:
  ```cpp
  void Lock(std::uint32_t a_pauseAttempts = 0);
  void Unlock();
  ...
  void LockForRead(); void UnlockForRead(); void LockForWrite(); void UnlockForWrite();
  ```
- Суть и сценарий: собственные guard'ы (`BSSpinLockGuard` и др.) нельзя переместить или вернуть из функции, и с ними нет `std::unique_lock` с `defer_lock`/`try_to_lock`, `std::scoped_lock` на два замка без взаимоблокировки и `std::condition_variable_any`. `TryLock` нет вовсе, хотя очередь сообщений (`BSTMessageQueue::TryPush/TryPop`) в движке этим пользуется.
- Как проверено: `requires(RE::BSSpinLock& l){ l.lock(); }` → «has no member named 'lock'; did you mean 'Lock'».
- Предложение: добавить `lock()/unlock()/try_lock()` (тонкие обёртки над `Lock/Unlock` и однократным `InterlockedCompareExchange`) и для `BSReadWriteLock` — `lock()/unlock()/lock_shared()/unlock_shared()`. Существующие имена сохранить.

### C-27. Форматирование: нет `std::formatter` для `BSFixedString`/`BSString`/`GString`; в `fmt::formatter<BSFixedString>` исключение создаётся, но не бросается
- Вид: расширение; Важность: низкая; Уверенность: подтверждено
- Где: `include/RE/B/BSFixedString.h:254-283`
- Код:
  ```cpp
  if (it != end && (*it == 'f'))
      presentation = *it++;
  if (it != end && *it != '}')
      format_error("invalid format");   // временный объект, без throw
  return it;
  ```
- Суть и сценарий: форматер скопирован из примера fmt для «точки» (спецификатор `'f'`), и выравнивание с шириной (`{:>20}`) для строк не поддерживается. Неверный спецификатор не даёт внятной ошибки: исключение создаётся и тут же отбрасывается. `std::format("{}", bsfs)` в C++23-плагине не компилируется, хотя в библиотеке уже есть готовый образец — `std::formatter<REL::Version, CharT> : formatter<std::basic_string_view<CharT>, CharT>` (`include/REL/Version.h:179`), `ActorValue`, `EffectArchetype`.
- Предложение: `template <class CharT> struct std::formatter<RE::detail::BSFixedString<CharT>, CharT> : std::formatter<std::basic_string_view<CharT>, CharT>` с `format(std::basic_string_view<CharT>(v), ctx)`. То же для `BSString` и `GString` (после C-5), а `fmt::formatter` наследовать от `fmt::formatter<std::string_view>`.

---

## Проверено и в порядке

- `BSTArray` c `BSTArrayHeapAllocator`: глубокое копирование в конструкторе и присваивании (с проверкой на самоприсваивание), `erase` (сдвиг перемещением + `pop_back`), `reserve`, `clear`, `shrink_to_fit`, `pop_back`, `begin()/end()` для пустого массива, перемещающий конструктор аллокатора. `BSStaticArray`. `BSTSmallSharedArray` после #361. Перенос элементов через `memcpy` совпадает с движком: типы движка тривиально перемещаемы, это сознательное решение, а не ошибка.
- `BSTScatterTable`: вставка с вытеснением «чужого» элемента из домашнего слота (инвариант «цепочка содержит только ключи своего слота» соблюдается), `find`, обе ветки `reserve` (включая статический аллокатор, где `newEntries == oldEntries` недостижимо), `clear`, `get_free_entry` с циклическим `_good`, перемещающее присваивание. Размеры и смещения `BSTScatterTableStandardParent`/`FixedParent`, `_sentinel` 18/10, `_allocator` 20.
- `BSTTuple`: конструкторы 1–8, piecewise, присваивания с проверкой на себя, `swap`, `make_pair`, CTAD. Структурные привязки работают через публичные члены.
- `CRC`: таблица и алгоритм CRC32 без начального и конечного XOR — сверка с движком вне области. `BSCRC32_` для арифметики, перечислений, указателей, `nullptr_t`, `string_view`. Для `BSFixedString` хешируется указатель пула, и это согласовано с `operator==`, сравнивающим указатели (пул регистронезависимый).
- `BSFixedString`: подсчёт ссылок при копировании, перемещении и присваивании (без самоприсваивания); сравнение со `string_view` проверяет длину до `_strnicmp`; `BSStringPool::Entry::acquire` — насыщающий CAS (как у движка).
- `BSAtomic`: `BSSpinLock::Lock/Unlock` (реентерабельность по `_owningThread`, CAS, барьеры), guard'ы некопируемы и неперемещаемы, `[[nodiscard]]` на конструкторах, прослойки `BSReadWriteLock`, `BSTAtomicValue`, `BSNonReentrantSpinLock`. Раскладки 8/8/4/0x28.
- `BSTEventSource`: протокол `pendingRegisters/pendingUnregisters` во время рассылки, вложенный `SendEvent` из синка (реентерабельный спин-замок), `PrependEventSink`. Смещения 00/18/30/48/50, размер 0x58.
- `NiRefObject` (атомарные Inc/Dec, `DeleteThis` через vtable), конструкторы и перемещение `NiPointer`, `BSCRC32_<NiPointer>`. `GRefCountImpl`/`GRefCountNTSImpl`, начальный счётчик 1 и `make_gptr` (сбрасывает лишнюю ссылку).
- `GArrayDataBase::Reserve/ResizeNoConstruct`, `GArrayData::PushBack/Append`, `GArrayBase::RemoveAt/InsertAt` (повторяют оригинал Scaleform), `GConstructorMov`, `GAllocatorGH/LH`, `GMemory` (обёртки над глобальной кучей).
- `MemoryManager`: свободные функции `malloc/aligned_alloc/calloc/realloc/free`, `malloc_runtime`. Смещения `MemoryManager` (кроме комментария из C-21), `ThreadScrapHeap` 0xA0, `ScrapHeap` 0x90 (все поля посчитаны вручную). `BSScrapArrayAllocator::allocate/deallocate` (`src/RE/B/BSTArray.cpp`).
- `TES_HEAP_REDEFINE_NEW`: выровненный `operator delete` без выровненного `operator new` — дефект скрытый. Ни один тип с `alignof > 16` макрос не использует (единственный `alignas(0x40)` — вложенный `hkpShape::ShapeFuncs2` без макроса), поэтому в находки не включено.
- `BSTSingleton*`, `BSTFreeList`/`BSTStaticFreeList`, `BSTMessageQueue`/`BSTCommon*MessageQueue`, `BSTCaseInsensitiveStringMap`, `NiTPointerMap`, `NiTStringMap`, `NiTPointerAllocator`, `NiTDefaultAllocator`: только объявления раскладок движка, смещения и `static_assert` согласованы.
- Раскладки `NiTArray` (0x18), `NiTLargeArray` (0x20), `NiTMapBase`/`NiTMap` (0x20), `NiTListBase` (head/tail/allocator), `GString::DataDesc` (0x10, выделение `len+8+4+1`), `GArray`/`GArrayLH` (0x18).
- Сознательно не включено из-за недостатка доказательств: `NiTArray::end()` считает до `_capacity`, а не до `_freeIdx` (зависит от того, обнуляет ли движок хвост массива; проверяется в игре на `NiNode` после `DetachChild`); `ScrapHeap::Size` читает заголовок по `a_mem`, а не по `a_mem - 0x10` (виртуальная функция, у объектов движка вызывается движковая версия); `BSCRC32_<std::wstring_view>` хеширует `size()` байт вместо `size()*sizeof(wchar_t)` (внутри библиотеки согласовано, совпадение с движком не проверено); у `NiTListBase` не компилируются постфиксный `++` и конструктор по умолчанию (`allocator(0)`) — списки создаёт только движок.
