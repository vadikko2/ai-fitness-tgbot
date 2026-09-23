from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "fitness_bot"

FORBIDDEN: dict[str, set[str]] = {
    "domain": {
        "fitness_bot.service",
        "fitness_bot.infrastructure",
        "fitness_bot.presentation",
        "aiogram",
        "sqlalchemy",
        "alembic",
    },
    "service": {
        "fitness_bot.infrastructure",
        "fitness_bot.presentation",
        "aiogram",
        "sqlalchemy",
        "alembic",
    },
    "presentation": {
        "fitness_bot.infrastructure.db",
        "sqlalchemy",
        "alembic",
    },
}


def _imports_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                found.add(top)
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.add(node.module.split(".")[0])
    return found


def test_layer_import_direction() -> None:
    violations: list[str] = []
    for layer, banned in FORBIDDEN.items():
        layer_root = ROOT / layer
        if not layer_root.exists():
            continue
        for path in layer_root.rglob("*.py"):
            # CLI entrypoints are composition roots (may wire infrastructure).
            if layer == "presentation" and "cli" in path.parts:
                continue
            imported = _imports_in(path)
            for module in banned:
                if any(item == module or item.startswith(module + ".") for item in imported):
                    violations.append(f"{path.relative_to(ROOT.parent.parent)} imports {module}")
    assert not violations, "\n".join(violations)
