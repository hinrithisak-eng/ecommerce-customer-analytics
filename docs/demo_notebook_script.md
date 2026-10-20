# Live Demo Script — Jupyter Notebook

A section-by-section script for presenting `notebooks/ecommerce_customer_analytics.ipynb`.
Each block has **SAY** (what to say aloud), **DO** (what to click/run), and **POINT AT** (the
number or output to draw attention to). Target length ~11 minutes; the ⏱ tags add up to that — trim §3/§9 if you're short on time.

> How to run a cell live: click it and press **Shift + Enter**. The cell below it becomes selected,
> so you can keep pressing Shift+Enter to walk down the notebook.

---

## Before the audience is watching (do this first)

1. Open a terminal in the project folder and launch Jupyter: `jupyter notebook`
   (or open the folder in VS Code and open the `.ipynb`).
2. Click **Kernel → Restart & Run All** and wait ~15 seconds until every cell shows output.
   This means that even if the live kernel misbehaves, all results and charts are already on screen.
3. Zoom the browser to **125–150 %** (Ctrl + `+`) so the back row can read the code.
4. In a **second terminal**, start the web app: `python webapp/app.py --reset` and leave it running.
   Open two browser windows on it — Dashboard (`http://127.0.0.1:5000`) and Add order
   (`http://127.0.0.1:5000/orders/new`).
5. Also have ready in tabs: the GitHub repo page, `docs/dashboard.html` (offline fallback) and
   `docs/notebook_export.html` (no-kernel fallback).
6. Collapse the Jupyter file browser so the notebook uses the full width.

**One-line framing to open with:**
> "This notebook takes a raw e-commerce order log, cleans it, and answers seven business questions
> with Pandas. I'll walk through it top to bottom, then show the same results as an interactive dashboard."

---

## §1–§2 · Problem, scope, objectives & questions ⏱ 1.5 min

**DO:** Scroll slowly through the top markdown cell (§1 and §2).

**SAY:**
> "The client is an online retailer across seven Southeast-Asian markets that has never analysed its
> order history. It can't say which products or customers drive revenue, whether customers come back,
> or why some leave bad reviews.
> I set three measurable objectives — identify the revenue drivers, measure retention, and diagnose
> service quality — and broke them into eight analytical questions, each tied to a specific Pandas
> technique. Everything after this answers one of those questions."

**POINT AT:** the O1–O3 objectives table and the Q1–Q8 questions table.

---

## §3 · Dataset & data dictionary ⏱ 30 sec

**DO:** Scroll through the data-dictionary table.

**SAY:**
> "The dataset is synthetic but realistic — I wrote a generator so it's fully reproducible with a
> fixed seed, and so I could inject known data-quality problems on purpose. That lets me prove the
> cleaning pipeline actually catches them. It has two files: a **product catalogue** — 60 products in 30
> subcategories, each with a fixed price and stock — and 2,045 orders of those products with 22 columns.
> The data dictionary documents every field, its type, and an example."

**POINT AT:** the "deliberately injects … missing values, 45 duplicates, out-of-range numbers" line.

---

## §4 · Setup ⏱ skip-through

**DO:** Click cell [3], press Shift+Enter (runs instantly).

**SAY:**
> "Standard imports — Pandas, NumPy, Matplotlib, Seaborn, SciPy. I also import my own cleaning
> module from the `src` folder, so the notebook and the command-line pipeline share one definition."

---

## §5 · Load & explore ⏱ 1.5 min  ← the "here's what's wrong" moment

**DO:** Run cells [5]–[10] one at a time (Shift+Enter through `head`, `shape`, `info`, `describe`,
`describe(include="object")` and the product catalogue).

**SAY (on `df.describe()`, cell [8]):**
> "This is the raw data loaded straight from CSV — 2,045 rows. And look at the describe output:
> minimum age is **minus 5**, maximum is **210**. Quantity goes negative. Discount hits **150 percent**.
> Review rating goes up to **7** on a 1-to-5 scale. This is exactly the kind of mess real exports
> contain, and the next three sections fix it."

**POINT AT:** the `min` and `max` rows — age −5 / 210, review_rating 0 / 7, discount_pct 150.

**SAY (on `df.describe(include="object")`, cell [9]):**
> "And the text columns show 19 categories where I expect seven, and 69 product names for 60 products —
> inconsistent capitalisation and whitespace I'll standardise in a moment."

**SAY (on the catalogue, cell [10]):**
> "The orders point into a **product catalogue**: 60 products in 7 categories and 30 subcategories —
> Books, for example, splits into Comics & Manga, Programming, Fiction, Self-Help and Children's. Every
> product has **one fixed list price** and a stock level. That catalogue becomes the source of truth for
> prices in cleaning."

---

## §6 · Missing values ⏱ 1 min

**DO:** Run cells [13]–[14].

**SAY:**
> "First I audit what's missing. The key judgement here: not every blank is an error. A missing
> **review rating** means the customer chose not to review — that's information, so I keep it as NaN.
> A missing **delivery date** on a cancelled order is expected. But a missing **age** or **price** is
> a genuine gap. So I impute age with the **median** because it's robust to those outlier ages we just
> saw, payment method with the **mode**, city with the most common city **within the same country** —
> and a missing **price** isn't a guess at all: every product has one list price, so I look it up in the
> catalogue."

**POINT AT:** the crosstab (cell [14]) showing ratings are missing for 100 % of cancelled orders —
that's the proof the blanks are structural, not random.

---

## §7 · Duplicates ⏱ 45 sec

**DO:** Run cells [17]–[19].

**SAY:**
> "Before checking for duplicates I standardise the text — strip whitespace, fix capitalisation — so
> that rows differing only by spelling are recognised as the same. Then `drop_duplicates` finds
> **45 exact duplicate rows** — double-exports — and removes them, leaving 2,000 unique orders. I assert
> that order IDs are now unique so the notebook fails loudly if this ever regresses."

**POINT AT:** "duplicates removed: 45 | rows remaining: 2,000".

---

## §8 · Validation ⏱ 1 min

**DO:** Run cells [22]–[24].

**SAY:**
> "Now I validate against explicit business rules — age 18 to 100, rating 1 to 5, discount 0 to 100,
> and so on. The report shows **25 values out of range**. Because those are physically impossible, I
> treat them as missing and drop the **5 rows** with no usable quantity. I also check every order against
> the catalogue: **23 prices** were missing or wrong, so they're restored from the list price instead of
> dropping the order. That leaves **1,995 clean rows**. From here, the only NaNs left are the deliberate
> structural ones."

**POINT AT:** the validation report table (`invalid_rows` column), "Prices restored from the catalogue: 23" and "1,995 rows".

---

## §9 · Derived columns ⏱ 45 sec

**DO:** Run cells [27]–[28].

**SAY:**
> "I engineer eleven new columns. The two that matter most: `total_amount` — what the customer paid,
> quantity times price minus discount plus shipping — and `net_revenue`, which is zero for cancelled
> or returned orders because those are refunded. I also bucket age and order value into bands for
> grouping, and flag returns and reviews. The clean, enriched dataset is saved to
> `data/processed/` so it's reusable."

**POINT AT:** the derived columns preview (gross_amount, total_amount, net_revenue, age_group).

---

## §10 · Analysis with Pandas ⏱ 2.5 min  ← the core; show Pandas executing

Run these live so the audience sees Pandas work. Don't read all eight — show **10.2, 10.6, 10.3**
and mention the rest exist.

**§10.1 KPIs (cell [32])** — run it.
> "A quick overview: 1,995 orders, 723 customers, about $149k in net revenue. Note the average order
> is $92 but the median is $50 — that gap tells me the data is skewed, which I come back to."

**§10.2 Q1 category (cells [35]–[36])** — run it. *This is your strongest headline.*
> "Grouping revenue by category: **Electronics is 47 percent of revenue from only 24 percent of
> orders**. The top three categories make 77 percent. But sorting by return rate, **Fashion is returned
> most — 15.7 percent** — so that's where the operational problem is."

**POINT AT:** the `revenue_share` column (Electronics 0.47) and the return-rate sort.

**§10.3 Q2 segments (cell [39])** — run it.
> "VIP customers are 23 percent of people but 40 percent of revenue — because they order **4.9 times**
> each versus 1.6 for new customers. Their average order is no bigger, though. So loyalty is about
> frequency, not bigger baskets — I test that statistically in a second."

**§10.6 Q5 delivery vs rating (cells [51]–[52])** — run it.
> "Binning by delivery time: ratings fall from **3.97 stars at 1–3 days to 3.00 at 10+ days**. That's
> almost a full star. Delivery speed is the clearest driver of satisfaction in the data."

**SAY (wave at the rest):**
> "The same pattern continues — Q3 is the monthly trend with a `pivot_table`, Q4 is countries and
> channels, Q6 builds a customer-level table, and Q7 uses `crosstab` for payment habits by age. Each
> has a written interpretation beneath it."

**§10.9 Q8 products & stock (cells [65]–[67])** — run it.
> "And down at product level: the **Smartphone A54 alone is 11 percent of revenue**, and the top 10 of
> 60 products make half. The stock-cover table divides stock on hand by monthly sales — **two products
> are already sold out**, including the Noise-Cancelling Headphones, which sell about $775 a month."

---

## §11 · Statistical analysis ⏱ 1 min  ← proves rigour

**DO:** Run cells [70], [72], [73].

**SAY:**
> "This is where I move from description to statistics. Descriptive stats confirm the skew — mean well
> above median. The correlation matrix and significance tests are the important part:
> delivery time versus rating gives **r = −0.41 with a p-value near zero** — a real, significant effect.
> The t-test comparing VIP and new-customer order value comes back **not significant, p = 0.26** — which
> confirms what I said earlier: VIPs don't spend more per order, they just order more often. And the
> chi-square on returns by category **is significant, p = 0.015**, so Fashion's high return rate isn't chance."

**POINT AT:** the `r = −0.406` / `p` line and the `p = 0.255` t-test line.

> Mentioning a result that is *not* significant (the VIP t-test), and adjusting your claim because of it, is exactly
> what examiners look for. Say it with confidence — it shows you understand the stats, not just the code.

---

## §12 · Visualisations ⏱ 1 min  (already rendered — scroll, don't re-run each)

**DO:** Scroll through the ten charts. Pause on **Chart 1** (category revenue), **Chart 5**
(delivery-vs-rating scatter), **Chart 6** (order value by segment box plot) and **Chart 10** (top products).

**SAY:**
> "Ten charts — bar, line, histogram, pie, scatter, box plot, grouped bar, heatmap, stacked bar and a
> top-products ranking —
> each with a title, labelled axes, and an interpretation written underneath; I never show a chart
> without saying what it means. The scatter here visualises that delivery-versus-rating correlation,
> and the box plot shows the three segments' order values overlapping almost entirely — the visual
> proof of the t-test result."

**POINT AT:** Chart 6's overlapping boxes (= VIPs don't spend more per order).

---

## §13 · Findings & recommendations ⏱ 1 min  ← land the plane

**DO:** Scroll through the findings, recommendations, and limitations tables.

**SAY:**
> "I close with eight findings, each backed by a number, and seven recommendations, each tied to a
> finding and a metric to track — for example, a 5-day delivery SLA to lift the average rating, and a
> second-purchase programme for the 45 percent of customers who've gone dormant, and reordering the
> products that are sold out. And I'm honest about limitations: the data is synthetic, there's no profit
> margin, and prices are fixed for the whole period."

---

## Close with the live web app ⏱ 2.5 min  ← the memorable finish

**Before the demo:** in a terminal run `python webapp/app.py --reset` (fresh data), leave it running, and
open **two browser windows side by side**: left = `http://127.0.0.1:5000` (Dashboard),
right = `http://127.0.0.1:5000/orders/new` (New order).

**SAY (left window, Dashboard):**
> "Everything you just saw in the notebook now runs as a web app on a real database. The cleaned CSV is
> loaded into SQLite — products, customers and orders as three linked tables — and every number here is a
> SQL query against it. 1,995 orders, $148,675 of net revenue — the same figures as the notebook."

**DO:** Hover **Cambodia** on the Southeast Asia map, then change **Country → Cambodia**, then **Clear**.
> "Our market is Southeast Asia, so revenue is mapped by country — Cambodia, Vietnam and Thailand bring in about 69 percent."
> "Filters run new SQL queries — the KPIs and charts recompute live."

**DO (right window):** type `C1122` in Customer ID — the customer details appear under the field. Choose
Category **Books** → Product **Python Programming for Beginners**: the price **$39.00** fills in by itself and
the stock shows "71 in stock". Type quantity **999** first — it turns red: "Only 71 in stock". Then set
quantity 3 · discount 0 · E-Wallet · delivery 2 days · rating 5. The **Summary** shows $117.00. Click **Create order**.
> "I never type a price — it comes from the catalogue — and I can't sell more than we have. The database
> enforces that too: stock has a CHECK constraint, and a trigger takes the 3 units out of stock."

**SAY (look at the left window — within a few seconds it refreshes by itself; the changed KPIs briefly highlight):**
> "And the dashboard picked it up on its own — orders went from 1,995 to 1,996 and revenue up by $117.
> On **Products**, that book now shows 68 in stock.
> The database bumps a change counter on every write, and the dashboard polls it."

**DO (right window):** click **New order** again, type customer `C9999`, quantity `0`, status **Cancelled**,
and submit.
> "It validates against the same business rules as the cleaning pipeline in §8 — unknown customer,
> impossible quantity, a cancelled order can't have a delivery time. And the database enforces the
> same rules a second time with CHECK constraints, so bad data can't get in even if the form were bypassed."

**Optional (if time):** open **Products** and click the red **6 low** badge in the sidebar — the stock alerts;
or on **Customers**, try to delete `C1122` →
> "Blocked — this customer has orders, and the foreign key protects that link."

**Closing line:**
> "So: a reproducible pipeline that cleans messy data, answers the business questions with Pandas and
> statistics, and serves the results from a database as a live web app — with 58 automated tests and CI
> checking all of it on every push. Happy to take questions."

**After the demo:** click **Reset data** at the bottom of the sidebar (or rerun `python webapp/app.py --reset`)
to restore the original 1,995 orders and stock levels.

> **Fallback:** if the server won't start, open `docs/dashboard.html` — the same charts with filters,
> no Python needed. Say: *"here's the offline version of the same dashboard."*

---

## If something breaks

- **A cell errors mid-demo:** don't debug on stage. Say *"the outputs are already saved from the full
  run"* and scroll — the results are still visible. Or switch to `docs/notebook_export.html`, which is
  the whole notebook frozen with outputs and needs no kernel.
- **The kernel won't start at all:** present entirely from `docs/notebook_export.html`.
- **A chart looks tiny on the projector:** increase browser zoom; the charts are vector/PNG and scale.

## Likely questions (quick answers)

- **Why synthetic data?** Reproducible with a fixed seed, and it let me inject known errors so I can
  prove the pipeline catches all of them — that's what the 16 cleaning tests assert.
- **Why keep missing review ratings instead of imputing?** A missing review is information (the
  customer chose not to review); imputing would invent opinions and bias the average upward.
- **Why is the price fixed per product?** That's how a catalogue works: the order form takes the list
  price, so staff can't mistype it. Changing a product's price affects new orders only — past orders keep
  the price they were sold at.
- **What stops overselling?** The form limits quantity to stock on hand, the server re-checks it, and the
  database has `CHECK (stock_on_hand >= 0)` with triggers that move stock on every order change.
- **Why a 180-day churn cut-off?** It's measured from a snapshot at the end of the data window; a
  per-customer definition (recency vs that customer's own typical gap) is a stated next step.
- **Why SQLite rather than MySQL/PostgreSQL?** It's a real SQL database in a single file — no server to
  install, so the project runs anywhere with `python webapp/app.py`. The SQL (tables, foreign keys, CHECK
  constraints, a view, triggers) carries over to PostgreSQL almost unchanged.
- **Why compute totals in a view instead of storing them?** If `total_amount` were stored, editing a price
  could leave it stale. The `v_orders` view derives it on every query, so it's always consistent.
- **Is it secure?** Every form is CSRF-protected, all SQL is parameterised (no string-built user input),
  redirects only go to same-site paths, and input is validated twice — Python, then database constraints.

