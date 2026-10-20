"""Unit tests for the cleaning pipeline (run with `pytest`)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import data_cleaning as dc  # noqa: E402
from generate_dataset import build_catalogue, generate, inject_quality_issues  # noqa: E402


@pytest.fixture(scope="module")
def catalogue():
    return build_catalogue(seed=1)


@pytest.fixture(scope="module")
def raw(catalogue):
    return inject_quality_issues(generate(rows=500, seed=1, catalogue=catalogue), seed=1)


@pytest.fixture(scope="module")
def clean(raw, catalogue):
    df = dc.standardise_categories(raw)
    df, _ = dc.remove_duplicates(df)
    df, _ = dc.validate_and_fix(df)
    df, _ = dc.reconcile_with_catalogue(df, catalogue)
    df, _ = dc.impute_missing(df)
    return dc.add_derived_columns(df)


def test_generator_is_reproducible():
    a = generate(rows=200, seed=7)
    b = generate(rows=200, seed=7)
    pd.testing.assert_frame_equal(a, b)


def test_raw_contains_injected_problems(raw):
    assert raw.duplicated().sum() == 45
    assert raw["age"].max() > 100 and raw["age"].min() < 18
    assert raw["review_rating"].max() > 5


def test_duplicates_removed(raw):
    df, n_dup = dc.remove_duplicates(dc.standardise_categories(raw))
    assert n_dup == 45
    assert df.duplicated().sum() == 0
    assert df["order_id"].is_unique


def test_categories_standardised(clean):
    assert set(clean["product_category"].unique()) <= set(dc.VALID_CATEGORIES)
    assert set(clean["gender"].unique()) <= {"Female", "Male"}


@pytest.mark.parametrize("col", list(dc.RULES))
def test_values_within_business_rules(clean, col):
    lo, hi = dc.RULES[col]
    vals = clean[col].dropna()
    assert vals.between(lo, hi).all(), f"{col} has out-of-range values"


def test_only_structural_missing_values_remain(clean):
    non_structural = clean.drop(columns=["delivery_days", "review_rating"]).isna().sum().sum()
    assert non_structural == 0
    # delivery_days may only be missing for cancelled orders
    assert clean.loc[clean["order_status"] != "Cancelled", "delivery_days"].notna().all()


def test_derived_columns_are_consistent(clean):
    expected = (clean["quantity"] * clean["unit_price"] * (1 - clean["discount_pct"] / 100)
                + clean["shipping_cost"]).round(2)
    assert np.allclose(clean["total_amount"], expected, atol=0.02)
    assert (clean.loc[clean["order_status"] != "Delivered", "net_revenue"] == 0).all()
    assert (clean["customer_tenure_days"] >= 0).all()


def test_customer_table(clean):
    cust = dc.build_customer_table(clean)
    assert cust["customer_id"].is_unique
    assert len(cust) == clean["customer_id"].nunique()
    assert cust["total_orders"].sum() == len(clean)
    assert set(cust["churn_risk"].unique()) <= {"Low", "Medium", "High"}


def test_catalogue_is_well_formed(catalogue):
    assert catalogue["product_id"].is_unique
    assert (catalogue["unit_price"] > 0).all() and (catalogue["stock_on_hand"] >= 0).all()
    # every category has several products spread over at least two subcategories
    per_cat = catalogue.groupby("category").agg(products=("product_id", "count"), subs=("subcategory", "nunique"))
    assert (per_cat["products"] >= 5).all() and (per_cat["subs"] >= 2).all()


def test_orders_use_fixed_catalogue_price_and_names(clean, catalogue):
    ref = catalogue.set_index("product_id")
    assert (clean["unit_price"] == clean["product_id"].map(ref["unit_price"])).all()
    assert (clean["product_name"] == clean["product_id"].map(ref["product_name"])).all()
    assert (clean["product_category"] == clean["product_id"].map(ref["category"])).all()
