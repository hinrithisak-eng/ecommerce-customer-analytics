# Data Dictionary — E-commerce Customer Analytics

Orders: `data/raw/ecommerce_orders_raw.csv` (2,045 rows × 22 columns, before cleaning)
Product catalogue: `data/raw/products.csv` (60 products × 7 columns)
Clean dataset: `data/processed/ecommerce_orders_clean.csv` (1,995 rows × 34 columns)

One row = one customer order of one product. Customer attributes are repeated on every order placed by that customer; product name, category and price come from the catalogue.

## Product catalogue (`products.csv`)

Seven categories, 30 subcategories, 60 products. Each product has **one fixed list price** — every order of that product is charged this price (discounts are applied on top) — and a **stock level** that the web app reduces when an order is delivered.

| Field | Data type | Description | Example value |
|-------|-----------|-------------|---------------|
| `product_id` | string | Unique product identifier | `P049` |
| `product_name` | string | Product name | `Python Programming for Beginners` |
| `category` | category | One of the 7 categories | `Books` |
| `subcategory` | category | Group within the category, e.g. Books → `Comics & Manga`, `Programming`, `Fiction`, `Self-Help`, `Children's` | `Programming` |
| `unit_price` | float | Fixed list price in USD (> 0) | `39.00` |
| `stock_on_hand` | integer | Units in stock on 30 June 2025 (≥ 0) | `71` |
| `reorder_level` | integer | Flag the product as low stock at or below this many units | `10` |

| Category | Subcategories |
|----------|---------------|
| Electronics | Phones & Tablets, Audio, Computers, Accessories |
| Fashion | Men's Clothing, Women's Clothing, Footwear, Bags & Accessories |
| Home & Kitchen | Cookware, Small Appliances, Home Decor, Storage |
| Beauty | Skincare, Makeup, Hair Care, Fragrance |
| Sports | Fitness, Outdoor, Team Sports, Cycling |
| Books | Comics & Manga, Programming, Fiction, Self-Help, Children's |
| Toys | Building Sets, Plush, Remote Control, Games & Puzzles, Arts & Crafts |

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
| 11 | `product_id` | string | Product ordered — key into the catalogue | `P036` |
| 12 | `product_name` | string | Product name | `Herbal Shampoo` |
| 13 | `product_category` | category | Category of the product: `Electronics`, `Fashion`, `Home & Kitchen`, `Beauty`, `Sports`, `Books`, `Toys` | `Beauty` |
| 14 | `quantity` | integer | Units ordered (valid range 1–50) | `2` |
| 15 | `unit_price` | float | Price per unit in USD — the product's fixed list price | `9.00` |
| 16 | `discount_pct` | float | Percentage discount applied to the order (0–100) | `0.0` |
| 17 | `shipping_cost` | float | Shipping fee in USD; $0 when gross amount > $120 | `6.99` |
| 18 | `payment_method` | category | `Credit Card`, `E-Wallet`, `Bank Transfer`, `Cash on Delivery`, `PayPal` | `Credit Card` |
| 19 | `device_type` | category | Device used to place the order: `Mobile`, `Desktop`, `Tablet` | `Mobile` |
| 20 | `delivery_days` | float | Days from order to delivery (0–30); blank for cancelled orders | *(blank)* |
| 21 | `order_status` | category | Final status: `Delivered`, `Cancelled`, `Returned` | `Cancelled` |
| 22 | `review_rating` | float | Customer's star rating 1–5; blank when no review was left | *(blank)* |

## Added and derived columns (cleaning / feature engineering)

| # | Field | Data type | Description / formula | Example value |
|---|-------|-----------|-----------------------|---------------|
| 23 | `subcategory` | category | Looked up from the catalogue by `product_id` | `Hair Care` |
| 24 | `gross_amount` | float | `quantity × unit_price` | `18.00` |
| 25 | `discount_amount` | float | `gross_amount × discount_pct / 100` | `0.00` |
| 26 | `total_amount` | float | Amount paid: `gross_amount − discount_amount + shipping_cost` | `24.99` |
| 27 | `net_revenue` | float | `total_amount` if status is `Delivered`, else 0 (refunded) | `0.00` |
| 28 | `customer_tenure_days` | integer | Days between `signup_date` and `order_date` | `35` |
| 29 | `age_group` | category | Age band: `18-24`, `25-34`, `35-44`, `45-54`, `55+` | `35-44` |
| 30 | `order_value_tier` | category | `Low (<$50)`, `Medium ($50-150)`, `High ($150-400)`, `Premium (>$400)` | `Low (<$50)` |
| 31 | `order_month` | string | Year-month of the order (`YYYY-MM`) | `2024-04` |
| 32 | `order_weekday` | string | Day of week of the order | `Thursday` |
| 33 | `is_returned` | integer (0/1) | 1 if `order_status == "Returned"` | `0` |
| 34 | `has_review` | integer (0/1) | 1 if a `review_rating` was given | `0` |

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
| Inconsistent text | `product_category` (case / whitespace), `product_name` (upper case + trailing spaces), `gender` (`F`/`M`) | 62 |
| Price disagrees with the catalogue | `unit_price` (20 missing + 3 negative) — restored from the list price | 23 |
