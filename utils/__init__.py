"""
Utils package - Hỗ trợ cả SQLite và PostgreSQL
"""
import sqlite3


def get_db_connection(db_path: str):
    """
    Tạo database connection - tự detect SQLite hoặc PostgreSQL.
    Trả về connection object tương thích.
    
    Args:
        db_path: Đường dẫn SQLite hoặc PostgreSQL URL
    
    Returns:
        Connection object (sqlite3 hoặc psycopg2)
    """
    if db_path and db_path.startswith(('postgresql://', 'postgres://')):
        import psycopg2
        conn = psycopg2.connect(db_path)
        conn.autocommit = False
        return conn
    else:
        conn = sqlite3.connect(db_path)
        return conn


def is_postgres(db_path: str) -> bool:
    """Check if db_path is a PostgreSQL URL"""
    return bool(db_path and db_path.startswith(('postgresql://', 'postgres://')))


def q(name: str, db_path: str) -> str:
    """Quote column/table name - bracket for SQLite, double-quote for PostgreSQL"""
    name = name.strip('[]').strip('"')
    if is_postgres(db_path):
        return f'"{name}"'
    else:
        return f'[{name}]'


def ph(db_path: str) -> str:
    """Placeholder - ? for SQLite, %s for PostgreSQL"""
    if is_postgres(db_path):
        return '%s'
    else:
        return '?'


def adapt_create_sql(sql: str, db_path: str) -> str:
    """
    Adapt CREATE TABLE SQL from SQLite syntax to PostgreSQL syntax.
    - INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL PRIMARY KEY
    - [column_name] → "column_name"
    - DATETIME → TIMESTAMP
    - Quote table name to preserve case
    """
    if not is_postgres(db_path):
        return sql
    import re
    # AUTOINCREMENT → SERIAL
    result = re.sub(
        r'ID\s+INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT',
        '"ID" SERIAL PRIMARY KEY',
        sql,
        flags=re.IGNORECASE
    )
    # Quote table name: CREATE TABLE IF NOT EXISTS TableName → CREATE TABLE IF NOT EXISTS "TableName"
    result = re.sub(
        r'CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)',
        lambda m: f'CREATE TABLE IF NOT EXISTS "{m.group(1)}"',
        result,
        flags=re.IGNORECASE
    )
    # [col] → "col"
    result = re.sub(r'\[([^\]]+)\]', r'"\1"', result)
    # DATETIME → TIMESTAMP
    result = re.sub(r'\bDATETIME\b', 'TIMESTAMP', result, flags=re.IGNORECASE)
    return result

