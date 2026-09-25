"""Idempotent upsert of exercise catalog rows from JSONL into Postgres."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import Connection, text

from fitness_bot.domain.catalog.normalize import normalize_exercise_name


def load_catalog_jsonl_records(jsonl_path: Path) -> list[dict]:
    if not jsonl_path.is_file():
        raise FileNotFoundError(f"catalog JSONL not found: {jsonl_path}")
    records: list[dict] = []
    for line_no, line in enumerate(jsonl_path.read_text(encoding="utf-8").splitlines(), start=1):
        text_line = line.strip()
        if not text_line:
            continue
        raw = json.loads(text_line)
        if not isinstance(raw, dict):
            raise ValueError(f"JSONL object expected at line {line_no}")
        name = str(raw.get("name") or "").strip()
        if not name:
            raise ValueError(f"missing name at line {line_no}")
        records.append(raw)
    return records


def seed_exercise_catalog(conn: Connection, jsonl_path: Path) -> int:
    """Upsert all JSONL exercises (muscles/videos replaced per exercise). Returns row count."""
    records = load_catalog_jsonl_records(jsonl_path)
    for raw in records:
        name = str(raw["name"]).strip()
        name_normalized = normalize_exercise_name(name)
        technique = str(raw.get("technique") or "")
        places = [str(p).strip() for p in (raw.get("places") or ["gym"]) if str(p).strip()]
        if not places:
            places = ["gym"]
        primary = [str(m).strip() for m in (raw.get("primary_muscles") or []) if str(m).strip()]
        secondary = [str(m).strip() for m in (raw.get("secondary_muscles") or []) if str(m).strip()]
        videos = raw.get("videos") or []

        row = conn.execute(
            text(
                """
                insert into exercises (name, name_normalized, technique, places)
                values (:name, :name_normalized, :technique, :places)
                on conflict (name_normalized) do update
                set name = excluded.name,
                    technique = excluded.technique,
                    places = excluded.places
                returning id
                """,
            ),
            {
                "name": name,
                "name_normalized": name_normalized,
                "technique": technique,
                "places": places,
            },
        ).one()
        exercise_id = row[0]

        conn.execute(
            text("delete from exercise_muscles where exercise_id = :exercise_id"),
            {"exercise_id": exercise_id},
        )
        conn.execute(
            text("delete from exercise_videos where exercise_id = :exercise_id"),
            {"exercise_id": exercise_id},
        )

        for muscle in primary:
            conn.execute(
                text(
                    """
                    insert into exercise_muscles (exercise_id, muscle, role)
                    values (:exercise_id, :muscle, 'primary')
                    """,
                ),
                {"exercise_id": exercise_id, "muscle": muscle},
            )
        for muscle in secondary:
            conn.execute(
                text(
                    """
                    insert into exercise_muscles (exercise_id, muscle, role)
                    values (:exercise_id, :muscle, 'secondary')
                    """,
                ),
                {"exercise_id": exercise_id, "muscle": muscle},
            )

        position = 0
        seen_urls: set[tuple[str, str]] = set()
        for video in videos:
            platform = str(video.get("platform") or "")
            url = str(video.get("url") or "").strip()
            title = str(video.get("title") or "")
            if platform not in ("youtube", "rutube") or not url:
                continue
            key = (platform, url)
            if key in seen_urls:
                continue
            seen_urls.add(key)
            position += 1
            conn.execute(
                text(
                    """
                    insert into exercise_videos (exercise_id, platform, url, title, position)
                    values (:exercise_id, :platform, :url, :title, :position)
                    """,
                ),
                {
                    "exercise_id": exercise_id,
                    "platform": platform,
                    "url": url,
                    "title": title,
                    "position": position,
                },
            )
    return len(records)
