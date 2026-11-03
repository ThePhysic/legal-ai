"""Behavioral regressions for browser-discovered unsupported-answer failures."""

import pytest

from api.retrieval import public_topic_gap
from api.tests.conftest import upload


@pytest.mark.parametrize("configuration", ["lexical", "dense", "hybrid", "rerank"])
@pytest.mark.parametrize("question", [
    "Is my landlord breaking the law by keeping my deposit?",
    "What are the federal patent filing deadlines?",
    "Is retaining my security deposit against the law?",
    "My landlord retained the deposit after an argument. Is that allowed?",
    "Does the landlord owe me damages for keeping the security deposit?",
    "Is this lease clause legally enforceable?",
    "Can my landlord keep my deposit after I paid the rent?",
    "Did my landlord violate the code by charging this screening fee?",
    "What are copyright registration deadlines for a landlord?",
    "Can a landlord claim a patent instead of returning a security deposit?",
    "What tax filing deadlines apply to landlords?",
    "What are the California landlord entry notice rules?",
    "What deposit rules does Civil Code 1954 set?",
    "What does FDIC insurance cover for security deposits?",
])
def test_public_unsupported_topics_and_personal_verdicts_abstain(client, question, configuration):
    result = client.post("/v1/research", json={"question": question, "configuration": configuration}).json()
    assert result["status"] == "insufficient_evidence", result
    assert result["claims"] == [] and result["passages"] == []
    assert result["coverage_gaps"]
    searched = client.post("/v1/search", json={"question": question, "configuration": configuration}).json()
    assert searched["passages"] == []


@pytest.mark.parametrize("question", [
    "When must the tenant security deposit be returned?",
    "Can a landlord use a security deposit for unpaid rent?",
    "Is using a security deposit for unpaid rent permitted?",
    "What does Civil Code 1950.5 say about security deposit deductions?",
    "When should my landlord return my security deposit?",
    "What cleaning can be deducted from a deposit?",
])
def test_abstract_statute_information_is_preserved(client, question):
    result = client.post("/v1/research", json={"question": question}).json()
    assert result["status"] == "answered", result
    assert result["claims"]


def test_topic_gate_uses_captured_source_inventory_and_specific_anchors():
    sources = [{"source_id": "ca-civ-1950.5", "title": "Civil Code 1950.5"}]
    assert public_topic_gap("How is an applicant screening fee itemized?", sources)
    sources.extend([{"source_id": "ca-civ-1950.6", "title": "Civil Code 1950.6"},
                    {"source_id": "ca-civ-1942.5", "title": "Civil Code 1942.5"}])
    assert public_topic_gap("How is an applicant screening fee itemized?", sources) is None
    assert public_topic_gap("What protections address lawful tenant organizing?", sources) is None
    assert public_topic_gap("How much written notice is described for a requested initial inspection?", sources) is None
    assert public_topic_gap("What deadline applies?", sources)
    assert public_topic_gap("What can landlords do under the law?", sources)
    assert public_topic_gap("Explain Nevada security deposit requirements", sources)
    synthetic = [{"source_id": "synthetic", "title": "Synthetic tenant security deposit fixture"}]
    assert public_topic_gap("What deadline applies to returning a tenant security deposit?", synthetic) is None
    assert public_topic_gap("What does Civil Code 1950.5 say?", synthetic)


@pytest.mark.parametrize("question", [
    "What patent filing deadline is listed in the document?",
    "What does the document say about my landlord breaking the law?",
    "Can I see the patent filing deadline in this document?",
])
def test_literal_private_qa_does_not_use_public_domain_gate(client, question):
    document = upload(client, b"The patent filing deadline is 2027-01-02. The document alleges my landlord is breaking the law by keeping the deposit.")
    result = client.post("/v1/research", json={"question": question, "source_scope": "private",
                                             "document_id": document["document_id"]}).json()
    assert result["status"] == "answered", result
    assert all(passage["source_id"] == document["document_id"] for passage in result["passages"])
    assert all(claim["identity_validated"] for claim in result["claims"])


@pytest.mark.parametrize("question", [
    "Is my landlord breaking the law by keeping my deposit?",
    "Is this lease clause enforceable?",
    "Does the landlord owe me damages for keeping the deposit?",
    "According to my lease, is the landlord legally allowed to keep the deposit?",
    "My lease says the landlord can keep the deposit. Is that lawful?",
    "What does the document say about my deposit, and is my landlord breaking the law?",
])
def test_private_qa_and_analysis_cannot_turn_contract_text_into_legal_verdict(client, question):
    document = upload(client, b"The landlord may keep the full deposit. The security deposit return date is 2026-12-01.")
    request = {"question": question, "source_scope": "private", "document_id": document["document_id"]}
    researched = client.post("/v1/research", json=request).json()
    assert researched["status"] == "insufficient_evidence", researched
    assert researched["claims"] == []
    assert any("case-specific" in gap for gap in researched["coverage_gaps"])
    analyzed = client.post(f"/v1/documents/{document['document_id']}/analysis", json={"question": question}).json()
    assert analyzed["answer"]["status"] == "insufficient_evidence"
    assert analyzed["answer"]["claims"] == []
    # Literal extraction is independently available, including explicit dates.
    literal = client.post(f"/v1/documents/{document['document_id']}/analysis", json={"question": "What security deposit return date is stated?"}).json()
    assert literal["answer"]["status"] == "answered"
    assert any("2026-12-01" in claim["text"] for claim in literal["answer"]["claims"])
