"""Run against the local application: uv run python examples/research.py."""
import os

import httpx

base = os.environ.get("LEGAL_AI_BASE_URL", "http://127.0.0.1:8000")
browser_origin = os.environ.get("LEGAL_AI_BROWSER_ORIGIN")
headers = {"Origin": browser_origin} if browser_origin else {}
with httpx.Client(base_url=base, headers=headers, timeout=30) as client:
    session = client.post("/v1/sessions", json={"label": "Python SDK example"})
    session.raise_for_status()
    client.headers["Authorization"] = "Bearer " + session.json()["access_token"]
    response = client.post("/v1/research", json={
        "question": "What paperwork must accompany a security deposit deduction?",
        "jurisdiction": "US-CA", "source_scope": "public", "configuration": "lexical", "top_k": 5,
    })
    response.raise_for_status()
    result = response.json()
    print("Status:", result["status"])
    print("Method:", result["method"])
    print("Coverage gaps:", result["coverage_gaps"])
    for claim in result["claims"]:
        print("Source quote:", claim["text"])
        print("Versioned passages:", claim["passage_ids"])
    print("Semantic support is not independently assessed; identity validation is a separate check.")
