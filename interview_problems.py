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
            # Check exact match or with hyphens as spaces
            if tag in text or tag.replace("-", " ") in text:
                score += 1
            # Check singular form (e.g., "graphs" -> "graph")
            elif tag.endswith("s") and tag[:-1] in text:
                score += 1
        if score > 0:
            scored.append((score, problem))

    scored.sort(key=lambda pair: -pair[0])
    matched = [problem for _, problem in scored[:limit]]

    if matched:
        return matched
    return _DEFAULT_PROBLEMS[:limit]
