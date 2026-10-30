import os
import sqlite3
import time
from typing import Any, Dict, List, Optional
from tools.ast_guard import assert_safe_sql, UnsafeSQLError

DEFAULT_DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "regguard.db"))

class SQLiteTool:
    """
    Read-only SQLite query engine with AST validation.
    """
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database not found at {self.db_path}. Run scripts/seed_sqlite.py first.")
        # SQLite URI for strict read-only mode
        self.uri = f"file:{os.path.abspath(self.db_path)}?mode=ro"

    def execute_query(self, sql_query: str) -> Dict[str, Any]:
        """
        Validates the query via AST guard and executes in read-only SQLite mode.
        """
        # Step 1: AST validation gate
        assert_safe_sql(sql_query)

        start_time = time.perf_counter()
        
        # Connect using read-only URI
        conn = sqlite3.connect(self.uri, uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute(sql_query)
            rows = cursor.fetchall()
            execution_ms = round((time.perf_counter() - start_time) * 1000, 2)
            
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            formatted_rows = [list(row) for row in rows]
            
            return {
                "columns": columns,
                "rows": formatted_rows,
                "row_count": len(formatted_rows),
                "execution_time_ms": execution_ms,
                "ast_validated": True
            }
        finally:
            conn.close()

# Singleton helper
_default_tool = None

def query_transactions(sql_query: str) -> Dict[str, Any]:
    """Top-level tool function conforming to the tool contract."""
    global _default_tool
    if _default_tool is None:
        _default_tool = SQLiteTool()
    return _default_tool.execute_query(sql_query)
