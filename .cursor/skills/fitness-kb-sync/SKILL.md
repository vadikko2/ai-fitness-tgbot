---
name: fitness-kb-sync
description: >-
  Sync the fitness bot exercise catalog (data/exercises.jsonl) into a Timeweb
  Cloud AI Knowledge Base and optionally link it to the Fitness Bot agent. Use
  when the user says "залей каталог в базу знаний", "синхронизируй KB",
  "обнови knowledge base упражнений", or asks to put exercises.jsonl into the
  Timeweb agent RAG. Do NOT treat KB sync as a substitute for catalog_json in
  program prompts — the bot already injects the catalog on every LLM call.
---

# Sync exercise catalog → Timeweb Knowledge Base

## When this helps / when it does not

The Telegram bot already sends a compact `catalog_json` (id, name, muscles) inside
`program_planner` / editor prompts. That is the source of truth for `exercise_id`
UUIDs. A Timeweb KB does **not** replace that path.

Use a KB only if you want RAG for **panel / widget / playground** chats with the
same agent, or an extra semantic lookup. Linking a KB **adds retrieved chunks to
every agent request** (more input tokens). Prefer a lean catalog dump, not the
full jsonl with video metadata.

## Source file

- Primary: `data/exercises.jsonl` (one JSON object per line).
- For KB upload, build **compact** documents: `id`, `name`, `primary_muscles`,
  `secondary_muscles`, optional `equipment`. Drop video URLs and long prose unless
  the user explicitly wants them (they burn indexing tokens).

## MCP flow (Timeweb Cloud)

All actions: `search_tools` → `get_tool_definition` → `execute_tool`.
`[WRITE]` / `[BILLABLE]` need the two-step `confirm_token` after an explicit user yes.
Live package prices: `list_knowledge_base_token_packages` — never invent prices.

1. `list_ai_agents` / `list_knowledge_bases` — find Fitness Bot agent and any existing
   exercise KB (reuse rather than duplicating).
2. If no KB: quote package price → `create_knowledge_base` (confirm) → note `kb_id`.
3. Build compact text from `data/exercises.jsonl` (script below or inline Python).
4. Split into chunks of **≤ 200_000 characters** each (MCP
   `upload_knowledge_base_document` hard cap is 256k; leave headroom).
5. For each chunk: `upload_knowledge_base_document` with
   `filename` like `exercises_part01.json` / `.md`, `content` = chunk text.
6. Wait for indexing: `list_knowledge_base_documents` until statuses are ready.
7. Optional: `link_knowledge_base_to_agent` for agent_id of Fitness Bot.
8. Remind: bot runtime still needs correct `exercise_id` UUIDs from `catalog_json`;
   KB does not fix invented UUIDs by itself.

## Compact export recipe

Run from repo root:

```bash
python3 - <<'PY'
import json
from pathlib import Path

src = Path("data/exercises.jsonl")
out_dir = Path("wip/kb_exercises")
out_dir.mkdir(parents=True, exist_ok=True)
lines = []
for raw in src.read_text(encoding="utf-8").splitlines():
    if not raw.strip():
        continue
    row = json.loads(raw)
    lines.append(
        json.dumps(
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "primary_muscles": row.get("primary_muscles") or row.get("primary") or [],
                "secondary_muscles": row.get("secondary_muscles") or row.get("secondary") or [],
                "equipment": row.get("equipment"),
            },
            ensure_ascii=False,
        )
    )
blob = "\n".join(lines)
limit = 200_000
parts = [blob[i : i + limit] for i in range(0, len(blob), limit)] or [""]
for i, part in enumerate(parts, start=1):
    path = out_dir / f"exercises_part{i:02d}.jsonl"
    path.write_text(part, encoding="utf-8")
    print(path, "chars", len(part))
print("parts", len(parts), "total_chars", len(blob))
PY
```

Then upload each part's **file contents** via
`upload_knowledge_base_document` (`content` = text, not a filesystem path).
MCP cannot upload binary user files; inline text only.

## Anti-patterns

- NEVER claim KB sync alone will make program proposals pick correct UUIDs.
- NEVER upload the raw 700KB+ jsonl as one document — split and compact first.
- NEVER buy a KB token package without showing live price and current
  `remaining_tokens`.
- NEVER link five huge KBs to the production agent "just in case" — token burn.
