"""
database.py
-----------
SQLite persistence layer for the E-commerce Customer Analytics web app.

Design
  * Three normalised tables: ``products`` (the catalogue: category -> subcategory
    -> product, each with a fixed list price and the stock on hand), ``customers``
    and ``orders`` (one row per order, foreign keys -> customers and products).
  * Stock is kept correct by triggers: a delivered order takes its quantity out of
    stock; cancelling, returning or deleting it puts the quantity back. The
    ``CHECK (stock_on_hand >= 0)`` constraint makes the database itself refuse an
    order for more units than are in stock.
  * The business rules used by the cleaning pipeline are enforced a second time
    by the database itself through CHECK constraints, so invalid data cannot be
    written even if a bug slipped past the form validation.
  * Derived values (total_amount, net_revenue, age_group, ...) are NOT stored.
    They are computed by the ``v_orders`` view, so they can never drift out of
    sync when an order is edited.

The database is built from ``data/processed/ecommerce_orders_clean.csv`` — the
output of ``src/data_cleaning.py`` — the first time the app starts.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path(__file__).resolve().parent / "instance" / "ecommerce.db"
CLEAN_CSV = ROOT / "data" / "processed" / "ecommerce_orders_clean.csv"
PRODUCTS_CSV = ROOT / "data" / "processed" / "products.csv"

# Allowed values — shared by the schema, the form validation and the templates.
CATEGORIES = ["Electronics", "Fashion", "Home & Kitchen", "Beauty", "Sports", "Books", "Toys"]
STATUSES = ["Delivered", "Returned", "Cancelled"]
SEGMENTS = ["New", "Regular", "VIP"]
CHANNELS = ["Organic Search", "Social Media", "Email", "Paid Ads", "Referral"]
PAYMENTS = ["Credit Card", "E-Wallet", "Bank Transfer", "Cash on Delivery", "PayPal"]
DEVICES = ["Mobile", "Desktop", "Tablet"]
GENDERS = ["Female", "Male"]
COUNTRIES = ["Cambodia", "Thailand", "Vietnam", "Singapore", "Malaysia", "Philippines", "Indonesia"]


def _in(values: list[str]) -> str:
    return "(" + ", ".join("'" + v.replace("'", "''") + "'" for v in values) + ")"


SCHEMA = f"""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS customers (
    customer_id          TEXT PRIMARY KEY,
    age                  INTEGER NOT NULL CHECK (age BETWEEN 18 AND 100),
    gender               TEXT    NOT NULL CHECK (gender IN {_in(GENDERS)}),
    country              TEXT    NOT NULL CHECK (country IN {_in(COUNTRIES)}),
    city                 TEXT    NOT NULL CHECK (length(trim(city)) > 0),
    signup_date          TEXT    NOT NULL CHECK (date(signup_date) IS NOT NULL),
    customer_segment     TEXT    NOT NULL CHECK (customer_segment IN {_in(SEGMENTS)}),
    acquisition_channel  TEXT    NOT NULL CHECK (acquisition_channel IN {_in(CHANNELS)})
);

CREATE TABLE IF NOT EXISTS products (
    product_id     TEXT PRIMARY KEY,
    product_name   TEXT    NOT NULL UNIQUE CHECK (length(trim(product_name)) > 0),
    category       TEXT    NOT NULL CHECK (category IN {_in(CATEGORIES)}),
    subcategory    TEXT    NOT NULL CHECK (length(trim(subcategory)) > 0),
    unit_price     REAL    NOT NULL CHECK (unit_price > 0 AND unit_price <= 5000),
    stock_on_hand  INTEGER NOT NULL CHECK (stock_on_hand >= 0),
    reorder_level  INTEGER NOT NULL DEFAULT 10 CHECK (reorder_level >= 0)
);

CREATE TABLE IF NOT EXISTS orders (
    order_id          TEXT PRIMARY KEY,
    order_date        TEXT    NOT NULL CHECK (date(order_date) IS NOT NULL),
    customer_id       TEXT    NOT NULL REFERENCES customers(customer_id) ON DELETE RESTRICT,
    product_id        TEXT    NOT NULL REFERENCES products(product_id) ON DELETE RESTRICT,
    quantity          INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 50),
    unit_price        REAL    NOT NULL CHECK (unit_price > 0 AND unit_price <= 5000),  -- list price when ordered
    discount_pct      REAL    NOT NULL CHECK (discount_pct BETWEEN 0 AND 100),
    shipping_cost     REAL    NOT NULL CHECK (shipping_cost BETWEEN 0 AND 100),
    payment_method    TEXT    NOT NULL CHECK (payment_method IN {_in(PAYMENTS)}),
    device_type       TEXT    NOT NULL CHECK (device_type IN {_in(DEVICES)}),
    order_status      TEXT    NOT NULL CHECK (order_status IN {_in(STATUSES)}),
    delivery_days     REAL             CHECK (delivery_days IS NULL OR delivery_days BETWEEN 0 AND 30),
    review_rating     INTEGER          CHECK (review_rating IS NULL OR review_rating BETWEEN 1 AND 5),
    -- a cancelled order is never delivered, so it cannot have a delivery time or a review
    CHECK (order_status <> 'Cancelled' OR (delivery_days IS NULL AND review_rating IS NULL)),
    CHECK (order_status =  'Cancelled' OR delivery_days IS NOT NULL)
);

-- Change counter: bumped by triggers on every write, so an open dashboard can
-- poll it cheaply and refresh only when the data actually changed.
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
INSERT OR IGNORE INTO meta VALUES ('data_version', 0);
CREATE TRIGGER IF NOT EXISTS trg_orders_ins AFTER INSERT ON orders    BEGIN UPDATE meta SET value = value + 1 WHERE key = 'data_version'; END;
CREATE TRIGGER IF NOT EXISTS trg_orders_upd AFTER UPDATE ON orders    BEGIN UPDATE meta SET value = value + 1 WHERE key = 'data_version'; END;
CREATE TRIGGER IF NOT EXISTS trg_orders_del AFTER DELETE ON orders    BEGIN UPDATE meta SET value = value + 1 WHERE key = 'data_version'; END;
CREATE TRIGGER IF NOT EXISTS trg_cust_ins   AFTER INSERT ON customers BEGIN UPDATE meta SET value = value + 1 WHERE key = 'data_version'; END;
CREATE TRIGGER IF NOT EXISTS trg_cust_upd   AFTER UPDATE ON customers BEGIN UPDATE meta SET value = value + 1 WHERE key = 'data_version'; END;
CREATE TRIGGER IF NOT EXISTS trg_cust_del   AFTER DELETE ON customers BEGIN UPDATE meta SET value = value + 1 WHERE key = 'data_version'; END;
CREATE TRIGGER IF NOT EXISTS trg_prod_ins   AFTER INSERT ON products  BEGIN UPDATE meta SET value = value + 1 WHERE key = 'data_version'; END;
CREATE TRIGGER IF NOT EXISTS trg_prod_upd   AFTER UPDATE ON products  BEGIN UPDATE meta SET value = value + 1 WHERE key = 'data_version'; END;
CREATE TRIGGER IF NOT EXISTS trg_prod_del   AFTER DELETE ON products  BEGIN UPDATE meta SET value = value + 1 WHERE key = 'data_version'; END;

CREATE INDEX IF NOT EXISTS ix_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS ix_orders_date     ON orders(order_date);
CREATE INDEX IF NOT EXISTS ix_orders_product  ON orders(product_id);

-- Every derived column the analysis needs, computed on the fly.
CREATE VIEW IF NOT EXISTS v_orders AS
SELECT
    o.*,
    p.product_name, p.category AS product_category, p.subcategory,
    c.age, c.gender, c.country, c.city, c.signup_date, c.customer_segment, c.acquisition_channel,
    ROUND(o.quantity * o.unit_price, 2)                                           AS gross_amount,
    ROUND(o.quantity * o.unit_price * o.discount_pct / 100.0, 2)                  AS discount_amount,
    ROUND(o.quantity * o.unit_price * (1 - o.discount_pct / 100.0) + o.shipping_cost, 2) AS total_amount,
    CASE WHEN o.order_status = 'Delivered'
         THEN ROUND(o.quantity * o.unit_price * (1 - o.discount_pct / 100.0) + o.shipping_cost, 2)
         ELSE 0 END                                                               AS net_revenue,
    substr(o.order_date, 1, 7)                                                    AS order_month,
    CASE WHEN c.age <= 24 THEN '18-24' WHEN c.age <= 34 THEN '25-34'
         WHEN c.age <= 44 THEN '35-44' WHEN c.age <= 54 THEN '45-54' ELSE '55+' END AS age_group,
    CAST(julianday(o.order_date) - julianday(c.signup_date) AS INTEGER)           AS customer_tenure_days
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
JOIN products  p ON p.product_id  = o.product_id;
"""

# Stock movements. Created *after* the historical orders are loaded, because the
# catalogue's stock_on_hand is already the stock left after those orders.
# Only a delivered order holds stock: cancelled orders never shipped, returned
# items came back. If an update would push stock below zero, the CHECK on
# products.stock_on_hand fails and the whole statement is rolled back.
STOCK_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS trg_stock_ins AFTER INSERT ON orders WHEN NEW.order_status = 'Delivered'
BEGIN UPDATE products SET stock_on_hand = stock_on_hand - NEW.quantity WHERE product_id = NEW.product_id; END;

CREATE TRIGGER IF NOT EXISTS trg_stock_del AFTER DELETE ON orders WHEN OLD.order_status = 'Delivered'
BEGIN UPDATE products SET stock_on_hand = stock_on_hand + OLD.quantity WHERE product_id = OLD.product_id; END;

CREATE TRIGGER IF NOT EXISTS trg_stock_upd AFTER UPDATE OF product_id, quantity, order_status ON orders
BEGIN
    UPDATE products SET stock_on_hand = stock_on_hand + OLD.quantity
     WHERE product_id = OLD.product_id AND OLD.order_status = 'Delivered';
    UPDATE products SET stock_on_hand = stock_on_hand - NEW.quantity
     WHERE product_id = NEW.product_id AND NEW.order_status = 'Delivered';
END;
"""


def connect(db_path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _mode(series: pd.Series):
    """Most frequent value; ties broken by first occurrence."""
    counts = series.value_counts(sort=False)
    return counts.idxmax()


def build_database(db_path: Path | str = DEFAULT_DB, csv_path: Path | str = CLEAN_CSV,
                   products_path: Path | str = PRODUCTS_CSV) -> dict:
    """(Re)create the database from the cleaned CSVs. Returns a small load report."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(csv_path)
    products = pd.read_csv(products_path)
    prod_cols = ["product_id", "product_name", "category", "subcategory", "unit_price", "stock_on_hand", "reorder_level"]

    # ---- customers: one row each. Per-order imputation left some customers with
    # different ages/cities across their orders, so keep each customer's most
    # frequent value (the true value appears on most of their orders).
    attrs = ["age", "gender", "country", "city", "signup_date", "customer_segment", "acquisition_channel"]
    conflicts = int((df.groupby("customer_id")[attrs].nunique() > 1).any(axis=1).sum())
    customers = df.groupby("customer_id")[attrs].agg(_mode).reset_index()
    customers["age"] = customers["age"].astype(int)

    order_cols = ["order_id", "order_date", "customer_id", "product_id", "quantity", "unit_price",
                  "discount_pct", "shipping_cost", "payment_method", "device_type", "order_status",
                  "delivery_days", "review_rating"]
    orders = df[order_cols].copy()
    orders["quantity"] = orders["quantity"].astype(int)
    orders["review_rating"] = orders["review_rating"].astype("Int64")
    orders = orders.astype(object).where(orders.notna(), None)

    # Rebuild in place (dropping objects) rather than deleting the file: on Windows a
    # SQLite file that another request still has open cannot be deleted.
    conn = connect(db_path)
    old_version = 0
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'meta'").fetchone():
        old_version = conn.execute("SELECT value FROM meta WHERE key = 'data_version'").fetchone()[0]
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript("""
        DROP VIEW IF EXISTS v_orders;
        DROP TABLE IF EXISTS orders;
        DROP TABLE IF EXISTS customers;
        DROP TABLE IF EXISTS products;
        DROP TABLE IF EXISTS meta;""")
    conn.execute("PRAGMA foreign_keys = ON")
    with conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            f"INSERT INTO products ({', '.join(prod_cols)}) VALUES ({', '.join('?' * len(prod_cols))})",
            products[prod_cols].astype(object).itertuples(index=False, name=None))
        conn.executemany(
            f"INSERT INTO customers ({', '.join(['customer_id'] + attrs)}) VALUES ({', '.join('?' * (len(attrs) + 1))})",
            customers[["customer_id"] + attrs].itertuples(index=False, name=None))
        conn.executemany(
            f"INSERT INTO orders ({', '.join(order_cols)}) VALUES ({', '.join('?' * len(order_cols))})",
            orders.itertuples(index=False, name=None))
        conn.executescript(STOCK_TRIGGERS)
        # keep the change counter strictly increasing so open dashboards notice a reset
        conn.execute("UPDATE meta SET value = ? WHERE key = 'data_version'",
                     (max(old_version + 1, conn.execute("SELECT value FROM meta").fetchone()[0]),))
    conn.execute("VACUUM")
    report = {
        "customers": conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
        "orders": conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        "products": conn.execute("SELECT COUNT(*) FROM products").fetchone()[0],
        "customers_with_conflicting_attributes": conflicts,
    }
    conn.close()
    return report


def ensure_database(db_path: Path | str = DEFAULT_DB) -> None:
    """Build the database on first run, or rebuild one created by an older version of the app."""
    current = False
    if Path(db_path).exists():
        conn = sqlite3.connect(str(db_path))
        current = conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'trg_stock_ins'").fetchone() is not None
        conn.close()
    if not current:
        report = build_database(db_path)
        print(f"Built database {db_path}: {report}")


def next_id(conn: sqlite3.Connection, table: str, column: str, prefix: str, width: int) -> str:
    row = conn.execute(
        f"SELECT MAX(CAST(substr({column}, {len(prefix) + 1}) AS INTEGER)) FROM {table}").fetchone()
    return f"{prefix}{(row[0] or 0) + 1:0{width}d}"


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Build the SQLite database from the cleaned CSV.")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    args = ap.parse_args()
    print(build_database(args.db))
