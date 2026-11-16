"""SQLite storage and Frappe-compatible query layer for the ERPNext mock server."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "erpnext_mock.db"


def get_db_path() -> Path:
    """Return the configured SQLite database path."""
    env_path = os.environ.get("ERPNEXT_MOCK_DB")
    return Path(env_path) if env_path else DEFAULT_DB_PATH


@contextmanager
def get_connection(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection with row_factory and foreign keys enabled."""
    path = db_path or get_db_path()
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# DocType metadata: SQLite table name, allowed columns, child table (if any), and ID prefix.
DOCTYPE_CONFIG: dict[str, dict[str, Any]] = {
    "Item": {
        "table": "tabItem",
        "columns": [
            "name",
            "item_code",
            "item_name",
            "item_group",
            "stock_uom",
            "standard_rate",
            "brand",
            "disabled",
            "creation",
            "modified",
        ],
        "child_table": None,
        "prefix": "ITEM-",
    },
    "Supplier": {
        "table": "tabSupplier",
        "columns": [
            "name",
            "supplier_name",
            "supplier_group",
            "country",
            "default_currency",
            "archetype",
            "creation",
            "modified",
        ],
        "child_table": None,
        "prefix": "SUP-",
    },
    "Purchase Order": {
        "table": "tabPurchaseOrder",
        "columns": [
            "name",
            "supplier",
            "transaction_date",
            "schedule_date",
            "status",
            "currency",
            "total_qty",
            "grand_total",
            "notes",
            "creation",
            "modified",
        ],
        "child_table": "tabPurchaseOrderItem",
        "child_columns": [
            "idx",
            "item_code",
            "item_name",
            "item_group",
            "qty",
            "uom",
            "rate",
            "amount",
        ],
        "prefix": "PUR-ORD-2026-",
    },
    "Purchase Invoice": {
        "table": "tabPurchaseInvoice",
        "columns": [
            "name",
            "supplier",
            "posting_date",
            "due_date",
            "status",
            "currency",
            "total_qty",
            "grand_total",
            "purchase_order",
            "notes",
            "creation",
            "modified",
        ],
        "child_table": "tabPurchaseInvoiceItem",
        "child_columns": [
            "idx",
            "item_code",
            "item_name",
            "item_group",
            "qty",
            "uom",
            "rate",
            "amount",
            "purchase_order",
        ],
        "prefix": "ACC-PINV-2026-",
    },
}


def init_db(db_path: Path | None = None) -> None:
    """Create all ERPNext mock tables if they do not already exist."""
    with get_connection(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tabItem (
                name TEXT PRIMARY KEY,
                item_code TEXT UNIQUE NOT NULL,
                item_name TEXT NOT NULL,
                item_group TEXT NOT NULL,
                stock_uom TEXT NOT NULL DEFAULT 'Case',
                standard_rate REAL NOT NULL DEFAULT 0.0,
                brand TEXT DEFAULT '',
                disabled INTEGER NOT NULL DEFAULT 0,
                creation TEXT NOT NULL,
                modified TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tabSupplier (
                name TEXT PRIMARY KEY,
                supplier_name TEXT NOT NULL,
                supplier_group TEXT NOT NULL DEFAULT 'Wholesale',
                country TEXT NOT NULL DEFAULT 'United Kingdom',
                default_currency TEXT NOT NULL DEFAULT 'GBP',
                archetype TEXT NOT NULL DEFAULT 'Standard',
                creation TEXT NOT NULL,
                modified TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tabPurchaseOrder (
                name TEXT PRIMARY KEY,
                supplier TEXT NOT NULL,
                transaction_date TEXT NOT NULL,
                schedule_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'To Receive and Bill',
                currency TEXT NOT NULL DEFAULT 'GBP',
                total_qty REAL NOT NULL DEFAULT 0.0,
                grand_total REAL NOT NULL DEFAULT 0.0,
                notes TEXT DEFAULT '',
                creation TEXT NOT NULL,
                modified TEXT NOT NULL,
                FOREIGN KEY (supplier) REFERENCES tabSupplier(name)
            );

            CREATE TABLE IF NOT EXISTS tabPurchaseOrderItem (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent TEXT NOT NULL,
                idx INTEGER NOT NULL DEFAULT 1,
                item_code TEXT NOT NULL,
                item_name TEXT NOT NULL,
                item_group TEXT NOT NULL DEFAULT '',
                qty REAL NOT NULL,
                uom TEXT NOT NULL DEFAULT 'Case',
                rate REAL NOT NULL,
                amount REAL NOT NULL,
                FOREIGN KEY (parent) REFERENCES tabPurchaseOrder(name) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS tabPurchaseInvoice (
                name TEXT PRIMARY KEY,
                supplier TEXT NOT NULL,
                posting_date TEXT NOT NULL,
                due_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Unpaid',
                currency TEXT NOT NULL DEFAULT 'GBP',
                total_qty REAL NOT NULL DEFAULT 0.0,
                grand_total REAL NOT NULL DEFAULT 0.0,
                purchase_order TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                creation TEXT NOT NULL,
                modified TEXT NOT NULL,
                FOREIGN KEY (supplier) REFERENCES tabSupplier(name)
            );

            CREATE TABLE IF NOT EXISTS tabPurchaseInvoiceItem (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent TEXT NOT NULL,
                idx INTEGER NOT NULL DEFAULT 1,
                item_code TEXT NOT NULL,
                item_name TEXT NOT NULL,
                item_group TEXT NOT NULL DEFAULT '',
                qty REAL NOT NULL,
                uom TEXT NOT NULL DEFAULT 'Case',
                rate REAL NOT NULL,
                amount REAL NOT NULL,
                purchase_order TEXT DEFAULT '',
                FOREIGN KEY (parent) REFERENCES tabPurchaseInvoice(name) ON DELETE CASCADE
            );
            """
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_filters(
    raw_filters: str | None, allowed_columns: list[str]
) -> tuple[str, list[Any]]:
    """Parse Frappe JSON filters into a parameterized SQL WHERE clause."""
    if not raw_filters:
        return "", []

    parsed = json.loads(raw_filters)
    clauses: list[str] = []
    params: list[Any] = []

    op_map = {
        "=": "=",
        "!=": "!=",
        ">": ">",
        ">=": ">=",
        "<": "<",
        "<=": "<=",
        "like": "LIKE",
        "not like": "NOT LIKE",
    }

    if isinstance(parsed, dict):
        for field, val in parsed.items():
            if field not in allowed_columns:
                raise ValueError(f"Invalid filter field: {field}")
            clauses.append(f"{field} = ?")
            params.append(val)
    elif isinstance(parsed, list):
        for item in parsed:
            if not isinstance(item, list):
                raise ValueError("Filter entries must be lists")
            # Support both [field, op, val] and [doctype, field, op, val]
            if len(item) == 4:
                _, field, op, val = item
            elif len(item) == 3:
                field, op, val = item
            else:
                raise ValueError("Filter entry must have 3 or 4 elements")

            if field not in allowed_columns:
                raise ValueError(f"Invalid filter field: {field}")
            op_lower = str(op).strip().lower()

            if op_lower in ("in", "not in"):
                if not isinstance(val, list) or not val:
                    raise ValueError(f"Filter operator '{op}' requires a non-empty list")
                placeholders = ", ".join("?" for _ in val)
                sql_op = "IN" if op_lower == "in" else "NOT IN"
                clauses.append(f"{field} {sql_op} ({placeholders})")
                params.extend(val)
            elif op_lower in op_map:
                clauses.append(f"{field} {op_map[op_lower]} ?")
                params.append(val)
            else:
                raise ValueError(f"Unsupported filter operator: {op}")
    else:
        raise ValueError("Filters must be a JSON object or array")

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where_sql, params


def list_documents(
    doctype: str,
    fields: str | None = None,
    filters: str | None = None,
    order_by: str | None = None,
    limit_start: int = 0,
    limit_page_length: int = 20,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Query documents from a DocType table using Frappe REST parameters."""
    if doctype not in DOCTYPE_CONFIG:
        raise KeyError(doctype)

    cfg = DOCTYPE_CONFIG[doctype]
    allowed_cols: list[str] = cfg["columns"]
    table: str = cfg["table"]

    if fields:
        requested = json.loads(fields)
        if requested == ["*"]:
            selected_cols = allowed_cols
        else:
            invalid = [f for f in requested if f not in allowed_cols]
            if invalid:
                raise ValueError(f"Invalid fields requested: {invalid}")
            selected_cols = requested
    else:
        selected_cols = ["name"]

    where_sql, params = _parse_filters(filters, allowed_cols)

    order_sql = "ORDER BY creation DESC"
    if order_by:
        parts = order_by.strip().split()
        col = parts[0]
        direction = parts[1].upper() if len(parts) > 1 else "ASC"
        if col not in allowed_cols or direction not in ("ASC", "DESC"):
            raise ValueError(f"Invalid order_by clause: {order_by}")
        order_sql = f"ORDER BY {col} {direction}"

    limit_sql = ""
    if limit_page_length and limit_page_length > 0:
        limit_sql = "LIMIT ? OFFSET ?"
        params.extend([limit_page_length, max(0, limit_start)])

    query = f"SELECT {', '.join(selected_cols)} FROM {table} {where_sql} {order_sql} {limit_sql}"

    with get_connection(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def get_document(
    doctype: str, name: str, db_path: Path | None = None
) -> dict[str, Any] | None:
    """Fetch a single document by name, including child items if applicable."""
    if doctype not in DOCTYPE_CONFIG:
        raise KeyError(doctype)

    cfg = DOCTYPE_CONFIG[doctype]
    with get_connection(db_path) as conn:
        row = conn.execute(
            f"SELECT * FROM {cfg['table']} WHERE name = ?", (name,)
        ).fetchone()
        if not row:
            return None
        doc = dict(row)
        doc["doctype"] = doctype

        child_table = cfg["child_table"]
        if child_table:
            child_rows = conn.execute(
                f"SELECT * FROM {child_table} WHERE parent = ? ORDER BY idx ASC",
                (name,),
            ).fetchall()
            doc["items"] = [dict(c) for c in child_rows]

        return doc


def _next_doc_name(conn: sqlite3.Connection, doctype: str, data: dict[str, Any]) -> str:
    """Generate a Frappe-style document name when not explicitly supplied."""
    if doctype == "Item" and data.get("item_code"):
        return str(data["item_code"])
    if doctype == "Supplier" and data.get("supplier_name"):
        return str(data["supplier_name"])

    cfg = DOCTYPE_CONFIG[doctype]
    count_row = conn.execute(f"SELECT COUNT(*) AS cnt FROM {cfg['table']}").fetchone()
    next_num = int(count_row["cnt"]) + 1
    return f"{cfg['prefix']}{next_num:05d}"


def create_document(
    doctype: str, payload: dict[str, Any], db_path: Path | None = None
) -> dict[str, Any]:
    """Insert a new document (and optional child items) into SQLite."""
    if doctype not in DOCTYPE_CONFIG:
        raise KeyError(doctype)

    cfg = DOCTYPE_CONFIG[doctype]
    now = _now_iso()
    data = dict(payload)

    with get_connection(db_path) as conn:
        name = str(data.get("name") or _next_doc_name(conn, doctype, data))
        data["name"] = name
        if doctype == "Item" and not data.get("item_code"):
            data["item_code"] = name
        data.setdefault("creation", now)
        data.setdefault("modified", now)

        items = data.pop("items", None)
        if items is not None and cfg["child_table"]:
            total_qty = sum(float(i.get("qty", 0)) for i in items)
            grand_total = sum(
                float(i.get("amount", float(i.get("qty", 0)) * float(i.get("rate", 0))))
                for i in items
            )
            data.setdefault("total_qty", round(total_qty, 2))
            data.setdefault("grand_total", round(grand_total, 2))

        cols = [c for c in cfg["columns"] if c in data]
        placeholders = ", ".join("?" for _ in cols)
        conn.execute(
            f"INSERT INTO {cfg['table']} ({', '.join(cols)}) VALUES ({placeholders})",
            [data[c] for c in cols],
        )

        if items and cfg["child_table"]:
            _insert_child_items(conn, cfg["child_table"], cfg["child_columns"], name, items)

    created = get_document(doctype, name, db_path)
    assert created is not None
    return created


def _insert_child_items(
    conn: sqlite3.Connection,
    child_table: str,
    child_columns: list[str],
    parent_name: str,
    items: list[dict[str, Any]],
) -> None:
    """Insert child line items for Purchase Order or Purchase Invoice."""
    for idx, item in enumerate(items, start=1):
        row = dict(item)
        row.setdefault("idx", idx)
        qty = float(row.get("qty", 0))
        rate = float(row.get("rate", 0))
        row.setdefault("amount", round(qty * rate, 2))
        cols = ["parent"] + [c for c in child_columns if c in row]
        vals = [parent_name] + [row[c] for c in cols if c != "parent"]
        placeholders = ", ".join("?" for _ in cols)
        conn.execute(
            f"INSERT INTO {child_table} ({', '.join(cols)}) VALUES ({placeholders})",
            vals,
        )


def update_document(
    doctype: str, name: str, payload: dict[str, Any], db_path: Path | None = None
) -> dict[str, Any] | None:
    """Update an existing document's fields (and optionally replace child items)."""
    if doctype not in DOCTYPE_CONFIG:
        raise KeyError(doctype)

    existing = get_document(doctype, name, db_path)
    if not existing:
        return None

    cfg = DOCTYPE_CONFIG[doctype]
    data = dict(payload)
    data["modified"] = _now_iso()
    items = data.pop("items", None)

    with get_connection(db_path) as conn:
        if items is not None and cfg["child_table"]:
            conn.execute(f"DELETE FROM {cfg['child_table']} WHERE parent = ?", (name,))
            _insert_child_items(conn, cfg["child_table"], cfg["child_columns"], name, items)
            data["total_qty"] = round(sum(float(i.get("qty", 0)) for i in items), 2)
            data["grand_total"] = round(
                sum(
                    float(i.get("amount", float(i.get("qty", 0)) * float(i.get("rate", 0))))
                    for i in items
                ),
                2,
            )

        update_cols = [c for c in cfg["columns"] if c in data and c != "name"]
        if update_cols:
            set_clause = ", ".join(f"{c} = ?" for c in update_cols)
            conn.execute(
                f"UPDATE {cfg['table']} SET {set_clause} WHERE name = ?",
                [data[c] for c in update_cols] + [name],
            )

    return get_document(doctype, name, db_path)


def delete_document(
    doctype: str, name: str, db_path: Path | None = None
) -> bool:
    """Delete a document by name. Returns True if a row was deleted."""
    if doctype not in DOCTYPE_CONFIG:
        raise KeyError(doctype)

    cfg = DOCTYPE_CONFIG[doctype]
    with get_connection(db_path) as conn:
        cur = conn.execute(f"DELETE FROM {cfg['table']} WHERE name = ?", (name,))
        return cur.rowcount > 0
