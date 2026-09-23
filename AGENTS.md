# Agent notes for ai-fitness-tgbot

- Skill `/graphify` lives at `.agents/skills/graphify/SKILL.md`. There is no `.cursor/commands/graphify.toml`.
- Do not run `graphify install --platform cursor`.
- Graph output directory is `graphify-out/` (gitignored). Rule: `.cursor/rules/graphify.mdc`.
- Layers: `presentation` → `service` → `domain`; `infrastructure` implements ports from `service`.

# Timeweb Cloud Skills — Router

Skills for managing Timeweb Cloud infrastructure through the Timeweb Cloud MCP server
(`timeweb-cloud`, hosted at `https://api.timeweb.cloud/api/v1/mcp/search`).

## Which skill to read

- **Cloud server (VDS):** create, reboot, backups, snapshots, disks, PTR, SSH keys, monitoring → `.cursor/skills/timeweb-servers/SKILL.md`
- **Billing:** balance, charges, catalog prices → `.cursor/skills/timeweb-billing/SKILL.md`
- **AI agents / RAG / models / token packages** → `.cursor/skills/timeweb-ai/SKILL.md`
- **Managed Kubernetes** → `.cursor/skills/timeweb-kubernetes/SKILL.md`
- **Managed databases** → `.cursor/skills/timeweb-databases/SKILL.md`
- **S3 object storage** → `.cursor/skills/timeweb-s3/SKILL.md`
- **Account:** blocks, login restrictions, notifications, projects → `.cursor/skills/timeweb-account/SKILL.md`
- **Domains / DNS / mailboxes** → `.cursor/skills/timeweb-domains/SKILL.md`
- **Network:** IPs, balancers, VPC, NAT, network disks → `.cursor/skills/timeweb-network/SKILL.md`
- **App Platform / Container Registry** → `.cursor/skills/timeweb-apps/SKILL.md`

## Rules that apply to every Timeweb skill

1. Actions go through MCP: `search_tools` → `get_tool_definition` → `execute_tool`. Never invent a `tool_id`.
2. `[WRITE]` needs two-step confirmation with `confirm_token` after explicit user yes.
3. `[BILLABLE]` charges immediately — fetch live price, state cost, get explicit yes. Never quote prices from memory.
4. If `search_tools` returns `not_exposed`, quote the reason, point to https://timeweb.cloud, do not work around.
5. Use only MCP or the documented public API. Answer in the user's language; search tools with English keywords.
