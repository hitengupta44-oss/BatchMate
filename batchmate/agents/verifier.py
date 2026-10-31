"""Verifier (human-in-the-loop): a placement coordinator gates what the batch sees."""
from ..memory import get_memory


def approve(memory_id: str, coordinator_id: str):
    return get_memory().promote(memory_id, approved_by=coordinator_id)


def reject(memory_id: str, coordinator_id: str):
    return get_memory().reject(memory_id, approved_by=coordinator_id)
