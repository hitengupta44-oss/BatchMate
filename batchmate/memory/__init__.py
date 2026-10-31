from functools import lru_cache

from .. import config
from .base import (SYSTEM, AccessDenied, Memory, MemoryService, batch_scope, company_scope,
                   student_scope)


def _store(kind: str) -> MemoryService:
    if kind == "supabase":
        from .supabase_store import SupabaseMemoryService

        return SupabaseMemoryService()
    from .local import LocalMemoryService

    return LocalMemoryService(config.LOCAL_STORE_PATH)


@lru_cache(maxsize=1)
def get_memory() -> MemoryService:
    if config.MEMORY_BACKEND == "meko":
        from .meko_store import MekoMemoryService

        return MekoMemoryService(ledger=_store(config.LEDGER_BACKEND))
    return _store(config.MEMORY_BACKEND)


__all__ = ["get_memory", "Memory", "MemoryService", "SYSTEM", "AccessDenied",
           "student_scope", "company_scope", "batch_scope"]
