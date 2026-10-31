"""Synchronous wrapper over Meko's MCP server (streamable HTTP, Bearer API key).

One background event loop keeps a single MCP session open; FastAPI's worker threads call
`call(tool, args)` and block on the result. Every call is logged (tool, args summary, ok/error,
latency) so the UI can show exactly what Meko returned.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import deque
from contextlib import AsyncExitStack

from .. import config


class MekoError(RuntimeError):
    pass


CALL_LOG: deque = deque(maxlen=300)


def _log(tool: str, args: dict, ok: bool, ms: int, note: str = ""):
    shown = {k: (v[:60] + "…" if isinstance(v, str) and len(v) > 60 else v)
             for k, v in args.items() if k not in ("content_base64",)}
    CALL_LOG.append({"at": time.time(), "tool": tool, "args": shown, "ok": ok, "ms": ms, "note": note})


def parse_result(res) -> dict | list:
    """CallToolResult → python data (structuredContent, else JSON in the text block)."""
    if getattr(res, "isError", False):
        text = " ".join(getattr(c, "text", "") for c in res.content or [])
        raise MekoError(text or "Meko tool error")
    sc = getattr(res, "structuredContent", None)
    if sc:
        return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
    text = "".join(getattr(c, "text", "") for c in res.content or [])
    try:
        data = json.loads(text) if text else {}
    except json.JSONDecodeError:
        return {"text": text}
    if isinstance(data, dict) and (data.get("error") or (isinstance(data.get("detail"), str)
                                                          and "error" in data["detail"].lower())):
        raise MekoError(str(data.get("error") or data.get("detail")))
    return data


class MekoClient:
    def __init__(self, url: str | None = None, api_key: str | None = None):
        self.url = url or config.MEKO_URL
        self.key = api_key or config.MEKO_API_KEY
        if not self.key:
            raise MekoError("MEKO_API_KEY is not set")
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, daemon=True, name="meko-mcp").start()
        self._stack: AsyncExitStack | None = None
        self._session = None
        self._lock = asyncio.Lock()

    async def _connect(self):
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        self._stack = AsyncExitStack()
        read, write, _ = await self._stack.enter_async_context(
            streamablehttp_client(self.url, headers={
                # Meko rejects requests without this User-Agent (see docs: Integrations).
                "Authorization": f"Bearer {self.key}", "User-Agent": "meko-mcp-installer/1.0"}))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()

    async def _close(self):
        if self._stack:
            try:
                await self._stack.aclose()
            except Exception:
                pass
        self._stack, self._session = None, None

    async def _call(self, tool: str, args: dict):
        async with self._lock:
            for attempt in (1, 2):
                try:
                    if self._session is None:
                        await self._connect()
                    return await self._session.call_tool(tool, args)
                except MekoError:
                    raise
                except Exception:
                    await self._close()  # dropped session → reconnect once
                    if attempt == 2:
                        raise

    def call(self, tool: str, args: dict, timeout: float = 30):
        args = {k: v for k, v in args.items() if v is not None}
        t0 = time.time()
        try:
            res = asyncio.run_coroutine_threadsafe(self._call(tool, args), self._loop).result(timeout)
            data = parse_result(res)
            _log(tool, args, True, int((time.time() - t0) * 1000))
            return data
        except Exception as e:
            _log(tool, args, False, int((time.time() - t0) * 1000), f"{e.__class__.__name__}: {e}"[:200])
            raise MekoError(f"{tool} failed: {e}") from e

    def list_tools(self) -> list[str]:
        async def _lt():
            async with self._lock:
                if self._session is None:
                    await self._connect()
                return await self._session.list_tools()
        res = asyncio.run_coroutine_threadsafe(_lt(), self._loop).result(30)
        return [t.name for t in res.tools]
