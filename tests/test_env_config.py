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
    MockLLMProvider,
    extract_json_content,
    is_valid_api_key
)
from app.server import health_check

def test_json_content_extraction():
    # 1. Pure JSON
    assert extract_json_content('{"status": "ok"}') == '{"status": "ok"}'

    # 2. Markdown fenced with ```json
    markdown_json = '```json\n{"action": "APPROVE"}\n```'
    assert extract_json_content(markdown_json) == '{"action": "APPROVE"}'

    # 3. Markdown fenced with surrounding commentary
    surrounded = 'Here is the result:\n```json\n{"result": 42}\n```\nHope that helps!'
    assert extract_json_content(surrounded) == '{"result": 42}'

def test_api_key_validity_check():
    assert not is_valid_api_key(None)
    assert not is_valid_api_key("")
    assert not is_valid_api_key("your_meta_api_key_here")
    assert not is_valid_api_key("placeholder")
    assert not is_valid_api_key("...")
    assert is_valid_api_key("sk_live_meta_9876543210abcdef")

def test_meta_provider_dynamic_resolution(monkeypatch):
    set_provider_override(None)
    monkeypatch.setenv("LLM_PROVIDER", "meta")
    monkeypatch.setenv("META_MODEL", "llama-3.3-70b-instruct")
    monkeypatch.setenv("META_BASE_URL", "https://api.meta.com/v1")
    monkeypatch.setenv("REGGUARD_MODE", "LIVE")

    # When key is placeholder -> fallback to mock
    monkeypatch.setenv("META_API_KEY", "your_meta_api_key_here")
    provider = get_llm_provider()
    assert isinstance(provider, MockLLMProvider)
    assert "llama-3.3-70b-instruct" in provider.provider_name

    # When live key is supplied -> returns OpenAICompatibleProvider
    monkeypatch.setenv("META_API_KEY", "meta_live_sec_key_123456789")
    live_provider = get_llm_provider()
    assert isinstance(live_provider, OpenAICompatibleProvider)
    assert live_provider.provider_name == "meta/llama-3.3-70b-instruct"
    assert live_provider.base_url == "https://api.meta.com/v1"
    assert live_provider.model == "llama-3.3-70b-instruct"

def test_embedding_config_and_health_endpoint(monkeypatch):
    set_provider_override(None)
    monkeypatch.setenv("EMBEDDING_DENSE_MODEL", "BAAI/bge-small-en-v1.5")
    monkeypatch.setenv("EMBEDDING_SPARSE_MODEL", "Qdrant/bm25")
    monkeypatch.setenv("LLM_PROVIDER", "meta")
    monkeypatch.setenv("META_API_KEY", "your_meta_api_key_here")

    import asyncio
    health_data = asyncio.run(health_check())
    assert health_data["status"] == "healthy"
    assert health_data["embedding_dense"] == "BAAI/bge-small-en-v1.5"
    assert health_data["embedding_sparse"] == "Qdrant/bm25"
    assert "provider" in health_data and health_data["provider"].startswith("mock/")
