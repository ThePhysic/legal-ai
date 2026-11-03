import io

import pytest
from docx import Document as WordDocument

from api.retrieval import foreign_jurisdiction_requested, temporal_applicability_requested
from api.tests.conftest import upload


@pytest.mark.parametrize("configuration", ["lexical", "dense", "hybrid", "rerank"])
@pytest.mark.parametrize("question", [
    "What are Massachusetts security deposit return deadlines?",
    "What are Illinois security deposit deductions?",
    "What security deposit return rules apply in Germany?",
    "What are Connecticut screening fee rules?",
    "What security deposit return rules apply in Brazil?",
    "What are security deposit requirements in South Africa?",
    "What are German security deposit return rules?",
    "What are MA security deposit return rules?",
    "Compare California and Illinois security deposit deductions.",
    "What security deposit return rules apply in California and Germany?",
    'What security deposit return rules apply in "Germany"?',
    "What security deposit rules applied two years ago?",
    "What security deposit rules applied a couple of years ago?",
    "What security deposit rules applied six months ago?",
    "What security deposit rules applied thirty years ago?",
    "What security deposit rules applied thirteen months ago?",
    "What security deposit rules applied a dozen years ago?",
    "What security deposit rules applied last winter?",
    "What security deposit rules apply next year?",
    "What security deposit rules were in force a decade ago?",
    "What security deposit rules applied before the amendment?",
])
def test_explicit_foreign_and_relative_temporal_requests_abstain(client, question, configuration):
    result = client.post("/v1/research", json={"question": question, "configuration": configuration}).json()
    assert result["status"] == "insufficient_evidence", result
    assert result["claims"] == [] and result["passages"] == []
    assert result["coverage_gaps"]
    searched = client.post("/v1/search", json={"question": question, "configuration": configuration}).json()
    assert searched["passages"] == []


@pytest.mark.parametrize("configuration", ["lexical", "dense", "hybrid", "rerank"])
@pytest.mark.parametrize("question", [
    "What California security deposit deductions are described?",
    "Does Civil Code 1950.5 describe returning the security deposit within 21 days?",
    'The lease address is "123 Massachusetts Avenue, Los Angeles, CA". What California security deposit deductions are described?',
    'The lease lists "45 Germany Street". What California security deposit deductions are described?',
    "Explain California security deposit deductions in English.",
])
def test_california_and_literal_addresses_do_not_select_foreign_law(client, question, configuration):
    result = client.post("/v1/research", json={"question": question, "configuration": configuration}).json()
    assert result["status"] == "answered", result
    assert result["claims"]


def test_jurisdiction_roster_covers_other_states_and_country_families():
    for place in ("Alabama", "Alaska", "Connecticut", "Illinois", "Massachusetts", "North Dakota", "Wyoming",
                  "Iceland", "Germany", "Japan", "Kenya", "Chile", "New Zealand", "Nepal", "Fiji"):
        assert foreign_jurisdiction_requested(f"What security deposit rules apply in {place}?"), place
    assert not foreign_jurisdiction_requested("What California security deposit rules apply?")
    assert not foreign_jurisdiction_requested("Explain the California security deposit law in French.")
    assert not foreign_jurisdiction_requested('The lease lists "123 Illinois Avenue"; what California deposit law is captured?')


def test_relative_applicability_is_distinct_from_statutory_durations():
    for wording in ("two years ago", "thirty years ago", "thirteen months ago", "a dozen years ago", "a couple of years ago", "three and a half years ago", "in the past few years",
                    "previously", "formerly", "last summer", "before the reform", "next month", "in two years time"):
        assert temporal_applicability_requested("What security deposit rules applied " + wording + "?"), wording
    for wording in ("What does Civil Code 1950.5 say about deposit return?",
                    "Must the landlord return the security deposit within 21 days?",
                    "What does the statute say about returning the deposit 21 days after vacating?",
                    "What notice is required 48 hours before the initial inspection?"):
        assert not temporal_applicability_requested(wording), wording


@pytest.mark.parametrize("configuration", ["lexical", "dense", "hybrid", "rerank"])
def test_private_literal_dates_and_foreign_addresses_remain_private_text(client, configuration):
    document = upload(client, b"The rental address is 123 Massachusetts Avenue, Germany. The security deposit was paid two years ago. The deposit return date is 2026-12-01.")
    result = client.post("/v1/research", json={"question": "What security deposit date and Germany address are stated?",
        "source_scope": "private", "document_id": document["document_id"], "configuration": configuration}).json()
    assert result["status"] == "answered", result
    assert result["claims"]
    assert all(passage["source_id"] == document["document_id"] for passage in result["passages"])


def test_docx_tables_follow_body_order_and_heading_locators(client):
    word = WordDocument()
    word.add_heading("Deposit", 1)
    word.add_paragraph("Tenant shall pay the security deposit listed below.")
    table = word.add_table(rows=1, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Security deposit", "$1500"
    word.add_heading("Pets", 1)
    word.add_paragraph("Pets require written permission.")
    output = io.BytesIO()
    word.save(output)
    document = upload(client, output.getvalue(), "ordered.docx")
    assert document["status"] == "ready"
    deposit, pets = document["sections"]
    assert deposit["title"] == "Deposit" and deposit["locator"] == "section-1"
    assert "Security deposit | $1500" in deposit["text"]
    assert pets["title"] == "Pets" and "$1500" not in pets["text"]
    matching = [passage for passage in document["passages"] if "$1500" in passage["text"]]
    assert matching and all(passage["locator"] == deposit["locator"] for passage in matching)
    analysis = client.post(f"/v1/documents/{document['document_id']}/analysis", json={"locator": deposit["locator"]}).json()
    assert any(finding["text"] == "$1500" and finding["locator"] == deposit["locator"] for finding in analysis["findings"])
