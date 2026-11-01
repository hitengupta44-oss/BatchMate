# Team protocol for coding agents (Meko build datapack)

This repo is built by several teammates' coding agents that share one Meko datapack:
**`batchmate-build`** (rename here if your team's datapack is named differently).

## Every task

1. **Before starting:** `context_search` (or `memory_search`) in `batchmate-build` for the task's topic.
   Follow any promoted decision you find; if you disagree, say so to your teammate instead of silently diverging.
2. **When the task ends:** `memory_add` a 1–3 sentence summary to `batchmate-build`: what changed, which
   files, and any decision it implies. Start it with the teammate's name, e.g. `Nishant: …`.
3. **Promote decisions others must follow** with `memory_promote` (only promoted rows reach the rest of the
   team). Examples: API contracts, env var names, datapack naming, schemas, gotchas.
   Show the teammate the exact memory and get a yes before promoting; promotion is one-way.

## Never

- Never put API keys, tokens, `.env` contents, or personal data in the build datapack.
- Never read or write the product's datapacks (`batchmate-student-*`, `batchmate-company-*`,
  `batchmate-batch-*`). They belong to the running app; the app never reads `batchmate-build`.

## Decisions worth promoting from day one

- Memory lives behind `MemoryService` (`backend/batchmate/memory/base.py`); agents only call `get_memory()`.
- `MEMORY_BACKEND=meko` in production: recall comes only from Meko `memory_search`; Supabase is the ledger
  for ids/status/metadata. Nothing is shown as context unless Meko returned it.
- Product datapacks: one per scope, `batchmate-<scope>`; raw senior reports in `batchmate-company-<name>-reports`.
- Promotion of a pattern needs a `coordinator-*` user; the Steward agent never approves.
- Frontend calls the backend only through `/api/*` (Vercel rewrite to the HF Space).
