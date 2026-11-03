import asyncio
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional
from app.graph import build_investigation_graph
from app.state import InvestigationState, verify_claims_chain

FIXTURES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "fixtures"))

class InvestigationSession:
    def __init__(self, investigation_id: str, case_id: str, mode: str):
        self.investigation_id = investigation_id
        self.case_id = case_id
        self.mode = mode
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.status = "INITIALIZED"
        self.queue: asyncio.Queue = asyncio.Queue()
        self.state_snapshot: Dict[str, Any] = {}
        self.human_decision: Optional[Dict[str, Any]] = None
        self.task: Optional[asyncio.Task] = None

class InvestigationManager:
    """
    Decouples LangGraph execution from HTTP/SSE request handlers.
    Manages in-memory investigation queues and background workers.
    """
    def __init__(self):
        self.sessions: Dict[str, InvestigationSession] = {}
        self._graph = None

    @property
    def graph(self):
        if self._graph is None:
            self._graph = build_investigation_graph()
        return self._graph

    def get_case_fixtures(self, case_id: str) -> Dict[str, Any]:
        """Loads case metadata and scenario payloads."""
        cid = case_id.lower()
        if "case-a" in cid or "case_a" in cid or "structuring" in cid:
            filename = "mock_case_a.json"
        elif "case-c" in cid or "case_c" in cid or "temporal" in cid:
            filename = "mock_case_c.json"
        else:
            filename = "mock_case_b.json"

        filepath = os.path.join(FIXTURES_DIR, filename)
        if not os.path.exists(filepath):
            filepath = os.path.join(FIXTURES_DIR, "mock_case_b.json")

        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def persist_custom_transaction_db(self, tx: Dict[str, Any]):
        """Persists custom transaction, account, and customer into SQLite so tools find it."""
        db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "regguard.db"))
        if not os.path.exists(db_path):
            return

        account_id = tx.get("account_id") or "ACC-CUSTOM-01"
        cust_id = f"CUST-{account_id[-4:]}"
        cust_name = tx.get("customer_name", "Custom Customer")
        entity_type = tx.get("entity_type", "INDIVIDUAL")
        dob = tx.get("dob") or "1990-01-01"
        bvn = tx.get("bvn") or "22200011122"
        tx_id = tx.get("transaction_id") or f"TX-CUSTOM-{uuid.uuid4().hex[:6].upper()}"
        amount = float(tx.get("amount", 0.0))
        timestamp = tx.get("timestamp") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        flag_code = tx.get("flag_reason", "MANUAL_COMPLIANCE_FLAG")
        narration = tx.get("narration", "Custom client transaction")

        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            # 1. Customer
            cur.execute(
                """
                INSERT OR IGNORE INTO customers (customer_id, full_name, entity_type, dob, bvn, nationality, risk_rating, kyc_status, created_at)
                VALUES (?, ?, ?, ?, ?, 'NGA', 'HIGH', 'VERIFIED', ?)
                """,
                (cust_id, cust_name, entity_type, dob, bvn, datetime.now(timezone.utc).isoformat())
            )
            # 2. Account
            cur.execute(
                """
                INSERT OR IGNORE INTO accounts (account_id, customer_id, account_number, account_type, currency, balance, status, opened_date)
                VALUES (?, ?, ?, ?, 'NGN', ?, 'ACTIVE', '2022-01-01')
                """,
                (account_id, cust_id, tx.get("account_number", "0998877665"), "SAVINGS" if entity_type == "INDIVIDUAL" else "CORPORATE", amount * 1.5)
            )
            # 3. Transaction
            cur.execute(
                """
                INSERT OR REPLACE INTO transactions (transaction_id, account_id, transaction_type, amount, currency, narration, channel, timestamp, flag_code)
                VALUES (?, ?, ?, ?, 'NGN', ?, 'BRANCH_TELLER', ?, ?)
                """,
                (tx_id, account_id, tx.get("transaction_type", "CASH_DEPOSIT"), amount, narration, timestamp, flag_code)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def create_investigation(
        self,
        case_id: str,
        mode: str = "LIVE",
        custom_transaction: Optional[Dict[str, Any]] = None
    ) -> InvestigationSession:
        """Initializes a new investigation session and starts background execution."""
        investigation_id = f"inv_{uuid.uuid4().hex[:8]}"
        session = InvestigationSession(investigation_id, case_id, mode)
        self.sessions[investigation_id] = session

        if custom_transaction:
            # Generate transaction_id and timestamp if needed
            if not custom_transaction.get("transaction_id"):
                custom_transaction["transaction_id"] = f"TX-CUSTOM-{uuid.uuid4().hex[:6].upper()}"
            if not custom_transaction.get("timestamp"):
                custom_transaction["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

            # Persist to local database
            self.persist_custom_transaction_db(custom_transaction)

            case_data = {
                "case_id": case_id if case_id != "CUSTOM" else custom_transaction["transaction_id"],
                "jurisdiction": "NGA_CBN",
                "flagged_transaction": custom_transaction
            }
        else:
            case_data = self.get_case_fixtures(case_id)

        initial_state: InvestigationState = {
            "case_id": case_data.get("case_id", case_id),
            "jurisdiction": case_data.get("jurisdiction", "NGA_CBN"),
            "flagged_transaction": case_data.get("flagged_transaction", {}),
            "claims": [],
            "unresolved_questions": [],
            "retry_count": 0,
            "max_retries": 1,
            "current_node": "START",
            "event_log": [],
            "last_event_sequence": 0,
            "evidence_sufficient": False,
            "final_status": "in_progress",
            "critique_decision": None,
            "audit_memo": None,
            "planned_queries": [],
            "mode": mode.upper(),
        }
        session.state_snapshot = initial_state

        # Dispatch background worker
        session.task = asyncio.create_task(self._run_investigation_worker(session, initial_state))
        return session

    async def _run_investigation_worker(self, session: InvestigationSession, initial_state: InvestigationState):
        """Asynchronously steps through the LangGraph loop and dispatches SSE events."""
        session.status = "RUNNING"
        dispatched_event_count = 0

        try:
            # Step through the graph
            for step_output in self.graph.stream(initial_state, stream_mode="updates"):
                for node_name, node_update in step_output.items():
                    # Update local state snapshot
                    for k, v in node_update.items():
                        if k in ("claims", "unresolved_questions", "event_log"):
                            session.state_snapshot[k] = session.state_snapshot.get(k, []) + v
                        else:
                            session.state_snapshot[k] = v

                    # Check for newly generated events in event_log
                    current_events = session.state_snapshot.get("event_log", [])
                    new_events = current_events[dispatched_event_count:]
                    for event in new_events:
                        await session.queue.put(event)
                        dispatched_event_count += 1

                    # Ergonomic pacing for demo visualization (300ms per node)
                    await asyncio.sleep(0.3)

            # Finalize status
            session.status = session.state_snapshot.get("final_status", "COMPLETED").upper()

            # Push terminal completion event
            terminal_event = {
                "event_type": "investigation_completed",
                "sequence_number": dispatched_event_count + 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "investigation_id": session.investigation_id,
                "payload": {
                    "final_status": session.status,
                    "case_id": session.case_id,
                    "claims_count": len(session.state_snapshot.get("claims", [])),
                    "audit_memo": session.state_snapshot.get("audit_memo", {})
                }
            }
            await session.queue.put(terminal_event)

        except Exception as e:
            session.status = "ERROR"
            error_event = {
                "event_type": "error",
                "sequence_number": dispatched_event_count + 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "investigation_id": session.investigation_id,
                "payload": {"error_message": str(e)}
            }
            await session.queue.put(error_event)

    async def stream_events(self, investigation_id: str) -> AsyncGenerator[str, None]:
        """Async generator emitting Server-Sent Events (SSE)."""
        session = self.sessions.get(investigation_id)
        if not session:
            yield f"event: error\ndata: {json.dumps({'error': 'Investigation not found'})}\n\n"
            return

        # Keep streaming until terminal event is seen or timeout
        while True:
            try:
                event = await asyncio.wait_for(session.queue.get(), timeout=15.0)
                event_type = event.get("event_type", "message")
                data_str = json.dumps(event)
                yield f"event: {event_type}\ndata: {data_str}\n\n"

                # Stop streaming after completion or error
                if event_type in ("investigation_completed", "error"):
                    break
            except asyncio.TimeoutError:
                # Keep-alive heartbeat comment
                yield ": ping\n\n"
                if session.status in ("COMPLETED", "ESCALATED", "ERROR"):
                    break

    def record_decision(
        self,
        investigation_id: str,
        decision: str,
        notes: str,
        officer_id: str = "OFFICER_CBN_01"
    ) -> Dict[str, Any]:
        """Records a human compliance officer action."""
        session = self.sessions.get(investigation_id)
        if not session:
            raise KeyError(f"Investigation {investigation_id} not found.")

        decision_payload = {
            "decision": decision,
            "notes": notes,
            "officer_id": officer_id,
            "recorded_at": datetime.now(timezone.utc).isoformat()
        }
        session.human_decision = decision_payload
        
        # Emit decision event into stream if queue active
        decision_event = {
            "event_type": "decision_recorded",
            "sequence_number": len(session.state_snapshot.get("event_log", [])) + 1,
            "timestamp": decision_payload["recorded_at"],
            "investigation_id": investigation_id,
            "payload": decision_payload
        }
        session.queue.put_nowait(decision_event)
        return decision_payload

    def get_snapshot(self, investigation_id: str) -> Dict[str, Any]:
        """Returns complete serializable snapshot of the investigation."""
        session = self.sessions.get(investigation_id)
        if not session:
            raise KeyError(f"Investigation {investigation_id} not found.")

        raw_claims = session.state_snapshot.get("claims", [])
        serializable_claims = [
            c.model_dump() if hasattr(c, "model_dump") else c
            for c in raw_claims
        ]

        return {
            "investigation_id": session.investigation_id,
            "case_id": session.case_id,
            "mode": session.mode,
            "status": session.status,
            "created_at": session.created_at,
            "current_node": session.state_snapshot.get("current_node", "START"),
            "retry_count": session.state_snapshot.get("retry_count", 0),
            "max_retries": session.state_snapshot.get("max_retries", 1),
            "claims": serializable_claims,
            "unresolved_questions": session.state_snapshot.get("unresolved_questions", []),
            "event_log": session.state_snapshot.get("event_log", []),
            "final_status": session.state_snapshot.get("final_status", "in_progress"),
            "audit_memo": session.state_snapshot.get("audit_memo"),
            "human_decision": session.human_decision
        }

# Global singleton
manager = InvestigationManager()
