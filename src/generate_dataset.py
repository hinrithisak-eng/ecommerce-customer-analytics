"""
generate_dataset.py
-------------------
Generates a realistic synthetic e-commerce order dataset for the
"E-commerce Customer Analytics" project.

The generator deliberately injects data-quality problems (missing values,
exact duplicate rows, out-of-range values and inconsistent categories) so
that the cleaning, validation and analysis steps in the notebook have
realistic work to do.

Usage:
    python src/generate_dataset.py            # writes data/raw/ecommerce_orders_raw.csv
    python src/generate_dataset.py --rows 3000 --seed 7
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
CATEGORIES = {
    # category: (mean unit price, price std, base return rate)
    "Electronics":   (185.0, 120.0, 0.09),
    "Fashion":       (48.0,  30.0,  0.16),
    "Home & Kitchen": (72.0, 45.0,  0.07),
    "Beauty":        (32.0,  18.0,  0.05),
    "Sports":        (65.0,  40.0,  0.08),
    "Books":         (18.0,   8.0,  0.03),
    "Toys":          (35.0,  20.0,  0.06),
}

COUNTRIES = {
    "Cambodia": 0.30, "Thailand": 0.18, "Vietnam": 0.17,
    "Singapore": 0.12, "Malaysia": 0.10, "Philippines": 0.08, "Indonesia": 0.05,
}
CITIES = {
    "Cambodia": ["Phnom Penh", "Siem Reap", "Battambang", "Sihanoukville"],
    "Thailand": ["Bangkok", "Chiang Mai", "Phuket"],
    "Vietnam": ["Ho Chi Minh City", "Hanoi", "Da Nang"],
    "Singapore": ["Singapore"],
    "Malaysia": ["Kuala Lumpur", "Penang", "Johor Bahru"],
    "Philippines": ["Manila", "Cebu", "Davao"],
    "Indonesia": ["Jakarta", "Surabaya", "Bandung"],
}
SEGMENTS = {"New": 0.35, "Regular": 0.45, "VIP": 0.20}
PAYMENTS = {"Credit Card": 0.34, "E-Wallet": 0.30, "Bank Transfer": 0.16,
            "Cash on Delivery": 0.15, "PayPal": 0.05}
DEVICES = {"Mobile": 0.58, "Desktop": 0.32, "Tablet": 0.10}
CHANNELS = {"Organic Search": 0.28, "Social Media": 0.27, "Email": 0.15,
            "Paid Ads": 0.20, "Referral": 0.10}
STATUSES = {"Delivered": 0.86, "Cancelled": 0.07, "Returned": 0.07}


def _choice(rng, mapping: dict, size: int):
    keys = list(mapping)
    probs = np.array([mapping[k] for k in keys], dtype=float)
    probs /= probs.sum()
    return rng.choice(keys, size=size, p=probs)


# --------------------------------------------------------------------------- #
# Core generator
# --------------------------------------------------------------------------- #
def generate(rows: int = 2000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    # ---- customers -------------------------------------------------------- #
    n_customers = int(rows * 0.42)  # ~2.4 orders per customer on average
    cust_ids = np.array([f"C{1000 + i}" for i in range(n_customers)])
    cust_age = np.clip(rng.normal(34, 11, n_customers).round(), 18, 72).astype(int)
    cust_gender = rng.choice(["Female", "Male"], size=n_customers, p=[0.54, 0.46])
    cust_country = _choice(rng, COUNTRIES, n_customers)
    cust_city = np.array([rng.choice(CITIES[c]) for c in cust_country])
    cust_segment = _choice(rng, SEGMENTS, n_customers)
    cust_channel = _choice(rng, CHANNELS, n_customers)
    signup_start = pd.Timestamp("2022-01-01")
    cust_signup = signup_start + pd.to_timedelta(rng.integers(0, 1000, n_customers), unit="D")

    # order propensity: VIP customers buy more often
    weight = np.where(cust_segment == "VIP", 3.2, np.where(cust_segment == "Regular", 1.6, 0.8))
    weight = weight / weight.sum()
    order_cust_idx = rng.choice(n_customers, size=rows, p=weight)

    # ---- orders ----------------------------------------------------------- #
    order_ids = [f"ORD{100000 + i}" for i in range(rows)]
    # order dates: 2024-01-01 .. 2025-06-30, with seasonal weighting (Nov/Dec peaks)
    date_range = pd.date_range("2024-01-01", "2025-06-30", freq="D")
    month_w = np.array([0.8, 0.8, 0.9, 0.95, 1.0, 1.0, 1.05, 1.0, 1.05, 1.1, 1.45, 1.6])
    dw = np.array([month_w[d.month - 1] for d in date_range])
    dw /= dw.sum()
    order_dates = rng.choice(date_range, size=rows, p=dw)
    order_dates = pd.to_datetime(order_dates)
    # make sure order date is after signup date
    signup_for_order = cust_signup[order_cust_idx]
    order_dates = np.maximum(order_dates, signup_for_order + pd.Timedelta(days=1))

    categories = rng.choice(list(CATEGORIES), size=rows,
                            p=[0.24, 0.22, 0.16, 0.12, 0.10, 0.09, 0.07])
    unit_price = np.array([
        max(3.0, rng.normal(CATEGORIES[c][0], CATEGORIES[c][1])) for c in categories
    ]).round(2)
    quantity = rng.choice([1, 2, 3, 4, 5], size=rows, p=[0.55, 0.25, 0.11, 0.06, 0.03])
    seg_for_order = cust_segment[order_cust_idx]
    # VIP customers receive slightly bigger discounts
    discount = rng.choice([0, 5, 10, 15, 20, 25, 30], size=rows,
                          p=[0.42, 0.18, 0.15, 0.10, 0.08, 0.04, 0.03]).astype(float)
    discount = np.where((seg_for_order == "VIP") & (rng.random(rows) < 0.3), discount + 5, discount)
    shipping_cost = np.where(unit_price * quantity > 120, 0.0,
                             rng.choice([2.99, 4.99, 6.99, 9.99], size=rows)).round(2)
    payment = _choice(rng, PAYMENTS, rows)
    device = _choice(rng, DEVICES, rows)
    status = _choice(rng, STATUSES, rows)
    # returns depend on category
    ret_rate = np.array([CATEGORIES[c][2] for c in categories])
    status = np.where((status == "Delivered") & (rng.random(rows) < ret_rate * 0.6), "Returned", status)

    delivery_days = rng.integers(1, 12, size=rows).astype(float)
    delivery_days = np.where(status == "Cancelled", np.nan, delivery_days)

    # review rating: correlated (negatively) with delivery time, slightly with returns
    base = 4.4 - 0.12 * np.nan_to_num(delivery_days, nan=5) + rng.normal(0, 0.7, rows)
    base = np.where(status == "Returned", base - 1.2, base)
    rating = np.clip(base.round(), 1, 5)
    # only ~68% of delivered/returned orders leave a review
    rating = np.where(rng.random(rows) < 0.32, np.nan, rating)
    rating = np.where(status == "Cancelled", np.nan, rating)

    df = pd.DataFrame({
        "order_id": order_ids,
        "order_date": order_dates,
        "customer_id": cust_ids[order_cust_idx],
        "age": cust_age[order_cust_idx],
        "gender": cust_gender[order_cust_idx],
        "country": cust_country[order_cust_idx],
        "city": cust_city[order_cust_idx],
        "signup_date": signup_for_order,
        "customer_segment": seg_for_order,
        "acquisition_channel": cust_channel[order_cust_idx],
        "product_category": categories,
        "quantity": quantity,
        "unit_price": unit_price,
        "discount_pct": discount,
        "shipping_cost": shipping_cost,
        "payment_method": payment,
        "device_type": device,
        "delivery_days": delivery_days,
        "order_status": status,
        "review_rating": rating,
    })
    df = df.sort_values("order_date").reset_index(drop=True)
    df["order_id"] = [f"ORD{100000 + i}" for i in range(len(df))]
    return df


# --------------------------------------------------------------------------- #
# Deliberate data-quality problems
# --------------------------------------------------------------------------- #
def inject_quality_issues(df: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed + 1)
    df = df.copy()
    n = len(df)

    # 1) Missing values
    df.loc[rng.choice(n, size=int(n * 0.03), replace=False), "age"] = np.nan
    df.loc[rng.choice(n, size=int(n * 0.02), replace=False), "payment_method"] = np.nan
    df.loc[rng.choice(n, size=int(n * 0.015), replace=False), "city"] = np.nan
    df.loc[rng.choice(n, size=int(n * 0.01), replace=False), "unit_price"] = np.nan

    # 2) Invalid values
    idx = rng.choice(n, size=6, replace=False)
    df.loc[idx[:3], "age"] = [-5, 150, 210]            # impossible ages
    df.loc[idx[3:], "age"] = [0, 130, -1]
    idx = rng.choice(n, size=5, replace=False)
    df.loc[idx, "quantity"] = [0, -2, 0, -1, 0]        # non-positive quantity
    idx = rng.choice(n, size=4, replace=False)
    df.loc[idx, "discount_pct"] = [110, 150, -10, 120] # discount outside 0-100
    idx = rng.choice(n, size=4, replace=False)
    df.loc[idx, "review_rating"] = [6, 0, 7, 6]        # rating outside 1-5
    idx = rng.choice(n, size=3, replace=False)
    df.loc[idx, "unit_price"] = [-20.0, -5.5, -100.0]  # negative price
    idx = rng.choice(n, size=3, replace=False)
    df.loc[idx, "delivery_days"] = [45, 60, -3]        # implausible delivery time

    # 3) Inconsistent category spelling / whitespace
    idx = rng.choice(n, size=25, replace=False)
    df.loc[idx, "product_category"] = df.loc[idx, "product_category"].str.lower()
    idx = rng.choice(n, size=15, replace=False)
    df.loc[idx, "product_category"] = " " + df.loc[idx, "product_category"] + " "
    idx = rng.choice(n, size=12, replace=False)
    df.loc[idx, "gender"] = df.loc[idx, "gender"].map({"Female": "F", "Male": "M"})

    # 4) Exact duplicate rows (e.g., double export)
    dup_rows = df.sample(45, random_state=seed)
    df = pd.concat([df, dup_rows], ignore_index=True)
    # Shuffle so duplicates aren't all at the bottom
    df = df.sample(frac=1, random_state=seed).reset_index(drop=True)
    return df


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic e-commerce dataset.")
    parser.add_argument("--rows", type=int, default=2000, help="number of clean orders to generate")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=str, default="data/raw/ecommerce_orders_raw.csv")
    args = parser.parse_args()

    df = inject_quality_issues(generate(args.rows, args.seed), args.seed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, date_format="%Y-%m-%d")
    print(f"Wrote {len(df):,} rows x {df.shape[1]} columns -> {out}")


if __name__ == "__main__":
    main()
