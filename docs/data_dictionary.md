# Data Dictionary — E-commerce Customer Analytics

Dataset: `data/raw/ecommerce_orders_raw.csv` (2,045 rows × 20 columns, before cleaning)
Clean dataset: `data/processed/ecommerce_orders_clean.csv` (1,972 rows × 31 columns)

One row = one customer order. Customer attributes are repeated on every order placed by that customer.

## Raw columns

| # | Field | Data type | Description | Example value |
|---|-------|-----------|-------------|---------------|
| 1 | `order_id` | string | Unique identifier of the order | `ORD100305` |
| 2 | `order_date` | date (YYYY-MM-DD) | Date the order was placed | `2024-04-25` |
| 3 | `customer_id` | string | Unique identifier of the customer; repeats across orders | `C1122` |
| 4 | `age` | integer | Customer's age in years (valid range 18–100) | `36` |
| 5 | `gender` | category | Customer gender: `Female` / `Male` | `Male` |
| 6 | `country` | category | Customer's country (7 Southeast-Asian markets) | `Cambodia` |
| 7 | `city` | category | Customer's city | `Phnom Penh` |
| 8 | `signup_date` | date (YYYY-MM-DD) | Date the customer registered an account | `2024-03-21` |
| 9 | `customer_segment` | category | Loyalty tier: `New`, `Regular`, `VIP` | `VIP` |
| 10 | `acquisition_channel` | category | Marketing channel that acquired the customer: `Organic Search`, `Social Media`, `Email`, `Paid Ads`, `Referral` | `Referral` |
| 11 | `product_category` | category | Category of the product ordered: `Electronics`, `Fashion`, `Home & Kitchen`, `Beauty`, `Sports`, `Books`, `Toys` | `Beauty` |
| 12 | `quantity` | integer | Units ordered (valid range 1–50) | `1` |
| 13 | `unit_price` | float | Price per unit in USD (must be > 0) | `37.40` |
| 14 | `discount_pct` | float | Percentage discount applied to the order (0–100) | `5.0` |
| 15 | `shipping_cost` | float | Shipping fee in USD; $0 when gross amount > $120 | `9.99` |
| 16 | `payment_method` | category | `Credit Card`, `E-Wallet`, `Bank Transfer`, `Cash on Delivery`, `PayPal` | `Credit Card` |
| 17 | `device_type` | category | Device used to place the order: `Mobile`, `Desktop`, `Tablet` | `Desktop` |
| 18 | `delivery_days` | float | Days from order to delivery (0–30); blank for cancelled orders | `7.0` |
| 19 | `order_status` | category | Final status: `Delivered`, `Cancelled`, `Returned` | `Returned` |
| 20 | `review_rating` | float | Customer's star rating 1–5; blank when no review was left | `3.0` |

## Derived columns (added during cleaning / feature engineering)

| # | Field | Data type | Description / formula | Example value |
|---|-------|-----------|-----------------------|---------------|
| 21 | `gross_amount` | float | `quantity × unit_price` | `37.40` |
| 22 | `discount_amount` | float | `gross_amount × discount_pct / 100` | `1.87` |
| 23 | `total_amount` | float | Amount paid: `gross_amount − discount_amount + shipping_cost` | `45.52` |
| 24 | `net_revenue` | float | `total_amount` if status is `Delivered`, else 0 (refunded) | `0.00` |
| 25 | `customer_tenure_days` | integer | Days between `signup_date` and `order_date` | `35` |
| 26 | `age_group` | category | Age band: `18-24`, `25-34`, `35-44`, `45-54`, `55+` | `35-44` |
| 27 | `order_value_tier` | category | `Low (<$50)`, `Medium ($50-150)`, `High ($150-400)`, `Premium (>$400)` | `Low (<$50)` |
| 28 | `order_month` | string | Year-month of the order (`YYYY-MM`) | `2024-04` |
| 29 | `order_weekday` | string | Day of week of the order | `Thursday` |
| 30 | `is_returned` | integer (0/1) | 1 if `order_status == "Returned"` | `1` |
| 31 | `has_review` | integer (0/1) | 1 if a `review_rating` was given | `1` |

## Customer-level table (built in the notebook by `build_customer_table`)

| Field | Data type | Description |
|-------|-----------|-------------|
| `customer_id` | string | Customer identifier |
| `first_order`, `last_order` | date | First and most recent order dates |
| `total_orders` | integer | Number of orders placed |
| `total_spent` | float | Sum of `net_revenue` |
| `avg_order_value` | float | Mean `total_amount` |
| `returns`, `return_rate` | integer, float | Returned orders and their share |
| `avg_rating` | float | Mean review rating |
| `recency_days` | integer | Days since last order (snapshot = day after last date in data) |
| `is_repeat` | integer (0/1) | 1 if more than one order |
| `churn_risk` | category | `Low` (≤ 90 days), `Medium` (91–180), `High` (> 180 days since last order) |

## Known data-quality issues in the raw file (deliberately injected)

| Issue | Columns affected | Count |
|-------|------------------|-------|
| Missing values | `age`, `payment_method`, `city`, `unit_price`, `delivery_days`, `review_rating` | see notebook §6 |
| Exact duplicate rows | all | 45 |
| Out-of-range values | `age`, `quantity`, `unit_price`, `discount_pct`, `delivery_days`, `review_rating` | 25 |
| Inconsistent text | `product_category` (case / whitespace), `gender` (`F`/`M`) | 52 |
