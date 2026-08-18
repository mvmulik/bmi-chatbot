from app.services.hybrid import extract_keywords, reciprocal_rank_fusion


def test_extract_keywords_drops_stopwords() -> None:
    terms = extract_keywords("What is the leave policy for employees?")
    assert "leave" in terms
    assert "policy" in terms
    assert "the" not in terms
    assert "what" not in terms


def test_reciprocal_rank_fusion_prefers_agreement() -> None:
    scores = reciprocal_rank_fusion(
        [
            ["a", "b", "c"],
            ["b", "a", "d"],
        ]
    )
    ranked = sorted(scores, key=scores.get, reverse=True)
    assert ranked[0] in {"a", "b"}
    assert scores["b"] > scores["c"]
