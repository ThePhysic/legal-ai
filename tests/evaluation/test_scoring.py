import copy
import math

import pytest

from evaluations.scoring import abstention_scores, citation_scores, percentile, retrieval_scores


def test_graded_metrics_match_independent_hand_calculation():
    # x is unjudged. Duplicate b at rank 3 occupies its rank but gains nothing.
    result = retrieval_scores(["x", "b", "b", "a"], {"a": 3, "b": 2, "c": 1})
    observed_dcg = 3 / math.log2(3) + 7 / math.log2(5)
    ideal_dcg = 7 + 3 / math.log2(3) + 1 / 2
    assert result == pytest.approx({"recall_at_5": 2 / 3, "recall_at_10": 2 / 3,
                                    "mrr_at_10": .5, "ndcg_at_10": observed_dcg / ideal_dcg})


def test_rank_cutoffs_and_all_relevant_denominator():
    ranked = ["a", "x", "x", "x", "x", "b", "x", "x", "x", "x", "c"]
    result = retrieval_scores(ranked, {"a": 1, "b": 1, "c": 1})
    assert result["recall_at_5"] == 1 / 3
    assert result["recall_at_10"] == 2 / 3
    assert result["mrr_at_10"] == 1
    assert retrieval_scores(["x"] * 10 + ["a"], {"a": 1})["mrr_at_10"] == 0


def test_unanswerable_is_excluded_and_answerable_miss_is_zero():
    assert set(retrieval_scores([], {}).values()) == {None}
    assert set(retrieval_scores([], {"a": 3}).values()) == {0}
    assert set(retrieval_scores(["a"], {"a": 0}).values()) == {None}


def test_abstention_confusion_matrix_and_undefined_denominators():
    actual = abstention_scores([(True, True), (True, True), (False, True), (True, False), (False, False), (True, None)])
    assert actual["true_positive"] == 2
    assert actual["false_positive"] == actual["false_negative"] == actual["true_negative"] == 1
    assert actual["precision"] == actual["recall"] == 2 / 3
    assert actual["unavailable_or_error"] == 1
    assert abstention_scores([(False, False)])["precision"] is None
    assert abstention_scores([(False, False)])["recall"] is None


def test_percentile_inclusive_linear_interpolation():
    assert percentile([4, 1, 3, 2], .5) == 2.5
    assert percentile([4, 1, 3, 2], .95) == pytest.approx(3.85)
    assert percentile([7], .95) == 7
    assert percentile([], .95) is None
    with pytest.raises(ValueError):
        percentile([1], 2)


@pytest.fixture
def cited():
    passage = {"passage_id": "p-v1", "source_id": "source", "version": "v1", "locator": "paragraph 1",
               "text": "The deposit must be returned.",
               "source": {"source_id": "source", "version": "v1", "scope": "public", "content_hash": "a" * 64}}
    response = {"passages": [copy.deepcopy(passage)], "claims": [
        {"text": "deposit must be returned", "passage_ids": ["p-v1"], "source_ids": ["source"],
         "identity_validated": False, "support_status": "verbatim_quote"}]}
    return response, {"p-v1": passage}


def test_identity_check_is_independent_of_backend_boolean(cited):
    response, canonical = cited
    assert citation_scores(response, canonical)[0]["identity_valid"] is True
    response["claims"][0]["identity_validated"] = True
    response["claims"][0]["text"] = "The tenant automatically wins in court."
    result = citation_scores(response, canonical)[0]
    assert result["identity_valid"] is True
    assert result["exact_quote_member"] is False


@pytest.mark.parametrize("mutation", ["passage_version", "source_version", "source_id", "source_hash", "quote_text", "scope"])
def test_tampered_returned_passage_is_not_accepted(cited, mutation):
    response, canonical = cited
    if mutation == "passage_version":
        response["passages"][0]["version"] = "v2"
    elif mutation == "source_version":
        response["passages"][0]["source"]["version"] = "v2"
    elif mutation == "source_id":
        response["claims"][0]["source_ids"] = ["other"]
    elif mutation == "source_hash":
        response["passages"][0]["source"]["content_hash"] = "b" * 64
    elif mutation == "quote_text":
        response["passages"][0]["text"] = "Replaced source text"
    else:
        response["passages"][0]["source"]["scope"] = "private"
    result = citation_scores(response, canonical)[0]
    assert result["identity_valid"] is result["exact_quote_member"] is False


def test_fabricated_reference_redacted_and_missing_context_fails(cited):
    response, canonical = cited
    response["claims"][0]["passage_ids"] = ["foreign-private-id"]
    result = citation_scores(response, canonical)[0]
    assert result["passage_ids"] == ["[unrecognized]"]
    assert result["identity_valid"] is False
    response["claims"][0]["passage_ids"] = ["p-v1"]
    response["passages"] = []
    assert citation_scores(response, canonical)[0]["identity_valid"] is False
