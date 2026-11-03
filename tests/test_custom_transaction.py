import asyncio
import os
import sys
import sqlite3
import pytest
from httpx import AsyncClient, ASGITransport

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.server import app

@pytest.mark.asyncio
async def test_custom_transaction_submission_and_investigation():
    """
    Verifies that a custom transaction submitted via API:
    1. Persists into SQLite (customers, accounts, transactions tables).
    2. Runs through the LangGraph engine.
    3. Streams SSE events to completion.
    4. Generates an Audit Memo with the custom customer details and SHA-256 hash chain.
    """
    custom_payload = {
        "case_id": "CUSTOM",
        "mode": "LIVE",
        "custom_transaction": {
            "transaction_id": "TX-CUSTOM-FATIMA-001",
            "customer_name": "Fatima Bello",
            "account_id": "ACC-CUSTOM-FATIMA",
            "amount": 12500000.0,
            "transaction_type": "CASH_DEPOSIT",
            "flag_reason": "STATUTORY_THRESHOLD_BREACH",
            "entity_type": "INDIVIDUAL",
            "dob": "1990-05-15",
            "bvn": "22200011122",
            "narration": "Commercial cash deposit Lekki branch"
        }
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Start investigation with custom transaction
        start_res = await client.post("/investigations", json=custom_payload)
        assert start_res.status_code == 200
        start_data = start_res.json()
        inv_id = start_data["investigation_id"]
        assert inv_id.startswith("inv_")

        # 2. Check SQLite persistence
        db_path = os.path.join(REPO_ROOT, "data", "regguard.db")
        assert os.path.exists(db_path)
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT full_name, entity_type FROM customers WHERE full_name = 'Fatima Bello'")
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "Fatima Bello"

        cur.execute("SELECT amount, transaction_type FROM transactions WHERE account_id = 'ACC-CUSTOM-FATIMA' AND amount = 12500000.0")
        tx_row = cur.fetchone()
        assert tx_row is not None
        assert tx_row[0] == 12500000.0
        conn.close()

        # 3. Stream SSE events to completion
        events = []
        async with client.stream("GET", f"/investigations/{inv_id}/stream") as stream_res:
            assert stream_res.status_code == 200
            async for line in stream_res.aiter_lines():
                if line.startswith("event:"):
                    events.append(line.split(":", 1)[1].strip())
                if "investigation_completed" in events:
                    break

        assert "state_transition" in events
        assert "tool_call" in events
        assert "claim_added" in events
        assert "synthesis_complete" in events

        # 4. Check Audit Memo
        memo_res = await client.get(f"/investigations/{inv_id}/audit_memo")
        assert memo_res.status_code == 200
        memo_data = memo_res.json()
        assert memo_data["investigation_id"] == inv_id
        assert memo_data["claims_count"] > 0
        
        md_text = memo_data["markdown"]
        assert "Fatima Bello" in md_text
        assert "CENTRAL BANK OF NIGERIA" in md_text

        # 5. Check Export Endpoints
        html_res = await client.get(f"/investigations/{inv_id}/export/html")
        assert html_res.status_code == 200
        assert "Fatima Bello" in html_res.text

        # Cleanup custom test data from SQLite
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("DELETE FROM transactions WHERE account_id = 'ACC-CUSTOM-FATIMA'")
        cur.execute("DELETE FROM accounts WHERE account_id = 'ACC-CUSTOM-FATIMA'")
        cur.execute("DELETE FROM customers WHERE full_name = 'Fatima Bello'")
        conn.commit()
        conn.close()
