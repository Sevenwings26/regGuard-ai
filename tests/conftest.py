import os
import sys
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.llm_adapter import set_provider_override

@pytest.fixture(autouse=True)
def configure_test_environment(monkeypatch):
    """
    Ensures the test suite runs deterministically with MockLLMProvider or replay cassettes,
    preserving external API rate limits and preventing live cloud network latency.
    Individual tests (e.g. test_env_config) can override LLM_PROVIDER as needed.
    """
    set_provider_override(None)
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    yield
    set_provider_override(None)
