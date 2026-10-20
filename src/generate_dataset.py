"""
generate_dataset.py
-------------------
Generates a realistic synthetic e-commerce dataset for the
"E-commerce Customer Analytics" project: a product catalogue
(category -> subcategory -> product, each with a fixed price and stock on hand)
and the orders placed against it.

The generator deliberately injects data-quality problems (missing values,
exact duplicate rows, out-of-range values and inconsistent categories) so
that the cleaning, validation and analysis steps in the notebook have
realistic work to do.

Usage:
    python src/generate_dataset.py            # writes data/raw/ecommerce_orders_raw.csv + data/raw/products.csv
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
# Product catalogue: category -> subcategory -> [(product name, fixed unit price USD, popularity weight)]
# Prices are list prices; every order of a product is charged this price (discounts are applied on top).
CATALOGUE = {
    "Electronics": {
        "Phones & Tablets": [("Smartphone A54 128GB", 349.00, 1.6), ("10-inch Android Tablet", 229.00, 1.0)],
        "Audio": [("Wireless Earbuds", 59.00, 3.0), ("Noise-Cancelling Headphones", 149.00, 1.2), ("Bluetooth Speaker", 45.00, 2.2)],
        "Computers": [("14-inch Laptop", 649.00, 0.6), ("Mechanical Keyboard", 79.00, 1.4), ("Wireless Mouse", 19.00, 2.6)],
        "Accessories": [("Smartwatch", 129.00, 1.5), ("65W USB-C Charger", 29.00, 2.4), ("20000mAh Power Bank", 35.00, 2.4)],
    },
    "Fashion": {
        "Men's Clothing": [("Cotton Crew T-Shirt", 15.00, 3.0), ("Slim-Fit Denim Jeans", 45.00, 1.8), ("Leather Belt", 25.00, 1.2)],
        "Women's Clothing": [("Floral Summer Dress", 39.00, 2.2), ("Linen Blouse", 29.00, 2.0)],
        "Footwear": [("Running Sneakers", 79.00, 1.5), ("Casual Sandals", 24.00, 1.6)],
        "Bags & Accessories": [("Canvas Backpack", 42.00, 1.4), ("Polarised Sunglasses", 35.00, 1.2), ("Leather Wallet", 32.00, 1.0)],
    },
    "Home & Kitchen": {
        "Cookware": [("Non-Stick Frying Pan", 34.00, 2.0), ("Stainless Steel Pot Set", 89.00, 1.0)],
        "Small Appliances": [("4L Air Fryer", 119.00, 1.6), ("Electric Kettle", 29.00, 2.0), ("Personal Blender", 59.00, 1.3), ("Rice Cooker 1.8L", 69.00, 1.2)],
        "Home Decor": [("LED Table Lamp", 39.00, 1.3), ("Cushion Cover Set", 22.00, 1.4)],
        "Storage": [("Glass Food Container Set", 24.00, 1.6)],
    },
    "Beauty": {
        "Skincare": [("Sunscreen SPF50", 14.00, 2.6), ("Daily Moisturiser", 22.00, 2.0), ("Vitamin C Serum", 28.00, 1.6)],
        "Makeup": [("Matte Lipstick", 15.00, 2.0), ("Liquid Foundation", 26.00, 1.4)],
        "Hair Care": [("Herbal Shampoo", 9.00, 2.2), ("Ionic Hair Dryer", 49.00, 0.9)],
        "Fragrance": [("Eau de Parfum 50ml", 65.00, 0.8)],
    },
    "Sports": {
        "Fitness": [("Yoga Mat", 25.00, 2.2), ("Adjustable Dumbbells 10kg", 59.00, 1.3), ("Resistance Band Set", 15.00, 2.0)],
        "Outdoor": [("2-Person Camping Tent", 129.00, 0.8), ("Hiking Backpack 40L", 79.00, 1.0)],
        "Team Sports": [("Size 5 Football", 22.00, 1.6), ("Badminton Racket", 35.00, 1.6)],
        "Cycling": [("Cycling Helmet", 45.00, 1.0)],
    },
    "Books": {
        "Comics & Manga": [("Manga Volume 1", 9.00, 2.6), ("Superhero Graphic Novel", 22.00, 1.4)],
        "Programming": [("Python Programming for Beginners", 39.00, 1.3), ("Data Science Handbook", 45.00, 0.9)],
        "Fiction": [("Mystery Novel", 14.00, 2.0), ("Fantasy Novel", 16.00, 1.8)],
        "Self-Help": [("Productivity Habits", 15.00, 1.4)],
        "Children's": [("Illustrated Picture Book", 8.00, 1.6)],
    },
    "Toys": {
        "Building Sets": [("Building Blocks Set 500pc", 49.00, 1.4)],
        "Plush": [("Plush Teddy Bear", 18.00, 2.2)],
        "Remote Control": [("RC Off-Road Car", 39.00, 1.4)],
        "Games & Puzzles": [("1000-Piece Jigsaw Puzzle", 19.00, 1.6), ("Family Board Game", 29.00, 1.6)],
        "Arts & Crafts": [("Art & Craft Kit", 15.00, 1.6)],
    },
}
CATEGORY_RETURN_RATE = {"Electronics": 0.09, "Fashion": 0.16, "Home & Kitchen": 0.07, "Beauty": 0.05,
                        "Sports": 0.08, "Books": 0.03, "Toys": 0.06}


def build_catalogue(seed: int = 42) -> pd.DataFrame:
    """One row per product with a fixed price and the stock on hand at the end of the data period."""
    rng = np.random.default_rng(seed + 7)
    rows, i = [], 1
    for cat, subs in CATALOGUE.items():
        for sub, items in subs.items():
            for name, price, pop in items:
                rows.append({"product_id": f"P{i:03d}", "product_name": name, "category": cat,
                             "subcategory": sub, "unit_price": price, "popularity": pop})
                i += 1
    cat_df = pd.DataFrame(rows)
    stock = rng.integers(25, 160, len(cat_df))
    low = rng.choice(len(cat_df), size=6, replace=False)          # a few items running low ...
    stock[low[:4]] = rng.integers(2, 10, 4)
    stock[low[4:]] = 0                                            # ... and two sold out
    cat_df["stock_on_hand"] = stock
    cat_df["reorder_level"] = 10
    return cat_df


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
def generate(rows: int = 2000, seed: int = 42, catalogue: pd.DataFrame | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    catalogue = build_catalogue(seed) if catalogue is None else catalogue

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

    # category first (same mix as before), then a product within it weighted by popularity
    categories = rng.choice(list(CATALOGUE), size=rows,
                            p=[0.24, 0.22, 0.16, 0.12, 0.10, 0.09, 0.07])
    prod_idx = np.empty(rows, dtype=int)
    for c in CATALOGUE:
        members = np.flatnonzero(catalogue["category"].to_numpy() == c)
        w = catalogue["popularity"].to_numpy()[members]
        sel = np.flatnonzero(categories == c)
        prod_idx[sel] = rng.choice(members, size=len(sel), p=w / w.sum())
    product = catalogue.iloc[prod_idx].reset_index(drop=True)
    unit_price = product["unit_price"].to_numpy()          # fixed catalogue price
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
    ret_rate = np.array([CATEGORY_RETURN_RATE[c] for c in categories])
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
        "product_id": product["product_id"].to_numpy(),
        "product_name": product["product_name"].to_numpy(),
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
    idx = rng.choice(n, size=10, replace=False)
    df.loc[idx, "product_name"] = df.loc[idx, "product_name"].str.upper() + "  "
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

    catalogue = build_catalogue(args.seed)
    df = inject_quality_issues(generate(args.rows, args.seed, catalogue), args.seed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, date_format="%Y-%m-%d")
    print(f"Wrote {len(df):,} rows x {df.shape[1]} columns -> {out}")
    cat_out = out.parent / "products.csv"
    catalogue.drop(columns="popularity").to_csv(cat_out, index=False)
    print(f"Wrote {len(catalogue)} products -> {cat_out}")


if __name__ == "__main__":
    main()
