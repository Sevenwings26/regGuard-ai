import os
import sys

# Ensure repository root is in sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tools.ast_guard import validate_sql_query, assert_safe_sql, UnsafeSQLError
from tools.sql_tool import query_transactions
from tools.watchlist_tool import watchlist_lookup
from tools.threshold_tool import calculate_threshold
from tools.qdrant_hybrid import regulation_search

def test_ast_guard_security():
    print("\n--- 1. Testing SQLglot AST Guard Security ---")
    
    # Valid queries
    valid_q1 = "SELECT * FROM transactions WHERE amount > 1000000;"
    valid_q2 = """
        SELECT t.transaction_id, t.amount, c.full_name, c.dob
        FROM transactions t
        JOIN accounts a ON t.account_id = a.account_id
        JOIN customers c ON a.customer_id = c.customer_id
        WHERE c.customer_id = 'CUST-IND-9021'
    """
    assert validate_sql_query(valid_q1)[0], "Valid SELECT query was incorrectly rejected"
    assert validate_sql_query(valid_q2)[0], "Valid multi-table JOIN query was incorrectly rejected"
    print("  ✓ Allowed valid SELECT and multi-table JOINs")

    # Prohibited queries
    disallowed_queries = [
        ("DROP TABLE transactions;", "DROP statement"),
        ("UPDATE customers SET risk_rating = 'LOW';", "UPDATE statement"),
        ("DELETE FROM accounts WHERE account_id = '1';", "DELETE statement"),
        ("INSERT INTO accounts VALUES ('1','2','3','SAVINGS','NGN',0,'ACTIVE','2020');", "INSERT statement"),
        ("SELECT * FROM transactions; DROP TABLE customers;", "Semicolon statement chaining"),
        ("SELECT * FROM sqlite_master;", "Non-whitelisted table sqlite_master"),
        ("SELECT * FROM users;", "Non-whitelisted table users"),
        ("PRAGMA table_info(transactions);", "PRAGMA statement"),
    ]

    for q, label in disallowed_queries:
        is_valid, reason = validate_sql_query(q)
        assert not is_valid, f"Security Breach! AST guard failed to block {label}: {q}"
        try:
            assert_safe_sql(q)
            assert False, f"Expected UnsafeSQLError for {label}"
        except UnsafeSQLError:
            pass
        print(f"  ✓ Blocked {label}: {reason[:60]}...")

def test_sqlite_read_only_execution():
    print("\n--- 2. Testing Read-Only SQLite Tool ---")
    # Query Case A account transactions
    query = """
        SELECT transaction_id, amount, channel, timestamp
        FROM transactions
        WHERE account_id = 'ACC-IND-9021'
        ORDER BY timestamp ASC;
    """
    result = query_transactions(query)
    assert result["ast_validated"] is True
    assert result["row_count"] == 3
    assert len(result["rows"]) == 3
    total_amount = sum(row[1] for row in result["rows"])
    assert total_amount == 5500000.0
    print(f"  ✓ Successfully executed read-only query. Retrieved 3 transactions totaling N{total_amount:,.2f} in {result['execution_time_ms']}ms.")

def test_watchlist_fuzzy_lookup():
    print("\n--- 3. Testing Watchlist Tool (Fuzzy Search & DOB Corroboration) ---")
    
    # Case B scenario: Name matches Musa Ibrahim, but customer KYC DOB is 1994 vs watchlist 1961
    res_b = watchlist_lookup(name="Musa Ibrahim", dob="1994-08-12")
    assert res_b["match_found"] is True
    assert res_b["best_match"]["name_similarity_score"] >= 0.85
    assert res_b["best_match"]["category"] == "PEP"
    assert res_b["best_match"]["dob_match_status"] == "MISMATCH"
    print(f"  ✓ Case B Match: {res_b['best_match']['matched_name']} ({res_b['best_match']['category']}) - Similarity: {res_b['best_match']['name_similarity_score']} - DOB Status: {res_b['best_match']['dob_match_status']}")

    # Exact match scenario
    res_exact = watchlist_lookup(name="Chief Kingsley Okoye", dob="1958-09-14")
    assert res_exact["match_found"] is True
    assert res_exact["best_match"]["dob_match_status"] == "EXACT"
    print(f"  ✓ Exact Match: {res_exact['best_match']['matched_name']} - DOB Status: {res_exact['best_match']['dob_match_status']}")

    # Non-match scenario
    res_none = watchlist_lookup(name="Unknown Random Person XYZ")
    assert res_none["match_found"] is False
    print(f"  ✓ Non-Match: Correctly identified no watchlist hit (highest similarity: {res_none['highest_similarity_score']})")

def test_threshold_calculation():
    print("\n--- 4. Testing Threshold & Structuring Calculation ---")
    
    # Case A: 3 structured cash deposits totaling 5.5M within 36 hours for Individual
    amounts_a = [1900000.0, 1750000.0, 1850000.0]
    timestamps_a = ["2023-01-01 10:15:00", "2023-01-01 16:30:00", "2023-01-02 11:45:00"]
    res_a = calculate_threshold(amounts=amounts_a, timestamps=timestamps_a, entity_type="INDIVIDUAL")
    assert res_a["aggregate_amount"] == 5500000.0
    assert res_a["threshold_breached"] is True
    assert res_a["structuring_indicator"] is True
    assert res_a["time_window_hours"] < 36.0
    print(f"  ✓ Case A Structuring Detected: Aggregate N{res_a['aggregate_amount']:,.2f} > Statutory N{res_a['statutory_threshold']:,.2f} over {res_a['time_window_hours']}h (Structuring: {res_a['structuring_indicator']})")

    # Case C: Single 7.5M deposit for Corporate under 2013 limit of 10M
    res_c = calculate_threshold(amounts=[7500000.0], timestamps=["2021-08-14 11:20:00"], entity_type="CORPORATE")
    assert res_c["aggregate_amount"] == 7500000.0
    assert res_c["threshold_breached"] is False
    assert res_c["structuring_indicator"] is False
    print(f"  ✓ Case C Corporate Cash: N{res_c['aggregate_amount']:,.2f} <= Statutory N{res_c['statutory_threshold']:,.2f} (Breached: {res_c['threshold_breached']})")

def test_qdrant_hybrid_search():
    print("\n--- 5. Testing Qdrant Local Hybrid RRF Retrieval ---")
    
    # General structuring query
    results_structuring = regulation_search("multiple structured cash deposits smurfing below threshold", top_k=2)
    assert len(results_structuring) > 0
    top_clause = results_structuring[0]
    assert "10" in top_clause["clause_id"] or "structuring" in top_clause["text"].lower()
    print(f"  ✓ Hybrid Query Match: [{top_clause['clause_id']}] {top_clause['section_title']} (RRF score: {top_clause['rrf_score']})")

    # Temporal filter query for Case C: transaction date 2021-08-14
    results_temporal = regulation_search(
        query="corporate cash deposit limit",
        effective_before="2021-08-14",
        top_k=2
    )
    assert len(results_temporal) > 0
    for r in results_temporal:
        assert r["effective_date"] <= "2021-08-14", f"Temporal filter failed! Got future clause {r['clause_id']} with date {r['effective_date']}"
    print(f"  ✓ Temporal Filtering: Returned {len(results_temporal)} clauses in force prior to 2021-08-14 (Top: [{results_temporal[0]['clause_id']}] {results_temporal[0]['section_title']})")

if __name__ == "__main__":
    print("=======================================================")
    print(" RegGuard AI — Day 2 Tool & Data Layer Test Suite")
    print("=======================================================")
    test_ast_guard_security()
    test_sqlite_read_only_execution()
    test_watchlist_fuzzy_lookup()
    test_threshold_calculation()
    test_qdrant_hybrid_search()
    print("\n=======================================================")
    print(" ✓ ALL DAY 2 TEST SUITE CHECKS PASSED (100%)")
    print("=======================================================\n")
