# Batchmate

**The interview coach that remembers you, and what your seniors were asked.**

Built by **Team Triton** for the **Meko challenge at hackCBS 9.0** (Track A, open project), on
[Meko](https://docs.mekodata.ai) by YugabyteDB.

| | |
|---|---|
| Live app | `https://<your-vercel-url>.vercel.app` |
| Backend API | https://happynishh-batchmate.hf.space (API reference at `/docs`) |
| Demo video | `<link>` |
| Meko feature proposal | `<link>` |

---

## In plain words

Every placement season in Indian engineering colleges goes the same way. Seniors' interview
experiences live in scattered WhatsApp chats and Google Docs, and they're lost when that batch
graduates. A student practises hundreds of problems but keeps stumbling on the same thing, such as
explaining their project or database transactions, and no tool remembers that. Mock interviews with
friends or chatbots start from zero every time.

**Batchmate is a mock-interview coach with a memory.** It remembers three things:

1. **You.** What you struggled with last time, what you've improved at, your projects, and what you
   promised to practise next. This stays private to you.
2. **Your seniors.** What they were actually asked at each company, collected from their write-ups
   with names removed. A topic becomes "batch knowledge" only when at least three seniors report it
   and a placement coordinator approves it.
3. **What it already asked you,** so it never repeats a question.

Before every question, the coach looks these up and uses them. The result is a mock interview that
feels like it was prepared for you, by someone who knows your college's history with that company.

### A short story: Priya

Priya, a 3rd-year CSE student, has an Amazon SDE intern interview in 5 days.

- **Memory off:** the coach asks generic questions ("reverse a linked list", "tell me about
  yourself") and gives generic feedback. It repeats things she already aced.
- **Memory on:** the coach remembers that Priya twice struggled to explain time complexity and DBMS
  transactions. It also knows that five seniors from her college were asked to design an LRU cache in
  Amazon's round 2. So it asks the LRU question, probes complexity when she skips it, asks about her
  own project (CampusEats), and ends with: *"You explained time complexity much better than last time;
  DBMS transactions is still weak, so tomorrow we'll drill transactions."* The next session starts
  exactly there.

Same student, same company, clearly different interview. That difference is what Meko provides.

---

## What you can do in the app

| As a student | As a placement coordinator |
|---|---|
| **Mock interview** with memory on or off, a live answer sheet, scores on correctness, clarity, complexity and communication | **Approve or reject** patterns before students see them |
| **Margin notes** showing exactly what the coach recalled, where it came from, and how confident it is | See approved, waiting, retired and rejected patterns on one board |
| **Ask your coach**: questions answered only from memory, with sources listed | Run the **Steward** (the maintenance agent) on demand |
| **My memory**: see everything stored about you, mark a weak spot as fixed, or forget anything | |
| **My profile**: projects and target companies the interviewer uses | |
| **Share an experience**: paste your interview story; names and contact details are removed | |
| **Show Meko activity**: a live list of every call the app makes to Meko | |

---

## How it works

```
 Student ──► Next.js website (Vercel) ──/api──► FastAPI backend (Hugging Face Space)
                                                   │
                                     LangGraph agents (Groq gpt-oss-120b)
                                                   │
                       ┌───────────────────────────┴───────────────────────────┐
                       ▼                                                       ▼
            Meko (memory: recall, write,                         Supabase Postgres
            promote, forget, over MCP)                    (ledger: ids, status, topic, round)
```

**The agents**

| Agent | Job |
|---|---|
| Planner | Builds today's mock from the target company, days left, your weak spots and verified patterns |
| Interviewer | Asks each question; recalls before every one; follows up when an answer skips complexity; never repeats |
| Evaluator | Scores each answer and writes "weak at X" or "improved at Y" to your private memory |
| Curator | Turns a senior's raw write-up into anonymised topics (company, round, topic, outcome) |
| Pattern agent | Finds a topic reported by 3+ independent seniors and proposes it |
| Verifier | The human step: a coordinator approves before the batch sees it |
| Steward | Runs on its own every 30 minutes: finds new patterns, retires stale ones, re-syncs to Meko. It never approves anything |
| Coach | Answers "Ask your coach" questions only from recalled memories |

---

## How Meko is used

Meko is load-bearing: with memory off, the product is a generic quiz.

### Requirements A1–A5

| Requirement | How Batchmate meets it |
|---|---|
| **A1** Context matters | The same mock with memory on vs off gives different questions, follow-ups and a different closing remark |
| **A2** Real Meko use (≥3) | Six uses, listed below |
| **A3** A user and a story | Priya's Amazon interview, above |
| **A4** Visible context | Margin notes show every recalled memory, its source and confidence; "Forget this" deletes it from Meko; **Show Meko activity** lists every Meko call |
| **A5** Honest and private | Context comes only from Meko search results; personal memory is private to its owner; seniors' names, emails and phone numbers are removed; exact questions are never stored; seeded demo data is labelled |

### Six uses of Meko (A2)

| Meko use | Where in Batchmate | Why |
|---|---|---|
| **Scopes (datapacks)** | One private datapack per student, one per company, one per batch | Weak spots stay private; company knowledge is shared |
| **Extracted memories** | The Evaluator writes "weak at X" / "improved at Y" with `memory_add` | Raw answers become reusable facts |
| **Recall before reasoning** | The Planner, Interviewer and Coach call `memory_search` before every plan, question and answer | This is the on/off difference |
| **Promotion to shared knowledge** | Coordinator approval calls `memory_promote` | One senior's story becomes batch knowledge only when verified |
| **Sharing across users** | Every student, and next year's batch, recalls promoted patterns | Knowledge doesn't graduate with the seniors |
| **Forget and correct** | "Forget this" calls `memory_delete_by_id`; "I've fixed this" retires a weak spot | Students control their own memory |

### Datapacks

| Datapack | Who can read it | What's in it |
|---|---|---|
| `batchmate-student-<id>` | That student only | Weak spots, strengths, session summaries, profile, questions already asked, next-session plan |
| `batchmate-company-<name>` | Every student | Verified patterns (promoted after approval) |
| `batchmate-company-<name>-reports` | Every student | Anonymised senior reports (kept apart so they don't drown out the patterns) |
| `batchmate-batch-<year>` | Every student | Anonymous batch tips, only from students who opted in, only when 3+ share a topic |
| `batchmate-build` | The team (and judges as Viewers) | Build-time decisions by the team's coding agents. Never read by the app |

The backend creates the product datapacks itself on first use. Only `batchmate-build` is created by hand.

---

## Built with Meko (coding agents and Check T)

The team built Batchmate with coding agents connected to Meko, sharing one build datapack,
**`batchmate-build`**, kept completely separate from the product's datapacks.

**Team setup**

1. **Team lead:** at [cloud.mekodata.ai](https://cloud.mekodata.ai), create the datapack
   `batchmate-build`, then **Share → Invite People**, enter teammates' emails, role **Maintainer**
   (only Maintainers can promote).
2. **Each teammate, with their own key:** connect a coding agent:

   ```sh
   npx @yugabytedb/meko-mcp@latest --client claude-code --url "https://mcp.mekodata.ai/mcp"
   # or --client cursor | codex
   ```

   Sign in with the invited email, restart the agent, then ask it *"List my datapacks in Meko"*.
   `batchmate-build` should appear.
3. **Team protocol:** `CLAUDE.md` and `AGENTS.md` in this repo tell every agent to search
   `batchmate-build` before a task, save a short summary after it, and **promote** decisions the rest of
   the team must follow, each starting with the teammate's name.
4. **Never** put keys, passwords or personal data in `batchmate-build`.

**Check T:** `batchmate-build` holds 10+ promoted decisions from 2+ teammates' coding agents, each
naming its teammate. Asking one teammate's agent about another's decision answers from Meko, live.
Judges are invited to `batchmate-build` as **Viewers**.

Full step-by-step guide: [`MEKO_SETUP.md`](MEKO_SETUP.md).

---

## Run it yourself

### Quick start: 5 commands, no keys needed

```bash
git clone https://github.com/hitengupta44-oss/BatchMate && cd BatchMate/backend
pip install -r requirements.txt
LLM_CHAIN=offline EMBED_MODEL=hash python -m seed.seed --approve --reset
LLM_CHAIN=offline EMBED_MODEL=hash python main.py &
cd ../frontend && npm install && BACKEND_URL=http://localhost:8000 npm run dev
```

Open http://localhost:3000 and sign in as **Priya**. This runs the whole loop locally on built-in
rules and a local memory file, with seeded demo data (10 Amazon experiences, 2 students).

### The real setup: Groq, Meko and Supabase

1. **Supabase:** create a project, then paste `supabase/migrations/20261031000000_memories.sql` into
   the SQL editor and run it.
2. **Meko:** create an API key at cloud.mekodata.ai (Settings → API Keys).
3. **Groq:** create an API key at console.groq.com.
4. Copy `backend/.env.example` to `backend/.env`, fill in the values below, and run `python app.py`
   in `backend/`. It seeds itself on first start.

| Setting | Value |
|---|---|
| `MEMORY_BACKEND` | `meko` |
| `MEKO_API_KEY` | your `mko_tkn_…` key |
| `GROQ_API_KEY` | your `gsk_…` key |
| `GROQ_MODEL` | `openai/gpt-oss-120b` |
| `LLM_CHAIN` | `groq,offline` |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | from Supabase → Project Settings → API |
| `DEMO_USERS` (optional) | `priya:pw1,arjun:pw2,coordinator-demo:pw3` turns on passwords |
| `AUTH_SECRET` (optional) | any long random string, keeps sign-ins valid across restarts |

### Deploy

| Part | Where | How |
|---|---|---|
| Backend | Hugging Face Space (Gradio SDK, ZeroGPU) | Upload the **contents** of `backend/` to the Space root; add the settings above as Space secrets and variables |
| Frontend | Vercel | Import the repo, root directory `frontend`, framework **Next.js**. No environment variables needed (`BACKEND_URL` is optional) |
| Database | Supabase | Run the migration once |

Health checks: `/health`, `/system/status` (shows whether Meko and Groq are live), `/meko/status`.

### Tests

From `backend/`:

```bash
LLM_CHAIN=offline EMBED_MODEL=hash python tests/test_flow.py
```

Also `test_autonomy`, `test_meko` (full story through a strict fake Meko), `test_auth`,
`test_features` (no repeated questions, profiles, coach), `test_speed` (parallel recall),
`test_api_names`.

---

## Privacy and honesty

- **Private by default.** A student's memory is readable only by that student. The Meko activity
  list never shows memory text or another student's datapack.
- **Sign-in** uses signed tokens; nobody can claim to be another student or the coordinator.
- **Seniors are anonymised** before anything is stored: names, emails, phone numbers and handles are
  removed. Only topics are kept, never the exact questions (any summary copying 8+ words is replaced).
- **Humans decide** what the batch sees. The Steward proposes; only a coordinator approves.
- **Nothing is invented.** Anything shown as context was returned by Meko's search. If Meko is
  unavailable, the coach shows no context rather than guessing.
- **Batch tips are opt-in** and published only when 3+ students share a topic.
- **Seeded demo data is labelled** as seeded wherever it appears.

---

## Repository layout

```
backend/
  app.py                     Hugging Face Space entry point (Gradio launch + API routes)
  batchmate/api.py           API routes;  batchmate/auth.py  signed sign-in tokens
  batchmate/graph.py         LangGraph loop: plan → ask → answer → evaluate → … → wrap-up
  batchmate/agents/          planner, interviewer, evaluator, curator, pattern, verifier,
                             steward, coach, profile
  batchmate/memory/          MemoryService interface; Meko client and store; Supabase and local stores
  batchmate/llm.py           Groq, Gemini or Ollama (configurable), then built-in rules
  seed/                      seeded demo data (labelled)
  tests/                     7 test suites
frontend/                    Next.js app (sign-in, mock, coach, memory, profile, share, coordinator)
supabase/                    database migration
AGENTS.md, CLAUDE.md         team protocol for coding agents
MEKO_SETUP.md                full Meko setup guide
```

## Tech stack

| Layer | Choice |
|---|---|
| Agents | LangGraph + LangChain |
| Language model | Groq `openai/gpt-oss-120b`, with built-in rules as fallback |
| Memory | Meko over MCP |
| Ledger | Supabase Postgres + pgvector |
| Embeddings | `BAAI/bge-small-en-v1.5` |
| Backend | FastAPI on a Hugging Face Space (Gradio SDK) |
| Frontend | Next.js 15 on Vercel |

## Known limits

- **Speed:** each Meko search takes several seconds, so a question takes about 10 seconds even with
  searches running in parallel.
- **Accounts:** demo users only (set in `DEMO_USERS`); there's no sign-up.
- **One company seeded:** Amazon SDE intern. Other companies work as soon as seniors share experiences.
- **Not yet built:** voice-note experiences (Whisper), PDF upload.

## Team Triton

Built at hackCBS 9.0, 31 October – 1 November 2026, SSCBS, New Delhi.
