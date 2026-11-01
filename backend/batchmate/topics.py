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
            'Design an LRU cache with get and put in O(1). Walk me through the data structures.',
            'Extend your LRU cache so each key can have a TTL. What changes?',
            'How would you make your LRU cache thread-safe without one global lock becoming a bottleneck?',
            'Your LRU cache must hold 10 GB across 4 machines. How do you shard it, and what happens on a node failure?',
            'Implement an LFU cache instead. How do the data structures change compared with LRU?',
            'Why does an LRU cache need a doubly linked list rather than a singly linked one? Show the operation that breaks.',
        ],
    },
    "time_complexity": {
        "label": "Explaining time complexity aloud",
        "short": "time complexity",
        "keywords": ["complexity", "big o", "big-o", "o(n", "o(1", "o(log"],
        "expect": ["o(", "worst", "space"],
        "questions": [
            'What is the time and space complexity of your last solution? Justify each term.',
            'Your solution uses recursion. What is its space complexity once you count the call stack?',
            'Explain the amortised cost of appending to a dynamic array, step by step.',
            'Two loops: the inner one runs i times for i from 1 to n. Derive the complexity out loud.',
            'When is an O(n log n) algorithm slower than an O(n^2) one in practice? Give a concrete case.',
        ],
    },
    "dbms_transactions": {
        "label": "DBMS transactions",
        "short": "transactions",
        "keywords": ["transaction", "acid", "isolation level", "commit", "rollback", "deadlock"],
        "expect": ["atomic", "isolation", "commit", "rollback", "lock"],
        "questions": [
            'Explain ACID with an example of a bank transfer. What can go wrong without isolation?',
            "What's the difference between READ COMMITTED and REPEATABLE READ? Give an anomaly each prevents.",
            'Two transactions deadlock while updating the same two rows. How does the database detect it, and how would you prevent it?',
            'What is a phantom read, and which isolation level stops it?',
            'How does write-ahead logging let a database recover after a crash mid-transaction?',
            'Optimistic vs pessimistic locking: when would you choose each for a seat-booking system?',
        ],
    },
    "dbms_normalization": {
        "label": "DBMS normalization",
        "keywords": ["normalization", "normal form", "3nf", "bcnf", "functional dependency"],
        "expect": ["dependency", "redundan", "3nf"],
        "questions": [
            'Normalize a students-courses-instructors table to 3NF and explain each step.',
            'What is the difference between 3NF and BCNF? Give a table that is in 3NF but not BCNF.',
            'When would you deliberately denormalize a schema? What do you give up?',
            'Find the candidate keys of R(A, B, C, D) with A→B, B→C, C→D, D→A.',
            'What update anomalies does 2NF remove that 1NF still has? Show one with an example table.',
        ],
    },
    "leadership_principles": {
        "label": "Leadership Principles (behavioural)",
        "keywords": ["leadership principle", "customer obsession", "ownership", "bias for action",
                     "dive deep", "star method", "behavioural", "behavioral"],
        "expect": ["situation", "task", "action", "result"],
        "questions": [
            'Tell me about a time you took ownership of something outside your responsibility. (STAR)',
            'Tell me about a time you disagreed with a teammate and how it was resolved.',
            'Describe a time you had to make a decision with incomplete data. What did you do and what happened?',
            'Tell me about a time you failed. What did you learn, and what did you change afterwards?',
            'Give an example of when you went deep into a problem that others had given up on.',
            'Tell me about a time you put the customer, or the end user, ahead of an easier path.',
        ],
    },
    "project_explanation": {
        "label": "Explaining your own project",
        "keywords": ["your project", "project", "resume", "internship work"],
        "expect": ["problem", "built", "challenge", "result"],
        "questions": [
            'Pick one project on your resume. What was the hardest technical decision and why?',
            'If you rebuilt your main project today, what would you change in its design?',
            'How did you test your project, and what bug taught you the most?',
            "Explain your project's architecture to me as if I were a new teammate joining tomorrow.",
            'What would break first if your project had 100 times more users?',
        ],
    },
    "trees_graphs": {
        "label": "Trees and graphs",
        "keywords": ["tree", "graph", "bfs", "dfs", "binary tree", "topological"],
        "expect": ["bfs", "dfs", "visited", "o("],
        "questions": [
            'Find the lowest common ancestor of two nodes in a binary tree.',
            'Detect a cycle in a directed graph. Which traversal do you use and why?',
            'Given course prerequisites, find a valid order to take all courses.',
            'Serialize and deserialize a binary tree. Discuss the format you chose.',
            'Find the shortest path in a grid with obstacles. Why BFS rather than DFS?',
            "Check whether a binary tree is a valid binary search tree. What's the common mistake?",
        ],
    },
    "arrays_strings": {
        "label": "Arrays and strings",
        "keywords": ["array", "string", "two pointer", "sliding window", "subarray"],
        "expect": ["pointer", "window", "o("],
        "questions": [
            'Find the longest substring without repeating characters.',
            'Given an array, find the maximum sum of any contiguous subarray.',
            'Group a list of words into anagrams. What key do you use for each group?',
            'Find all pairs in an array that sum to a target. Do it in O(n).',
            'Merge overlapping intervals. Walk me through the sort and the merge.',
            'Find the minimum window in a string that contains all characters of another string.',
        ],
    },
    "linked_lists": {
        "label": "Linked lists",
        "keywords": ["linked list", "reverse a list"],
        "expect": ["pointer", "next", "o("],
        "questions": [
            'Reverse a singly linked list, iteratively and recursively.',
            'Detect whether a linked list has a cycle and find where it starts.',
            'Merge two sorted linked lists into one sorted list.',
            'Remove the nth node from the end of a linked list in one pass.',
            'Find the intersection point of two linked lists.',
        ],
    },
    "behavioral_intro": {
        "label": "Tell me about yourself",
        "keywords": ["tell me about yourself", "introduce yourself"],
        "expect": ["project", "interest"],
        "questions": [
            'Tell me about yourself.',
            'Why do you want this role in particular?',
            "What is one thing you've built that you're proud of, and why?",
            'Where do you want to be technically in two years?',
            'What did you learn from your most recent internship or project?',
        ],
    },
    "system_design": {
        "label": "System design trade-offs",
        "keywords": ["system design", "scalab", "load balancer", "sharding", "trade-off"],
        "expect": ["trade", "scale", "cache", "database"],
        "questions": [
            'Design a URL shortener. Where are the bottlenecks?',
            'Design a rate limiter for an API. Which algorithm, and where does it live?',
            'Design the backend for a food-delivery order tracker. How do updates reach the customer?',
            'Design a notification service that sends email, SMS and push. How do you handle retries?',
            'Design a leaderboard for a game with 10 million players. How do you keep ranks fresh?',
        ],
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
