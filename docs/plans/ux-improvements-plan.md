# План UX-улучшений AI Fitness бота

Дата: 18.10.2026. Статус: исследование и дизайн, код не менялся.

Слои: `presentation` → `service` → `domain`; `infrastructure` реализует порты из `service`.
Пути ниже относительно `src/fitness_bot/`, если не указано иное.

---

## 0. Базовая линия для исполнителей

- Тесты: `uv run pytest -q` (pytest 9 + pytest-asyncio, `asyncio_mode = "auto"`, `testpaths = ["tests"]`).
  Сейчас собирается **241 тест, все зелёные** (прогон ~5 с, без БД — сервисные тесты на `InMemoryUow`).
- Линт/формат: `uv run pre-commit run --all-files --hook-stage pre-push` (ruff, add-trailing-comma,
  `name-tests-test --pytest-test-first` — файлы тестов должны называться `test_*.py`).
- Миграции: `alembic/versions/00NN_<name>.py`, последняя — `0016_places_program_types`.
  **Revision ID ≤ 32 символов** (`alembic_version.version_num varchar(32)`, уже дважды чинили).
- В БД есть CHECK-констрейнты на enum-значения: `users.expected_input`
  (см. `0015_expected_input_wellbeing.py`, список надо держать синхронным с `domain/enums.py::ExpectedInput`),
  `proposals.kind`, `programs.status`. **Новое значение `ExpectedInput`/`ProposalKind` = обязательная миграция**
  (иначе запись падает в проде, как было с wellbeing — коммит 5489ede).
- Тесты, которые завязаны на клавиатуры главного меню/профиля: `tests/presentation/test_profile_ui.py`,
  `tests/presentation/test_info_ux.py`, `tests/presentation/test_feedback_ux.py`.
- UX-диаграмма `docs/ux.drawio` + проверка `docs/check_ux_bindings.py` (ссылается на внешний plan-файл,
  в CI не участвует) — обновлять по желанию.
- После правок кода: `graphify update .`.

---

## 1. Перенести вес / рост / обхваты в «Профиль»

### Текущее состояние
- Главное меню `presentation/keyboards/__init__.py::home_keyboard` содержит отдельный ряд
  `⚖️ Вес` (`wt_menu`) · `📏 Обхваты` (`meas_menu`) · `📷 Результаты` (`pp_menu`), рядом `🥗 Питание`,
  `🙂 Самочувствие` (`feel`), `📜 История` (`hist`).
- `👤 Профиль` (`profile`, `presentation/routers/profile.py::handle_profile`) показывает `templates/profile.j2`
  (там уже есть рост и вес текстом) и `profile_edit_keyboard()` — плоский список из 17 полей анкеты + «Цель».
  Вес из анкеты исключён («WEIGHT is logged separately»), рост редактируется в анкете.
- Экраны веса/обхватов/фото: `presentation/routers/body.py`, `presentation/routers/progress_photo.py`;
  кнопки «назад» в них ведут в `home` (`weight_menu_keyboard`, `measurement_sites_keyboard`,
  `progress_photo_menu_keyboard`, `weight_reminder_menu_keyboard` → «⬅️ К весу»).
- «Как это работает»: `SECTION_INFO_ORIGIN` знает `wt_menu`, `meas_menu`, `pp_menu` → тема `body`.

### Предлагаемый флоу
Главное меню (короче):
```
🏋️ Начать тренировку            ← см. п.2
📋 Мой план сейчас
🥗 Питание   🙂 Самочувствие   📜 История
📚 Библиотека программ
👤 Профиль   🔎 Найти тренера / 🧑‍🏫 Мой тренер
ℹ️ Инфо
💡 Есть идея   ⚠️ Сообщить о проблеме
...
```
Экран «👤 Профиль» становится хабом (текст `profile.j2` + сводка: последний вес с датой, дата последних обхватов):
```
✏️ Анкета и цель          → prof_form   (текущий profile_edit_keyboard)
⚖️ Вес                    → wt_menu
📏 Обхваты                → meas_menu
📷 Фото прогресса         → pp_menu
⏰ Напоминания            → prof_remind (вес / фото / тренировки — после п.3)
🏠 В меню
```
Все «назад/в меню» внутри веса/обхватов/фото → `⬅️ В профиль` (`profile`) + `🏠 В меню`.
Рост остаётся в анкете; опционально — кнопка «📐 Рост» прямо в хабе (одно нажатие).

### Реализация
- presentation only, без миграций:
  - `keyboards/__init__.py`: `home_keyboard` (убрать ряд), новая `profile_hub_keyboard()`,
    `profile_edit_keyboard` → оставить как экран «Анкета» с «⬅️ В профиль»; back-кнопки в
    `weight_menu_keyboard`, `measurement_sites_keyboard`, `progress_photo_menu_keyboard`, `history_*`.
  - `routers/profile.py::handle_profile` → хаб; новый `prof_form`. После сохранения поля анкеты
    (`finish_profile_edit_if_active` в `flow_helpers.py`) — возвращать в «Анкету», а не в меню.
  - `routers/text.py`: после «Вес сохранён.» / «Обхват сохранён.» отдавать клавиатуру с «⬅️ В профиль».
  - `SECTION_INFO_ORIGIN`: добавить `profile` → `body` (или новую тему `profile`), текст `info.j2` поправить
    («Вес и обхваты теперь в Профиле»).
- Старые callback’и `wt_menu`/`meas_menu`/`pp_menu` сохранить — старые сообщения с кнопками в чатах
  продолжат работать.
- Тесты: обновить `test_profile_ui.py`, `test_info_ux.py`; добавить тест на состав хаба.

Риски: пользователи привыкли к кнопке «Вес» в меню (низкий). Размер: **S**.

---

## 2. Тренировка одной кнопкой

### Текущее состояние
- `🏋️ Тренировка сегодня` (`sess`) → `routers/session.py::handle_sess` → `GetTodayWorkoutQueryHandler`
  (`service/handlers/queries/session.py`) решает экран: `session` (идёт тренировка), `template`
  (превью дня), `rest`, `no_program`.
- На экране `template` (`session_template_keyboard`) надо нажать ещё `▶️ Начать как в плане` (`sess_plan`) →
  `StartSessionFromTemplateCommandHandler` (`service/handlers/commands/session.py`). Если сегодня уже
  была завершённая тренировка — третий шаг `session_repeat_confirm`.
- Там же: `✏️ Изменить тренировку`, `🙂 Обновить план с учётом самочувствия`, `🆕 Начать новую неделю`.
- В день отдыха (`rest`) начать тренировку нельзя вообще: шаблон ищется строго по `weekday`
  (`program.days[].weekday == today.isoweekday()`), иначе `DomainError("today is not a training day ...")`.

### Предлагаемый флоу
Кнопка в меню: `▶️ Начать тренировку` (новый callback `sess_go`, `sess` оставить для совместимости):
- есть открытая сессия → сразу карточка тренировки (как сейчас `screen=session`), текст «Продолжаем 💪»;
- сегодня тренировочный день → **сразу** `StartSessionFromTemplate` → карточка тренировки
  (`session_card.j2` + `session_card_keyboard`). Превью дня больше не показываем;
- сегодня уже сделано → «✅ Сегодня тренировка уже сделана» + `🔄 Повторить` / `📋 План недели` / `🏠 В меню`;
- день отдыха → «Сегодня по плану отдых» + `💪 Всё равно потренироваться: «<ближайший день>»`
  (стартует ближайший невыполненный день недели; см. открытый вопрос) + `🏠 В меню`;
- нет программы → как сейчас (`session_no_program`).
- Если есть свежая неучтённая отметка самочувствия — тренировка всё равно стартует сразу, но на карточке
  баннер «Ты отметил: “<текст>”. Подстроить тренировку?» + кнопка `🙂 Подстроить под самочувствие`
  (зависит от п.5: адаптация открытой сессии).
- Карточка сессии получает `✏️ Изменить` (уже есть) — «Изменить тренировку» переезжает сюда с превью.
- Превью дня по-прежнему доступно через `📋 Мой план сейчас → день`.

### Реализация
- service: новый `StartTodayWorkoutCommand` (или расширить `StartSessionFromTemplateCommand` полем
  `resume_open: bool`, `weekday_override: int | None`), возвращающий `outcome: started|resumed|already_done|rest|no_program`.
  Логику выбора экрана перенести из presentation в service (один запрос вместо query+command).
- domain: функция «ближайший невыполненный день недели» в `domain/workout/week_progress.py`
  (там уже `training_week_progress`) — для кнопки в день отдыха.
- presentation: `home_keyboard` (лейбл/callback), `routers/session.py` новый `sess_go`, `session_rest_keyboard`.
- Без миграций.
- Тесты: сервисный тест на все outcome; презентационный — на клавиатуру.

Риски: потеря шага «посмотреть перед стартом» (смягчается тем, что карточка показывает весь день и есть
«🔄 Начать заново»/`✏️ Изменить`); старт «не по дню» влияет на `training_week_progress` (проверить подсчёт
выполненных дней). Размер: **S** (без rest-day) / **M** (с тренировкой в день отдыха).

---

## 3. Напоминание «тренируешься сегодня / завтра?»

### Текущее состояние
- Есть in-process планировщик `presentation/scheduler.py::run_weight_reminder_scheduler`
  (старт из `presentation/main.py` через `asyncio.create_task`), тикает раз в 60 с:
  `ListDueWeightRemindersQuery` / `ListDueProgressPhotoRemindersQuery`
  (`service/handlers/queries/body.py`).
- Модели напоминаний: `domain/body/reminder.py` (`WeightReminder`, `ProgressPhotoReminder`:
  `local_time`, `weekdays`, `last_sent_on`), таблицы `weight_reminders`, `progress_photo_reminders`.
- Ограничения текущей схемы:
  - due = **точное совпадение минуты** (`local_dt.hour/minute == reminder.local_time`) — пропущенный тик
    (рестарт/долгий тик) = напоминание потеряно;
  - напоминание пропускается, если `user.expected_input != NONE` (пользователь «завис» в любом вводе —
    напоминаний нет никогда);
  - весовое напоминание выставляет `expected_input=WEIGHT` и перетирает текущий флоу.
- Часовой пояс: `user.timezone_offset` (строка), дни тренировок: `program.days[].weekday`
  и `user.training_weekdays`.
- Про тренировки напоминаний нет совсем.

### Предлагаемый флоу
Два касания (оба отключаемы):

**Вечер накануне тренировочного дня** (по умолчанию 20:00 местного):
```
Завтра по плану: «Ноги и ягодицы» · 6 упражнений · ~60 мин.
Тренируешься завтра?
[💪 Да, буду]  [😴 Завтра пропущу]
[🙂 Отметить самочувствие]
```
**Утро тренировочного дня** (по умолчанию 09:00), если вчера не было «пропущу»:
```
Сегодня тренировка «Ноги и ягодицы». Как настрой?
[▶️ Начать тренировку]        → sess_go (п.2)
[🙂 Как самочувствие?]        → feel (п.5) → после записи «Подстроить тренировку?»
[⏰ Напомнить позже]           → +2 ч (один раз)
[😴 Сегодня не буду]
```
- «Да, буду» → короткий ответ «Отлично, утром напомню 👍»; утреннее сообщение короче.
- «Пропущу» → «Ок, отдыхаем. Перенести на другой день?» [📅 Послезавтра] [Нет] (перенос — см. открытые вопросы).
- Сообщения с кнопками **не** выставляют `expected_input` (не ломают текущий флоу пользователя).
- Настройки: `👤 Профиль → ⏰ Напоминания → 🏋️ Тренировки`: вкл/выкл, время вечернего и утреннего
  (переиспользовать паттерн `weight_reminder_time_keyboard`).

### Реализация
- domain: `domain/workout/training_reminder.py` — `TrainingReminder(user_id, enabled, evening_time,
  morning_time, last_evening_sent_on, last_morning_sent_on)`; `TrainingDayIntent(user_id, local_date,
  answer: yes|skip|later, answered_at)`; enum `TrainingIntentAnswer`.
- service: порты `ITrainingReminderRepository`, `ITrainingIntentRepository` в `service/interfaces/uow.py`
  (+ `IUow` свойства); запросы `ListDueTrainingRemindersQuery` (фильтр: есть активная программа,
  завтра/сегодня — день программы, тренировка сегодня ещё не начата/не завершена, нет `skip` на дату),
  команды `MarkTrainingReminderSentCommand`, `AnswerTrainingIntentCommand`, `SetTrainingReminderCommand`,
  `EnsureDefaultTrainingReminderCommand`.
- infrastructure: SQLAlchemy-модели и репозитории, in-memory реализации в `infrastructure/uow/in_memory.py`.
- Миграция `0018_training_reminders` (две таблицы; уникальный индекс `(user_id, local_date)` для intent).
- presentation: `scheduler.py` — `handle_training_tick` в тот же цикл; новый роутер
  `routers/training_reminder.py` (callbacks `tr_yes:<date>`, `tr_skip:<date>`, `tr_later:<date>`,
  `tr_set*`), регистрация в `main.py`/`wiring/container.py`, шаблоны `training_reminder_*.j2`.
- Попутно починить общий due-алгоритм: «наступило время и сегодня ещё не отправляли» вместо точной минуты
  (окно, например, 30 мин), и не блокировать по `expected_input` для сообщений-кнопок.
- Обработать `TelegramForbiddenError` (пользователь заблокировал бота) — выключать напоминание.

Риски: спам (нужен понятный выключатель и разумный дефолт), часовые пояса (у части пользователей
`timezone_offset=None` → UTC), повторная отправка при нескольких репликах бота (in-process планировщик —
сейчас одна реплика; при масштабировании нужен лок/`SELECT ... FOR UPDATE SKIP LOCKED`).
Размер: **L** (M без переноса дня).

---

## 4. «Показать похожее упражнение» (замена)

### Текущее состояние
- Каталог: `data/exercises.jsonl` — **749 упражнений**, поля: `name`, `primary_muscles` (18 значений:
  квадрицепс, ягодицы, грудь, плечи, пресс, широчайшие, трицепс, икры…), `secondary_muscles` (21),
  `places` (`gym` 749, `home` 459, `outdoor` 223), `technique`, `videos`. **Поля «оборудование» и
  «паттерн движения» нет.**
- Порт `service/ports/video_search.py::ExerciseCatalogReader` (`list_exercises`, `get_guide`),
  запись `CatalogExerciseRecord(id, name, primary_muscles, secondary_muscles, places)`.
- Есть ранжирование `domain/catalog/match.py::match_exercises` — по токенам названия и мышцам
  (используется для нераспознанных слотов: `match_session_exercises_keyboard`, `sess_pick:`).
- Экран упражнения в тренировке: `slot:<pos>` → `_show_slot_screen` → `slot_actions_keyboard`
  (`✅ Как в плане → дальше`, `✏️ Вес и повторы`, `📖 Как делать`, `🎥 видео`, назад). Замены нет —
  только «✏️ Изменить» текстом через LLM (`ProposeWorkoutChangeCommandHandler`).
- Домен сессии `domain/workout/session.py`: есть `_replace_slot`, `ExerciseSlot.with_exercise(exercise_id)`
  — заменить упражнение в слоте технически просто.

### Предлагаемый флоу
На экране упражнения в тренировке новая кнопка `🔄 Похожее упражнение` (`slot_alt:<pos>`), если у слота нет факта:
```
Вместо «Жим штанги лёжа» (грудь · трицепс, плечи) можно:
[💪 Жим гантелей лёжа]
[💪 Отжимания на брусьях с наклоном]
[💪 Жим в тренажёре сидя]
[🔁 Ещё варианты]   [⬅️ Назад]
```
Нажатие варианта (`slot_swap:<pos>:<exercise_id>`, ≤ 64 байт) → сразу замена в текущей сессии без
подтверждения → экран упражнения с новой карточкой, подходы/повторы/отдых сохраняются, вес:
сбрасывается в «без веса»/«подбери рабочий» (см. открытый вопрос). Внизу `↩️ Вернуть «Жим штанги лёжа»`.
Опционально (вторая итерация): та же кнопка на экране упражнения в плане (`prog_view_slot`) с выбором
«Заменить только сегодня / во всей программе»; и «🤖 Подобрать с объяснением» через LLM.

### Реализация
- domain: `domain/catalog/similar.py::similar_exercises(target, pool, *, place, exclude_ids, limit)` —
  чистая функция: фильтр по месту (`exercise_matches_training_place`), скоринг
  `3·|primary∩primary| + |secondary∩secondary| + 1·|primary_target∩secondary_cand|`, бонус за общие
  токены названия по оборудованию (штанга/гантели/тренажёр/резина — эвристика из `catalog/normalize.tokenize`),
  исключить упражнения, уже стоящие в этой тренировке. `Session.swap_slot_exercise(position, exercise_id)`
  (только `IN_PROGRESS` и `slot.actual is None`).
- service: `GetSimilarExercisesQuery(telegram_user_id, slot_position, offset)` и
  `SwapSessionSlotExerciseCommand(telegram_user_id, slot_position, exercise_id)`; хранить исходный
  `exercise_id` для «Вернуть» — достаточно передать его в callback возврата (`slot_swap:<pos>:<old_id>`).
- presentation: `slot_actions_keyboard(+has_alternatives)`, новая `similar_exercises_keyboard`, хендлеры
  в `routers/session.py`.
- Миграций нет. (Улучшение качества: добавить в каталог поле `equipment` через `enrich-catalog` — отдельная задача.)
- Тесты: domain-тест на скоринг (на фикстурах из `service/ports/exercise_catalog.py::record`),
  сервисный тест замены и запрета замены после факта.

Риски: качество «похожести» без поля оборудования (штанга↔тренажёр — ок, но может предложить домашнее
упражнение в зале → фильтр по месту обязателен); замена ломает прогрессию веса в истории
(история хранит документ сессии — ок). Размер: **M**.

---

## 5. БАГ: самочувствие не учитывается, нет истории, нет кнопки адаптации

### Текущее состояние
- Запись: `🙂 Самочувствие` (`feel`) → `routers/body.py::handle_feel` → `ExpectedInput.WELLBEING` →
  текст/голос в `routers/text.py::handle_user_utterance` → `RecordWellbeingCommandHandler`
  (`service/handlers/commands/body.py`) → `WellbeingEntry(user_id, text, created_at, applied_at)`
  (`domain/body/wellbeing.py`, таблица `wellbeing_entries`). Ответ: «Самочувствие записано.» + главное меню.
- Использование: только кнопка `🙂 Обновить план с учётом самочувствия` (`sess_feel_adapt`) →
  `GenerateNextSessionCommand(adapt_for_wellbeing=True)` → промпт `service/prompts/next_session_planner.md`
  (`wellbeing_json`) → черновик `NEXT_SESSION` → `✅ Подтвердить` (`sess_gen_ok`) →
  `ApproveProposalCommandHandler` помечает записи `applied_at`.

### Корневые причины
1. **Кнопка адаптации почти никогда не видна.** Она рисуется только в `session_template_keyboard`
   (экран превью дня), т.е. только если: сегодня тренировочный день по программе **и** нет открытой
   сессии **и** есть неучтённая запись. В день отдыха, во время тренировки, сразу после записи
   самочувствия (ответ — просто главное меню) и в плане недели её нет.
2. **Все остальные пути генерации игнорируют самочувствие:** `StartSessionFromTemplate`
   («Начать как в плане» — копия шаблона без LLM), `sess_gen` («Перегенерировать по истории» шлёт
   `adapt_for_wellbeing=False` → `wellbeing_json=""`), `ProposeWorkoutChangeCommandHandler` (правка текстом),
   `GenerateNextWeekCommandHandler` (`next_week_planner.md` вообще не получает самочувствие),
   `ProposeProgram*`, `ApplyCatalogProgram`. Т.е. при обычном использовании самочувствие не влияет ни на что.
3. **Связь «черновик → записи самочувствия» хранится в памяти процесса**
   (`service/handlers/commands/wellbeing_adapt.py::_PENDING_WELLBEING_BY_PROPOSAL`). После рестарта/деплоя
   (или при >1 реплике) подтверждение не помечает записи как учтённые → кнопка висит вечно, старые жалобы
   повторно подаются как «жёсткие ограничения на СЕГОДНЯ». При отмене черновика словарь не чистится.
4. **Нет свежести:** «неучтённой» считается любая запись без `applied_at`, даже месячной давности.
5. **Нет чтения:** `IWellbeingRepository.list_recent` реализован, но нет ни query, ни экрана; в
   `📜 История` (`history_menu_keyboard`) раздела «Самочувствие» нет.
6. Текст приглашения (`templates/onboarding_prompt.j2`, `field == "wellbeing"`) обещает «Это учтём при плане
   на сегодня» — обещание не выполняется.
7. Тест `tests/service/test_generate_handlers.py::test_wellbeing_record_flag_and_adapt_marks_applied`
   покрывает только «счастливый путь» в одном процессе, поэтому баг не ловится.

### Предлагаемый флоу
**Запись** (`🙂 Самочувствие`):
```
🙂 Как самочувствие?
[😀 Отлично] [🙂 Нормально] [😕 Так себе] [🤕 Плохо / болит]
Можно добавить подробности текстом или голосом: что болит, сон, усталость.
[📖 История самочувствия]  [🏠 В меню]
```
(быстрая оценка опциональна — см. открытые вопросы; текст/голос остаются).
**После записи:**
```
Записал: «болит левое колено, спал 5 часов».
Подстроить под это?
[🏋️ Сегодняшнюю тренировку]   → sess_feel_adapt_today
[📅 План на неделю]            → sess_feel_adapt_week
[Не надо]
```
- «Сегодняшнюю»: если сессия открыта — черновик `WORKOUT_EDIT` к открытой сессии; если ещё не начата и
  сегодня тренировочный день — `NEXT_SESSION` (как сейчас); если отдых — «Сегодня отдых, учтём в
  следующей тренировке» + предложить «План на неделю».
- «План на неделю»: `GenerateNextWeek`/правка активной программы с `wellbeing_json` → черновик программы
  → подтверждение (существующий экран `render_proposal`).
- Отдельная постоянная кнопка `🙂 Подстроить под самочувствие` — на карточке тренировки (п.2) и на экране
  программы, пока есть свежие неучтённые записи.
- **Автоучёт:** свежие записи (≤ 48 ч, см. вопрос) автоматически подаются как контекст во все LLM-генерации
  (перегенерация дня, правка текстом, неделя, адаптация из библиотеки) — «мягкий» контекст; явная кнопка
  делает «жёсткую» адаптацию и помечает записи учтёнными.
- **История:** `📜 История → 🙂 Самочувствие` и `🙂 Самочувствие → 📖 История`: список за 30 дней
  (дата, оценка, текст, «✅ учтено в тренировке 12.10» / «⏳ не учтено»), пагинация как в `session_history_keyboard`.
  Тренер видит то же в карточке клиента (опционально, переиспользовать `require_coach_of`).

### Реализация
- domain: `WellbeingEntry` + `score: int | None` (1–4), `applied_proposal_id: UUID | None`;
  методы `is_fresh(now, max_age)`; функция `fresh_unapplied(entries, now)`.
- infrastructure: миграция `0017_wellbeing_tracking` — `wellbeing_entries.score smallint null`,
  `wellbeing_entries.proposal_id uuid null references proposals(id) on delete set null`, индекс
  `(user_id, created_at desc)`. Репозиторий: `link_to_proposal(entry_ids, proposal_id)`,
  `mark_applied_for_proposal(proposal_id)`, `list_page(user_id, offset, limit)`; in-memory аналоги.
- service:
  - удалить `wellbeing_adapt.py`; в `GenerateNextSessionCommandHandler` вместо `remember_wellbeing_adapt`
    — `repos.wellbeing.link_to_proposal(...)` в той же транзакции; в `ApproveProposalCommandHandler`
    (`service/handlers/commands/program.py`) — `mark_applied_for_proposal(pending.id)` для всех kind;
  - общий хелпер `wellbeing_context(repos, user, now) -> (json, ids)` и прокидка в
    `next_session_planner.md`, `next_week_planner.md`, `workout_editor.md`, `program_*` промпты
    (добавить блок `{% if wellbeing_json %}` в каждый);
  - `AdaptForWellbeingCommand(scope: today|week)` — роутинг на нужный генератор с учётом открытой сессии
    (для открытой — `ProposeWorkoutChange` с утверждением-«утилитой» из записей);
  - `GetWellbeingHistoryQuery(offset, limit, subject_user_id=None)`;
  - `GetTodayWorkoutQuery.has_unapplied_wellbeing` → считать только свежие.
- presentation: `routers/body.py` (`feel`, оценка `feel_score:<n>`, `feel_hist[:offset]`), `routers/text.py`
  (после записи — клавиатура «Подстроить?»), `routers/session.py` (`sess_feel_adapt_today/_week`; старый
  `sess_feel_adapt` оставить алиасом), `history_menu_keyboard` (+ «🙂 Самочувствие»), шаблоны
  `wellbeing_saved.j2`, `wellbeing_history.j2`, поправить `onboarding_prompt.j2`.
- Тесты: сценарий «записал → рестарт (новый handler/без глобального словаря) → подтвердил → applied»;
  свежесть; история с пагинацией; прокидка `wellbeing_json` в каждый промпт (фейковая LanguageModel
  ловит prompt_context — паттерн уже есть в `test_generate_handlers.py`).

Риски: LLM может перестраховываться (вычищать всю тренировку при «немного устал») — промпт должен
различать «мягкий контекст» и «жёсткие ограничения»; медицинские формулировки («болит» → совет к врачу,
дисклеймер). Размер: **L** (M без оценки и тренерского просмотра).

---

## 6. БАГ: библиотека тренировок — нет деталей, редактирования и названий

### Текущее состояние
- `📚 Библиотека программ` → `presentation/routers/library.py::library_home` → `ListProgramCatalogQuery`
  (`service/handlers/queries/coach.py::ListProgramCatalogQueryHandler`) → кнопки `lib_card:<id>` с
  `display_title()` + статус + автор.
- Карточка `lib_card:` → `GetCatalogProgramQueryHandler` возвращает `document` (полный план!), но
  роутер выводит только `title`, статус и код; дни/упражнения не рендерятся. Кнопки: `Применить сейчас`
  (адаптация LLM), `Как у автора`, `Опубликовать`, `Снять с публикации`, `Назад`.
- Сохранение в библиотеку: `routers/program.py::handle_prog_lib_save` / `handle_prog_lib_save_active` →
  `SaveProgramDraftCommand(title=program_type_label(...))` → `Program.draft_from_document`
  (`domain/workout/program.py`).
- Редактирования/переименования/удаления карточек нет ни в домене, ни в сервисе, ни в UI.

### Корневые причины
1. **Названия:** при сохранении всегда подставляется `program_type_label(program_type)` («Фулбоди»,
   «Верх/низ»…), пользователя не спрашивают; команд переименования нет. Две программы одного типа —
   две одинаковые кнопки в списке, отличить нельзя. Копии по коду наследуют то же название.
2. **Детали:** данные есть (`GetCatalogProgramQueryResult.document`), но `library.py::card` их не
   показывает — чисто презентационный пробел. Нет навигации по дням/упражнениям (в отличие от
   `prog_view_day`/`prog_view_slot` для активной программы).
3. **Редактирование:** весь pipeline правок (`ProposeProgramChangeCommandHandler` → черновик → `prog_ok`)
   завязан на *активную* программу: подтверждение черновика PROGRAM всегда активирует новую программу.
   Цели «сохранить правку в карточку библиотеки» не существует.

### Предлагаемый флоу
**Сохранение:**
```
📚 Как назвать программу?
Напиши название или выбери:
[✅ «Фулбоди · 3 дня · окт 2026»]
[⬅️ Отмена]
```
(автоназвание: тип + дней в неделю + месяц; оставляем, если пользователь не ответил).
**Список:** `📗 Моя сила зима · черновик` / `📘 Фулбоди для Маши · опубликовано · код ABC12345`.
**Карточка:**
```
📗 Моя сила зима
Тип: Фулбоди · 3 дня/нед · ~60 мин · статус: черновик
Пн — Грудь и спина: жим лёжа 4×8, тяга штанги 4×8, …
Ср — Ноги: …
Пт — …
[📅 Пн · Грудь и спина] [📅 Ср · Ноги] [📅 Пт · …]   → lib_day:<id>:<pos> → упражнения → «📖 Как делать»
[▶️ Сделать активной]  [✨ Применить с адаптацией]
[✏️ Изменить текстом или голосом]   → lib_edit:<id>
[🏷 Переименовать]                  → lib_rename:<id>
[📤 Опубликовать / Отправить код] [Снять с публикации]
[🗑 Удалить]  (подтверждение)
[⬅️ К библиотеке]
```
**Редактирование:** `✏️ Изменить` → «Что поменять в «Моя сила зима»?» → LLM (`workout_editor.md`) →
черновик с превью (существующий `render_proposal`, но кнопка `💾 Сохранить в карточку` вместо
«Сделать активной») → карточка обновлена. Активную программу это не трогает.

### Реализация
- domain (`domain/workout/program.py`): `rename(title)` (1–60 символов, trim), `replace_document(document)`
  (только `DRAFT`/`PUBLISHED`, `assert_approvable`), автоназвание `default_library_title(document, now)`.
  Опционально `soft delete` (статус `ARCHIVED` для карточек или флаг) — проверить CHECK `programs.status`.
- service (`service/handlers/commands/catalog.py`): `RenameLibraryProgramCommand`,
  `ProposeLibraryProgramEditCommand(program_id, utterance)` (черновик `ProposalKind.PROGRAM` с
  `base_program_id = card.id`), `DeleteLibraryProgramCommand`. В `ApproveProposalCommandHandler`
  ветка: если `base_program_id` указывает на карточку в статусе draft/published владельца → `card.replace_document`
  и **не** активировать. Это обходится без новой `ProposalKind` → без миграции CHECK.
  `GetCatalogProgramQueryResult` уже содержит `document` — добавить `days_per_week`, удобные поля.
- Ввод названия: новое `ExpectedInput.LIBRARY_TITLE` (+ миграция CHECK) **или** существующий паттерн
  `PROFILE_FIELD` + `expected_field="library_title:<uuid>"` (так уже сделано для `weight_reminder_time`) —
  второй вариант без миграции, рекомендуем его для параллельности. Обработка в `routers/text.py`.
- presentation: переписать `library.py` (карточка через шаблон `library_card.j2`, переиспользовать рендер
  недели из `routers/program.py`/`session.py::_render_document_template`), `lib_day`, `lib_slot`,
  `lib_rename`, `lib_edit`, `lib_del`; клавиатуры вынести в `keyboards/__init__.py` (сейчас `_kb` внутри роутера).
  `prog_lib_save*` → спросить название.
- Миграция: не требуется (если выбран вариант без нового enum и без soft-delete-статуса).
- Тесты: rename/replace_document в домене; сервис: правка карточки не меняет `user.active_program_id`;
  чужую карточку нельзя менять; публикация после правки.

Риски: правка **опубликованной** программы меняет то, что получат новые люди по коду (у уже забравших —
копии, их не трогает); approve-ветка в `ApproveProposalCommandHandler` пересекается с фазой самочувствия;
длинный текст карточки (лимит Telegram 4096) — сокращать или разбивать. Размер: **M**.

---

## 7. Приоритеты и фазы

Логика приоритизации:
- Сначала **баги** (5, 6): обещанная функциональность не работает, теряется доверие.
- Затем **дешёвые улучшения навигации** (1, 2) — малый объём, большой эффект на каждую сессию.
- Затем **новые возможности** (4, 3). Напоминание (3) строится поверх «одной кнопки» (2) и
  исправленного самочувствия (5): из напоминания ведём в `sess_go` и в «Подстроить под самочувствие».

| Фаза | Пункты | Размер | Зависимости | Миграция | Параллельно с |
|---|---|---|---|---|---|
| A. Самочувствие работает | 5 | L | — | 0017 | B, C |
| B. Библиотека: названия, детали, правка | 6 | M | — | нет | A, C |
| C. Профиль-хаб | 1 | S | — | нет | A, B |
| D. Тренировка одной кнопкой | 2 | S–M | A желательно (баннер адаптации); C (меню) | нет | E |
| E. Похожее упражнение | 4 | M | — (лучше после D: карточка сессии стабилизирована) | нет | D |
| F. Напоминания о тренировке | 3 | L | D, A (кнопки ведут в них), C (настройки в профиле) | 0018 | — |

Волны:
1. **Волна 1 (параллельно): A, B, C.**
   Пересечения: `keyboards/__init__.py` (разные функции — мердж обычно чистый),
   `routers/text.py` (A — ветка WELLBEING; B — ввод названия; C — ответы после веса/обхвата),
   `service/handlers/commands/program.py::ApproveProposalCommandHandler` (A — пометка applied; B — ветка
   «сохранить в карточку»). Рекомендуется мерджить A первым, B ребейзит. Миграцию берёт только A (0017).
2. **Волна 2 (параллельно): D, E.** Обе трогают `routers/session.py` и `keyboards/__init__.py`, но разные
   хендлеры (D — `sess`/`sess_go`/rest; E — `slot:`/`slot_alt`/`slot_swap`) и разные доменные файлы
   (D — `week_progress.py`; E — `catalog/similar.py`, `session.py`). Мердж D первым.
3. **Волна 3: F.** Миграция 0018 (`down_revision = 0017_wellbeing_tracking`).

Если параллельных агентов нет — порядок: A → B → C → D → E → F (C можно делать в любой момент, это самая
дешёвая видимая победа; при желании показать результат быстро — C и D первыми, они не зависят от A
функционально, только баннер в D).

Правила для исполнителей каждой фазы:
- Номер миграции фиксирован этим планом (A=0017, F=0018); revision id ≤ 32 символов.
- Новые значения enum, попадающие в БД, — только с миграцией CHECK.
- Старые callback_data оставлять рабочими (сообщения с кнопками живут в чатах).
- callback_data ≤ 64 байт (UUID = 36).
- `uv run pytest -q` зелёный, `uv run pre-commit run --all-files --hook-stage pre-push`, `graphify update .`.
- Коммиты — conventional commits.

---

## 8. Открытые продуктовые вопросы

Напоминания (п.3):
1. Одно касание или два: только вечер накануне («завтра тренируешься?»), только утро («сегодня?») или оба?
2. Время по умолчанию (предложение: вечер 20:00, утро 09:00) и включать ли по умолчанию всем с активной
   программой, или предлагать включить (opt-in) после первой тренировки?
3. Что делает ответ «Да, завтра»: только подтверждение (и короткое утреннее напоминание) или ещё что-то
   (например, заранее сгенерировать адаптированную тренировку)?
4. Ответ «Пропущу»: просто пропуск или предлагать перенос на другой день? Если перенос — тренировка
   «съезжает» (меняется план недели) или просто разрешаем сделать этот день в другой день недели?
5. Напоминать, если пользователь не ответил на вечернее? Повторы «напомнить позже» — сколько раз?

Одна кнопка (п.2):
6. День отдыха: разрешать «всё равно потренироваться»? Какой день брать — ближайший невыполненный на этой
   неделе, или дать выбрать день?
7. Убираем ли совсем экран превью перед стартом (рекомендуем да, превью остаётся в «Мой план»)?

Самочувствие (п.5):
8. Нужна ли быстрая шкала (😀/🙂/😕/🤕) помимо текста? (Рекомендуем: да, это даёт историю-график.)
9. Срок «свежести» отметки для автоучёта: 24 ч, 48 ч, до следующей тренировки?
10. Автоматически учитывать свежие отметки в любой генерации (мягко) — или только по явной кнопке?
11. Показывать историю самочувствия тренеру клиента?

Похожее упражнение (п.4):
12. Замена только в сегодняшней тренировке, или также «заменить во всей программе»?
13. Вес после замены: сбрасывать («подбери рабочий вес»), оставлять как был, или пусть LLM пересчитает?
14. Запоминать «не нравится это упражнение» и не предлагать его в будущих генерациях?

Библиотека (п.6):
15. Можно ли редактировать опубликованную программу (изменения увидят новые получатели) или сначала снять
    с публикации?
16. Нужно ли удаление карточек из библиотеки?
17. Спрашивать название при каждом сохранении или сохранять с автоназванием и давать «Переименовать»?

Профиль (п.1):
18. «📷 Фото прогресса» тоже переносим в Профиль (предлагаем да) и остаётся ли «🙂 Самочувствие» в главном
    меню (предлагаем оставить — это ежедневное действие)?
