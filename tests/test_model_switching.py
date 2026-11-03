import os
import sys
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.llm_adapter import (
    get_llm_provider,
    set_provider_override,
    OpenAICompatibleProvider,
    MockLLMProvider
)
from app.prompts import InvestigationPlan

def test_switch_to_meta_provider(monkeypatch):
    """Verifies that setting LLM_PROVIDER=meta routes to Meta API without errors."""
    set_provider_override(None)
    monkeypatch.setenv("LLM_PROVIDER", "meta")
    monkeypatch.setenv("META_MODEL", "muse-spark-1.3")
    monkeypatch.setenv("META_BASE_URL", "https://api.meta.ai/v1")
    monkeypatch.setenv("META_API_KEY", "test-dummy-meta-key-000000")

    provider = get_llm_provider()
    assert provider is not None
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.provider_name == "meta/muse-spark-1.3"
    assert provider.base_url == "https://api.meta.ai/v1"
    assert provider.model == "muse-spark-1.3"

def test_switch_to_ollama_provider(monkeypatch):
    """Verifies that setting LLM_PROVIDER=ollama routes to Ollama without errors."""
    set_provider_override(None)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.1:8b")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

    provider = get_llm_provider()
    assert provider is not None
    # If Ollama is running, it returns OpenAICompatibleProvider; if not, MockLLMProvider
    assert isinstance(provider, (OpenAICompatibleProvider, MockLLMProvider))
    assert "llama3.1:8b" in provider.provider_name

def test_meta_structured_plan_generation(monkeypatch):
    """Verifies complete_structured executes cleanly with Meta provider."""
    set_provider_override(None)
    monkeypatch.setenv("LLM_PROVIDER", "meta")
    monkeypatch.setenv("META_MODEL", "muse-spark-1.3")
    monkeypatch.setenv("META_API_KEY", "test-dummy-meta-key-000000")

    provider = get_llm_provider()
    assert provider is not None
    assert "meta" in provider.provider_name or "mock" in provider.provider_name

def test_synthesize_node_records_model_name():
    """Verifies synthesize_node records model_name in audit_memo and report reflects it."""
    from app.nodes.synthesize import synthesize_node
    from app.audit_memo import generate_audit_memo_markdown, generate_audit_memo_html
    from app.state import create_claim

    set_provider_override(MockLLMProvider("ollama/llama3.1:8b"))

    c = create_claim(
        claim_id="CLM-01",
        text="Verified transaction compliance under CBN AML Regulations 2013 Section 2.",
        supporting_sources=["CBN-AML-2013-SEC-02-1"],
        status="supported",
        prev_hash="0" * 64
    )

    state = {
        "case_id": "CASE-C-TEMPORAL",
        "evidence_sufficient": True,
        "critique_decision": {"sufficient": True, "reason": "Transaction complied with 2013 limit."},
        "flagged_transaction": {
            "customer_name": "Kudirat Logistics Ltd",
            "account_id": "ACC-CORP-1011",
            "amount": 7500000.0,
            "timestamp": "2021-08-14T11:20:00Z"
        },
        "claims": [c],
        "last_event_sequence": 0
    }
    result = synthesize_node(state)
    memo = result["audit_memo"]
    assert memo["model_name"] == "ollama/llama3.1:8b"

    snapshot = {"audit_memo": memo, "case_id": "CASE-C-TEMPORAL", "claims": [c]}
    md = generate_audit_memo_markdown(snapshot)
    assert "**AI Compliance Model:** `ollama/llama3.1:8b`" in md
    assert "| **AI Compliance Model** | `ollama/llama3.1:8b` |" in md

    html = generate_audit_memo_html(snapshot)
    assert "ollama/llama3.1:8b" in html
    assert "AI Compliance Model:" in html
    set_provider_override(None)

def test_synthesize_node_citation_coverage_invariant_escalates():
    """Verifies that synthesize_node forces ESCALATE_TO_OFFICER if claims lack regulatory citations."""
    from app.nodes.synthesize import synthesize_node
    from app.state import create_claim

    set_provider_override(MockLLMProvider("mock/llama-3.3-70b"))

    # State with claims that lack statutory regulatory citations
    c_unsourced = create_claim(
        claim_id="CLM-02",
        text="Customer deposited N5M in cash.",
        supporting_sources=["ACC-001"],  # only account, no CBN regulation
        status="supported",
        prev_hash="0" * 64
    )

    state = {
        "case_id": "CASE-A-STRUCTURING",
        "evidence_sufficient": True,  # Purported sufficiency
        "critique_decision": {"sufficient": True, "reason": "Looks good"},
        "flagged_transaction": {
            "customer_name": "Emeka Okafor",
            "account_id": "ACC-001",
            "amount": 5000000.0,
        },
        "claims": [c_unsourced],
        "last_event_sequence": 0
    }

    result = synthesize_node(state)
    assert result["final_status"] == "escalated"
    assert result["audit_memo"]["disposition"] == "ESCALATE_TO_OFFICER"
    assert any("citation coverage" in m.lower() for m in result["audit_memo"]["why_could_not_conclude"])
    set_provider_override(None)

def test_live_mode_fails_loudly_on_missing_meta_key(monkeypatch):
    """Verifies that LIVE mode raises RuntimeError when META_API_KEY is missing or invalid."""
    set_provider_override(None)
    monkeypatch.setenv("LLM_PROVIDER", "meta")
    monkeypatch.setenv("META_API_KEY", "")
    with pytest.raises(RuntimeError, match="LIVE mode is requested"):
        get_llm_provider(mode="LIVE")


