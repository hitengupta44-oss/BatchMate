"""Hugging Face Space entrypoint (Gradio SDK).

Serves the Batchmate FastAPI backend (used by the Vercel website) with a small Gradio
status page mounted at "/". API docs at /docs.
"""
import os

# Sensible Space defaults; Space secrets/variables override these.
os.environ.setdefault("LLM_CHAIN", "groq,gemini,offline")

# ZeroGPU: `spaces` must be imported before torch / CUDA-touching libraries.
try:
    import spaces  # noqa: E402
except ImportError:  # local runs / CPU hardware
    spaces = None

import gradio as gr  # noqa: E402

from batchmate import config  # noqa: E402
from batchmate.api import api  # noqa: E402
from batchmate.memory import SYSTEM, get_memory  # noqa: E402
from seed.seed import seed  # noqa: E402

# ZeroGPU requires at least one @spaces.GPU function. Bulk embedding (seeding, re-indexing)
# runs on the GPU; single-query embeddings stay on CPU to save the free GPU quota.
if spaces is not None:
    from batchmate.memory import embeddings

    @spaces.GPU(duration=60)
    def gpu_embed(texts: list[str]) -> list[list[float]]:
        emb = embeddings.get_embedder()
        model = getattr(emb, "model", None)
        if model is None:  # hashing fallback, nothing to accelerate
            return emb.embed(texts)
        model.to("cuda")
        try:
            return model.encode(texts, normalize_embeddings=True, batch_size=64).tolist()
        finally:
            model.to("cpu")

    embeddings.register_bulk_embedder(gpu_embed)

# Seed on first boot only (an empty store); never touches existing data.
if not get_memory().list_scopes("company-"):
    print("[boot] empty store, seeding:", seed(approve=True))
else:
    print("[boot] store already has data, skipping seed")


def status():
    mem = get_memory()
    companies = mem.list_scopes("company-")
    rows = [[c.removeprefix("company-"),
             len(mem.list(c, SYSTEM, kinds=["experience"])),
             len(mem.list(c, SYSTEM, kinds=["pattern"], statuses=("active",))),
             len(mem.list(c, SYSTEM, kinds=["pattern"], statuses=("proposed",)))] for c in companies]
    info = (f"**Memory backend:** {config.MEMORY_BACKEND}  \n"
            f"**LLM chain:** {', '.join(config.LLM_CHAIN)}  \n"
            f"**Students with memory:** {len(mem.list_scopes('student-'))}")
    return info, rows


with gr.Blocks(title="Batchmate API") as demo:
    gr.Markdown("# Batchmate API\nThis Space is the backend for the Batchmate website. "
                "API reference: [/docs](/docs) · health check: [/health](/health)")
    info = gr.Markdown()
    table = gr.Dataframe(headers=["company", "experiences", "approved patterns", "pending patterns"],
                         interactive=False)
    gr.Button("Refresh").click(status, outputs=[info, table])
    demo.load(status, outputs=[info, table])

if __name__ == "__main__":
    import threading

    from batchmate.api import _steward_loop

    # ZeroGPU only detects @spaces.GPU functions when Gradio's own launch() starts the server.
    # The Batchmate API routes are handed to Gradio's FastAPI app AT CREATION (app_kwargs → FastAPI
    # `routes=`), so they are registered before Gradio's own routes and take precedence.
    api_routes = [r for r in api.router.routes if getattr(r, "path", "") not in ("/",)]
    demo.queue().launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
        prevent_thread_lock=True,
        show_api=False,
        # SSR puts a Node.js server in front that answers unknown paths (/health, /meko/…) with the
        # Gradio page instead of forwarding them to Python. Off, so the API routes are reachable.
        ssr_mode=False,
        app_kwargs={"routes": api_routes},
    )

    # Belt and braces: if this Gradio version ignored `routes`, add them to the served app now.
    served = getattr(demo, "server_app", None) or demo.app
    paths = [getattr(r, "path", "") for r in served.router.routes]
    if "/health" not in paths:
        served.router.routes[0:0] = api_routes
        paths = [getattr(r, "path", "") for r in served.router.routes]
    print("[boot] live API routes:", [p for p in paths if p.startswith(("/health", "/meko", "/sessions",
                                                                         "/memory", "/docs"))])

    # FastAPI's lifespan doesn't run under Gradio's server, so start the Steward here.
    if config.STEWARD_INTERVAL_MIN > 0:
        threading.Thread(target=_steward_loop, daemon=True, name="steward").start()
    demo.block_thread()
