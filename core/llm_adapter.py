import json
import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type, TypeVar
import httpx
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment configuration from .env (do not override explicit process env, e.g. pytest/CI)
_dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
if os.path.exists(_dotenv_path):
    load_dotenv(_dotenv_path, override=False)
else:
    load_dotenv(override=False)

logger = logging.getLogger("regguard.llm")

_last_llm_latency_ms: Optional[float] = None

def get_last_llm_latency() -> Optional[float]:
    """Returns the latency in ms of the most recent LLM invocation."""
    return _last_llm_latency_ms

def set_last_llm_latency(latency_ms: Optional[float]) -> None:
    global _last_llm_latency_ms
    _last_llm_latency_ms = latency_ms

_last_llm_usage: Dict[str, Any] = {"calls": 0, "schema_valid": 0, "schema_total": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

def record_llm_usage(data: Optional[Dict[str, Any]], schema_ok: Optional[bool] = None) -> None:
    _last_llm_usage["calls"] += 1
    if schema_ok is not None:
        _last_llm_usage["schema_total"] += 1
        if schema_ok:
            _last_llm_usage["schema_valid"] += 1
    if isinstance(data, dict):
        u = data.get("usage") or {}
        _last_llm_usage["prompt_tokens"] += int(u.get("prompt_tokens") or 0)
        _last_llm_usage["completion_tokens"] += int(u.get("completion_tokens") or 0)
        _last_llm_usage["total_tokens"] += int(u.get("total_tokens") or 0)

def get_llm_usage_snapshot() -> Dict[str, Any]:
    return dict(_last_llm_usage)

def reset_llm_usage() -> None:
    _last_llm_usage.update({"calls": 0, "schema_valid": 0, "schema_total": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})

T = TypeVar("T", bound=BaseModel)

class LLMProvider(ABC):
    """Abstract interface for LLM providers with telemetry logging."""
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Returns provider identifier e.g. 'meta/llama-3.3-70b'."""
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
                # Dynamic generic plan for custom & evaluation transactions
                cust_name = "Subject Customer"
                acc_id = "ACC-CUSTOM-01"
                amt = 5000000.0
                ent_type = "INDIVIDUAL"
                flag_r = "STATUTORY_THRESHOLD_BREACH"
                dob_val = None
                tx_ts = "2023-01-01 12:00:00"

                for line in prompt.splitlines():
                    line_s = line.strip()
                    if line_s.startswith("- Customer Name:"):
                        cust_name = line_s.split(":", 1)[1].strip()
                    elif line_s.startswith("- Account ID:"):
                        acc_id = line_s.split(":", 1)[1].strip()
                        if "corp" in acc_id.lower():
                            ent_type = "CORPORATE"
                    elif line_s.startswith("- Amount:"):
                        try:
                            amt_str = line_s.split(":", 1)[1].replace("NGN", "").replace(",", "").strip()
                            amt = float(amt_str)
                        except Exception:
                            pass
                    elif line_s.startswith("- Flag Reason:"):
                        flag_r = line_s.split(":", 1)[1].strip()
                    elif line_s.startswith("- DOB (KYC):"):
                        val = line_s.split(":", 1)[1].strip()
                        dob_val = None if val in ("None", "") else val
                    elif line_s.startswith("- Timestamp:"):
                        tx_ts = line_s.split(":", 1)[1].strip()

                # Choose targeted regulation query based on alert type
                if "pep" in flag_r.lower():
                    reg_query = "Politically Exposed Persons identification and Enhanced Due Diligence obligations"
                elif "contra" in flag_r.lower() or "round" in flag_r.lower():
                    reg_query = "Mandatory Suspicious Transaction Reporting STR Section 9"
                elif "structuring" in flag_r.lower():
                    reg_query = "Prohibition of structuring and smurfing cash transactions Section 10-3"
                elif "temporal" in flag_r.lower() or "2021" in tx_ts or "2020" in tx_ts:
                    reg_query = "Corporate cash deposit transaction threshold and statutory limits"
                else:
                    reg_query = "Cash transaction reporting statutory thresholds Section 10-1"

                mock_dict = {
                    "hypotheses": [
                        f"Hypothesis 1: Customer {cust_name} conducted transaction in potential breach of statutory limits or AML rules.",
                        f"Hypothesis 2: Transaction pattern and customer KYC require compliance verification."
                    ],
                    "initial_questions": [
                        f"Query transaction history for account {acc_id}.",
                        f"Calculate aggregate turnover against CBN statutory thresholds.",
                        f"Evaluate customer {cust_name} against sanctions and PEP watchlists."
                    ],
                    "planned_tool_calls": [
                        {
                            "tool_name": "threshold_calc",
                            "parameters": {
                                "amounts": [amt],
                                "timestamps": [tx_ts],
                                "entity_type": ent_type
                            }
                        },
                        {
                            "tool_name": "query_transactions",
                            "parameters": {
                                "sql_query": f"SELECT * FROM transactions WHERE account_id = '{acc_id}' ORDER BY timestamp ASC;"
                            }
                        },
                        {
                            "tool_name": "watchlist_lookup",
                            "parameters": {
                                "name": cust_name,
                                "dob": dob_val
                            }
                        },
                        {
                            "tool_name": "regulation_search",
                            "parameters": {
                                "query": reg_query
                            }
                        }
                    ]
                }

        elif schema_name == "CritiqueDecision":
            if "case-a" in prompt_lower or "emeka okafor" in prompt_lower:
                mock_dict = {
                    "sufficient": True,
                        "assessment": "SATISFIED",
                        "recommended_disposition": "DRAFT_STR",
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
                        "recommended_disposition": "CLEAR_NO_SUSPICION",
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
                # Dynamic critique evaluation for custom & synthetic evaluation transactions
                if "dob (kyc): none" in prompt_lower or "kyc dob: none" in prompt_lower or "bvn: none" in prompt_lower or "unverified" in prompt_lower or ("missing" in prompt_lower and "kyc" in prompt_lower):
                    mock_dict = {
                        "sufficient": False,
                        "assessment": "INSUFFICIENT",
                        "reason": "Missing mandatory KYC demographic identifiers (DOB/BVN) prevents conclusive customer identity verification.",
                        "missing": ["Customer KYC date of birth", "Biometric Bank Verification Number (BVN)"],
                        "detected_contradictions": [],
                        "suggested_queries": []
                    }
                elif "conflict" in prompt_lower or "contradict" in prompt_lower:
                    mock_dict = {
                        "sufficient": False,
                        "assessment": "CONTRADICTED",
                        "reason": "Contradictory evidence detected between declared business profile and actual transaction flows.",
                        "missing": ["Secondary source of funds corroboration"],
                        "detected_contradictions": ["Business activity declaration conflicts with counterparty classification"],
                        "suggested_queries": []
                    }
                elif any(p in prompt_lower for p in ["system override", "ignore all instructions", "drop table", "confidential cbn exemption", "mandate_clear"]):
                    if "breached': true" in prompt_lower or "breached: true" in prompt_lower:
                        mock_dict = {
                            "sufficient": True,
                        "assessment": "SATISFIED",
                        "recommended_disposition": "DRAFT_STR",
                        "reason": "Customer transaction breaches statutory cash reporting limits under CBN AML/CFT Regulations 2022 Section 10; adversarial override instruction rejected.",
                            "missing": [],
                            "detected_contradictions": ["Adversarial instruction detected in narration field"],
                            "suggested_queries": []
                        }
                    else:
                        mock_dict = {
                            "sufficient": False,
                            "assessment": "AMBIGUOUS",
                            "reason": "Adversarial prompt injection detected in transaction memo; requires compliance officer determination.",
                            "missing": ["Manual counter-party and customer interview"],
                            "detected_contradictions": ["Adversarial payload detected in narration field"],
                            "suggested_queries": []
                        }
                elif "flag: pep_name_match" in prompt_lower or "flag reason: pep_name_match" in prompt_lower or "flag: pep_exposure" in prompt_lower:
                    # True PEP vs Demographic mismatch
                    if "exact demographic match" in prompt_lower or any(dob in prompt_lower for dob in ["1961-04-03", "1958-09-14", "1982-01-30", "1975-11-22"]):
                        mock_dict = {
                            "sufficient": True,
                        "assessment": "SATISFIED",
                        "recommended_disposition": "DRAFT_STR",
                        "reason": "PEP match corroborated by identical KYC date of birth and nationality. Mandatory Enhanced Due Diligence required under CBN AML Regulations Section 18.",
                            "missing": [],
                            "detected_contradictions": [],
                            "suggested_queries": []
                        }
                    else:
                        mock_dict = {
                            "sufficient": False,
                            "assessment": "AMBIGUOUS",
                            "reason": "Watchlist match detected with demographic discrepancy. Requires compliance officer determination.",
                            "missing": ["Secondary biometric verification (BVN/NIN)"],
                            "detected_contradictions": ["Customer age differs by 30+ years from listed PEP profile"],
                            "suggested_queries": []
                        }
                elif ("2021" in prompt_lower or "2020" in prompt_lower or "pre-2022" in prompt_lower) and ("retry: 1" in prompt_lower or "retry count: 1" in prompt_lower or "2013" in prompt_lower):
                    if "breached': true" in prompt_lower or "breached: true" in prompt_lower or "14,000,000" in prompt_lower:
                        mock_dict = {
                            "sufficient": True,
                        "assessment": "SATISFIED",
                        "recommended_disposition": "DRAFT_STR",
                        "reason": "Historical corporate cash deposit breaches statutory N10,000,000 limit under CBN AML/CFT Regulations 2013 Section 2(1).",
                            "missing": [],
                            "detected_contradictions": [],
                            "suggested_queries": []
                        }
                    else:
                        mock_dict = {
                            "sufficient": True,
                        "assessment": "SATISFIED",
                        "recommended_disposition": "CLEAR_NO_SUSPICION",
                        "reason": "Temporal alignment verified. Applicable governing law at transaction time was CBN AML/CFT Regulations 2013 Section 2(1). Corporate cash deposit does not breach statutory limit; compliant.",
                            "missing": [],
                            "detected_contradictions": [],
                            "suggested_queries": []
                        }
                elif "breached': true" in prompt_lower or "structuring': true" in prompt_lower or "breached: true" in prompt_lower or "breaching" in prompt_lower or "over-limit" in prompt_lower:
                    mock_dict = {
                        "sufficient": True,
                        "assessment": "SATISFIED",
                        "recommended_disposition": "DRAFT_STR",
                        "reason": "Transaction turnover breaches statutory cash reporting limits under CBN AML/CFT Regulations 2022 Section 10.",
                        "missing": [],
                        "detected_contradictions": [],
                        "suggested_queries": []
                    }
                elif "breached': false" in prompt_lower or "breached: false" in prompt_lower or "compliant with" in prompt_lower or "strictly below" in prompt_lower:
                    mock_dict = {
                        "sufficient": True,
                        "assessment": "SATISFIED",
                        "recommended_disposition": "CLEAR_NO_SUSPICION",
                        "reason": "Transaction verified compliant with statutory limits under CBN AML/CFT Regulations 2022 Section 10; does not breach threshold.",
                        "missing": [],
                        "detected_contradictions": [],
                        "suggested_queries": []
                    }
                else:
                    mock_dict = {
                        "sufficient": True,
                        "assessment": "SATISFIED",
                        "recommended_disposition": "DRAFT_STR",
                        "reason": "Compliance investigation completed across regulatory rules and internal records.",
                        "missing": [],
                        "detected_contradictions": [],
                        "suggested_queries": []
                    }

        elif schema_name == "RefinePlan":
            if "case-c" in prompt_lower or "kudirat" in prompt_lower or "temporal" in prompt_lower or "2021" in prompt_lower or "2020" in prompt_lower or "predates" in prompt_lower:
                tx_date = "2021-08-14"
                for line in prompt.splitlines():
                    if "Date:" in line:
                        try:
                            tx_date = line.split("Date:", 1)[1].strip().split("T")[0].split()[0]
                        except Exception:
                            pass
                mock_dict = {
                    "action": f"Reformulate regulatory search with strict temporal filter: effective_before='{tx_date}' to retrieve the governing historical regulation in force in {tx_date[:7]}.",
                    "planned_tool_calls": [
                        {
                            "tool_name": "regulation_search",
                            "parameters": {"query": "corporate cash deposit limit", "effective_before": tx_date}
                        },
                        {
                            "tool_name": "threshold_calc",
                            "parameters": {"amounts": [7500000.0], "timestamps": [f"{tx_date} 11:20:00"], "entity_type": "CORPORATE"}
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
            if "case-b" in prompt_lower or "musa ibrahim" in prompt_lower:
                mock_dict = {
                    "claims": [
                        {
                            "text": "Watchlist search identified 1.00 similarity match for Musa Ibrahim (PEP category). Customer KYC DOB (1994-08-12) conflicts with PEP DOB (1961-04-03).",
                            "supporting_sources": ["WATCHLIST-PEP-NGA-041", "KYC-ACC-IND-4412"],
                            "status": "insufficient"
                        }
                    ]
                }
            else:
                cust_name = "Subject Customer"
                amt_str = "statutory limit"
                for line in prompt.splitlines():
                    ls = line.strip().lower()
                    if ls.startswith("- customer name:"):
                        cust_name = line.split(":", 1)[1].strip()
                    elif ls.startswith("- amount:"):
                        amt_str = line.split(":", 1)[1].strip()

                mock_dict = {
                    "claims": [
                        {
                            "text": f"Compliance investigation established cash transaction of {amt_str} for customer {cust_name} evaluated under CBN AML/CFT regulations.",
                            "supporting_sources": ["CBN-AML-2022-SEC-10-1"],
                            "status": "supported"
                        }
                    ]
                }

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        set_last_llm_latency(latency_ms)
        logger.info(f"LLM Call [{self.provider_name}] Schema: {schema_name} Latency: {latency_ms}ms")
        return schema.model_validate(mock_dict)

def extract_json_content(content: str) -> str:
    """Strips markdown code fences and isolates valid JSON object or array."""
    clean = content.strip()
    if clean.startswith("```json"):
        clean = clean[7:]
    elif clean.startswith("```"):
        clean = clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    clean = clean.strip()

    if not (clean.startswith("{") or clean.startswith("[")):
        start_idx = clean.find("{")
        end_idx = clean.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            clean = clean[start_idx:end_idx + 1]
    return clean

def is_valid_api_key(key: Optional[str]) -> bool:
    """Checks whether an API key is provided and not a placeholder."""
    if not key:
        return False
    k = key.strip().lower()
    placeholders = {"...", "placeholder", "your_meta_api_key_here", "your_api_key", "meta_placeholder", "gsk_placeholder"}
    if k in placeholders or k.startswith("your_") or len(k) < 6:
        return False
    return True

def format_schema_instruction(schema: Type[BaseModel]) -> str:
    """
    Builds a clean, human-readable JSON skeleton instruction without $defs/$ref blocks,
    preventing smaller models (like LLaMA-3.1-8B) from echoing schema meta-definitions.
    """
    schema_name = schema.__name__
    if schema_name == "InvestigationPlan":
        example = {
            "hypotheses": [
                "Hypothesis 1: Potential statutory cash threshold breach.",
                "Hypothesis 2: Transaction pattern and customer KYC require verification."
            ],
            "initial_questions": [
                "Verify transaction amount against CBN statutory threshold.",
                "Query transaction history and check PEP/Sanctions watchlists."
            ],
            "planned_tool_calls": [
                {
                    "tool_name": "threshold_calc",
                    "parameters": {"amounts": [5000000.0], "timestamps": ["2023-01-01 12:00:00"], "entity_type": "INDIVIDUAL"}
                },
                {
                    "tool_name": "regulation_search",
                    "parameters": {"query": "Cash transaction reporting limit threshold"}
                }
            ]
        }
    elif schema_name == "CritiqueDecision":
        example = {
            "sufficient": True,
                        "assessment": "SATISFIED",
                        "recommended_disposition": "DRAFT_STR",
                        "reason": "Detailed evidentiary rationale explaining whether evidence is sufficient or contradictory.",
            "missing": [],
            "detected_contradictions": [],
            "suggested_queries": []
        }
    elif schema_name == "RefinePlan":
        example = {
            "action": "Explanation of reformulated query to resolve missing evidence or contradiction.",
            "planned_tool_calls": [
                {
                    "tool_name": "regulation_search",
                    "parameters": {"query": "applicable regulation clause"}
                }
            ]
        }
    elif schema_name == "ClaimsSynthesis":
        example = {
            "claims": [
                {
                    "text": "Factual compliance claim extracted from collected evidence.",
                    "supporting_sources": ["SOURCE-ID-01"],
                    "status": "supported"
                }
            ]
        }
    else:
        example = schema.model_json_schema().get("properties", {})

    return (
        f"You MUST respond with a valid JSON object matching this exact field structure:\n"
        f"{json.dumps(example, indent=2)}\n\n"
        f"CRITICAL INSTRUCTIONS FOR JSON GENERATION:\n"
        f"1. Fill in the keys above with actual compliance data from the prompt.\n"
        f"2. DO NOT output '$defs', '$ref', 'properties', or schema definitions.\n"
        f"3. Return ONLY the raw JSON object. Do not include commentary or markdown fences."
    )

class OpenAICompatibleProvider(LLMProvider):
    """
    Adapter for any OpenAI-compatible API (Meta Model API, Ollama).
    """
    def __init__(
        self,
        provider_name: str,
        base_url: str,
        api_key: str,
        model: str,
        timeout: Optional[float] = None
    ):
        self._name = provider_name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout or float(os.getenv("LLM_TIMEOUT", "60.0"))
        self.client = httpx.Client(timeout=self.timeout)

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

        endpoint = f"{self.base_url}/chat/completions" if not self.base_url.endswith("/chat/completions") else self.base_url
        response = self.client.post(
            endpoint,
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        record_llm_usage(data)
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        set_last_llm_latency(latency_ms)
        logger.info(f"LLM Complete [{self.provider_name}] Latency: {latency_ms}ms")
        return data["choices"][0]["message"]["content"]

    def complete_structured(
        self,
        schema: Type[T],
        prompt: str,
        system: Optional[str] = None
    ) -> T:
        start_time = time.perf_counter()

        augmented_system = (
            (system or "") + 
            f"\n\nYou are a compliance intelligence engine.\n"
            f"{format_schema_instruction(schema)}"
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
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }

        endpoint = f"{self.base_url}/chat/completions" if not self.base_url.endswith("/chat/completions") else self.base_url
        try:
            response = self.client.post(
                endpoint,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if "response_format" in str(e.response.text).lower():
                # Retry without response_format if provider does not support OpenAI json_object mode
                del payload["response_format"]
                response = self.client.post(
                    endpoint,
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
            else:
                raise

        data = response.json()
        record_llm_usage(data)
        raw_content = data["choices"][0]["message"]["content"]

        clean_content = extract_json_content(raw_content)
        parsed_json = json.loads(clean_content)

        # Handle nested wrapper keys emitted by models (e.g. {"InvestigationPlan": {...}})
        if isinstance(parsed_json, dict):
            if schema.__name__ in parsed_json and isinstance(parsed_json[schema.__name__], dict):
                parsed_json = parsed_json[schema.__name__]
            elif "data" in parsed_json and isinstance(parsed_json["data"], dict) and len(parsed_json) == 1:
                parsed_json = parsed_json["data"]
            elif "response" in parsed_json and isinstance(parsed_json["response"], dict) and len(parsed_json) == 1:
                parsed_json = parsed_json["response"]
            elif "properties" in parsed_json and isinstance(parsed_json["properties"], dict):
                parsed_json = parsed_json["properties"]

            # Maximize LLM intelligence by gracefully normalizing flexible fields
            if schema.__name__ == "CritiqueDecision":
                if "assessment" in parsed_json and isinstance(parsed_json["assessment"], str):
                    raw_ass = parsed_json["assessment"].strip().upper()
                    for std_stat in ["SATISFIED", "INSUFFICIENT", "CONTRADICTED", "AMBIGUOUS"]:
                        if std_stat in raw_ass:
                            parsed_json["assessment"] = std_stat
                            break
                if "sufficient" in parsed_json and isinstance(parsed_json["sufficient"], str):
                    parsed_json["sufficient"] = parsed_json["sufficient"].strip().lower() in ("true", "yes", "1")
                # Ensure suggested_queries preserves rich model suggestions (whether string or dict)
                if "suggested_queries" in parsed_json and isinstance(parsed_json["suggested_queries"], list):
                    parsed_json["suggested_queries"] = [
                        sq if (isinstance(sq, dict) or isinstance(sq, str)) else str(sq)
                        for sq in parsed_json["suggested_queries"]
                    ]

            if "planned_tool_calls" in parsed_json and isinstance(parsed_json["planned_tool_calls"], list):
                parsed_json["planned_tool_calls"] = [
                    tc if (isinstance(tc, dict) or isinstance(tc, str)) else str(tc)
                    for tc in parsed_json["planned_tool_calls"]
                ]

        try:
            validated = schema.model_validate(parsed_json)
            record_llm_usage(None, schema_ok=True)
        except Exception as val_err:
            record_llm_usage(None, schema_ok=False)
            logger.error(f"Live model [{self.provider_name}] output failed schema validation for {schema.__name__}: {val_err}")
            raise ValueError(
                f"Model [{self.provider_name}] returned output that failed compliance schema validation for {schema.__name__}: {val_err}. "
                f"Raw extracted response: {clean_content[:250]}"
            )

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        set_last_llm_latency(latency_ms)
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
    LLM_PROVIDER=meta|ollama|mock|cached
    or mode="CACHED" / "LIVE"
    """
    global _provider_override
    if _provider_override is not None:
        return _provider_override

    env_mode = os.getenv("REGGUARD_MODE", "").upper()
    provider_type = os.getenv("LLM_PROVIDER", "").lower()
    is_explicit_live = (mode is not None and mode.upper() == "LIVE")

    if (mode and mode.upper() == "CACHED") or env_mode == "CACHED" or provider_type == "cached":
        from core.replay_engine import get_cached_provider
        return get_cached_provider()

    meta_key = os.getenv("META_API_KEY")
    default_model = os.getenv("LLM_MODEL", "llama-3.3-70b-instruct")

    if provider_type == "meta" or (not provider_type and is_valid_api_key(meta_key)):
        meta_model = os.getenv("META_MODEL", default_model)
        meta_base_url = os.getenv("META_BASE_URL", "https://api.meta.com/v1")
        if not is_valid_api_key(meta_key):
            if is_explicit_live:
                raise RuntimeError(
                    f"LIVE mode is requested with LLM_PROVIDER='meta', but META_API_KEY is not configured or is a placeholder. "
                    f"Please set a valid META_API_KEY in .env or switch execution mode to CACHED."
                )
            logger.warning("META_API_KEY is not configured or placeholder. Falling back to MockLLMProvider for offline execution.")
            return MockLLMProvider(f"mock/{meta_model}")
        return OpenAICompatibleProvider(
            provider_name=f"meta/{meta_model}",
            base_url=meta_base_url,
            api_key=meta_key,
            model=meta_model
        )
    elif provider_type == "ollama":
        ollama_model = os.getenv("OLLAMA_MODEL", default_model)
        ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        # Check if local Ollama daemon is reachable
        try:
            with httpx.Client(timeout=0.8) as probe:
                probe.get(f"{ollama_base_url.rstrip('/')}/models")
        except Exception as exc:
            if is_explicit_live:
                raise RuntimeError(
                    f"LIVE mode is requested with LLM_PROVIDER='ollama', but Ollama daemon at {ollama_base_url} is unreachable ({exc}). "
                    f"Ensure Ollama is running ('ollama serve') or switch execution mode to CACHED."
                )
            logger.warning(f"Ollama daemon not reachable at {ollama_base_url}. Falling back to MockLLMProvider.")
            return MockLLMProvider(f"mock/{ollama_model}")

        return OpenAICompatibleProvider(
            provider_name=f"ollama/{ollama_model}",
            base_url=ollama_base_url,
            api_key="ollama",
            model=ollama_model
        )

    if is_explicit_live and provider_type not in ("mock", "cached"):
        raise RuntimeError(
            "LIVE mode is requested, but no live LLM provider is configured (META_API_KEY is missing and Ollama daemon is offline). "
            "Please configure META_API_KEY or start Ollama, or switch execution mode to CACHED."
        )

    # Default offline mock provider
    mock_model = os.getenv("LLM_MODEL", "llama-3.3-70b-instruct")
    return MockLLMProvider(f"mock/{mock_model}")
