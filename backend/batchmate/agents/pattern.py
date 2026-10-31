"""Pattern Agent: finds (round, topic) seen in ≥N independent reports and proposes promotion."""
from __future__ import annotations

from collections import defaultdict

from .. import config
from ..memory import SYSTEM, Memory, company_scope, get_memory
from ..topics import label


def find_and_propose(company: str, role: str) -> list[Memory]:
    mem = get_memory()
    scope = company_scope(company)
    groups: dict[tuple, dict] = defaultdict(lambda: {"reports": set(), "latest": "", "outcomes": []})
    for e in mem.list(scope, SYSTEM, kinds=["experience"]):
        if e.meta.get("role") != role:
            continue
        g = groups[(e.meta["round"], e.meta["topic"])]
        g["reports"].add(e.meta["report_id"])
        g["latest"] = max(g["latest"], e.meta.get("observed_at", e.created_at))
        g["outcomes"].append(e.meta.get("outcome"))

    known = {(m.meta.get("round"), m.meta.get("topic")): m
             for m in mem.list(scope, SYSTEM, kinds=["pattern"])}
    proposals = []
    for (rnd, topic), g in sorted(groups.items()):
        n = len(g["reports"])
        if n < config.PROMOTION_MIN_REPORTS:
            continue
        rej = sum(o == "rejected" for o in g["outcomes"])
        text = (f"{company} {role} round {rnd}: {n} seniors reported {label(topic)}"
                + (f" ({rej} of those {n} did not get the offer)" if rej else "")
                + f". Latest report {g['latest'][:10]}.")
        meta = {"round": rnd, "topic": topic, "role": role, "report_ids": sorted(g["reports"]),
                "observed_at": g["latest"]}
        if (rnd, topic) in known:
            k = known[(rnd, topic)]
            if k.source_count != n and k.status != "rejected":  # new corroboration → refresh
                # A retired pattern revived by fresh reports must be re-approved by a human.
                status = "proposed" if k.status == "stale" else k.status
                mem.update(k.id, requester=SYSTEM, text=text, source_count=n, status=status,
                           meta={**k.meta, **meta})
                if status == "proposed" and k.status == "stale":
                    proposals.append(mem.get(k.id))
            continue
        proposals.append(mem.propose(Memory(scope=scope, kind="pattern", text=text, source_count=n,
                                            meta=meta)))
    return proposals


def pending(company: str) -> list[Memory]:
    return get_memory().list(company_scope(company), SYSTEM, kinds=["pattern"], statuses=("proposed",))
