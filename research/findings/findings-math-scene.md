# CommonLibSSE-NG 9.1.0 (`ng`, a898f4698): математика, граф сцены, рендер, Scaleform

Область: `src/RE/N/*` (NiMath, NiPoint2/3, NiMatrix3, NiQuaternion, NiTransform, NiColor, NiAVObject, NiObjectNET, NiNode, NiCamera), `src/RE/B/BSVisit.cpp`, `BSGeometry`, `BSLightingShader*`, `BSShader*`, `BSEffectShaderData`, `src/RE/R/Renderer.cpp`, `src/RE/G/*` (GFxValue, GString, GFxWStringBuffer, GFxMovie, GFxMovieView, GFxTranslator и др.), вместе с `include/RE`. `src/RE/C/Color.cpp` взят как вторая половина преобразования NiColor↔Color. Файлов `NiPoint4.cpp`, `NiBound.cpp`, `NiRect.cpp`, `BSTriShape.cpp` и `BSDynamicTriShape.cpp` в репозитории нет: эти типы описаны только в заголовках, и заголовки просмотрены.

Как проверялось: каждую находку подтверждает чтение кода. История смотрелась через `git log`/`git blame`/`git show`, удалённые ветки — через `git branch -r` и `git diff HEAD...<ветка>` (131 ветка, среди них `sync/powerof3-*`, `dev`, `vr`). По PR апстрима искал через GitHub-поиск. Формулы проверены численно в python3/numpy. Клон не менялся.

Итог: 17 находок — 14 ошибок, 1 неоптимальное, 2 расширения.

---

### M-1. `NiFastATan2` возвращает atan2 с обратным знаком при |y| ≤ |x| (регрессия 2021 г.)
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено
- Где: `src/RE/N/NiMath.cpp:61`. Через эту функцию ломаются `src/RE/N/NiMatrix3.cpp:56-57` (`ToEulerAnglesXYZ`), `src/RE/T/TESObjectREFR.cpp:400` (`GetHeadingAngle`) и `:957` (`MoveToNode`)
- Код:
  ```cpp
  		result += 0.9998660F;
  		result *= z;

  		result = offset - result;      // было: if (offset) { result = offset - result; }

  		if (a_y < 0.0F && a_x < 0.0F) {
  			result -= NI_PI;
  ```
- Суть и сценарий: при |y| ≤ |x| смещение `offset` равно 0, и безусловное `result = offset - result` меняет знак полинома atan(y/x). У Gamebryo и в первой версии файла (88daa12f2e, 2019) вычитание стояло под `if (offset)`. Условие убрал коммит b2532f4bab «remove the casts and enforce float postfix» (2021-06-20), то есть это регрессия рефакторинга.
  - `NiFastATan2(1, 2)` = −0.4637 при верном +0.4636; `NiFastATan2(1, −2)` = 3.6052 при верном 2.6779 — результат ещё и выходит из (−π, π].
  - Кругооборот через Эйлера: `NiMatrix3(0.3, 0.2, 0.5).ToEulerAnglesXYZ()` даёт (−0.3, 0.2, −0.5). Знак X и Z теряется, пока угол по модулю меньше 45°; при 1.0 рад ответ уже верный, поэтому на 45° появляется разрыв.
  - `TESObjectREFR::GetHeadingAngle`: цель в точке (dx=1, dy=10), взгляд на север. Метод возвращает −5.71° вместо +5.71°. При dx=0.99, dy=1 выходит −44.71°, при dx=1.01, dy=1 — +45.28°.
  - `MoveToNode` ставит объект с зеркальным поворотом по X/Z, если углы по модулю меньше 45°.
  Соседний `NiTransform::GetHeadingAngle` (`src/RE/N/NiTransform.cpp:45`) использует `std::atan2f` и считает верно, так что два одноимённых метода расходятся.
- Как проверено: `git blame`/`git show b2532f4bab`, `git log -5 -- src/RE/N/NiMath.cpp` (исправлений после нет), веток с правкой нет. Функция перенесена в python один в один, сравнение с `math.atan2` на 8 квадрантах плюс кругооборот `SetEulerAnglesXYZ`→`ToEulerAnglesXYZ`. С возвращённым `if (offset)` расхождений нет.
- Предложение: вернуть `if (offset != 0.0F) { result = offset - result; }`. Добавить тест `tests/RE/N/NiMath.test.cpp` на кругооборот Эйлера и на знак по всем квадрантам.

### M-2. `NiCamera::WorldPtToScreenPt3(point, …)` в VR берёт матрицу со смещения 0 объекта
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено (по коду; поведение на живом VR не проверялось)
- Где: `src/RE/N/NiCamera.cpp:36`, `include/RE/N/NiCamera.h:89`
- Код:
  ```cpp
  // NiCamera.h
  RUNTIME_DATA_ACCESSOR(RUNTIME_DATA, 0x110, 0);                 // VR-смещение 0 = «нет VR-раскладки»
  VR_RUNTIME_DATA_ACCESSOR(RUNTIME_DATA_VR, GetVRRuntimeData, 0x138);
  // NiCamera.cpp
  return WorldPtToScreenPt3(GetRuntimeData().worldToCam, GetRuntimeData2().port, a_point, ...);
  ```
- Суть и сценарий: коммит 00b0142696 «fix(VR): NiCamera RE» (2026-03) перенёс VR-раскладку в `RUNTIME_DATA_VR` (`worldToCam` там по 0x138), а у `GetRuntimeData()` VR-смещение сменил с 0x138 на 0. Макрос `RUNTIME_DATA_ACCESSOR_EX` (`include/REL/RuntimeDataAccessors.h:55-60`) в VR при смещении 0 срабатывает на assert, а в release возвращает `this + 0`. PR #353 (c919cccd9) поправил только `GetRuntimeData2`.
  Последствие: любой плагин, проецирующий точку мира на экран через экземплярный `WorldPtToScreenPt3` (маркеры HUD, всплывающий урон, прицел), в VR-Debug падает на assert, а в VR-Release считает проекцию по «матрице» из указателя vtable, счётчика ссылок и имени объекта и получает мусорные координаты.
- Как проверено: `git show 00b0142696`, `git show c919cccd9`, чтение `RelocateMember` (`include/REL/Relocation.h:1031`). `grep worldToCam` находит одно место использования.
- Предложение: `const auto& m = REL::Module::IsVR() ? GetVRRuntimeData().worldToCam : GetRuntimeData().worldToCam;`. Правило AGENTS.md требует проверить результат в живом VR: у VR есть ещё поглазные `eyeViewMatrices`, и для проекции в конкретный глаз может понадобиться отдельная перегрузка.

### M-3. `GFxValue::operator=(GFxValue&&)` не освобождает прежнее управляемое значение
- Вид: ошибка; Важность: высокая; Уверенность: подтверждено
- Где: `src/RE/G/GFxValue.cpp:618-631`
- Код:
  ```cpp
  GFxValue& GFxValue::operator=(GFxValue&& a_rhs)
  {
  	if (this != std::addressof(a_rhs)) {
  		_objectInterface = std::move(a_rhs._objectInterface);   // старое значение не Release
  		a_rhs._objectInterface = nullptr;
  		_type = std::move(a_rhs._type);
  ```
- Суть и сценарий: копирующее присваивание (строки 601-616) и `ChangeType` вызывают `ReleaseManagedValue()`, перемещающее — нет. Если `*this` держит объект, массив, DisplayObject или управляемую строку, ссылка теряется, а `ObjectRelease` не вызывается никогда. Где это случается:
  - `GFxValue obj; movie->CreateObject(&obj); obj = RE::GFxValue(5.0);` — временное связывается с move-присваиванием;
  - `args[0] = GFxValue(x)` поверх элемента, заполненного через `GetMember`/`GetElement`;
  - `std::vector<GFxValue>::erase`/`insert`/`std::swap`/`std::sort` — сдвиг элементов идёт через move-присваивание, поэтому каждый сдвинутый управляемый элемент теряет ссылку.
  Итог: объекты ActionScript и символы остаются в куче фильма и не собираются, пока фильм живёт; меню, переоткрываемые много раз, накапливают утечку.
- Как проверено: сравнение с копирующим присваиванием и с `ChangeType` (строки 1064-1070). Метод без изменений с 2020 г. (`git log -S`).
- Предложение: в начале ветки `if` добавить `if (IsManagedValue()) { ReleaseManagedValue(); }`, остальное оставить.

### M-4. `NiObjectNET::AddExtraData(key, extra)`: оба условия инвертированы, метод никогда не работает
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `src/RE/N/NiObjectNET.cpp:13-25`
- Код:
  ```cpp
  if (!a_key.empty()) {          // любой непустой ключ -> false
  	return false;
  }
  ...
  if (!a_extra->GetName().empty()) {
  	a_extra->SetName(a_key);    // у именованного extra имя затирается пустым ключом
  } else if (a_key != a_extra->GetName()) {
  ```
- Суть и сценарий: `node->AddExtraData("MyKey", ed)` всегда возвращает false, и данные не добавляются. С пустым ключом `AddExtraData("", ed)` стирает имя у `ed` и вставляет запись без имени, которую потом не найти через `GetExtraData`/`HasExtraData`. Замысел (Gamebryo `NiObjectNET::AddExtraData`): пустой ключ отклонить, extra без имени назвать ключом, при несовпадении имени вернуть false. Одноаргументная перегрузка (строки 30-65) написана правильно.
- Как проверено: `git blame` — код не менялся с 33f43f6ce5 (2019). Семантика `BSFixedString::empty()` и `operator==` сверена по `include/RE/B/BSFixedString.h:127-139`. В библиотеке у метода вызовов нет.
- Предложение: `if (a_key.empty()) return false;` и `if (a_extra->GetName().empty()) a_extra->SetName(a_key); else if (a_key != a_extra->GetName()) return false;`.

### M-5. `GFxValue::DisplayInfo`: `SetYRotation` ставит флаг `kRotation`, конструкторы не ставят флагов
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `src/RE/G/GFxValue.cpp:231-235`, `src/RE/G/GFxValue.cpp:7-18`
- Код:
  ```cpp
  void GFxValue::DisplayInfo::SetYRotation(double a_degrees)
  {
  	_flags.set(Flag::kRotation);          // должно быть kYRotation (ср. SetXRotation, стр. 213-217)
  	_yRotation = a_degrees;
  }
  GFxValue::DisplayInfo::DisplayInfo(double a_x, double a_y) : _x(a_x), _y(a_y) {}   // флаги kNone
  ```
- Суть и сценарий: `SetDisplayInfo` применяет только поля, у которых стоит флаг, — на этом построены `GetPerspectiveMatrix3D`/`IsFlagSet` в том же файле и `DisplayInfo` в Scaleform SDK.
  - `info.SetYRotation(30); clip.SetDisplayInfo(info);` не поворачивает клип по Y (флаг `kYRotation` не поднят) и одновременно выставляет 2D-поворот `_rotation`: 0 или прежнее значение из `GetDisplayInfo`. То есть вызов сбрасывает обычный поворот клипа.
  - `GFxValue::DisplayInfo info(100.0, 50.0); clip.SetDisplayInfo(info);` ничего не делает: у `DisplayInfo(x,y)`, `DisplayInfo(rotation)` и `DisplayInfo(visible)` поле `_flags` остаётся `kNone`. В Scaleform SDK (GFxPlayer.h) эти конструкторы ставят `V_x|V_y`, `V_rotation` и `V_visible`; значения enum `Flag` здесь совпадают с SDK побитно.
- Как проверено: сравнение с соседними сеттерами и с `include/RE/G/GFxValue.h:125-147`.
- Предложение: `SetYRotation` → `Flag::kYRotation`. В конструкторы добавить `_flags(Flag::kX | Flag::kY)`, `_flags(Flag::kRotation)` и `_flags(Flag::kVisible)` соответственно.

### M-6. `GFxValue(std::string_view)` / `SetString(std::string_view)` отбрасывают длину и копят висячие указатели
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `src/RE/G/GFxValue.cpp:500-507`, `:518-525`, `:777-791`; объявления — `include/RE/G/GFxValue.h:285,306`
- Код:
  ```cpp
  GFxValue::GFxValue(std::string_view a_rhs) : ... _type(ValueType::kString) ...
  { _value.string = a_rhs.data(); }
  void GFxValue::SetString(std::string_view a_str) { SetString(a_str.data()); }
  ```
- Суть и сценарий: неуправляемая строка GFxValue — это указатель на NUL-терминированную строку без владения.
  1. Подстрока: `v.SetString(std::string_view("Iron Sword (Legendary)").substr(0, 10));` — Flash получает всю строку «Iron Sword (Legendary)»: размер отброшен, чтение идёт до ближайшего NUL. Если за view NUL нет, чтение уходит за буфер.
  2. Временный `std::string`: перегрузка неявно принимает `std::string` (одно пользовательское преобразование), поэтому `RE::GFxValue v(fmt::format("{}", n));` и `v = someFuncReturningStdString();` компилируются, а указатель повисает сразу после выражения. То же для `std::wstring_view` и UTF-16-текста.
  Вызовов этих перегрузок внутри библиотеки нет, пострадавшие — плагины.
- Как проверено: чтение кода. `std::string_view::data()` не гарантирует NUL на `size()`.
- Предложение: так как GFxValue ничем не владеет, у перегрузок два честных варианта: (а) удалить их или объявить `= delete` для `std::string&&`, оставив `const char*`; (б) в debug проверять `assert(a_str.data()[a_str.size()] == '\0')` и документировать, что для копии нужен `GFxMovie::CreateString`/`CreateStringW` (`include/RE/G/GFxMovie.h:53-54`).

### M-7. `NiQuaternion::SetEulerAnglesXYZ` расходится с `NiMatrix3::SetEulerAnglesXYZ` по оси Y
- Вид: ошибка; Важность: средняя; Уверенность: вероятно (расхождение подтверждено численно; что оно не повторяет движок, требует сверки с бинарником)
- Где: `src/RE/N/NiQuaternion.cpp:58-71` (строка 69 — компонента `y`)
- Код:
  ```cpp
  float cos_x = std::cos(a_x * -0.5f);
  float cos_y = std::cos(a_y * 0.5f);      // у X и Z стоит -0.5, у Y +0.5
  float cos_z = std::cos(a_z * -0.5f);
  ...
  y = sin_x * cos_y * sin_z + sin_y * cos_x * cos_z;
  ```
- Суть и сценарий: `NiQuaternion(x,y,z).ToRotation()` должна совпадать с `NiMatrix3(x,y,z)`: оба конструктора называются «Эйлер XYZ» и живут в одном классе рядом с `NiQuaternion(const NiMatrix3&)`. Но `NiQuaternion(0, 0.5, 0).ToRotation()` = `[[0.8776,0,+0.4794],[0,1,0],[−0.4794,0,0.8776]]`, а `NiMatrix3(0, 0.5, 0)` = `[[0.8776,0,−0.4794],[0,1,0],[+0.4794,0,0.8776]]`: поворот по Y идёт в обратную сторону. На 1000 случайных углов текущий кватернион отличается от эталона Gamebryo `qX(−x/2)·qY(−y/2)·qZ(−z/2)` (он в точности равен `NiMatrix3::SetEulerAnglesXYZ`) только знаком компоненты `y`. Код с пометкой `2i64` — вывод Hex-Rays (d7433595f, 2026-02). Похоже, при переносе потеряно отрицание, которое MSVC кодирует как `xorps` с маской знака. Плагин, собирающий ориентацию (VR-руки, сохранение/восстановление поворота) через `NiQuaternion(x,y,z)`, получает при ненулевом Y поворот, отличный от `NiMatrix3(x,y,z)`.
- Как проверено: numpy, 1000 случайных троек углов. Инверсия `y` даёт совпадение 1000/1000. `SetRotation`/`ToRotation` взаимно обратны (см. «в порядке»).
- Предложение: сверить функцию движка в Ghidra (адрес по коммиту d7433595f не указан). При подтверждении — `y = -(sin_x * cos_y * sin_z + sin_y * cos_x * cos_z);` и тест `ToRotation(NiQuaternion(x,y,z)) == NiMatrix3(x,y,z)`.

### M-8. `Color(const NiColor&)` делит 255 на компоненту; `NiColor::ToHex` без ведущих нулей
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `src/RE/C/Color.cpp:7-12`, `src/RE/N/NiColor.cpp:22-29`
- Код:
  ```cpp
  Color::Color(const NiColor& a_rhs) :
  	red(static_cast<std::uint8_t>(255.0f / a_rhs.red)),     // должно быть a_rhs.red * 255
  	green(static_cast<std::uint8_t>(255.0f / a_rhs.green)),
  ...
  return std::format("{:X}{:X}{:X}", r, g, b);              // NiColor::ToHex
  ```
- Суть и сценарий: `Color(NiColor(0.5f, 0.25f, 0.1f))`: 255/0.5 = 510, 255/0.25 = 1020, 255/0.1 = 2550 — значения вне диапазона `uint8_t`, приведение float→uint8 здесь UB. На практике (усечение через int32) выходит (254, 252, 246) вместо (127, 63, 25). Для 0.0 получается inf → UB, для 1.0 — 255, поэтому белый цвет выглядит правильным и ошибку не замечают. Коммит 6569070ba «Fix color conversion» (2022) эту строку не тронул. `NiColor(1,0,0).ToHex()` = "FF00" вместо "FF0000"; (15/255, 1, 15/255) и (1, 15/255, 15/255) оба дают "FFFF", то есть строка неоднозначна. В `ToInt`/`ToHex` значения > 1 (HDR-цвета NiColor) заворачиваются через `& 0xFF`/`{:X}`, а не клампятся.
- Как проверено: `git blame` (adc2f32da4, 2021), `git show 6569070ba`. Числа посчитаны в float32.
- Предложение: `static_cast<std::uint8_t>(std::clamp(a_rhs.red, 0.f, 1.f) * 255.0f + 0.5f)`; формат `"{:02X}{:02X}{:02X}"` с тем же клампом в `ToInt`/`ToHex`.

### M-9. `NiAVObject::GetMass` читает `hkpRigidBody::motion` у фантомов — выход за объект
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено (по смещениям; частота зависит от наличия фантомов в поддереве)
- Где: `src/RE/N/NiAVObject.cpp:100-104`
- Код:
  ```cpp
  BSVisit::TraverseScenegraphCollision(this, [&](bhkNiCollisionObject* a_col) -> BSVisit::BSVisitControl {
  	if (auto hkpBody = a_col->body ? static_cast<RE::hkpRigidBody*>(a_col->body->referencedObject.get()) : nullptr) {
  		mass += hkpBody->motion.GetMass();
  ```
- Суть и сценарий: `bhkNiCollisionObject::body` имеет тип `bhkWorldObject`. У `bhkPCollisionObject`/`bhkSPCollisionObject` (фантомы: триггеры, часть активаторов) это `bhkPhantom`, а `referencedObject` — `hkpAabbPhantom` (0x130 байт) или `hkpSimpleShapePhantom` (0x1C0). `motion.inertiaAndMassInv` лежит по смещению 0x150 + 0xD0 = 0x220, это за пределами обоих объектов. Результат — чтение соседней памяти кучи: в сумму попадает 1/мусор (inf, NaN, огромные значения) либо access violation. Соседний `GetCollisionLayer` (строки 57-58) проверяет тип через `AsBhkRigidBody()`.
- Как проверено: размеры и смещения — `include/RE/H/hkpEntity.h:114`, `hkpMotion.h:80`, `hkpAabbPhantom.h:44`, `hkpSimpleShapePhantom.h:34`.
- Предложение: `auto rb = a_col->body ? a_col->body->AsBhkRigidBody() : nullptr; if (rb && rb->referencedObject) …`.

### M-10. `BSVisit::Traverse*`: после колбэка обход продолжает по сырому указателю — UAF при отсоединении узла
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено (по коду)
- Где: `src/RE/B/BSVisit.cpp:102-114` (так же в `TraverseScenegraphCollision`, строки 23-35)
- Код:
  ```cpp
  result = a_func(a_object);
  ...
  auto node = a_object->AsNode();                    // a_object мог быть удалён в a_func
  if (node) {
  	for (auto& child : node->GetChildren()) {
  		result = TraverseScenegraphObjects(child.get(), a_func);
  ```
- Суть и сценарий: частый приём в плагинах — «удалить из 3D все узлы с именем X»: `TraverseScenegraphObjects(root, [](NiAVObject* o){ if (o->name == "Torch") o->parent->DetachChild2(o); return kContinue; })`. `DetachChild` обнуляет `NiPointer` в массиве родителя. Если других ссылок нет, объект удаляется, после чего обход вызывает виртуальный `AsNode()` на освобождённой памяти. Кроме того, диапазонный `for` держит ссылку в массив `children`: `AttachChild` внутри колбэка может перераспределить массив, и итератор станет недействительным. Нигде не документировано, что менять граф в колбэке нельзя.
- Как проверено: чтение кода. `GetChildren()` — `NiTObjectArray<NiPointer<NiAVObject>>` (`include/RE/N/NiNode.h:59`).
- Предложение: в начале функции держать `NiPointer<NiAVObject> hold(a_object);`, по детям идти по индексу с повторным чтением размера и `NiPointer` на ребёнка. Либо явно запретить изменение графа в колбэке (комментарий плюс assert на размер массива в debug).

### M-11. `GFxWStringBuffer`: запись по nullptr, копия без терминатора, `back()` за границей
- Вид: ошибка; Важность: средняя; Уверенность: подтверждено
- Где: `src/RE/G/GFxWStringBuffer.cpp:131-144` и `:241-243`; `:56-65`; `:184-192`
- Код:
  ```cpp
  _length = 0; auto len = a_rhs ? std::wcslen(a_rhs) : 0;
  resize(len);                       // resize(0) при _length==0 сразу return, _text остаётся nullptr
  if (a_rhs) { std::wmemcpy(_text, a_rhs, _length); _text[_length] = L'\0'; }   // запись в nullptr
  ...
  _text = alloc(_length); std::wmemcpy(_text, a_rhs._text, _length);   // copy-ctor: нет места под L'\0'
  ...
  return operator[](size());         // back(): индекс _length
  ```
- Суть и сценарий:
  1. `RE::GFxWStringBuffer b; b = L"";` (буфер без резерва, как в `src/SKSE/Translation.cpp:168`) пишет `L'\0'` по адресу 0 → access violation. Тот же путь — `GFxTranslator::TranslateInfo::SetResult(L"")` с длиной по умолчанию (`src/RE/G/GFxTranslator.cpp:42`) в собственном переводчике плагина. Копирующее присваивание из пустого буфера с ненулевым `_text` делает то же самое.
  2. Копирующий конструктор выделяет `_length` символов без терминатора, а `c_str()` возвращает `_text` — `wcslen`/`utf16_to_utf8` читают за буфер. Он же копирует `_reserved` чужого объекта (часто стековый `Reserve<N>`): последующий `resize` пишет в чужой, возможно уже мёртвый буфер.
  3. `back()` вызывает `operator[](size())`: в debug срабатывает assert, в release возвращается терминатор, а не последний символ.
- Как проверено: трассировка по коду `resize`/`release`. Файл не менялся с 2021 г.
- Предложение: в `resize` не выходить досрочно при `_text == nullptr` (или всегда выделять `a_count + 1`). Копирующий конструктор — `alloc(_length + 1)` плюс терминатор, `_reserved` не копировать (по памяти о Scaleform SDK: там `Reserved(0,0)` и `*this = other`). `back()` → `operator[](size() - 1)`.

### M-12. `BSLightingShaderProperty::CopyMembers` выделяет `emissiveColor` из кучи CRT плагина
- Вид: ошибка; Важность: средняя; Уверенность: вероятно (что освобождает деструктор движка, по бинарнику не сверено)
- Где: `src/RE/B/BSLightingShaderProperty.cpp:13-16`
- Код:
  ```cpp
  if (flags.all(EShaderPropertyFlag::kOwnEmit) && a_other->emissiveColor) {
  	if (!emissiveColor) {
  		emissiveColor = new NiColor();      // глобальный operator new плагина
  	}
  ```
- Суть и сценарий: `NiColor` не переопределяет `operator new` (нет `TES_HEAP_REDEFINE_NEW`), поэтому память приходит из CRT плагина. Флаг `kOwnEmit` означает, что свойство владеет цветом и освободит его в своём деструкторе кодом движка, через `MemoryManager`. Освобождение указателя из чужой кучи повреждает кучу; падение отложено и случается при выгрузке 3D (смена ячейки). Остальная библиотека выделяет объекты движка через `RE::malloc`/`TES_HEAP_REDEFINE_NEW` — например, `BSEffectShaderData` в `NiAVObject::TintScenegraph`.
- Как проверено: `grep TES_HEAP_REDEFINE_NEW` (у `NiColor` нет, у `BSIntrusiveRefCounted`/`NiRefObject` есть). `git blame` — строка с 2021 г.
- Предложение: `emissiveColor = RE::malloc<NiColor>(); std::construct_at(emissiveColor);`. Проверить в Ghidra, чем деструктор `BSLightingShaderProperty` освобождает `emissiveColor`.

### M-13. `fixed_range_to_radians`: множитель 2π/6553.6 вместо 1/1000 для `BSInvMarker`
- Вид: ошибка; Важность: низкая; Уверенность: вероятно
- Где: `include/RE/N/NiMath.h:26-29`, используется в `src/RE/B/BSInvMarker.cpp:6-13`
- Код:
  ```cpp
  inline float fixed_range_to_radians(uint16_t a_fixed_range)
  {
  	return static_cast<float>(a_fixed_range) * (2.0f * NI_PI / 6553.6f);
  }
  ```
- Суть и сценарий: поля `BSInvMarker::rotationX/Y/Z` в NIF хранятся в тысячных радиана. В описании `BSInvMarker` в nif.xml (niftools; цитата по памяти, в репозитории её нет) сказано: «a short of 4712 appears as 4.712». Здесь 4712 → 4.5176 рад (258.8°) вместо 4.712 (270°), 6283 → 345.1° вместо 360°, то есть 11–15° ошибки в угле показа предмета в инвентаре. Функция появилась вместе с `BSInvMarker` (60f8fcc03, 2026-01) без указания источника константы.
- Как проверено: `git show 60f8fcc03`, численный расчёт.
- Предложение: сверить с кодом `Inventory3DManager` в Ghidra (как движок переводит `rotationX`). Если там /1000 — заменить множитель на `0.001f`.

### M-14. `NiMatrix3::Inverse` объявлен, но нигде не определён
- Вид: ошибка; Важность: низкая; Уверенность: подтверждено
- Где: `include/RE/N/NiMatrix3.h:31`
- Код:
  ```cpp
  bool      Inverse(NiMatrix3& a_in) const;
  ```
- Суть и сценарий: `m.Inverse(out)` компилируется, но плагин не линкуется (LNK2019). Функция нужна для перевода между мировой и локальной системой узла, когда в матрице есть масштаб, и в `src/RE/N/NiMatrix3.cpp` её нет.
- Как проверено: `grep -rn "Inverse" src include` — определение отсутствует.
- Предложение: реализовать через сопряжённую матрицу и определитель, вернуть `false` при |det| < ε (так в Gamebryo). Для ортонормированных матриц в комментарии отослать к `Transpose()`.

### M-15. `BSVisit`: `std::function` передаётся по значению и копируется на каждом уровне рекурсии
- Вид: неоптимальное; Важность: низкая; Уверенность: подтверждено
- Где: `include/RE/B/BSVisit.h:18-21`, `src/RE/B/BSVisit.cpp:13,32,58,84,110`
- Код:
  ```cpp
  BSVisitControl TraverseScenegraphObjects(NiAVObject* a_object, std::function<BSVisitControl(NiAVObject*)> a_func);
  ...
  result = TraverseScenegraphObjects(child.get(), a_func);   // копия std::function на каждого ребёнка
  ```
- Суть и сценарий: на каждый узел (скелет NPC — сотни узлов) копируется `std::function`, а лямбда, не влезшая в SBO (у MSVC около 7 указателей), копируется с выделением памяти. На этой функции построены `CullGeometry`, `UpdateHairColor`, `UpdateBodyTint`, `SetProjectedUVData`, `UpdateMaterialAlpha` и другие, которые часто вызываются на каждое обновление 3D.
- Как проверено: чтение кода.
- Предложение: принимать `const std::function<…>&` — ABI заголовка не меняется, это правка сигнатуры с перекомпиляцией. Лучше добавить шаблонную перегрузку `template <class F> TraverseScenegraphObjects(NiAVObject*, F&&)` без стирания типа (см. M-17).

### M-16. Нет математики, которую VR- и физические плагины пишут сами
- Вид: расширение; Важность: средняя; Уверенность: подтверждено (отсутствие проверено grep)
- Где: `include/RE/N/NiQuaternion.h`, `NiMatrix3.h`, `NiTransform.h`, `NiPoint3.h`, `include/RE/H/hkVector4.h`, `hkQuaternion.h`, `hkRotation.h`
- Код:
  ```cpp
  // NiQuaternion: есть только Dot, Neg, Correct, SetEulerAnglesXYZ, SetRotation, ToRotation
  // hkVector4: есть hkVector4(const NiPoint3&) без масштаба, обратного преобразования нет
  static float GetWorldScale();   // bhkWorld.h:45 — есть, но не связан с конверсиями
  ```
- Суть и сценарий: VR-плагины (руки, контроллеры, физика) дублируют у себя:
  - (1) кватернионы: `operator*`, сопряжение/обратный, нормализация с проверкой нулевой длины, `FromAngleAxis`/`ToAngleAxis`, поворот вектора, `Slerp`/`Nlerp` с учётом знака (у `Correct()` уже есть половина логики);
  - (2) `NiMatrix3`: `Inverse` (M-14), определитель, ортонормализация (накопленная ошибка при интегрировании поворота руки), `LookAt(forward, up)`/`FromVectors`, `ToEulerAnglesZXY` в пару к `EulerAnglesToAxesZXY`;
  - (3) `NiTransform`: `Lerp`/интерполяция (translate lerp + rotate slerp + scale lerp), `InvertedMultiply`;
  - (4) `NiPoint3`: `Lerp`, `ProjectOnto`, `Normalized()` (не меняя `*this`), угол между векторами;
  - (5) Havok↔Ni: `NiPoint3 ToNi(const hkVector4&)`, `hkVector4 ToHavok(const NiPoint3&)` с учётом `bhkWorld::GetWorldScale()` (0.0142875) / `GetWorldScaleInverse()` (69.99125); `NiMatrix3`↔`hkRotation` (у Havok столбцы — это оси, у Ni действует транспонированное соглашение поворота, самому легко ошибиться со знаком); `NiQuaternion`↔`hkQuaternion`;
  - (6) DirectXMath: `XMMATRIX`/`XMFLOAT4X4` из `NiTransform` и `NiCamera::worldToCam`, `XMFLOAT3` из `NiPoint3` для шейдерных плагинов.
- Как проверено: `grep -rln "Slerp\|LookAt\|XMMATRIX\|0.0142875"` по `include`/`src` — совпадений в математических типах нет.
- Предложение: добавлять новые методы с тестами кругооборота (Эйлер↔матрица↔кватернион, Havok↔Ni). Соглашение Ni (транспонированные повороты `MakeXRotation`) описать одной строкой в заголовке `NiMatrix3.h` — M-1 и M-7 показывают, как легко его перепутать.

### M-17. Граф сцены: нет шаблонного visitor, поиска по пути и доступа к полям `NiRect`
- Вид: расширение; Важность: низкая; Уверенность: подтверждено
- Где: `include/RE/B/BSVisit.h`, `include/RE/N/NiAVObject.h:118`, `include/RE/N/NiRect.h:41-46`
- Код:
  ```cpp
  SKYRIM_REL_VR_VIRTUAL NiAVObject* GetObjectByName(const BSFixedString& a_name);   // полный обход каждый раз
  protected:
  	T left; T right; T top; T bottom;   // NiRect: у NiCamera::port читаются только ширина/высота
  ```
- Суть и сценарий: плагины ищут кости руки/оружия (`"NPC R Hand [RHnd]"`, `"WEAPON"`) каждый кадр через `GetObjectByName` — это полный обход поддерева на каждый вызов. Нет (1) шаблонного обхода с ранним выходом без `std::function`, (2) `FindByPath("NPC Root [Root]/NPC Spine [Spn0]/…")` с поиском только среди прямых детей на каждом шаге, (3) обхода «вверх к корню» (есть лишь рекурсивный `GetUserData`). У `NiRect` поля `protected` без геттеров, поэтому собственную проекцию через `NiCamera::port` (левый/верхний край вьюпорта, VR-глаз) не написать без `reinterpret_cast`.
- Как проверено: чтение заголовков.
- Предложение: `template <class F> BSVisitControl Visit(NiAVObject*, F&&)` с удержанием `NiPointer` (см. M-10); `NiNode::FindChildByPath(std::string_view)`; публичные геттеры `NiRect::Left()/Right()/Top()/Bottom()`.

---

## Проверено и в порядке

- `NiMatrix3`: `MakeXRotation/Y/Z` и `MakeRotation(angle, axis)` повторяют соглашение Gamebryo (транспонированный поворот), `MakeRotation(a,(1,0,0)) == MakeXRotation(a)`. `SetEulerAnglesXYZ == X(a)·Y(b)·Z(c)`, `EulerAnglesToAxesZXY == Z·X·Y` (проверено численно). Корректны `operator*` (матрица·матрица и матрица·вектор), `Transpose`, `+`, `-`. Формула `ToEulerAnglesXYZ` совпадает с Gamebryo, дефект только в `NiFastATan2` (M-1).
- `NiQuaternion::ToRotation` и `SetRotation` взаимно обратны на 20000 случайных единичных кватернионах, включая ветку `trace ≤ 0` (выбор наибольшей диагонали и индексы `next` верны).
- `NiTransform::operator*` (порядок масштаб→поворот→сдвиг), `Invert` (`R^T`, `1/s`, `-(1/s)R^T t`), `operator*(NiPoint3)`, `GetHeadingAngle` (одной поправки на ±360° хватает) — верны.
- `NiPoint2/3::Unitize` — защита от нулевой длины (`FLT_EPSILON`), NaN даёт ноль. `GetDistance` использует `GetSquaredDistance`, лишних `sqrt` нет. `NiASin` клампит аргумент, `normalize_angle` даёт [−π, π).
- `GFxValue`: копирующий конструктор и присваивание, перемещающий конструктор, деструктор и `ChangeType` вызывают `ObjectAddRef`/`ObjectRelease` парно (дефект только в move-присваивании, M-3).
- `GString`: копирование, перемещение и присваивание сохраняют счётчик ссылок `DataDesc`, размер выделения (`len + 8 + 4 + 1`) соответствует раскладке `DataDesc`.
- `NiObjectNET::InsertExtraData/DeleteExtraData/RemoveAllExtraData` — IncRef/DecRef парны. Бинарный поиск по адресу имени — соглашение Gamebryo (пул `BSFixedString`), а не ошибка.
- `NiNode::Create` уже выделяет память по размеру рантайма (`malloc_runtime(0x128, 0x150)`), правка ветки `fix/nininode-runtime-sized-create` по содержанию в `ng` есть.
- `NiAVObject::TintScenegraph`: `new BSEffectShaderData` идёт через `TES_HEAP_REDEFINE_NEW` базового `BSIntrusiveRefCounted`, это куча движка.
- `BSLightingShaderMaterialBase::CreateMaterial` через scrap heap — сознательная правка a53747388 (doodlum), не оспаривается.
- `Renderer::Apply{VS,PS}ConstantGroup`: VR-кэш в пределах массивов (12 слотов, `ConstantGroupLevel` ≤ 0xB).
- `GFxWWHelper`, `GFxMovie::SetVariable*`, `GFxMovieView`, `GFxMovieDef::CreateInstance`, `GRenderer::Cxform` — повторяют Scaleform SDK, расхождений не найдено.

Мелкое и неподтверждённое (в находки не вынесено):
- `BSShaderTextureSet::Create` (`src/RE/B/BSShaderTextureSet.cpp:19-21`) вызывает `memset` до проверки на `nullptr`.
- `GFxValue::SetColorTint` (`src/RE/G/GFxValue.cpp:1024-1026`) пишет добавки Cxform в долях (≤ 0.5). Если, как в Scaleform 3.x, добавки задаются в единицах 0..255, «подсветка» почти не видна. Проверить в игре через `GetCxform` у клипа с `colorTransform.redOffset = 255`.
- `GString::operator=(std::string_view)` (`src/RE/G/GString.cpp:134-135`) всегда ставит старший бит размера. В Scaleform этот бит значит «длина в символах = длине в байтах». Для UTF-8 с кириллицей `GString::GetLength()` движка вернёт число байт. Путь, где движок читает длину строки, созданной плагином, не найден.
- `Renderer::Prepare{VS,PS}ConstantGroup` (`src/RE/R/Renderer.cpp:204-206`, `217-219`) не проверяет HRESULT `Map`: при потере устройства в `group.data` попадает неинициализированный указатель. Скорее всего, так же устроен встроенный код движка.
- Как устроен `fmt::formatter<RE::NiPoint3>` (`include/RE/N/NiPoint3.h:78`): `format_error("invalid format")` создаёт временный объект без `throw`, но fmt всё равно отвергает неверный спецификатор сам.
