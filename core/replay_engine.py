import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Type, TypeVar
from pydantic import BaseModel

logger = logging.getLogger("regguard.replay")

T = TypeVar("T", bound=BaseModel)

DEFAULT_REPLAY_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "replay_fixtures"))
DEFAULT_REPLAY_FILE = os.path.join(DEFAULT_REPLAY_DIR, "replay_store.json")

class DeterministicReplayMismatchError(Exception):
    """
    Raised when CACHED mode encounters an unknown prompt/input key.
    Guarantees that state transitions cannot be fabricated or drift from recorded fixtures.
    """
    pass

def generate_fixture_key(node_name: str, input_payload: dict) -> str:
    """
    Deterministic compound keying algorithm:
    fixture_key = SHA256(node_name + ':' + canonical_json(inputs))
    """
    serialized = json.dumps(input_payload, sort_keys=True, separators=(",", ":"))
    content = f"{node_name}:{serialized}".encode("utf-8")
    return hashlib.sha256(content).hexdigest()

class ReplayStore:
    """
    In-memory and on-disk repository of verified deterministic replay fixtures.
    """
    def __init__(self, filepath: str = DEFAULT_REPLAY_FILE):
        self.filepath = filepath
        self._entries: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self, filepath: Optional[str] = None):
        target = filepath or self.filepath
        if os.path.exists(target):
            try:
                with open(target, "r", encoding="utf-8") as f:
                    self._entries = json.load(f)
                logger.info(f"Loaded {len(self._entries)} deterministic replay fixtures from {target}")
            except Exception as e:
                logger.warning(f"Could not load replay store from {target}: {e}")
                self._entries = {}
        else:
            self._entries = {}

    def save(self, filepath: Optional[str] = None):
        target = filepath or self.filepath
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(self._entries, f, indent=2, sort_keys=True)
        logger.info(f"Saved {len(self._entries)} replay fixtures to {target}")

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        return self._entries.get(key)

    def add(
        self,
        key: str,
        node_name: str,
        schema_name: str,
        input_payload: dict,
        output_payload: dict,
        metadata: Optional[dict] = None
    ):
        self._entries[key] = {
            "key": key,
            "node_name": node_name,
            "schema_name": schema_name,
            "input_payload": input_payload,
            "output_payload": output_payload,
            "metadata": metadata or {},
            "recorded_at": datetime.now(timezone.utc).isoformat()
        }

    def __len__(self) -> int:
        return len(self._entries)

from core.llm_adapter import LLMProvider

def infer_node_name_from_schema(schema_name: str) -> str:
    mapping = {
        "InvestigationPlan": "plan",
        "CritiqueDecision": "critique",
        "RefinePlan": "refine",
        "ClaimsSynthesis": "act"
    }
    return mapping.get(schema_name, "general")

class CachedLLMProvider(LLMProvider):
    """
    Deterministic replay LLM provider.
    Intercepts calls, hashes exact canonical inputs, and looks up recorded fixtures.
    Throws DeterministicReplayMismatchError if any character in prompt or schema drifts.
    """
    def __init__(
        self,
        replay_store: Optional[ReplayStore] = None,
        provider_name: str = "cached/llama-3.3-70b-replay"
    ):
        self._name = provider_name
        self.store = replay_store if replay_store is not None else get_replay_store()

    @property
    def provider_name(self) -> str:
        return self._name

    def complete(self, prompt: str, system: Optional[str] = None) -> str:
        input_payload = {"prompt": prompt.strip()}
        if system:
            input_payload["system"] = system.strip()

        key = generate_fixture_key("unstructured", input_payload)
        entry = self.store.get(key)
        if not entry:
            raise DeterministicReplayMismatchError(
                f"Deterministic replay mismatch: No cached fixture found for key '{key}'. "
                f"Prompt excerpt: '{prompt[:80]}...'."
            )
        return entry["output_payload"].get("text", "")

    def complete_structured(
        self,
        schema: Type[T],
        prompt: str,
        system: Optional[str] = None
    ) -> T:
        start_time = time.perf_counter()
        schema_name = schema.__name__
        node_name = infer_node_name_from_schema(schema_name)

        input_payload = {
            "prompt": prompt.strip(),
            "schema": schema_name
        }
        if system:
            input_payload["system"] = system.strip()

        key = generate_fixture_key(node_name, input_payload)
        entry = self.store.get(key)

        if not entry:
            raise DeterministicReplayMismatchError(
                f"Deterministic replay mismatch: No cached fixture found for key '{key}' "
                f"(node: '{node_name}', schema: '{schema_name}'). "
                f"Prompt begins with: '{prompt.strip()[:100]}...'"
            )

        output_dict = entry["output_payload"]
        validated = schema.model_validate(output_dict)
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.info(f"Replay HIT [{self.provider_name}] Key: {key[:12]}... Schema: {schema_name} ({latency_ms}ms)")
        return validated

class RecordingLLMProvider(LLMProvider):
    """
    Decorator provider that intercepts calls to an inner LLM provider,
    executes them, and stores the deterministic fixture in a ReplayStore.
    """
    def __init__(self, inner: LLMProvider, replay_store: Optional[ReplayStore] = None):
        self.inner = inner
        self.store = replay_store if replay_store is not None else get_replay_store()

    @property
    def provider_name(self) -> str:
        return f"recording({self.inner.provider_name})"

    def complete(self, prompt: str, system: Optional[str] = None) -> str:
        result = self.inner.complete(prompt, system=system)
        input_payload = {"prompt": prompt.strip()}
        if system:
            input_payload["system"] = system.strip()
        key = generate_fixture_key("unstructured", input_payload)
        self.store.add(
            key=key,
            node_name="unstructured",
            schema_name="str",
            input_payload=input_payload,
            output_payload={"text": result}
        )
        return result

    def complete_structured(
        self,
        schema: Type[T],
        prompt: str,
        system: Optional[str] = None
    ) -> T:
        result = self.inner.complete_structured(schema, prompt, system=system)
        schema_name = schema.__name__
        node_name = infer_node_name_from_schema(schema_name)

        input_payload = {
            "prompt": prompt.strip(),
            "schema": schema_name
        }
        if system:
            input_payload["system"] = system.strip()

        key = generate_fixture_key(node_name, input_payload)
        output_payload = result.model_dump()
        self.store.add(
            key=key,
            node_name=node_name,
            schema_name=schema_name,
            input_payload=input_payload,
            output_payload=output_payload
        )
        return result

_global_replay_store: Optional[ReplayStore] = None

def get_replay_store(filepath: Optional[str] = None) -> ReplayStore:
    global _global_replay_store
    if _global_replay_store is None or filepath is not None:
        _global_replay_store = ReplayStore(filepath or DEFAULT_REPLAY_FILE)
    return _global_replay_store

def get_cached_provider(store: Optional[ReplayStore] = None) -> CachedLLMProvider:
    return CachedLLMProvider(replay_store=store if store is not None else get_replay_store())
