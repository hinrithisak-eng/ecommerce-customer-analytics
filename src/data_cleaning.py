"""
data_cleaning.py
----------------
Reusable cleaning pipeline for the E-commerce Customer Analytics project.

Steps (mirroring the notebook):
    1. Load raw CSV with parsed dates
    2. Standardise categorical text (case / whitespace / abbreviations)
    3. Remove exact duplicate rows
    4. Validate value ranges and fix / drop invalid records
    5. Impute missing values (median / mode) with documented rationale
    5b. Reconcile every order with the product catalogue (name, category, fixed price)
    6. Create derived columns

Usage:
    python src/data_cleaning.py
    -> writes data/processed/ecommerce_orders_clean.csv and prints a cleaning log
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

RAW_PATH = Path("data/raw/ecommerce_orders_raw.csv")
CLEAN_PATH = Path("data/processed/ecommerce_orders_clean.csv")
CATALOGUE_PATH = Path("data/raw/products.csv")
CLEAN_CATALOGUE_PATH = Path("data/processed/products.csv")

VALID_CATEGORIES = ["Electronics", "Fashion", "Home & Kitchen", "Beauty",
                    "Sports", "Books", "Toys"]
VALID_STATUS = ["Delivered", "Cancelled", "Returned"]

# Business rules used for validation -------------------------------------- #
RULES = {
    "age":           (18, 100),
    "quantity":      (1, 50),
    "unit_price":    (0.01, 5000),
    "discount_pct":  (0, 100),
    "shipping_cost": (0, 100),
    "delivery_days": (0, 30),
    "review_rating": (1, 5),
}


def load_raw(path: Path = RAW_PATH) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["order_date", "signup_date"])


def load_catalogue(path: Path = CATALOGUE_PATH) -> pd.DataFrame:
    """Product master data: one row per product with its fixed price and stock on hand."""
    cat = pd.read_csv(path)
    assert cat["product_id"].is_unique, "product_id must be unique in the catalogue"
    assert (cat["unit_price"] > 0).all() and (cat["stock_on_hand"] >= 0).all()
    return cat


def reconcile_with_catalogue(df: pd.DataFrame, catalogue: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """The catalogue is the source of truth for product name, category, subcategory and price.

    * orders whose product_id is not in the catalogue are dropped (can't be priced);
    * product names / categories are reset to the catalogue spelling;
    * a missing or wrong unit_price is restored from the catalogue price.
    """
    df = df.copy()
    log = {}
    known = df["product_id"].isin(catalogue["product_id"])
    log["unknown_product_id"] = int((~known).sum())
    df = df[known].copy()
    ref = catalogue.set_index("product_id")
    log["product_name_fixed"] = int((df["product_name"] != df["product_id"].map(ref["product_name"])).sum())
    log["category_fixed"] = int((df["product_category"] != df["product_id"].map(ref["category"])).sum())
    df["product_name"] = df["product_id"].map(ref["product_name"])
    df["product_category"] = df["product_id"].map(ref["category"])
    df["subcategory"] = df["product_id"].map(ref["subcategory"])
    list_price = df["product_id"].map(ref["unit_price"])
    wrong = df["unit_price"].isna() | ~np.isclose(df["unit_price"].fillna(-1), list_price)
    log["unit_price_restored_from_catalogue"] = int(wrong.sum())
    df["unit_price"] = list_price
    cols = list(df.columns)
    cols.remove("subcategory")
    cols.insert(cols.index("product_category") + 1, "subcategory")
    return df[cols].reset_index(drop=True), log


def standardise_categories(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["product_category"] = df["product_category"].str.strip().str.title()
    # .title() turns "Home & Kitchen" into "Home & Kitchen" (fine) but check anyway
    df["product_category"] = df["product_category"].replace({"Home & Kitchen": "Home & Kitchen"})
    df["gender"] = df["gender"].replace({"F": "Female", "M": "Male"})
    return df


def remove_duplicates(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    n_dup = int(df.duplicated().sum())
    return df.drop_duplicates().reset_index(drop=True), n_dup


def validate_and_fix(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Apply business rules. Returns cleaned df and a log of what was changed."""
    df = df.copy()
    log = {}

    # Out-of-range numeric values -> treat as data-entry errors -> set to NaN,
    # then impute (for attributes) or drop (for transaction-critical fields).
    for col, (lo, hi) in RULES.items():
        mask = df[col].notna() & ((df[col] < lo) | (df[col] > hi))
        log[f"{col}_out_of_range"] = int(mask.sum())
        df.loc[mask, col] = np.nan

    # Transaction-critical field: a row without a valid quantity cannot be used for
    # revenue analysis -> drop. (A bad price is restored from the catalogue instead.)
    critical_na = df["quantity"].isna()
    log["rows_dropped_invalid_transaction"] = int(critical_na.sum())
    df = df[~critical_na].copy()
    df["quantity"] = df["quantity"].astype(int)

    # Logical rule: order_date must be on/after signup_date
    bad_dates = df["order_date"] < df["signup_date"]
    log["order_before_signup"] = int(bad_dates.sum())
    df = df[~bad_dates].copy()

    # Categorical domain checks
    log["unknown_category"] = int((~df["product_category"].isin(VALID_CATEGORIES)).sum())
    log["unknown_status"] = int((~df["order_status"].isin(VALID_STATUS)).sum())
    return df.reset_index(drop=True), log


def impute_missing(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    df = df.copy()
    log = {}
    # age: numeric, skewed by outliers -> median
    log["age_imputed"] = int(df["age"].isna().sum())
    df["age"] = df["age"].fillna(df["age"].median()).astype(int)
    # payment_method: categorical -> mode
    log["payment_method_imputed"] = int(df["payment_method"].isna().sum())
    df["payment_method"] = df["payment_method"].fillna(df["payment_method"].mode()[0])
    # city: categorical dependent on country -> mode within each country
    log["city_imputed"] = int(df["city"].isna().sum())
    df["city"] = df.groupby("country")["city"].transform(lambda s: s.fillna(s.mode()[0]))
    # discount_pct: invalid values were nulled -> assume no discount (0)
    log["discount_imputed"] = int(df["discount_pct"].isna().sum())
    df["discount_pct"] = df["discount_pct"].fillna(0)
    # delivery_days: only meaningful for non-cancelled orders -> median for those
    mask = (df["order_status"] != "Cancelled") & df["delivery_days"].isna()
    log["delivery_days_imputed"] = int(mask.sum())
    df.loc[mask, "delivery_days"] = df.loc[df["order_status"] != "Cancelled", "delivery_days"].median()
    # review_rating: leave NaN -> "no review" is real information, not an error
    log["review_rating_left_missing"] = int(df["review_rating"].isna().sum())
    return df, log


def add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["gross_amount"] = (df["quantity"] * df["unit_price"]).round(2)
    df["discount_amount"] = (df["gross_amount"] * df["discount_pct"] / 100).round(2)
    df["total_amount"] = (df["gross_amount"] - df["discount_amount"] + df["shipping_cost"]).round(2)
    # Revenue actually realised (cancelled / returned orders generate no net revenue)
    df["net_revenue"] = np.where(df["order_status"] == "Delivered", df["total_amount"], 0.0)
    df["customer_tenure_days"] = (df["order_date"] - df["signup_date"]).dt.days
    df["age_group"] = pd.cut(df["age"], bins=[17, 24, 34, 44, 54, 100],
                             labels=["18-24", "25-34", "35-44", "45-54", "55+"])
    df["order_value_tier"] = pd.cut(df["total_amount"], bins=[-np.inf, 50, 150, 400, np.inf],
                                    labels=["Low (<$50)", "Medium ($50-150)",
                                            "High ($150-400)", "Premium (>$400)"])
    df["order_month"] = df["order_date"].dt.to_period("M").astype(str)
    df["order_weekday"] = df["order_date"].dt.day_name()
    df["is_returned"] = (df["order_status"] == "Returned").astype(int)
    df["has_review"] = df["review_rating"].notna().astype(int)
    return df


def build_customer_table(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate order-level data to one row per customer (RFM-style)."""
    snapshot = df["order_date"].max() + pd.Timedelta(days=1)
    cust = (df.groupby("customer_id")
              .agg(first_order=("order_date", "min"),
                   last_order=("order_date", "max"),
                   total_orders=("order_id", "count"),
                   total_spent=("net_revenue", "sum"),
                   avg_order_value=("total_amount", "mean"),
                   returns=("is_returned", "sum"),
                   avg_rating=("review_rating", "mean"),
                   segment=("customer_segment", "first"),
                   country=("country", "first"),
                   channel=("acquisition_channel", "first"),
                   age=("age", "first"),
                   gender=("gender", "first"))
              .reset_index())
    cust["recency_days"] = (snapshot - cust["last_order"]).dt.days
    cust["return_rate"] = (cust["returns"] / cust["total_orders"]).round(3)
    cust["is_repeat"] = (cust["total_orders"] > 1).astype(int)
    # simple churn-risk flag: no order in the last 180 days
    cust["churn_risk"] = np.where(cust["recency_days"] > 180, "High",
                          np.where(cust["recency_days"] > 90, "Medium", "Low"))
    return cust


def run_pipeline(raw_path: Path = RAW_PATH, clean_path: Path = CLEAN_PATH,
                 catalogue_path: Path = CATALOGUE_PATH,
                 clean_catalogue_path: Path = CLEAN_CATALOGUE_PATH) -> pd.DataFrame:
    df = load_raw(raw_path)
    catalogue = load_catalogue(catalogue_path)
    print(f"Loaded raw data: {df.shape}; catalogue: {len(catalogue)} products")
    df = standardise_categories(df)
    df, n_dup = remove_duplicates(df)
    print(f"Duplicates removed: {n_dup}  -> {len(df):,} rows remain")
    df, vlog = validate_and_fix(df)
    print("Validation log:", vlog)
    df, clog = reconcile_with_catalogue(df, catalogue)
    print("Catalogue reconciliation:", clog)
    df, ilog = impute_missing(df)
    print("Imputation log:", ilog)
    df = add_derived_columns(df)
    clean_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(clean_path, index=False)
    catalogue.to_csv(clean_catalogue_path, index=False)
    print(f"Clean data written: {df.shape} -> {clean_path}; catalogue -> {clean_catalogue_path}")
    return df


if __name__ == "__main__":
    run_pipeline()
