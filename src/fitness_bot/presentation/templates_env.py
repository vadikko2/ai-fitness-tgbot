from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def create_jinja_env() -> Environment:
    # Telegram messages use parse_mode=HTML; templates contain real <b>/<code> markup.
    # Autoescape would turn tags into &lt;b&gt; and Telegram would show them literally.
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
