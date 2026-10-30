import json
import os
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

DEFAULT_WATCHLIST_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "seeded_watchlist.json"))

def _similarity(a: str, b: str) -> float:
    """Computes case-insensitive similarity score between two strings."""
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()

class WatchlistTool:
    """
    Fuzzy search against seeded PEPs and Sanctions records with DOB corroboration.
    """
    def __init__(self, filepath: Optional[str] = None):
        self.filepath = filepath or DEFAULT_WATCHLIST_PATH
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"Watchlist file not found at {self.filepath}")
        with open(self.filepath, "r", encoding="utf-8") as f:
            self.records = json.load(f)

    def lookup(
        self,
        name: str,
        dob: Optional[str] = None,
        nationality: Optional[str] = None,
        threshold: float = 0.80
    ) -> Dict[str, Any]:
        """
        Fuzzy matches name against watchlist entries and aliases.
        Evaluates DOB consistency.
        """
        best_match = None
        best_score = 0.0

        for record in self.records:
            # Score against primary name
            score = _similarity(name, record["name"])
            
            # Score against aliases
            for alias in record.get("aliases", []):
                alias_score = _similarity(name, alias)
                if alias_score > score:
                    score = alias_score

            if score > best_score:
                best_score = score
                best_match = record

        if best_match and best_score >= threshold:
            # Evaluate Date of Birth status
            record_dob = best_match.get("dob")
            if dob and record_dob:
                if dob.strip() == record_dob.strip():
                    dob_status = "EXACT"
                else:
                    dob_status = "MISMATCH"
            else:
                dob_status = "UNAVAILABLE"

            return {
                "match_found": True,
                "best_match": {
                    "watchlist_id": best_match["watchlist_id"],
                    "matched_name": best_match["name"],
                    "aliases": best_match.get("aliases", []),
                    "dob": record_dob,
                    "category": best_match["category"],
                    "role_description": best_match.get("role_description", ""),
                    "name_similarity_score": round(best_score, 2),
                    "dob_match_status": dob_status,
                    "risk_level": best_match.get("risk_level", "HIGH")
                }
            }

        return {
            "match_found": False,
            "best_match": None,
            "highest_similarity_score": round(best_score, 2)
        }

_default_watchlist_tool = None

def watchlist_lookup(
    name: str,
    dob: Optional[str] = None,
    nationality: Optional[str] = None,
    threshold: float = 0.80
) -> Dict[str, Any]:
    """Convenience functional wrapper for watchlist search."""
    global _default_watchlist_tool
    if _default_watchlist_tool is None:
        _default_watchlist_tool = WatchlistTool()
    return _default_watchlist_tool.lookup(name, dob, nationality, threshold)
