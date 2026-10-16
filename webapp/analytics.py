"""
analytics.py
------------
Every number on the dashboard, computed with SQL against the live database.

``compute(conn, country, segment, category)`` returns one JSON-ready dict.
Aggregations (GROUP BY, SUM, AVG, COUNT DISTINCT, CASE bands) run in SQLite;
only the statistics SQLite lacks (median, Pearson r) are finished in Python.
"""

from __future__ import annotations

import math
import sqlite3
from datetime import date, timedelta

BANDS = ["1–3 days", "4–6 days", "7–9 days", "10+ days"]
AGE_GROUPS = ["18-24", "25-34", "35-44", "45-54", "55+"]
HIST_EDGES = [0, 25, 50, 75, 100, 150, 200, 300, 400, 600, 1000, 2000]


def _where(country: str, segment: str, category: str) -> tuple[str, list]:
    clauses, params = [], []
    for col, val in (("country", country), ("customer_segment", segment), ("product_category", category)):
        if val:
            clauses.append(f"{col} = ?")
            params.append(val)
    return "WHERE 1=1" + "".join(f" AND {c}" for c in clauses), params


def compute(conn: sqlite3.Connection, country: str = "", segment: str = "", category: str = "") -> dict:
    W, P = _where(country, segment, category)
    q = lambda sql, extra=(): conn.execute(sql.replace("{W}", W), [*P, *extra]).fetchall()

    total_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    k = q("""SELECT COUNT(*) n, COALESCE(SUM(net_revenue),0) rev, AVG(total_amount) aov,
                    COUNT(DISTINCT customer_id) cust,
                    SUM(order_status='Returned') ret, SUM(order_status='Cancelled') canc,
                    SUM(CASE WHEN order_status<>'Delivered' THEN total_amount ELSE 0 END) refunded
             FROM v_orders {W}""")[0]
    n = k["n"]
    out: dict = {"filters": {"country": country, "segment": segment, "category": category},
                 "total_orders": total_orders, "n": n}
    if n == 0:
        return out

    # ---------------- overview ----------------
    amounts = [r[0] for r in q("SELECT total_amount FROM v_orders {W} ORDER BY total_amount")]
    mid = len(amounts) // 2
    median = amounts[mid] if len(amounts) % 2 else (amounts[mid - 1] + amounts[mid]) / 2
    out["kpis"] = {"orders": n, "revenue": k["rev"], "aov": k["aov"], "median": median,
                   "customers": k["cust"], "return_rate": k["ret"] / n, "cancel_rate": k["canc"] / n,
                   "refunded": k["refunded"]}

    out["category"] = [dict(r) for r in q(
        """SELECT product_category AS k, SUM(net_revenue) AS rev, COUNT(*) AS n,
                  AVG(order_status='Returned') AS return_rate
           FROM v_orders {W} GROUP BY product_category ORDER BY rev DESC""")]
    out["monthly"] = [dict(r) for r in q(
        "SELECT order_month AS m, COUNT(*) AS n, SUM(net_revenue) AS rev FROM v_orders {W} GROUP BY m ORDER BY m")]
    out["histogram"] = {
        "labels": [f"${HIST_EDGES[i]}–{HIST_EDGES[i + 1]}" for i in range(len(HIST_EDGES) - 1)],
        "counts": [sum(HIST_EDGES[i] <= a < HIST_EDGES[i + 1] for a in amounts) for i in range(len(HIST_EDGES) - 1)],
    }
    st = {r["k"]: r["n"] for r in q("SELECT order_status AS k, COUNT(*) AS n FROM v_orders {W} GROUP BY k")}
    out["status"] = [{"k": s, "n": st.get(s, 0)} for s in ("Delivered", "Returned", "Cancelled")]

    # fulfilment funnel: every stage is a subset of the one before it
    f = q("""SELECT COUNT(*) placed, SUM(order_status<>'Cancelled') shipped, SUM(order_status='Delivered') kept,
                    SUM(order_status='Delivered' AND review_rating IS NOT NULL) reviewed FROM v_orders {W}""")[0]
    out["funnel"] = [{"k": "Placed", "n": f["placed"]}, {"k": "Shipped", "n": f["shipped"]},
                     {"k": "Delivered & kept", "n": f["kept"]}, {"k": "Reviewed", "n": f["reviewed"]}]

    out["recent_orders"] = [dict(r) for r in q(
        """SELECT order_id, order_date, customer_id, country, product_category, quantity, total_amount, order_status
           FROM v_orders {W} ORDER BY order_date DESC, order_id DESC LIMIT 6""")]
    events = []
    for r in out["recent_orders"][:5]:
        verb = {"Delivered": "ordered", "Returned": "returned", "Cancelled": "cancelled"}[r["order_status"]]
        events.append({"date": r["order_date"], "kind": r["order_status"].lower(), "who": r["customer_id"],
                       "text": f"{verb} {r['product_category']} · ${r['total_amount']:,.2f}"})
    for r in conn.execute("""SELECT customer_id, signup_date, city, country FROM customers
                             ORDER BY signup_date DESC, customer_id DESC LIMIT 2"""):
        events.append({"date": r["signup_date"], "kind": "signup", "who": r["customer_id"],
                       "text": f"signed up from {r['city']}, {r['country']}"})
    out["activity"] = sorted(events, key=lambda e: e["date"], reverse=True)[:5]

    # ---------------- customers & service ----------------
    seg_rows = {r["k"]: r for r in q(
        """SELECT customer_segment AS k, COUNT(*) AS n, COUNT(DISTINCT customer_id) AS c,
                  AVG(total_amount) AS aov, SUM(net_revenue) AS rev
           FROM v_orders {W} GROUP BY k""")}
    out["segments"] = [{"k": s, "customers": r["c"], "orders": r["n"], "orders_per_customer": r["n"] / r["c"],
                        "aov": r["aov"], "rev_per_customer": r["rev"] / r["c"]}
                       for s in ("New", "Regular", "VIP") if (r := seg_rows.get(s))]

    # Recency is measured from the day after the latest order in the database, so it
    # stays correct as new orders are added.
    last_date = conn.execute("SELECT MAX(order_date) FROM orders").fetchone()[0]
    snapshot = date.fromisoformat(last_date) + timedelta(days=1)
    per_cust = q("""SELECT customer_id, COUNT(*) AS n, MAX(order_date) AS last, SUM(net_revenue) AS spent
                    FROM v_orders {W} GROUP BY customer_id""")
    hi = me = lo = 0
    for r in per_cust:
        days = (snapshot - date.fromisoformat(r["last"])).days
        if days > 180: hi += 1
        elif days > 90: me += 1
        else: lo += 1
    cust = len(per_cust)
    spend = sorted((r["spent"] for r in per_cust), reverse=True)
    top_n = max(1, round(len(spend) * 0.2))
    out["churn"] = {"high": hi, "medium": me, "low": lo, "snapshot": snapshot.isoformat()}
    out["retention"] = {"customers": cust,
                        "repeat_rate": sum(r["n"] > 1 for r in per_cust) / cust,
                        "dormant_share": hi / cust,
                        "top20_share": sum(spend[:top_n]) / (k["rev"] or 1)}

    out["country"] = [dict(r) for r in q(
        """SELECT country AS k, SUM(net_revenue) AS rev, COUNT(DISTINCT customer_id) AS c, COUNT(*) AS n
           FROM v_orders {W} GROUP BY country ORDER BY rev DESC""")]
    out["channel"] = [dict(r) for r in q(
        """SELECT acquisition_channel AS k, SUM(net_revenue) * 1.0 / COUNT(DISTINCT customer_id) AS rpc,
                  COUNT(DISTINCT customer_id) AS c
           FROM v_orders {W} GROUP BY acquisition_channel ORDER BY rpc DESC""")]
    out["rev_per_customer"] = k["rev"] / k["cust"]

    pay = {}
    for r in q("SELECT age_group AS a, payment_method AS p, COUNT(*) AS n FROM v_orders {W} GROUP BY a, p"):
        pay.setdefault(r["a"], {})[r["p"]] = r["n"]
    out["payment_by_age"] = {a: {p: v / sum(pay[a].values()) for p, v in pay[a].items()} for a in AGE_GROUPS if a in pay}

    reviewed = "{W} AND review_rating IS NOT NULL AND delivery_days IS NOT NULL"
    band_rows = {r["band"]: r for r in q(
        f"""SELECT CASE WHEN delivery_days <= 3 THEN '{BANDS[0]}' WHEN delivery_days <= 6 THEN '{BANDS[1]}'
                        WHEN delivery_days <= 9 THEN '{BANDS[2]}' ELSE '{BANDS[3]}' END AS band,
                   AVG(review_rating) AS rating, COUNT(*) AS n
            FROM v_orders {reviewed} GROUP BY band""")}
    out["delivery_bands"] = [{"band": b, "rating": band_rows[b]["rating"] if b in band_rows else None,
                              "n": band_rows[b]["n"] if b in band_rows else 0} for b in BANDS]

    pts = [dict(r) for r in q(f"""SELECT delivery_days AS x, review_rating AS y, COUNT(*) AS c
                                  FROM v_orders {reviewed} GROUP BY x, y""")]
    out["scatter"] = pts
    # weighted Pearson r and least-squares trend line from the grouped points
    N = sum(p["c"] for p in pts)
    if N > 1:
        mx = sum(p["x"] * p["c"] for p in pts) / N
        my = sum(p["y"] * p["c"] for p in pts) / N
        sxy = sum((p["x"] - mx) * (p["y"] - my) * p["c"] for p in pts)
        sxx = sum((p["x"] - mx) ** 2 * p["c"] for p in pts)
        syy = sum((p["y"] - my) ** 2 * p["c"] for p in pts)
        r = sxy / math.sqrt(sxx * syy) if sxx and syy else 0.0
        slope = sxy / sxx if sxx else 0.0
        out["correlation"] = {"r": r, "n": N, "slope": slope, "intercept": my - slope * mx}
    else:
        out["correlation"] = {"r": 0.0, "n": N, "slope": 0.0, "intercept": 0.0}

    out["returns_by_category"] = sorted(
        ({"k": c["k"], "rate": c["return_rate"]} for c in out["category"]), key=lambda d: -d["rate"])

    rs = {r["s"]: r for r in q(
        """SELECT order_status AS s, AVG(review_rating) AS rating, AVG(review_rating <= 2) AS low, COUNT(*) AS n
           FROM v_orders {W} AND review_rating IS NOT NULL AND order_status IN ('Delivered','Returned')
           GROUP BY s""")}
    out["rating_by_status"] = [{"s": s, "rating": rs[s]["rating"] if s in rs else None,
                                "low": rs[s]["low"] if s in rs else None, "n": rs[s]["n"] if s in rs else 0}
                               for s in ("Delivered", "Returned")]
    return out
