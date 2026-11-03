import json

import httpx
import pytest

from api.openai_adapters import (
    BoundedOpenAIHTTP,
    OpenAIEmbeddingAdapter,
    ProviderBudget,
    prepared_generator,
)
from api.providers import ProviderUnavailable


def budget(**overrides):
    # Synthetic prices authorize MockTransport reservations; NOT live cost estimates.
    return ProviderBudget(**{"authorized": True, "max_calls": 2, "max_input_tokens": 20000,
        "max_output_tokens": 2000, "max_cost_usd": 1, "input_usd_per_million": 1,
        "output_usd_per_million": 1, **overrides})


def test_embedding_actual_http_shape_model_dimensions_usage_and_budget():
    requests = []
    def transport(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert str(request.url) == "https://api.openai.com/v1/embeddings"
        assert payload == {"model": "text-embedding-3-small", "input": ["security deposit"], "encoding_format": "float", "dimensions": 1536}
        return httpx.Response(200, json={"model": payload["model"], "data": [{"index": 0, "embedding": [0.1] * 1536}],
            "usage": {"prompt_tokens": 2, "total_tokens": 2}})
    limits = budget(max_calls=1)
    http = BoundedOpenAIHTTP("synthetic-test-key", enabled=True, budget=limits, transport=httpx.MockTransport(transport))
    vectors = OpenAIEmbeddingAdapter(http).embed(["security deposit"])
    assert len(vectors[0]) == 1536 and limits.observed_input_tokens == 2
    with pytest.raises(ProviderUnavailable, match="exhausted"):
        OpenAIEmbeddingAdapter(http).embed(["security deposit"])
    assert len(requests) == 1


def test_embedding_disabled_missing_authorization_and_wrong_model_never_silently_substitute():
    def transport(request):
        raise AssertionError("disabled/zero budget must not reach network")
    for http in [BoundedOpenAIHTTP(transport=httpx.MockTransport(transport)),
                 BoundedOpenAIHTTP("synthetic", enabled=True, budget=ProviderBudget(), transport=httpx.MockTransport(transport))]:
        with pytest.raises(ProviderUnavailable):
            OpenAIEmbeddingAdapter(http).embed(["text"])
    with pytest.raises(ValueError, match="1536"):
        OpenAIEmbeddingAdapter(BoundedOpenAIHTTP(), dimension=384)
    def bad(request):
        return httpx.Response(200, json={"model": "wrong-model", "data": [{"index": 0, "embedding": [1]}], "usage": {"prompt_tokens": 1}})
    with pytest.raises(ProviderUnavailable, match="validation"):
        OpenAIEmbeddingAdapter(BoundedOpenAIHTTP("synthetic", enabled=True, budget=budget(), transport=httpx.MockTransport(bad))).embed(["text"])


def test_responses_structured_schema_source_identity_and_no_tool_store_calls():
    seen = []
    def transport(request):
        payload = json.loads(request.content)
        seen.append(payload)
        assert str(request.url) == "https://api.openai.com/v1/responses"
        assert payload["model"] == "gpt-6-astra" and payload["store"] is False and payload["tools"] == []
        assert payload["max_output_tokens"] == 1000
        schema = payload["text"]["format"]
        assert schema["type"] == "json_schema" and schema["strict"] is True
        assert schema["schema"]["additionalProperties"] is False
        assert "evidence" in payload["input"][0]["content"][0]["text"]
        output = {"answer": "Quoted evidence", "claims": [{"claim_id": "1", "text": "Quoted evidence",
            "source_ids": ["source"], "passage_ids": ["source:v1:1"], "support_status": "not_assessed", "identity_validated": False}]}
        return httpx.Response(200, json={"model": "gpt-6-astra", "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(output)}]}],
            "usage": {"input_tokens": 100, "output_tokens": 20}})
    limits = budget()
    http = BoundedOpenAIHTTP("synthetic-test-key", enabled=True, budget=limits, transport=httpx.MockTransport(transport))
    generator = prepared_generator(http)
    passages = [{"passage_id": "source:v1:1", "source_id": "source", "version": "v1", "text": "Quoted evidence", "source": {"version": "v1"}}]
    assert generator.generate("What does this say?", passages)["claims"][0]["identity_validated"]
    assert limits.observed_output_tokens == 20
    with pytest.raises(ProviderUnavailable, match="citation validation"):
        generator.generate("What does this say?", [])
    assert len(seen) == 2


@pytest.mark.parametrize("kind", ["refusal", "incomplete", "malformed", "timeout"])
def test_responses_refusal_incomplete_malformed_timeout_are_outages(kind):
    def transport(request):
        if kind == "timeout":
            raise httpx.ReadTimeout("mock timeout", request=request)
        if kind == "malformed":
            return httpx.Response(200, text="invalid json")
        return httpx.Response(200, json={"model": "gpt-6-astra", "status": "incomplete" if kind == "incomplete" else "completed",
            "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "Cannot comply"}]}]})
    http = BoundedOpenAIHTTP("synthetic", enabled=True, budget=budget(), transport=httpx.MockTransport(transport))
    with pytest.raises(ProviderUnavailable):
        prepared_generator(http).generate("question", [])
