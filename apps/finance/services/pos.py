"""POS Phase 8A boundary: tender settlement remains a later Finance phase."""


def pos_candidate_readiness(candidate):
    if candidate.event_code == "POS_TENDER":
        return {"status": "DEFERRED", "reason": "Cash/Bank/Payment ledger is Phase 8B."}
    if candidate.event_code in {"POS_SALE_REVENUE", "POS_COGS"}:
        return {
            "status": "DEFERRED",
            "reason": "A balanced Phase 8A counter-account is not available.",
        }
    return {"status": "PENDING_SOURCE", "reason": "Unsupported POS source candidate."}
