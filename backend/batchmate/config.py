"""Central settings, read from environment / .env."""
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


# Memory backend: "meko" (Meko MCP; recall comes from Meko), "supabase" (pgvector) or "local" (JSON).
MEMORY_BACKEND = _env("MEMORY_BACKEND", "local")
# With MEMORY_BACKEND=meko, the structured ledger (ids, status, metadata) lives here:
LEDGER_BACKEND = _env("LEDGER_BACKEND", "supabase" if _env("SUPABASE_URL") else "local")
MEKO_URL = _env("MEKO_URL", "https://mcp.mekodata.ai/mcp")
MEKO_API_KEY = _env("MEKO_API_KEY")
MEKO_DATAPACK_PREFIX = _env("MEKO_DATAPACK_PREFIX", "batchmate")
LOCAL_STORE_PATH = _env("LOCAL_STORE_PATH", "data/memory.json")
SUPABASE_URL = _env("SUPABASE_URL")
SUPABASE_KEY = _env("SUPABASE_SERVICE_KEY")

# LLM chain. Comma-separated order; "offline" uses deterministic heuristics (no API, for tests/demos).
LLM_CHAIN = [p.strip() for p in _env("LLM_CHAIN", "ollama,groq,gemini").split(",") if p.strip()]
OLLAMA_MODEL = _env("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_BASE_URL = _env("OLLAMA_BASE_URL", "http://localhost:11434")
GROQ_MODEL = _env("GROQ_MODEL", "llama-3.3-70b-versatile")
GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-2.5-flash")

# Embeddings: sentence-transformers model; falls back to a hashing embedder if unavailable.
EMBED_MODEL = _env("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
EMBED_DIM = 384

# Memory weighting (the feature-proposal knobs).
RECENCY_HALF_LIFE_DAYS = float(_env("RECENCY_HALF_LIFE_DAYS", "365"))
PROMOTION_MIN_REPORTS = int(_env("PROMOTION_MIN_REPORTS", "3"))
STALE_RECENCY = float(_env("STALE_RECENCY", "0.25"))  # 2 half-lives (~2 years) → retire pattern
BATCH_MIN_STUDENTS = int(_env("BATCH_MIN_STUDENTS", "3"))  # k-anonymity for batch lessons
STEWARD_INTERVAL_MIN = int(_env("STEWARD_INTERVAL_MIN", "30"))  # 0 disables the timer

# Upstash Redis REST (optional rate limiting).
UPSTASH_URL = _env("UPSTASH_REDIS_REST_URL")
UPSTASH_TOKEN = _env("UPSTASH_REDIS_REST_TOKEN")
RATE_LIMIT_PER_MIN = int(_env("RATE_LIMIT_PER_MIN", "30"))

MOCK_TURNS = int(_env("MOCK_TURNS", "3"))
