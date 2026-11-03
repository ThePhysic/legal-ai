"""Pure scorers independent of retrieval; no model or provider dependency."""

import math


def passage_identity_matches(actual: dict, expected: dict) -> bool:
    return (all(actual.get(key) == expected.get(key) for key in ("passage_id", "source_id", "version", "text", "locator"))
            and all(actual.get("source", {}).get(key) == expected["source"].get(key)
                    for key in ("source_id", "version", "content_hash", "scope")))


def retrieval_scores(ranked_ids: list[str], judgments: dict[str, int]) -> dict:
    """Passage recall, reciprocal rank and exponential-gain graded nDCG.

    Duplicate IDs occupy returned ranks but receive credit once. Unjudged
    passages have gain zero. Cases without positives are excluded, not perfect.
    """
    relevant = {key for key, grade in judgments.items() if grade > 0}
    if not relevant:
        return dict.fromkeys(("recall_at_5", "recall_at_10", "mrr_at_10", "ndcg_at_10"))
    seen = set()
    gains, first = [], 0
    for rank, identity in enumerate(ranked_ids[:10], 1):
        grade = judgments.get(identity, 0) if identity not in seen else 0
        if grade > 0 and not first:
            first = rank
        gains.append((2 ** grade - 1) / math.log2(rank + 1))
        seen.add(identity)
    ideal = sorted((grade for grade in judgments.values() if grade > 0), reverse=True)[:10]
    ideal_dcg = sum((2 ** grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(ideal, 1))
    return {
        "recall_at_5": len(set(ranked_ids[:5]) & relevant) / len(relevant),
        "recall_at_10": len(set(ranked_ids[:10]) & relevant) / len(relevant),
        "mrr_at_10": 1 / first if first else 0.0,
        "ndcg_at_10": sum(gains) / ideal_dcg,
    }


def percentile(values: list[float], fraction: float) -> float | None:
    """Linear interpolation over sorted observations, inclusive endpoints."""
    if not values:
        return None
    if not 0 <= fraction <= 1:
        raise ValueError("Percentile fraction must be in [0, 1].")
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def abstention_scores(observations: list[tuple[bool, bool | None]]) -> dict:
    """Positive means abstain; errors/unavailable responses stay unscored."""
    counts = {"true_positive": 0, "false_positive": 0, "false_negative": 0, "true_negative": 0}
    unavailable = 0
    for expected, actual in observations:
        if actual is None:
            unavailable += 1
            continue
        name = ("true_" if expected == actual else "false_") + ("positive" if actual else "negative")
        counts[name] += 1
    tp, fp, fn = counts["true_positive"], counts["false_positive"], counts["false_negative"]
    return {**counts, "unavailable_or_error": unavailable,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "positive_label": "expected abstention"}


def citation_scores(response: dict, canonical: dict[str, dict]) -> list[dict]:
    """Check exact canonical identity/version and quote membership independently.

    These mechanical checks are not legal/semantic judgments. Text is checked
    in memory only; diagnostics contain no generated answer or source excerpts.
    """
    returned = {item.get("passage_id"): item for item in response.get("passages", [])}
    results = []
    for index, claim in enumerate(response.get("claims", []), 1):
        refs = claim.get("passage_ids", [])
        identities_valid = bool(refs) and len(set(refs)) == len(refs)
        expected_sources = set()
        for identity in refs:
            source = canonical.get(identity)
            actual = returned.get(identity)
            if source is None or actual is None:
                identities_valid = False
                continue
            expected_sources.add(source["source_id"])
            if not passage_identity_matches(actual, source):
                identities_valid = False
        if set(claim.get("source_ids", [])) != expected_sources:
            identities_valid = False
        quote_valid = bool(identities_valid and claim.get("support_status") == "verbatim_quote"
                           and isinstance(claim.get("text"), str) and claim["text"].strip()
                           and any(claim["text"] in canonical[identity]["text"] for identity in refs))
        results.append({"claim_index": index, "identity_valid": identities_valid,
                        "exact_quote_member": quote_valid,
                        "passage_ids": [identity if identity in canonical else "[unrecognized]" for identity in refs]})
    return results
