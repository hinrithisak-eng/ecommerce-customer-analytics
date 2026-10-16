"""
app.py
------
Flask web application for E-commerce Customer Analytics.

    python webapp/app.py            # builds the SQLite DB on first run, serves http://127.0.0.1:5000

Pages
  /                      live analytics dashboard (charts read /api/analytics)
  /orders                search, filter, sort and page through orders; add / edit / delete
  /customers             same for customers
API
  /api/analytics         every dashboard number, computed with SQL (?country=&segment=&category=)
  /api/version           data-change counter, polled by the dashboard to auto-refresh
  /api/customers/<id>    customer summary, used by the order form
"""

from __future__ import annotations

import math
import secrets
import sqlite3
from datetime import date, datetime
from pathlib import Path

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template, request, session, url_for)

try:  # imported as a package (tests, `flask --app webapp.app`)
    from . import analytics
    from . import database as dbm
except ImportError:  # run as a script: python webapp/app.py
    import analytics
    import database as dbm

PAGE_SIZE = 25
ORDER_SORTS = {"order_date", "order_id", "customer_id", "product_category", "total_amount", "order_status", "country"}
CUSTOMER_SORTS = {"customer_id", "country", "customer_segment", "orders", "spent", "last_order", "age"}


# ----------------------------------------------------------------------------- validation
def _num(form, key, cast, errors, label, lo=None, hi=None, required=True):
    raw = (form.get(key) or "").strip()
    if raw == "":
        if required:
            errors[key] = f"{label} is required."
        return None
    try:
        val = cast(raw)
        if cast is float and not math.isfinite(val):
            raise ValueError
    except ValueError:
        errors[key] = f"{label} must be a {'whole number' if cast is int else 'number'}."
        return None
    if (lo is not None and val < lo) or (hi is not None and val > hi):
        errors[key] = f"{label} must be between {lo:g} and {hi:g}."
    return val


def _choice(form, key, options, errors, label):
    val = (form.get(key) or "").strip()
    if val not in options:
        errors[key] = f"Choose a valid {label.lower()}."
    return val


def _date(form, key, errors, label):
    raw = (form.get(key) or "").strip()
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        errors[key] = f"{label} must be a valid date (YYYY-MM-DD)."
        return raw


def validate_order(form, conn) -> tuple[dict, dict]:
    """Same business rules as the cleaning pipeline (notebook §8), applied at entry time."""
    e: dict = {}
    d = {
        "order_date": _date(form, "order_date", e, "Order date"),
        "customer_id": (form.get("customer_id") or "").strip().upper(),
        "product_category": _choice(form, "product_category", dbm.CATEGORIES, e, "Category"),
        "quantity": _num(form, "quantity", int, e, "Quantity", 1, 50),
        "unit_price": _num(form, "unit_price", float, e, "Unit price", 0.01, 5000),
        "discount_pct": _num(form, "discount_pct", float, e, "Discount", 0, 100),
        "shipping_cost": _num(form, "shipping_cost", float, e, "Shipping cost", 0, 100),
        "payment_method": _choice(form, "payment_method", dbm.PAYMENTS, e, "Payment method"),
        "device_type": _choice(form, "device_type", dbm.DEVICES, e, "Device"),
        "order_status": _choice(form, "order_status", dbm.STATUSES, e, "Status"),
        "delivery_days": _num(form, "delivery_days", float, e, "Delivery days", 0, 30, required=False),
        "review_rating": _num(form, "review_rating", int, e, "Review rating", 1, 5, required=False),
    }
    cust = conn.execute("SELECT signup_date FROM customers WHERE customer_id = ?", (d["customer_id"],)).fetchone()
    if not d["customer_id"]:
        e["customer_id"] = "Customer is required."
    elif cust is None:
        e["customer_id"] = f"No customer {d['customer_id']} — add the customer first."
    elif "order_date" not in e and d["order_date"] < cust["signup_date"]:
        e["order_date"] = f"Order date can't be before the customer signed up ({cust['signup_date']})."
    if d["order_status"] == "Cancelled":
        if d["delivery_days"] is not None or d["review_rating"] is not None:
            e["order_status"] = "A cancelled order can't have a delivery time or a review."
    elif d["order_status"] in dbm.STATUSES and d["delivery_days"] is None and "delivery_days" not in e:
        e["delivery_days"] = "Delivery days is required unless the order was cancelled."
    if d["quantity"] is not None and d["unit_price"] is not None and "unit_price" not in e:
        d["unit_price"] = round(d["unit_price"], 2)
    return d, e


def validate_customer(form, conn, customer_id: str | None = None) -> tuple[dict, dict]:
    e: dict = {}
    d = {
        "age": _num(form, "age", int, e, "Age", 18, 100),
        "gender": _choice(form, "gender", dbm.GENDERS, e, "Gender"),
        "country": _choice(form, "country", dbm.COUNTRIES, e, "Country"),
        "city": (form.get("city") or "").strip(),
        "signup_date": _date(form, "signup_date", e, "Sign-up date"),
        "customer_segment": _choice(form, "customer_segment", dbm.SEGMENTS, e, "Segment"),
        "acquisition_channel": _choice(form, "acquisition_channel", dbm.CHANNELS, e, "Channel"),
    }
    if not d["city"]:
        e["city"] = "City is required."
    elif len(d["city"]) > 60:
        e["city"] = "City must be 60 characters or fewer."
    if "signup_date" not in e and d["signup_date"] > date.today().isoformat():
        e["signup_date"] = "Sign-up date can't be in the future."
    if customer_id and "signup_date" not in e:
        first = conn.execute("SELECT MIN(order_date) FROM orders WHERE customer_id = ?", (customer_id,)).fetchone()[0]
        if first and d["signup_date"] > first:
            e["signup_date"] = f"Sign-up date can't be after this customer's first order ({first})."
    return d, e


def safe_next(target: str | None, fallback: str) -> str:
    """Only follow same-site relative paths from the `next` field (prevents open redirects)."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return fallback


# ----------------------------------------------------------------------------- app factory
def create_app(db_path: str | Path | None = None, testing: bool = False) -> Flask:
    app = Flask(__name__)
    app.config.update(
        DATABASE=str(db_path or dbm.DEFAULT_DB),
        SECRET_KEY=secrets.token_hex(32),
        TESTING=testing,
        JSON_SORT_KEYS=False,
    )
    dbm.ensure_database(app.config["DATABASE"])

    # ---- per-request DB connection ------------------------------------------------------
    def db() -> sqlite3.Connection:
        if "db" not in g:
            g.db = dbm.connect(app.config["DATABASE"])
        return g.db

    @app.teardown_appcontext
    def _close(_exc):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    # ---- CSRF protection for every form POST -------------------------------------------
    def csrf_token() -> str:
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_urlsafe(32)
        return session["_csrf"]

    @app.before_request
    def _check_csrf():
        if request.method == "POST":
            sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
            if not sent or sent != session.get("_csrf"):
                abort(400, description="The form expired or was submitted from another page. Reload and try again.")

    @app.context_processor
    def _globals():
        conn = db()
        nav = {
            "orders": conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
            "customers": conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
            "version": conn.execute("SELECT value FROM meta WHERE key='data_version'").fetchone()[0],
            "loaded_at": datetime.now().strftime("%H:%M"),
        }
        return {"csrf_token": csrf_token, "C": dbm, "today": date.today().isoformat(), "nav": nav}

    @app.template_filter("money")
    def _money(v):
        return "" if v is None else f"${v:,.2f}"


    def options(conn):
        return {
            "countries": [r[0] for r in conn.execute("SELECT DISTINCT country FROM customers ORDER BY 1")],
            "segments": [s for s in dbm.SEGMENTS],
            "categories": [r[0] for r in conn.execute("SELECT DISTINCT product_category FROM orders ORDER BY 1")],
        }

    def page_args(total: int):
        page = max(1, request.args.get("page", 1, type=int))
        pages = max(1, math.ceil(total / PAGE_SIZE))
        page = min(page, pages)
        return page, pages, (page - 1) * PAGE_SIZE

    # ---- dashboard + API ------------------------------------------------------------------
    def _analytics_page(view: str):
        conn = db()
        span = conn.execute("SELECT MIN(order_date), MAX(order_date) FROM orders").fetchone()
        return render_template("dashboard.html", opts=options(conn), view=view,
                               active="overview" if view == "overview" else "service",
                               span=(date.fromisoformat(span[0]), date.fromisoformat(span[1])))

    @app.get("/")
    def dashboard():
        return _analytics_page("overview")

    @app.get("/analytics/customers")
    def dashboard_customers():
        return _analytics_page("customers")

    @app.get("/api/analytics")
    def api_analytics():
        a = request.args
        return jsonify(analytics.compute(db(), a.get("country", ""), a.get("segment", ""), a.get("category", "")))

    @app.get("/api/version")
    def api_version():
        conn = db()
        return jsonify(version=conn.execute("SELECT value FROM meta WHERE key='data_version'").fetchone()[0],
                       orders=conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0])

    @app.get("/api/customers/<customer_id>")
    def api_customer(customer_id):
        r = db().execute(
            """SELECT c.*, COUNT(o.order_id) AS orders FROM customers c
               LEFT JOIN orders o ON o.customer_id = c.customer_id
               WHERE c.customer_id = ? GROUP BY c.customer_id""", (customer_id.strip().upper(),)).fetchone()
        if r is None:
            return jsonify(found=False), 404
        return jsonify(found=True, **dict(r))

    # ---- orders ---------------------------------------------------------------------------
    @app.get("/orders")
    def orders():
        conn = db()
        a = request.args
        where, params = ["1=1"], []
        if q := a.get("q", "").strip():
            where.append("(order_id LIKE ? OR customer_id LIKE ? OR city LIKE ?)")
            params += [f"%{q}%"] * 3
        for col, key in (("order_status", "status"), ("country", "country"), ("product_category", "category")):
            if v := a.get(key, ""):
                where.append(f"{col} = ?")
                params.append(v)
        sort = a.get("sort", "order_date") if a.get("sort") in ORDER_SORTS else "order_date"
        direction = "ASC" if a.get("dir") == "asc" else "DESC"
        W = " AND ".join(where)
        total = conn.execute(f"SELECT COUNT(*) FROM v_orders WHERE {W}", params).fetchone()[0]
        page, pages, offset = page_args(total)
        rows = conn.execute(
            f"""SELECT order_id, order_date, customer_id, country, product_category, quantity, unit_price,
                       discount_pct, total_amount, order_status, review_rating, delivery_days
                FROM v_orders WHERE {W} ORDER BY {sort} {direction}, order_id {direction}
                LIMIT ? OFFSET ?""", [*params, PAGE_SIZE, offset]).fetchall()
        return render_template("orders.html", rows=rows, total=total, page=page, pages=pages, offset=offset,
                               sort=sort, dir=direction.lower(), opts=options(conn), args=a, active="orders",
                               grand_total=conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0])

    def _order_form(order=None, errors=None, form=None):
        conn = db()
        latest = conn.execute("SELECT MAX(order_date) FROM orders").fetchone()[0]
        return render_template("order_form.html", order=order, errors=errors or {}, form=form or {},
                               latest_date=latest, active="orders",
                               customer_ids=[r[0] for r in conn.execute("SELECT customer_id FROM customers ORDER BY 1")])

    @app.route("/orders/new", methods=["GET", "POST"])
    def order_new():
        if request.method == "GET":
            return _order_form()
        conn = db()
        d, errors = validate_order(request.form, conn)
        if errors:
            return _order_form(errors=errors, form=request.form), 422
        d["order_id"] = dbm.next_id(conn, "orders", "order_id", "ORD", 6)
        try:
            with conn:
                conn.execute(f"INSERT INTO orders ({', '.join(d)}) VALUES ({', '.join('?' * len(d))})", list(d.values()))
        except sqlite3.IntegrityError as exc:
            return _order_form(errors={"_": f"The database rejected this order: {exc}"}, form=request.form), 422
        total = conn.execute("SELECT total_amount FROM v_orders WHERE order_id = ?", (d["order_id"],)).fetchone()[0]
        flash(f"Order {d['order_id']} created for ${total:,.2f}.", "success")
        return redirect(url_for("orders", highlight=d["order_id"]))

    @app.route("/orders/<order_id>/edit", methods=["GET", "POST"])
    def order_edit(order_id):
        conn = db()
        order = conn.execute("SELECT * FROM v_orders WHERE order_id = ?", (order_id,)).fetchone()
        if order is None:
            abort(404)
        if request.method == "GET":
            return _order_form(order=order)
        d, errors = validate_order(request.form, conn)
        if errors:
            return _order_form(order=order, errors=errors, form=request.form), 422
        try:
            with conn:
                conn.execute(f"UPDATE orders SET {', '.join(f'{k} = ?' for k in d)} WHERE order_id = ?",
                             [*d.values(), order_id])
        except sqlite3.IntegrityError as exc:
            return _order_form(order=order, errors={"_": f"The database rejected this change: {exc}"}, form=request.form), 422
        flash(f"Order {order_id} updated.", "success")
        return redirect(url_for("orders", highlight=order_id))

    @app.post("/orders/<order_id>/delete")
    def order_delete(order_id):
        conn = db()
        with conn:
            n = conn.execute("DELETE FROM orders WHERE order_id = ?", (order_id,)).rowcount
        flash(f"Order {order_id} deleted." if n else f"Order {order_id} was not found.", "success" if n else "error")
        return redirect(safe_next(request.form.get("next"), url_for("orders")))

    # ---- customers ------------------------------------------------------------------------
    @app.get("/customers")
    def customers():
        conn = db()
        a = request.args
        where, params = ["1=1"], []
        if q := a.get("q", "").strip():
            where.append("(c.customer_id LIKE ? OR c.city LIKE ?)")
            params += [f"%{q}%"] * 2
        for col, key in (("c.country", "country"), ("c.customer_segment", "segment")):
            if v := a.get(key, ""):
                where.append(f"{col} = ?")
                params.append(v)
        sort = a.get("sort") if a.get("sort") in CUSTOMER_SORTS else "spent"
        direction = "ASC" if a.get("dir") == "asc" else "DESC"
        W = " AND ".join(where)
        base = f"""FROM customers c LEFT JOIN v_orders o ON o.customer_id = c.customer_id
                   WHERE {W} GROUP BY c.customer_id"""
        total = conn.execute(f"SELECT COUNT(*) FROM (SELECT c.customer_id {base})", params).fetchone()[0]
        page, pages, offset = page_args(total)
        rows = conn.execute(
            f"""SELECT c.*, COUNT(o.order_id) AS orders, COALESCE(SUM(o.net_revenue), 0) AS spent,
                       MAX(o.order_date) AS last_order
                {base} ORDER BY {sort} {direction}, c.customer_id LIMIT ? OFFSET ?""",
            [*params, PAGE_SIZE, offset]).fetchall()
        return render_template("customers.html", rows=rows, total=total, page=page, pages=pages, offset=offset,
                               sort=sort, dir=direction.lower(), args=a, active="customers",
                               opts=options(conn),
                               grand_total=conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0])

    def _customer_form(customer=None, errors=None, form=None):
        return render_template("customer_form.html", customer=customer, errors=errors or {}, form=form or {},
                               active="customers")

    @app.route("/customers/new", methods=["GET", "POST"])
    def customer_new():
        if request.method == "GET":
            return _customer_form()
        conn = db()
        d, errors = validate_customer(request.form, conn)
        if errors:
            return _customer_form(errors=errors, form=request.form), 422
        d["customer_id"] = dbm.next_id(conn, "customers", "customer_id", "C", 4)
        with conn:
            conn.execute(f"INSERT INTO customers ({', '.join(d)}) VALUES ({', '.join('?' * len(d))})", list(d.values()))
        flash(f"Customer {d['customer_id']} created." + (" Add their first order below." if request.form.get("then") == "order" else ""), "success")
        return redirect(url_for("order_new", customer_id=d["customer_id"]) if request.form.get("then") == "order"
                        else url_for("customers", q=d["customer_id"]))

    @app.route("/customers/<customer_id>/edit", methods=["GET", "POST"])
    def customer_edit(customer_id):
        conn = db()
        customer = conn.execute("SELECT * FROM customers WHERE customer_id = ?", (customer_id,)).fetchone()
        if customer is None:
            abort(404)
        if request.method == "GET":
            return _customer_form(customer=customer)
        d, errors = validate_customer(request.form, conn, customer_id)
        if errors:
            return _customer_form(customer=customer, errors=errors, form=request.form), 422
        with conn:
            conn.execute(f"UPDATE customers SET {', '.join(f'{k} = ?' for k in d)} WHERE customer_id = ?",
                         [*d.values(), customer_id])
        flash(f"Customer {customer_id} updated.", "success")
        return redirect(url_for("customers", q=customer_id))

    @app.post("/customers/<customer_id>/delete")
    def customer_delete(customer_id):
        conn = db()
        try:
            with conn:
                n = conn.execute("DELETE FROM customers WHERE customer_id = ?", (customer_id,)).rowcount
            flash(f"Customer {customer_id} deleted." if n else f"Customer {customer_id} was not found.",
                  "success" if n else "error")
        except sqlite3.IntegrityError:
            cnt = conn.execute("SELECT COUNT(*) FROM orders WHERE customer_id = ?", (customer_id,)).fetchone()[0]
            flash(f"{customer_id} still has {cnt} order{'s' if cnt != 1 else ''}, so it can't be deleted. "
                  f"Delete those orders first.", "error")
        return redirect(safe_next(request.form.get("next"), url_for("customers")))

    # ---- admin ----------------------------------------------------------------------------
    @app.post("/admin/reset")
    def admin_reset():
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()
        report = dbm.build_database(app.config["DATABASE"])
        flash(f"Data restored from the cleaned dataset: {report['orders']:,} orders, {report['customers']:,} customers.",
              "success")
        return redirect(safe_next(request.form.get("next"), url_for("dashboard")))

    @app.errorhandler(404)
    def _404(_e):
        return render_template("error.html", code=404, message="That page or record doesn't exist."), 404

    @app.errorhandler(400)
    def _400(e):
        return render_template("error.html", code=400, message=e.description), 400

    return app


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Run the E-commerce Customer Analytics web app.")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--reset", action="store_true", help="rebuild the database from the cleaned CSV first")
    args = ap.parse_args()
    if args.reset:
        print(dbm.build_database())
    application = create_app()
    print(f"\n  E-commerce Customer Analytics  →  http://{args.host}:{args.port}\n")
    application.run(host=args.host, port=args.port, debug=False)
