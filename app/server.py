import os
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, Response, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.manager import manager
from app.audit_memo import generate_audit_memo_markdown, generate_audit_memo_html, get_canonical_json_for_claim
from app.state import compute_claim_hash

app = FastAPI(
    title="RegGuard AI Compliance Investigator",
    description="Autonomous Agentic Compliance Investigator under CBN AML/CFT Regulations",
    version="1.0.0"
)

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))

# Request schemas
class StartInvestigationRequest(BaseModel):
    case_id: str = Field(default="CASE-B-PEP-002", description="Identifier of the compliance case")
    mode: str = Field(default="CACHED", description="Execution mode: LIVE or CACHED")

class HumanDecisionRequest(BaseModel):
    decision: str = Field(..., description="Decision action: APPROVE_STR | REQUEST_MORE_INFO | ESCALATE_TO_SENIOR")
    notes: str = Field(..., description="Justification and notes from reviewing officer")
    officer_id: Optional[str] = Field(default="OFFICER_CBN_01", description="Reviewing officer badge/ID")

@app.get("/health")
async def health_check():
    provider = os.getenv("LLM_PROVIDER", "mock/llama-3.3-70b")
    return {
        "status": "healthy",
        "provider": provider,
        "active_sessions": len(manager.sessions)
    }

@app.get("/cases")
async def list_demo_cases():
    return [
        {
            "id": "CASE-A-STRUCTURING",
            "name": "Case A: Structuring & Threshold Breach",
            "subject": "Emeka Okafor (Retail Trader)",
            "flag": "RAPID_AGGREGATION_STRUCTURING",
            "description": "3 cash deposits totaling N5.5M within 36 hours evading statutory N5M reporting limit."
        },
        {
            "id": "CASE-B-PEP-002",
            "name": "Case B: PEP Watchlist Match (DOB Mismatch)",
            "subject": "Musa Ibrahim (Inward Transfer N8.2M)",
            "flag": "PEP_NAME_MATCH",
            "description": "High name similarity (0.87) to Former State Commissioner, but 33-year KYC DOB discrepancy."
        },
        {
            "id": "CASE-C-TEMPORAL",
            "name": "Case C: Regulatory Enactment Contradiction",
            "subject": "Kudirat Logistics Ltd (N7.5M Deposit)",
            "flag": "CORPORATE_CASH_THRESHOLD",
            "description": "2021 transaction flagged under 2022 regulations; requires temporal reconciliation to 2013 rules."
        }
    ]

@app.post("/investigations")
async def start_investigation(req: StartInvestigationRequest):
    session = manager.create_investigation(case_id=req.case_id, mode=req.mode.upper())
    return {
        "investigation_id": session.investigation_id,
        "case_id": session.case_id,
        "mode": session.mode,
        "status": session.status,
        "stream_url": f"/investigations/{session.investigation_id}/stream"
    }

@app.get("/investigations/{investigation_id}/stream")
async def stream_investigation(investigation_id: str):
    if investigation_id not in manager.sessions:
        raise HTTPException(status_code=404, detail="Investigation ID not found.")

    return StreamingResponse(
        manager.stream_events(investigation_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.get("/investigations/{investigation_id}")
async def get_investigation_state(investigation_id: str):
    try:
        return manager.get_snapshot(investigation_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Investigation ID not found.")

@app.post("/investigations/{investigation_id}/decision")
async def submit_human_decision(investigation_id: str, req: HumanDecisionRequest):
    try:
        recorded = manager.record_decision(
            investigation_id=investigation_id,
            decision=req.decision,
            notes=req.notes,
            officer_id=req.officer_id or "OFFICER_CBN_01"
        )
        return {"status": "RECORDED", "decision": recorded}
    except KeyError:
        raise HTTPException(status_code=404, detail="Investigation ID not found.")

@app.get("/investigations/{investigation_id}/audit_memo")
async def get_audit_memo(investigation_id: str):
    """Returns the structured and formatted audit memo for an investigation."""
    try:
        snapshot = manager.get_snapshot(investigation_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Investigation ID not found.")
    
    memo = snapshot.get("audit_memo") or {}
    return {
        "investigation_id": investigation_id,
        "case_id": snapshot.get("case_id"),
        "status": snapshot.get("status"),
        "disposition": memo.get("disposition", "PENDING"),
        "audit_memo": memo,
        "claims_count": len(snapshot.get("claims", [])),
        "markdown": generate_audit_memo_markdown(snapshot),
        "html": generate_audit_memo_html(snapshot)
    }

@app.get("/investigations/{investigation_id}/export/markdown")
async def export_audit_memo_markdown(investigation_id: str):
    """Exports official NFIU/CBN compliance memo in Markdown format."""
    try:
        snapshot = manager.get_snapshot(investigation_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Investigation ID not found.")
    
    md_content = generate_audit_memo_markdown(snapshot)
    filename = f"cbn_audit_memo_{investigation_id}.md"
    return Response(
        content=md_content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@app.get("/investigations/{investigation_id}/export/html")
async def export_audit_memo_html(investigation_id: str):
    """Exports printable official compliance audit document with print stylesheet."""
    try:
        snapshot = manager.get_snapshot(investigation_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Investigation ID not found.")
    
    html_content = generate_audit_memo_html(snapshot)
    return HTMLResponse(content=html_content)

@app.get("/investigations/{investigation_id}/claims/{claim_id}/verify")
async def verify_claim_endpoint(investigation_id: str, claim_id: str):
    """Verifies cryptographic hash chain integrity for an individual evidence block."""
    try:
        snapshot = manager.get_snapshot(investigation_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Investigation ID not found.")
    
    claims = snapshot.get("claims", [])
    target = next((c for c in claims if c.get("claim_id") == claim_id), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found in investigation.")
    
    canonical_str = get_canonical_json_for_claim(target)
    recalculated_hash = compute_claim_hash(target, target.get("prev_hash", "0" * 64))
    is_valid = (recalculated_hash == target.get("hash"))
    return {
        "claim_id": claim_id,
        "stored_hash": target.get("hash"),
        "recalculated_hash": recalculated_hash,
        "is_valid": is_valid,
        "canonical_json": canonical_str
    }

# Mount static frontend
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def serve_dashboard():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "message": "RegGuard AI API is operational. Place static/index.html to view dashboard.",
        "stream_endpoint": "/investigations/{id}/stream"
    }



