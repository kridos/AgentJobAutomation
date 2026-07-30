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
