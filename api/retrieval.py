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


def case_verdict_question(question, *, source_scope="public"):
    """Conservative intent rules, not a general legal-language classifier.

    Combine a personal/deictic case reference with a legal judgment or permission
    request. Abstract statutory descriptions remain extractable, as do explicit
    questions about what a private document literally says (not whether it is true).
    """
    value = question.lower().replace("’", "'")
    literal_private = source_scope == "private" and bool(re.search(
        r"^\s*(?:(?:what|which|where|when)\s+)?(?:does|do|did)\s+(?:(?:the|this|my|our|uploaded)\s+)?(?:document|lease|contract|uploaded text|passage)\s+(?:explicitly\s+)?(?:say|state|mention|describe|list|record|contain)\b", value))
    # A literal first question cannot license an appended request for a verdict.
    if re.search(r"(?:[?;]|\band\b|\bbut\b)\s*(?:is|are|was|does|did|can|will|am|should)\b", value):
        literal_private = False
    if literal_private:
        return False
    personal = bool(re.search(r"\b(?:my|our|your|i|we|me|us)\b", value))
    specific = bool(re.search(r"\b(?:this|that)\s+(?:lease|clause|landlord|tenant|case|situation|agreement|deduction|deposit|fee|eviction|conduct|action)\b", value))
    abstract_source = bool(re.search(r"\b(?:what|which|how|when)\b.{0,35}\b(?:statute|code|section|source|captured|provision|text)\b", value))
    definite_case = not abstract_source and bool(re.search(r"\bthe\s+(?:landlord|tenant|lease|clause|deduction|deposit|eviction)\b", value))
    legal_judgment = bool(re.search(
        r"\b(?:illegal|illegally|legal|legally|lawful|unlawful|lawfully|unlawfully|enforceable|unenforceable|liable|guilty|entitled|violation|violat(?:e|es|ed|ing)|breach(?:es|ed|ing)?|compliant|noncompliant|permitted|allowed|allowable|prohibited|wrongful|wrongfully|lawsuit|compensation)\b"
        r"|\b(?:break|breaks|breaking|broke|broken|against)\b.{0,25}\b(?:the\s+)?law\b"
        r"|\b(?:owe|owes|owed)\b.{0,25}\b(?:me|us|compensation|damages)\b", value))
    permission_request = bool(re.search(r"\b(?:can|could|may|should)\s+(?:i|we|my\s+landlord|our\s+landlord|the\s+landlord)\s+(?:sue|withhold|deduct|evict|keep|retain|charge|terminate|refuse|recover|demand|win)\b", value))
    return ((personal or specific or definite_case) and legal_judgment) or permission_request


def public_topic_gap(question, sources):
    """Require an explicit anchor in the actual captured statutory topics.

    Generic words such as law, deadline, landlord and tenant are not evidence of
    topic coverage. This bounded release knows only three statutory sections;
    unsupported or ambiguous topics need a narrower question instead of matching
    coincidental corpus terms. It does not establish substantive answer coverage.
    """
    value = question.lower()
    inventory = " ".join(str(source.get("source_id", "")) + " " + str(source.get("title", "")) for source in sources)
    available = set(re.findall(r"\b(?:1942\.5|1950\.5|1950\.6)\b", inventory))
    covered_topics = set(available)
    # A curated title can identify its narrow topic without claiming a statute
    # identity (e.g. an explicitly synthetic evaluation fixture). Exact statute
    # requests still require that exact identifier in the inventory above.
    for source in sources:
        title = str(source.get("title", "")).lower()
        for section, label in (("1950.5", r"\bsecurity[ -]?deposits?\b"),
                               ("1950.6", r"\bscreening[ -]?fees?\b"),
                               ("1942.5", r"\bretaliat\w*\b")):
            if re.search(label, title):
                covered_topics.add(section)
    identifiers = set(re.findall(r"\b\d{4}\.\d+\b", value))
    identifiers.update(re.findall(r"\b(?:civil\s+code|section|code)\s+(\d{4}(?:\.\d+)?)\b", value))
    if identifiers - available:
        return "The requested statutory identifier is outside the captured corpus. Ask about a captured section or provide another authoritative source."
    outside = re.search(
        r"\b(?:patents?|copyrights?|trademarks?|bankruptcy|insolvency|immigration|visas?|asylum|deportation|citizenship|divorce|custody|alimony|probate|inheritance|murder|arrest|criminal|prosecut(?:e|ion)|federal|fdic|mortgages?|overtime)\b"
        r"|\b(?:intellectual property|income tax|estate tax|employment law|workers compensation|banking law)\b", value)
    foreign = re.search(r"\b(?:nevada|new york|texas|florida|washington|oregon|arizona|canada|united kingdom|england|australia)\b", value)
    if outside or foreign:
        return "This question includes a topic or jurisdiction outside the captured California deposit, screening-fee and retaliation statutes. The corpus cannot answer it."
    if identifiers and identifiers <= available:
        return None
    topic_patterns = {
        "1950.5": (
            r"\b(?:security[ -]?deposits?|deposits?|nonrefundable security|ordinary wear|wear and tear|preexisting defects|carpet cleaning|cleanliness baseline|initial inspection|itemized statement|deduction documentation)\b",
            r"\b(?:deduct(?:ed|ion|ions)?|withheld|withholding)\b.{0,65}\b(?:rent|repair|cleaning|damage|work|charges|documentation)\b",
            r"\b(?:repair|cleaning|damage|work|charges)\b.{0,65}\b(?:deduct(?:ed|ion|ions)?|withheld|withholding)\b",
        ),
        "1950.6": (r"\b(?:screening|application[ -]?fees?|credit[ -]?reports?|consumer[ -]?reports?|applicants?|rental applications?)\b",),
        "1942.5": (r"\b(?:retaliat\w*|tenant[ -]?(?:organizing|organisation|organization|association)|renters?[ -]?(?:organizing|association))\b",),
    }
    if any(section in covered_topics and any(re.search(pattern, value) for pattern in patterns)
           for section, patterns in topic_patterns.items()):
        return None
    return "The question does not identify a covered topic. Ask about residential security deposits, rental screening fees, tenant retaliation or a captured Civil Code section."


def unsafe_question(question, *, source_scope="public"):
    value = question.lower()
    if re.search(r"ignore\b.{0,45}\b(instructions|rules|previous)|system\s*(prompt|message)|reveal\b.{0,30}(secret|token|workspace)|bypass\b.{0,30}(auth|filter)|act as\b|<\s*/?\s*(system|assistant)|(?:show|list|read|search|download)\b.{0,50}(?:other|another|all)\s+(?:users?|workspaces?)", value):
        return "Instructions targeting system behavior or other workspaces cannot be answered from source evidence."
    if case_verdict_question(question, source_scope=source_scope) or re.search(r"\b(will i win|am i entitled|can i sue|should i sue|what (?:should|must) i do|do i have a case)\b", value):
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


def explicit_evidence_conflicts(passages):
    """Narrow mechanical opposite detection, not legal contradiction adjudication.

    At most 30 candidates / 12 sentences each / 1000 chars per sentence. Detect
    otherwise-identical sentences with explicit not/never negation, or permitted
    versus prohibited. Conditions, amounts and dates remain part of the key, so
    differing circumstances are not silently collapsed into a contradiction.
    """
    seen, conflicts, reported = {}, [], set()
    for passage in passages[:30]:
        sentences = re.split(r"(?<=[.!?;])\s+|\n+", passage["text"])
        for sentence in sentences[:12]:
            value = sentence[:1000].lower().replace("’", "'")
            for contraction, expansion in {"cannot": "can not", "can't": "can not", "won't": "will not",
                    "isn't": "is not", "aren't": "are not", "mustn't": "must not", "shouldn't": "should not",
                    "doesn't": "does not", "don't": "do not", "hasn't": "has not", "haven't": "have not"}.items():
                value = value.replace(contraction, expansion)
            words = re.findall(r"[a-z0-9]+(?:\.[0-9]+)*", value)
            negative = sum(word in ("not", "never", "prohibited", "forbidden") for word in words) % 2
            canonical = tuple("permitted" if word in ("prohibited", "forbidden") else word
                              for word in words if word not in ("not", "never"))
            if len(canonical) < 5:
                continue
            earlier = seen.get((canonical, 1 - negative))
            if earlier is not None:
                pair = tuple(sorted({earlier, passage["passage_id"]}))
                if pair not in reported:
                    reported.add(pair)
                    conflicts.append({"passage_ids": list(pair), "method": "explicit-opposite-sentence-v1"})
                    if len(conflicts) >= 10:
                        return conflicts
            seen.setdefault((canonical, negative), passage["passage_id"])
    return conflicts


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
