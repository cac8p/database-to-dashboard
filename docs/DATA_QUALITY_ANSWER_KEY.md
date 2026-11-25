# Data quality answer key

> ⚠️ **Spoilers.** Explore the raw files and make your own list first. Spotting these problems is part of the skill.

These problems are planted on purpose. Each one mirrors something that really happens in company data. The "Fix in silver" column is a hint, not the only right answer.

## CRM: `crm/accounts.csv`

| Issue | Why it happens in real life | Fix in silver |
|---|---|---|
| **~50 duplicate accounts**: same company entered twice with name variants (`ACME CORP`, `Acme Corp Inc.`, trailing spaces) and website variants (`www.`, `https://`, uppercase) | Reps create a new record instead of searching the CRM first | Normalize website to a bare domain, then dedupe on domain. Keep the earliest record as the "golden" account and map duplicates to it |
| **Inconsistent region values**: `NA`, `N. America`, `north america`, `Europe`, `emea`, `APAC ` (trailing space) | Free-text field, no picklist validation | Trim, lowercase, then map to a standard list with a CASE statement or a mapping table |
| **The `NA` trap**: many tools (pandas, some CSV readers) read the text `NA` as a NULL | "NA" means "not available" to most software | Load bronze with everything as text so nothing gets reinterpreted. Notice some "nulls" in region are really North America |
| **Country variants**: `United States`, `USA`, `US`, `U.S.` | Same as above | Map to a standard list (or ISO codes) |
| **Missing industry (~3%) and employee band (~5%)** | Optional fields reps skip | Keep as `Unknown`. Don't drop the rows |
| **Prospects with no subscriptions** | The CRM holds leads and lost deals, not only customers | Not an error! But "accounts" ≠ "customers". Define customer = has had a subscription |
| **Company names containing commas** | Legal names like "Smith, Jones and Partners" | The CSV quotes them correctly. Make sure your loader handles quoted fields |

## Billing: `billing/invoices.csv`

| Issue | Why | Fix in silver |
|---|---|---|
| **Billing system migration on 2025-04-01** changes three formats at once: invoice IDs (`INV-000123` → `inv-2025-003800`), dates (`2024-03-15` → `03/15/2025`), amounts (`7584.00` → `"$13,200.00"`, `"£4,100.00"`, `"€2,950.00"`) | Companies switch billing systems and history isn't converted | Parse dates with both formats. Strip currency symbols and commas, then cast to a number. Flag `source_system` = legacy/new |
| **Exact duplicate rows** after the migration | The new system re-sent some invoices | Dedupe on all columns, or on invoice_id |
| **Credit notes with negative amounts** | Partial refunds and service credits | Keep them, but label them. Revenue = invoices + credit notes |
| **Mixed currencies** (USD, GBP, EUR) | Global customers are billed locally | Convert to USD in silver or gold using `reference/fx_rates_monthly.csv` (later: real FX from FRED) |
| **Open/overdue invoices** with no paid date | Normal near "today" | Not an error. Great for an accounts receivable aging view |
| **Invoices dated before 2023** | Legacy customers' contracts started in 2022 | Not an error. The history window starts with those contracts |

## Billing: `billing/subscriptions.csv`

Fairly clean, like a well-run billing system. Things to understand rather than fix:
- One row per **product per contract term**. A renewal creates a new row linked by `previous_subscription_id`.
- `status`: `renewed`, `churned` (account left), `cancelled` (one product dropped, account stayed), `active` (current).
- `annual_contract_value` is in the **local currency**.
- 24-month contracts show ACV per year, not the total.

## Product app: `product_app/users.csv`

| Issue | Fix in silver |
|---|---|
| ~4% of emails in UPPERCASE | `lower(email)` |
| ~10% missing job title | `Unknown` |

## Product app: `product_app/usage_events/usage_events_YYYY_MM.csv`

| Issue | Why | Fix in silver |
|---|---|---|
| **Files are split by arrival month, not event month** | Logs land as they arrive | Combine all files in bronze. Never assume the file name equals the event date |
| **Late-arriving events (~3%)**: `ingested_at` is 2–10 days after `event_timestamp`. Some October events land in November's file | Mobile devices offline, retry queues | Always analyze on `event_timestamp`. Incremental loads need a look-back window |
| **Schema drift**: files from 2025-09 onward have an extra `platform` column | The app team added a field | Union files by column name, not position. Older rows get NULL platform |
| **Two timestamp formats**: `2024-03-05T14:22:10Z` and `2024-03-05 14:22:10` | Different services write logs | Parse both into one timestamp type |
| **Casing bug from 2024-06-10 to 2024-07-22**: `LOGIN`, `Login`, `report download` | A buggy app release | `lower()` and replace spaces with underscores |
| **Duplicate events (~1.2%)**: same `event_id` appears twice | Client retries | Dedupe on `event_id` |
| **NULL user_id** on many Pricing Benchmark API calls | Service accounts / API keys, not people | Keep them. Count them as account-level usage, not user-level |

## Business patterns worth finding in gold

These aren't errors. They're the story your dashboard should tell:
- Usage drops in the ~4 months before an account churns. Can you build an at-risk flag?
- The January 2025 price increase. Did it affect churn?
- Adoption of Supply Chain Monitor (launched May 2024) through cross-sell
- Q4 and quarter-end spikes in new bookings
- Late payers tend to be lower-health accounts
