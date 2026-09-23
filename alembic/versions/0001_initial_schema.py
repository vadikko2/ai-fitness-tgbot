"""Initial schema from plan DDL.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DDL = r"""
create table users (
    id uuid primary key default gen_random_uuid(),
    telegram_user_id bigint not null,
    chat_id bigint not null,
    sex text check (sex in ('male', 'female')),
    birth_year integer check (birth_year > 0),
    height_cm numeric(5, 1) check (height_cm > 0),
    experience text,
    days_per_week smallint check (days_per_week between 1 and 7),
    equipment text,
    limitations text,
    timezone_offset text check (
        timezone_offset is null
        or timezone_offset ~ '^[+-](?:0[0-9]|1[0-4]):[0-5][0-9]$'
    ),
    goal text check (goal in ('fat_loss', 'muscle_gain', 'strength', 'maintenance')),
    nutrition_stale boolean not null default false,
    expected_input text not null default 'none' check (
        expected_input in (
            'none', 'profile_field', 'weight', 'measurement_value',
            'proposal_utterance', 'completion_deviation', 'technique_video'
        )
    ),
    expected_field text,
    focus_slot smallint check (focus_slot > 0),
    active_program_id uuid,
    active_session_id uuid,
    pending_proposal_id uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index uq_users_telegram_user_id on users (telegram_user_id);

create table user_training_weekdays (
    user_id uuid not null references users (id) on delete cascade,
    weekday smallint not null check (weekday between 1 and 7),
    primary key (user_id, weekday)
);

create table weight_entries (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users (id) on delete cascade,
    kilograms numeric(5, 2) not null check (kilograms > 0),
    measured_at timestamptz not null,
    source text not null check (source in ('onboarding', 'manual', 'reminder'))
);

create index ix_weight_entries_user_measured
    on weight_entries (user_id, measured_at desc);

create table weight_reminders (
    user_id uuid primary key references users (id) on delete cascade,
    local_time time not null,
    last_sent_on date
);

create table weight_reminder_weekdays (
    user_id uuid not null references weight_reminders (user_id) on delete cascade,
    weekday smallint not null check (weekday between 1 and 7),
    primary key (user_id, weekday)
);

create table measurement_sites (
    id uuid primary key default gen_random_uuid(),
    code text not null,
    name text not null,
    is_custom boolean not null,
    user_id uuid references users (id) on delete cascade,
    constraint measurement_sites_owner check (
        (is_custom = false and user_id is null)
        or (is_custom = true and user_id is not null)
    )
);

create unique index uq_measurement_sites_fixed_code
    on measurement_sites (code)
    where is_custom = false;

create unique index uq_measurement_sites_custom_name
    on measurement_sites (user_id, lower(name))
    where is_custom = true;

create index ix_measurement_sites_user
    on measurement_sites (user_id)
    where user_id is not null;

create table measurement_guides (
    site_id uuid primary key references measurement_sites (id) on delete cascade,
    instruction text not null
);

create table measurement_entries (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users (id) on delete cascade,
    site_id uuid not null references measurement_sites (id),
    centimeters numeric(5, 1) not null check (centimeters > 0),
    measured_at timestamptz not null
);

create index ix_measurement_entries_user_site_time
    on measurement_entries (user_id, site_id, measured_at desc);

create table exercises (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    name_normalized text not null,
    technique text not null
);

create unique index uq_exercises_name_normalized on exercises (name_normalized);

create table exercise_muscles (
    exercise_id uuid not null references exercises (id) on delete cascade,
    muscle text not null,
    role text not null check (role in ('primary', 'secondary')),
    primary key (exercise_id, muscle, role)
);

create index ix_exercise_muscles_muscle on exercise_muscles (muscle);

create table exercise_videos (
    id uuid primary key default gen_random_uuid(),
    exercise_id uuid not null references exercises (id) on delete cascade,
    platform text not null check (platform in ('youtube', 'rutube')),
    url text not null,
    title text not null,
    position smallint not null check (position > 0),
    unique (exercise_id, platform, url)
);

create index ix_exercise_videos_exercise
    on exercise_videos (exercise_id, position);

create table programs (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users (id) on delete cascade,
    program_type text not null check (program_type in ('split', 'full_body', 'push_pull')),
    status text not null check (status in ('active', 'archived')),
    created_at timestamptz not null default now(),
    activated_at timestamptz,
    archived_at timestamptz
);

create index ix_programs_user_status on programs (user_id, status);

create unique index uq_programs_one_active
    on programs (user_id)
    where status = 'active';

create table sessions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users (id) on delete cascade,
    source_day_id uuid,
    status text not null check (status in ('in_progress', 'pending_completion', 'completed')),
    started_at timestamptz not null default now(),
    completed_at timestamptz
);

create index ix_sessions_user_completed
    on sessions (user_id, completed_at desc)
    where status = 'completed';

create unique index uq_sessions_one_open
    on sessions (user_id)
    where status in ('in_progress', 'pending_completion');

create table proposals (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users (id) on delete cascade,
    kind text not null check (
        kind in (
            'program', 'workout_edit', 'performance',
            'next_session', 'completion_deviation'
        )
    ),
    status text not null check (status in ('pending', 'approved', 'discarded')),
    program_type text check (program_type in ('split', 'full_body', 'push_pull')),
    base_program_id uuid references programs (id),
    base_session_id uuid references sessions (id),
    created_at timestamptz not null default now(),
    constraint proposals_program_type check (
        kind <> 'program' or program_type is not null
    )
);

create index ix_proposals_user_status on proposals (user_id, status);

create unique index uq_proposals_one_pending
    on proposals (user_id)
    where status = 'pending';

create table workout_days (
    id uuid primary key default gen_random_uuid(),
    program_id uuid references programs (id) on delete cascade,
    proposal_id uuid references proposals (id) on delete cascade,
    session_id uuid references sessions (id) on delete cascade,
    weekday smallint check (weekday between 1 and 7),
    title text not null,
    position smallint not null check (position > 0),
    constraint workout_days_one_owner check (
        num_nonnulls(program_id, proposal_id, session_id) = 1
    )
);

create unique index uq_workout_days_program_weekday
    on workout_days (program_id, weekday)
    where program_id is not null;

create unique index uq_workout_days_program_position
    on workout_days (program_id, position)
    where program_id is not null;

create unique index uq_workout_days_proposal_position
    on workout_days (proposal_id, position)
    where proposal_id is not null;

create unique index uq_workout_days_session
    on workout_days (session_id)
    where session_id is not null;

create index ix_workout_days_program on workout_days (program_id);
create index ix_workout_days_proposal on workout_days (proposal_id);

alter table sessions
    add constraint sessions_source_day_fk
    foreign key (source_day_id) references workout_days (id);

create index ix_sessions_source_day on sessions (source_day_id);

create table exercise_slots (
    id uuid primary key default gen_random_uuid(),
    day_id uuid not null references workout_days (id) on delete cascade,
    position smallint not null check (position > 0),
    exercise_id uuid references exercises (id),
    custom_request text,
    muscle_group text,
    sets smallint not null check (sets > 0),
    reps smallint check (reps > 0),
    duration_seconds integer check (duration_seconds > 0),
    weight_kg numeric(6, 2) check (weight_kg > 0),
    rest_seconds integer not null check (rest_seconds > 0),
    rpe smallint not null check (rpe between 1 and 10),
    technique_note text not null default '',
    unique (day_id, position),
    constraint slots_reps_xor_duration check (
        (reps is not null and duration_seconds is null)
        or (reps is null and duration_seconds is not null)
    ),
    constraint slots_exercise_ref check (
        exercise_id is not null
        or (custom_request is not null and muscle_group is not null)
    )
);

create index ix_exercise_slots_exercise
    on exercise_slots (exercise_id)
    where exercise_id is not null;

create table slot_actuals (
    slot_id uuid primary key references exercise_slots (id) on delete cascade,
    sets smallint not null check (sets > 0),
    reps smallint check (reps > 0),
    duration_seconds integer check (duration_seconds > 0),
    weight_kg numeric(6, 2) check (weight_kg > 0),
    note text not null default '',
    constraint slot_actuals_reps_xor_duration check (
        (reps is not null and duration_seconds is null)
        or (reps is null and duration_seconds is not null)
    )
);

create table technique_videos (
    slot_id uuid primary key references exercise_slots (id) on delete cascade,
    user_id uuid not null references users (id) on delete cascade,
    session_id uuid not null references sessions (id) on delete cascade,
    object_key text not null,
    content_type text not null check (content_type like 'video/%%'),
    byte_size integer not null check (byte_size > 0 and byte_size <= 20971520),
    telegram_file_id text,
    created_at timestamptz not null default now(),
    unique (object_key)
);

create index ix_technique_videos_session on technique_videos (session_id);

create table nutrition_recommendations (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users (id) on delete cascade,
    program_id uuid not null references programs (id),
    goal text not null check (goal in ('fat_loss', 'muscle_gain', 'strength', 'maintenance')),
    stale boolean not null default false,
    kcal numeric(7, 1) not null check (kcal > 0),
    protein_g numeric(6, 1) not null check (protein_g >= 0),
    fat_g numeric(6, 1) not null check (fat_g >= 0),
    carb_g numeric(6, 1) not null check (carb_g >= 0),
    calculation text not null,
    meal_regularity text not null,
    snapshot_sex text not null,
    snapshot_birth_year integer not null check (snapshot_birth_year > 0),
    snapshot_height_cm numeric(5, 1) not null,
    snapshot_weight_kg numeric(5, 2) not null,
    snapshot_days_per_week smallint not null,
    snapshot_program_type text not null,
    created_at timestamptz not null default now()
);

create index ix_nutrition_user_created
    on nutrition_recommendations (user_id, created_at desc);

create index ix_nutrition_current
    on nutrition_recommendations (user_id, program_id, goal)
    where stale = false;

alter table users
    add constraint users_active_program_fk
    foreign key (active_program_id) references programs (id)
    on delete set null
    deferrable initially deferred;

alter table users
    add constraint users_active_session_fk
    foreign key (active_session_id) references sessions (id)
    on delete set null
    deferrable initially deferred;

alter table users
    add constraint users_pending_proposal_fk
    foreign key (pending_proposal_id) references proposals (id)
    on delete set null
    deferrable initially deferred;

comment on table users is 'Пользователь бота: профиль, одна цель и текущий шаг диалога.';
comment on column users.id is 'Суррогатный ключ пользователя.';
comment on column users.telegram_user_id is 'Идентификатор пользователя в Telegram. Уникален.';
comment on column users.chat_id is 'Чат, в который бот пишет этому пользователю.';
comment on column users.sex is 'Пол: male или female. Пусто, пока шаг онбординга не пройден.';
comment on column users.birth_year is 'Год рождения. Возраст в колонке не хранится, его считает код.';
comment on column users.height_cm is 'Рост в сантиметрах.';
comment on column users.experience is 'Свободный текст об опыте тренировок.';
comment on column users.days_per_week is 'Сколько дней в неделю пользователь тренируется, от 1 до 7.';
comment on column users.equipment is 'Свободный текст: место и оборудование.';
comment on column users.limitations is 'Травмы и ограничения свободным текстом.';
comment on column users.timezone_offset is 'Смещение пояса вида +03:00 или -05:00. Пусто, пока пользователь его не прислал.';
comment on column users.goal is 'Одна активная цель: fat_loss, muscle_gain, strength или maintenance.';
comment on column users.nutrition_stale is 'true, когда цель или активная программа сменились и питание надо пересчитать.';
comment on column users.expected_input is 'Какой следующий ввод ждёт бот. none — бот ничего не ждёт.';
comment on column users.expected_field is 'Имя поля профиля, когда expected_input равен profile_field.';
comment on column users.focus_slot is 'Позиция слота открытой сессии, когда диалог про факт или видео этого упражнения.';
comment on column users.active_program_id is 'Единственная активная программа. Пусто, если программы нет.';
comment on column users.active_session_id is 'Открытая сессия. Пусто, если тренировка не начата.';
comment on column users.pending_proposal_id is 'Единственный черновик на подтверждение. Пусто, если черновика нет. Новый pending заменяет предыдущий.';
comment on column users.created_at is 'Когда пользователь впервые написал боту.';
comment on column users.updated_at is 'Когда строка пользователя менялась в последний раз.';

comment on table user_training_weekdays is 'Дни недели тренировок. Их число совпадает с days_per_week, это сверяет домен.';
comment on column user_training_weekdays.user_id is 'Пользователь.';
comment on column user_training_weekdays.weekday is 'ISO-день: 1 понедельник … 7 воскресенье.';

comment on table weight_entries is 'История веса. Текущий вес — последняя строка по measured_at.';
comment on column weight_entries.id is 'Суррогатный ключ записи.';
comment on column weight_entries.user_id is 'Чей вес.';
comment on column weight_entries.kilograms is 'Вес в килограммах.';
comment on column weight_entries.measured_at is 'Момент, к которому относится замер.';
comment on column weight_entries.source is 'Откуда запись: onboarding, manual или reminder.';

comment on table weight_reminders is 'Расписание напоминания о весе. Одна строка на пользователя, если он его задал.';
comment on column weight_reminders.user_id is 'Пользователь. Он же первичный ключ.';
comment on column weight_reminders.local_time is 'Локальное время напоминания в поясе пользователя.';
comment on column weight_reminders.last_sent_on is 'Локальная дата последней отправки. Пусто, если ещё не отправляли.';

comment on table weight_reminder_weekdays is 'Дни недели, в которые уходит напоминание о весе.';
comment on column weight_reminder_weekdays.user_id is 'Расписание, к которому относится день.';
comment on column weight_reminder_weekdays.weekday is 'ISO-день напоминания.';

comment on table measurement_sites is 'Точки обхвата: восемь общих и свои точки пользователей.';
comment on column measurement_sites.id is 'Суррогатный ключ точки.';
comment on column measurement_sites.code is 'Код точки. У восьми общих точек он фиксированный.';
comment on column measurement_sites.name is 'Название точки, как его видит пользователь.';
comment on column measurement_sites.is_custom is 'false — общая точка, true — точка, которую пользователь назвал сам.';
comment on column measurement_sites.user_id is 'Владелец своей точки. У общей точки пусто.';

comment on table measurement_guides is 'Готовая инструкция замера. Пишется только для общей точки.';
comment on column measurement_guides.site_id is 'Точка, к которой относится инструкция.';
comment on column measurement_guides.instruction is 'Текст, как мерить эту точку.';

comment on table measurement_entries is 'История обхватов: одно число в сантиметрах на замер.';
comment on column measurement_entries.id is 'Суррогатный ключ замера.';
comment on column measurement_entries.user_id is 'Кто замерил.';
comment on column measurement_entries.site_id is 'Какая точка.';
comment on column measurement_entries.centimeters is 'Обхват в сантиметрах.';
comment on column measurement_entries.measured_at is 'Момент замера.';

comment on table exercises is 'Каталог упражнений. В диалоге бот его не пополняет: строки приходят из JSONL ревизией Alembic.';
comment on column exercises.id is 'Суррогатный ключ упражнения.';
comment on column exercises.name is 'Название для показа.';
comment on column exercises.name_normalized is 'Название для upsert и поиска. Уникально.';
comment on column exercises.technique is 'Текст техники выполнения.';

comment on table exercise_muscles is 'Мышцы упражнения каталога.';
comment on column exercise_muscles.exercise_id is 'Упражнение.';
comment on column exercise_muscles.muscle is 'Название мышцы из списка групп.';
comment on column exercise_muscles.role is 'primary — основная мышца, secondary — дополнительная.';

comment on table exercise_videos is 'Ссылки каталога на YouTube и Rutube. Это не видео техники пользователя.';
comment on column exercise_videos.id is 'Суррогатный ключ ссылки.';
comment on column exercise_videos.exercise_id is 'Упражнение.';
comment on column exercise_videos.platform is 'youtube или rutube.';
comment on column exercise_videos.url is 'Адрес ролика.';
comment on column exercise_videos.title is 'Название ролика из поиска.';
comment on column exercise_videos.position is 'Порядок ссылки внутри упражнения.';

comment on table programs is 'Подтверждённая недельная программа. Активна одна, прошлые остаются со статусом archived. До аппрува недели здесь нет.';
comment on column programs.id is 'Суррогатный ключ программы.';
comment on column programs.user_id is 'Владелец.';
comment on column programs.program_type is 'Вид: split, full_body или push_pull.';
comment on column programs.status is 'active или archived. Черновик сюда не пишется: до аппрува неделя лежит в proposals.';
comment on column programs.created_at is 'Когда программа создана аппрувом.';
comment on column programs.activated_at is 'Когда программа стала активной. Совпадает с аппрувом.';
comment on column programs.archived_at is 'Когда программу сняли с активности.';

comment on table sessions is 'Одна тренировка. Открыта одна, завершённые остаются в истории.';
comment on column sessions.id is 'Суррогатный ключ сессии.';
comment on column sessions.user_id is 'Кто тренируется.';
comment on column sessions.source_day_id is 'День программы, с которого сессия скопирована. Пусто, если сессия собрана без шаблона.';
comment on column sessions.status is 'in_progress, pending_completion или completed.';
comment on column sessions.started_at is 'Когда сессия начата.';
comment on column sessions.completed_at is 'Когда сессия завершена. Пусто, пока статус не completed.';

comment on table proposals is 'Черновик на подтверждение. У пользователя один pending, нового вида или того же.';
comment on column proposals.id is 'Суррогатный ключ черновика.';
comment on column proposals.user_id is 'Чей черновик.';
comment on column proposals.kind is 'program, workout_edit, performance, next_session или completion_deviation.';
comment on column proposals.status is 'pending, approved или discarded.';
comment on column proposals.program_type is 'Вид недели: split, full_body или push_pull. Заполнен только при kind = program.';
comment on column proposals.base_program_id is 'Программа, поверх которой черновик. Пусто, если черновик не про программу.';
comment on column proposals.base_session_id is 'Сессия, поверх которой черновик. Пусто, если черновик не про сессию.';
comment on column proposals.created_at is 'Когда черновик создан.';

comment on table workout_days is 'День программы, черновика или сессии. Владелец ровно один.';
comment on column workout_days.id is 'Суррогатный ключ дня.';
comment on column workout_days.program_id is 'Программа-владелец. Пусто, если день принадлежит черновику или сессии.';
comment on column workout_days.proposal_id is 'Черновик-владелец. Пусто у дня программы и сессии.';
comment on column workout_days.session_id is 'Сессия-владелец. Пусто у дня программы и черновика.';
comment on column workout_days.weekday is 'ISO-день. Для дня программы заполнен.';
comment on column workout_days.title is 'Название дня, как его видит пользователь.';
comment on column workout_days.position is 'Порядок дня внутри владельца.';

comment on table exercise_slots is 'Упражнение внутри дня: план подходов, веса, отдыха и техники.';
comment on column exercise_slots.id is 'Суррогатный ключ слота.';
comment on column exercise_slots.day_id is 'День, в который входит слот.';
comment on column exercise_slots.position is 'Порядок упражнения в дне.';
comment on column exercise_slots.exercise_id is 'Упражнение каталога. Пусто, пока слот не выбран из каталога.';
comment on column exercise_slots.custom_request is 'Текст пользователя, какое движение он хочет, пока exercise_id пуст.';
comment on column exercise_slots.muscle_group is 'Мышца из той же реплики. Заполняется вместе с custom_request, когда exercise_id пуст.';
comment on column exercise_slots.sets is 'Число подходов.';
comment on column exercise_slots.reps is 'Повторы. Заполнены, когда длительности нет.';
comment on column exercise_slots.duration_seconds is 'Длительность подхода в секундах. Заполнена, когда повторов нет.';
comment on column exercise_slots.weight_kg is 'Рабочий или целевой вес в килограммах. Пусто, если вес не задан.';
comment on column exercise_slots.rest_seconds is 'Отдых между подходами в секундах.';
comment on column exercise_slots.rpe is 'Интенсивность от 1 до 10.';
comment on column exercise_slots.technique_note is 'Комментарий по технике в плане. Пустая строка, если комментария нет.';

comment on table slot_actuals is 'Факт выполнения слота сессии. Шаблон дня из-за этой строки не меняется.';
comment on column slot_actuals.slot_id is 'Слот, к которому относится факт. Одна строка на слот.';
comment on column slot_actuals.sets is 'Сколько подходов сделано.';
comment on column slot_actuals.reps is 'Фактические повторы. Заполнены, когда длительности нет.';
comment on column slot_actuals.duration_seconds is 'Фактическая длительность в секундах. Заполнена, когда повторов нет.';
comment on column slot_actuals.weight_kg is 'Фактический вес в килограммах. Пусто, если вес не записывали.';
comment on column slot_actuals.note is 'Заметка к факту. Пустая строка, если заметки нет.';

comment on table technique_videos is 'Один ролик техники пользователя на слот сессии. Файл лежит в S3.';
comment on column technique_videos.slot_id is 'Слот сессии. Новая загрузка заменяет эту строку.';
comment on column technique_videos.user_id is 'Кто снял ролик.';
comment on column technique_videos.session_id is 'Сессия, которой принадлежит день этого слота.';
comment on column technique_videos.object_key is 'Ключ объекта в бакете: users/{user_id}/sessions/{session_id}/slots/{slot_id}.';
comment on column technique_videos.content_type is 'MIME ролика. Начинается с video/.';
comment on column technique_videos.byte_size is 'Размер файла в байтах, не больше 20 МБ.';
comment on column technique_videos.telegram_file_id is 'file_id после первой успешной отправки в чат. Пусто до неё и после замены ролика.';
comment on column technique_videos.created_at is 'Когда ролик сохранён.';

comment on table nutrition_recommendations is 'Сохранённый расчёт питания. Новый расчёт — когда меняется цель или активная программа.';
comment on column nutrition_recommendations.id is 'Суррогатный ключ рекомендации.';
comment on column nutrition_recommendations.user_id is 'Кому рассчитано.';
comment on column nutrition_recommendations.program_id is 'Программа, на которую рассчитано.';
comment on column nutrition_recommendations.goal is 'Цель на момент расчёта.';
comment on column nutrition_recommendations.stale is 'true, если цель или программа уже другие.';
comment on column nutrition_recommendations.kcal is 'Калории.';
comment on column nutrition_recommendations.protein_g is 'Белок, граммы.';
comment on column nutrition_recommendations.fat_g is 'Жиры, граммы.';
comment on column nutrition_recommendations.carb_g is 'Углеводы, граммы.';
comment on column nutrition_recommendations.calculation is 'Текст хода расчёта.';
comment on column nutrition_recommendations.meal_regularity is 'Текст про регулярность приёмов пищи.';
comment on column nutrition_recommendations.snapshot_sex is 'Пол на момент расчёта.';
comment on column nutrition_recommendations.snapshot_birth_year is 'Год рождения на момент расчёта. Возраст в снимок не пишется.';
comment on column nutrition_recommendations.snapshot_height_cm is 'Рост на момент расчёта, сантиметры.';
comment on column nutrition_recommendations.snapshot_weight_kg is 'Вес на момент расчёта, килограммы.';
comment on column nutrition_recommendations.snapshot_days_per_week is 'Дней в неделю на момент расчёта.';
comment on column nutrition_recommendations.snapshot_program_type is 'Вид программы на момент расчёта.';
comment on column nutrition_recommendations.created_at is 'Когда рекомендация создана.';
"""


def upgrade() -> None:
    # Raw driver SQL: timezone regex contains `:0` / `:[0-5]`, which SQLAlchemy
    # would otherwise treat as bind parameters.
    op.get_bind().exec_driver_sql(DDL)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        drop table if exists nutrition_recommendations cascade;
        drop table if exists technique_videos cascade;
        drop table if exists slot_actuals cascade;
        drop table if exists exercise_slots cascade;
        drop table if exists workout_days cascade;
        drop table if exists proposals cascade;
        drop table if exists sessions cascade;
        drop table if exists programs cascade;
        drop table if exists exercise_videos cascade;
        drop table if exists exercise_muscles cascade;
        drop table if exists exercises cascade;
        drop table if exists measurement_entries cascade;
        drop table if exists measurement_guides cascade;
        drop table if exists measurement_sites cascade;
        drop table if exists weight_reminder_weekdays cascade;
        drop table if exists weight_reminders cascade;
        drop table if exists weight_entries cascade;
        drop table if exists user_training_weekdays cascade;
        drop table if exists users cascade;
        """
    )
