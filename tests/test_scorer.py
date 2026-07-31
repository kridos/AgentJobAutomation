import scorer


def test_metric_pattern_matches_percent_with_no_trailing_word_char():
    # Regression: METRIC_PATTERN previously required a trailing \b after "%",
    # which "%" (a non-word char) can never satisfy when followed by a space
    # or punctuation — so real percentage metrics were invisible to scoring.
    assert scorer.METRIC_PATTERN.search("reduced hardware cost by 50%")
    assert scorer.METRIC_PATTERN.search("reduced hardware cost by 50%.")
    assert scorer.METRIC_PATTERN.search("99.9% uptime")


def test_metric_pattern_still_matches_word_suffixes():
    assert scorer.METRIC_PATTERN.search("2x growth")
    assert scorer.METRIC_PATTERN.search("ran for 3 hours")


def test_contains_term_does_not_match_inside_unrelated_word():
    # Regression: plain substring matching let "go" match inside "Government",
    # "logo", etc., producing false keyword matches.
    assert not scorer._contains_term("u.s. government export regulations", "go")
    assert not scorer._contains_term("see our logo", "go")


def test_contains_term_matches_whole_word_and_phrase():
    assert scorer._contains_term("we use go for backend services", "go")
    assert scorer._contains_term("experience with machine learning pipelines", "machine learning")


def test_extract_job_keywords_excludes_false_positive_from_boilerplate():
    job_description = (
        "To conform to U.S. Government export regulations, applicant must be a citizen."
    )
    keywords = scorer._extract_job_keywords(job_description, resume_master="", listing={})

    assert "go" not in keywords


def test_score_requirement_match_does_not_credit_substring_false_positive():
    score, matched, missing, details = scorer._score_requirement_match(
        "I have experience with government compliance work.", ["go"],
    )

    assert matched == []
    assert missing == ["go"]
