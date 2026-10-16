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
> service quality — and broke them into seven analytical questions, each tied to a specific Pandas
> technique. Everything after this answers one of those questions."

**POINT AT:** the O1–O3 objectives table and the Q1–Q7 questions table.

---

## §3 · Dataset & data dictionary ⏱ 30 sec

**DO:** Scroll through the data-dictionary table.

**SAY:**
> "The dataset is synthetic but realistic — I wrote a generator so it's fully reproducible with a
> fixed seed, and so I could inject known data-quality problems on purpose. That lets me prove the
> cleaning pipeline actually catches them. There are 20 original columns; the data dictionary
> documents every field, its type, and an example."

**POINT AT:** the "deliberately injects … missing values, 45 duplicates, out-of-range numbers" line.

---

## §4 · Setup ⏱ skip-through

**DO:** Click cell [3], press Shift+Enter (runs instantly).

**SAY:**
> "Standard imports — Pandas, NumPy, Matplotlib, Seaborn, SciPy. I also import my own cleaning
> module from the `src` folder, so the notebook and the command-line pipeline share one definition."

---

## §5 · Load & explore ⏱ 1.5 min  ← the "here's what's wrong" moment

**DO:** Run cells [5]–[9] one at a time (Shift+Enter through `head`, `shape`, `info`, `describe`,
`describe(include="object")`).

**SAY (on `df.describe()`, cell [8]):**
> "This is the raw data loaded straight from CSV — 2,045 rows. And look at the describe output:
> minimum age is **minus 5**, maximum is **210**. Quantity goes negative. Discount hits **150 percent**.
> Review rating goes up to **7** on a 1-to-5 scale. This is exactly the kind of mess real exports
> contain, and the next three sections fix it."

**POINT AT:** the `min` and `max` rows — age −5 / 210, review_rating 0 / 7, discount_pct 150.

**SAY (on `df.describe(include="object")`, cell [9]):**
> "And the text columns show more than the seven categories I expect — that's inconsistent
> capitalisation and whitespace I'll standardise in a moment."

---

## §6 · Missing values ⏱ 1 min

**DO:** Run cells [12]–[13].

**SAY:**
> "First I audit what's missing. The key judgement here: not every blank is an error. A missing
> **review rating** means the customer chose not to review — that's information, so I keep it as NaN.
> A missing **delivery date** on a cancelled order is expected. But a missing **age** or **price** is
> a genuine gap. So I impute age with the **median** because it's robust to those outlier ages we just
> saw, payment method with the **mode**, city with the most common city **within the same country**,
> and I **drop** rows with no price because you can't invent revenue."

**POINT AT:** the crosstab (cell [13]) showing ratings are missing for 100 % of cancelled orders —
that's the proof the blanks are structural, not random.

---

## §7 · Duplicates ⏱ 45 sec

**DO:** Run cells [16]–[18].

**SAY:**
> "Before checking for duplicates I standardise the text — strip whitespace, fix capitalisation — so
> that rows differing only by spelling are recognised as the same. Then `drop_duplicates` finds
> **45 exact duplicate rows** — double-exports — and removes them, leaving 2,000 unique orders. I assert
> that order IDs are now unique so the notebook fails loudly if this ever regresses."

**POINT AT:** "duplicates removed: 45 | rows remaining: 2,000".

---

## §8 · Validation ⏱ 1 min

**DO:** Run cells [21]–[23].

**SAY:**
> "Now I validate against explicit business rules — age 18 to 100, rating 1 to 5, discount 0 to 100,
> and so on. The report shows **25 values out of range**. Because those are physically impossible, I
> treat them as missing, then drop the 28 rows that have no usable quantity or price. That leaves
> **1,972 clean rows**. From here, the only NaNs left are the deliberate structural ones."

**POINT AT:** the validation report table (`invalid_rows` column) and the final "1,972 rows".

---

## §9 · Derived columns ⏱ 45 sec

**DO:** Run cells [26]–[27].

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

**§10.1 KPIs (cell [31])** — run it.
> "A quick overview: 1,972 orders, 721 customers, about $227k in net revenue. Note the average order
> is $136 but the median is $76 — that gap tells me the data is skewed, which I come back to."

**§10.2 Q1 category (cells [34]–[35])** — run it. *This is your strongest headline.*
> "Grouping revenue by category: **Electronics is 54 percent of revenue from only 24 percent of
> orders**. The top three categories make 80 percent. But sorting by return rate, **Fashion is returned
> most — 13.6 percent** — so that's where the operational problem is."

**POINT AT:** the `revenue_share` column (Electronics 0.54) and the return-rate sort.

**§10.3 Q2 segments (cell [38])** — run it.
> "VIP customers are 23 percent of people but 40 percent of revenue — because they order **4.8 times**
> each versus 1.6 for new customers. Their average order is the same size, though. So loyalty is about
> frequency, not bigger baskets — I test that statistically in a second."

**§10.6 Q5 delivery vs rating (cells [50]–[51])** — run it.
> "Binning by delivery time: ratings fall from **3.96 stars at 1–3 days to 3.02 at 10+ days**. That's
> almost a full star. Delivery speed is the clearest driver of satisfaction in the data."

**SAY (wave at the rest):**
> "The same pattern continues — Q3 is the monthly trend with a `pivot_table`, Q4 is countries and
> channels, Q6 builds a customer-level table, and Q7 uses `crosstab` for payment habits by age. Each
> has a written interpretation beneath it."

---

## §11 · Statistical analysis ⏱ 1 min  ← proves rigour

**DO:** Run cells [64], [66], [67].

**SAY:**
> "This is where I move from description to statistics. Descriptive stats confirm the skew — mean well
> above median. The correlation matrix and significance tests are the important part:
> delivery time versus rating gives **r = −0.38 with a p-value near zero** — a real, significant effect.
> The t-test comparing VIP and new-customer order value comes back **not significant, p = 0.60** — which
> confirms what I said earlier: VIPs don't spend more per order, they just order more often. And the
> chi-square on returns by category is **not significant**, so I'm careful to call that one indicative."

**POINT AT:** the `r = −0.38` / `p` line and the `p = 0.60` t-test line.

> Mentioning a result that is *not* significant, and adjusting your claim because of it, is exactly
> what examiners look for. Say it with confidence — it shows you understand the stats, not just the code.

---

## §12 · Visualisations ⏱ 1 min  (already rendered — scroll, don't re-run each)

**DO:** Scroll through the nine charts. Pause on **Chart 1** (category revenue), **Chart 5**
(delivery-vs-rating scatter) and **Chart 6** (order value by segment box plot).

**SAY:**
> "Nine charts — bar, line, histogram, pie, scatter, box plot, grouped bar, heatmap and stacked bar —
> each with a title, labelled axes, and an interpretation written underneath; I never show a chart
> without saying what it means. The scatter here visualises that delivery-versus-rating correlation,
> and the box plot shows the three segments' order values overlapping almost entirely — the visual
> proof of the t-test result."

**POINT AT:** Chart 6's overlapping boxes (= VIPs don't spend more per order).

---

## §13 · Findings & recommendations ⏱ 1 min  ← land the plane

**DO:** Scroll through the findings, recommendations, and limitations tables.

**SAY:**
> "I close with seven findings, each backed by a number, and seven recommendations, each tied to a
> finding and a metric to track — for example, a 5-day delivery SLA to lift the average rating, and a
> second-purchase programme for the 45 percent of customers who've gone dormant. And I'm honest about
> limitations: the data is synthetic, there's no profit margin, and the category return differences
> weren't statistically significant."

---

## Close with the live web app ⏱ 2.5 min  ← the memorable finish

**Before the demo:** in a terminal run `python webapp/app.py --reset` (fresh data), leave it running, and
open **two browser windows side by side**: left = `http://127.0.0.1:5000` (Dashboard),
right = `http://127.0.0.1:5000/orders/new` (Add order).

**SAY (left window, Dashboard):**
> "Everything you just saw in the notebook now runs as a web app on a real database. The cleaned CSV is
> loaded into SQLite — customers and orders as two linked tables — and every number here is a SQL query
> against it. 1,972 orders, $227,155 of net revenue — the same figures as the notebook."

**DO:** Change **Country → Cambodia**, then **Reset**.
> "Filters run new SQL queries — the KPIs and charts recompute live."

**DO (right window):** type `C1122` in Customer ID — the green card shows who it is. Fill in:
Electronics · quantity 3 · price 299.99 · discount 5 · E-Wallet · delivery 2 days · rating 5.
Point at the **Order total $854.97** updating as you type. Click **Add order**.

**SAY (look at the left window — within ~4 seconds it refreshes by itself):**
> "And the dashboard picked it up on its own — orders went from 1,972 to 1,973 and revenue up by $855.
> The database bumps a change counter on every write, and the dashboard polls it."

**DO (right window):** click **Add order** again, type customer `C9999`, quantity `0`, status **Cancelled**,
and submit.
> "It validates against the same business rules as the cleaning pipeline in §8 — unknown customer,
> impossible quantity, a cancelled order can't have a delivery time. And the database enforces the
> same rules a second time with CHECK constraints, so bad data can't get in even if the form were bypassed."

**Optional (if time):** on **Customers**, try to delete `C1122` →
> "Blocked — this customer has orders, and the foreign key protects that link."

**Closing line:**
> "So: a reproducible pipeline that cleans messy data, answers the business questions with Pandas and
> statistics, and serves the results from a database as a live web app — with 39 automated tests and CI
> checking all of it on every push. Happy to take questions."

**After the demo:** click **Reset demo data** in the page footer (or rerun `python webapp/app.py --reset`)
to restore the original 1,972 orders.

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
  prove the pipeline catches all of them — that's what the 14 unit tests assert.
- **Why keep missing review ratings instead of imputing?** A missing review is information (the
  customer chose not to review); imputing would invent opinions and bias the average upward.
- **Why is the chi-square not significant?** Sample size — 1,972 orders across 7 categories. I report
  the return-rate ranking as indicative and say so in the limitations.
- **Why a 180-day churn cut-off?** It's measured from a snapshot at the end of the data window; a
  per-customer definition (recency vs that customer's own typical gap) is a stated next step.
- **Why SQLite rather than MySQL/PostgreSQL?** It's a real SQL database in a single file — no server to
  install, so the project runs anywhere with `python webapp/app.py`. The SQL (tables, foreign keys, CHECK
  constraints, a view, triggers) carries over to PostgreSQL almost unchanged.
- **Why compute totals in a view instead of storing them?** If `total_amount` were stored, editing a price
  could leave it stale. The `v_orders` view derives it on every query, so it's always consistent.
- **Is it secure?** Every form is CSRF-protected, all SQL is parameterised (no string-built user input),
  redirects only go to same-site paths, and input is validated twice — Python, then database constraints.

