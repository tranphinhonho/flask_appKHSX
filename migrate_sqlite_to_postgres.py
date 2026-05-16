"""
Migration Script: SQLite → PostgreSQL (Neon.tech)
Chạy 1 lần để chuyển toàn bộ dữ liệu từ database_new.db sang PostgreSQL.

Usage:
    python migrate_sqlite_to_postgres.py <DATABASE_URL>

Ví dụ:
    python migrate_sqlite_to_postgres.py "postgresql://neondb_owner:xxx@ep-xxx.aws.neon.tech/neondb?sslmode=require"
"""
import sqlite3
import psycopg2
import sys
import os

# SQLite type → PostgreSQL type mapping
TYPE_MAP = {
    'integer': 'INTEGER',
    'int': 'INTEGER',
    'real': 'DOUBLE PRECISION',
    'float': 'DOUBLE PRECISION',
    'text': 'TEXT',
    'varchar': 'TEXT',
    'blob': 'BYTEA',
    'numeric': 'NUMERIC',
    'boolean': 'BOOLEAN',
    'date': 'TEXT',
    'datetime': 'TEXT',
    '': 'TEXT',  # default
}


def get_pg_type(sqlite_type):
    """Convert SQLite type to PostgreSQL type"""
    st = sqlite_type.lower().strip() if sqlite_type else ''
    for key, val in TYPE_MAP.items():
        if key in st:
            return val
    return 'TEXT'


def migrate(sqlite_path, pg_url):
    """Migrate toàn bộ dữ liệu từ SQLite sang PostgreSQL"""
    # Kết nối SQLite
    print(f"🔗 Kết nối SQLite: {sqlite_path}")
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_cursor = sqlite_conn.cursor()

    # Kết nối PostgreSQL
    print(f"🔗 Kết nối PostgreSQL...")
    pg_conn = psycopg2.connect(pg_url)
    pg_cursor = pg_conn.cursor()

    # Lấy danh sách bảng
    sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [row[0] for row in sqlite_cursor.fetchall()]
    print(f"\n📋 Tìm thấy {len(tables)} bảng: {', '.join(tables)}")

    for table_name in tables:
        print(f"\n{'='*60}")
        print(f"📦 Đang xử lý bảng: {table_name}")

        # Lấy thông tin cột
        sqlite_cursor.execute(f'PRAGMA table_info([{table_name}])')
        columns_info = sqlite_cursor.fetchall()
        # columns_info: (cid, name, type, notnull, dflt_value, pk)

        # Tạo bảng PostgreSQL - dùng TEXT cho tất cả cột (trừ ID)
        # vì SQLite loose typing, cột INTEGER có thể chứa text
        col_defs = []
        col_names = []
        has_pk = False
        for col in columns_info:
            col_name = col[1]
            is_pk = col[5]

            col_names.append(col_name)

            # ID column thường là primary key autoincrement
            if is_pk and col_name.upper() == 'ID':
                col_defs.append(f'"{col_name}" SERIAL PRIMARY KEY')
                has_pk = True
            else:
                # Dùng TEXT cho tất cả cột khác để tránh type mismatch
                col_defs.append(f'"{col_name}" TEXT')

        # Drop bảng cũ nếu tồn tại
        pg_cursor.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')

        create_sql = f'CREATE TABLE "{table_name}" (\n  ' + ',\n  '.join(col_defs) + '\n)'
        print(f"  ✅ Tạo bảng với {len(col_defs)} cột")
        pg_cursor.execute(create_sql)
        pg_conn.commit()

        # Copy dữ liệu
        sqlite_cursor.execute(f'SELECT * FROM [{table_name}]')
        rows = sqlite_cursor.fetchall()
        print(f"  📊 Copy {len(rows)} bản ghi...")

        if rows:
            # Nếu có ID SERIAL, cần insert kèm ID và reset sequence sau
            placeholders = ', '.join(['%s'] * len(col_names))
            quoted_cols = ', '.join(f'"{c}"' for c in col_names)
            insert_sql = f'INSERT INTO "{table_name}" ({quoted_cols}) VALUES ({placeholders})'

            batch_size = 500
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i + batch_size]
                # Convert None/NaN values and ensure strings for TEXT columns
                clean_batch = []
                for row in batch:
                    clean_row = []
                    for idx, val in enumerate(row):
                        if val is None:
                            clean_row.append(None)
                        elif isinstance(val, float) and (val != val):  # NaN check
                            clean_row.append(None)
                        elif idx == 0 and has_pk and col_names[0].upper() == 'ID':
                            # ID column: keep as integer
                            clean_row.append(int(val) if val is not None else None)
                        else:
                            # All other columns are TEXT
                            clean_row.append(str(val))
                    clean_batch.append(tuple(clean_row))
                pg_cursor.executemany(insert_sql, clean_batch)

            pg_conn.commit()

            # Reset sequence cho ID SERIAL
            if has_pk:
                try:
                    pg_cursor.execute(f'SELECT MAX("ID") FROM "{table_name}"')
                    max_id = pg_cursor.fetchone()[0]
                    if max_id:
                        seq_name = f'{table_name}_ID_seq'
                        pg_cursor.execute(f"SELECT setval('\"{seq_name}\"', {max_id})")
                        pg_conn.commit()
                        print(f"  🔄 Reset sequence tới {max_id}")
                except Exception as e:
                    print(f"  ⚠️ Không thể reset sequence: {e}")
                    pg_conn.rollback()

        print(f"  ✅ Hoàn tất bảng {table_name}")

    # Tổng kết
    print(f"\n{'='*60}")
    print(f"🎉 Migration hoàn tất! Đã chuyển {len(tables)} bảng sang PostgreSQL.")

    sqlite_conn.close()
    pg_cursor.close()
    pg_conn.close()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python migrate_sqlite_to_postgres.py <DATABASE_URL>")
        print('Example: python migrate_sqlite_to_postgres.py "postgresql://user:pass@host/db?sslmode=require"')
        sys.exit(1)

    pg_url = sys.argv[1]

    # Tìm database SQLite
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    sqlite_path = os.path.join(project_dir, 'database_new.db')

    if not os.path.exists(sqlite_path):
        print(f"❌ Không tìm thấy SQLite database: {sqlite_path}")
        sys.exit(1)

    print("🚀 Bắt đầu migration SQLite → PostgreSQL")
    print(f"   SQLite: {sqlite_path}")
    print(f"   PostgreSQL: {pg_url[:50]}...")

    migrate(sqlite_path, pg_url)
