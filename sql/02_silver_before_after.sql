-- ============================================================
-- Silver layer: before (bronze) vs after (silver)
-- Run:  python scripts/run_sql.py sql/02_silver_before_after.sql
--
-- Each query shows a data problem in bronze next to the fix in silver.
-- ============================================================


-- show: 1. Row counts: what cleaning removed (duplicates) and why counts differ
SELECT 'accounts'     AS entity, (SELECT count(*) FROM bronze.crm_accounts)     AS bronze_rows, (SELECT count(*) FROM silver.accounts)     AS silver_rows, 'duplicate CRM records merged' AS why
UNION ALL
SELECT 'invoices',     (SELECT count(*) FROM bronze.billing_invoices), (SELECT count(*) FROM silver.invoices),     're-sent invoices removed'
UNION ALL
SELECT 'usage events', (SELECT count(*) FROM bronze.app_usage_events), (SELECT count(*) FROM silver.usage_events), 'double-sent events removed';


-- show: 2. Regions: 14 messy spellings in bronze become 4 standard values in silver
SELECT 'bronze' AS layer, count(DISTINCT region) AS distinct_regions FROM bronze.crm_accounts
UNION ALL
SELECT 'silver', count(DISTINCT region) FROM silver.accounts;

SELECT region, count(*) AS accounts
FROM silver.accounts
GROUP BY region
ORDER BY accounts DESC;


-- show: 3. Duplicate accounts: how the CRM variants rolled up into one master record
SELECT a.account_id, a.company_name, a.domain, a.country,
       string_agg(b.company_name, '  |  ') AS crm_names_merged
FROM silver.accounts a
JOIN silver.account_id_map m ON m.account_id = a.account_id
JOIN bronze.crm_accounts b   ON b.account_id = m.crm_account_id
WHERE a.crm_record_count > 1
GROUP BY ALL
ORDER BY a.account_id
LIMIT 8;


-- show: 4. Billing migration: two formats in bronze, one in silver
SELECT b.invoice_id, b.invoice_date AS raw_date, b.amount AS raw_amount, b.currency,
       s.invoice_date AS clean_date, s.amount_local, s.amount_usd, s.billing_system
FROM bronze.billing_invoices b
JOIN silver.invoices s USING (invoice_id)
WHERE b.invoice_id IN ('INV-000100', 'INV-003000')
   OR b.invoice_id LIKE 'inv-2025-0040%'
ORDER BY s.invoice_date
LIMIT 6;


-- show: 5. Now dates are real dates, so they sort correctly (compare query 6 in file 01)
SELECT billing_system, min(invoice_date) AS first_invoice, max(invoice_date) AS last_invoice, count(*) AS invoices
FROM silver.invoices
GROUP BY billing_system
ORDER BY first_invoice;


-- show: 6. The June-July 2024 casing bug, fixed
SELECT 'bronze' AS layer, event_type, count(*) AS events
FROM bronze.app_usage_events
WHERE lower(event_type) LIKE 'log%'
GROUP BY ALL
UNION ALL
SELECT 'silver', event_type, count(*)
FROM silver.usage_events
WHERE event_type LIKE 'log%'
GROUP BY ALL
ORDER BY layer, events DESC;


-- show: 7. New facts silver can tell us: late-arriving and service-account events
SELECT count(*)                                           AS total_events,
       count(*) FILTER (WHERE is_late_arriving)           AS late_arriving,
       round(avg(ingestion_lag_hours) FILTER (WHERE is_late_arriving), 1) AS avg_late_lag_hours,
       count(*) FILTER (WHERE is_service_account_event)   AS service_account_events
FROM silver.usage_events;


-- show: 8. Types: silver columns are real dates, numbers and booleans now
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'silver' AND table_name = 'invoices'
ORDER BY ordinal_position;
