"""Canonical topic tags, keyword detectors and a small offline question bank.

Topic tags are what memories, experiences and patterns are keyed on, so "Amazon R2 LRU cache"
from three different seniors collapses into one pattern.
"""
from __future__ import annotations

TOPICS: dict[str, dict] = {
    "lru_cache": {
        "label": "LRU cache design",
        "short": "the LRU cache",
        "keywords": ["lru", "least recently used", "cache eviction", "linkedhashmap"],
        "expect": ["hash", "doubly", "linked", "o(1)"],
        "questions": [
            "Design an LRU cache with get and put in O(1). Walk me through the data structures.",
            "Extend your LRU cache so each key can have a TTL. What changes?",
        ],
    },
    "time_complexity": {
        "label": "Explaining time complexity aloud",
        "short": "time complexity",
        "keywords": ["complexity", "big o", "big-o", "o(n", "o(1", "o(log"],
        "expect": ["o(", "worst", "space"],
        "questions": [
            "What is the time and space complexity of your last solution? Justify each term.",
        ],
    },
    "dbms_transactions": {
        "label": "DBMS transactions",
        "short": "transactions",
        "keywords": ["transaction", "acid", "isolation level", "commit", "rollback", "deadlock"],
        "expect": ["atomic", "isolation", "commit", "rollback", "lock"],
        "questions": [
            "Explain ACID with an example of a bank transfer. What can go wrong without isolation?",
            "What's the difference between READ COMMITTED and REPEATABLE READ? Give an anomaly each prevents.",
        ],
    },
    "dbms_normalization": {
        "label": "DBMS normalization",
        "keywords": ["normalization", "normal form", "3nf", "bcnf", "functional dependency"],
        "expect": ["dependency", "redundan", "3nf"],
        "questions": ["Normalize a students-courses-instructors table to 3NF and explain each step."],
    },
    "leadership_principles": {
        "label": "Leadership Principles (behavioural)",
        "keywords": ["leadership principle", "customer obsession", "ownership", "bias for action",
                     "dive deep", "star method", "behavioural", "behavioral"],
        "expect": ["situation", "task", "action", "result"],
        "questions": [
            "Tell me about a time you took ownership of something outside your responsibility. (STAR)",
            "Tell me about a time you disagreed with a teammate and how it was resolved.",
        ],
    },
    "project_explanation": {
        "label": "Explaining your own project",
        "keywords": ["your project", "project", "resume", "internship work"],
        "expect": ["problem", "built", "challenge", "result"],
        "questions": ["Pick one project on your resume. What was the hardest technical decision and why?"],
    },
    "trees_graphs": {
        "label": "Trees and graphs",
        "keywords": ["tree", "graph", "bfs", "dfs", "binary tree", "topological"],
        "expect": ["bfs", "dfs", "visited", "o("],
        "questions": ["Find the lowest common ancestor of two nodes in a binary tree."],
    },
    "arrays_strings": {
        "label": "Arrays and strings",
        "keywords": ["array", "string", "two pointer", "sliding window", "subarray"],
        "expect": ["pointer", "window", "o("],
        "questions": ["Find the longest substring without repeating characters."],
    },
    "linked_lists": {
        "label": "Linked lists",
        "keywords": ["linked list", "reverse a list"],
        "expect": ["pointer", "next", "o("],
        "questions": ["Reverse a singly linked list, iteratively and recursively."],
    },
    "behavioral_intro": {
        "label": "Tell me about yourself",
        "keywords": ["tell me about yourself", "introduce yourself"],
        "expect": ["project", "interest"],
        "questions": ["Tell me about yourself."],
    },
    "system_design": {
        "label": "System design trade-offs",
        "keywords": ["system design", "scalab", "load balancer", "sharding", "trade-off"],
        "expect": ["trade", "scale", "cache", "database"],
        "questions": ["Design a URL shortener. Where are the bottlenecks?"],
    },
}

GENERIC_TOPICS = ["linked_lists", "behavioral_intro", "arrays_strings"]  # what a memoryless coach asks


def detect_topics(text: str) -> list[str]:
    t = text.lower()
    return [tag for tag, spec in TOPICS.items() if any(k in t for k in spec["keywords"])]


def label(tag: str) -> str:
    return TOPICS.get(tag, {}).get("label", tag.replace("_", " "))


def short(tag: str) -> str:
    """Noun phrase for sentences: 'you explained {short} much better'."""
    return TOPICS.get(tag, {}).get("short", label(tag).lower())
