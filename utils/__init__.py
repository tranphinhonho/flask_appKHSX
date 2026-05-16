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
