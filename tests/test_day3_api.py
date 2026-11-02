import asyncio
import os
import sys
import pytest
from httpx import AsyncClient, ASGITransport

# Ensure repository root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.server import app
from app.manager import manager

@pytest.mark.asyncio
async def test_health_and_cases():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Health check
        res_health = await client.get("/health")
        assert res_health.status_code == 200
        health_data = res_health.json()
        assert health_data["status"] == "healthy"
        assert "provider" in health_data

        # Cases list
        res_cases = await client.get("/cases")
        assert res_cases.status_code == 200
        cases = res_cases.json()
        assert len(cases) == 3
        case_ids = [c["id"] for c in cases]
        assert "CASE-B-PEP-002" in case_ids

@pytest.mark.asyncio
async def test_full_investigation_sse_lifecycle():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Start investigation
        start_res = await client.post(
            "/investigations",
            json={"case_id": "CASE-B-PEP-002", "mode": "CACHED"}
        )
        assert start_res.status_code == 200
        start_data = start_res.json()
        inv_id = start_data["investigation_id"]
        assert inv_id.startswith("inv_")
        assert start_data["status"] in ("INITIALIZED", "RUNNING")

        # 2. Connect to SSE stream and collect events
        collected_event_types = []
        async with client.stream("GET", f"/investigations/{inv_id}/stream") as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    event_type = line.split(":", 1)[1].strip()
                    collected_event_types.append(event_type)
                if "investigation_completed" in collected_event_types:
                    break

        print(f"\nCollected SSE Event Types: {collected_event_types}")
        assert "state_transition" in collected_event_types
        assert "claim_added" in collected_event_types
        assert "evidence_insufficient" in collected_event_types
        assert "synthesis_started" in collected_event_types
        assert "escalation" in collected_event_types
        assert "investigation_completed" in collected_event_types

        # 3. Retrieve full state snapshot
        snap_res = await client.get(f"/investigations/{inv_id}")
        assert snap_res.status_code == 200
        snap = snap_res.json()
        assert snap["investigation_id"] == inv_id
        assert snap["status"] == "ESCALATED"
        assert snap["final_status"] == "escalated"
        assert len(snap["claims"]) >= 2
        assert len(snap["event_log"]) >= 16

        # 4. Submit human compliance officer decision
        decision_payload = {
            "decision": "ESCALATE_TO_SENIOR",
            "notes": "Confirmed 33-year DOB mismatch. Escalating for manual biometric BVN verification.",
            "officer_id": "OFFICER_CBN_41"
        }
        dec_res = await client.post(f"/investigations/{inv_id}/decision", json=decision_payload)
        assert dec_res.status_code == 200
        assert dec_res.json()["status"] == "RECORDED"

        # Verify decision reflected in snapshot
        snap_res_after = await client.get(f"/investigations/{inv_id}")
        assert snap_res_after.json()["human_decision"]["decision"] == "ESCALATE_TO_SENIOR"

@pytest.mark.asyncio
async def test_dashboard_static_serve():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/")
        assert res.status_code == 200
        html = res.text
        assert "RegGuard AI" in html
        assert "viewport" in html
        assert "lg:grid-cols-12" in html
