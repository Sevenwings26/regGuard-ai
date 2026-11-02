import asyncio
import os
import sys
import pytest
from httpx import AsyncClient, ASGITransport

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.server import app

@pytest.mark.asyncio
async def test_responsive_layout_html_structure():
    """
    Day 8 Verification:
    - Asserts that fixed 1280x720 body dimensions have been removed.
    - Asserts that standard responsive meta viewport tag is present.
    - Asserts responsive Tailwind grid classes (grid-cols-1, lg:grid-cols-12) are present.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/")
        assert res.status_code == 200
        html = res.text

        # 1. Responsive Viewport Check
        assert '<meta name="viewport" content="width=device-width, initial-scale=1.0">' in html
        
        # 2. Assert absence of fixed 1280px / 720px body sizing
        assert "width: 1280px;" not in html
        assert "height: 720px;" not in html

        # 3. Assert presence of responsive layout classes
        assert "grid-cols-1" in html
        assert "lg:grid-cols-12" in html
        assert "min-h-screen" in html

@pytest.mark.asyncio
async def test_three_column_ui_elements():
    """
    Verifies that all 3 columns and key interactive visual components exist in index.html.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/")
        html = res.text

        # Column 1 elements
        assert "State Machine" in html
        assert "Node Stepper" in html or "nodeSteps" in html
        assert "Sub-Step Activity Stream" in html

        # Column 2 elements
        assert "Evidence Ledger" in html
        assert "SHA-256 Hash Chain" in html
        assert "Flagged Transaction" in html

        # Column 3 elements
        assert "Synthesis & Review" in html
        assert "Evidence Gaps & Contradictions" in html
        assert "Case Disposition" in html
        assert "Compliance Officer Determination" in html
        assert "APPROVE_STR" in html or "Approve STR" in html

@pytest.mark.asyncio
async def test_sse_streaming_live_event_transitions():
    """
    Tests live SSE event streaming across state machine transitions in CACHED mode.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Start investigation
        start_res = await client.post(
            "/investigations",
            json={"case_id": "CASE-A-STRUCTURING", "mode": "CACHED"}
        )
        assert start_res.status_code == 200
        inv_id = start_res.json()["investigation_id"]

        # Stream events
        events_received = []
        async with client.stream("GET", f"/investigations/{inv_id}/stream") as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    events_received.append(line.split(":", 1)[1].strip())
                if "investigation_completed" in events_received:
                    break

        assert "state_transition" in events_received
        assert "tool_call" in events_received
        assert "claim_added" in events_received
        assert "synthesis_started" in events_received
        assert "synthesis_complete" in events_received
        assert "investigation_completed" in events_received
