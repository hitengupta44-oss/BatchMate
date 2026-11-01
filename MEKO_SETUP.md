# Batchmate × Meko: setup guide

Two separate uses of Meko, never mixed (hackCBS rule):

| | Build time | Run time |
|---|---|---|
| Who uses it | Each teammate's **coding agent** (Claude Code, Cursor, …) | The **Batchmate backend** on the HF Space |
| Datapack(s) | `batchmate-build` (one, shared by the team) | `batchmate-student-<id>`, `batchmate-company-<name>`, `batchmate-company-<name>-reports`, `batchmate-batch-<year>` |
| Created by | Team lead, by hand in the portal | The backend, automatically (`datapack_create`) |
| Scores | "Built with Meko" (10) + Check T | "Meko's role" (30): A1, A2, A4, A5 |

Never put API keys, `.env` contents or personal data in any datapack.

---

## Part A: Team lead, one time (≈10 min)

### A1. Accounts
Every teammate signs up at **https://cloud.mekodata.ai** with the email you'll invite.

### A2. Create the build datapack
1. Portal → create a new datapack named exactly **`batchmate-build`**.
2. Don't use the default datapack, and don't create any `batchmate-student-…` / `batchmate-company-…`
   datapacks by hand; the backend creates those.

### A3. Invite teammates as Maintainers
1. Open `batchmate-build` → **Share → Invite People**.
2. **Invite humans:** all teammates' emails, comma-separated.
3. Role: **Maintainer** (Maintainers can promote; a share link can't grant Maintainer, so use email).
4. **Send invite.** Check **Share** later: everyone listed as Maintainer, nobody under **Pending**.

### A4. Create the backend's API key
1. Portal → **Settings → API Keys → Generate API key**, name it `hf-space/batchmate`.
2. Copy it (starts with `mko_tkn_`) or **Download .txt**. It's shown once.
3. This key belongs to the team lead's account, so the product datapacks will too. Keep it for Part B.

---

## Part B: Switch the backend to Meko (≈10 min, team lead)

### B1. Files to upload to the Space (Files → Contribute → Upload files, into these exact paths)

| File in this repo (`backend/…`) | What changed |
|---|---|
| `requirements.txt` | adds `mcp` (Python MCP client) |
| `batchmate/config.py` | `MEKO_API_KEY`, `MEKO_URL`, `MEKO_DATAPACK_PREFIX`, `LEDGER_BACKEND` |
| `batchmate/api.py` | new `GET /meko/status`, `GET /meko/log` |
| `batchmate/agents/steward.py` | Steward re-syncs anything Meko missed |
| `batchmate/memory/__init__.py` | `MEMORY_BACKEND=meko` → Meko service with Supabase ledger |
| `batchmate/memory/meko_client.py` | **new**: MCP client (Bearer key + required User-Agent) |
| `batchmate/memory/meko_store.py` | **new**: Meko-backed memory (add/search/update/delete/promote) |

Nothing else in the backend changes. Agents are untouched.

### B2. Space settings → Variables and secrets
| Type | Name | Value |
|---|---|---|
| Secret | `MEKO_API_KEY` | the `hf-space/batchmate` key from A4 |
| Variable | `MEMORY_BACKEND` | change `supabase` → **`meko`** |
| (keep) | `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `GROQ_API_KEY`, `LLM_CHAIN` | unchanged |

### B3. Verify
1. Wait for the Space to restart (requirements changed → rebuild, ~5 min).
2. Open **`https://happynishh-batchmate.hf.space/meko/status`**
   → `"meko": true`, `"tools": ~28`.
3. Within ~1 minute the Steward pushes existing memories into Meko. In the portal you'll see:
   - `batchmate-company-amazon` (6 approved patterns, promoted)
   - `batchmate-company-amazon-reports` (~37 anonymised senior reports)
   - `batchmate-student-priya`, `batchmate-student-arjun` (seeded weak spots)
4. `https://happynishh-batchmate.hf.space/meko/log` shows every Meko call (tool, ok, ms).
5. Run Priya's mock on the website: `/meko/log` should show `memory_search` before each question.

If `/meko/status` shows an error: `401/403` → key or User-Agent (re-paste the key);
`no Meko account found` → the key's account doesn't exist; quota errors → Free tier is 10,000
retrievals/month (a mock uses ~10–15).

---

## Part C: Every teammate, own laptop (≈5 min each)

### C1. Accept the invite
Accept the email invite, then check `batchmate-build` appears at https://cloud.mekodata.ai.

### C2. Connect your coding agent (use YOUR OWN key, never the Space key)
Needs Node.js ≥ 20.18.1. In a terminal:

```sh
# pick one: claude-code | cursor | codex | kiro | opencode | claude-desktop
npx @yugabytedb/meko-mcp@latest --client claude-code --url "https://mcp.mekodata.ai/mcp"
```
It opens a browser to sign in and creates a key for you. Restart the agent afterwards.

**VS Code / anything else (manual config):** add an MCP server with
```json
{
  "mcpServers": {
    "meko": {
      "url": "https://mcp.mekodata.ai/mcp",
      "headers": {
        "Authorization": "Bearer mko_tkn_YOUR_KEY",
        "User-Agent": "meko-mcp-installer/1.0"
      }
    }
  }
}
```
Keep both headers; Meko rejects requests without the User-Agent.

### C3. Verify
Ask your agent: **"List my datapacks in Meko."** → it should show `batchmate-build`.

### C4. Load the team protocol
Clone the GitHub repo. `CLAUDE.md` (Claude Code) and `AGENTS.md` (Codex, Cursor and others) are already
in the root, so the agent follows them automatically. For Cursor, also copy `AGENTS.md` to `.cursorrules`.

---

## Part D: Daily workflow (what earns Check T)

Every task, every teammate's agent:
1. **Before:** search `batchmate-build` for the topic.
2. **After:** `memory_add` a 1–3 line summary starting with your name: `Riya: …`.
3. **Promote** decisions others must follow (after the teammate confirms; one-way).

**Check T needs:** ≥ 10 **promoted** decisions in `batchmate-build`, from ≥ 2 teammates' agents, each
naming its teammate. Starter decisions you can promote today (split them between two people):

| # | Decision (promote with the teammate's name in front) |
|---|---|
| 1 | Agents only use `get_memory()`; memory lives behind `MemoryService` (`backend/batchmate/memory/base.py`). |
| 2 | Production uses `MEMORY_BACKEND=meko`; recall comes only from Meko `memory_search`. |
| 3 | Supabase is the ledger for ids, status and metadata; it never adds recall results of its own. |
| 4 | Product datapacks are named `batchmate-<scope>`; raw reports go to `batchmate-company-<name>-reports`. |
| 5 | Only `coordinator-*` users approve patterns; approval calls `memory_promote`. The Steward never approves. |
| 6 | A pattern needs ≥ 3 independent reports (`PROMOTION_MIN_REPORTS`); duplicate write-ups don't count. |
| 7 | Stored experiences keep topics only, never verbatim questions (8-word copy guard in the Curator). |
| 8 | Batch lessons are opt-in and published only when ≥ 3 students share a topic. |
| 9 | Frontend calls the backend only through `/api/*` (Vercel rewrite to the HF Space). |
| 10 | LLM chain is Groq → offline heuristic on the Space; the offline path must never crash a demo. |
| 11 | The Space runs on ZeroGPU; `app.py` must launch via `demo.launch()` (ZeroGPU only detects GPU functions that way). |
| 12 | Meko MCP calls must send `User-Agent: meko-mcp-installer/1.0` with the Bearer key. |

Write each one with your agent ("Remember this decision in batchmate-build and promote it after I confirm: …").

### Rehearse Check T
Teammate B asks their agent: *"Why do raw senior reports live in a separate datapack?"*
It should answer from `batchmate-build`, naming the teammate who decided it.

---

## Part E: Before judging
1. `batchmate-build` → **Share → Invite People** → judges' emails → role **Viewer**.
2. Warm up the Space (open it; first request after sleep takes ~30 s).
3. Demo order: Memory **off** → Memory **on** → show the margin notes (what Meko returned) → forget one →
   coordinator approves a pattern → open `/meko/log`.
