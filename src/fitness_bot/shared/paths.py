from __future__ import annotations

from pathlib import Path

# src/fitness_bot/shared/paths.py → repository root
REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"
MUSCLE_GROUPS_PATH = DATA_DIR / "muscle_groups.txt"
EXERCISES_JSONL_PATH = DATA_DIR / "exercises.jsonl"
MEASUREMENT_GUIDES_DIR = DATA_DIR / "measurement_guides"
PROGRESS_POSES_DIR = DATA_DIR / "progress_poses"
