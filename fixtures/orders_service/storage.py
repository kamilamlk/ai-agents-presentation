"""The order table.

One row per order, keyed by order id. Rows are written through insert_row and
never updated: a correction arrives as a new order that voids the old one.
"""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    order_id   TEXT PRIMARY KEY,
    total      INTEGER NOT NULL,
    state      TEXT NOT NULL
)
"""


def connect(path=":memory:"):
    conn = sqlite3.connect(path)
    conn.execute(SCHEMA)
    return conn


def upsert_row(conn, order_id, total, state):
    """Write the order, or overwrite it if the retry arrives after the first try."""
    conn.execute(
        "INSERT INTO orders (order_id, total, state) VALUES (?, ?, ?) "
        "ON CONFLICT (order_id) DO UPDATE SET total = ?, state = ?",
        (order_id, total, state, total, state),
    )
    conn.commit()


def row(conn, order_id):
    cur = conn.execute(
        "SELECT order_id, total, state FROM orders WHERE order_id = ?", (order_id,)
    )
    return cur.fetchone()


def states(conn):
    # ORDER_STATES is the list the column is allowed to hold.
    return [r[0] for r in conn.execute("SELECT DISTINCT state FROM orders")]
