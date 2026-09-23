"""Проверка, что коды UX на диаграмме совпадают с реестром плана и что сценарии проходимы."""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRAWIO = ROOT / "docs" / "ux.drawio"
PLAN = Path(
    "/Users/vadimkozyrevskij/.cursor/plans/fitness_bot_plan_fa2e044c.plan.md",
)

# Plan registry still uses Sx.yy; diagram/callbacks use idiomatic UX ids.
PLAN_TO_UX: dict[str, str] = {
    "S1.01": "start",
    "S1.02": "onb_check",
    "S1.03": "onb_sex",
    "S1.04": "onb_birth",
    "S1.05": "onb_height",
    "S1.06": "onb_weight",
    "S1.07": "onb_exp",
    "S1.08": "onb_freq",
    "S1.09": "onb_days",
    "S1.10": "onb_equip",
    "S1.11": "onb_limits",
    "S1.12": "onb_tz",
    "S1.13": "onb_goal",
    "S1.14": "home",
    "S2.01": "profile",
    "S2.02": "prof_edit",
    "S2.03": "prof_goal",
    "S2.04": "prof_value",
    "S3.01": "wt_menu",
    "S3.02": "wt_log",
    "S3.03": "wt_save",
    "S3.04": "wt_hist",
    "S3.05": "wt_remind",
    "S4.01": "wt_tick",
    "S4.02": "wt_ask",
    "S5.01": "meas_menu",
    "S5.02": "meas_site",
    "S5.03": "meas_custom",
    "S5.04": "meas_value",
    "S5.05": "meas_hist",
    "S6.01": "prog",
    "S6.02": "prog_setup",
    "S6.03": "prog_type",
    "S6.04": "prog_text",
    "S7.01": "prog_gen",
    "S7.02": "prog_draft",
    "S8.01": "prog_edit",
    "S8.02": "prog_utter",
    "S8.03": "prog_unres",
    "S8.04": "prog_match",
    "S8.05": "prog_pick",
    "S8.06": "prog_ok",
    "S8.07": "prog_block",
    "S8.08": "prog_saved",
    "S8.09": "draft_cancel",
    "S9.01": "sess",
    "S9.02": "sess_state",
    "S9.03": "sess_rest",
    "S9.04": "sess_tmpl",
    "S9.05": "sess_plan",
    "S9.06": "sess_gen",
    "S9.07": "sess_card",
    "S9.08": "sess_noprog",
    "S9.09": "sess_plan_ask",
    "S9.10": "sess_plan_repeat",
    "S9.11": "sess_tmpl_edit",
    "S9.12": "sess_tmpl_edit_text",
    "S10.01": "sess_edit",
    "S10.02": "sess_utter",
    "S10.03": "sess_match",
    "S10.04": "sess_pick",
    "S10.05": "sess_edit_ok",
    "S11.01": "slot",
    "S11.02": "slot_plan",
    "S11.03": "slot_fact",
    "S11.04": "slot_utter",
    "S11.05": "slot_ok",
    "S11.06": "slot_video",
    "S11.07": "slot_vid_up",
    "S11.08": "slot_vid_ok",
    "S11.09": "slot_how",
    "S12.01": "sess_all",
    "S12.02": "sess_sum",
    "S12.03": "sess_fin",
    "S12.04": "sess_dev",
    "S12.05": "sess_fin_ok",
    "S13.02": "sess_gen_ok",
    "S14.01": "nutr",
    "S14.02": "nutr_gen",
    "S14.03": "nutr_show",
    "S14.04": "nutr_noprog",
    "S14.05": "nutr_check",
    "S15.01": "hist",
    "S15.02": "hist_sess",
    "S15.03": "hist_wt",
    "S15.04": "hist_meas",
    "S15.05": "hist_one",
    "S15.06": "hist_card",
    "S15.07": "hist_vid",
    "S15.08": "hist_vid_ok",
}

CODE_RE = re.compile(r"^(C\d+|TG-TEXT|TG-VIDEO|TG-VOICE|[a-z][a-z0-9_]{1,31})$")
HANDLER_RE = re.compile(r"`([A-Z][A-Za-z]+(?:Command|Query))`")
CALLBACK_RE = re.compile(r"callback `([^`]+)`")
ROW_RE = re.compile(r"^\| `?(S\d+\.\d+|C\d+|TG-TEXT|TG-VIDEO|TG-VOICE)`? \|")

ANNOTATIONS = {"TG-TEXT", "TG-VOICE", "C1", "C2"}
ENTRIES = ANNOTATIONS | {"start", "wt_tick"}

DEFERRED_DIAGRAM_CODES: set[str] = set()

JOURNEYS: dict[str, list[str]] = {
    "new_user_to_home_via_agent": [
        "start",
        "onb_check",
        "onb_sex",
        "onb_birth",
        "onb_height",
        "onb_weight",
        "onb_exp",
        "onb_freq",
        "onb_days",
        "onb_equip",
        "onb_limits",
        "onb_tz",
        "onb_goal",
        "prog",
        "prog_setup",
        "prog_gen",
        "prog_draft",
        "prog_ok",
        "prog_saved",
        "home",
    ],
    "choose_type_then_text": [
        "prog_setup",
        "prog_type",
        "prog_text",
        "prog_utter",
        "prog_unres",
        "prog_match",
        "prog_pick",
        "prog_unres",
    ],
    "unresolved_approve_blocked": ["prog_draft", "prog_ok", "prog_block", "prog_match"],
    "discard_draft": ["prog_draft", "draft_cancel", "prog"],
    "edit_active_program": ["prog", "prog_edit", "prog_utter"],
    "open_pending_draft": ["prog", "prog_draft"],
    "agent_after_type": ["prog_type", "prog_gen"],
    "resolved_back_to_draft": ["prog_unres", "prog_draft"],
    "session_as_planned_then_finish": [
        "home",
        "sess",
        "sess_state",
        "sess_tmpl",
        "sess_plan",
        "sess_card",
        "slot",
        "slot_plan",
        "sess_card",
        "sess_all",
        "sess_sum",
        "sess_fin",
        "home",
    ],
    "session_repeat_overwrite": [
        "sess_tmpl",
        "sess_plan",
        "sess_plan_ask",
        "sess_plan_repeat",
        "sess_card",
    ],
    "slot_free_text": ["slot", "slot_fact", "slot_utter", "slot_ok", "sess_card"],
    "complete_with_deviation": ["sess_sum", "sess_dev", "sess_fin_ok", "home"],
    "generate_next_session": ["sess_tmpl", "sess_tmpl_edit", "sess_gen", "sess_gen_ok", "sess_card"],
    "edit_template_before_start": ["sess_tmpl", "sess_tmpl_edit", "sess_tmpl_edit_text", "sess_card"],
    "edit_session": ["sess_card", "sess_edit", "sess_utter", "sess_match", "sess_pick", "sess_edit_ok", "sess_card"],
    "edit_session_already_resolved": ["sess_utter", "sess_edit_ok"],
    "no_program_from_today": ["sess_state", "sess_noprog", "prog"],
    "rest_day_to_history": ["sess_state", "sess_rest", "hist", "hist_sess"],
    "history_weight_tab": ["hist", "hist_wt"],
    "history_measures_tab": ["hist", "hist_meas"],
    "weight_manual": ["home", "wt_menu", "wt_log", "wt_save"],
    "weight_history": ["wt_menu", "wt_hist"],
    "weight_schedule": ["wt_menu", "wt_remind"],
    "weight_reminder": ["wt_tick", "wt_ask", "wt_save"],
    "measure_fixed": ["home", "meas_menu", "meas_site", "meas_value", "meas_menu"],
    "measure_custom": ["meas_menu", "meas_custom", "meas_value"],
    "measure_history": ["meas_site", "meas_hist"],
    "nutrition_cached": ["home", "nutr", "nutr_check", "nutr_show"],
    "nutrition_generate": ["nutr_check", "nutr_gen", "nutr_show"],
    "nutrition_without_program": ["nutr", "nutr_noprog", "prog"],
    "change_goal": ["home", "profile", "prof_edit", "prof_goal", "home"],
    "change_field": ["prof_edit", "prof_value", "home"],
    "resume_in_progress": ["sess_state", "sess_card"],
    "technique_upload": ["slot", "slot_video", "TG-VIDEO", "slot_vid_up", "sess_card"],
    "technique_upload_after_custom": [
        "slot",
        "slot_fact",
        "slot_utter",
        "slot_ok",
        "slot_video",
        "TG-VIDEO",
        "slot_vid_up",
    ],
    "technique_bad_file": ["slot_video", "TG-VIDEO", "slot_vid_ok"],
    "technique_how_to": ["slot", "slot_how"],
    "history_open_session": ["hist", "hist_sess", "hist_one", "hist_card"],
    "history_watch": ["hist_card", "hist_vid"],
}


def to_ux(plan_code: str) -> str:
    if plan_code in ANNOTATIONS or plan_code.startswith("C"):
        return plan_code
    return PLAN_TO_UX.get(plan_code, plan_code)


def rewrite_plan_callback(template: str) -> str:
    """Map plan callback prefixes like s8.05:… to idiomatic UX ids."""

    def repl(match: re.Match[str]) -> str:
        old = match.group(0)
        key = old.upper() if old.startswith("s") else old
        # normalize s8.05 -> S8.05
        if re.fullmatch(r"s\d+\.\d+", old):
            key = f"S{old[1:]}"
        return PLAN_TO_UX.get(key, old)

    return re.sub(r"\bs\d+\.\d+\b", repl, template)


def registry_rows(plan_text: str) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for line in plan_text.splitlines():
        if not ROW_RE.match(line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 4:
            raise SystemExit(f"registry row has {len(cells)} cells: {line}")
        code = cells[0].strip().strip("`")
        rows.append((code, cells[1], cells[2], cells[3]))
    return rows


def cqrs_section_handlers(plan_text: str) -> set[str]:
    start = plan_text.find("## CQRS-обработчики")
    end = plan_text.find("## Этапы и роли разработчиков")
    if start < 0 or end < 0:
        raise SystemExit("CQRS section markers missing")
    return set(HANDLER_RE.findall(plan_text[start:end]))


def diagram_graph(path: Path) -> tuple[dict[str, set[str]], set[str], set[str]]:
    tree = ET.parse(path)
    outgoing: dict[str, set[str]] = {}
    diamonds: set[str] = set()
    present: set[str] = set()
    for diagram in tree.getroot().findall("diagram"):
        cells: dict[str, ET.Element] = {}
        for cell in diagram.iter("mxCell"):
            cell_id = cell.get("id")
            if cell_id:
                cells[cell_id] = cell
        code_of: dict[str, str] = {}
        for cell_id, cell in cells.items():
            if cell.get("edge") == "1":
                continue
            value = cell.get("value") or ""
            first = value.split("&#xa;")[0].split("\n")[0].strip()
            if CODE_RE.match(first):
                code_of[cell_id] = first
                present.add(first)
                style = cell.get("style") or ""
                if "rhombus" in style:
                    diamonds.add(first)
        for cell in cells.values():
            if cell.get("edge") != "1":
                continue
            source = code_of.get(cell.get("source") or "")
            target = code_of.get(cell.get("target") or "")
            if not source or not target:
                raise SystemExit(f"edge {cell.get('id')} is not bound to step codes")
            outgoing.setdefault(source, set()).add(target)
    return outgoing, diamonds, present


def callback_byte_length(template: str) -> int:
    sample = template
    sample = sample.replace("{day_position}", "12")
    sample = sample.replace("{slot_position}", "12")
    sample = sample.replace("{position}", "12")
    sample = sample.replace("{offset}", "10")
    sample = sample.replace("{session_id}", "123e4567-e89b-12d3-a456-426614174000")
    sample = sample.replace("{slot_id}", "123e4567-e89b-12d3-a456-426614174000")
    sample = sample.replace("{exercise_id}", "123e4567-e89b-12d3-a456-426614174000")
    sample = sample.replace("{payload}", "male")
    return len(sample.encode("utf-8"))


def main() -> int:
    errors: list[str] = []
    plan_text = PLAN.read_text()
    rows = registry_rows(plan_text)
    codes = [row[0] for row in rows]
    if len(codes) != len(set(codes)):
        errors.append("duplicate code in registry")
    registry = {row[0]: row for row in rows}

    registry_end = plan_text.find("## Спецформат, контракт JSON")
    handlers_in_rows = set(HANDLER_RE.findall(plan_text[plan_text.find("## Коды шагов"): registry_end]))
    for handler in sorted(cqrs_section_handlers(plan_text)):
        if handler not in handlers_in_rows:
            errors.append(f"CQRS handler {handler} has no registry row")

    outgoing, diamonds, present = diagram_graph(DRAWIO)
    ux_codes = {to_ux(code) for code in codes}
    required_on_diagram = ux_codes - DEFERRED_DIAGRAM_CODES
    missing_on_diagram = sorted(required_on_diagram - present)
    extra_on_diagram = sorted(present - ux_codes - ANNOTATIONS)
    if missing_on_diagram:
        errors.append("missing on diagram: " + ", ".join(missing_on_diagram))
    if extra_on_diagram:
        errors.append("diagram codes absent from registry: " + ", ".join(extra_on_diagram))

    incoming: dict[str, int] = {code: 0 for code in present}
    for targets in outgoing.values():
        for target in targets:
            incoming[target] = incoming.get(target, 0) + 1
    for code in sorted(present - ENTRIES):
        if incoming.get(code, 0) == 0:
            errors.append(f"{code} is not reachable")

    for code in sorted(diamonds):
        if len(outgoing.get(code, ())) < 2:
            errors.append(f"decision {code} has fewer than 2 exits")

    for name, path in JOURNEYS.items():
        for left, right in zip(path, path[1:]):
            if right not in outgoing.get(left, ()):
                errors.append(f"journey {name}: no edge {left} -> {right}")

    for code, _step, telegram, _cqrs in rows:
        match = CALLBACK_RE.search(telegram)
        if not match:
            continue
        # Validate both plan-era and idiomatic rewritten callback lengths.
        for label, template in (
            (code, match.group(1)),
            (to_ux(code), rewrite_plan_callback(match.group(1))),
        ):
            size = callback_byte_length(template)
            if size > 64:
                errors.append(f"{label} callback is {size} bytes ({template})")

    for plan_code in ("S8.05", "S10.04"):
        telegram = registry[plan_code][2]
        if "{exercise_id}" not in telegram:
            errors.append(f"{to_ux(plan_code)} must carry exercise_id in callback")
    if "{day_position}" not in registry["S8.05"][2] or "{slot_position}" not in registry["S8.05"][2]:
        errors.append("prog_pick must carry day_position and slot_position in callback")

    birth_year_label = registry["S1.04"][1]
    if "Год рождения" not in birth_year_label:
        errors.append("onb_birth must be labelled as year of birth")

    if errors:
        print("UX binding check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"registry steps: {len(codes)}")
    print(f"diagram steps: {len(present)}")
    print(f"journeys: {len(JOURNEYS)}")
    print("callback payloads within 64 bytes")
    print("UX binding check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
