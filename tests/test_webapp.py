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
    data = dict(_csrf=token, customer_id="C1122", order_date="2025-06-30", product_category="Electronics",
                quantity="2", unit_price="250", discount_pct="10", shipping_cost="0", payment_method="E-Wallet",
                device_type="Mobile", order_status="Delivered", delivery_days="3", review_rating="5")
    data.update(over)
    return data


# ------------------------------------------------------------------ database
def test_database_matches_cleaned_dataset(tmp_path):
    report = database.build_database(tmp_path / "db.sqlite")
    assert report == {"customers": 721, "orders": 1972, "customers_with_conflicting_attributes": 69}
    conn = database.connect(tmp_path / "db.sqlite")
    rev, aov = conn.execute("SELECT SUM(net_revenue), AVG(total_amount) FROM v_orders").fetchone()
    assert round(rev) == 227155 and round(aov, 2) == 136.47


@pytest.mark.parametrize("sql", [
    "INSERT INTO orders VALUES ('X','2025-01-01','C1122','Books',0,10,0,0,'PayPal','Mobile','Delivered',3,5)",      # qty 0
    "INSERT INTO orders VALUES ('X','2025-01-01','C1122','Books',1,10,0,0,'PayPal','Mobile','Delivered',3,7)",      # rating 7
    "INSERT INTO orders VALUES ('X','2025-01-01','NOBODY','Books',1,10,0,0,'PayPal','Mobile','Delivered',3,5)",     # unknown customer
    "INSERT INTO orders VALUES ('X','2025-01-01','C1122','Books',1,10,0,0,'PayPal','Mobile','Cancelled',3,NULL)",   # cancelled w/ delivery
    "DELETE FROM customers WHERE customer_id = 'C1122'",                                                         # has orders
])
def test_database_constraints_reject_invalid_data(tmp_path, sql):
    database.build_database(tmp_path / "db.sqlite")
    conn = database.connect(tmp_path / "db.sqlite")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql)


def test_analytics_reproduces_notebook_findings(tmp_path):
    database.build_database(tmp_path / "db.sqlite")
    a = analytics.compute(database.connect(tmp_path / "db.sqlite"))
    assert a["n"] == 1972 and a["kpis"]["median"] == pytest.approx(75.73)
    assert a["category"][0]["k"] == "Electronics"
    assert a["correlation"]["r"] == pytest.approx(-0.378, abs=0.001)
    assert a["retention"]["repeat_rate"] == pytest.approx(0.671, abs=0.001)
    assert [round(b["rating"], 2) for b in a["delivery_bands"]] == [3.96, 3.65, 3.34, 3.02]


# ------------------------------------------------------------------ pages & API
@pytest.mark.parametrize("url", ["/", "/orders", "/customers", "/orders/new", "/customers/new",
                                 "/orders?q=C1122&sort=total_amount&dir=asc", "/orders/ORD100305/edit"])
def test_pages_render(client, url):
    assert client.get(url).status_code == 200


def test_api_filters(client):
    assert client.get("/api/analytics").get_json()["n"] == 1972
    assert client.get("/api/analytics?country=Cambodia").get_json()["n"] == 616
    assert client.get("/api/analytics?country=Atlantis").get_json()["n"] == 0


# ------------------------------------------------------------------ CRUD
def test_add_order_updates_dashboard(client):
    before = client.get("/api/analytics").get_json()
    v0 = client.get("/api/version").get_json()["version"]
    r = client.post("/orders/new", data=order_form(csrf(client)))
    assert r.status_code == 302
    after = client.get("/api/analytics").get_json()
    assert after["n"] == before["n"] + 1
    assert after["kpis"]["revenue"] == pytest.approx(before["kpis"]["revenue"] + 450.0)  # 2 × 250 × 0.9
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
    assert client.get("/api/analytics").get_json()["n"] == 1972


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
    assert client.get("/api/analytics").get_json()["n"] == 1972
    assert client.get("/api/version").get_json()["version"] > v


def test_dashboard_widgets_data(client):
    a = client.get("/api/analytics").get_json()
    f = [s["n"] for s in a["funnel"]]
    assert f[0] == 1972 and f[0] >= f[1] >= f[2] >= f[3] > 0   # each stage is a subset of the previous one
    assert len(a["recent_orders"]) == 6 and a["recent_orders"][0]["order_date"] == "2025-06-30"
    assert sum(c["c"] for c in a["channel"]) == a["kpis"]["customers"]
    assert b"sea-map" in client.get("/").data
