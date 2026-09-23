from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

PROMPTS_DIR = Path(__file__).resolve().parent


def create_prompt_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(PROMPTS_DIR)),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )


def load_system_prompt() -> str:
    return (PROMPTS_DIR / "system.md").read_text(encoding="utf-8").strip()


def render_prompt(template_name: str, **context: object) -> str:
    return create_prompt_env().get_template(template_name).render(**context).strip()
