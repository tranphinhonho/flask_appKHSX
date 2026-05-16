"""
Database Layer - Dual mode: SQLite (local) / PostgreSQL (production)
Port từ admin/sys_sqlite.py, bỏ phụ thuộc Streamlit
"""
import os
import re
import pandas as pd
import numpy as np
from datetime import datetime

# Detect database mode
_database_url = None
_db_type = None  # 'sqlite' or 'postgres'


def _translate_sql(sql):
    """
    Tự động chuyển SQL từ SQLite syntax sang PostgreSQL syntax.
    - [column_name] → "column_name"
    - ? → %s
    - [Đã xóa] = 0/1 → "Đã xóa" = '0'/'1' (vì cột này là TEXT trên PostgreSQL)
    - DaXoa = 0/1 → "DaXoa" = '0'/'1'
    - strftime('%d', col) → EXTRACT(DAY FROM col)
    - datetime('now') → NOW()
    Giúp route files không cần thay đổi!
    """
    if _db_type != 'postgres':
        return sql

    # Thay [tên cột] → "tên cột"
    result = re.sub(r'\[([^\]]+)\]', r'"\1"', sql)

    # Auto-quote tên bảng CamelCase (PostgreSQL lowercase unquoted identifiers)
    _TABLES = [
        'StockOld', 'StockHomNay', 'SanPham', 'DatHang', 'DonViTinh',
        'EmailImportLog', 'MasterdataLoss', 'PackingPlan', 'BagStock',
        'BaoBi', 'Packing', 'Pellet', 'PelletCapacity', 'Plan', 'Sale',
        'TestCan_Reports', 'Testcan', 'Mixer', 'Forecast',
        'PelletPlan', 'Batching',
        'tbsys_ChucNangChinh', 'tbsys_ChucNangTheoVaiTro',
        'tbsys_DanhSachChucNang', 'tbsys_LichSuBackupDatabase',
        'tbsys_Logs', 'tbsys_ModuleChucNang', 'tbsys_Users',
        'tbsys_VaiTro', 'tbsys_config', 'TonBon',
    ]
    for tbl in _TABLES:
        # Replace unquoted table name with quoted version
        # Match table name NOT already inside double quotes
        result = re.sub(
            r'(?<!")(?<!\w)\b' + re.escape(tbl) + r'\b(?!")',
            f'"{tbl}"',
            result
        )

    # Auto-quote CamelCase column names (BagStock table uses CamelCase without brackets)
    _COLUMNS = [
        'NgayStock', 'TenCam', 'KichCoDongBao', 'SoLuongBaoBi',
        'TenFile', 'NguoiTao', 'ThoiGianTao', 'DaXoa',
        'TenFile', 'NgayEmail', 'LoaiFile', 'SoLuongDong',
        'ThoiGianImport', 'NguoiImport',
    ]
    for col in _COLUMNS:
        result = re.sub(
            r'(?<!")(?<!\w)(?<!\.)' + re.escape(col) + r'(?!")',
            f'"{col}"',
            result
        )

    # Fix ID → "ID" (PostgreSQL lowercases unquoted identifiers)
    # Handles both standalone SELECT ID and sp.ID patterns
    result = re.sub(r'(?<!")\bID\b(?!")', '"ID"', result)

    # Thay ? → %s
    result = result.replace('?', '%s')

    # Fix TEXT column "Đã xóa" comparison with integer
    # "Đã xóa" = 0 → "Đã xóa" = '0'  and  "Đã xóa" = 1 → "Đã xóa" = '1'
    result = re.sub(r'"Đã xóa"\s*=\s*0\b', '"Đã xóa" = \'0\'', result)
    result = re.sub(r'"Đã xóa"\s*=\s*1\b', '"Đã xóa" = \'1\'', result)
    
    # Fix DaXoa = 0/1 (used in BagStock table - already quoted by _COLUMNS above)
    result = re.sub(r'"DaXoa"\s*=\s*0\b', '"DaXoa" = \'0\'', result)
    result = re.sub(r'"DaXoa"\s*=\s*1\b', '"DaXoa" = \'1\'', result)

    # Fix VALUES (..., 0) at end of INSERT for Đã xóa column
    # Pattern: , 0) at the end of VALUES clause
    result = re.sub(r',\s*0\s*\)\s*$', ", '0')", result, flags=re.MULTILINE)

    # Fix JOIN type mismatch: TEXT FK columns compared with INTEGER PK "ID"
    # Pattern 1: alias."ID sản phẩm" = alias."ID" → CAST(alias."ID sản phẩm" AS INTEGER) = alias."ID"
    # Pattern 2: alias."ID" = alias."ID sản phẩm" → alias."ID" = CAST(alias."ID sản phẩm" AS INTEGER)
    # Handles FK columns like "ID sản phẩm", "ID Vai trò", "ID Chức năng chính" etc.
    # FK columns have "ID " (with space) followed by more text; PK is just "ID"
    result = re.sub(
        r'(\w+\."ID\s[^"]+")\s*=\s*(\w+\."ID")',
        r'CAST(\1 AS INTEGER) = \2',
        result
    )
    result = re.sub(
        r'(\w+\."ID")\s*=\s*(\w+\."ID\s[^"]+")',
        r'\1 = CAST(\2 AS INTEGER)',
        result
    )

    # Fix aggregate functions on TEXT columns - add ::numeric cast
    # SUM("column") → SUM("column"::numeric)
    # AVG("column") → AVG("column"::numeric)
    # Only for SUM and AVG which require numeric input
    # MIN/MAX work on TEXT (lexicographic comparison) so don't cast them
    result = re.sub(
        r'\b(SUM|AVG)\("([^"]+)"\)',
        r'\1("\2"::numeric)',
        result
    )

    # Fix strftime for PostgreSQL
    result = re.sub(
        r"strftime\('%d',\s*\"([^\"]+)\"\)",
        r"EXTRACT(DAY FROM \"\1\")::TEXT",
        result
    )
    result = re.sub(
        r"strftime\('%Y',\s*\"([^\"]+)\"\)",
        r"EXTRACT(YEAR FROM \"\1\")::TEXT",
        result
    )
    result = re.sub(
        r"strftime\('%m',\s*\"([^\"]+)\"\)",
        r"LPAD(EXTRACT(MONTH FROM \"\1\")::TEXT, 2, '0')",
        result
    )
    
    # Fix datetime('now') → NOW()
    result = result.replace("datetime('now')", "NOW()")

    return result


class _PgRow:
    """Wrap PostgreSQL row to support both index-based (row[0]) and key-based (row['col']) access.
    Also supports dict(row) like sqlite3.Row."""
    def __init__(self, values, columns):
        self._values = values
        self._columns = columns
        self._col_map = {col: i for i, col in enumerate(columns)}

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        elif isinstance(key, str):
            return self._values[self._col_map[key]]
        raise KeyError(key)

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def keys(self):
        return self._columns


class _PgCursorWrapper:
    """Wrapper cursor cho PostgreSQL - tự động translate SQL, trả về _PgRow"""
    def __init__(self, cursor):
        self._cursor = cursor
        self._columns = None

    def execute(self, sql, params=None):
        sql = _translate_sql(sql)
        if params:
            # Escape bare % in column names (e.g. "Loss (%)") for psycopg2
            # Only needed when params are present (psycopg2 uses % formatting)
            sql = re.sub(r'%(?!s)', '%%', sql)
            self._cursor.execute(sql, params)
        else:
            self._cursor.execute(sql)
        # Cache column names after execute
        if self._cursor.description:
            self._columns = [desc[0] for desc in self._cursor.description]

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return _PgRow(row, self._columns)

    def fetchall(self):
        rows = self._cursor.fetchall()
        return [_PgRow(row, self._columns) for row in rows]

    @property
    def description(self):
        return self._cursor.description

    @property
    def lastrowid(self):
        return getattr(self._cursor, 'lastrowid', None)

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def close(self):
        self._cursor.close()


class _PgConnectionWrapper:
    """Wrapper connection cho PostgreSQL - cursor() trả về auto-translate cursor"""
    def __init__(self, conn):
        self._conn = conn

    def cursor(self, **kwargs):
        # kwargs (like cursor_factory) are ignored - we use _PgCursorWrapper instead
        real_cursor = self._conn.cursor()
        return _PgCursorWrapper(real_cursor)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    @property
    def row_factory(self):
        return None

    @row_factory.setter
    def row_factory(self, value):
        pass  # ignore for postgres


def init_db(database_path_or_url):
    """Khởi tạo database - tự detect SQLite hoặc PostgreSQL"""
    global _database_url, _db_type
    _database_url = database_path_or_url

    if database_path_or_url and database_path_or_url.startswith(('postgresql://', 'postgres://')):
        _db_type = 'postgres'
    else:
        _db_type = 'sqlite'


def connect_db():
    """Kết nối database - tự chọn driver theo mode.
    Cho PostgreSQL, trả về wrapper tự động translate SQL."""
    if _database_url is None:
        raise RuntimeError("Database chưa được khởi tạo. Gọi init_db() trước.")
    try:
        if _db_type == 'postgres':
            import psycopg2
            conn = psycopg2.connect(_database_url)
            conn.autocommit = False
            return _PgConnectionWrapper(conn)
        else:
            import sqlite3
            conn = sqlite3.connect(_database_url, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            return conn
    except Exception as e:
        raise ConnectionError(f"Không thể kết nối database: {e}")


def _make_cursor(conn):
    """Tạo cursor phù hợp với loại database"""
    if _db_type == 'postgres':
        import psycopg2.extras
        return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        return conn.cursor()


def _q(name):
    """Quote tên cột/bảng - bracket cho SQLite, double-quote cho PostgreSQL"""
    name = name.strip('[]').strip('"')
    if _db_type == 'postgres':
        return f'"{name}"'
    else:
        return f'[{name}]'


def _ph(index=None):
    """Placeholder cho parameterized query - ? cho SQLite, %s cho PostgreSQL"""
    if _db_type == 'postgres':
        return '%s'
    else:
        return '?'


def _row_to_dict(row):
    """Convert row to dict tùy theo loại database"""
    if _db_type == 'postgres':
        return dict(row) if row else {}
    else:
        return dict(row) if row else {}


def _get_table_columns_info(cursor, table_name):
    """Lấy thông tin cột - hỗ trợ cả SQLite và PostgreSQL"""
    if _db_type == 'postgres':
        cursor.execute(
            """SELECT column_name, data_type 
               FROM information_schema.columns 
               WHERE table_name = %s 
               ORDER BY ordinal_position""",
            (table_name.strip('[]').strip('"'),)
        )
        rows = cursor.fetchall()
        return {row[0]: row[1] for row in rows}
    else:
        cursor.execute(f"PRAGMA table_info([{table_name}])")
        return {row[1]: row[2].lower() for row in cursor.fetchall()}


def _get_column_names(cursor, table_name):
    """Lấy danh sách tên cột"""
    if _db_type == 'postgres':
        cursor.execute(
            """SELECT column_name 
               FROM information_schema.columns 
               WHERE table_name = %s 
               ORDER BY ordinal_position""",
            (table_name.strip('[]').strip('"'),)
        )
        rows = cursor.fetchall()
        if rows and isinstance(rows[0], dict):
            return [row['column_name'] for row in rows]
        else:
            return [row[0] for row in rows]
    else:
        cursor.execute(f"PRAGMA table_info([{table_name}])")
        return [row[1] for row in cursor.fetchall()]


def _has_column(cursor, table_name, column_name):
    """Kiểm tra bảng có cột hay không"""
    cols = _get_column_names(cursor, table_name)
    return column_name in cols


def query_database(sql_string, data_type=None, delimiter=' | ', params=None):
    """
    Thực thi truy vấn SQL.
    data_type: 'dataframe', 'list', 'value', hoặc None (INSERT/UPDATE/DELETE)
    """
    conn = None
    cursor = None
    try:
        conn = connect_db()
        cursor = _make_cursor(conn)

        # Auto-translate SQL for PostgreSQL
        translated = _translate_sql(sql_string)

        if params:
            # Escape bare % for psycopg2 when params present
            if _db_type == 'postgres':
                translated = re.sub(r'%(?!s)', '%%', translated)
            cursor.execute(translated, params)
        else:
            cursor.execute(translated)

        if data_type is not None:
            columns = [desc[0] for desc in cursor.description] if cursor.description else []

            if data_type == 'dataframe':
                rows = cursor.fetchall()
                if _db_type == 'postgres':
                    return pd.DataFrame([dict(row) for row in rows])
                else:
                    return pd.DataFrame([dict(row) for row in rows])
            elif data_type == 'list':
                rows = cursor.fetchall()
                if _db_type == 'postgres':
                    return [delimiter.join(str(row[col]) for col in columns) for row in rows]
                else:
                    return [delimiter.join(str(row[col]) for col in columns) for row in rows]
            elif data_type == 'value':
                result = cursor.fetchone()
                if result is None:
                    return None
                if _db_type == 'postgres':
                    if isinstance(result, dict):
                        return list(result.values())[0]
                    return result[0]
                else:
                    return result[0] if result is not None else None
        else:
            conn.commit()
            return "Đã xử lý thành công!"
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def sql(query):
    """
    Public helper: translate SQL from SQLite syntax to match current DB.
    Route files viết SQL bằng SQLite syntax ([column], ?) rồi gọi db.sql(query)
    để auto-convert cho PostgreSQL.
    
    Usage: cursor.execute(db.sql(query), params)
    """
    return _translate_sql(query)


def adapt_params(params):
    """
    Ensure params is a tuple (required for psycopg2).
    """
    if params is None:
        return ()
    if isinstance(params, list):
        return tuple(params)
    return params


def get_table_columns(table_name):
    """Lấy danh sách tất cả các cột của một bảng"""
    conn = connect_db()
    cursor = conn.cursor()
    columns = _get_column_names(cursor, table_name)
    cursor.close()
    conn.close()
    return columns


def _quote_sql_value(value, sql_type):
    """Helper: quote giá trị SQL theo kiểu dữ liệu"""
    if value is None:
        return "NULL"
    numeric_types = ['integer', 'real', 'numeric', 'bigint', 'smallint',
                     'double precision', 'decimal', 'int', 'float']
    if sql_type in numeric_types:
        return str(value)
    safe_value = str(value).replace("'", "''")
    return f"'{safe_value}'"


def get_columns_data(table_name, columns=None, delimiter=" | ", data_type="dataframe",
                     col_where=None, col_order=None, group_by=None, date_columns=None,
                     joins=None, distinct=False, custom_columns=None, output_columns=None,
                     page_number=None, rows_per_page=None, search_value=None, search_columns=None):
    """
    Lấy dữ liệu từ bảng với nhiều tùy chọn lọc và sắp xếp.
    Hỗ trợ cả SQLite và PostgreSQL.
    """
    conn = connect_db()
    cursor = conn.cursor()

    if col_order is None:
        col_order = {}
    if group_by is None:
        group_by = []
    if custom_columns is None:
        custom_columns = []

    # Lấy kiểu dữ liệu các cột
    column_types = _get_table_columns_info(cursor, table_name)

    # Xây dựng danh sách cột
    working_columns = list(columns) if columns is not None else []
    selected_columns = []

    if not working_columns:
        all_table_columns = _get_column_names(cursor, table_name)
        if not all_table_columns:
            selected_columns.append(f"{_q(table_name)}.*")
        else:
            selected_columns += [f"{_q(table_name)}.{_q(col)} AS {_q(col)}" for col in all_table_columns]
    else:
        selected_columns += [f"{_q(table_name)}.{_q(col)} AS {_q(col)}" for col in working_columns]

    # Custom columns
    for cc in custom_columns:
        name = cc.get("name")
        expr = cc.get("expression")
        if name and expr:
            selected_columns.append(f"({expr}) AS {_q(name)}")

    # JOINs
    join_statements = []
    if joins:
        for join in joins:
            from_table = join.get("from_table", table_name)
            join_table = join.get("table")
            join_alias = join.get("alias", join_table)
            join_on = join.get("on")
            join_columns = join.get("columns", [])

            selected_columns += [f"{_q(join_alias)}.{_q(col)} AS {_q(join_alias + '_' + col)}" for col in join_columns]

            on_conditions = " AND ".join(
                f"{_q(from_table)}.{_q(key)} = {_q(join_alias)}.{_q(value)}" for key, value in join_on.items()
            )

            join_where = join.get("join_where")
            if join_where and isinstance(join_where, dict):
                for col, cond in join_where.items():
                    if isinstance(cond, tuple) and len(cond) == 2:
                        operator, value = cond
                        ct = column_types.get(col, "text")
                        on_conditions += f" AND {_q(from_table)}.{_q(col)} {operator} {_quote_sql_value(value, ct)}"

            join_statements.append(f"LEFT JOIN {_q(join_table)} AS {_q(join_alias)} ON {on_conditions}")

    # Build query
    distinct_clause = "DISTINCT" if distinct else ""
    query = f"SELECT {distinct_clause} {', '.join(selected_columns)} FROM {_q(table_name)}"

    if join_statements:
        query += " " + " ".join(join_statements)

    # WHERE
    where_clauses = []
    if col_where:
        for column, condition in col_where.items():
            if '.' in column:
                parts = column.rsplit('.', 1)
                table_prefix, column_name = parts[0], parts[1]
            else:
                table_prefix, column_name = table_name, column

            column_name = column_name.strip('[]').strip('"')
            ct = column_types.get(column_name, "text")

            if isinstance(condition, dict) and 'Between' in condition:
                bv = condition['Between']
                if len(bv) == 2:
                    where_clauses.append(
                        f"{_q(table_prefix)}.{_q(column_name)} BETWEEN {_quote_sql_value(bv[0], ct)} AND {_quote_sql_value(bv[1], ct)}"
                    )
            elif isinstance(condition, list) or (isinstance(condition, tuple) and condition[0] in ["IN", "NOT IN"]):
                operator, values = ("IN", condition) if isinstance(condition, list) else condition
                if values:
                    vals = ", ".join(_quote_sql_value(v, ct) for v in values)
                    where_clauses.append(f"{_q(table_prefix)}.{_q(column_name)} {operator} ({vals})")
            elif isinstance(condition, tuple) and len(condition) == 2:
                operator, value = condition
                where_clauses.append(f"{_q(table_prefix)}.{_q(column_name)} {operator} {_quote_sql_value(value, ct)}")
            elif isinstance(condition, str) and condition.strip().upper() in ['IS NULL', 'IS NOT NULL']:
                where_clauses.append(f"{_q(table_prefix)}.{_q(column_name)} {condition}")
            else:
                where_clauses.append(f"{_q(table_prefix)}.{_q(column_name)} = {_quote_sql_value(condition, ct)}")

    # Search
    if search_value and search_columns:
        search_conditions = []
        safe_val = str(search_value).replace("'", "''")
        for col in search_columns:
            tp = col.split('.')[0] if '.' in col else table_name
            cn = col.split('.')[-1]
            search_conditions.append(f"CAST({_q(tp)}.{_q(cn)} AS TEXT) LIKE '%{safe_val}%'")
        if search_conditions:
            where_clauses.append(f"({' OR '.join(search_conditions)})")

    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    # GROUP BY
    if group_by:
        query += " GROUP BY " + ", ".join(f"{_q(col)}" for col in group_by)

    # ORDER BY
    if col_order:
        order_parts = [f"{_q(col)} {order}" for col, order in col_order.items()]
        query += " ORDER BY " + ", ".join(order_parts)

    # PAGINATION
    if page_number is not None and rows_per_page is not None:
        offset = (page_number - 1) * rows_per_page
        query += f" LIMIT {rows_per_page} OFFSET {offset}"

    # Execute
    cursor.execute(query)
    rows = cursor.fetchall()
    if _db_type == 'postgres':
        cols_from_db = [desc[0] for desc in cursor.description]
        df = pd.DataFrame([dict(row) for row in rows], columns=cols_from_db)
    else:
        cols_from_db = [desc[0] for desc in cursor.description]
        df = pd.DataFrame([dict(row) for row in rows], columns=cols_from_db)

    # Date columns
    if date_columns:
        for col in date_columns:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce').dt.date

    # Reorder
    if not output_columns and columns:
        ordered = list(columns) if columns else []
        if custom_columns:
            for cc in custom_columns:
                if 'name' in cc:
                    ordered.append(cc['name'])
        available = [c for c in ordered if c in df.columns]
        remaining = [c for c in df.columns if c not in available]
        df = df[available + remaining]

    conn.close()

    # Return type
    if data_type == "dataframe":
        if output_columns:
            df = df[[c for c in output_columns if c in df.columns]]
        return df
    elif data_type == "list":
        df_proc = df[[c for c in output_columns if c in df.columns]] if output_columns else df
        rows_list = df_proc.values.tolist()
        return [delimiter.join("None" if item is None else str(item) for item in row) for row in rows_list]
    elif data_type == "dictionary":
        dict_cols = output_columns if output_columns else columns
        if dict_cols and len(dict_cols) == 2:
            key_col, val_col = dict_cols[0], dict_cols[1]
        else:
            cols_list = df.columns.tolist()
            key_col, val_col = cols_list[0], cols_list[1]
        return pd.Series(df[val_col].values, index=df[key_col]).to_dict()
    elif data_type == "value":
        if len(df) > 0:
            return df.iloc[0, 0]
        return None
    else:
        return df


def get_total_count(table_name, col_where=None, search_value=None, search_columns=None):
    """Đếm tổng số bản ghi"""
    conn = connect_db()
    cursor = conn.cursor()

    column_types = _get_table_columns_info(cursor, table_name)

    query = f"SELECT COUNT(*) FROM {_q(table_name)}"

    where_clauses = []
    if col_where:
        for column, condition in col_where.items():
            table_prefix, column_name = table_name, column
            column_name = column_name.strip('[]').strip('"')
            ct = column_types.get(column_name, "text")

            if isinstance(condition, tuple) and len(condition) == 2:
                operator, value = condition
                where_clauses.append(f"{_q(table_prefix)}.{_q(column_name)} {operator} {_quote_sql_value(value, ct)}")
            else:
                where_clauses.append(f"{_q(table_prefix)}.{_q(column_name)} = {_quote_sql_value(condition, ct)}")

    if search_value and search_columns:
        search_conditions = []
        safe_val = str(search_value).replace("'", "''")
        for col in search_columns:
            search_conditions.append(f"CAST({_q(col)} AS TEXT) LIKE '%{safe_val}%'")
        if search_conditions:
            where_clauses.append(f"({' OR '.join(search_conditions)})")

    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    try:
        cursor.execute(query)
        result = cursor.fetchone()
        conn.close()
        if _db_type == 'postgres' and isinstance(result, dict):
            total = list(result.values())[0]
        else:
            total = result[0] if result else 0
        return total if total else 0
    except Exception as e:
        conn.close()
        return 0


def insert_data_to_table(table_name, columns_list, values_list):
    """Chèn dữ liệu vào bảng"""
    try:
        conn = connect_db()
        cursor = conn.cursor()

        # Auto-add 'Đã xóa' = 0 if not in columns (prevents NULL on PostgreSQL)
        cols = list(columns_list)
        vals = list(values_list)
        if 'Đã xóa' not in cols:
            # Check if column exists in table
            table_cols = _get_column_names(cursor, table_name)
            col_names_lower = [c.lower() for c in table_cols]
            if 'đã xóa' in col_names_lower or 'Đã xóa' in table_cols:
                cols.append('Đã xóa')
                vals.append(0)

        columns = ", ".join(_q(c) for c in cols)
        placeholders = ', '.join([_ph() for _ in vals])
        query = f"INSERT INTO {_q(table_name)} ({columns}) VALUES ({placeholders})"

        if _db_type == 'postgres':
            # PostgreSQL: dùng RETURNING ID
            query += ' RETURNING "ID"'
            cursor.execute(query, tuple(vals))
            result = cursor.fetchone()
            last_id = result[0] if result else None
        else:
            cursor.execute(query, tuple(vals))
            last_id = cursor.lastrowid

        conn.commit()
        conn.close()
        return {"success": True, "message": "Đã chèn dữ liệu thành công", "id": last_id}
    except Exception as e:
        return {"success": False, "message": f"Lỗi: {str(e)}"}


def update_data_by_id(table_name, row_id, data_dict, nguoisua):
    """Cập nhật một bản ghi theo ID"""
    try:
        conn = connect_db()
        cursor = conn.cursor()

        set_parts = []
        values = []
        for col, val in data_dict.items():
            set_parts.append(f"{_q(col)} = {_ph()}")
            values.append(val)

        set_parts.append(f'{_q("Người sửa")} = {_ph()}')
        values.append(nguoisua)
        set_parts.append(f'{_q("Thời gian sửa")} = {_ph()}')
        values.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

        values.append(row_id)

        sql = f"UPDATE {_q(table_name)} SET {', '.join(set_parts)} WHERE {_q('ID')} = {_ph()}"
        cursor.execute(sql, tuple(values))
        conn.commit()
        conn.close()
        return {"success": True, "message": "Cập nhật thành công"}
    except Exception as e:
        return {"success": False, "message": f"Lỗi: {str(e)}"}


def delete_data_by_ids(table_name, list_ids, nguoisua):
    """Soft delete - đánh dấu xóa theo danh sách ID"""
    try:
        conn = connect_db()
        cursor = conn.cursor()

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if _db_type == 'postgres':
            placeholders = ', '.join([_ph() for _ in list_ids])
            sql = f'UPDATE {_q(table_name)} SET {_q("Đã xóa")} = 1, {_q("Người sửa")}={_ph()}, {_q("Thời gian sửa")}={_ph()} WHERE {_q("ID")} IN ({placeholders})'
            cursor.execute(sql, (nguoisua, now, *[int(i) for i in list_ids]))
        else:
            ids_string = "'" + "','".join(map(str, list_ids)) + "'"
            sql = f"UPDATE [{table_name}] SET [Đã xóa] = 1, [Người sửa]=?, [Thời gian sửa]=? WHERE [ID] IN ({ids_string})"
            cursor.execute(sql, (nguoisua, now))

        conn.commit()
        conn.close()
        return {"success": True, "message": "Đã xóa thành công"}
    except Exception as e:
        return {"success": False, "message": f"Lỗi: {str(e)}"}


def insert_dataframe_to_table(table_name, dataframe, created_by=None, delete_by_ids=None):
    """Import DataFrame vào bảng"""
    try:
        dataframe = dataframe.replace({pd.NA: None, np.nan: None, pd.NaT: None})

        for col in dataframe.columns:
            if pd.api.types.is_datetime64_any_dtype(dataframe[col]):
                dataframe[col] = dataframe[col].apply(
                    lambda x: x.strftime('%Y-%m-%d %H:%M:%S') if pd.notna(x) else None
                )

        conn = connect_db()
        cursor = conn.cursor()

        if created_by is not None:
            dataframe['Người tạo'] = created_by

        for _, row in dataframe.iterrows():
            # Xóa bản ghi cũ nếu có delete_by_ids
            if delete_by_ids is not None:
                conditions = []
                params = []
                for col in delete_by_ids:
                    if col in row.index and pd.notna(row[col]):
                        conditions.append(f"{_q(col)} = {_ph()}")
                        params.append(row[col])

                if conditions:
                    if _has_column(cursor, table_name, 'Đã xóa'):
                        conditions.append(f"{_q('Đã xóa')} = 0")

                    where_clause = " AND ".join(conditions)
                    cursor.execute(f"DELETE FROM {_q(table_name)} WHERE {where_clause}", tuple(params))

            # Insert
            cols = ", ".join(_q(c) for c in dataframe.columns)
            placeholders = ', '.join([_ph() for _ in row])
            cursor.execute(f"INSERT INTO {_q(table_name)} ({cols}) VALUES ({placeholders})", tuple(row))

        conn.commit()
        conn.close()
        return {"success": True, "message": f"Đã import {len(dataframe)} bản ghi thành công"}
    except Exception as e:
        return {"success": False, "message": f"Lỗi: {str(e)}"}


def get_info(df, table_name, columns_name, columns_map, columns_key=None,
             columns_output=None, columns_position=None, where=True):
    """Lấy thông tin từ bảng và merge vào DataFrame"""
    if not all(col in df.columns for col in columns_map):
        return df

    if columns_key is None:
        columns_key = [columns_name[0]]

    col_where_clause = {'Đã xóa': ('=', 0)} if where else None

    unique_values = {}
    for col in columns_map:
        unique_values[col] = df[col].dropna().unique().tolist()

    if col_where_clause is None:
        col_where_clause = {}

    for key, map_col in zip(columns_key, columns_map):
        if unique_values[map_col]:
            col_where_clause[key] = ('IN', unique_values[map_col])

    df_info = get_columns_data(table_name=table_name, columns=columns_name, col_where=col_where_clause)

    if df_info.empty:
        return df

    rename_dict = {key: map_col for key, map_col in zip(columns_key, columns_map)}
    df_info = df_info.rename(columns=rename_dict)
    df_info = df_info.drop_duplicates(subset=columns_map)

    # Normalize merge columns to same type (string) for PostgreSQL compatibility
    # PostgreSQL: ID columns are SERIAL (integer) but other columns are TEXT (string)
    # This causes merge mismatch: '1' (str) != 1 (int)
    for col in columns_map:
        if col in df.columns:
            df[col] = df[col].astype(str)
        if col in df_info.columns:
            df_info[col] = df_info[col].astype(str)

    df_merged = pd.merge(df, df_info, how='left', on=columns_map)

    if columns_output:
        rename_output = {old: new for old, new in zip(columns_name, columns_output) if old in df_merged.columns}
        df_merged = df_merged.rename(columns=rename_output)

    if columns_position:
        final_cols = [col for col in columns_position if col in df_merged.columns]
        df_merged = df_merged[final_cols]

    return df_merged


def generate_next_code(tablename, column_name, prefix='DH', num_char=5):
    """Tạo mã tự động tiếp theo (ví dụ: DH00001, DH00002)"""
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute(f"SELECT MAX({_q(column_name)}) FROM {_q(tablename)}")
        result = cursor.fetchone()
        conn.close()

        if _db_type == 'postgres' and isinstance(result, dict):
            last_code = list(result.values())[0]
        else:
            last_code = result[0] if result else None

        if last_code:
            num_part = int(last_code.replace(prefix, ''))
            next_num = num_part + 1
        else:
            next_num = 1

        return f"{prefix}{str(next_num).zfill(num_char)}"
    except:
        return f"{prefix}{'1'.zfill(num_char)}"
