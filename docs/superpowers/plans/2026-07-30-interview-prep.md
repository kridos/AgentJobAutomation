# Interview Prep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `automator prep <company>` locates an existing application and generates `interview_prep.md` in that application's output folder: company/role research, hallucination-checked likely questions + STAR-format resume talking points, and a curated set of relevant technical practice problems.

**Architecture:** `interview_problems.py` owns a bundled, curated list of well-known problems (title/tags/difficulty/link only, never full problem text) with deterministic keyword-tag matching — no LLM involved. `interview_prep.py` locates the application, reuses `researcher.research()` and `generator`'s context-loading/Ollama-calling helpers, and validates generated content via the same `factual_validator.validate_outputs(content, content, listing)` reuse trick `outreach.py` established. `automator/cli.py` gains one thin `prep` subcommand.

**Tech Stack:** Python 3.10+, stdlib only for `interview_problems.py` — no new dependencies anywhere in this plan.

## Global Constraints

- `interview_problems.py`'s bundled list contains only problem titles, topic tags, difficulty, and a lookup link — never the full problem statement (that's the source site's content, not this project's to redistribute).
- `match_problems` never raises and never returns an empty list — it falls back to a fixed default set when nothing scores above zero, so the practice-problems section is unconditionally present in generated output.
- Generated prep content (questions + talking points) is validated exactly like cold-outreach emails: `validate_outputs(content, content, listing, ...)`, one corrective retry, and the run is blocked (not saved) if validation still fails — never save unvalidated content.
- `_find_application` never raises on zero matches — returns `None`, and the CLI turns that into a clear non-zero-exit error message.
- No new runtime dependencies.

---

### Task 1: interview_problems.py — curated problem list + matching

**Files:**
- Create: `interview_problems.py`
- Test: `tests/test_interview_problems.py`

**Interfaces:**
- Consumes: nothing (standalone, stdlib only).
- Produces: `interview_problems.match_problems(job_description: str, limit: int = 8) -> list[dict]` (each dict shaped `{"title": str, "tags": list[str], "difficulty": str, "link": str}`) — consumed by Task 2's `interview_prep.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_interview_problems.py`:

```python
import interview_problems


def test_match_problems_matches_by_tag_keyword():
    result = interview_problems.match_problems(
        "We do a lot of graph traversal and BFS/DFS work on our backend team.",
        limit=5,
    )

    titles = [p["title"] for p in result]
    assert any(p["title"] == "Number of Islands" for p in result) or any(
        "graphs" in p["tags"] for p in result
    )
    assert len(result) <= 5


def test_match_problems_falls_back_to_default_set_when_no_match():
    result = interview_problems.match_problems("We value great communication and teamwork.", limit=8)

    assert len(result) > 0
    assert len(result) <= 8


def test_match_problems_respects_limit():
    result = interview_problems.match_problems(
        "arrays hash-map dynamic-programming graphs trees strings linked-list intervals",
        limit=3,
    )

    assert len(result) == 3


def test_match_problems_returns_expected_shape():
    result = interview_problems.match_problems("arrays and hash maps", limit=1)

    assert len(result) == 1
    problem = result[0]
    assert set(problem.keys()) == {"title", "tags", "difficulty", "link"}
    assert isinstance(problem["tags"], list)
    assert problem["link"].startswith("https://leetcode.com/problems/")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_interview_problems.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'interview_problems'`

- [ ] **Step 3: Create interview_problems.py**

Create `interview_problems.py`:

```python
"""
A curated, bundled list of well-known technical interview practice
problems (title + topic tags + difficulty + a lookup link only — never
the full problem statement) with deterministic keyword-tag matching
against a job description. No LLM involvement.
"""

_PROBLEMS = [
    # Array
    {"title": "Two Sum", "tags": ["arrays", "hash-map"], "difficulty": "easy", "link": "https://leetcode.com/problems/two-sum/"},
    {"title": "Best Time to Buy and Sell Stock", "tags": ["arrays", "dynamic-programming"], "difficulty": "easy", "link": "https://leetcode.com/problems/best-time-to-buy-and-sell-stock/"},
    {"title": "Contains Duplicate", "tags": ["arrays", "hash-map"], "difficulty": "easy", "link": "https://leetcode.com/problems/contains-duplicate/"},
    {"title": "Product of Array Except Self", "tags": ["arrays"], "difficulty": "medium", "link": "https://leetcode.com/problems/product-of-array-except-self/"},
    {"title": "Maximum Subarray", "tags": ["arrays", "dynamic-programming"], "difficulty": "medium", "link": "https://leetcode.com/problems/maximum-subarray/"},
    {"title": "Maximum Product Subarray", "tags": ["arrays", "dynamic-programming"], "difficulty": "medium", "link": "https://leetcode.com/problems/maximum-product-subarray/"},
    {"title": "Find Minimum in Rotated Sorted Array", "tags": ["arrays", "binary-search"], "difficulty": "medium", "link": "https://leetcode.com/problems/find-minimum-in-rotated-sorted-array/"},
    {"title": "Search in Rotated Sorted Array", "tags": ["arrays", "binary-search"], "difficulty": "medium", "link": "https://leetcode.com/problems/search-in-rotated-sorted-array/"},
    {"title": "3Sum", "tags": ["arrays", "two-pointers"], "difficulty": "medium", "link": "https://leetcode.com/problems/3sum/"},
    {"title": "Container With Most Water", "tags": ["arrays", "two-pointers"], "difficulty": "medium", "link": "https://leetcode.com/problems/container-with-most-water/"},
    # Binary / bit manipulation
    {"title": "Sum of Two Integers", "tags": ["bit-manipulation"], "difficulty": "medium", "link": "https://leetcode.com/problems/sum-of-two-integers/"},
    {"title": "Number of 1 Bits", "tags": ["bit-manipulation"], "difficulty": "easy", "link": "https://leetcode.com/problems/number-of-1-bits/"},
    {"title": "Counting Bits", "tags": ["bit-manipulation", "dynamic-programming"], "difficulty": "easy", "link": "https://leetcode.com/problems/counting-bits/"},
    {"title": "Missing Number", "tags": ["bit-manipulation", "arrays"], "difficulty": "easy", "link": "https://leetcode.com/problems/missing-number/"},
    {"title": "Reverse Bits", "tags": ["bit-manipulation"], "difficulty": "easy", "link": "https://leetcode.com/problems/reverse-bits/"},
    # Dynamic programming
    {"title": "Climbing Stairs", "tags": ["dynamic-programming"], "difficulty": "easy", "link": "https://leetcode.com/problems/climbing-stairs/"},
    {"title": "Coin Change", "tags": ["dynamic-programming"], "difficulty": "medium", "link": "https://leetcode.com/problems/coin-change/"},
    {"title": "Longest Increasing Subsequence", "tags": ["dynamic-programming"], "difficulty": "medium", "link": "https://leetcode.com/problems/longest-increasing-subsequence/"},
    {"title": "Longest Common Subsequence", "tags": ["dynamic-programming"], "difficulty": "medium", "link": "https://leetcode.com/problems/longest-common-subsequence/"},
    {"title": "Word Break", "tags": ["dynamic-programming"], "difficulty": "medium", "link": "https://leetcode.com/problems/word-break/"},
    {"title": "Combination Sum IV", "tags": ["dynamic-programming"], "difficulty": "medium", "link": "https://leetcode.com/problems/combination-sum-iv/"},
    {"title": "House Robber", "tags": ["dynamic-programming"], "difficulty": "medium", "link": "https://leetcode.com/problems/house-robber/"},
    {"title": "House Robber II", "tags": ["dynamic-programming"], "difficulty": "medium", "link": "https://leetcode.com/problems/house-robber-ii/"},
    {"title": "Decode Ways", "tags": ["dynamic-programming"], "difficulty": "medium", "link": "https://leetcode.com/problems/decode-ways/"},
    {"title": "Unique Paths", "tags": ["dynamic-programming"], "difficulty": "medium", "link": "https://leetcode.com/problems/unique-paths/"},
    {"title": "Jump Game", "tags": ["dynamic-programming", "greedy"], "difficulty": "medium", "link": "https://leetcode.com/problems/jump-game/"},
    # Graph
    {"title": "Clone Graph", "tags": ["graphs"], "difficulty": "medium", "link": "https://leetcode.com/problems/clone-graph/"},
    {"title": "Course Schedule", "tags": ["graphs"], "difficulty": "medium", "link": "https://leetcode.com/problems/course-schedule/"},
    {"title": "Pacific Atlantic Water Flow", "tags": ["graphs"], "difficulty": "medium", "link": "https://leetcode.com/problems/pacific-atlantic-water-flow/"},
    {"title": "Number of Islands", "tags": ["graphs"], "difficulty": "medium", "link": "https://leetcode.com/problems/number-of-islands/"},
    {"title": "Longest Consecutive Sequence", "tags": ["arrays", "hash-map"], "difficulty": "medium", "link": "https://leetcode.com/problems/longest-consecutive-sequence/"},
    {"title": "Alien Dictionary", "tags": ["graphs"], "difficulty": "hard", "link": "https://leetcode.com/problems/alien-dictionary/"},
    {"title": "Graph Valid Tree", "tags": ["graphs"], "difficulty": "medium", "link": "https://leetcode.com/problems/graph-valid-tree/"},
    {"title": "Number of Connected Components in an Undirected Graph", "tags": ["graphs"], "difficulty": "medium", "link": "https://leetcode.com/problems/number-of-connected-components-in-an-undirected-graph/"},
    # Interval
    {"title": "Insert Interval", "tags": ["intervals"], "difficulty": "medium", "link": "https://leetcode.com/problems/insert-interval/"},
    {"title": "Merge Intervals", "tags": ["intervals"], "difficulty": "medium", "link": "https://leetcode.com/problems/merge-intervals/"},
    {"title": "Non-overlapping Intervals", "tags": ["intervals", "greedy"], "difficulty": "medium", "link": "https://leetcode.com/problems/non-overlapping-intervals/"},
    {"title": "Meeting Rooms", "tags": ["intervals"], "difficulty": "easy", "link": "https://leetcode.com/problems/meeting-rooms/"},
    {"title": "Meeting Rooms II", "tags": ["intervals", "heap"], "difficulty": "medium", "link": "https://leetcode.com/problems/meeting-rooms-ii/"},
    # Linked list
    {"title": "Reverse Linked List", "tags": ["linked-list"], "difficulty": "easy", "link": "https://leetcode.com/problems/reverse-linked-list/"},
    {"title": "Linked List Cycle", "tags": ["linked-list", "two-pointers"], "difficulty": "easy", "link": "https://leetcode.com/problems/linked-list-cycle/"},
    {"title": "Merge Two Sorted Lists", "tags": ["linked-list"], "difficulty": "easy", "link": "https://leetcode.com/problems/merge-two-sorted-lists/"},
    {"title": "Merge k Sorted Lists", "tags": ["linked-list", "heap"], "difficulty": "hard", "link": "https://leetcode.com/problems/merge-k-sorted-lists/"},
    {"title": "Remove Nth Node From End of List", "tags": ["linked-list", "two-pointers"], "difficulty": "medium", "link": "https://leetcode.com/problems/remove-nth-node-from-end-of-list/"},
    {"title": "Reorder List", "tags": ["linked-list", "two-pointers"], "difficulty": "medium", "link": "https://leetcode.com/problems/reorder-list/"},
    # Matrix
    {"title": "Set Matrix Zeroes", "tags": ["matrix"], "difficulty": "medium", "link": "https://leetcode.com/problems/set-matrix-zeroes/"},
    {"title": "Spiral Matrix", "tags": ["matrix"], "difficulty": "medium", "link": "https://leetcode.com/problems/spiral-matrix/"},
    {"title": "Rotate Image", "tags": ["matrix"], "difficulty": "medium", "link": "https://leetcode.com/problems/rotate-image/"},
    {"title": "Word Search", "tags": ["matrix", "backtracking"], "difficulty": "medium", "link": "https://leetcode.com/problems/word-search/"},
    # String
    {"title": "Longest Substring Without Repeating Characters", "tags": ["strings", "sliding-window"], "difficulty": "medium", "link": "https://leetcode.com/problems/longest-substring-without-repeating-characters/"},
    {"title": "Longest Repeating Character Replacement", "tags": ["strings", "sliding-window"], "difficulty": "medium", "link": "https://leetcode.com/problems/longest-repeating-character-replacement/"},
    {"title": "Minimum Window Substring", "tags": ["strings", "sliding-window"], "difficulty": "hard", "link": "https://leetcode.com/problems/minimum-window-substring/"},
    {"title": "Valid Anagram", "tags": ["strings", "hash-map"], "difficulty": "easy", "link": "https://leetcode.com/problems/valid-anagram/"},
    {"title": "Group Anagrams", "tags": ["strings", "hash-map"], "difficulty": "medium", "link": "https://leetcode.com/problems/group-anagrams/"},
    {"title": "Valid Parentheses", "tags": ["strings", "stack"], "difficulty": "easy", "link": "https://leetcode.com/problems/valid-parentheses/"},
    {"title": "Valid Palindrome", "tags": ["strings", "two-pointers"], "difficulty": "easy", "link": "https://leetcode.com/problems/valid-palindrome/"},
    {"title": "Longest Palindromic Substring", "tags": ["strings", "dynamic-programming"], "difficulty": "medium", "link": "https://leetcode.com/problems/longest-palindromic-substring/"},
    {"title": "Palindromic Substrings", "tags": ["strings", "dynamic-programming"], "difficulty": "medium", "link": "https://leetcode.com/problems/palindromic-substrings/"},
    {"title": "Encode and Decode Strings", "tags": ["strings"], "difficulty": "medium", "link": "https://leetcode.com/problems/encode-and-decode-strings/"},
    # Tree
    {"title": "Maximum Depth of Binary Tree", "tags": ["trees"], "difficulty": "easy", "link": "https://leetcode.com/problems/maximum-depth-of-binary-tree/"},
    {"title": "Same Tree", "tags": ["trees"], "difficulty": "easy", "link": "https://leetcode.com/problems/same-tree/"},
    {"title": "Invert Binary Tree", "tags": ["trees"], "difficulty": "easy", "link": "https://leetcode.com/problems/invert-binary-tree/"},
    {"title": "Binary Tree Maximum Path Sum", "tags": ["trees"], "difficulty": "hard", "link": "https://leetcode.com/problems/binary-tree-maximum-path-sum/"},
    {"title": "Binary Tree Level Order Traversal", "tags": ["trees"], "difficulty": "medium", "link": "https://leetcode.com/problems/binary-tree-level-order-traversal/"},
    {"title": "Serialize and Deserialize Binary Tree", "tags": ["trees"], "difficulty": "hard", "link": "https://leetcode.com/problems/serialize-and-deserialize-binary-tree/"},
    {"title": "Subtree of Another Tree", "tags": ["trees"], "difficulty": "easy", "link": "https://leetcode.com/problems/subtree-of-another-tree/"},
    {"title": "Construct Binary Tree from Preorder and Inorder Traversal", "tags": ["trees"], "difficulty": "medium", "link": "https://leetcode.com/problems/construct-binary-tree-from-preorder-and-inorder-traversal/"},
    {"title": "Validate Binary Search Tree", "tags": ["trees"], "difficulty": "medium", "link": "https://leetcode.com/problems/validate-binary-search-tree/"},
    {"title": "Kth Smallest Element in a BST", "tags": ["trees", "binary-search"], "difficulty": "medium", "link": "https://leetcode.com/problems/kth-smallest-element-in-a-bst/"},
    {"title": "Lowest Common Ancestor of a Binary Search Tree", "tags": ["trees"], "difficulty": "medium", "link": "https://leetcode.com/problems/lowest-common-ancestor-of-a-binary-search-tree/"},
    {"title": "Implement Trie (Prefix Tree)", "tags": ["trees", "tries"], "difficulty": "medium", "link": "https://leetcode.com/problems/implement-trie-prefix-tree/"},
    {"title": "Design Add and Search Words Data Structure", "tags": ["trees", "tries"], "difficulty": "medium", "link": "https://leetcode.com/problems/design-add-and-search-words-data-structure/"},
    {"title": "Word Search II", "tags": ["trees", "tries", "backtracking"], "difficulty": "hard", "link": "https://leetcode.com/problems/word-search-ii/"},
    # Heap
    {"title": "Top K Frequent Elements", "tags": ["heap", "hash-map"], "difficulty": "medium", "link": "https://leetcode.com/problems/top-k-frequent-elements/"},
    {"title": "Find Median from Data Stream", "tags": ["heap"], "difficulty": "hard", "link": "https://leetcode.com/problems/find-median-from-data-stream/"},
]

_DEFAULT_PROBLEMS = [
    {"title": "Two Sum", "tags": ["arrays", "hash-map"], "difficulty": "easy", "link": "https://leetcode.com/problems/two-sum/"},
    {"title": "Valid Parentheses", "tags": ["strings", "stack"], "difficulty": "easy", "link": "https://leetcode.com/problems/valid-parentheses/"},
    {"title": "Merge Two Sorted Lists", "tags": ["linked-list"], "difficulty": "easy", "link": "https://leetcode.com/problems/merge-two-sorted-lists/"},
    {"title": "Maximum Subarray", "tags": ["arrays", "dynamic-programming"], "difficulty": "medium", "link": "https://leetcode.com/problems/maximum-subarray/"},
    {"title": "Binary Tree Level Order Traversal", "tags": ["trees"], "difficulty": "medium", "link": "https://leetcode.com/problems/binary-tree-level-order-traversal/"},
    {"title": "Number of Islands", "tags": ["graphs"], "difficulty": "medium", "link": "https://leetcode.com/problems/number-of-islands/"},
    {"title": "Climbing Stairs", "tags": ["dynamic-programming"], "difficulty": "easy", "link": "https://leetcode.com/problems/climbing-stairs/"},
    {"title": "Longest Substring Without Repeating Characters", "tags": ["strings", "sliding-window"], "difficulty": "medium", "link": "https://leetcode.com/problems/longest-substring-without-repeating-characters/"},
]


def match_problems(job_description: str, limit: int = 8) -> list[dict]:
    """Deterministically scores each bundled problem by how many of its
    tags appear as keywords in job_description (case-insensitive,
    hyphens optionally treated as spaces), returns the top `limit` by
    score. Falls back to a fixed, well-rounded default set when nothing
    scores above zero — never raises, never returns an empty list."""
    text = job_description.lower()
    scored = []
    for problem in _PROBLEMS:
        score = 0
        for tag in problem["tags"]:
            if tag in text or tag.replace("-", " ") in text:
                score += 1
        if score > 0:
            scored.append((score, problem))

    scored.sort(key=lambda pair: -pair[0])
    matched = [problem for _, problem in scored[:limit]]

    if matched:
        return matched
    return _DEFAULT_PROBLEMS[:limit]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_interview_problems.py -v`
Expected: 4 tests PASS

- [ ] **Step 5: Run the full test suite as a regression check**

Run: `pytest tests/ -v`
Expected: All tests PASS — `interview_problems.py` is a new standalone module, no existing file modified.

- [ ] **Step 6: Commit**

```bash
git add interview_problems.py tests/test_interview_problems.py
git commit -m "feat: add curated interview practice problem list with keyword matching"
```

---

### Task 2: interview_prep.py — application lookup + generation + validation

**Files:**
- Create: `interview_prep.py`
- Test: `tests/test_interview_prep.py`

**Interfaces:**
- Consumes: `interview_problems.match_problems(job_description: str, limit: int = 8) -> list[dict]` (Task 1); `generator._call_ollama(prompt: str, model: str = ..., base_url: str = ..., temperature: float = 0.7, max_tokens: int = 4096) -> str` and `generator._load_context_files() -> dict[str, str]` (existing, unchanged); `factual_validator.validate_outputs(resume_md: str, cover_md: str, listing: dict, model: str = ..., base_url: str = ..., semantic_check: bool = True) -> dict` and `factual_validator.format_validation_feedback(result: dict) -> str` (existing, unchanged); `researcher.research(company: str, role: str, timeout_seconds: int = 30) -> str` (existing, unchanged).
- Produces: `interview_prep.generate_interview_prep(company: str, role_hint: str = "") -> dict` (returns `{"status": "ok"|"not_found"|"validation_blocked", "path": str|None}`) — consumed by Task 3's CLI wiring. Also produces `interview_prep._find_application(company: str, role_hint: str = "") -> Path | None`, used only internally by this task's own tests.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_interview_prep.py` (uses `tmp_path` + `monkeypatch.chdir` to build a fake `output/` tree, matching the established convention in `tests/test_pipeline_limit.py`):

```python
import json
from pathlib import Path

import interview_prep


def _write_application(date: str, source: str, company_slug: str, role_slug: str, role: str = "Software Engineer Intern", job_description: str = "") -> Path:
    app_dir = Path("output") / date / source / company_slug / role_slug
    app_dir.mkdir(parents=True, exist_ok=True)
    listing = {"company": "Acme Corp", "role": role, "location": "Remote", "link": "https://acme.com", "date_posted": date, "id": f"{company_slug}-{role_slug}"}
    (app_dir / "listing.json").write_text(json.dumps(listing), encoding="utf-8")
    if job_description:
        (app_dir / "job_description.txt").write_text(job_description, encoding="utf-8")
    return app_dir


def test_find_application_returns_single_match(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    expected = _write_application("2026-07-01", "simplify", "acme_corp", "swe_intern")

    result = interview_prep._find_application("Acme Corp")

    assert result == expected


def test_find_application_returns_most_recent_of_multiple_matches(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_application("2026-01-01", "simplify", "acme_corp", "swe_intern")
    newest = _write_application("2026-07-01", "simplify", "acme_corp", "ml_intern")

    result = interview_prep._find_application("Acme Corp")

    assert result == newest


def test_find_application_returns_none_when_no_match(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = interview_prep._find_application("Nonexistent Co")

    assert result is None


def test_generate_interview_prep_returns_not_found_without_generation_calls(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(interview_prep, "_find_application", lambda company, role_hint="": None)

    research_calls = []
    monkeypatch.setattr(interview_prep, "research", lambda *a, **k: research_calls.append(1) or "")
    ollama_calls = []
    monkeypatch.setattr(interview_prep, "_call_ollama", lambda *a, **k: ollama_calls.append(1) or "")

    result = interview_prep.generate_interview_prep("Nonexistent Co")

    assert result == {"status": "not_found", "path": None}
    assert research_calls == []
    assert ollama_calls == []


def test_generate_interview_prep_blocks_on_repeated_validation_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app_dir = _write_application("2026-07-01", "simplify", "acme_corp", "swe_intern")
    monkeypatch.setattr(interview_prep, "_find_application", lambda company, role_hint="": app_dir)
    monkeypatch.setattr(interview_prep, "research", lambda *a, **k: "")
    monkeypatch.setattr(interview_prep, "_load_context_files", lambda: {"resume_master": "", "voice": "", "preferences": "", "accomplishments": "", "recent_updates": ""})
    monkeypatch.setattr(interview_prep, "_call_ollama", lambda *a, **k: "bad content")
    monkeypatch.setattr(
        interview_prep, "validate_outputs",
        lambda *a, **k: {"passed": False, "violation_count": 1, "categories": ["x"], "violations": [{"category": "x", "claim": "y", "reason": "z"}]},
    )

    result = interview_prep.generate_interview_prep("Acme Corp")

    assert result == {"status": "validation_blocked", "path": None}
    assert not (app_dir / "interview_prep.md").exists()


def test_generate_interview_prep_writes_all_sections_on_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app_dir = _write_application("2026-07-01", "simplify", "acme_corp", "swe_intern", job_description="graphs and dynamic programming")
    monkeypatch.setattr(interview_prep, "_find_application", lambda company, role_hint="": app_dir)
    monkeypatch.setattr(interview_prep, "research", lambda *a, **k: "Acme Corp builds widgets.")
    monkeypatch.setattr(interview_prep, "_load_context_files", lambda: {"resume_master": "", "voice": "", "preferences": "", "accomplishments": "", "recent_updates": ""})
    monkeypatch.setattr(interview_prep, "_call_ollama", lambda *a, **k: "## Likely Questions & Talking Points\n- Q: Why Acme?")
    monkeypatch.setattr(interview_prep, "validate_outputs", lambda *a, **k: {"passed": True, "violation_count": 0, "categories": [], "violations": []})
    monkeypatch.setattr(interview_prep, "match_problems", lambda job_description, limit=8: [{"title": "Number of Islands", "tags": ["graphs"], "difficulty": "medium", "link": "https://leetcode.com/problems/number-of-islands/"}])

    result = interview_prep.generate_interview_prep("Acme Corp")

    assert result["status"] == "ok"
    content = (app_dir / "interview_prep.md").read_text(encoding="utf-8")
    assert "Acme Corp builds widgets." in content
    assert "Likely Questions & Talking Points" in content
    assert "Number of Islands" in content
    assert "## Practice Problems" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_interview_prep.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'interview_prep'`

- [ ] **Step 3: Create interview_prep.py**

Create `interview_prep.py`:

```python
"""
Generates hallucination-checked interview prep material for an existing
application: company/role research, likely questions with STAR-format
resume talking points, and curated technical practice problems.
Run standalone: python interview_prep.py "Acme Corp"
"""

import json
import re
import sys
from pathlib import Path

import yaml

from generator import _call_ollama, _load_context_files, DEFAULT_MODEL, OLLAMA_BASE_URL
from factual_validator import validate_outputs, format_validation_feedback
from researcher import research
from interview_problems import match_problems


CONFIG_PATH = Path(__file__).parent / "config.yaml"


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _find_application(company: str, role_hint: str = "") -> Path | None:
    """Globs output/*/*/<company-slug>/*/listing.json for the slugified
    company name, optionally filtered by role_hint (substring match
    against listing.json's role field). Returns the most recent match's
    directory, or None if no match. Prints disambiguation info when
    multiple matches exist."""
    company_slug = _slugify(company)
    output_base = Path("output")
    if not output_base.exists():
        return None

    matches = []
    for listing_path in output_base.glob(f"*/*/{company_slug}/*/listing.json"):
        try:
            listing = json.loads(listing_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if role_hint and role_hint.lower() not in listing.get("role", "").lower():
            continue
        matches.append(listing_path.parent)

    if not matches:
        return None

    matches.sort(key=lambda p: p.parts[1] if len(p.parts) > 1 else "", reverse=True)

    if len(matches) > 1:
        print(f"[interview_prep] Found {len(matches)} matching applications for '{company}':", flush=True)
        for m in matches:
            print(f"  {m}", flush=True)
        print(f"[interview_prep] Using most recent: {matches[0]}", flush=True)

    return matches[0]


def _build_prep_prompt(
    context: dict,
    listing: dict,
    job_description: str,
    research_context: str,
    validation_feedback: str = "",
) -> str:
    company = listing.get("company", "")
    role = listing.get("role", "")

    parts = [
        "You are an interview-prep coach helping a candidate prepare for a real upcoming interview.",
        "",
        f"## Target\n**Company:** {company}\n**Role:** {role}",
        "",
        "## My Background (for facts/context)\n" + context.get("resume_master", ""),
    ]

    if context.get("accomplishments"):
        parts += ["", "## Recent Accomplishments\n" + context["accomplishments"]]

    if job_description:
        parts += ["", "## Job Posting\n" + job_description]

    if research_context:
        parts += ["", "## Company/Role Research\n" + research_context]

    parts += [
        "",
        "## Instructions",
        "- HARD RULE: Do not invent or alter personal identity details (name, phone, email, links)",
        "- HARD RULE: Do not invent qualifications, degrees, GPA, employers, projects, dates, tools, metrics, awards, or responsibilities",
        "- HARD RULE: If a detail is not explicitly present in My Background above, omit it",
        "- Write 6-10 likely interview questions: a mix of behavioral and role-specific technical/situational questions, tailored to the job posting and company research above",
        "- For each question, write a brief STAR-format (Situation/Task/Action/Result) talking point using ONLY real experience from My Background — if no real experience genuinely fits a question, say so explicitly rather than inventing one",
        "- Output ONLY markdown: a '## Likely Questions & Talking Points' heading followed by the questions and talking points, no preamble or explanation",
    ]

    if validation_feedback:
        parts += [
            "",
            "## Validation Corrections (must fix all)",
            validation_feedback,
            "Revise to remove or correct unsupported claims while preserving the question/talking-point structure.",
        ]

    return "\n".join(parts)


def generate_interview_prep(company: str, role_hint: str = "") -> dict:
    """Orchestrates: find the application, research the company, generate
    + validate questions/talking-points, match technical problems, save
    interview_prep.md. Returns {"status": "ok"|"not_found"|"validation_blocked",
    "path": str|None}."""
    app_dir = _find_application(company, role_hint)
    if app_dir is None:
        return {"status": "not_found", "path": None}

    listing = json.loads((app_dir / "listing.json").read_text(encoding="utf-8"))

    job_description = ""
    jd_path = app_dir / "job_description.txt"
    if jd_path.exists():
        job_description = jd_path.read_text(encoding="utf-8")

    config = _load_config()
    ollama_cfg = config.get("ollama", {})
    research_cfg = config.get("research", {})
    model = ollama_cfg.get("model", "qwen3:14b")
    base_url = ollama_cfg.get("base_url", "http://localhost:11434")
    temperature = ollama_cfg.get("temperature", 0.7)
    semantic_check = config.get("validation", {}).get("semantic_check", True)

    research_context = ""
    if research_cfg.get("enabled", True):
        try:
            research_context = research(
                listing.get("company", company), listing.get("role", ""),
                research_cfg.get("timeout_seconds", 30),
            )
        except Exception as e:
            print(f"[interview_prep] Research failed (non-fatal): {e}", file=sys.stderr)

    context = _load_context_files()

    content = _call_ollama(
        _build_prep_prompt(context, listing, job_description, research_context),
        model=model, base_url=base_url, temperature=temperature,
    ).strip()

    validation = validate_outputs(content, content, listing, model=model, base_url=base_url, semantic_check=semantic_check)

    if not validation.get("passed", False):
        feedback = format_validation_feedback(validation)
        retry_temp = min(float(temperature), 0.2)
        print(f"[interview_prep] Validation failed. Retrying once...", flush=True)
        content = _call_ollama(
            _build_prep_prompt(context, listing, job_description, research_context, validation_feedback=feedback),
            model=model, base_url=base_url, temperature=retry_temp,
        ).strip()
        validation = validate_outputs(content, content, listing, model=model, base_url=base_url, semantic_check=semantic_check)

        if not validation.get("passed", False):
            msg = f"Validation blocked: {validation.get('violation_count', 0)} unsupported claim(s)"
            print(f"[interview_prep] ERROR: {msg}", file=sys.stderr)
            return {"status": "validation_blocked", "path": None}

    problems = match_problems(job_description or listing.get("role", ""))
    problems_md = "\n".join(
        f"- **{p['title']}** ({p['difficulty']}, {', '.join(p['tags'])}) — {p['link']}"
        for p in problems
    )

    research_section = f"## Company Research\n{research_context}\n\n" if research_context else ""
    full_md = f"{research_section}{content}\n\n## Practice Problems\n{problems_md}\n"

    output_path = app_dir / "interview_prep.md"
    output_path.write_text(full_md, encoding="utf-8")

    return {"status": "ok", "path": str(output_path)}


if __name__ == "__main__":
    company_arg = sys.argv[1] if len(sys.argv) > 1 else "Stripe"
    result = generate_interview_prep(company_arg)
    print(result)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_interview_prep.py -v`
Expected: 6 tests PASS

- [ ] **Step 5: Run the full test suite as a regression check**

Run: `pytest tests/ -v`
Expected: All tests PASS — `interview_prep.py` is a new module, no existing file modified.

- [ ] **Step 6: Commit**

```bash
git add interview_prep.py tests/test_interview_prep.py
git commit -m "feat: add interview_prep.py application lookup, generation, and validation"
```

---

### Task 3: CLI wiring — automator prep

**Files:**
- Modify: `automator/cli.py` (add `prep` subcommand)
- Modify: `pyproject.toml:14-18` (add `"interview_prep"`, `"interview_problems"` to `py-modules`)
- Modify: `README.md` (add `automator prep` usage example)
- Test: `tests/test_cli_prep.py`

**Interfaces:**
- Consumes: `interview_prep.generate_interview_prep(company: str, role_hint: str = "") -> dict` (Task 2, returns `{"status": "ok"|"not_found"|"validation_blocked", "path": str|None}`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_prep.py`:

```python
import pytest

from automator.cli import build_parser


def test_prep_dispatches_to_generate_interview_prep_and_prints_path(monkeypatch, capsys):
    monkeypatch.setattr(
        "interview_prep.generate_interview_prep",
        lambda company, role_hint="": {"status": "ok", "path": "output/2026-07-01/simplify/acme_corp/swe_intern/interview_prep.md"},
    )

    parser = build_parser()
    args = parser.parse_args(["prep", "Acme Corp"])
    args.func(args)

    captured = capsys.readouterr()
    assert "interview_prep.md" in captured.out


def test_prep_passes_role_flag_through(monkeypatch):
    captured_kwargs = {}

    def _fake_generate(company, role_hint=""):
        captured_kwargs["company"] = company
        captured_kwargs["role_hint"] = role_hint
        return {"status": "ok", "path": "some/path.md"}

    monkeypatch.setattr("interview_prep.generate_interview_prep", _fake_generate)

    parser = build_parser()
    args = parser.parse_args(["prep", "Acme Corp", "--role", "ML Intern"])
    args.func(args)

    assert captured_kwargs["company"] == "Acme Corp"
    assert captured_kwargs["role_hint"] == "ML Intern"


def test_prep_exits_nonzero_on_not_found(monkeypatch):
    monkeypatch.setattr(
        "interview_prep.generate_interview_prep",
        lambda company, role_hint="": {"status": "not_found", "path": None},
    )

    parser = build_parser()
    args = parser.parse_args(["prep", "Nonexistent Co"])

    with pytest.raises(SystemExit):
        args.func(args)


def test_prep_exits_nonzero_on_validation_blocked(monkeypatch):
    monkeypatch.setattr(
        "interview_prep.generate_interview_prep",
        lambda company, role_hint="": {"status": "validation_blocked", "path": None},
    )

    parser = build_parser()
    args = parser.parse_args(["prep", "Acme Corp"])

    with pytest.raises(SystemExit):
        args.func(args)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli_prep.py -v`
Expected: FAIL — `argparse` error, `prep` is not a recognized subcommand

- [ ] **Step 3: Add the CLI handler**

In `automator/cli.py`, immediately after `_cmd_gui` (currently ending at line 106, right before `def build_parser`), add:

```python
def _cmd_prep(args: argparse.Namespace) -> None:
    from interview_prep import generate_interview_prep

    result = generate_interview_prep(args.company, role_hint=args.role or "")

    if result["status"] == "ok":
        print(f"Interview prep saved to: {result['path']}")
    elif result["status"] == "not_found":
        print(f"No application found for '{args.company}'. Run `automator run` first, or check the company name.", file=sys.stderr)
        sys.exit(1)
    elif result["status"] == "validation_blocked":
        print("Interview prep generation blocked by validation — unsupported claims could not be resolved after retry.", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 4: Register the prep subcommand**

In `automator/cli.py`'s `build_parser()`, immediately after the `outreach_confirm_p` block (currently ending with `outreach_confirm_p.set_defaults(func=_cmd_outreach_confirm)`, right before the `test_p` block), add:

```python
    prep_p = subparsers.add_parser("prep", help="Generate interview prep material for an application")
    prep_p.add_argument("company", help="Company name (matches an existing application in output/)")
    prep_p.add_argument("--role", default="", help="Filter by role substring when multiple applications match")
    prep_p.set_defaults(func=_cmd_prep)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_cli_prep.py -v`
Expected: 4 tests PASS

- [ ] **Step 6: Add new modules to pyproject.toml's py-modules**

In `pyproject.toml`, change:

```toml
py-modules = [
    "pipeline", "generator", "researcher", "scraper", "gmail_reader",
    "job_fetcher", "factual_validator", "scorer", "archive_processed",
    "manual_run", "crawl4ai_scraper", "accomplishments", "outreach",
    "yc_scraper", "email_verify",
]
```

to:

```toml
py-modules = [
    "pipeline", "generator", "researcher", "scraper", "gmail_reader",
    "job_fetcher", "factual_validator", "scorer", "archive_processed",
    "manual_run", "crawl4ai_scraper", "accomplishments", "outreach",
    "yc_scraper", "email_verify", "interview_prep", "interview_problems",
]
```

- [ ] **Step 7: Update README.md usage section**

In `README.md`, add this example near the other `automator` usage examples (immediately after the `automator outreach confirm <contact-id> <email>` line, or wherever the outreach examples end):

```
# Generate interview prep for an application you already made (research,
# likely questions with resume talking points, and practice problems)
automator prep "Acme Corp"
automator prep "Acme Corp" --role "ML Intern"   # disambiguate multiple matches
```

- [ ] **Step 8: Run the full test suite as a regression check**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 9: Commit**

```bash
git add automator/cli.py pyproject.toml README.md tests/test_cli_prep.py
git commit -m "feat: wire automator prep into the CLI"
```

---

## Self-Review Notes

- **Spec coverage:** Curated problem list (title/tags/difficulty/link only, never full problem text) + deterministic keyword matching + non-empty-never-raises fallback → Task 1. Application lookup with most-recent-match disambiguation → Task 2's `_find_application`. Research reuse (non-fatal) → Task 2's `generate_interview_prep`. Generation + validation with one corrective retry + block-on-repeated-failure → Task 2. CLI wiring, packaging, docs → Task 3. Error handling (not_found, validation_blocked, non-fatal research) → Task 2's return-shape and Task 3's status handling, both tested explicitly. Testing sections from the spec (all 3 test files' bullet points) → each task's Step 1.
- **Placeholder scan:** found and fixed one — Task 2 Step 1 originally had a leftover draft artifact (`Path_placeholder`) before the real test file; removed, Step 1 now contains only the complete, real test file.
- **Type consistency:** `match_problems(job_description: str, limit: int = 8) -> list[dict]` (Task 1) is imported and called identically in Task 2's `generate_interview_prep`. `generate_interview_prep(company: str, role_hint: str = "") -> dict` (Task 2) matches Task 3's CLI call site and test mocks exactly (`args.company`, `args.role`, `result["status"]`, `result["path"]`). `_find_application(company: str, role_hint: str = "") -> Path | None` is used identically across Task 2's own tests and implementation.
- **Task ordering:** Task 2 depends on Task 1's `match_problems`; Task 3 depends on Task 2's `generate_interview_prep` — sequential, matching subagent-driven-development's one-implementer-at-a-time execution.
