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


def to_tag(topic: str, summary: str = "") -> str | None:
    """Map the model's wording ("LRU cache design", "Trees/graphs") to a canonical topic tag."""
    t = (topic or "").strip().lower()
    key = "_".join(re.findall(r"[a-z0-9]+", t))
    if key in TOPICS:
        return key
    for tag, spec in TOPICS.items():
        lab = spec["label"].lower()
        if t and (t == lab or t in lab or lab in t):
            return tag
    hits = detect_topics(f"{topic} {summary}")
    return hits[0] if hits else None


def curate_report(raw_text: str, company: str, role: str, year: int, observed_at: str,
                  names: list[str] | None = None, seeded: bool = False) -> tuple[list[Memory], str]:
    """Like curate(), plus why nothing was stored: "added", "duplicate" or "no_topics"."""
    clean = anonymise(raw_text, names)
    fp = fingerprint(clean)
    mem = get_memory()
    # The same write-up submitted twice must not count as two corroborating reports.
    if any(e.meta.get("fingerprint") == fp
           for e in mem.list(company_scope(company), SYSTEM, kinds=["experience"])):
        return [], "duplicate"
    if len(re.findall(r"[a-zA-Z]{2,}", clean)) < 8:  # "hello 123": nothing to learn, don't let a model invent topics
        return [], "no_topics"
    system = ("You structure senior interview experiences. Extract one entry per (round, topic). "
              f"topic must be one of these tags exactly: {', '.join(TOPICS)}. Paraphrase the topic; "
              "do NOT copy verbatim questions. Never include names.")
    try:
        ai = structured(Entries, system, clean, lambda: Entries(entries=[])).entries
    except Exception as e:  # never lose a senior's report to a model hiccup
        print(f"[curator] model extraction failed: {e!r}")
        ai = []
    # Merge: the model's entries (wording mapped to tags) + the keyword extractor's, deduped by
    # (round, topic). The keyword pass guarantees clear mentions ("LRU cache") are never dropped.
    merged: dict[tuple, Entry] = {}
    for e in ai:
        tag = to_tag(e.topic, e.summary)
        if tag:
            e.topic = tag
            merged.setdefault((e.round, tag), e)
    for e in _heuristic(clean).entries:
        merged.setdefault((e.round, e.topic), e)
    if not merged:
        return [], "no_topics"

    report_id = uuid.uuid4().hex[:8]
    written = []
    for e in merged.values():
        if not e.summary or _copies_source(e.summary, clean):  # never leak verbatim questions
            e.summary = f"Round {e.round}: {TOPICS[e.topic]['label']}"
        m = Memory(scope=company_scope(company), kind="experience",
                   text=f"{company} {role} {e.summary} (outcome: {e.outcome})",
                   meta={"company": company, "role": role, "round": e.round, "topic": e.topic,
                         "outcome": e.outcome, "year": year, "observed_at": observed_at,
                         "report_id": report_id, "fingerprint": fp, "seeded": seeded,
                         "anonymised": True})
        written.append(mem.write(m, requester=SYSTEM))
    return written, "added"


def curate(raw_text: str, company: str, role: str, year: int, observed_at: str,
           names: list[str] | None = None, seeded: bool = False) -> list[Memory]:
    return curate_report(raw_text, company, role, year, observed_at, names, seeded)[0]
