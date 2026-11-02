import json
import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type, TypeVar
import httpx
from pydantic import BaseModel

logger = logging.getLogger("regguard.llm")

T = TypeVar("T", bound=BaseModel)

class LLMProvider(ABC):
    """Abstract interface for LLM providers with telemetry logging."""
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Returns provider identifier e.g. 'groq/llama-3.3-70b'."""
        pass

    @abstractmethod
    def complete(self, prompt: str, system: Optional[str] = None) -> str:
        """Unstructured text completion."""
        pass

    @abstractmethod
    def complete_structured(
        self,
        schema: Type[T],
        prompt: str,
        system: Optional[str] = None
    ) -> T:
        """Structured completion returning validated Pydantic model."""
        pass

class MockLLMProvider(LLMProvider):
    """
    Deterministic mock provider for testing and offline demo execution.
    Inspects prompt content and returns schema-compliant compliance models.
    """
    def __init__(self, simulated_name: str = "mock/llama-3.3-70b"):
        self._name = simulated_name

    @property
    def provider_name(self) -> str:
        return self._name

    def complete(self, prompt: str, system: Optional[str] = None) -> str:
        return "Mock response generated for compliance investigation."

    def complete_structured(
        self,
        schema: Type[T],
        prompt: str,
        system: Optional[str] = None
    ) -> T:
        start_time = time.perf_counter()
        
        # Scenario detection based on prompt text
        prompt_lower = prompt.lower()
        mock_dict: Dict[str, Any] = {}

        schema_name = schema.__name__

        if schema_name == "InvestigationPlan":
            if "musa ibrahim" in prompt_lower or "case-b" in prompt_lower:
                mock_dict = {
                    "hypotheses": [
                        "Hypothesis 1: Customer Musa Ibrahim has active PEP exposure violating CBN AML/CFT EDD rules.",
                        "Hypothesis 2: Inward transfer of N8,200,000 exceeds threshold and requires source-of-funds verification.",
                        "Hypothesis 3: Name match on watchlist may represent a false positive due to demographic mismatch."
                    ],
                    "initial_questions": [
                        "Verify customer name against PEP/Sanctions watchlist.",
                        "Verify secondary KYC identifiers (DOB, BVN, Nationality).",
                        "Evaluate statutory reporting threshold under CBN AML Regulations."
                    ],
                    "planned_tool_calls": [
                        {
                            "tool_name": "watchlist_lookup",
                            "parameters": {"name": "Musa Ibrahim", "dob": "1994-08-12"}
                        },
                        {
                            "tool_name": "regulation_search",
                            "parameters": {"query": "Politically Exposed Persons Enhanced Due Diligence requirements"}
                        }
                    ]
                }
            elif "emeka okafor" in prompt_lower or "case-a" in prompt_lower:
                mock_dict = {
                    "hypotheses": [
                        "Hypothesis 1: Customer Emeka Okafor is structuring multiple cash deposits below N5,000,000.",
                        "Hypothesis 2: Aggregate deposits within rolling 48-72h breach statutory CBN cash limits.",
                        "Hypothesis 3: Activity mandates filing a Suspicious Transaction Report (STR)."
                    ],
                    "initial_questions": [
                        "Retrieve historical transactions for account ACC-IND-9021 in 48-hour window.",
                        "Calculate aggregate cash deposit turnover.",
                        "Verify CBN Section 10 structuring clauses."
                    ],
                    "planned_tool_calls": [
                        {
                            "tool_name": "query_transactions",
                            "parameters": {
                                "sql_query": "SELECT * FROM transactions WHERE account_id = 'ACC-IND-9021' ORDER BY timestamp ASC;"
                            }
                        },
                        {
                            "tool_name": "threshold_calc",
                            "parameters": {
                                "amounts": [1900000.0, 1750000.0, 1850000.0],
                                "timestamps": ["2023-01-01 10:15:00", "2023-01-01 16:30:00", "2023-01-02 11:45:00"],
                                "entity_type": "INDIVIDUAL"
                            }
                        },
                        {
                            "tool_name": "regulation_search",
                            "parameters": {"query": "prohibition of structuring and smurfing cash deposits"}
                        }
                    ]
                }
            elif "kudirat" in prompt_lower or "case-c" in prompt_lower or "2021-0303" in prompt_lower or "acc-corp-1011" in prompt_lower:
                mock_dict = {
                    "hypotheses": [
                        "Hypothesis 1: Corporate cash deposit of N7,500,000 exceeds statutory reporting limit under CBN regulations.",
                        "Hypothesis 2: Applicable threshold must be determined under governing regulation in force at transaction date.",
                        "Hypothesis 3: Commercial freight proceeds without transaction structuring."
                    ],
                    "initial_questions": [
                        "Retrieve corporate cash deposit transaction records for ACC-CORP-1011.",
                        "Identify applicable CBN cash transaction threshold regulation."
                    ],
                    "planned_tool_calls": [
                        {
                            "tool_name": "query_transactions",
                            "parameters": {
                                "sql_query": "SELECT * FROM transactions WHERE account_id = 'ACC-CORP-1011' ORDER BY timestamp ASC;"
                            }
                        },
                        {
                            "tool_name": "regulation_search",
                            "parameters": {"query": "Cash Transaction Reporting Thresholds"}
                        }
                    ]
                }
            else:
                # Default generic plan
                mock_dict = {
                    "hypotheses": [
                        "Hypothesis 1: Transaction breaches statutory limits under CBN AML/CFT regulations.",
                        "Hypothesis 2: Customer KYC requires enhanced due diligence."
                    ],
                    "initial_questions": [
                        "Query transaction records.",
                        "Search regulatory clauses."
                    ],
                    "planned_tool_calls": [
                        {
                            "tool_name": "regulation_search",
                            "parameters": {"query": "Cash Transaction Reporting Thresholds"}
                        }
                    ]
                }

        elif schema_name == "CritiqueDecision":
            if "case-a" in prompt_lower or "emeka okafor" in prompt_lower:
                mock_dict = {
                    "sufficient": True,
                    "assessment": "SATISFIED",
                    "reason": "Customer Emeka Okafor conducted 3 cash deposits totaling N5,500,000.00 within 25.5 hours, structuring to evade statutory individual limit of N5,000,000 under CBN AML/CFT 2022 Section 10(3).",
                    "missing": [],
                    "detected_contradictions": [],
                    "suggested_queries": []
                }
            elif "case-c" in prompt_lower or "kudirat" in prompt_lower or "2021-08-14" in prompt_lower:
                if "retry: 1" in prompt_lower or "retry count: 1" in prompt_lower or "2013" in prompt_lower:
                    mock_dict = {
                        "sufficient": True,
                        "assessment": "SATISFIED",
                        "reason": "Temporal alignment verified. Applicable governing law at transaction time was CBN AML/CFT Regulations 2013 Section 2(1). Corporate cash deposit of N7,500,000 does not breach N10,000,000 statutory limit.",
                        "missing": [],
                        "detected_contradictions": [],
                        "suggested_queries": []
                    }
                else:
                    mock_dict = {
                        "sufficient": False,
                        "assessment": "CONTRADICTED",
                        "reason": "Temporal contradiction detected: Transaction timestamp (2021-08-14) predates effective date (2022-11-01) of cited CBN AML/CFT Regulations 2022 Section 10(1).",
                        "missing": ["applicable corporate cash threshold regulation in force prior to 2021-08-14"],
                        "detected_contradictions": ["Transaction timestamp 2021-08-14 predates effective date 2022-11-01 of cited clause CBN-AML-2022-SEC-10-1"],
                        "suggested_queries": [{"tool_name": "regulation_search", "parameters": {"query": "corporate cash deposit limit", "effective_before": "2021-08-14"}}]
                    }
            elif "case-b" in prompt_lower or "musa ibrahim" in prompt_lower:
                if "retry: 1" in prompt_lower or "retry count: 1" in prompt_lower or "conflicts" in prompt_lower or "clm-kyc" in prompt_lower:
                    mock_dict = {
                        "sufficient": False,
                        "assessment": "AMBIGUOUS",
                        "reason": "watchlist ambiguity not resolved; transaction intent not established",
                        "missing": ["historical transaction pattern"],
                        "detected_contradictions": [],
                        "suggested_queries": []
                    }
                else:
                    mock_dict = {
                        "sufficient": False,
                        "assessment": "INSUFFICIENT",
                        "reason": "Watchlist name similarity 0.87 matches PEP entry, but DOB and nationality require verification before concluding.",
                        "missing": ["DOB verification", "nationality verification"],
                        "detected_contradictions": [],
                        "suggested_queries": [{"tool_name": "watchlist_lookup", "parameters": {"name": "Musa Ibrahim", "dob": "1994-08-12"}}]
                    }
            else:
                mock_dict = {
                    "sufficient": False,
                    "assessment": "INSUFFICIENT",
                    "reason": "Evidence is incomplete to verify statutory compliance hypotheses.",
                    "missing": ["corroborating transaction documentation"],
                    "detected_contradictions": [],
                    "suggested_queries": []
                }

        elif schema_name == "RefinePlan":
            if "case-c" in prompt_lower or "kudirat" in prompt_lower or "temporal" in prompt_lower or "2021-08-14" in prompt_lower:
                mock_dict = {
                    "action": "Reformulate regulatory search with strict temporal filter: effective_before='2021-08-14' to retrieve the governing historical regulation in force in August 2021.",
                    "planned_tool_calls": [
                        {
                            "tool_name": "regulation_search",
                            "parameters": {"query": "corporate cash deposit limit", "effective_before": "2021-08-14"}
                        },
                        {
                            "tool_name": "threshold_calc",
                            "parameters": {"amounts": [7500000.0], "timestamps": ["2021-08-14 11:20:00"], "entity_type": "CORPORATE"}
                        }
                    ]
                }
            elif "case-b" in prompt_lower or "musa ibrahim" in prompt_lower:
                mock_dict = {
                    "action": "Re-query watchlist with KYC secondary attributes (DOB: 1994-08-12, Nationality: NGA) and verify customer identity profile.",
                    "planned_tool_calls": [
                        {
                            "tool_name": "watchlist_lookup",
                            "parameters": {"name": "Musa Ibrahim", "dob": "1994-08-12", "nationality": "NGA"}
                        }
                    ]
                }
            else:
                mock_dict = {
                    "action": "Target missing evidence gaps with refined tool queries.",
                    "planned_tool_calls": []
                }

        elif schema_name == "ClaimsSynthesis":
            mock_dict = {
                "claims": [
                    {
                        "text": "Watchlist search identified 1.00 similarity match for Musa Ibrahim (PEP category). Customer KYC DOB (1994-08-12) conflicts with PEP DOB (1961-04-03).",
                        "supporting_sources": ["WATCHLIST-PEP-NGA-041", "KYC-ACC-IND-4412"],
                        "status": "insufficient"
                    }
                ]
            }

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.info(f"LLM Call [{self.provider_name}] Schema: {schema_name} Latency: {latency_ms}ms")
        return schema.model_validate(mock_dict)

class OpenAICompatibleProvider(LLMProvider):
    """
    Adapter for any OpenAI-compatible API (Meta Model API, Groq, Together AI, Ollama).
    """
    def __init__(
        self,
        provider_name: str,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 30.0
    ):
        self._name = provider_name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)

    @property
    def provider_name(self) -> str:
        return self._name

    def complete(self, prompt: str, system: Optional[str] = None) -> str:
        start_time = time.perf_counter()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1
        }

        response = self.client.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.info(f"LLM Complete [{self.provider_name}] Latency: {latency_ms}ms")
        return data["choices"][0]["message"]["content"]

    def complete_structured(
        self,
        schema: Type[T],
        prompt: str,
        system: Optional[str] = None
    ) -> T:
        start_time = time.perf_counter()
        json_schema = schema.model_json_schema()

        augmented_system = (
            (system or "") + 
            f"\n\nYou are a compliance intelligence engine. You MUST respond in valid JSON conforming to this schema:\n"
            f"{json.dumps(json_schema, indent=2)}\n"
            f"Output JSON ONLY. Do not enclose in markdown code blocks."
        )

        messages = [
            {"role": "system", "content": augmented_system.strip()},
            {"role": "user", "content": prompt}
        ]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
            "response_format": {"type": "json_object"}
        }

        response = self.client.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        raw_content = data["choices"][0]["message"]["content"]
        
        parsed_json = json.loads(raw_content)
        validated = schema.model_validate(parsed_json)
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.info(f"LLM Structured [{self.provider_name}] Schema: {schema.__name__} Latency: {latency_ms}ms")
        return validated

_provider_override: Optional[LLMProvider] = None

def set_provider_override(provider: Optional[LLMProvider]):
    """Sets a global override provider (used during test recording/mocking)."""
    global _provider_override
    _provider_override = provider

def get_llm_provider(mode: Optional[str] = None) -> LLMProvider:
    """
    Factory resolving LLM provider dynamically based on environment configuration:
    LLM_PROVIDER=meta|groq|together|gemini|ollama|mock|cached
    or mode="CACHED"
    """
    global _provider_override
    if _provider_override is not None:
        return _provider_override

    env_mode = os.getenv("REGGUARD_MODE", "").upper()
    provider_type = os.getenv("LLM_PROVIDER", "").lower()

    if (mode and mode.upper() == "CACHED") or env_mode == "CACHED" or provider_type == "cached":
        from core.replay_engine import get_cached_provider
        return get_cached_provider()

    groq_key = os.getenv("GROQ_API_KEY")
    meta_key = os.getenv("META_API_KEY")
    together_key = os.getenv("TOGETHER_API_KEY")

    if provider_type == "groq" or (not provider_type and groq_key):
        return OpenAICompatibleProvider(
            provider_name="groq/llama-3.3-70b-versatile",
            base_url="https://api.groq.com/openai/v1",
            api_key=groq_key or "gsk_placeholder",
            model="llama-3.3-70b-versatile"
        )
    elif provider_type == "meta" or (not provider_type and meta_key):
        return OpenAICompatibleProvider(
            provider_name="meta/llama-3.3-70b",
            base_url=os.getenv("META_BASE_URL", "https://api.meta.com/v1"),
            api_key=meta_key or "meta_placeholder",
            model="llama-3.3-70b"
        )
    elif provider_type == "together" or (not provider_type and together_key):
        return OpenAICompatibleProvider(
            provider_name="together/llama-3.3-70b",
            base_url="https://api.together.xyz/v1",
            api_key=together_key or "together_placeholder",
            model="meta-llama/Llama-3.3-70B-Instruct-Turbo"
        )
    elif provider_type == "ollama":
        return OpenAICompatibleProvider(
            provider_name="ollama/llama3.3:70b",
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            api_key="ollama",
            model=os.getenv("OLLAMA_MODEL", "llama3.3:70b")
        )

    # Default offline mock provider
    return MockLLMProvider("mock/llama-3.3-70b")
