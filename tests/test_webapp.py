"""Tests for the Flask + SQLite web app (run with `pytest`)."""
import re
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from webapp import analytics, database  # noqa: E402
from webapp.app import create_app  # noqa: E402


@pytest.fixture()
def client(tmp_path):
    app = create_app(tmp_path / "test.db", testing=True)
    return app.test_client()


def csrf(client, url="/orders/new"):
    return re.search(r'name="_csrf" value="([^"]+)"', client.get(url).get_data(as_text=True)).group(1)


def order_form(token, **over):
    data = dict(_csrf=token, customer_id="C1122", order_date="2025-06-30", product_id="P001",   # Smartphone, $349
                quantity="2", discount_pct="10", shipping_cost="0", payment_method="E-Wallet",
                device_type="Mobile", order_status="Delivered", delivery_days="3", review_rating="5")
    data.update(over)
    return data


# ------------------------------------------------------------------ database
def test_database_matches_cleaned_dataset(tmp_path):
    report = database.build_database(tmp_path / "db.sqlite")
    assert report == {"customers": 723, "orders": 1995, "products": 60, "customers_with_conflicting_attributes": 71}
    conn = database.connect(tmp_path / "db.sqlite")
    rev, aov = conn.execute("SELECT SUM(net_revenue), AVG(total_amount) FROM v_orders").fetchone()
    assert round(rev) == 148675 and round(aov, 2) == 91.90
    # stock in the database equals the catalogue snapshot (history is loaded before the stock triggers)
    assert conn.execute("SELECT stock_on_hand FROM products WHERE product_id = 'P001'").fetchone()[0] == 30


@pytest.mark.parametrize("sql", [
    "INSERT INTO orders VALUES ('X','2025-01-01','C1122','P036',0,9,0,0,'PayPal','Mobile','Delivered',3,5)",       # qty 0
    "INSERT INTO orders VALUES ('X','2025-01-01','C1122','P036',1,9,0,0,'PayPal','Mobile','Delivered',3,7)",       # rating 7
    "INSERT INTO orders VALUES ('X','2025-01-01','NOBODY','P036',1,9,0,0,'PayPal','Mobile','Delivered',3,5)",      # unknown customer
    "INSERT INTO orders VALUES ('X','2025-01-01','C1122','P999',1,9,0,0,'PayPal','Mobile','Delivered',3,5)",       # unknown product
    "INSERT INTO orders VALUES ('X','2025-01-01','C1122','P036',1,9,0,0,'PayPal','Mobile','Cancelled',3,NULL)",    # cancelled w/ delivery
    "INSERT INTO orders VALUES ('X','2025-01-01','C1122','P001',31,349,0,0,'PayPal','Mobile','Delivered',3,5)",    # more than the 30 in stock
    "UPDATE products SET stock_on_hand = -1 WHERE product_id = 'P001'",                                          # negative stock
    "DELETE FROM customers WHERE customer_id = 'C1122'",                                                         # has orders
    "DELETE FROM products WHERE product_id = 'P036'",                                                            # on orders
])
def test_database_constraints_reject_invalid_data(tmp_path, sql):
    database.build_database(tmp_path / "db.sqlite")
    conn = database.connect(tmp_path / "db.sqlite")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql)


def test_analytics_reproduces_notebook_findings(tmp_path):
    database.build_database(tmp_path / "db.sqlite")
    a = analytics.compute(database.connect(tmp_path / "db.sqlite"))
    assert a["n"] == 1995 and a["kpis"]["median"] == pytest.approx(49.54)
    assert a["category"][0]["k"] == "Electronics"
    assert a["correlation"]["r"] == pytest.approx(-0.406, abs=0.001)
    assert a["retention"]["repeat_rate"] == pytest.approx(0.672, abs=0.001)
    assert [round(b["rating"], 2) for b in a["delivery_bands"]] == [3.97, 3.68, 3.29, 3.00]


# ------------------------------------------------------------------ pages & API
@pytest.mark.parametrize("url", ["/", "/analytics/customers", "/orders", "/customers", "/orders/new", "/customers/new",
                                 "/orders?q=C1122&sort=total_amount&dir=asc", "/orders/ORD100305/edit",
                                 "/products", "/products?stock=low&sort=revenue&dir=desc", "/products/new",
                                 "/products/P001/edit", "/orders/new?product_id=P036"])
def test_pages_render(client, url):
    assert client.get(url).status_code == 200


def test_api_filters(client):
    assert client.get("/api/analytics").get_json()["n"] == 1995
    assert client.get("/api/analytics?country=Cambodia").get_json()["n"] == 623
    assert client.get("/api/analytics?country=Atlantis").get_json()["n"] == 0


# ------------------------------------------------------------------ CRUD
def test_add_order_updates_dashboard(client):
    before = client.get("/api/analytics").get_json()
    v0 = client.get("/api/version").get_json()["version"]
    r = client.post("/orders/new", data=order_form(csrf(client)))
    assert r.status_code == 302
    after = client.get("/api/analytics").get_json()
    assert after["n"] == before["n"] + 1
    assert after["kpis"]["revenue"] == pytest.approx(before["kpis"]["revenue"] + 628.2)  # 2 × $349 × 0.9
    assert client.get("/api/version").get_json()["version"] > v0


def test_invalid_order_is_rejected_with_field_errors(client):
    n = client.get("/api/analytics").get_json()["n"]
    r = client.post("/orders/new", data=order_form(csrf(client), quantity="0", customer_id="C9999"))
    assert r.status_code == 422
    errs = re.findall(r'class="err">([^<]+)', r.get_data(as_text=True))
    assert any("Quantity" in e for e in errs) and any("C9999" in e for e in errs)
    assert client.get("/api/analytics").get_json()["n"] == n


def test_order_before_signup_is_rejected(client):
    r = client.post("/orders/new", data=order_form(csrf(client), order_date="2020-01-01"))
    assert r.status_code == 422 and b"signed up" in r.data


def test_future_order_date_is_rejected(client):
    r = client.post("/orders/new", data=order_form(csrf(client), order_date="2062-01-01"))
    assert r.status_code == 422 and b"in the future" in r.data
    assert client.get("/api/analytics").get_json()["n"] == 1995


def test_monthly_trend_shows_empty_months_as_zero(client):
    client.post("/orders/new", data=order_form(csrf(client), order_date="2025-09-15"))
    m = client.get("/api/analytics").get_json()["monthly"]
    assert [r["m"] for r in m[-4:]] == ["2025-06", "2025-07", "2025-08", "2025-09"]
    assert m[-3]["n"] == m[-2]["n"] == 0 and m[-1]["n"] == 1


def test_fill_months_crosses_year_end():
    rows = [{"m": "2024-11", "n": 2, "rev": 5.0}, {"m": "2025-02", "n": 1, "rev": 3.0}]
    assert [r["m"] for r in analytics._fill_months(rows)] == ["2024-11", "2024-12", "2025-01", "2025-02"]


def test_new_record_id_clash_is_retried(tmp_path, monkeypatch):
    from webapp import app as app_module
    database.build_database(tmp_path / "db.sqlite")
    conn = database.connect(tmp_path / "db.sqlite")
    taken = database.next_id(conn, "products", "product_id", "P", 3)
    ids = iter([taken, None])   # first attempt returns an ID another request already used
    real = database.next_id
    with conn:   # another request saves a product under that ID first
        conn.execute("INSERT INTO products VALUES (?, 'Racer', 'Toys', 'Cars', 9.0, 5, 1)", (taken,))
    monkeypatch.setattr(app_module.dbm, "next_id", lambda *a: next(ids) or real(*a))
    d = dict(product_name="Racer 2", category="Toys", subcategory="Cars", unit_price=9.0, stock_on_hand=5, reorder_level=1)
    new = app_module.insert_with_new_id(conn, "products", "product_id", "P", 3, d)
    assert new != taken and conn.execute("SELECT product_name FROM products WHERE product_id = ?", (new,)).fetchone()[0] == "Racer 2"


def test_edit_to_returned_removes_net_revenue(client):
    t = csrf(client)
    base = client.get("/api/analytics").get_json()["kpis"]["revenue"]
    client.post("/orders/new", data=order_form(t))
    client.post("/orders/ORD102000/edit", data=order_form(t, order_status="Returned"))
    assert client.get("/api/analytics").get_json()["kpis"]["revenue"] == pytest.approx(base)


def test_delete_order(client):
    t = csrf(client)
    client.post("/orders/new", data=order_form(t))
    client.post("/orders/ORD102000/delete", data={"_csrf": t})
    assert client.get("/api/analytics").get_json()["n"] == 1995


def test_customer_with_orders_cannot_be_deleted(client):
    r = client.post("/customers/C1122/delete", data={"_csrf": csrf(client)}, follow_redirects=True)
    assert b"still has" in r.data
    assert client.get("/api/customers/C1122").status_code == 200


def test_new_customer_then_first_order(client):
    t = csrf(client)
    r = client.post("/customers/new", data=dict(_csrf=t, age="29", gender="Female", country="Cambodia", city="Kampot",
                                                signup_date="2025-01-10", customer_segment="New",
                                                acquisition_channel="Email", then="order"))
    assert r.status_code == 302 and "customer_id=C1840" in r.headers["Location"]
    assert client.post("/orders/new", data=order_form(t, customer_id="C1840")).status_code == 302


# ------------------------------------------------------------------ security & admin
def test_post_without_csrf_token_is_refused(client):
    assert client.post("/orders/new", data=order_form("forged")).status_code == 400


def test_next_parameter_cannot_redirect_off_site(client):
    r = client.post("/orders/ORD100305/delete", data={"_csrf": csrf(client), "next": "https://evil.example/"})
    assert r.headers["Location"].startswith("/")


def test_reset_restores_original_data(client):
    t = csrf(client)
    client.post("/orders/new", data=order_form(t))
    v = client.get("/api/version").get_json()["version"]
    client.post("/admin/reset", data={"_csrf": t})
    assert client.get("/api/analytics").get_json()["n"] == 1995
    assert client.get("/api/version").get_json()["version"] > v


def test_dashboard_widgets_data(client):
    a = client.get("/api/analytics").get_json()
    f = [s["n"] for s in a["funnel"]]
    assert f[0] == 1995 and f[0] >= f[1] >= f[2] >= f[3] > 0   # each stage is a subset of the previous one
    assert len(a["recent_orders"]) == 6 and a["recent_orders"][0]["order_date"] == "2025-06-30"
    assert sum(c["c"] for c in a["channel"]) == a["kpis"]["customers"]
    assert b"sea-map" in client.get("/").data


# ------------------------------------------------------------------ products, price and stock
def stock(client, pid):
    return int(re.search(rf'id="stock_on_hand" name="stock_on_hand" value="(\d+)"',
                         client.get(f"/products/{pid}/edit").get_data(as_text=True)).group(1))


def test_price_comes_from_catalogue_not_the_form(client):
    r = client.post("/orders/new", data=order_form(csrf(client), unit_price="0.01", quantity="1", discount_pct="0"))
    assert r.status_code == 302
    o = client.get("/api/analytics").get_json()["recent_orders"][0]
    assert o["product_name"] == "Smartphone A54 128GB" and o["total_amount"] == pytest.approx(349.0)


def test_delivered_order_takes_stock_and_cancel_returns_it(client):
    t = csrf(client)
    assert stock(client, "P001") == 30
    client.post("/orders/new", data=order_form(t, quantity="3"))
    assert stock(client, "P001") == 27
    client.post("/orders/ORD102000/edit", data=order_form(t, quantity="3", order_status="Cancelled",
                                                          delivery_days="", review_rating=""))
    assert stock(client, "P001") == 30
    client.post("/orders/ORD102000/edit", data=order_form(t, quantity="5"))
    assert stock(client, "P001") == 25
    client.post("/orders/ORD102000/delete", data={"_csrf": t})
    assert stock(client, "P001") == 30


def test_order_for_more_than_stock_is_rejected(client):
    r = client.post("/orders/new", data=order_form(csrf(client), quantity="31"))
    assert r.status_code == 422
    errs = re.findall(r'class="err">([^<]+)', r.get_data(as_text=True))
    assert any("Only 30 units" in e for e in errs)
    r = client.post("/orders/new", data=order_form(csrf(client), product_id="P004", quantity="1"))   # sold out
    assert r.status_code == 422 and b"out of stock" in r.data
    assert stock(client, "P001") == 30


def test_editing_an_order_can_reuse_its_own_units(client):
    t = csrf(client)
    client.post("/orders/new", data=order_form(t, quantity="30"))          # takes all 30
    assert stock(client, "P001") == 0
    assert client.post("/orders/ORD102000/edit", data=order_form(t, quantity="30")).status_code == 302
    assert client.post("/orders/ORD102000/edit", data=order_form(t, quantity="31")).status_code == 422


def test_add_and_restock_product(client):
    t = csrf(client, "/products/new")
    r = client.post("/products/new", data=dict(_csrf=t, product_name="Comic Anthology", category="Books",
                                               subcategory="Comics & Manga", unit_price="20", stock_on_hand="5",
                                               reorder_level="2"))
    assert r.status_code == 302
    assert client.post("/orders/new", data=order_form(t, product_id="P061", quantity="6")).status_code == 422
    client.post("/products/P061/edit", data=dict(_csrf=t, product_name="Comic Anthology", category="Books",
                                                 subcategory="Comics & Manga", unit_price="20", stock_on_hand="50",
                                                 reorder_level="2"))
    assert client.post("/orders/new", data=order_form(t, product_id="P061", quantity="6", discount_pct="0")).status_code == 302
    assert client.get("/api/analytics").get_json()["recent_orders"][0]["total_amount"] == pytest.approx(120.0)
    assert stock(client, "P061") == 44


def test_product_on_orders_cannot_be_deleted(client):
    r = client.post("/products/P036/delete", data={"_csrf": csrf(client)}, follow_redirects=True)
    assert b"can&#39;t be deleted" in r.data or b"can't be deleted" in r.data
