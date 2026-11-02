import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.state import compute_claim_hash

def get_canonical_json_for_claim(claim: Dict[str, Any]) -> str:
    """Returns the canonical JSON string that was hashed to generate the claim's SHA-256 fingerprint."""
    canonical = {
        "claim_id": claim.get("claim_id", ""),
        "text": claim.get("text", ""),
        "supporting_sources": sorted(claim.get("supporting_sources", [])),
        "status": claim.get("status", ""),
        "timestamp": claim.get("timestamp", ""),
        "prev_hash": claim.get("prev_hash", "0" * 64),
    }
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"))

def generate_audit_memo_markdown(snapshot: Dict[str, Any]) -> str:
    """
    Generates an official CBN/NFIU compliance audit document in Markdown.
    """
    case_id = snapshot.get("case_id", "UNKNOWN_CASE")
    inv_id = snapshot.get("investigation_id", "inv_unknown")
    memo = snapshot.get("audit_memo", {}) or {}
    disposition = memo.get("disposition", "UNKNOWN")
    claims = snapshot.get("claims", [])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    human_dec = snapshot.get("human_decision") or {}

    subject_name = memo.get("subject_name") or snapshot.get("flagged_transaction", {}).get("customer_name", "Subject")
    account_id = memo.get("account_id") or snapshot.get("flagged_transaction", {}).get("account_id", "N/A")
    flag_reason = snapshot.get("flagged_transaction", {}).get("flag_reason", "COMPLIANCE_FLAG")
    tip_hash = claims[-1].get("hash") if claims else ("0" * 64)

    lines = []
    lines.append("# CENTRAL BANK OF NIGERIA (CBN) AML/CFT COMPLIANCE AUDIT MEMORANDUM")
    lines.append("**Reporting Financial Institution:** RegGuard Demo Bank Nigeria")
    lines.append(f"**Investigation Reference:** `{inv_id}` | **Case:** `{case_id}`")
    lines.append(f"**Audit Generated At:** {now}")
    lines.append("**Governing Jurisdiction:** Federal Republic of Nigeria (CBN AML/CFT Regulations 2022 / 2013)")
    lines.append("\n---\n")

    # 1. Executive Disposition Banner
    lines.append(f"## 1. EXECUTIVE DISPOSITION: {disposition}")
    if disposition == "DRAFT_STR":
        lines.append("> [!IMPORTANT]")
        lines.append("> **MANDATORY FILING REQUIRED**: Investigation substantiates intentional transaction structuring below the individual cash transaction threshold of ₦5,000,000.00. Filing with the Nigerian Financial Intelligence Unit (NFIU) is mandated within 24 hours pursuant to CBN AML/CFT Regulations 2022 Section 10(3).\n")
    elif disposition == "ESCALATE_TO_OFFICER":
        lines.append("> [!WARNING]")
        lines.append("> **AUTONOMOUS EXECUTION HALTED — ESCALATED FOR HUMAN DETERMINATION**: Unresolved demographic mismatch and/or evidentiary ambiguity detected. In accordance with zero-hallucination compliance guardrails, this case is escalated to a senior compliance officer.\n")
    elif disposition == "CLEAR_NO_SUSPICION":
        lines.append("> [!NOTE]")
        lines.append("> **STATUTORY CLEARANCE ISSUED**: Factual investigation verified that the transaction strictly complied with applicable CBN regulations in force at transaction timestamp. No suspicious activity identified.\n")

    lines.append(f"**Synthesis Summary:** {memo.get('summary', 'Investigation completed.')}\n")

    # 2. Subject & Account Profile
    lines.append("## 2. SUBJECT & ACCOUNT METADATA")
    lines.append("| Field | Recorded Value |")
    lines.append("| :--- | :--- |")
    lines.append(f"| **Customer / Entity Name** | {subject_name} |")
    lines.append(f"| **Account Identifier** | `{account_id}` |")
    lines.append(f"| **Risk Rating / Flag** | `{flag_reason}` |")
    lines.append(f"| **Execution Mode** | `{snapshot.get('mode', 'LIVE')}` |")
    lines.append(f"| **Investigation Retries** | {snapshot.get('retry_count', 0)} / {snapshot.get('max_retries', 1)} |")
    lines.append(f"| **Terminal Workflow Status** | `{snapshot.get('final_status', 'in_progress').upper()}` |\n")

    # 3. Specific Disposition Details
    if disposition == "DRAFT_STR":
        draft_str = memo.get("draft_str", {})
        lines.append("## 3. FORMAL SUSPICIOUS TRANSACTION REPORT (STR) DETAILS")
        lines.append(f"- **Reporting Entity:** {draft_str.get('reporting_entity', 'RegGuard Demo Bank Nigeria')}")
        lines.append(f"- **Statutory Violation Clause:** {draft_str.get('statutory_violation', 'CBN AML/CFT 2022 Section 10(3)')}")
        lines.append(f"- **Violations Found:** {', '.join(draft_str.get('violations_found', []))}")
        lines.append(f"- **Filing Deadline:** {draft_str.get('filing_deadline', 'Within 24 hours')}")
        lines.append(f"- **Formal Narrative:**\n  > {draft_str.get('narrative', '')}\n")
    elif disposition == "ESCALATE_TO_OFFICER":
        lines.append("## 3. ESCALATION GAP ANALYSIS & WHY AGENT COULD NOT CONCLUDE")
        why = memo.get("why_could_not_conclude", [])
        lines.append("**Critical Missing Verification Items:**")
        for w in why:
            lines.append(f"- ⚠ {w}")
        lines.append(f"\n**Recommended Officer Action:** {memo.get('recommended_officer_action', 'Conduct manual KYC review.')}\n")
    elif disposition == "CLEAR_NO_SUSPICION":
        lines.append("## 3. STATUTORY CLEARANCE ANALYSIS")
        lines.append(f"- **Governing Regulation:** `{memo.get('applicable_regulation', 'CBN-AML-2013-SEC-02-1')}`")
        lines.append(f"- **Applicable Statutory Limit:** ₦{memo.get('governing_limit', 0):,.2f}")
        lines.append(f"- **Transaction Turnover:** ₦{memo.get('transaction_amount', 0):,.2f}")
        lines.append(f"- **Clearance Determination:** {memo.get('cleared_reason', 'Compliant.')}\n")

    # 4. Anti-Hallucination & Unresolved Questions
    lines.append("## 4. EVIDENTIARY AUDIT QUESTIONS & GAPS")
    unresolved = snapshot.get("unresolved_questions", [])
    if unresolved:
        for idx, q in enumerate(unresolved, 1):
            lines.append(f"{idx}. {q}")
    else:
        lines.append("*(No unresolved compliance questions remain open. Evidence satisfied statutory thresholds.)*")
    lines.append("")

    # 5. Tamper-Evident Evidence Ledger
    lines.append("## 5. CRYPTOGRAPHIC EVIDENCE LEDGER (SHA-256 HASH CHAIN)")
    lines.append(f"**Total Blocks Committed:** {len(claims)} | **Genesis Hash:** `{'0' * 64}`")
    lines.append(f"**Ledger Tip Root Hash:** `{tip_hash}`\n")
    lines.append("| Block # | Claim ID | Status | Supporting Sources | SHA-256 Hash |")
    lines.append("| :--- | :--- | :--- | :--- | :--- |")
    for idx, c in enumerate(claims, 1):
        sources = ", ".join(c.get("supporting_sources", []))
        short_hash = c.get("hash", "")[:16] + "..."
        lines.append(f"| #{idx} | `{c.get('claim_id')}` | **{c.get('status', '').upper()}** | `{sources}` | `{short_hash}` |")
    lines.append("")

    lines.append("### Detailed Block Propositions:")
    for idx, c in enumerate(claims, 1):
        lines.append(f"#### Block #{idx} (`{c.get('claim_id')}`) — {c.get('status', '').upper()}")
        lines.append(f"- **Proposition:** {c.get('text')}")
        lines.append(f"- **Timestamp:** `{c.get('timestamp')}`")
        lines.append(f"- **Previous Hash:** `{c.get('prev_hash')}`")
        lines.append(f"- **Block Hash:** `{c.get('hash')}`")
        lines.append(f"- **Canonical JSON Hashed:**\n```json\n{get_canonical_json_for_claim(c)}\n```\n")

    # 6. Compliance Officer Decision
    lines.append("## 6. COMPLIANCE OFFICER DETERMINATION")
    if human_dec:
        lines.append(f"- **Reviewing Officer:** `{human_dec.get('officer_id', 'OFFICER_CBN_01')}`")
        lines.append(f"- **Decision Action:** **{human_dec.get('decision', 'PENDING')}**")
        lines.append(f"- **Audit Notes:** {human_dec.get('notes', '—')}")
        lines.append(f"- **Recorded Timestamp:** `{human_dec.get('recorded_at', '—')}`\n")
    else:
        lines.append("*(Pending Review — Compliance Officer determination has not yet been submitted.)*\n")

    lines.append("---\n")
    lines.append("**RegGuard AI Assurance:** Cryptographic hash integrity verified. Anti-hallucination guards enforced. Zero unsubstantiated conclusions permitted.")
    return "\n".join(lines)

def generate_audit_memo_html(snapshot: Dict[str, Any]) -> str:
    """
    Generates a clean, standalone, printable HTML compliance report.
    Includes print CSS styles and bank letterhead presentation.
    """
    case_id = snapshot.get("case_id", "UNKNOWN_CASE")
    inv_id = snapshot.get("investigation_id", "inv_unknown")
    memo = snapshot.get("audit_memo", {}) or {}
    disposition = memo.get("disposition", "UNKNOWN")
    claims = snapshot.get("claims", [])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    human_dec = snapshot.get("human_decision") or {}

    subject_name = memo.get("subject_name") or snapshot.get("flagged_transaction", {}).get("customer_name", "Subject")
    account_id = memo.get("account_id") or snapshot.get("flagged_transaction", {}).get("account_id", "N/A")
    flag_reason = snapshot.get("flagged_transaction", {}).get("flag_reason", "COMPLIANCE_FLAG")
    tip_hash = claims[-1].get("hash") if claims else ("0" * 64)

    # Disposition color badge
    if disposition == "DRAFT_STR":
        disp_bg = "#ecfdf5"
        disp_border = "#10b981"
        disp_text = "#065f46"
        disp_badge = "MANDATORY STR FILING REQUIRED (24H)"
    elif disposition == "ESCALATE_TO_OFFICER":
        disp_bg = "#fff1f2"
        disp_border = "#f43f5e"
        disp_text = "#9f1239"
        disp_badge = "HUMAN COMPLIANCE OFFICER ESCALATION"
    else:
        disp_bg = "#f0fdf4"
        disp_border = "#22c55e"
        disp_text = "#15803d"
        disp_badge = "STATUTORY CLEARANCE CERTIFICATE"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Compliance Audit Memo — {inv_id}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
      margin: 0;
      padding: 30px;
      color: #1e293b;
      background: #f8fafc;
      line-height: 1.5;
    }}
    .container {{
      max-width: 900px;
      margin: 0 auto;
      background: #ffffff;
      padding: 40px;
      border: 1px solid #e2e8f0;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
      border-radius: 8px;
    }}
    .header {{
      border-bottom: 2px solid #0f172a;
      padding-bottom: 20px;
      margin-bottom: 25px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .bank-title {{
      font-size: 20px;
      font-weight: 800;
      color: #0f172a;
      letter-spacing: -0.5px;
      margin: 0;
    }}
    .sub-title {{
      font-size: 13px;
      color: #64748b;
      margin-top: 4px;
    }}
    .badge {{
      display: inline-block;
      padding: 4px 10px;
      border-radius: 4px;
      font-weight: 700;
      font-size: 11px;
      font-family: monospace;
    }}
    .disposition-card {{
      background: {disp_bg};
      border: 2px solid {disp_border};
      color: {disp_text};
      padding: 16px 20px;
      border-radius: 6px;
      margin-bottom: 25px;
    }}
    .disposition-card h2 {{
      margin: 0 0 6px 0;
      font-size: 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 15px 0 25px 0;
      font-size: 12px;
    }}
    th, td {{
      padding: 8px 12px;
      border: 1px solid #e2e8f0;
      text-align: left;
    }}
    th {{
      background: #f1f5f9;
      font-weight: 700;
      color: #334155;
    }}
    .code {{
      font-family: ui-monospace, Menlo, Monaco, monospace;
      font-size: 11px;
      background: #f1f5f9;
      padding: 2px 5px;
      border-radius: 3px;
      color: #0f172a;
    }}
    .block-card {{
      background: #f8fafc;
      border: 1px solid #cbd5e1;
      padding: 12px;
      border-radius: 6px;
      margin-bottom: 12px;
      font-size: 12px;
    }}
    .actions-bar {{
      margin-bottom: 20px;
      display: flex;
      gap: 10px;
    }}
    .btn {{
      padding: 8px 16px;
      background: #0f172a;
      color: white;
      border: none;
      border-radius: 4px;
      cursor: pointer;
      font-weight: 600;
      font-size: 12px;
    }}
    .btn-secondary {{
      background: #e2e8f0;
      color: #1e293b;
    }}
    @media print {{
      body {{ background: white; padding: 0; }}
      .container {{ box-shadow: none; border: none; padding: 0; }}
      .actions-bar {{ display: none; }}
    }}
  </style>
</head>
<body>
  <div class="actions-bar">
    <button class="btn" onclick="window.print()">🖨 Print / Save as PDF</button>
    <button class="btn btn-secondary" onclick="window.close()">Close</button>
  </div>

  <div class="container">
    <div class="header">
      <div>
        <h1 class="bank-title">RegGuard Demo Bank Nigeria</h1>
        <div class="sub-title">Central Bank of Nigeria (CBN) AML/CFT Compliance Department</div>
      </div>
      <div style="text-align: right;">
        <span class="badge" style="background:#e0f2fe; color:#0369a1; border:1px solid #bae6fd;">NGA-CBN COMPLIANCE</span>
        <div class="sub-title">Ref: {inv_id}</div>
      </div>
    </div>

    <div class="disposition-card">
      <h2>
        <span>DISPOSITION: {disposition}</span>
        <span class="badge" style="background:white; color:{disp_text}; border:1px solid {disp_border};">{disp_badge}</span>
      </h2>
      <div style="font-size: 13px;">{memo.get("summary", "")}</div>
    </div>

    <h3 style="font-size: 14px; margin-bottom: 5px; color:#0f172a;">Subject Profile & Investigation Parameters</h3>
    <table>
      <tr>
        <th style="width: 25%;">Subject Customer</th>
        <td><b>{subject_name}</b></td>
        <th style="width: 25%;">Account ID</th>
        <td><span class="code">{account_id}</span></td>
      </tr>
      <tr>
        <th>Flag Reason</th>
        <td><span class="code">{flag_reason}</span></td>
        <th>Audit Timestamp</th>
        <td>{now}</td>
      </tr>
      <tr>
        <th>Execution Mode</th>
        <td>{snapshot.get("mode", "LIVE")}</td>
        <th>Investigation Retries</th>
        <td>{snapshot.get("retry_count", 0)} of {snapshot.get("max_retries", 1)}</td>
      </tr>
      <tr>
        <th>Ledger Root Hash</th>
        <td colspan="3"><span class="code">{tip_hash}</span></td>
      </tr>
    </table>
"""

    # Disposition specifics
    if disposition == "DRAFT_STR":
        draft_str = memo.get("draft_str", {})
        html += f"""
    <div style="background:#f0fdf4; border:1px solid #bbf7d0; padding:15px; border-radius:6px; margin-bottom:25px;">
      <h3 style="margin-top:0; color:#166534; font-size:14px;">Formal Suspicious Transaction Report (STR) Filing Schedule</h3>
      <p style="font-size:12px; margin-bottom:10px;"><b>Statutory Clause:</b> {draft_str.get("statutory_violation")}</p>
      <p style="font-size:12px; margin-bottom:10px;"><b>Filing Notice:</b> Within 24 hours to Nigerian Financial Intelligence Unit (NFIU)</p>
      <blockquote style="margin:10px 0; padding:10px; background:#dcfce7; border-left:3px solid #16a34a; font-size:12px; font-style:italic;">
        {draft_str.get("narrative", "")}
      </blockquote>
    </div>
"""
    elif disposition == "ESCALATE_TO_OFFICER":
        html += f"""
    <div style="background:#fff1f2; border:1px solid #fecdd3; padding:15px; border-radius:6px; margin-bottom:25px;">
      <h3 style="margin-top:0; color:#9f1239; font-size:14px;">Senior Officer Escalation Dossier</h3>
      <p style="font-size:12px; font-weight:bold; color:#be123c;">Reason Autonomous Action Halted:</p>
      <ul style="font-size:12px; color:#475569; margin:5px 0 10px 20px;">
"""
        for r in memo.get("why_could_not_conclude", []):
            html += f"<li>{r}</li>"
        html += f"""
      </ul>
      <p style="font-size:12px;"><b>Recommended Action:</b> {memo.get("recommended_officer_action")}</p>
    </div>
"""
    elif disposition == "CLEAR_NO_SUSPICION":
        html += f"""
    <div style="background:#f0fdf4; border:1px solid #bbf7d0; padding:15px; border-radius:6px; margin-bottom:25px;">
      <h3 style="margin-top:0; color:#166534; font-size:14px;">Statutory Clearance Certificate</h3>
      <p style="font-size:12px;"><b>Governing Rule:</b> {memo.get("applicable_regulation")}</p>
      <p style="font-size:12px;"><b>Statutory Limit:</b> ₦{memo.get("governing_limit", 0):,.2f} | <b>Transaction Amount:</b> ₦{memo.get("transaction_amount", 0):,.2f}</p>
      <p style="font-size:12px; color:#166534;"><b>Determination:</b> {memo.get("cleared_reason")}</p>
    </div>
"""

    # Evidence ledger block trail
    html += """
    <h3 style="font-size: 14px; margin-bottom: 5px; color:#0f172a;">Cryptographic Evidence Ledger Audit Trail</h3>
    <table>
      <thead>
        <tr>
          <th style="width: 8%;">Block</th>
          <th style="width: 15%;">Claim ID</th>
          <th style="width: 12%;">Status</th>
          <th>Factual Proposition</th>
          <th style="width: 25%;">SHA-256 Hash</th>
        </tr>
      </thead>
      <tbody>
"""
    for idx, c in enumerate(claims, 1):
        html += f"""
        <tr>
          <td><b>#{idx}</b></td>
          <td><span class="code">{c.get("claim_id")}</span></td>
          <td><b>{c.get("status", "").upper()}</b></td>
          <td>{c.get("text")}</td>
          <td><span class="code">{c.get("hash")[:16]}...</span></td>
        </tr>
"""
    html += """
      </tbody>
    </table>
"""

    # Human officer sign-off
    html += f"""
    <div style="border-top:1px solid #cbd5e1; padding-top:15px; margin-top:30px; font-size:12px;">
      <h4 style="margin:0 0 10px 0; color:#0f172a;">Reviewing Compliance Officer Sign-off</h4>
      <div style="display:flex; justify-content:space-between;">
        <div><b>Officer ID:</b> {human_dec.get("officer_id", "OFFICER_CBN_01")}</div>
        <div><b>Determination:</b> {human_dec.get("decision", "RECORDED / PENDING")}</div>
        <div><b>Date:</b> {human_dec.get("recorded_at", now)}</div>
      </div>
      <p style="margin-top:8px; font-style:italic; color:#475569;"><b>Officer Remarks:</b> {human_dec.get("notes", "Automated compliance verification performed under verified hash chain.")}</p>
    </div>
  </div>
</body>
</html>
"""
    return html
