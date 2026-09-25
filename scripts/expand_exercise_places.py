#!/usr/bin/env python3
"""One-shot: tag places on existing exercises, append new ones, fetch Rutube videos."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fitness_bot.domain.catalog.places import normalize_exercise_places  # noqa: E402
from fitness_bot.infrastructure.adapters.rutube_search import RutubeApiSearch  # noqa: E402
from fitness_bot.service.catalog.jsonl import (  # noqa: E402
    ExerciseJsonlRecord,
    ExerciseVideoLine,
    load_exercises_jsonl,
    upsert_exercise,
    write_exercises_jsonl,
)
from fitness_bot.service.catalog.llm_parse import dedupe_videos, filter_relevant_video_hits  # noqa: E402
from fitness_bot.shared.paths import EXERCISES_JSONL_PATH  # noqa: E402

GYM_ONLY = re.compile(
    r"(смит|smith|кроссовер|хаммер|гравитрон|pec.?deck|хак-?присед|жим ногами|"
    r"разгибани[ея].*тренаж|сгибани[ея].*тренаж|тренажёр|тренажер|"
    r"кабельн|блочн|тяга верхнего блока|тяга нижнего блока|"
    r"беговой дорожк|степпер|эллипс|гребн.*тренаж|велотренаж|"
    r"жим.*в тренаж|сведение.*в тренаж|разведение.*в тренаж)",
    re.I,
)
PORTABLE_LOAD = re.compile(r"(гантел|гир|резин|лент|эспандер|скакал|trx|кольц)", re.I)
BARBELL = re.compile(r"(штан|гриф|паддингтон|румынская тяга со штан|становая)", re.I)
BODYWEIGHT = re.compile(
    r"(отжиман|подтягив|планка|берпи|прыж|выпад(?!.*гантел)|присед.*без|"
    r"своим весом|воздушн|скамье|скамейк|угол в упоре|l-sit|"
    r"австралийск|негативн|изометрич|алмазн|"
    r"бег с|ходьба на носках|прыжки|берпи|альпинист|берд.?дог|bird.?dog|"
    r"супермен|ягодичн.*мост|wall sit|у стены)",
    re.I,
)
MOBILITY = re.compile(r"(мобилити|растяж|cars|кошка.?корова|поза голубя|дыхание)", re.I)
OUTDOOR_FRIENDLY = re.compile(
    r"(турник|брусь|скакал|бег|спринт|ступен|улиц|прыж|берпи|планка|"
    r"отжиман|подтягив|выпад|гир|резин|мобилити|растяж)",
    re.I,
)


def infer_places(name: str) -> list[str]:
    n = name.strip()
    if GYM_ONLY.search(n):
        return ["gym"]
    if MOBILITY.search(n):
        return ["gym", "home", "outdoor"]
    if PORTABLE_LOAD.search(n):
        places = ["gym", "home"]
        if OUTDOOR_FRIENDLY.search(n) or re.search(r"гир|резин|скакал", n, re.I):
            places.append("outdoor")
        return list(normalize_exercise_places(places))
    if BARBELL.search(n) and not PORTABLE_LOAD.search(n):
        # Barbell usually gym; allow home if user has a bar but default gym-only for machines-adjacent
        if re.search(r"(жим штанги лёжа|приседани[ея] со штан|становая|тяга штанги)", n, re.I):
            return ["gym", "home"]
        return ["gym"]
    if BODYWEIGHT.search(n) or re.search(
        r"^(планка|отжимания|подтягивания|выпады|приседания(?!.*штан)|берпи)",
        n,
        re.I,
    ):
        return ["gym", "home", "outdoor"]
    # Default: gym equipment / unknown → gym only (safer than leaking into home plans)
    if re.search(r"(гантел)", n, re.I):
        return ["gym", "home"]
    return ["gym"]


NEW_EXERCISES: list[dict] = [
    # Kettlebell
    {
        "name": "Гоблет-приседания с гирей",
        "primary_muscles": ["квадрицепс"],
        "secondary_muscles": ["ягодицы", "пресс"],
        "places": ["gym", "home", "outdoor"],
        "technique": "Держите гирю у груди ручками вверх или за рога, локти вниз. Ноги чуть шире плеч, носки слегка наружу. Садитесь вниз, сохраняя корпус вертикальным и пятки на полу, колени вдоль носков. Встаньте, выдох на подъёме, вдох на опускании. Держите пресс и не округляйте поясницу. Частая ошибка — завал коленей внутрь и отрыв пяток.",
        "video_queries": ["гоблет приседания с гирей техника", "goblet squat kettlebell"],
    },
    {
        "name": "Подъём гири на грудь (clean)",
        "primary_muscles": ["трапеции"],
        "secondary_muscles": ["ягодицы", "бицепс бедра", "пресс"],
        "places": ["gym", "home", "outdoor"],
        "technique": "Гиря между стоп, хват одной рукой. Сделайте мах назад между ног и резко разогните бёдра, проведя гирю по дуге к груди в стойку на предплечье. Локоть прижат, кисть нейтральна. Опустите мягко обратно. Выдох на подъёме. Не тяните рукой и не ударяйте предплечье — работайте бёдрами.",
        "video_queries": ["подъём гири на грудь техника", "kettlebell clean technique"],
    },
    {
        "name": "Высокая тяга гири",
        "primary_muscles": ["трапеции"],
        "secondary_muscles": ["плечи", "ягодицы"],
        "places": ["gym", "home", "outdoor"],
        "technique": "Гиря в двух руках, стойка на ширине плеч. Сделайте короткий мах и тяните локти вверх до уровня груди, гиря близко к телу. Опустите под контролем. Выдох на тяге. Не поднимайте плечи к ушам и не горбитесь.",
        "video_queries": ["высокая тяга гири техника", "kettlebell high pull"],
    },
    {
        "name": "Жим гири лёжа на полу",
        "primary_muscles": ["грудь"],
        "secondary_muscles": ["трицепс", "плечи"],
        "places": ["gym", "home"],
        "technique": "Лягте на пол, гиря в одной руке над плечом, локоть на полу. Выжмите гирю вверх до выпрямления руки, лопатка стабильна. Опустите до касания локтем пола. Выдох на жиме. Не прогибайте поясницу и не разворачивайте корпус.",
        "video_queries": ["жим гири лёжа на полу", "kettlebell floor press"],
    },
    {
        "name": "Вращение гири вокруг головы (halo)",
        "primary_muscles": ["плечи"],
        "secondary_muscles": ["пресс", "трапеции"],
        "places": ["gym", "home", "outdoor"],
        "technique": "Держите гирю за рога у груди. Медленно обводите её вокруг головы по кругу, сохраняя корпус неподвижным и пресс напряжённым. Меняйте направление. Дышите ровно. Не запрокидывайте голову и не раскачивайте таз.",
        "video_queries": ["halo с гирей техника", "kettlebell halo"],
    },
    {
        "name": "Выпады с гирей у груди",
        "primary_muscles": ["квадрицепс"],
        "secondary_muscles": ["ягодицы", "пресс"],
        "places": ["gym", "home", "outdoor"],
        "technique": "Гиря у груди в гоблет-хвате. Шагните вперёд или назад в выпад, оба колена около 90 градусов, передняя пятка на полу. Вернитесь и смените ногу. Выдох на подъёме. Не заваливайте колено внутрь и не наклоняйтесь сильно вперёд.",
        "video_queries": ["выпады с гирей техника", "kettlebell goblet lunge"],
    },
    {
        "name": "Тяга гири в упоре (renegade row)",
        "primary_muscles": ["широчайшие"],
        "secondary_muscles": ["пресс", "трапеции"],
        "places": ["gym", "home"],
        "technique": "Упор лёжа на двух гирях или одной гире и ладони. Подтяните гирю к поясу, сохраняя таз ровным и пресс жёстким. Опустите и повторите с другой стороны. Выдох на тяге. Не крутите корпус и не провисайте в пояснице.",
        "video_queries": ["renegade row гиря техника", "тяга гири в упоре"],
    },
    {
        "name": "Приседания с гирей над головой",
        "primary_muscles": ["квадрицепс"],
        "secondary_muscles": ["ягодицы", "плечи", "пресс"],
        "places": ["gym", "home", "outdoor"],
        "technique": "Выжмите гирю одной рукой над головой, локоть выпрямлен, лопатка активна. Садитесь в присед, удерживая гирю стабильно над головой, взгляд вперёд. Встаньте. Выдох на подъёме. Начинайте с лёгкой гири; не допускайте завала плеча.",
        "video_queries": ["приседания с гирей над головой", "overhead kettlebell squat"],
    },
    # Bands
    {
        "name": "Тяга резины к лицу (face pull)",
        "primary_muscles": ["задние дельты"],
        "secondary_muscles": ["трапеции", "ротаторы плеча"],
        "places": ["gym", "home"],
        "technique": "Закрепите резину на уровне лица. Тяните к лицу, разводя руки и вращая наружу так, чтобы кисти оказались у висков. Сожмите лопатки, выдох на тяге. Контролируйте возврат. Не поднимайте плечи и не прогибайтесь в пояснице.",
        "video_queries": ["face pull с резиной техника", "тяга резины к лицу"],
    },
    {
        "name": "Жим резины от груди стоя",
        "primary_muscles": ["грудь"],
        "secondary_muscles": ["трицепс", "плечи"],
        "places": ["gym", "home", "outdoor"],
        "technique": "Резину за спиной или закреплённой сзади на уровне груди. Выжмите руки вперёд до почти полного выпрямления, не блокируя локти резко. Верните медленно. Выдох на жиме. Держите рёбра вниз, не раскачивайтесь.",
        "video_queries": ["жим резины от груди стоя", "band chest press"],
    },
    {
        "name": "Тяга резины к поясу стоя",
        "primary_muscles": ["широчайшие"],
        "secondary_muscles": ["бицепс", "трапеции"],
        "places": ["gym", "home", "outdoor"],
        "technique": "Закрепите резину впереди на уровне пояса. Шагните назад до натяжения, тяните рукояти к поясу, сводя лопатки. Выдох на тяге. Корпус чуть наклонён, спина ровная. Не округляйте поясницу и не дёргайте рывком.",
        "video_queries": ["тяга резины к поясу", "band row technique"],
    },
    {
        "name": "Приседания с резиной вокруг бёдер",
        "primary_muscles": ["ягодицы"],
        "secondary_muscles": ["квадрицепс", "приводящие бедра"],
        "places": ["gym", "home", "outdoor"],
        "technique": "Резина чуть выше колен. Ноги на ширине плеч, разведите колени против резины и садитесь назад-вниз. Встаньте, сохраняя натяжение. Выдох на подъёме. Не сводите колени и не отрывайте пятки.",
        "video_queries": ["приседания с резиной на бёдрах", "band squat technique"],
    },
    {
        "name": "Ягодичный мост с резиной",
        "primary_muscles": ["ягодицы"],
        "secondary_muscles": ["бицепс бедра", "пресс"],
        "places": ["gym", "home"],
        "technique": "Лягте на спину, резина над коленями, стопы на полу. Поднимите таз, сжимая ягодицы, колени разведены против резины. Опуститесь без касания пола полностью при желании. Выдох на подъёме. Не прогибайте поясницу чрезмерно.",
        "video_queries": ["ягодичный мост с резиной", "band glute bridge"],
    },
    {
        "name": "Разведение рук с резиной (pull-apart)",
        "primary_muscles": ["задние дельты"],
        "secondary_muscles": ["трапеции"],
        "places": ["gym", "home", "outdoor"],
        "technique": "Держите резину перед собой на уровне груди хватом шире плеч. Разводите руки в стороны, растягивая ленту до касания груди. Медленно верните. Выдох на разведении. Плечи вниз, без прогиба поясницы.",
        "video_queries": ["band pull apart техника", "разведение резины перед собой"],
    },
    {
        "name": "Тяга резины сверху вниз (имитация тяги блока)",
        "primary_muscles": ["широчайшие"],
        "secondary_muscles": ["бицепс", "трапеции"],
        "places": ["gym", "home"],
        "technique": "Закрепите резину высоко над головой. Встаньте или сядьте, тяните вниз к груди или ключицам, локти вниз-назад. Выдох на тяге. Контролируйте подъём рук. Не отклоняйтесь сильно назад и не дёргайте шеей.",
        "video_queries": ["тяга резины сверху вниз", "band lat pulldown"],
    },
    {
        "name": "Разгибание рук с резиной из-за головы",
        "primary_muscles": ["трицепс"],
        "secondary_muscles": [],
        "places": ["gym", "home"],
        "technique": "Резину под ногой или сзади. Руки за головой, локти вверх. Разгибайте предплечья, не разводя локти широко. Выдох на разгибании. Держите плечи стабильными; не выгибайте поясницу.",
        "video_queries": ["французский жим с резиной", "band overhead tricep extension"],
    },
    # Outdoor / bodyweight cardio & recovery
    {
        "name": "Берпи",
        "primary_muscles": ["грудь"],
        "secondary_muscles": ["квадрицепс", "плечи", "пресс"],
        "places": ["gym", "home", "outdoor"],
        "technique": "Из стойки присядьте, руки на пол, прыжком в планку, отжимание по желанию, прыжком к рукам и выпрыгивание вверх. Дышите ритмично. Для новичка уберите прыжок и отжимание. Частая ошибка — провисание поясницы в планке.",
        "video_queries": ["берпи техника выполнения", "burpee technique"],
    },
    {
        "name": "Альпинист (mountain climbers)",
        "primary_muscles": ["пресс"],
        "secondary_muscles": ["плечи", "квадрицепс"],
        "places": ["gym", "home", "outdoor"],
        "technique": "Упор лёжа, тело в прямой линии. Поочерёдно подтягивайте колени к груди в быстром темпе, таз стабилен. Дышите ровно. Не подпрыгивайте тазом вверх и не роняйте поясницу.",
        "video_queries": ["альпинист упражнение техника", "mountain climbers technique"],
    },
    {
        "name": "Выпрыгивания из приседа",
        "primary_muscles": ["квадрицепс"],
        "secondary_muscles": ["ягодицы", "икры"],
        "places": ["gym", "home", "outdoor"],
        "technique": "Присядьте до параллели и взрывным движением выпрыгните вверх, мягко приземлитесь обратно в присед. Выдох на прыжке. Приземляйтесь на всю стопу, колени мягкие. Не блокируйте колени на приземлении.",
        "video_queries": ["выпрыгивания из приседа техника", "jump squat"],
    },
    {
        "name": "Спринты на месте",
        "primary_muscles": ["квадрицепс"],
        "secondary_muscles": ["икры", "ягодицы"],
        "places": ["gym", "home", "outdoor"],
        "technique": "Быстрый бег на месте с высоким подниманием коленей, руки работают в противофазе. Держите корпус вертикально. Дышите активно. Не заваливайтесь назад и не ударьте пятками о пол жёстко.",
        "video_queries": ["бег на месте с высоким коленом", "high knees sprint in place"],
    },
    {
        "name": "Ходьба / бег по ступенькам",
        "primary_muscles": ["ягодицы"],
        "secondary_muscles": ["квадрицепс", "икры"],
        "places": ["outdoor", "gym"],
        "technique": "Поднимайтесь по ступенькам быстрым шагом или лёгким бегом, корпус чуть вперёд, стопа целиком на ступень. Спускайтесь осторожно. Дышите ровно. Не прыгайте вниз и держитесь за перила при необходимости.",
        "video_queries": ["ходьба по ступенькам техника", "stair climb workout"],
    },
    {
        "name": "Ягодичный мост лёжа",
        "primary_muscles": ["ягодицы"],
        "secondary_muscles": ["бицепс бедра", "пресс"],
        "places": ["gym", "home"],
        "technique": "Лягте на спину, стопы на ширине таза. Поднимите таз, сжимая ягодицы, задержитесь на секунду и опуститесь. Выдох на подъёме. Не прогибайте поясницу и не давите за счёт шеи.",
        "video_queries": ["ягодичный мост техника", "glute bridge technique"],
    },
    {
        "name": "Bird dog",
        "primary_muscles": ["пресс"],
        "secondary_muscles": ["разгибатели спины", "ягодицы"],
        "places": ["gym", "home", "outdoor"],
        "technique": "На четвереньках вытяните противоположные руку и ногу параллельно полу, удерживая таз ровным. Вернитесь и смените сторону. Выдох на вытяжении. Двигайтесь медленно; не провисайте в пояснице.",
        "video_queries": ["bird dog техника", "берд дог упражнение"],
    },
    {
        "name": "Супермен лёжа",
        "primary_muscles": ["разгибатели спины"],
        "secondary_muscles": ["ягодицы", "плечи"],
        "places": ["gym", "home"],
        "technique": "Лягте на живот, руки вперёд. Одновременно оторвите грудь и бёдра от пола, сожмите ягодицы, задержитесь и опуститесь. Выдох на подъёме. Не запрокидывайте голову и не делайте рывков.",
        "video_queries": ["супермен упражнение техника", "superman exercise back"],
    },
    {
        "name": "Приседания у стены (wall sit)",
        "primary_muscles": ["квадрицепс"],
        "secondary_muscles": ["ягодицы"],
        "places": ["gym", "home", "outdoor"],
        "technique": "Спиной к стене спуститесь до угла 90 градусов в коленях, бёдра параллельны полу. Удерживайте позицию, дышите ровно. Колени над стопами. Не задерживайте дыхание и не съезжайте ниже комфортного угла при боли.",
        "video_queries": ["приседания у стены изометрия", "wall sit technique"],
    },
    {
        "name": "Вис на турнике (dead hang)",
        "primary_muscles": ["предплечья"],
        "secondary_muscles": ["широчайшие", "плечи"],
        "places": ["gym", "home", "outdoor"],
        "technique": "Повисните на турнике хватом сверху, плечи слегка активны (не провисайте пассивно в ушах), ноги спокойны. Дышите ровно. Удерживайте время. Не раскачивайтесь; при дискомфорте в плечах сократите время.",
        "video_queries": ["вис на турнике техника", "dead hang pull up bar"],
    },
    {
        "name": "Ангелы у стены (wall angels)",
        "primary_muscles": ["задние дельты"],
        "secondary_muscles": ["трапеции", "пресс"],
        "places": ["gym", "home"],
        "technique": "Встаньте спиной к стене, поясница и затылок касаются. Руки в позицию «голки», скользите вверх и вниз, сохраняя контакт локтей и запястий со стеной насколько возможно. Дышите ровно. Не отрывайте поясницу.",
        "video_queries": ["wall angels техника", "ангелы у стены плечи"],
    },
    # Stretching
    {
        "name": "Растяжка грудных у дверного проёма",
        "primary_muscles": ["грудь"],
        "secondary_muscles": ["плечи"],
        "places": ["gym", "home"],
        "technique": "Предплечье на косяке, локоть на уровне плеча. Шагните вперёд, пока не почувствуете растяжение груди. Держите 20–40 секунд, дышите спокойно. Не прогибайте поясницу и не форсируйте боль.",
        "video_queries": ["растяжка грудных у двери", "doorway chest stretch"],
    },
    {
        "name": "Растяжка квадрицепса стоя",
        "primary_muscles": ["квадрицепс"],
        "secondary_muscles": [],
        "places": ["gym", "home", "outdoor"],
        "technique": "Стоя, согните ногу назад и захватите стопу рукой, колени рядом, таз слегка вперёд. Держите баланс, дышите. Смените сторону. Не выгибайте поясницу и не тяните через боль в колене.",
        "video_queries": ["растяжка квадрицепса стоя", "standing quad stretch"],
    },
    {
        "name": "Растяжка задней поверхности бедра сидя",
        "primary_muscles": ["бицепс бедра"],
        "secondary_muscles": ["разгибатели спины"],
        "places": ["gym", "home", "outdoor"],
        "technique": "Сидя, одна нога выпрямлена, другая согнута. Наклонитесь к прямой ноге с прямой спиной до лёгкого натяжения. Держите 20–40 с. Дышите. Не округляйте сильно поясницу рывком.",
        "video_queries": ["растяжка бицепса бедра сидя", "seated hamstring stretch"],
    },
    {
        "name": "Поза ребёнка",
        "primary_muscles": ["разгибатели спины"],
        "secondary_muscles": ["ягодицы", "плечи"],
        "places": ["gym", "home"],
        "technique": "На коленях сядьте на пятки, руки вытяните вперёд, лоб на пол. Расслабьте плечи и дышите животом 30–60 с. Можно развести колени шире. Не форсируйте, если болят колени — подложите опору.",
        "video_queries": ["поза ребёнка йога", "child pose stretch"],
    },
    {
        "name": "Собака мордой вниз",
        "primary_muscles": ["бицепс бедра"],
        "secondary_muscles": ["икры", "плечи", "спина"],
        "places": ["gym", "home", "outdoor"],
        "technique": "Из упора поднимите таз вверх, образуя перевёрнутую V. Пятки тяните к полу, руки давят в опору, шея расслаблена. Дышите ровно 20–40 с. Не округляйте спину сильно; согните колени при жёстких хамстрингах.",
        "video_queries": ["собака мордой вниз техника", "downward dog stretch"],
    },
    {
        "name": "Мировая растяжка (world's greatest stretch)",
        "primary_muscles": ["ягодицы"],
        "secondary_muscles": ["грудной отдел", "сгибатели бедра"],
        "places": ["gym", "home", "outdoor"],
        "technique": "В выпаде положите одноимённую руку внутрь стопы, другую руку откройте вверх с ротацией корпуса. Вернитесь и смените сторону. Дышите на открытии. Двигайтесь контролируемо; не падайте в поясницу.",
        "video_queries": ["worlds greatest stretch", "мировая растяжка выпад"],
    },
    {
        "name": "Растяжка сгибателей бедра в выпаде на месте",
        "primary_muscles": ["сгибатели бедра"],
        "secondary_muscles": ["ягодицы"],
        "places": ["gym", "home", "outdoor"],
        "technique": "В выпаде опустите заднее колено, таз подайте вперёд, корпус вертикален. Ощутите растяжение спереди бедра сзади стоящей ноги. Держите 20–40 с. Дышите. Не прогибайте поясницу чрезмерно.",
        "video_queries": ["растяжка сгибателей бедра в выпаде", "hip flexor stretch lunge"],
    },
    {
        "name": "Растяжка грушевидной сидя (figure-4)",
        "primary_muscles": ["ягодицы"],
        "secondary_muscles": ["приводящие бедра"],
        "places": ["gym", "home"],
        "technique": "Сидя или лёжа, лодыжку одной ноги положите на колено другой (фигура 4). Подтяните опорную ногу к себе до растяжения ягодицы. Держите 20–40 с. Дышите. Не давите на колено через боль.",
        "video_queries": ["растяжка грушевидной figure 4", "piriformis stretch"],
    },
    {
        "name": "Мобилити шеи: медленные круги и наклоны",
        "primary_muscles": ["трапеции"],
        "secondary_muscles": [],
        "places": ["gym", "home", "outdoor"],
        "technique": "Сидя или стоя, медленно наклоняйте голову в стороны и вперёд, затем маленькие круги без резких рывков. Дышите спокойно. Амплитуда комфортная. Не запрокидывайте голову резко назад при головокружении.",
        "video_queries": ["мобилити шеи упражнения", "neck mobility stretch"],
    },
    {
        "name": "Диафрагмальное дыхание лёжа",
        "primary_muscles": ["пресс"],
        "secondary_muscles": [],
        "places": ["gym", "home"],
        "technique": "Лягте на спину, одна рука на живот, другая на грудь. Вдыхайте носом, поднимая живот, выдыхайте ртом медленно. 8–12 циклов. Грудь почти неподвижна. Не задерживайте дыхание до дискомфорта.",
        "video_queries": ["диафрагмальное дыхание техника", "diaphragmatic breathing"],
    },
    {
        "name": "Тень бокса (shadow boxing)",
        "primary_muscles": ["плечи"],
        "secondary_muscles": ["пресс", "ноги"],
        "places": ["gym", "home", "outdoor"],
        "technique": "Лёгкая стойка, перемещения на носках, прямые и боковые удары без полного выпрямления локтей. Держите темп кардио. Дышите на ударе. Не задерживайте дыхание и не бейте «в полную» без разминки плеч.",
        "video_queries": ["тень бокса кардио", "shadow boxing workout"],
    },
    {
        "name": "Боковые выпады с резиной",
        "primary_muscles": ["приводящие бедра"],
        "secondary_muscles": ["ягодицы", "квадрицепс"],
        "places": ["gym", "home", "outdoor"],
        "technique": "Резина над коленями. Широкий шаг в сторону, садясь на опорную ногу, вторая почти прямая. Вернитесь и смените сторону. Выдох на подъёме. Колени следят за носками; не заваливайтесь внутрь.",
        "video_queries": ["боковые выпады с резиной", "lateral lunge band"],
    },
    {
        "name": "Махи гирей двумя руками — лёгкие восстановительные",
        "primary_muscles": ["ягодицы"],
        "secondary_muscles": ["бицепс бедра", "пресс"],
        "places": ["gym", "home", "outdoor"],
        "technique": "Лёгкая гиря, махи до уровня груди без агрессивного темпа. Акцент на дыхании и мягком разгибании бёдер. 8–12 спокойных повторов. Не округляйте спину и не поднимайте выше комфорта плеч.",
        "video_queries": ["лёгкие махи гирей техника", "easy kettlebell swing"],
    },
]


async def fetch_videos(name: str, queries: list[str], search: RutubeApiSearch) -> list[ExerciseVideoLine]:
    hits = []
    for query in queries:
        hits.extend(await search.search(query, limit=3))
        await asyncio.sleep(0.15)
    hits = filter_relevant_video_hits(hits, exercise_name=name)
    return dedupe_videos(hits, limit_per_platform=2)


async def main() -> None:
    store = load_exercises_jsonl(EXERCISES_JSONL_PATH)
    tagged = 0
    for record in list(store.values()):
        places = infer_places(record.name)
        if list(record.places) != places:
            record.places = places
            tagged += 1
        upsert_exercise(store, record)

    search = RutubeApiSearch()
    added = 0
    missing_video = []
    try:
        for item in NEW_EXERCISES:
            name = item["name"]
            from fitness_bot.domain.catalog.normalize import normalize_exercise_name

            key = normalize_exercise_name(name)
            if key in store:
                # refresh places on existing twin
                store[key].places = list(normalize_exercise_places(item["places"]))
                continue
            videos = await fetch_videos(name, item["video_queries"], search)
            if not videos:
                missing_video.append(name)
            record = ExerciseJsonlRecord(
                name=name,
                primary_muscles=item["primary_muscles"],
                secondary_muscles=item["secondary_muscles"],
                technique=item["technique"][:500],
                places=list(normalize_exercise_places(item["places"])),
                videos=videos,
            )
            upsert_exercise(store, record)
            added += 1
            print(f"+ {name} videos={len(videos)}")
    finally:
        await search.aclose()

    write_exercises_jsonl(EXERCISES_JSONL_PATH, store.values())
    # stats
    from collections import Counter

    c = Counter()
    for r in store.values():
        c[tuple(r.places)] += 1
    print("total", len(store), "retagged", tagged, "added", added)
    print("place combos", dict(c))
    if missing_video:
        print("no video:", missing_video)


if __name__ == "__main__":
    asyncio.run(main())
