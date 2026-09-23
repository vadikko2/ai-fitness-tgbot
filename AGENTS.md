# Agent notes for ai-fitness-tgbot

- Skill `/graphify` lives at `.agents/skills/graphify/SKILL.md`. There is no `.cursor/commands/graphify.toml`.
- Do not run `graphify install --platform cursor`.
- Graph output directory is `graphify-out/` (gitignored). Rule: `.cursor/rules/graphify.mdc`.
- Layers: `presentation` → `service` → `domain`; `infrastructure` implements ports from `service`.
