from typing import List, Optional, Set, Tuple
import sqlglot
from sqlglot import exp

ALLOWED_TABLES: Set[str] = {"transactions", "customers", "accounts"}

DISALLOWED_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.Command,
    exp.Create,
    exp.Pragma,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
)

class UnsafeSQLError(ValueError):
    """Raised when an SQL query fails AST security validation."""
    pass

def validate_sql_query(query: str, allowed_tables: Optional[Set[str]] = None) -> Tuple[bool, str]:
    """
    Validates that a SQL query:
      1. Is a single, valid SELECT statement.
      2. Contains no DML/DDL or mutation AST nodes.
      3. Touches only tables in the whitelist.
    
    Returns (True, "OK") or (False, reason).
    """
    tables_whitelist = allowed_tables or ALLOWED_TABLES
    cleaned = query.strip()
    
    if not cleaned:
        return False, "Query string is empty."
    
    # Reject semicolon chaining of multiple statements
    statements = [s for s in cleaned.split(";") if s.strip()]
    if len(statements) > 1:
        return False, "Multiple SQL statements separated by semicolons are strictly prohibited."
    
    try:
        parsed = sqlglot.parse_one(statements[0], read="sqlite")
    except Exception as e:
        return False, f"SQL syntax parsing error: {str(e)}"
    
    # 1. Root must be Select
    if not isinstance(parsed, exp.Select):
        return False, f"Forbidden statement type: Root AST expression must be SELECT, got {parsed.key.upper()}."
    
    # 2. Check for any disallowed nodes anywhere in the tree
    for node in parsed.walk():
        if isinstance(node, DISALLOWED_NODES):
            return False, f"Prohibited operation detected in AST: {node.key.upper()} is not permitted."
    
    # 3. Check table whitelist
    tables_in_query = set()
    for table_expr in parsed.find_all(exp.Table):
        table_name = table_expr.name.lower()
        if table_name:
            tables_in_query.add(table_name)
    
    disallowed_tables = tables_in_query - tables_whitelist
    if disallowed_tables:
        return False, f"Access denied to table(s): {sorted(list(disallowed_tables))}. Allowed tables: {sorted(list(tables_whitelist))}."
    
    return True, "OK"

def assert_safe_sql(query: str, allowed_tables: Optional[Set[str]] = None) -> None:
    """Convenience wrapper that raises UnsafeSQLError on validation failure."""
    is_valid, reason = validate_sql_query(query, allowed_tables)
    if not is_valid:
        raise UnsafeSQLError(f"SQL AST Security Gate: {reason}")
