"""Backend entrypoint: python main.py  (API on :8000, docs at /docs)."""
import os

import uvicorn

from batchmate.api import api

if __name__ == "__main__":
    uvicorn.run(api, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
