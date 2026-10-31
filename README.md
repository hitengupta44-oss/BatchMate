# Batchmate — the interview coach that remembers your batch

Multi-agent mock-interview coach. Remembers each student's weak spots privately, learns what seniors
were actually asked, and promotes verified patterns into shared batch knowledge.

```
batchmate/
├── backend/    FastAPI + LangGraph agents + MemoryService (local JSON or Supabase pgvector)
├── frontend/   static website for Vercel (HTML/CSS/JS, no build step); /api/* is proxied to the backend
└── supabase/   migrations (memories table, pgvector index, match_memories RPC) + CLI config
```

## Run locally

```bash
# 1. backend  (http://localhost:8000, docs at /docs)
cd backend
pip install -r requirements.txt
cp .env.example .env            # GROQ_API_KEY / GOOGLE_API_KEY, or Ollama with qwen3:8b
python -m seed.seed --approve --reset
python main.py

# 2. frontend: set window.BATCHMATE_API = "http://localhost:8000" in frontend/config.js, then
cd frontend && python -m http.server 3000   # http://localhost:3000
```

No keys or model download: start the backend with `LLM_CHAIN=offline EMBED_MODEL=hash python main.py`.

Tests (from `backend/`): `LLM_CHAIN=offline EMBED_MODEL=hash python tests/test_flow.py && python tests/test_autonomy.py`

## Switch memory to Supabase

```bash
cd supabase && supabase link --project-ref <ref> && supabase db push
# or paste migrations/*.sql into the Supabase SQL editor
cd ../backend
# .env: MEMORY_BACKEND=supabase, SUPABASE_URL=..., SUPABASE_SERVICE_KEY=...
python -m seed.seed --approve
```

## Deploy

- **supabase/**: run the migration in the SQL editor (or `supabase db push`).
- **backend/** → one Hugging Face Space (**Gradio SDK**, runs `app.py`). Secrets: `GROQ_API_KEY`, `GOOGLE_API_KEY`, `MEMORY_BACKEND=supabase`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`. Seeds itself on first boot.
- **frontend/** → Vercel, root directory `frontend`, framework preset "Other". Put your Space URL in `vercel.json`.

## Backend layout

```
batchmate/memory/base.py       MemoryService: write · recall · promote · forget, scopes, privacy, confidence
batchmate/memory/local.py      JSON-file backend (default)
batchmate/memory/supabase_store.py  pgvector backend
batchmate/agents/              planner · interviewer · evaluator · curator · pattern · verifier
batchmate/graph.py             LangGraph: plan → ask → interrupt(answer) → evaluate → … → wrap_up
batchmate/llm.py               Ollama → Groq → Gemini → offline heuristic
batchmate/api.py               FastAPI routes (X-User header = demo identity)
seed/                          10 seeded Amazon experiences + 2 students (labelled seeded)
```

## Autonomy

The **Steward** agent (`agents/steward.py`) runs every `STEWARD_INTERVAL_MIN` minutes and needs no clicks:

- re-runs pattern detection for every company/role; a new experience also triggers it immediately
- retires patterns whose evidence is older than ~2 years (`STALE_RECENCY`); fresh reports revive them **back to the coordinator**, never straight to students
- publishes anonymous batch lessons ("4 students are also working on DBMS transactions") from students who opted in, only when ≥3 share a topic

Each session's closing promise ("tomorrow we'll drill transactions") is stored and the next plan starts with it.
Duplicate write-ups don't count as extra corroboration, and the Curator replaces any summary that copies 8+ words from the raw text.

Humans still decide: the Steward never approves a pattern.

## Memory design

| Scope | Who can read | What lives there |
|---|---|---|
| `student-<id>` | that student only | weaknesses, strengths, session summaries |
| `company-<name>` | everyone | anonymised experiences, patterns (`proposed` → `active` after approval) |
| `batch-<year>` | everyone | batch-wide lessons |

`recall(..., weight_by=("recency","corroboration"))` returns a confidence per memory:
`similarity × (0.5 + 0.5·recency) × (0.5 + 0.5·corroboration)`. That's the Meko feature proposal, working today.

## Adding Meko later

Agents only call `get_memory()`. Add `backend/batchmate/memory/meko_store.py` implementing
`MemoryService`, map scopes to datapacks, add a `"meko"` branch in `memory/__init__.py`.

## Not done yet

Real auth (the `X-User` header is a demo stand-in) · Whisper voice notes · PDF upload for experiences.
