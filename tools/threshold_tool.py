from datetime import datetime
from typing import Any, Dict, List

def calculate_threshold(
    amounts: List[float],
    timestamps: List[str],
    entity_type: str,
    currency: str = "NGN"
) -> Dict[str, Any]:
    """
    Evaluates financial amounts against CBN statutory cash limits and smurfing rules.
    Statutory limits:
      - Individual: N5,000,000
      - Corporate:  N10,000,000
    """
    if not amounts:
        return {
            "aggregate_amount": 0.0,
            "statutory_threshold": 5_000_000.0 if entity_type.upper() == "INDIVIDUAL" else 10_000_000.0,
            "threshold_breached": False,
            "time_window_hours": 0.0,
            "structuring_indicator": False,
            "individual_counts": 0,
            "entity_type": entity_type.upper(),
            "currency": currency
        }

    aggregate_amount = sum(float(a) for a in amounts)
    statutory_threshold = 5_000_000.0 if entity_type.upper() == "INDIVIDUAL" else 10_000_000.0
    threshold_breached = aggregate_amount > statutory_threshold

    # Calculate time window in hours
    time_window_hours = 0.0
    if len(timestamps) >= 2:
        parsed_dates = []
        for ts in timestamps:
            # Handle standard formats: ISO or YYYY-MM-DD HH:MM:SS
            clean_ts = ts.replace("Z", "+00:00")
            try:
                parsed_dates.append(datetime.fromisoformat(clean_ts))
            except ValueError:
                parsed_dates.append(datetime.strptime(ts, "%Y-%m-%d %H:%M:%S"))
        
        parsed_dates.sort()
        delta = parsed_dates[-1] - parsed_dates[0]
        time_window_hours = delta.total_seconds() / 3600.0

    # Structuring rule:
    # 2+ transactions, aggregate > threshold, but EACH transaction is below threshold, within 72h window
    all_below_threshold = all(float(a) < statutory_threshold for a in amounts)
    structuring_indicator = (
        threshold_breached and
        len(amounts) >= 2 and
        all_below_threshold and
        (time_window_hours <= 72.0 or len(timestamps) <= 1)
    )

    return {
        "aggregate_amount": round(aggregate_amount, 2),
        "statutory_threshold": statutory_threshold,
        "threshold_breached": threshold_breached,
        "time_window_hours": round(time_window_hours, 2),
        "structuring_indicator": structuring_indicator,
        "individual_counts": len(amounts),
        "entity_type": entity_type.upper(),
        "currency": currency
    }
