"""Actual BM25, transparent hash-vector baseline, RRF and bounded reranking."""

import hashlib
import math
import re
from collections import Counter

STOP = set("a an the is are was were be to of in on for and or by with it as at what how when can does do my i me you your this that which from about under much must may should would will not have has been any if then they their".split())


def tokenize(text: str):
    return [token for token in re.findall(r"[a-z0-9]+(?:\.[0-9]+)*", text.lower()) if token not in STOP]


def bm25(question, passages, k1=1.5, b=0.75):
    terms = tokenize(question)
    docs = [Counter(tokenize(item["text"] + " " + item.get("source", {}).get("title", ""))) for item in passages]
    lengths = [sum(doc.values()) for doc in docs]
    average = sum(lengths) / max(1, len(docs))
    frequencies = Counter(token for doc in docs for token in doc)
    results = []
    for item, doc, length in zip(passages, docs, lengths):
        score = 0.0
        for term in set(terms):
            frequency = doc[term]
            idf = math.log(1 + (len(docs) - frequencies[term] + 0.5) / (frequencies[term] + 0.5))
            if frequency:
                score += idf * frequency * (k1 + 1) / (frequency + k1 * (1 - b + b * length / (average or 1)))
        if score > 0:
            results.append({**item, "score": score})
    return sorted(results, key=lambda item: (-item["score"], item["passage_id"]))


SYNONYMS = {
    "deposit": "security", "deposits": "security", "refund": "return", "refunded": "return",
    "repair": "repair", "repairs": "repair", "habitable": "habitable", "habitability": "habitable",
    "livable": "habitable", "heat": "heating", "enter": "entry", "entering": "entry",
    "notice": "notice", "notification": "notice", "renter": "tenant", "renters": "tenant",
    "tenants": "tenant", "landlords": "landlord", "lease": "rental", "leases": "rental",
    "plumbing": "water", "hot": "water", "utilities": "water", "deductions": "deduct",
    "deduction": "deduct", "cleaning": "clean", "cleaned": "clean", "cleanliness": "clean",
}


def local_vector(text, dimension=384):
    """Signed feature hashing of words plus a fixed, documented small synonym table.

    No pretrained semantic model, no provider. Exact deterministic CPU features.
    """
    vector = [0.0] * dimension
    for word in tokenize(text):
        word = SYNONYMS.get(word, word)
        digest = hashlib.sha256(word.encode()).digest()
        index = int.from_bytes(digest[:4], "big") % dimension
        vector[index] += 1 if digest[4] & 1 else -1
    norm = math.sqrt(sum(value * value for value in vector)) or 1
    return [value / norm for value in vector]


def dense(question, passages):
    query = local_vector(question)
    ranked = []
    for item in passages:
        vector = local_vector(item["text"] + " " + item.get("source", {}).get("title", ""))
        score = sum(a * b for a, b in zip(query, vector))
        if score > 0:
            ranked.append({**item, "score": score})
    return sorted(ranked, key=lambda item: (-item["score"], item["passage_id"]))


def rrf(*rankings, constant=60):
    scores, items = {}, {}
    for ranking in rankings:
        seen = set()
        for rank, item in enumerate(ranking, 1):
            identity = item["passage_id"]
            if identity in seen:
                continue
            seen.add(identity)
            scores[identity] = scores.get(identity, 0) + 1 / (constant + rank)
            items[identity] = item
    return [{**items[key], "score": scores[key]} for key in sorted(scores, key=lambda key: (-scores[key], key))]


def retrieve(question, passages, configuration, top_k):
    lexical = bm25(question, passages)
    if configuration == "lexical":
        return lexical[:top_k]
    vectors = dense(question, passages)
    if configuration == "dense":
        return vectors[:top_k]
    fused = rrf(lexical, vectors)
    if configuration == "hybrid":
        return fused[:top_k]
    terms = set(tokenize(question))
    candidates = fused[:30]
    # A bounded exact-term coverage/identifier reranker; no semantic accuracy claim.
    for item in candidates:
        words = set(tokenize(item["text"] + " " + item.get("source", {}).get("title", "")))
        overlap = len(terms & words) / max(1, len(terms))
        identifiers = [term for term in terms if re.match(r"\d{4}\.\d+", term)]
        bonus = sum(identifier in words for identifier in identifiers)
        item["score"] = overlap + bonus + item["score"]
    return sorted(candidates, key=lambda item: (-item["score"], item["passage_id"]))[:top_k]


def unsafe_question(question):
    value = question.lower()
    if re.search(r"ignore\b.{0,45}\b(instructions|rules|previous)|system\s*(prompt|message)|reveal\b.{0,30}(secret|token|workspace)|bypass\b.{0,30}(auth|filter)|act as\b|<\s*/?\s*(system|assistant)|(?:show|list|read|search|download)\b.{0,50}(?:other|another|all)\s+(?:users?|workspaces?)", value):
        return "Instructions targeting system behavior or other workspaces cannot be answered from source evidence."
    if re.search(r"\b(will i win|am i entitled|is (?:my|this|the) .{0,50}(?:illegal|lawful|legal|enforceable|guilty|liable)|can i sue|should i sue|what (?:should|must) i do|is .{0,30}liable|do i have a case|did my .{0,30}(?:violate|break)|has my .{0,30}(?:violated|broken))\b", value):
        return "The request asks for a case-specific legal determination that this extractive system cannot make."
    if (re.search(r"\b(verify|confirm|prove|actually|really)\b.{0,90}\b(paid|payment|bank|transfer|identity|signed|forged|true|authentic)\b", value)
            or re.search(r"\b(paid|payment|bank|transfer|identity|signature)\b.{0,70}\b(verify|confirm|prove|authentic)\b", value)):
        return "Source text cannot verify a person's identity, actual payment, bank transfer, signature authenticity or real-world truth."
    if re.search(r"\b(conflict|conflicting|contradict|contradictory|reconcile|overrides?|takes precedence|which .{0,20}controls)\b", value):
        return "This extractive system cannot resolve conflicting provisions or decide which authority controls; competing text needs an applicability and legal assessment."
    return None


def evidence_relevance(question, passages):
    if not passages:
        return False
    terms = set(tokenize(question))
    terms = {SYNONYMS.get(term, term) for term in terms}
    words = set(tokenize(" ".join(item["text"] + " " + item["source"]["title"] for item in passages)))
    words = {SYNONYMS.get(term, term) for term in words}
    intersection = terms & words
    domain = {"security", "tenant", "landlord", "rental", "habitable", "repair", "entry", "notice", "1950.5", "1941.1", "1954"}
    return bool(intersection) and ((len(terms) <= 2 and bool(intersection & domain))
                                  or (len(intersection) >= 2 and len(intersection) / max(1, len(terms)) >= 0.3))


def bounded_context(passages, budget):
    result, used = [], 0
    for passage in passages:
        # UTF-8 byte count is a deliberately conservative token upper bound.
        # Never truncate a citation passage, which preserves exact source identity.
        cost = len(passage["text"].encode("utf-8")) + len(passage["passage_id"]) + 16
        if used + cost <= budget:
            result.append(passage)
            used += cost
    return result, used


def validate_claims(claims, passages):
    lookup = {item["passage_id"]: item for item in passages}
    for claim in claims:
        refs = [lookup.get(identity) for identity in claim["passage_ids"]]
        if not refs or any(ref is None for ref in refs):
            return False
        if sorted(set(ref["source_id"] for ref in refs)) != sorted(set(claim["source_ids"])):
            return False
        if any(ref["version"] != ref["source"]["version"] for ref in refs):
            return False
        if claim["support_status"] == "verbatim_quote" and not any(claim["text"] in ref["text"] for ref in refs):
            return False
    return True
