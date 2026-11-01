"""Experience Curator: raw senior write-ups → anonymised, structured experience memories."""
from __future__ import annotations

import hashlib
import re
import uuid

from pydantic import BaseModel, Field

from ..llm import structured
from ..memory import SYSTEM, Memory, company_scope, get_memory
from ..topics import TOPICS, detect_topics

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"(\+?\d[\d\s-]{8,}\d)")
_HANDLE = re.compile(r"@\w{2,}")
_INTRO = re.compile(r"\b(my name is|i am|i'm|this is)\s+[A-Z][a-z]+(\s+[A-Z][a-z]+)?", re.I)
_ROUND = re.compile(r"round\s*(\d)", re.I)


def anonymise(text: str, names: list[str] | None = None) -> str:
    """A5: strip names and contact details before anything reaches shared memory."""
    text = _EMAIL.sub("[email]", text)
    text = _PHONE.sub("[phone]", text)
    text = _HANDLE.sub("[handle]", text)
    text = _INTRO.sub(lambda m: m.group(1) + " [senior]", text)
    for n in names or []:
        if n.strip():
            text = re.sub(re.escape(n.strip()), "[senior]", text, flags=re.I)
    return text


class Entry(BaseModel):
    round: int = Field(ge=1, le=6)
    topic: str = Field(description="one canonical topic tag")
    summary: str = Field(description="the TOPIC/pattern asked, paraphrased; never a verbatim confidential question")
    outcome: str = Field(description="cleared | rejected | unknown")


class Entries(BaseModel):
    entries: list[Entry]


def _heuristic(text: str) -> Entries:
    out, current = [], 1
    outcome = "rejected" if re.search(r"reject|didn'?t clear|not selected", text, re.I) else \
        ("cleared" if re.search(r"selected|cleared|got the offer|offer", text, re.I) else "unknown")
    for line in re.split(r"[\n.]", text):
        m = _ROUND.search(line)
        if m:
            current = int(m.group(1))
        for tag in detect_topics(line):
            out.append(Entry(round=current, topic=tag, summary=f"Round {current}: {TOPICS[tag]['label']}",
                             outcome=outcome))
    uniq = {(e.round, e.topic): e for e in out}
    return Entries(entries=list(uniq.values()))


def fingerprint(text: str) -> str:
    norm = " ".join(re.findall(r"[a-z0-9]+", text.lower()))
    return hashlib.sha1(norm.encode()).hexdigest()[:16]


def _copies_source(summary: str, source: str, n: int = 8) -> bool:
    """True if the summary contains any run of n words copied from the raw write-up."""
    s, src = summary.lower().split(), " ".join(source.lower().split())
    return any(" ".join(s[i:i + n]) in src for i in range(max(0, len(s) - n + 1)))


def curate(raw_text: str, company: str, role: str, year: int, observed_at: str,
           names: list[str] | None = None, seeded: bool = False) -> list[Memory]:
    clean = anonymise(raw_text, names)
    fp = fingerprint(clean)
    mem = get_memory()
    # The same write-up submitted twice must not count as two corroborating reports.
    if any(e.meta.get("fingerprint") == fp
           for e in mem.list(company_scope(company), SYSTEM, kinds=["experience"])):
        return []
    system = ("You structure senior interview experiences. Extract one entry per (round, topic). "
              f"topic must be one of: {', '.join(TOPICS)}. Paraphrase the topic; do NOT copy "
              "verbatim questions. Never include names.")
    entries = structured(Entries, system, clean, lambda: _heuristic(clean)).entries
    report_id = uuid.uuid4().hex[:8]
    written = []
    for e in entries:
        if e.topic not in TOPICS:
            continue
        if _copies_source(e.summary, clean):  # guard against leaking verbatim questions
            e.summary = f"Round {e.round}: {TOPICS[e.topic]['label']}"
        m = Memory(scope=company_scope(company), kind="experience",
                   text=f"{company} {role} {e.summary} (outcome: {e.outcome})",
                   meta={"company": company, "role": role, "round": e.round, "topic": e.topic,
                         "outcome": e.outcome, "year": year, "observed_at": observed_at,
                         "report_id": report_id, "fingerprint": fp, "seeded": seeded,
                         "anonymised": True})
        written.append(mem.write(m, requester=SYSTEM))
    return written
