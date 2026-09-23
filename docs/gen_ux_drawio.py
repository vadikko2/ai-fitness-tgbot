"""Собирает docs/ux.drawio. Узлы начинаются с кода шага из реестра плана."""

from __future__ import annotations

import html
from pathlib import Path

OUT = Path(__file__).resolve().parent / "ux.drawio"

STYLES = {
    "user": "rounded=1;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=11;",
    "bot": "rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;fontSize=11;",
    "agent": "rounded=1;whiteSpace=wrap;html=1;fillColor=#ffe6cc;strokeColor=#d79b00;fontSize=11;",
    "decision": "rhombus;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;fontSize=11;",
    "store": "shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=12;fillColor=#e1d5e7;strokeColor=#9673a6;fontSize=11;",
    "note": "rounded=1;whiteSpace=wrap;html=1;fillColor=#f5f5f5;strokeColor=#666666;fontSize=11;align=left;spacingLeft=8;",
}


def box(kind: str) -> tuple[int, int]:
    if kind == "decision":
        return 220, 110
    if kind == "note":
        return 280, 70
    return 230, 68


def node(code: str, body: str, kind: str, x: int, y: int) -> dict:
    width, height = box(kind)
    return {
        "id": code.replace(".", "").replace("-", "_"),
        "code": code,
        "value": f"{code}\n{body}",
        "kind": kind,
        "x": x,
        "y": y,
        "w": width,
        "h": height,
    }


def page_nodes(specs: list[tuple[str, str, str, int, int]]) -> list[dict]:
    return [node(code, body, kind, x, y) for code, body, kind, x, y in specs]


PAGE_1 = page_nodes(
    [
        ("start", "/start\nhandle_start\nEnsureUserCommand", "user", 40, 40),
        ("onb_check", "Профиль полный?\nGetProfileQuery", "decision", 50, 140),
        ("onb_sex", "Пол\nhandle_onb_sex\nUpdateProfileCommand", "user", 40, 290),
        ("onb_birth", "Год рождения\nhandle_tg_text\nUpdateProfileCommand", "bot", 40, 390),
        ("onb_height", "Рост\nhandle_tg_text\nUpdateProfileCommand", "bot", 40, 480),
        ("onb_weight", "Первый вес\nUpdateProfileCommand\nRecordWeightCommand", "store", 40, 570),
        ("onb_exp", "Опыт\nhandle_tg_text\nUpdateProfileCommand", "bot", 40, 680),
        ("onb_freq", "Дней в неделю\nhandle_tg_text\nUpdateProfileCommand", "bot", 40, 770),
        ("onb_days", "Дни недели\nhandle_onb_days\nUpdateProfileCommand", "user", 40, 860),
        ("onb_equip", "Оборудование\nhandle_tg_text\nUpdateProfileCommand", "bot", 40, 960),
        ("onb_limits", "Ограничения или нет\nhandle_onb_limits\nUpdateProfileCommand", "user", 40, 1050),
        ("onb_tz", "Пояс +03:00\nhandle_tg_text\nUpdateProfileCommand", "bot", 40, 1150),
        ("onb_goal", "Одна цель\nhandle_onb_goal\nSetGoalCommand", "user", 40, 1240),
        ("prog", "Дальше программа\nhandle_prog", "bot", 40, 1340),
        ("TG-TEXT", "Любой текст\nhandle_tg_text\nGetWorkflowQuery", "note", 420, 40),
        ("TG-VOICE", "Голос → SpeechToText\nдальше TG-TEXT", "note", 740, 40),
        ("home", "Главное меню\nhandle_home\nGetHomeQuery", "bot", 560, 160),
        ("sess", "Тренировка сегодня\nhandle_sess", "user", 420, 280),
        ("wt_menu", "Вес\nhandle_wt_menu", "user", 680, 280),
        ("meas_menu", "Обхваты\nhandle_meas_menu", "user", 940, 280),
        ("nutr", "Питание\nhandle_nutr", "user", 420, 380),
        ("profile", "Профиль\nhandle_profile\nGetProfileQuery", "user", 680, 380),
        ("hist", "История\nhandle_hist", "user", 940, 380),
        ("prof_edit", "Поле или цель?\nhandle_prof_edit", "decision", 620, 500),
        ("prof_value", "Новое значение поля\nUpdateProfileCommand", "bot", 420, 660),
        ("prof_goal", "Новая цель\nhandle_prof_goal\nSetGoalCommand", "user", 760, 660),
    ]
)

PAGE_1_EDGES = [
    ("start", "onb_check", ""),
    ("onb_check", "onb_sex", "нет"),
    ("onb_check", "home", "да"),
    ("onb_sex", "onb_birth", ""),
    ("onb_birth", "onb_height", ""),
    ("onb_height", "onb_weight", ""),
    ("onb_weight", "onb_exp", ""),
    ("onb_exp", "onb_freq", ""),
    ("onb_freq", "onb_days", ""),
    ("onb_days", "onb_equip", ""),
    ("onb_equip", "onb_limits", ""),
    ("onb_limits", "onb_tz", ""),
    ("onb_tz", "onb_goal", ""),
    ("onb_goal", "prog", ""),
    ("home", "sess", ""),
    ("home", "prog", ""),
    ("home", "wt_menu", ""),
    ("home", "meas_menu", ""),
    ("home", "nutr", ""),
    ("home", "profile", ""),
    ("home", "hist", ""),
    ("profile", "prof_edit", ""),
    ("prof_edit", "prof_value", "поле"),
    ("prof_edit", "prof_goal", "цель"),
    ("prof_value", "home", ""),
    ("prof_goal", "home", ""),
]

PAGE_2 = page_nodes(
    [
        ("prog", "Экран программы\nGetActiveProgramQuery\nGetPendingProposalQuery", "bot", 40, 40),
        ("prog_setup", "Как задать?\nhandle_prog_setup", "decision", 50, 160),
        ("prog_type", "Вид: сплит / фуллбади / тяни-толкай\nhandle_prog_type\nChooseProgramTypeCommand", "user", 40, 320),
        ("prog_gen", "Пусть предложит\nhandle_prog_gen\nProposeProgramCommand", "agent", 360, 320),
        ("prog_text", "Опишу текстом\nhandle_prog_text\nExpectInputCommand", "user", 40, 460),
        ("prog_edit", "Изменить текстом\nhandle_prog_edit\nExpectInputCommand", "user", 360, 460),
        ("prog_utter", "Реплика про неделю\nhandle_tg_text\nProposeProgramChangeCommand", "agent", 40, 580),
        ("prog_unres", "Слот без exercise_id?", "decision", 340, 560),
        ("prog_match", "До 5 кнопок\nMatchExercisesQuery", "bot", 860, 580),
        ("prog_pick", "Выбор упражнения\nhandle_prog_pick\nSelectExerciseForProposalCommand", "user", 860, 720),
        ("prog_block", "Аппрув отклонён\nслот пустой", "bot", 1160, 580),
        ("prog_draft", "Черновик недели\nhandle_prog_draft\nGetPendingProposalQuery", "bot", 360, 740),
        ("prog_ok", "Подтвердить\nhandle_prog_ok\nApproveProposalCommand", "user", 40, 860),
        ("prog_saved", "Программа активна\nпитание устарело", "store", 40, 980),
        ("draft_cancel", "Отмена черновика\nhandle_draft_cancel\nDiscardProposalCommand", "user", 700, 40),
        ("home", "В меню\nhandle_home", "bot", 40, 1120),
    ]
)

PAGE_2_EDGES = [
    ("prog", "prog_setup", "заново"),
    ("prog", "prog_edit", "изменить"),
    ("prog", "prog_draft", "есть черновик"),
    ("prog_setup", "prog_type", "сам"),
    ("prog_setup", "prog_gen", "агент"),
    ("prog_type", "prog_text", "текстом"),
    ("prog_type", "prog_gen", "агент"),
    ("prog_text", "prog_utter", "текст"),
    ("prog_edit", "prog_utter", "текст"),
    ("prog_gen", "prog_draft", ""),
    ("prog_utter", "prog_unres", ""),
    ("prog_unres", "prog_match", "да"),
    ("prog_unres", "prog_draft", "нет"),
    ("prog_match", "prog_pick", ""),
    ("prog_pick", "prog_unres", ""),
    ("prog_draft", "prog_edit", "изменить"),
    ("prog_draft", "prog_ok", "подтвердить"),
    ("prog_ok", "prog_saved", "все слоты из каталога"),
    ("prog_ok", "prog_block", "слот пустой", [(1500, 894), (1500, 614)]),
    ("prog_block", "prog_match", ""),
    ("prog_saved", "home", ""),
    ("prog_draft", "draft_cancel", "отмена", [(1500, 820), (1500, 74)]),
    ("draft_cancel", "prog", ""),
]

PAGE_3 = page_nodes(
    [
        ("sess", "Тренировка сегодня\nhandle_sess\nGetTodayWorkoutQuery", "user", 40, 40),
        ("sess_state", "Есть in_progress?", "decision", 50, 150),
        ("sess_card", "Карточка сессии\nhandle_sess_card\nGetTodayWorkoutQuery", "bot", 480, 150),
        ("sess_noprog", "Нет программы\nкнопка на prog", "bot", 40, 310),
        ("prog", "К программе\nhandle_prog", "bot", 40, 430),
        ("sess_rest", "Выходной", "bot", 320, 310),
        ("hist", "История\nhandle_hist", "user", 320, 430),
        ("sess_tmpl", "Шаблон дня\nплан на сегодня", "bot", 780, 310),
        ("sess_plan", "Начать как в плане\nhandle_sess_plan\nStartSessionFromTemplateCommand", "user", 780, 430),
        ("sess_plan_ask", "Уже выполнена?\nповторить с перезаписью", "decision", 520, 560),
        ("sess_plan_repeat", "Повторить\nhandle_sess_plan_repeat\nStartSessionFromTemplateCommand", "user", 780, 700),
        ("sess_tmpl_edit", "Изменить тренировку\nhandle_sess_tmpl_edit", "bot", 1060, 200),
        ("sess_tmpl_edit_text", "Написать что поменять\nhandle_sess_tmpl_edit_text", "user", 1060, 560),
        ("sess_gen", "Перегенерировать по истории\nhandle_sess_gen\nGenerateNextSessionCommand", "agent", 1320, 200),
        ("sess_gen_ok", "Аппрув генерации\nhandle_sess_gen_ok\nApproveProposalCommand", "user", 1320, 560),
        ("slot", "Тап по упражнению\nhandle_slot", "decision", 40, 760),
        ("slot_plan", "Как в плане → дальше\nhandle_slot_plan\nConfirmExerciseAsPlannedCommand", "user", 40, 920),
        ("slot_fact", "Вес и повторы\nhandle_slot_fact\nSLOT_WEIGHT → SLOT_LOAD", "user", 320, 920),
        ("slot_utter", "Текст факта\nhandle_tg_text\nProposeSlotActualCommand", "agent", 320, 1020),
        ("slot_ok", "Аппрув слота\nhandle_slot_ok\nApproveProposalCommand", "user", 320, 1140),
        ("slot_how", "Как делать\nhandle_slot_how\nGetExerciseGuideQuery", "bot", 40, 1160),
        ("slot_video", "Загрузить видео упражнения\nhandle_slot_video\nExpectInputCommand", "user", 40, 1280),
        ("TG-VIDEO", "Видео / кружок / документ\nhandle_tg_video", "user", 40, 1400),
        ("slot_vid_up", "Ролик сохранён\nSaveTechniqueVideoCommand", "store", 320, 1400),
        ("slot_vid_ok", "Ролик не принят", "bot", 40, 1520),
        ("sess_edit", "Изменить сессию\nhandle_sess_edit\nExpectInputCommand", "user", 620, 860),
        ("sess_utter", "Реплика\nhandle_tg_text\nProposeWorkoutChangeCommand", "agent", 620, 980),
        ("sess_match", "Кнопки каталога\nMatchExercisesQuery", "bot", 900, 860),
        ("sess_pick", "Выбор упражнения\nhandle_sess_pick\nSelectExerciseForProposalCommand", "user", 900, 980),
        ("sess_edit_ok", "Аппрув правки\nhandle_sess_edit_ok\nApproveProposalCommand", "user", 900, 1100),
        ("sess_all", "Выполнить всю\nhandle_sess_all\nBeginSessionCompletionCommand", "user", 620, 1280),
        ("sess_sum", "Что не по плану?", "decision", 630, 1390),
        ("sess_fin", "Готово\nhandle_sess_fin\nFinalizeSessionCommand", "store", 620, 1550),
        ("sess_dev", "Текст отклонений\nhandle_tg_text\nProposeSessionDeviationCommand", "agent", 900, 1550),
        ("sess_fin_ok", "Аппрув и завершить\nhandle_sess_fin_ok\nApproveProposalCommand\nFinalizeSessionCommand", "store", 900, 1660),
        ("home", "В меню", "bot", 620, 1780),
    ]
)

PAGE_3_EDGES = [
    ("sess", "sess_state", ""),
    ("sess_state", "sess_card", "да"),
    ("sess_state", "sess_noprog", "нет программы"),
    ("sess_state", "sess_rest", "выходной", [(160, 280), (430, 280), (430, 344)]),
    ("sess_state", "sess_tmpl", "день программы", [(160, 280), (895, 280), (895, 344)]),
    ("sess_noprog", "prog", ""),
    ("sess_rest", "hist", ""),
    ("sess_tmpl", "sess_plan", "начать"),
    ("sess_tmpl", "sess_tmpl_edit", "изменить"),
    ("sess_tmpl_edit", "sess_tmpl_edit_text", "написать"),
    ("sess_tmpl_edit", "sess_gen", "по истории"),
    ("sess_tmpl_edit", "sess", "назад"),
    ("sess_tmpl_edit_text", "sess_card", "старт + правка"),
    ("sess_plan", "sess_card", "ещё не было"),
    ("sess_plan", "sess_plan_ask", "уже выполнена"),
    ("sess_plan_ask", "sess_plan_repeat", "повторить"),
    ("sess_plan_ask", "sess", "отмена"),
    ("sess_plan_repeat", "sess_card", "перезапись"),
    ("sess_gen", "sess_gen_ok", ""),
    ("sess_gen_ok", "sess_card", "", [(1550, 464), (1550, 100), (710, 100)]),
    ("sess_card", "slot", ""),
    ("slot", "slot_plan", "как в плане"),
    ("slot", "slot_fact", "свой факт"),
    ("slot", "slot_how", "как делать"),
    ("slot", "slot_video", "загрузить видео"),
    ("slot_plan", "sess_card", ""),
    ("slot_fact", "slot_utter", "текст"),
    ("slot_utter", "slot_ok", ""),
    ("slot_ok", "sess_card", "к карточке"),
    ("slot_ok", "slot_video", "видео"),
    ("slot_how", "slot", "назад"),
    ("slot_video", "TG-VIDEO", "ролик"),
    ("TG-VIDEO", "slot_vid_up", "принято"),
    ("TG-VIDEO", "slot_vid_ok", "отклонено"),
    ("slot_vid_up", "sess_card", "к карточке"),
    ("slot_vid_ok", "slot_video", "ещё раз"),
    ("sess_card", "sess_edit", ""),
    ("sess_edit", "sess_utter", "текст"),
    ("sess_utter", "sess_match", "есть пустой слот"),
    ("sess_utter", "sess_edit_ok", "все из каталога"),
    ("sess_match", "sess_pick", ""),
    ("sess_pick", "sess_edit_ok", ""),
    ("sess_edit_ok", "sess_card", "к карточке"),
    ("sess_card", "sess_all", ""),
    ("sess_all", "sess_sum", ""),
    ("sess_sum", "sess_fin", "Готово"),
    ("sess_sum", "sess_dev", "текст"),
    ("sess_dev", "sess_fin_ok", ""),
    ("sess_fin", "home", ""),
    ("sess_fin_ok", "home", ""),
]

PAGE_4 = page_nodes(
    [
        ("wt_menu", "Меню веса\nhandle_wt_menu", "user", 40, 40),
        ("wt_log", "Записать\nhandle_wt_log\nExpectInputCommand", "user", 40, 150),
        ("wt_save", "Число кг\nhandle_tg_text\nRecordWeightCommand", "store", 40, 260),
        ("wt_hist", "История веса\nhandle_wt_hist\nGetWeightHistoryQuery", "bot", 40, 380),
        ("wt_remind", "Расписание\nhandle_wt_remind\nSetWeightReminderCommand", "user", 40, 490),
        ("wt_tick", "Тик раз в минуту\nhandle_wt_tick\nListDueWeightRemindersQuery", "bot", 40, 700),
        ("wt_ask", "Какой вес?\nhandle_wt_ask\nMarkWeightReminderSentCommand", "bot", 300, 700),
        ("meas_menu", "Точки обхвата\nhandle_meas_menu", "user", 360, 40),
        ("meas_site", "Инструкция\nhandle_meas_site\nGetMeasurementGuideQuery", "bot", 360, 150),
        ("meas_custom", "Своё имя\nhandle_tg_text\nAddCustomMeasurementSiteCommand", "bot", 640, 150),
        ("meas_value", "Сантиметры\nhandle_tg_text\nRecordMeasurementCommand", "store", 500, 280),
        ("meas_hist", "История точки\nhandle_meas_hist\nGetMeasurementHistoryQuery", "bot", 360, 400),
        ("nutr", "Питание\nhandle_nutr\nGetNutritionQuery", "user", 920, 40),
        ("nutr_noprog", "Нет программы\nувести в prog", "bot", 1480, 40),
        ("prog", "К программе\nhandle_prog", "bot", 1480, 160),
        ("nutr_check", "Запись годна?", "decision", 930, 160),
        ("nutr_show", "Показать сохранённое\nhandle_nutr_show", "bot", 900, 340),
        ("nutr_gen", "Считать заново\nhandle_nutr_gen\nGenerateNutritionCommand", "agent", 1180, 340),
        ("hist", "Меню истории\nhandle_hist", "user", 920, 520),
        ("hist_sess", "Сессии\nhandle_hist_sess\nGetSessionHistoryQuery", "bot", 920, 630),
        ("hist_one", "Выбор тренировки\nhandle_hist_one\nGetSessionDetailQuery", "user", 1180, 630),
        ("hist_card", "Факт сессии\nhistory_session.j2", "bot", 1180, 740),
        ("hist_vid", "Посмотреть видео\nhandle_hist_vid\nPrepareTechniqueVideoDeliveryQuery", "user", 1440, 740),
        ("hist_vid_ok", "Не удалось отправить\ntechnique_video_failed.j2", "bot", 1440, 850),
        ("hist_wt", "Вес\nhandle_hist_wt\nGetWeightHistoryQuery", "bot", 920, 740),
        ("hist_meas", "Обхваты\nhandle_hist_meas\nGetMeasurementHistoryQuery", "bot", 920, 850),
        ("C1", "CLI\nSeedMeasurementGuidesCommand", "store", 640, 520),
        ("C2", "CLI\nSeedExerciseCatalogCommand", "store", 640, 660),
    ]
)

PAGE_4_EDGES = [
    ("wt_menu", "wt_log", "записать"),
    ("wt_menu", "wt_hist", "история"),
    ("wt_menu", "wt_remind", "расписание"),
    ("wt_log", "wt_save", "число"),
    ("wt_tick", "wt_ask", "срок наступил"),
    ("wt_ask", "wt_save", "ответ", [(410, 800), (20, 800), (20, 294)]),
    ("meas_menu", "meas_site", "фиксированная"),
    ("meas_menu", "meas_custom", "своя"),
    ("meas_site", "meas_value", "сантиметры"),
    ("meas_custom", "meas_value", "сантиметры"),
    ("meas_site", "meas_hist", "история"),
    ("meas_value", "meas_menu", ""),
    ("nutr", "nutr_noprog", "нет программы"),
    ("nutr", "nutr_check", "есть программа"),
    ("nutr_check", "nutr_show", "годна"),
    ("nutr_check", "nutr_gen", "устарела"),
    ("nutr_gen", "nutr_show", ""),
    ("nutr_noprog", "prog", ""),
    ("hist", "hist_sess", ""),
    ("hist", "hist_wt", ""),
    ("hist", "hist_meas", ""),
    ("hist_sess", "hist_one", ""),
    ("hist_one", "hist_card", ""),
    ("hist_card", "hist_vid", "смотреть"),
    ("hist_vid", "hist_vid_ok", "ошибка"),
]


def overlaps(nodes: list[dict]) -> list[str]:
    problems: list[str] = []
    for i, left in enumerate(nodes):
        for right in nodes[i + 1 :]:
            separated = (
                left["x"] + left["w"] + 12 <= right["x"]
                or right["x"] + right["w"] + 12 <= left["x"]
                or left["y"] + left["h"] + 12 <= right["y"]
                or right["y"] + right["h"] + 12 <= left["y"]
            )
            if not separated:
                problems.append(f"{left['code']} overlaps {right['code']}")
    return problems


def _rects_for(nodes: list[dict]) -> dict[str, tuple[float, float, float, float]]:
    return {
        item["code"]: (item["x"], item["y"], item["x"] + item["w"], item["y"] + item["h"])
        for item in nodes
    }


def _segment_hits_rect(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    rect: tuple[float, float, float, float],
    *,
    endpoint_slack: float = 1.0,
) -> bool:
    left, top, right, bottom = rect
    # Skip nearly-zero segments.
    if abs(x1 - x2) < 1e-6 and abs(y1 - y2) < 1e-6:
        return False
    # Sample the open interval of the segment; endpoints may touch node borders.
    for step in range(1, 20):
        t = step / 20
        x = x1 + (x2 - x1) * t
        y = y1 + (y2 - y1) * t
        if left + endpoint_slack < x < right - endpoint_slack and top + endpoint_slack < y < bottom - endpoint_slack:
            return True
    return False


def edge_crosses_nodes(nodes: list[dict], edges: list[tuple]) -> list[str]:
    by_code = {item["code"]: item for item in nodes}
    rects = _rects_for(nodes)
    problems: list[str] = []
    for edge in edges:
        if len(edge) < 4 or not edge[3]:
            continue
        source, target = edge[0], edge[1]
        points = list(edge[3])
        src = by_code[source]
        dst = by_code[target]
        path = [
            (src["x"] + src["w"] / 2, src["y"] + src["h"] / 2),
            *points,
            (dst["x"] + dst["w"] / 2, dst["y"] + dst["h"] / 2),
        ]
        for index in range(len(path) - 1):
            x1, y1 = path[index]
            x2, y2 = path[index + 1]
            for code, rect in rects.items():
                if code in {source, target}:
                    continue
                if _segment_hits_rect(x1, y1, x2, y2, rect):
                    problems.append(f"edge {source}->{target} crosses {code}")
    return problems


def render_page(name: str, nodes: list[dict], edges: list[tuple], width: int, height: int) -> str:
    problems = overlaps(nodes)
    if problems:
        raise SystemExit(name + ": " + "; ".join(problems))
    crossing = edge_crosses_nodes(nodes, edges)
    if crossing:
        raise SystemExit(name + ": " + "; ".join(crossing))
    by_code = {}
    for item in nodes:
        if item["code"] in by_code:
            raise SystemExit(f"{name}: duplicate {item['code']}")
        by_code[item["code"]] = item["id"]
    cells = [
        '<mxCell id="0"/>',
        '<mxCell id="1" parent="0"/>',
    ]
    legend = html.escape(
        "Зелёный — действие. Синий — экран. Оранжевый — модель. Жёлтый — развилка. Фиолетовый — запись."
    )
    cells.append(
        f'<mxCell id="legend" value="{legend}" style="{STYLES["note"]}" vertex="1" parent="1">'
        f'<mxGeometry x="40" y="8" width="640" height="28" as="geometry"/></mxCell>'
    )
    for item in nodes:
        value = html.escape(item["value"]).replace("\n", "&#xa;")
        cells.append(
            f'<mxCell id="{item["id"]}" value="{value}" style="{STYLES[item["kind"]]}" vertex="1" parent="1">'
            f'<mxGeometry x="{item["x"]}" y="{item["y"]}" width="{item["w"]}" height="{item["h"]}" as="geometry"/>'
            f"</mxCell>"
        )
    for index, edge in enumerate(edges):
        source, target, label = edge[0], edge[1], edge[2]
        points = edge[3] if len(edge) > 3 else ()
        if source not in by_code or target not in by_code:
            raise SystemExit(f"{name}: missing endpoint {source} -> {target}")
        point_xml = ""
        if points:
            inner = "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in points)
            point_xml = f'<Array as="points">{inner}</Array>'
        cells.append(
            f'<mxCell id="e{index}" value="{html.escape(label)}" '
            f'style="edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;endFill=1;fontSize=11;" '
            f'edge="1" parent="1" source="{by_code[source]}" target="{by_code[target]}">'
            f'<mxGeometry relative="1" as="geometry">{point_xml}</mxGeometry></mxCell>'
        )
    body = "".join(f"<root>{''.join(cells)}</root>")
    return (
        f'<diagram id="{html.escape(name)}" name="{html.escape(name)}">'
        f'<mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{width}" pageHeight="{height}" math="0" shadow="0">'
        f"{body}</mxGraphModel></diagram>"
    )


def main() -> None:
    # Self-loop on hist was a placeholder and is removed: history tabs live on page 4.
    pages = [
        render_page("Онбординг и меню", PAGE_1, PAGE_1_EDGES, 1400, 1560),
        render_page("Программа", PAGE_2, PAGE_2_EDGES, 1720, 1320),
        render_page("Тренировка", PAGE_3, PAGE_3_EDGES, 1650, 1960),
        render_page("Тело питание история", PAGE_4, PAGE_4_EDGES, 1820, 1100),
    ]
    OUT.write_text(
        '<mxfile host="app.diagrams.net" agent="cursor" version="22.1.0" type="device">'
        + "".join(pages)
        + "</mxfile>\n",
        encoding="utf-8",
    )
    print(OUT)


if __name__ == "__main__":
    main()
